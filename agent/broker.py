"""agent/broker.py —— Aegis Agent/MCP 政策 broker（Python 侧现役决策面单源）。

审计第六轮（2026-10-03）：安全闭环——决策此前只存在于 pytest 文件的
**测试局部类**（`agent/tests/redteam_e2e_test.py:104` 的 E2EBroker，除该文件
外零消费方），而 `agent/local-ipc/identity.md`（SP-064）把"现役等价实现"
指向它——文档指针落在测试脚手架上，红队 fixtures 从未驱动过任何出厂代码。
本模块把决策面提取为可导入实现（消费 contracts/policy/action-catalog.yaml
单源），pytest 与红队 fixtures 一律消费本模块："deny by default" 自此有
真实被测对象。

`PolicyBroker` 实现的、且 Python 侧可实现的文档化不变量：

- default_deny：未登记 intent → DENY_UNKNOWN（catalog 缺失/损坏拒绝构造）
- scope 最小权限：intent→scope 按 catalog 逐条配对，跨配对拼装即拒（SP-142）
- 会话：session_id 缺失/空即拒（SP-140）；session↔tab_id 绑定，跨标签重放即拒
  （PY-252/260）
- 过期：expires_at 以 RFC3339 锚定（与发布链 update_verifier 同源——PY-282），
  到期即拒（<= 口径——PY-237），解析失败同拒；max_ttl 上限（SP-157）
- 政策版本：显式空串不回退 broker 默认（SP-159）
- 标签代际：与 broker 当前代际比对，代际只允许前进（SP-158）
- kill switch：revoke() 后一切评估拒绝（SP-013/ADR-004）
- 参数规范化：canonical_parameters 缺失即拒（SP-019——STDIO 注入面）
- 预算：per-action catalog 预算 + broker 侧 per-session 累计计数（自报值不
  可信——SP-148/149），deny 不计预算
- nonce：一次性（跨会话全局）+ 有界重放缓存（容量上限 + 最旧逐出——SP-156）
- 工具描述哈希：注册绑定后哈希必填且精确匹配；未注册而自带哈希无从校验
  同拒（SP-141）

明确**不**由本模块承担（OS 能力，Python 侧无实现——local-ipc/*.md 记有现状
注记）：OS ACL/套接字访问控制、连接进程 PID/可执行路径身份核验、IPC 传输与
每连接会话的建立、原生 kill switch UI 触发链。这些的真实强制点在
Windows C# `windows/src/Aegis.Windows.App/Broker/`、Android `android/broker/`、
Rust `core/rust-policy-core/src/broker.rs`。

安全校验写法（PY-187 口径）：一律显式 `raise`，绝不用裸 `assert`——
`PYTHONOPTIMIZE=1`/`-O` 在字节码编译期剥离断言，可剥离的门禁等于没有门禁。
"""

from __future__ import annotations

import dataclasses
import pathlib
import sys
import threading
import time
import uuid
from collections import OrderedDict
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any, ClassVar

import yaml

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
CATALOG_PATH = REPO_ROOT / "contracts" / "policy" / "action-catalog.yaml"
ACTION_SCHEMA_PATH = REPO_ROOT / "contracts" / "schemas" / "action.schema.json"

# PY-282（2026-10-02 审计）口径沿用：expires_at 解析复用发布链
# update_verifier 的 RFC3339 锚定正则单源（两套判定面不得漂移）。
_RELEASE_DIR = str(REPO_ROOT / "release")
if _RELEASE_DIR not in sys.path:
    sys.path.insert(0, _RELEASE_DIR)
from update_verifier import _RFC3339

__all__ = [
    "ACTION_SCHEMA_PATH",
    "CATALOG",
    "CATALOG_PATH",
    # 审计第六轮（2026-10-03）：删除从未实现的 "CONTRACT_REQUIRED" 导出——
    # __all__ 里的未定义名会让 from broker import CONTRACT_REQUIRED 抛
    # ImportError（F822 捕获）。契约必填面的权威判定在 action.schema.json
    # 与 redteam_e2e_test.test_field_set_matches_schema 的直接加载比对里，
    # 不需要本模块再复制一份常量。
    "BrokerConfigError",
    "BrokerInputError",
    "Decision",
    "PolicyBroker",
    "ProposedAction",
    "load_catalog",
    "parse_expires_at",
    "proposed_action_from_dict",
    "well_formed_action",
]


class BrokerConfigError(RuntimeError):
    """catalog 不满足 fail-closed 前提——broker 拒绝构造（显式异常，非 assert）。"""


class BrokerInputError(ValueError):
    """不可信载荷非法（未知字段/缺必填/类型不符）——拒绝，不静默降级。"""


def _is_positive_int(value: object) -> bool:
    """PY-251：正整数判定——bool 是 int 子类，显式排除（true 不得当 1 过门禁）。"""
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _is_int_not_bool(value: object) -> bool:
    """int 字段类型判定——允许 0/负数（超限由 evaluate 判定），仅排除 bool
    冒充整数（PY-251 同口径：`isinstance(True, int)` 为真）。"""
    return isinstance(value, int) and not isinstance(value, bool)


class Decision:
    """SP-068：结构化决策常量——调用方/断言读语义而非魔法字符串。"""

    ALLOW = "allow"
    DENY_UNKNOWN = "deny_unknown"            # 未登记 action（default_deny）
    DENY_SESSION = "deny_session"            # 缺/空/省略 session_id
    DENY_EXPIRED = "deny_expired"            # expires_at 已过（解析失败同拒——fail-closed）
    DENY_MAX_TTL = "deny_max_ttl"            # SP-157：expires_at 超过 max_ttl 上限
    DENY_POLICY = "deny_policy"              # policy_version 不匹配
    DENY_SCOPE = "deny_scope"                # scope 不在白名单/与 intent 配对不符
    DENY_GENERATION = "deny_generation"      # 标签代际过期
    DENY_REVOKED = "deny_revoked"            # kill switch 已撤销
    DENY_REPLAY = "deny_replay"              # nonce 重放（跨会话全局）
    DENY_BUDGET = "deny_budget"              # 超 max_actions（broker 侧计数判定）
    DENY_BYTES = "deny_budget_bytes"         # 超 max_bytes（broker 侧累计判定）
    DENY_CANONICAL = "deny_canonical"        # canonical_parameters 缺失/非法
    DENY_TAB = "deny_tab"                    # PY-252：session 已绑定其他 tab_id
    DENY_DESCRIPTION_HASH = "deny_description_hash"  # 工具描述哈希未批准/缺失
    DENY_PAYLOAD = "deny_payload"            # 载荷无法构造（无法判定 ≠ 放行）


@dataclasses.dataclass
class ProposedAction:
    """SP-150（2026-09-26 审计）：字段面与冻结 contracts/schemas/action.schema.json
    对齐——schema 必填的 tab_id/origin/method/document_generation 补齐为构造必填
    （不提供伪造契约数据的默认值）；expires_at 改 schema 口径（RFC3339 date-time
    字符串，不再是 unix 秒 float）。intent/budget_used/max_bytes/
    tool_description_hash 为 broker 判定层字段（catalog 派生判定与红队场景所需，
    schema 契约面无此四字段）。

    SP-140（2026-09-26 审计）：session_id 默认 None 即拒 DENY_SESSION——省略字段
    不再自带合法会话（fail-open 默认消除）。
    """

    intent: str                          # catalog action 名（default_deny 判定键）
    scope: str
    budget_used: int                     # 自报"已用次数"——SP-149：不可信，仅冗余校验
    nonce: str
    document_generation: int             # schema 口径字段名
    tab_id: str                          # schema 必填（minLength 1）
    origin: str                          # schema 必填（^https?://）
    method: str                          # schema 必填（GET/POST/PUT/DELETE/NAVIGATE/DOWNLOAD）
    tool_description_hash: str | None = None
    session_id: str | None = None        # SP-140：默认 None 即 DENY_SESSION
    expires_at: str | None = None        # SP-150：schema 口径 date-time 字符串；None = 不过期
    max_bytes: int = 0                   # 本调用数据体字节声明——SP-149：broker 累计判定
    canonical_parameters: str | None = None  # 参数规范化串（STDIO 注入面）
    policy_version: str | None = None    # None = 采用 broker 版本


def load_catalog(path: pathlib.Path | str = CATALOG_PATH) -> dict[str, Any]:
    """读取并校验 action-catalog——fail-closed（审计第六轮）。

    此前 catalog 损坏或 `default_deny` 被改成 false 时 broker 照常构造，
    "默认拒绝"只剩文档承诺。现逐项显式判定（不用 assert——PY-187）：顶层
    映射 / default_deny 必须为 true / policy_version 非空 / actions 非空且
    每条带 name+scope+正整数预算——任一不满足即 BrokerConfigError。
    """
    catalog_path = pathlib.Path(path)
    if not catalog_path.is_file():
        raise BrokerConfigError(f"action-catalog 缺失：{catalog_path}")
    try:
        doc = yaml.safe_load(catalog_path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise BrokerConfigError(f"action-catalog 解析失败：{exc}") from exc
    if not isinstance(doc, dict):
        raise BrokerConfigError("action-catalog 顶层必须是映射")
    if doc.get("default_deny") is not True:
        raise BrokerConfigError("action-catalog default_deny 必须显式为 true（fail-closed）")
    if not doc.get("policy_version"):
        raise BrokerConfigError("action-catalog 必须声明非空 policy_version（单源）")
    actions = doc.get("actions")
    if not isinstance(actions, list) or not actions:
        raise BrokerConfigError("action-catalog actions 必须是非空列表")
    for index, action in enumerate(actions):
        if not isinstance(action, dict):
            raise BrokerConfigError(f"actions[{index}] 非字典条目")
        if not action.get("name") or not action.get("scope"):
            raise BrokerConfigError(f"actions[{index}] 缺 name/scope（intent→scope 配对不可缺）")
        budget = action.get("budget")
        if not isinstance(budget, dict):
            raise BrokerConfigError(f"actions[{index}] budget 必须为映射")
        for key in ("max_actions", "max_bytes"):
            value = budget.get(key)
            # PY-251 口径：bool 是 int 子类——布尔预算不得冒充整数过门禁
            if not _is_positive_int(value):
                raise BrokerConfigError(
                    f"{action['name']} 需正整数 budget.{key}（当前: {value!r}）")
    return doc


CATALOG: dict[str, Any] = load_catalog()


def parse_expires_at(value: str) -> datetime | None:
    """SP-150（2026-09-26 审计）：expires_at 为 schema 口径 RFC3339 date-time
    字符串——解析失败返回 None（调用方 fail-closed 拒绝）；无时区按 UTC。
    PY-282（2026-10-02 审计）：与 update_verifier 口径对齐——先锚定
    RFC3339 形态（复用其 _RFC3339 正则单源），再 fromisoformat；裸日期/
    空格分隔等宽松形态不再被裸 fromisoformat 悄悄放行（两套判定面归一）。"""
    if not isinstance(value, str) or not _RFC3339.fullmatch(value):
        return None
    # 小写 t/z 分隔符归一（正则放行、fromisoformat 拒绝——PY-262 同款归一）
    normalized = value.replace("t", "T").replace("z", "Z")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed


def proposed_action_from_dict(data: Mapping[str, Any]) -> ProposedAction:
    """反序列化 ProposedAction（不可信输入的构造边界——审计第六轮）。

    红队 fixtures / 外部提交载荷由此进入 broker。三条 fail-closed 规则，
    任一不满足即 BrokerInputError（显式抛出，不用 assert——PY-187）：
    ① 未知字段拒绝（additionalProperties:false——拼错/多余字段不得静默
       丢弃：漏一个 `canonical_parameters` 键就等于漏一道参数规范化门）；
    ② 必填字段缺失拒绝（dataclass 无默认值字段 = broker 必填面）；
    ③ 字段类型逐个校验（int 字段排除 bool——PY-251 同口径）。
    """
    if not isinstance(data, Mapping):
        raise BrokerInputError(f"action 载荷必须是映射，实际 {type(data).__name__}")
    fields = {field.name: field for field in dataclasses.fields(ProposedAction)}
    unknown = sorted(set(data) - set(fields))
    if unknown:
        raise BrokerInputError(f"action 载荷含未知字段（additionalProperties:false）: {unknown}")
    absent = sorted(name for name, field in fields.items()
                    if field.default is dataclasses.MISSING and name not in data)
    if absent:
        raise BrokerInputError(f"action 载荷缺必填字段: {absent}")
    for name, value in data.items():
        annotation = str(fields[name].type)
        if annotation == "int":
            if not _is_int_not_bool(value):
                raise BrokerInputError(f"字段 {name} 必须为 int（bool 被拒——PY-251）: {value!r}")
        elif annotation == "str":
            if not isinstance(value, str):
                raise BrokerInputError(f"字段 {name} 必须为 str: {value!r}")
        elif annotation == "str | None":
            if value is not None and not isinstance(value, str):
                raise BrokerInputError(f"字段 {name} 必须为 str 或 None: {value!r}")
        elif annotation == "int | None":
            if value is not None and (not isinstance(value, int) or isinstance(value, bool)):
                raise BrokerInputError(f"字段 {name} 必须为 int 或 None: {value!r}")
    return ProposedAction(**dict(data))


def well_formed_action(intent: str = "get_current_title",
                       nonce: str | None = None,
                       **overrides: Any) -> ProposedAction:
    """well-formed 动作工厂（正路径基准——红队样例的最小合法底座）。

    scope 按 catalog intent→scope 配对自动填充（显式覆盖用于构造跨配对攻击
    样例）；nonce 缺省随机（同工厂多次调用不得自带重放）。
    """
    base: dict[str, Any] = {
        "intent": intent,
        "scope": PolicyBroker.INTENT_SCOPES.get(intent, ""),
        "budget_used": 1,
        "nonce": nonce if nonce is not None else uuid.uuid4().hex,
        "document_generation": 0,
        "tab_id": "tab-1",
        "origin": "https://example.test",
        "method": "GET",
        "session_id": "session-default",
        "canonical_parameters": "{}",
    }
    base.update(overrides)
    return ProposedAction(**base)


class PolicyBroker:
    """政策 broker（Default Deny——fail-closed——action-catalog 单源判定面）。"""

    # SP-009/010/014/022：intents/scope/版本从 action-catalog 单源派生
    # SP-142（2026-09-26 审计）：intent→scope 逐条配对映射（catalog 逐条登记）——
    # 取代独立 ALLOWED_SCOPES 成员判定（跨配对拼装如 get_current_origin +
    # tabs:read 即拒）
    INTENT_SCOPES: ClassVar[dict[str, str]] = {a["name"]: a["scope"] for a in CATALOG["actions"]}
    ALLOWED_INTENTS: ClassVar[frozenset[str]] = frozenset(INTENT_SCOPES)
    # SP-148（2026-09-26 审计）：per-action 预算逐条登记——DEFAULT_BUDGET 全局
    # fallback 字典已删（不再取第一条 action 的预算当全局默认）
    ACTION_BUDGETS: ClassVar[dict[str, dict]] = {
        a["name"]: dict(a.get("budget") or {}) for a in CATALOG["actions"]}
    CATALOG_VERSION: ClassVar[str] = str(CATALOG["policy_version"])
    # SP-157（2026-09-26 审计）：授权 TTL 上限（session.md——短生命周期语义）——
    # now+10 年的 expires_at 不再永久有效
    DEFAULT_MAX_TTL: ClassVar[float] = 300.0
    # SP-156（2026-09-26 审计）：consumed_nonces 有界——真机 broker 语义为
    # 有界重放缓存（容量上限+最旧逐出；窗口内重放必拒）
    NONCE_CACHE_CAPACITY: ClassVar[int] = 4096

    def __init__(self, policy_version: str | None = None, max_actions: int | None = None,
                 max_bytes: int | None = None, max_ttl: float | None = None):
        # SP-159（2026-09-26 审计）：is None 判定——显式 ""/0 不再被默认值吞掉
        # （显式 0 上限 = 全部拒绝——fail-closed 生效）
        self.policy_version = policy_version if policy_version is not None else self.CATALOG_VERSION
        # SP-148：None = 按 action.intent 查 catalog per-action 预算
        self.max_actions = max_actions
        self.max_bytes = max_bytes
        self.max_ttl = max_ttl if max_ttl is not None else self.DEFAULT_MAX_TTL
        # SP-156：有界重放缓存（OrderedDict——插入序即最旧序）
        self.consumed_nonces: OrderedDict[str, None] = OrderedDict()
        self.approved_descriptions: dict[str, str] = {}  # tool -> 已批准描述哈希
        self.revoked = False
        self.current_generation = 0  # SP-158：当前标签代际（advance_generation 推进）
        # SP-012/SP-149：nonce 消费与预算计数共用一把锁（检查/登记/累计同锁窗口——原子）
        self._state_lock = threading.Lock()
        self._session_actions: dict[str, int] = {}  # SP-149：per-session 累计计数
        self._session_bytes: dict[str, int] = {}
        # PY-252（2026-10-01 审计）：per-session tab 绑定——session.md 声称
        # "session 绑定 tab_id + document_generation——跨标签/代际变化使批准
        # 失效"，此前只比对代际。会话首笔固定 tab 绑定，后续同 session
        # 换 tab_id 即拒（跨标签重放面闭合）。
        self._session_tabs: dict[str, str] = {}

    def revoke(self) -> None:
        """SP-013：kill switch 撤销（ADR-004）——此后一切 evaluate 拒绝。"""
        self.revoked = True

    def advance_generation(self, generation: int) -> None:
        """SP-158（2026-09-26 审计）：标签代际推进（标签刷新/导航后调用）——
        只允许前进；回退尝试忽略（fail-closed：旧代际授权不因回退复活）。"""
        self.current_generation = max(self.current_generation, generation)

    def session_usage(self, session_id: str) -> tuple[int, int]:
        """SP-149：per-session 累计用量只读快照（actions, bytes）。"""
        with self._state_lock:
            return (self._session_actions.get(session_id, 0),
                    self._session_bytes.get(session_id, 0))

    def _limits(self, intent: str) -> tuple[int, int]:
        """SP-148：生效限额——构造器显式覆盖优先，否则按 intent 查 catalog
        per-action 预算（缺登记 fail-closed=0——全部拒绝）。"""
        budget = self.ACTION_BUDGETS.get(intent) or {}
        limit_actions = (self.max_actions if self.max_actions is not None
                         else budget.get("max_actions", 0))
        limit_bytes = (self.max_bytes if self.max_bytes is not None
                       else budget.get("max_bytes", 0))
        return limit_actions, limit_bytes

    def evaluate(self, action: ProposedAction) -> str:
        """Default Deny（fail-closed）——action-catalog（intent→scope 配对——
        SP-142 / per-action 预算——SP-148）+ 会话（SP-140）+ 过期/TTL 上限
        （SP-157）+ 版本 + 代际（SP-158）+ 撤销 + 参数规范化 + broker 侧
        per-session 累计预算（SP-149）+ 描述哈希（SP-141）+ nonce 一次性
        （跨会话全局——有界缓存 SP-156）+ 会话-tab 绑定（PY-252/260——锁内
        全部门禁通过后落绑定）。deny 不消费 nonce、不计预算（SP-066）。"""
        if action.intent not in self.ALLOWED_INTENTS:
            return Decision.DENY_UNKNOWN
        if not action.session_id:
            return Decision.DENY_SESSION  # SP-140：缺/空/省略 session_id 一律拒绝
        if action.expires_at is not None:
            expires = parse_expires_at(action.expires_at)
            now = time.time()
            # PY-237（2026-10-01 审计）：过期边界与 update_verifier 对齐（<=）——
            # expires 恰等于 now 即过期（此前用 < 留出 1 瞬窗口，两套口径）
            if expires is None or expires.timestamp() <= now:
                return Decision.DENY_EXPIRED  # 已过（含恰好到期）；解析失败同拒（fail-closed）
            if expires.timestamp() - now > self.max_ttl:
                return Decision.DENY_MAX_TTL  # SP-157：TTL 超上限——超长授权拒绝
        # SP-159：显式 "" policy_version 不再回退 broker 默认（falsy 吞没消除）
        actual_policy = (action.policy_version if action.policy_version is not None
                         else self.policy_version)
        if actual_policy != self.policy_version:
            return Decision.DENY_POLICY
        if self.INTENT_SCOPES.get(action.intent) != action.scope:
            # SP-142：intent→scope 配对一致（覆盖 scope 白名单——跨配对拼装即拒）
            return Decision.DENY_SCOPE
        if action.document_generation != self.current_generation:
            return Decision.DENY_GENERATION  # SP-158：与 broker 当前代际比对（可推进）
        # PY-252：per-session tab 绑定——同 session 换 tab_id 即拒。
        # PY-260（2026-10-02 审计）：绑定写入移进 _state_lock、置于全部门禁
        # 通过后——此前绑定在全部 deny 门之前且在锁外（deny 燃烧绑定 +
        # 并发竞态）。此处只保留只读预检（快速失败），不写状态。
        bound_tab = self._session_tabs.get(action.session_id)
        if bound_tab is not None and bound_tab != action.tab_id:
            return Decision.DENY_TAB
        if self.revoked:
            return Decision.DENY_REVOKED
        if action.canonical_parameters is None:
            return Decision.DENY_CANONICAL  # STDIO 参数注入面——参数必须规范化
        limit_actions, limit_bytes = self._limits(action.intent)
        if action.budget_used > limit_actions:
            # SP-149：自报值本身超限——冗余拒绝路径（真实判定以 broker 计数为准）
            return Decision.DENY_BUDGET
        session = action.session_id
        # SP-149：broker 侧 per-session 计数预检（无锁快速失败——最终以锁内复核为准）
        if self._session_actions.get(session, 0) + 1 > limit_actions:
            return Decision.DENY_BUDGET
        if self._session_bytes.get(session, 0) + action.max_bytes > limit_bytes:
            return Decision.DENY_BYTES
        approved = self.approved_descriptions.get(action.intent)
        if approved is not None:
            # SP-141：注册过 approved_descriptions 的工具——哈希必填且精确匹配
            # （省略/空串即拒——真值检查 `if hash:` 绕过面消除）
            if not action.tool_description_hash or action.tool_description_hash != approved:
                return Decision.DENY_DESCRIPTION_HASH
        elif action.tool_description_hash:
            # 未注册哈希绑定的工具自带哈希——无从校验——fail-closed（原语义保留）
            return Decision.DENY_DESCRIPTION_HASH  # 工具哈希绑定（CSA——描述变更需重新批准）
        # nonce 一次性 + 预算计数 + tab 绑定：检查/登记/累计/绑定必须同锁窗口
        # （原子——防并发双消费与并发超限——SP-012/SP-149；PY-260 补 tab 绑定）。
        # deny 不消费 nonce、不计预算、不燃烧 tab 绑定（SP-066/PY-260）。
        with self._state_lock:
            if action.nonce in self.consumed_nonces:
                return Decision.DENY_REPLAY
            # PY-260：会话-tab 绑定写入移到锁内全部门禁通过后——首笔放行才
            # 落绑定（deny 路径不再燃烧绑定）；并发首笔不同 tab 只有一笔能
            # 绑定，迟到者在锁内复核即拒（锁外竞态窗口消除）
            bound_tab = self._session_tabs.get(session)
            if bound_tab is None:
                self._session_tabs[session] = action.tab_id
            elif bound_tab != action.tab_id:
                return Decision.DENY_TAB
            if self._session_actions.get(session, 0) + 1 > limit_actions:  # 锁内复核
                return Decision.DENY_BUDGET
            if self._session_bytes.get(session, 0) + action.max_bytes > limit_bytes:
                return Decision.DENY_BYTES
            self.consumed_nonces[action.nonce] = None
            while len(self.consumed_nonces) > self.NONCE_CACHE_CAPACITY:
                self.consumed_nonces.popitem(last=False)  # SP-156：淘汰最旧（有界窗口）
            self._session_actions[session] = self._session_actions.get(session, 0) + 1
            self._session_bytes[session] = self._session_bytes.get(session, 0) + action.max_bytes
        return Decision.ALLOW

    def decide(self, payload: Mapping[str, Any] | ProposedAction) -> str:
        """不可信载荷 → 决策字符串（fixtures/外部提交的统一入口）。

        载荷无法构造（未知字段/缺必填/类型不符）本身即拒绝理由——返回
        DENY_PAYLOAD，绝不因"无法判定"而放行（fail-closed）。
        """
        if isinstance(payload, ProposedAction):
            return self.evaluate(payload)
        try:
            action = proposed_action_from_dict(payload)
        except BrokerInputError:
            return Decision.DENY_PAYLOAD
        return self.evaluate(action)

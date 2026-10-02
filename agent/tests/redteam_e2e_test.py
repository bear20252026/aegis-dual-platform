"""agent/tests/redteam_e2e_test.py —— 阶段 G 红队端到端（蓝图 agent/tests/）。

端到端断言：提示注入/工具投毒/scope 重放/标签代际/超预算/过期/跨会话重放/
并发竞态/撤销都不能导致未批准副作用（阶段 G 完成标准——ADR-004——kill switch
撤销）。模拟 broker 与 contracts/Windows Broker/AndroidBroker 同语义
（Default Deny——fail-closed——工具级 scope/每调用验证/工具描述哈希绑定）。

SP-A1（审计 2026-09-26）：intents/scope/预算/政策版本全部从
contracts/policy/action-catalog.yaml 单源派生（不再手工维护双源——SP-009/
010/014/022）；Decision 结构化常量替代魔法字符串（SP-068）；补
session_id/expires_at/max_bytes/canonical_parameters 字段与各自 fail-closed
分支+测试（SP-015/016/017/019）；nonce 消费线程安全（SP-012）；revoke()
撤销语义（SP-013）；描述哈希未批准分支与 deny 不消费 nonce（SP-011/066）。

SP-N1（审计 2026-09-26）：session_id 默认 None 即拒——省略字段不再自带合法
会话（SP-140）；注册过 approved_descriptions 的工具哈希必填——省略/空串即拒
（SP-141）；intent→scope 按 catalog 逐条配对——跨配对拼装即拒（SP-142）；
预算按 action.intent 查 per-action catalog 预算——删全局 fallback 字典
（SP-148）；budget_used/max_bytes 自报不可信——broker 侧 per-session 累计
计数（锁内 check-and-increment）判定（SP-149）；ProposedAction 字段面直读
冻结 action.schema.json 对齐——补 tab_id/origin/method/document_generation、
expires_at 改 schema 口径 date-time 字符串（SP-150）；consumed_nonces 有界
重放缓存（SP-156）；expires_at 增 max_ttl 上限（SP-157）；broker 持当前
代际（可推进）比对（SP-158）；policy_version/max_actions 等显式 falsy 值
不再被默认吞掉（SP-159）。
"""

from __future__ import annotations

import dataclasses
import json
import pathlib
import sys
import threading
import time
import uuid
from collections import OrderedDict
from datetime import UTC, datetime, timedelta
from typing import ClassVar
from unittest import mock

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
CATALOG = yaml.safe_load(
    (ROOT.parent / "contracts/policy/action-catalog.yaml").read_text(encoding="utf-8"))

# PY-282（2026-10-02 审计）：expires_at 解析复用发布链 update_verifier 的
# RFC3339 锚定正则单源（此前 e2e 侧裸 fromisoformat——宽于 schema
# format:date-time 口径，两套判定面漂移）。
sys.path.insert(0, str(ROOT.parent / "release"))
from update_verifier import _RFC3339


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
    DENY_TAB = "deny_tab"                      # PY-252：session 已绑定其他 tab_id
    DENY_DESCRIPTION_HASH = "deny_description_hash"  # 工具描述哈希未批准/缺失


@dataclasses.dataclass
class ProposedAction:
    """SP-150（2026-09-26 审计）：字段面与冻结 contracts/schemas/action.schema.json
    对齐——schema 必填的 tab_id/origin/method/document_generation 补齐为构造必填
    （不提供伪造契约数据的默认值）；expires_at 改 schema 口径（RFC3339 date-time
    字符串，不再是 unix 秒 float）。intent/budget_used/max_bytes/
    tool_description_hash 为 e2e 模拟层字段（catalog 派生判定与红队场景所需，
    schema 契约面无此四字段）。

    SP-140（2026-09-26 审计）：session_id 默认 None——省略字段即 DENY_SESSION
    （不再自带合法会话——fail-open 默认消除）。
    """

    intent: str                          # 模拟层：catalog action 名（default_deny 判定键）
    scope: str
    budget_used: int                     # 自报"已用次数"——SP-149：不可信，仅冗余校验
    nonce: str
    document_generation: int             # schema 口径字段名（原 e2e 字段名 generation——漂移已对齐）
    tab_id: str                          # schema 必填（minLength 1）
    origin: str                          # schema 必填（^https?://）
    method: str                          # schema 必填（GET/POST/PUT/DELETE/NAVIGATE/DOWNLOAD）
    tool_description_hash: str | None = None
    session_id: str | None = None        # SP-140：默认 None 即 DENY_SESSION
    expires_at: str | None = None        # SP-150：schema 口径 date-time 字符串；None = 不过期
    max_bytes: int = 0                   # 本调用数据体字节声明——SP-149：broker 累计判定
    canonical_parameters: str | None = None  # 参数规范化串（STDIO 注入面）
    policy_version: str | None = None    # None = 采用 broker 版本


class E2EBroker:
    """红队 e2e 模拟 broker（与 contracts Decision 语义一致——Default Deny）。"""

    # SP-009/010/014/022：intents/scope/版本从 action-catalog 单源派生
    # SP-142（2026-09-26 审计）：intent→scope 逐条配对映射（catalog 逐条登记）——
    # 取代独立 ALLOWED_SCOPES 成员判定（跨配对拼装如 get_current_origin +
    # tabs:read 即拒）
    INTENT_SCOPES: ClassVar[dict[str, str]] = {a["name"]: a["scope"] for a in CATALOG["actions"]}
    ALLOWED_INTENTS: frozenset[str] = frozenset(INTENT_SCOPES)
    # SP-148（2026-09-26 审计）：per-action 预算逐条登记——DEFAULT_BUDGET 全局
    # fallback 字典已删（不再取第一条 action 的预算当全局默认）
    ACTION_BUDGETS: ClassVar[dict[str, dict]] = {
        a["name"]: dict(a.get("budget") or {}) for a in CATALOG["actions"]}
    CATALOG_VERSION: str = str(CATALOG["policy_version"])
    # SP-157（2026-09-26 审计）：授权 TTL 上限（session.md——短生命周期语义）——
    # now+10 年的 expires_at 不再永久有效
    DEFAULT_MAX_TTL: float = 300.0
    # SP-156（2026-09-26 审计）：consumed_nonces 有界——真机 broker 语义为
    # 有界重放缓存（容量上限+最旧逐出；窗口内重放必拒）
    NONCE_CACHE_CAPACITY: int = 4096

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
        # 失效"，此前模拟面只比对代际。会话首笔固定 tab 绑定，后续同 session
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
        budget = self.ACTION_BUDGETS[intent]
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
            expires = _parse_expires_at(action.expires_at)
            now = time.time()
            # PY-237（2026-10-01 审计）：过期边界与 update_verifier 对齐（<=）——
            # expires 恰等于 now 即过期（此前 e2e 用 < 留出 1 瞬窗口，两套口径）
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


def _parse_expires_at(value: str) -> datetime | None:
    """SP-150（2026-09-26 审计）：expires_at 为 schema 口径 RFC3339 date-time
    字符串——解析失败返回 None（调用方 fail-closed 拒绝）；无时区按 UTC。
    PY-282（2026-10-02 审计）：与 update_verifier 口径对齐——先锚定
    RFC3339 形态（复用其 _RFC3339 正则单源），再 fromisoformat；裸日期/
    空格分隔等宽松形态不再被 fromisoformat 悄悄放行（两套判定面归一）。"""
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


def _ok(intent: str = "get_current_title", **kw) -> ProposedAction:
    """well-formed 动作工厂——显式提供全部契约必填字段。
    SP-142：scope 按 catalog intent→scope 配对自动填充（显式传参可覆盖——
    用于构造跨配对攻击样例）。"""
    base = {"intent": intent, "scope": E2EBroker.INTENT_SCOPES.get(intent, "tabs:read"),
            "budget_used": 1, "nonce": uuid.uuid4().hex, "document_generation": 0,
            "tab_id": "tab-1", "origin": "https://example.test", "method": "GET",
            "session_id": "session-default", "canonical_parameters": "{}"}
    base.update(kw)
    return ProposedAction(**base)


def test_prompt_injection_denied():
    """网页内容提示注入（ignore instructions——导出书签）——无法产生副作用。"""
    broker = E2EBroker()
    injected = ProposedAction(intent="export_bookmarks", scope="tabs:read",
                              budget_used=1, nonce="n1", document_generation=0,
                              tab_id="tab-1", origin="https://example.test",
                              method="GET", canonical_parameters="{}")
    assert broker.evaluate(injected) == Decision.DENY_UNKNOWN  # 未登记 action（default_deny）


def test_tool_poisoning_description_hash():
    """工具投毒（工具描述注入恶意指令）——描述哈希变更需重新批准（CSA 官方）。"""
    broker = E2EBroker()
    broker.approved_descriptions["get_current_title"] = "hash-approved"
    poisoned = _ok(tool_description_hash="hash-poisoned")  # 投毒后描述
    assert broker.evaluate(poisoned) == Decision.DENY_DESCRIPTION_HASH


def test_description_hash_honored_when_approved():
    """已批准哈希精确匹配——放行（哈希语义正路径）。"""
    broker = E2EBroker()
    broker.approved_descriptions["get_current_title"] = "hash-approved"
    assert broker.evaluate(_ok(tool_description_hash="hash-approved")) == Decision.ALLOW


def test_description_hash_required_when_registered():
    """SP-141（2026-09-26 审计）：注册过 approved_descriptions 的工具——哈希必填：
    省略字段（None）/空串均拒绝（真值检查绕过面消除）；未注册工具不受影响。"""
    broker = E2EBroker()
    broker.approved_descriptions["get_current_title"] = "hash-approved"
    assert broker.evaluate(_ok(nonce="h1")) == Decision.DENY_DESCRIPTION_HASH  # 省略哈希字段
    assert broker.evaluate(_ok(nonce="h2", tool_description_hash="")) == Decision.DENY_DESCRIPTION_HASH
    assert broker.evaluate(_ok(nonce="h3", tool_description_hash="hash-approved")) == Decision.ALLOW
    # 未注册哈希绑定的工具：省略哈希不受影响（哈希绑定按工具配对注册生效）
    origin = _ok(intent="get_current_origin", nonce="h4")
    assert origin.tool_description_hash is None
    assert broker.evaluate(origin) == Decision.ALLOW


def test_replay_and_generation():
    """scope 重放（nonce 复用）+ 标签代际变化——拒绝。"""
    broker = E2EBroker()
    ok = _ok(nonce="n3")
    assert broker.evaluate(ok) == Decision.ALLOW
    replayed = _ok(budget_used=2, nonce="n3")  # 重放同一 nonce
    assert broker.evaluate(replayed) == Decision.DENY_REPLAY
    stale = _ok(nonce="n4", document_generation=2)  # 标签代际过期
    assert broker.evaluate(stale) == Decision.DENY_GENERATION


def test_generation_advances_with_broker_state():
    """SP-158（2026-09-26 审计）：broker 持当前代际（可推进）——合法新代际
    （推进后 =1）放行，旧代际（=0）随即失效；代际回退尝试被忽略（fail-closed）。"""
    broker = E2EBroker()
    assert broker.evaluate(_ok(nonce="gen0")) == Decision.ALLOW  # 当前代际 0
    assert broker.evaluate(_ok(nonce="gen1", document_generation=1)) == Decision.DENY_GENERATION
    broker.advance_generation(1)  # 标签刷新/导航——代际推进
    assert broker.evaluate(_ok(nonce="gen2", document_generation=1)) == Decision.ALLOW
    assert broker.evaluate(_ok(nonce="gen3", document_generation=0)) == Decision.DENY_GENERATION
    broker.advance_generation(0)  # 回退尝试——被忽略
    assert broker.current_generation == 1
    assert broker.evaluate(_ok(nonce="gen4", document_generation=0)) == Decision.DENY_GENERATION


def test_resource_budget():
    """超预算——自报 budget_used 本身超限即拒（SP-149 冗余校验——保留原拒绝
    路径；真实判定以 broker 侧 per-session 累计计数为准——见累计计数用例）。"""
    broker = E2EBroker(max_actions=5)
    over = _ok(budget_used=6, nonce="n5")
    assert broker.evaluate(over) == Decision.DENY_BUDGET


def test_budget_bytes():
    """SP-016：超 max_bytes（数据体预算）——拒绝。"""
    broker = E2EBroker(max_bytes=1024)
    assert broker.evaluate(_ok(max_bytes=2048)) == Decision.DENY_BYTES
    assert broker.evaluate(_ok(max_bytes=512)) == Decision.ALLOW


def test_per_action_budget_from_catalog():
    """SP-148（2026-09-26 审计）：预算按 action.intent 逐条查 catalog 判定
    （DEFAULT_BUDGET 全局 fallback 字典已删——逐条预算字段真实生效）。
    （临时替换类级 ACTION_BUDGETS——mock 自恢复，不经 pytest 也能跑。）"""
    budgets = {name: dict(spec) for name, spec in E2EBroker.ACTION_BUDGETS.items()}
    budgets["get_current_title"]["max_actions"] = 2
    with mock.patch.object(E2EBroker, "ACTION_BUDGETS", budgets):
        broker = E2EBroker()
        assert broker.evaluate(_ok(nonce="pb1")) == Decision.ALLOW
        assert broker.evaluate(_ok(nonce="pb2")) == Decision.ALLOW
        assert broker.evaluate(_ok(nonce="pb3")) == Decision.DENY_BUDGET  # title 限额 2——第 3 次拒
        # 其他 action 不受影响——按各自 catalog 预算独立判定
        assert broker.evaluate(_ok(intent="get_current_origin", nonce="pb4")) == Decision.ALLOW


def test_session_cumulative_budget_counter():
    """SP-148/149（2026-09-26 审计）：broker 侧 per-session 累计计数判定——
    catalog per-action 预算（max_actions=5）达限后第 N+1 次拒绝；deny 不计数。"""
    broker = E2EBroker()
    for i in range(5):
        assert broker.evaluate(_ok(nonce=f"cum{i}")) == Decision.ALLOW
    assert broker.evaluate(_ok(nonce="cum-deny-first", scope="")) == Decision.DENY_SCOPE
    assert broker.session_usage("session-default") == (5, 0)  # deny 未计入
    assert broker.evaluate(_ok(nonce="cum-over")) == Decision.DENY_BUDGET


def test_self_reported_budget_lie_still_denied():
    """SP-149（2026-09-26 审计）：自报预算不可信——broker 侧 per-session 累计
    计数判定：恒报 budget_used=1 的谎报在真实计数达限后仍被拒；字节数逐笔
    累计——拆分传输累计超限同样拒绝（计数在锁窗口内推进——并发安全）。"""
    broker = E2EBroker()
    for i in range(5):
        # 每次自报 budget_used=1（谎报——从未承认累计用量）
        assert broker.evaluate(_ok(nonce=f"lie{i}", budget_used=1)) == Decision.ALLOW
    # broker 真实计数已达 5——第 6 次即使仍自报 1 也被拒
    assert broker.evaluate(_ok(nonce="lie-over", budget_used=1)) == Decision.DENY_BUDGET

    broker2 = E2EBroker()
    assert broker2.evaluate(_ok(nonce="by1", max_bytes=32768)) == Decision.ALLOW
    assert broker2.evaluate(_ok(nonce="by2", max_bytes=32768)) == Decision.ALLOW  # 累计 = 上限
    assert broker2.evaluate(_ok(nonce="by3", max_bytes=1)) == Decision.DENY_BYTES  # 累计超限
    assert broker2.session_usage("session-default") == (2, 65536)


def test_explicit_zero_override_honored():
    """SP-159（2026-09-26 审计）：构造器显式 0 上限生效（is None 判定——显式
    falsy 值不再被默认吞掉——0 = 全部拒绝，fail-closed）。"""
    broker = E2EBroker(max_actions=0)
    assert broker.evaluate(_ok(nonce="z1")) == Decision.DENY_BUDGET


def test_scope_minimal_privilege():
    """工具级 scope 最小权限——登记的 action 携带未授权 scope——一律拒绝。"""
    broker = E2EBroker()
    assert broker.evaluate(_ok(intent="get_current_origin", scope="downloads:read")) == Decision.DENY_SCOPE
    assert broker.evaluate(_ok(scope="")) == Decision.DENY_SCOPE
    assert broker.evaluate(_ok(scope="navigation:read", intent="get_current_origin")) == Decision.ALLOW


def test_intent_scope_cross_pairing_denied():
    """SP-142（2026-09-26 审计）：intent→scope 配对一致（catalog 逐条绑定）——
    get_current_origin 搭配另一 action 的 tabs:read 必须拒绝（独立成员判定消除）。"""
    broker = E2EBroker()
    cross = _ok(intent="get_current_origin", scope="tabs:read", nonce="x1")
    assert broker.evaluate(cross) == Decision.DENY_SCOPE
    # 正配对不受影响（不误伤合法组合）
    assert broker.evaluate(_ok(intent="get_current_origin", scope="navigation:read",
                               nonce="x2")) == Decision.ALLOW
    assert broker.evaluate(_ok(intent="get_current_title", scope="tabs:read",
                               nonce="x3")) == Decision.ALLOW


def test_cross_session_replay_denied():
    """SP-015：nonce 消费跨会话全局——同一 nonce 换会话仍拒绝（重放不跨会话复活）。"""
    broker = E2EBroker()
    assert broker.evaluate(_ok(nonce="shared")) == Decision.ALLOW
    cross = _ok(session_id="other-session", nonce="shared")
    assert broker.evaluate(cross) == Decision.DENY_REPLAY


def test_empty_session_rejected():
    """SP-015：缺/空 session_id——deny_session（会话上下文是授权前提）。"""
    assert E2EBroker().evaluate(_ok(session_id="")) == Decision.DENY_SESSION


def test_omitted_session_id_rejected():
    """SP-140（2026-09-26 审计）：省略 session_id 字段（默认 None）——deny_session
    （默认值不再自带合法会话——fail-open 默认消除）。"""
    broker = E2EBroker()
    omitted = ProposedAction(intent="get_current_title", scope="tabs:read",
                             budget_used=1, nonce=uuid.uuid4().hex,
                             document_generation=0, tab_id="tab-1",
                             origin="https://example.test", method="GET",
                             canonical_parameters="{}")
    assert omitted.session_id is None  # 默认 None——不再预置合法会话
    assert broker.evaluate(omitted) == Decision.DENY_SESSION


def test_expiry_enforced():
    """SP-017：expires_at 过期——deny_expired；未过期——放行。
    SP-150：expires_at 为 schema 口径 RFC3339 date-time 字符串。
    SP-157：解析失败 fail-closed 视同过期（无宽限）。"""
    broker = E2EBroker()
    now = datetime.now(UTC)
    assert broker.evaluate(_ok(
        nonce="e1", expires_at=(now - timedelta(seconds=10)).isoformat())) == Decision.DENY_EXPIRED
    assert broker.evaluate(_ok(
        nonce="e2", expires_at=(now + timedelta(seconds=10)).isoformat())) == Decision.ALLOW
    assert broker.evaluate(_ok(nonce="e3", expires_at=None)) == Decision.ALLOW  # 不过期显式
    assert broker.evaluate(_ok(nonce="e4", expires_at="not-a-timestamp")) == Decision.DENY_EXPIRED


def test_expiry_boundary_inclusive_denied():
    """PY-237（2026-10-01 审计）：expires_at 恰等于 now 即过期——与
    update_verifier 的 <= 口径对齐（此前 e2e 用 < 留出同瞬放行窗口，
    发布链验证器与 e2e 模拟面边界分叉）。"""
    import time as _time
    broker = E2EBroker()
    frozen = datetime(2030, 1, 1, tzinfo=UTC)
    original = _time.time
    try:
        _time.time = lambda: frozen.timestamp()
        assert broker.evaluate(_ok(
            nonce="eq1", expires_at=frozen.isoformat())) == Decision.DENY_EXPIRED
        one_ns_later = frozen + timedelta(microseconds=1)
        assert broker.evaluate(_ok(
            nonce="eq2", expires_at=one_ns_later.isoformat())) == Decision.ALLOW
    finally:
        _time.time = original


def test_session_tab_binding_enforced():
    """PY-252（2026-10-01 审计）：session 绑定 tab_id——同 session 首笔固定
    绑定，换 tab_id 即 DENY_TAB（session.md 声称的跨标签失效语义落地——
    此前模拟面只比对代际，窄于文档）。"""
    broker = E2EBroker()
    assert broker.evaluate(_ok(nonce="t1", tab_id="tab-1")) == Decision.ALLOW
    # 同 session 换 tab：拒绝（跨标签重放/劫持面）
    assert broker.evaluate(_ok(nonce="t2", tab_id="tab-2")) == Decision.DENY_TAB
    # 原 tab 继续：放行（绑定未失效）
    assert broker.evaluate(_ok(nonce="t3", tab_id="tab-1")) == Decision.ALLOW
    # 不同 session 各自独立绑定同一 tab：互不影响
    assert broker.evaluate(_ok(nonce="t4", tab_id="tab-1",
                               session_id="session-b")) == Decision.ALLOW
    assert broker.evaluate(_ok(nonce="t5", tab_id="tab-9",
                               session_id="session-b")) == Decision.DENY_TAB


def test_deny_does_not_burn_tab_binding():
    """PY-260（2026-10-02 审计）：deny 不燃烧会话-tab 绑定——绑定写入移进
    _state_lock、置于全部门禁通过后。此前绑定在全部 deny 门之前且在锁外：
    首笔被 deny（scope/撤销/预算/重放…）的请求也会固定 tab 绑定，后续合法
    tab 的请求被无端 DENY_TAB（deny 燃烧绑定）；且锁外写入与并发评估竞态。"""
    # 场景①：撤销后首笔（tab-1）被拒——绑定不得落在 tab-1 上
    broker = E2EBroker()
    broker.revoke()
    assert broker.evaluate(_ok(nonce="nb1", tab_id="tab-1")) == Decision.DENY_REVOKED
    assert broker._session_tabs == {}  # deny 未燃烧绑定（绑定表空）
    broker.revoked = False  # 撤销恢复（仅测试构造）
    assert broker.evaluate(_ok(nonce="nb2", tab_id="tab-2")) == Decision.ALLOW
    # 场景②：换 tab 的请求被 DENY_TAB 拒绝后，原 tab 请求继续放行——
    # 拒绝路径不覆盖/不破坏既有绑定
    assert broker.evaluate(_ok(nonce="nb3", tab_id="tab-9")) == Decision.DENY_TAB
    assert broker.evaluate(_ok(nonce="nb4", tab_id="tab-2")) == Decision.ALLOW
    # 场景③：scope deny 首笔同样不燃烧绑定
    broker2 = E2EBroker()
    denied = _ok(scope="downloads:read", nonce="nb5", tab_id="tab-1")
    assert broker2.evaluate(denied) == Decision.DENY_SCOPE
    assert broker2._session_tabs == {}
    assert broker2.evaluate(_ok(nonce="nb6", tab_id="tab-7")) == Decision.ALLOW


def test_concurrent_first_binding_single_winner():
    """PY-260（2026-10-02 审计）：并发首笔绑定无竞态——多线程同时以不同
    tab_id 评估同一 session 时，恰好一笔完成绑定（其余 DENY_TAB），绑定表
    不因锁外写入出现后写覆盖先写的双绑定窗口。"""
    n_threads = 8
    broker = E2EBroker(max_actions=n_threads)  # 提升限额——隔离绑定语义
    results: list[str] = []
    lock = threading.Lock()

    def worker(i: int) -> None:
        decision = broker.evaluate(_ok(nonce=f"race{i}", tab_id=f"tab-{i}"))
        with lock:
            results.append(decision)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(n_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    # 恰好一笔 ALLOW（首笔绑定者），其余全部 DENY_TAB——无双绑定/无丢失
    assert results.count(Decision.ALLOW) == 1, results
    assert results.count(Decision.DENY_TAB) == n_threads - 1
    assert len(broker._session_tabs) == 1


def test_expires_at_rfc3339_anchored():
    """PY-282（2026-10-02 审计）：expires_at 解析与 update_verifier._RFC3339
    锚定口径对齐——裸日期/空格分隔/无时区等宽松形态在 e2e 侧同样拒绝
    （DENY_EXPIRED fail-closed），不再被裸 fromisoformat 悄悄放行。"""
    broker = E2EBroker()
    # 宽松形态（fromisoformat 可解析但非 RFC3339）→ 拒绝（对齐 schema 口径）
    for bad in ("2026-01-01", "2026-01-01 12:00:00Z", "2026-01-01T12:00:00"):
        assert broker.evaluate(_ok(nonce=f"an{bad}", expires_at=bad)) == Decision.DENY_EXPIRED, bad
    # 小写 t/z 分隔符——正则放行 + 归一后可解析（PY-262 同款归一口径）
    near = datetime.now(UTC) + timedelta(seconds=30)  # TTL 上限内
    assert broker.evaluate(_ok(
        nonce="an-lower",
        expires_at=near.strftime("%Y-%m-%dt%H:%M:%Sz"))) == Decision.ALLOW
    # 标准 RFC3339（大写 T/Z 与 ±HH:MM 偏移）不受影响
    assert broker.evaluate(_ok(
        nonce="an-upper",
        expires_at=near.strftime("%Y-%m-%dT%H:%M:%SZ"))) == Decision.ALLOW
    assert broker.evaluate(_ok(
        nonce="an-off",
        expires_at=near.strftime("%Y-%m-%dT%H:%M:%S") + "+00:00")) == Decision.ALLOW


def test_max_ttl_enforced():
    """SP-157（2026-09-26 审计）：expires_at 超过 max_ttl——拒绝（now+10 年的
    授权不再永久有效）；TTL 内仍放行；构造器可收紧 max_ttl。"""
    broker = E2EBroker()
    far = (datetime.now(UTC) + timedelta(days=3650)).isoformat()
    assert broker.evaluate(_ok(nonce="ttl1", expires_at=far)) == Decision.DENY_MAX_TTL
    near = (datetime.now(UTC) + timedelta(seconds=10)).isoformat()
    assert broker.evaluate(_ok(nonce="ttl2", expires_at=near)) == Decision.ALLOW
    tight = E2EBroker(max_ttl=5.0)
    assert tight.evaluate(_ok(nonce="ttl3", expires_at=near)) == Decision.DENY_MAX_TTL


def test_policy_version_enforced():
    """SP-014：policy_version 不匹配——deny_policy（策略升级后旧授权失效）。
    SP-159：显式空串 policy_version 不再回退 broker 默认（falsy 吞没消除）。"""
    broker = E2EBroker(policy_version="1.0")
    assert broker.evaluate(_ok(nonce="p1", policy_version="0.9")) == Decision.DENY_POLICY
    assert broker.evaluate(_ok(nonce="p2", policy_version="1.0")) == Decision.ALLOW
    assert broker.evaluate(_ok(nonce="p3", policy_version="")) == Decision.DENY_POLICY


def test_canonical_parameters_required():
    """SP-019：canonical_parameters 缺失——deny_canonical（STDIO 参数注入面）。"""
    assert E2EBroker().evaluate(_ok(canonical_parameters=None)) == Decision.DENY_CANONICAL


def test_deny_does_not_consume_nonce():
    """SP-066：deny 不消费 nonce——失败分支后同 nonce 仍可合法放行一次。"""
    broker = E2EBroker()
    denied = _ok(scope="downloads:read", nonce="keep")
    assert broker.evaluate(denied) == Decision.DENY_SCOPE
    assert broker.evaluate(_ok(nonce="keep")) == Decision.ALLOW  # 未被 deny 消费


def test_revoke_blocks_everything():
    """SP-013：revoke()（kill switch）后一切 approve 尝试拒绝。"""
    broker = E2EBroker()
    broker.revoke()
    assert broker.evaluate(_ok()) == Decision.DENY_REVOKED
    assert broker.evaluate(_ok(intent="get_current_origin")) == Decision.DENY_REVOKED


def test_concurrent_nonce_consumption():
    """SP-012：8 线程并发唯一 nonce——恰好消费一次（无双消费/丢失）。
    SP-149：per-session 预算计数并发安全——限额提升到用例规模后全部放行，
    broker 侧计数恰等于放行数。"""
    n_threads, per_thread = 8, 32
    broker = E2EBroker(max_actions=n_threads * per_thread)  # 提升限额——隔离 nonce 并发语义
    nonces = [uuid.uuid4().hex for _ in range(n_threads * per_thread)]
    results: list[list[str]] = [[] for _ in range(n_threads)]

    def worker(ti: int) -> None:
        for i in range(per_thread):
            results[ti].append(broker.evaluate(_ok(nonce=nonces[ti * per_thread + i])))

    threads = [threading.Thread(target=worker, args=(ti,)) for ti in range(n_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    flat = [r for group in results for r in group]
    assert flat.count(Decision.ALLOW) == n_threads * per_thread  # 全部唯一 → 全部放行
    assert len(broker.consumed_nonces) == n_threads * per_thread  # 恰好各一次
    assert broker.session_usage("session-default") == (n_threads * per_thread, 0)  # 计数无丢失


def test_nonce_cache_bounded():
    """SP-156（2026-09-26 审计）：consumed_nonces 有界——容量上限+最旧逐出
    （真机 broker 语义：有界重放缓存——窗口内重放必拒；窗口外随逐出失效）。
    （临时调小容量常量——mock 自恢复，不经 pytest 也能跑。）"""
    with mock.patch.object(E2EBroker, "NONCE_CACHE_CAPACITY", 8):
        broker = E2EBroker(max_actions=64)
        for i in range(12):
            assert broker.evaluate(_ok(nonce=f"cap{i}")) == Decision.ALLOW
        assert len(broker.consumed_nonces) == 8          # 容量封顶——不再无界增长
        assert "cap0" not in broker.consumed_nonces      # 最旧已逐出
        assert "cap11" in broker.consumed_nonces         # 最新仍在窗口内
        assert broker.evaluate(_ok(nonce="cap11")) == Decision.DENY_REPLAY  # 窗口内重放仍拒


def test_field_set_matches_schema():
    """SP-067/SP-150（2026-09-26 审计）：直接加载冻结 action.schema.json 提取
    required/properties 集合与 ProposedAction 字段集对比——不再手写集合自证
    （契约新增/删除字段即元断言失败，强制 e2e 模型对齐冻结契约）。"""
    schema = json.loads(
        (ROOT.parent / "contracts/schemas/action.schema.json").read_text(encoding="utf-8"))
    fields = {f.name for f in dataclasses.fields(ProposedAction)}
    required = set(schema["required"])
    assert required <= fields, f"e2e 模型缺 schema 必填字段: {sorted(required - fields)}"
    properties = set(schema.get("properties", {}))
    assert properties <= fields, f"e2e 模型缺 schema 声明字段: {sorted(properties - fields)}"
    # SP-150：expires_at 类型以 schema 为准（string date-time——不再是 unix 秒 float）
    expires_at = next(f for f in dataclasses.fields(ProposedAction) if f.name == "expires_at")
    assert expires_at.type == "str | None"


if __name__ == "__main__":
    # 保留原独立运行入口（不经 pytest 也能跑）——逐用例异常捕获+汇总
    failures = []
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"  ✅ {name}")
            except Exception as ex:  # noqa: BLE001
                failures.append((name, ex))
                print(f"  ❌ {name}: {ex}")
    if failures:
        raise SystemExit(f"{len(failures)} 失败")
    print("ALL OK — 阶段 G 红队 e2e 通过")

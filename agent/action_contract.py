"""R7-TOOL-02（第七轮 2026-10-04）：冻结 `contracts/schemas/action.schema.json`
的**判定面**兑现（此前只有字段名对齐，没有判定）。

缺陷形态：`PolicyBroker.evaluate()` 只在 `expires_at is not None` 时才查过期与
`max_ttl`，且**从不**校验 `origin` 的 `^https?://` pattern 与 `method` 的 enum——
而契约把 `expires_at`/`origin`/`method`/`policy_version`/`nonce`/`tab_id` 列为
required。后果是「省略 expires_at 即得到永久有效授权」，`file:///C:/secrets`、
`javascript:alert(1)`、`method=ARBITRARY` 全部 allow；红队夹具还把「不带
expires_at 放行」钉成 allow 对照，即门禁反向保护该缺陷。既有
`test_field_set_matches_schema` 只比对字段名集合（`required ⊆ fields`），
所以这块缺口一直显示为「契约已对齐」。

本模块的口径：
- 必填集 / 枚举 / pattern / minLength **从 schema 现算**，不在 Python 侧手抄第二份
  （抄一份就再造一个漂移面）；
- 违背契约是一条独立拒绝码 `deny_schema`——与 `contracts/vectors` 既有词汇一致；
- schema 读不到 / 结构不合预期即 `ActionContractError`，broker 拒绝构造
  （"读不到就算通过" 是本项目已封的失效形态）。
"""

from __future__ import annotations

import dataclasses
import json
import pathlib
import re
import sys
from datetime import UTC, datetime
from typing import Any

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
ACTION_SCHEMA_PATH = REPO_ROOT / "contracts" / "schemas" / "action.schema.json"

# PY-282（2026-10-02 审计）口径沿用：expires_at 解析复用发布链
# update_verifier 的 RFC3339 锚定正则单源（两套判定面不得漂移）。
_RELEASE_DIR = str(REPO_ROOT / "release")
if _RELEASE_DIR not in sys.path:
    sys.path.insert(0, _RELEASE_DIR)
from update_verifier import _RFC3339


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

# 本模块判定面依赖的 schema 声明项——缺任一项即契约不可读（fail-closed）
_NEEDED_PROPERTIES = ("origin", "method")


class ActionContractError(RuntimeError):
    """冻结 action.schema.json 不可读或结构不符——broker 拒绝构造。"""


def load_action_schema(path: pathlib.Path = ACTION_SCHEMA_PATH) -> dict[str, Any]:
    """读取并校验 schema 结构（fail-closed，显式 raise，绝不用裸 assert——PY-187）。

    只验本模块要用到的最小面：required 非空、properties 非空、origin 带 pattern、
    method 带非空 enum。任一不满足即拒绝——静默降级成"没有必填集"等于回到修复前。
    """
    try:
        raw = pathlib.Path(path).read_text(encoding="utf-8")
    except OSError as exc:
        raise ActionContractError(f"action schema 不可读：{path}（{exc}）") from exc
    try:
        doc = json.loads(raw)
    except ValueError as exc:
        raise ActionContractError(f"action schema 非合法 JSON：{exc}") from exc
    if not isinstance(doc, dict):
        raise ActionContractError("action schema 顶层必须是对象")
    required = doc.get("required")
    if not isinstance(required, list) or not required or not all(isinstance(x, str) for x in required):
        raise ActionContractError("action schema 必须声明非空 required 字符串列表")
    properties = doc.get("properties")
    if not isinstance(properties, dict) or not properties:
        raise ActionContractError("action schema 必须声明非空 properties")
    for name in _NEEDED_PROPERTIES:
        spec = properties.get(name)
        if not isinstance(spec, dict):
            raise ActionContractError(f"action schema 缺 properties.{name}")
    if not isinstance(properties["origin"].get("pattern"), str):
        raise ActionContractError("action schema 的 origin 必须声明 pattern")
    enum = properties["method"].get("enum")
    if not isinstance(enum, list) or not enum or not all(isinstance(x, str) for x in enum):
        raise ActionContractError("action schema 的 method 必须声明非空 enum")
    return doc


@dataclasses.dataclass(frozen=True)
class ActionContract:
    """从 schema 派生的载荷判定面（单源，不含任何手抄字段名）。"""

    required: frozenset[str]
    constrained_fields: frozenset[str]
    string_fields: frozenset[str]
    integer_fields: frozenset[str]
    min_lengths: frozenset[str]
    patterns: dict[str, re.Pattern[str]]
    enums: dict[str, frozenset[str]]

    @classmethod
    def from_schema(cls, doc: dict[str, Any]) -> ActionContract:
        properties: dict[str, Any] = doc["properties"]
        # R8-PY-03（第八轮 2026-10-04）：**带约束的字段集**要单独算，不能拿 required
        # 当判定面——原实现只遍历 required，于是「把 origin 从 required 摘掉（pattern
        # 原地保留）」就让 origin 的 pattern 判定整段消失，而全部红队夹具与门禁仍绿：
        # 被证明物自己决定了证明面。现判定面取 required ∪ constrained_fields，
        # 摘 required 只是把「缺失即违规」降成「出现即校验」，校验本身不再可摘。
        constrained = frozenset(
            name for name, spec in properties.items()
            if spec.get("type") in ("string", "integer")
            or (isinstance(spec.get("minLength"), int) and spec["minLength"] > 0)
            or isinstance(spec.get("pattern"), str)
            or isinstance(spec.get("enum"), list))
        return cls(
            required=frozenset(doc["required"]),
            constrained_fields=constrained,
            string_fields=frozenset(
                name for name, spec in properties.items() if spec.get("type") == "string"),
            integer_fields=frozenset(
                name for name, spec in properties.items() if spec.get("type") == "integer"),
            min_lengths=frozenset(
                name for name, spec in properties.items()
                if isinstance(spec.get("minLength"), int) and spec["minLength"] > 0),
            patterns={name: re.compile(spec["pattern"])
                      for name, spec in properties.items()
                      if isinstance(spec.get("pattern"), str)},
            enums={name: frozenset(spec["enum"])
                   for name, spec in properties.items()
                   if isinstance(spec.get("enum"), list)},
        )

    def violation(self, action: object) -> str | None:
        """载荷与冻结契约的首个违背（None = 符合）。

        只判 schema 声明的形状（必填/类型/长度/pattern/enum）——语义门禁
        （scope 配对、代际、预算、nonce 一次性）仍归 broker，两条面不互相顶替。
        """
        for name in sorted(self.required | self.constrained_fields):
            if not hasattr(action, name):
                if name in self.required:
                    return f"契约必填字段在模型上不存在: {name}"
                continue   # 非 required 且模型无此属性——schema 允许的形状，不编造违背
            value = getattr(action, name)
            if value is None:
                if name in self.required:
                    return f"缺必填字段: {name}"
                continue
            if name in self.string_fields and not isinstance(value, str):
                return f"字段 {name} 必须为字符串"
            if name in self.integer_fields and type(value) is not int:
                # type 严格判定：bool 是 int 子类，不得冒充 int（PY-251 同口径）
                return f"字段 {name} 必须为整数"
            if name in self.min_lengths and not value:
                return f"字段 {name} 不得为空"
            pattern = self.patterns.get(name)
            if pattern is not None and not pattern.match(value):
                return f"字段 {name} 不合契约 pattern: {value!r}"
            allowed = self.enums.get(name)
            if allowed is not None and value not in allowed:
                return f"字段 {name} 不在契约 enum 内: {value!r}"
        return None


CONTRACT = ActionContract.from_schema(load_action_schema())
CONTRACT_REQUIRED = CONTRACT.required
CONTRACT_METHODS = CONTRACT.enums["method"]

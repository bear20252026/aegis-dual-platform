"""agent/tests/action_contract_test.py —— R7-TOOL-02（第七轮 2026-10-04）回归锚。

冻结的 `contracts/schemas/action.schema.json` 把 expires_at/origin/method/
policy_version/nonce/tab_id 等列为 required（origin 带 ^https?:// pattern、
method 带 enum、多数带 minLength 1），而 `PolicyBroker.evaluate()` 此前只看
`expires_at is not None` 才查过期、从不查 origin/method —— 于是「省略
expires_at」= 永久有效授权，`file:///C:/secrets`、`javascript:alert(1)`、
`method=ARBITRARY` 全部 allow。同仓 `test_field_set_matches_schema` 只比对
字段名集合，所以这块缺口一直显示为「契约已对齐」。

本文件锚四件事：① 判定面确实**取自** schema（并可用改写副本反证不是硬编码）；
② 省略/置空任一必填字段绝不放行；③ schema 读不到或结构不合预期时 broker
拒绝构造（"读不到就算通过" 是本项目已封的失效形态）；④ R8-PY-03——判定面**不得
由被证明物自己决定**：原实现只遍历 `required`，把 `origin` 从 required 摘掉（pattern
原地保留）就让 origin 校验整段消失，而红队夹具与五门禁全部仍绿。
"""

from __future__ import annotations

import json
import pathlib
import sys
import uuid

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from action_contract import (
    ACTION_SCHEMA_PATH,
    CONTRACT,
    CONTRACT_REQUIRED,
    ActionContract,
    ActionContractError,
    load_action_schema,
)
from broker import Decision, PolicyBroker, well_formed_action

SCHEMA = json.loads(ACTION_SCHEMA_PATH.read_text(encoding="utf-8"))
ENUM_METHODS = set(SCHEMA["properties"]["method"]["enum"])
# 更具体的既有码优先（口径不变），其余契约违背一律落 deny_schema
SCHEMA_OR_SPECIFIC = {Decision.DENY_SCHEMA, Decision.DENY_SESSION,
                      Decision.DENY_SCOPE, Decision.DENY_CANONICAL,
                      Decision.DENY_GENERATION}


def _fresh(**overrides):
    return well_formed_action(nonce=uuid.uuid4().hex, **overrides)


def test_contract_is_derived_from_the_frozen_schema():
    """判定面与 schema 逐字一致——手抄第二份字段表就是新的漂移面。"""
    assert CONTRACT_REQUIRED == frozenset(SCHEMA["required"])
    assert CONTRACT.enums["method"] == frozenset(ENUM_METHODS)
    assert CONTRACT.patterns["origin"].pattern == SCHEMA["properties"]["origin"]["pattern"]
    assert CONTRACT.min_lengths >= {
        name for name, spec in SCHEMA["properties"].items()
        if spec.get("minLength", 0) > 0 and name in CONTRACT_REQUIRED}
    assert Decision.DENY_SCHEMA == "deny_schema"  # 与 contracts/vectors 词汇一致


def test_widened_schema_copy_moves_the_gate(tmp_path):
    """反证：判定面真的来自 schema 文件。把 enum 改写出一份副本——副本接受
    TELEPORT，出厂契约仍拒；若这行逻辑是硬编码，两侧会同时接受或同时拒绝。"""
    doc = json.loads(json.dumps(SCHEMA))
    doc["properties"]["method"]["enum"] = sorted(ENUM_METHODS | {"TELEPORT"})
    path = tmp_path / "action.schema.json"
    path.write_text(json.dumps(doc), encoding="utf-8")
    widened = ActionContract.from_schema(load_action_schema(path))
    action = _fresh(method="TELEPORT")
    assert widened.violation(action) is None
    assert CONTRACT.violation(action) is not None
    assert PolicyBroker().evaluate(action) == Decision.DENY_SCHEMA


def _schema_copy(tmp_path, mutate):
    """出厂 schema 的改写副本（判定面来源单源，测试不另抄一份字段表）。"""
    doc = json.loads(json.dumps(SCHEMA))
    mutate(doc)
    path = tmp_path / "action.schema.json"
    path.write_text(json.dumps(doc), encoding="utf-8")
    return load_action_schema(path)


def test_narrowing_required_does_not_shrink_the_judgment_surface(tmp_path):
    """R8-PY-03 的核心反证：摘掉 required 里的 origin 之后，坏 origin 仍必须被拒。

    修复前这里是绿的——`violation()` 只遍历 required，pattern 声明还在 schema 里
    却再无人执行；等价于把「证明面」交给被证明的对象自己签字。
    """
    narrowed = ActionContract.from_schema(
        _schema_copy(tmp_path, lambda doc: doc["required"].remove("origin")))
    assert "origin" not in narrowed.required
    assert "origin" in narrowed.constrained_fields

    bad = narrowed.violation(_fresh(origin="javascript:alert(1)"))
    assert bad is not None and "origin" in bad, (
        f"required 摘掉 origin 后 pattern 判定整段消失：{bad!r}")

    # 枚举同理：method 摘出 required 后仍不得接受词表外的值
    m_narrowed = ActionContract.from_schema(
        _schema_copy(tmp_path, lambda doc: doc["required"].remove("method")))
    assert m_narrowed.violation(_fresh(method="TELEPORT")) is not None


def test_optional_absent_constrained_field_is_not_invented_as_violation(tmp_path):
    """反向对照（防「一律拒绝」式假修复）：非 required 且确实缺席的字段不是违背。

    收紧判定面的正当边界是「出现即校验」，不是「缺席即有罪」——否则同一改动会
    把 schema 允许的可选形态判成攻击样例。
    """
    narrowed = ActionContract.from_schema(
        _schema_copy(tmp_path, lambda doc: doc["required"].remove("origin")))
    assert narrowed.violation(_fresh(origin=None)) is None
    # 出厂面（origin 属 required）同形态必须照旧拒绝
    assert CONTRACT.violation(_fresh(origin=None)) is not None


def test_judgment_surface_is_a_pinned_bounded_set():
    """判定面是有界常量集：扩/缩 required 或约束集都要显式改这里（同 KNOWN_* 口径）。

    写死这 10 个名字是刻意的——它与 `contracts/schemas/action.schema.json` 的
    required 逐字相等（上一条用例已锚定派生关系），任何"少判一个字段"的改动
    都会撞在这里，而不是静默少一条断言。
    """
    assert CONTRACT.required == frozenset({
        "session_id", "tab_id", "document_generation", "origin", "method",
        "canonical_parameters", "scope", "expires_at", "nonce", "policy_version",
    })
    assert CONTRACT.constrained_fields == CONTRACT.required
    assert sorted(CONTRACT.required | CONTRACT.constrained_fields) == sorted(
        SCHEMA["properties"])


@pytest.mark.parametrize("field", sorted(CONTRACT_REQUIRED))
def test_omitting_any_required_field_never_allows(field):
    """契约 required 的字段被省略（None）——绝不放行。

    具体码（deny_session/deny_scope/deny_canonical）优先于 deny_schema 是刻意
    口径（既有断言不变），但无论落哪一码都必须是拒。"""
    action = _fresh()
    setattr(action, field, None)
    decision = PolicyBroker().evaluate(action)
    assert decision != Decision.ALLOW
    assert decision in SCHEMA_OR_SPECIFIC, f"{field} 省略后被判 {decision!r}"


@pytest.mark.parametrize("field", sorted(CONTRACT.min_lengths))
def test_blank_required_field_never_allows(field):
    """minLength:1 的必填字段给空串——空串不得冒充合法值。"""
    action = _fresh()
    setattr(action, field, "")
    assert PolicyBroker().evaluate(action) != Decision.ALLOW


@pytest.mark.parametrize("origin", [
    "file:///C:/secrets", "javascript:alert(1)", "data:text/html,eviL",
    "https:/example.test", "ftp://example.test", "HTTP://example.test",
])
def test_non_https_origin_is_denied(origin):
    assert PolicyBroker().evaluate(_fresh(origin=origin)) == Decision.DENY_SCHEMA


@pytest.mark.parametrize("origin", ["https://example.test", "http://example.test"])
def test_contract_conforming_origin_passes(origin):
    assert PolicyBroker().evaluate(_fresh(origin=origin)) == Decision.ALLOW


@pytest.mark.parametrize("method", sorted(ENUM_METHODS))
def test_every_schema_method_enum_is_admissible(method):
    """enum 内的动词都能过契约门（enum 外的见 spoofed-origin-and-method 夹具）。"""
    assert PolicyBroker().evaluate(_fresh(method=method)) == Decision.ALLOW


def test_bool_does_not_pass_as_integer_document_generation():
    """PY-251 口径：bool 是 int 子类，不得冒充 schema 的 integer 字段。
    取 False（== 当代际 0）——若靠值比较而非类型判定，它会一路放行到门禁之外。"""
    assert PolicyBroker().evaluate(_fresh(document_generation=False)) == Decision.DENY_SCHEMA


@pytest.mark.parametrize("label, mutation", [
    ("required 为空", lambda d: d.__setitem__("required", [])),
    ("properties 缺失", lambda d: d.pop("properties")),
    ("origin 无 pattern", lambda d: d["properties"]["origin"].pop("pattern")),
    ("method enum 为空", lambda d: d["properties"]["method"].__setitem__("enum", [])),
    ("缺 properties.method", lambda d: d["properties"].pop("method")),
])
def test_unreadable_schema_is_fail_closed(tmp_path, label, mutation):
    """契约不可读 = broker 拒绝构造，绝不退化成「没有必填集」。"""
    doc = json.loads(json.dumps(SCHEMA))
    mutation(doc)
    path = tmp_path / "action.schema.json"
    path.write_text(json.dumps(doc), encoding="utf-8")
    with pytest.raises(ActionContractError):
        load_action_schema(path)
    with pytest.raises(ActionContractError):
        load_action_schema(tmp_path / "absent.schema.json")


def test_broker_actually_calls_the_contract_gate():
    """静态锚（R6-26 教训）：判定面必须被出厂 broker 接上，只定义不接线等于没有。"""
    source = (ROOT / "broker.py").read_text(encoding="utf-8")
    assert "CONTRACT.violation(action)" in source
    assert "Decision.DENY_SCHEMA" in source
    # 构造边界同样取 schema required——省略 expires_at 的载荷不得连构造都通过
    assert "set(CONTRACT_REQUIRED)" in source

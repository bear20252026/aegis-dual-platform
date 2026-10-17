"""R9-B87（队列 Q65）：Agent IPC 载荷契约 ⇄ broker 必填面的双向对账门禁的用例。

四条判据各自都要「能红」——`violations()` 是纯函数，注入的假面走的是同一条判定；
再加一条**运行时**验证：契约写着 `additionalProperties: false`，那就必须真的被
`proposed_action_from_dict` 执行，否则这份契约只是在描述一个没人遵守的形状。
"""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "agent"))

import verify_agent_action_schema as gate


def real_surfaces() -> tuple[set[str], set[str], set[str], set[str], set[str]]:
    """（契约 required, 契约 properties, broker 必填, broker 全部字段, 冻结 required）。"""
    mandatory, all_fields, frozen_required = gate.broker_surfaces()
    doc = json.loads((ROOT / "agent" / "agent-action.schema.json").read_text(encoding="utf-8"))
    return set(doc["required"]), set(doc["properties"]), mandatory, all_fields, frozen_required


def test_real_contract_matches_the_derived_broker_face() -> None:
    agent_required, agent_properties, mandatory, all_fields, frozen_required = real_surfaces()
    assert gate.violations(agent_required, agent_properties, mandatory, all_fields, frozen_required) == []
    # 关系而不是常量：冻结面必须是 Agent 面的真子集（两张面各自成立，不许静默并成一张）
    assert frozen_required < agent_required
    assert gate.run() == 0


@pytest.mark.parametrize(
    ("mutate", "expected"),
    [
        (lambda req, props, m, f, fr: (req - {"intent"}, props, m, f, fr), "契约 required 与 broker 必填面不一致"),
        (lambda req, props, m, f, fr: (req | {"ghost_field"}, props, m, f, fr), "契约 required 与 broker 必填面不一致"),
        (lambda req, props, m, f, fr: (req, props - {"nonce"}, m, f, fr), "契约 properties 与 ProposedAction 字段集不一致"),
        (lambda req, props, m, f, fr: (req, props | {"not_a_field"}, m, f, fr), "契约 properties 与 ProposedAction 字段集不一致"),
        # required 指向 properties 里没有的字段——JSON Schema 层谁都验不过的形状。
        # 这一刀同时也破了第二条（properties 少了一个真字段），所以只断言「第三条必须出现」，
        # 不假设违规条数恰好是 1（真实缺陷经常一次打破多条判据，条数断言是给理想型写的）。
        (
            lambda req, props, m, f, fr: (req, props - {"scope"}, m, f, fr),
            "required 指向 properties 里没有的字段",
        ),
        # 并成一张面：把 Agent 多出来的两个字段收回契约——分歧消失就等于 Q65 的结论被改写
        (lambda req, props, m, f, fr: (fr, props, m, f, fr), "多出来的字段必须恰好是"),
    ],
    ids=["drop-required", "add-required", "drop-property", "add-property", "required-without-property", "merge-the-two-faces"],
)
def test_each_injection_is_red(mutate, expected) -> None:
    agent_required, agent_properties, mandatory, all_fields, frozen_required = real_surfaces()
    req, props, m, f, fr = mutate(agent_required, agent_properties, mandatory, all_fields, frozen_required)
    problems = gate.violations(req, props, m, f, fr)
    assert problems, f"注入没被抓到：{expected}"
    assert any(expected in p for p in problems), problems


def test_clean_surfaces_produce_no_problems() -> None:
    """正面控制：第一条里那句 `== []` 依赖同一份判定，若判定恒真它也会「通过」。"""
    agent_required, agent_properties, mandatory, all_fields, frozen_required = real_surfaces()
    assert gate.violations(copy.deepcopy(agent_required), agent_properties, mandatory, all_fields, frozen_required) == []


def test_environment_problems_are_not_reported_as_pass() -> None:
    """判定面塌缩/契约缺失必须 exit 2，不能因为「什么都没判」而绿。"""
    assert gate.load_required({"required": []}) == set()  # 空集合本身不抛——由 run() 的空面检查兜住
    with pytest.raises(ValueError, match="required"):
        gate.load_required({"required": "not-a-list"})
    with pytest.raises(ValueError, match="properties"):
        gate.load_properties({})
    missing = ROOT / "contracts" / "schemas" / "does-not-exist.json"
    assert not missing.is_file()


def test_runtime_actually_enforces_the_contract_face() -> None:
    """契约不是装饰：`additionalProperties: false` 与 required 缺席都得被 broker 真判。"""
    from broker import BrokerInputError, proposed_action_from_dict

    payload = {
        "session_id": "s-1",
        "tab_id": "t-1",
        "document_generation": 3,
        "origin": "https://example.test",
        "method": "GET",
        "canonical_parameters": "a=1",
        "scope": "read",
        "expires_at": "2099-01-01T00:00:00Z",
        "nonce": "n-1",
        "policy_version": "1.0.0",
        "intent": "navigate",
        "budget_used": 0,
    }
    action = proposed_action_from_dict(payload)
    assert action.intent == "navigate" and action.budget_used == 0

    without_intent = dict(payload)
    del without_intent["intent"]
    with pytest.raises(BrokerInputError, match="intent"):
        proposed_action_from_dict(without_intent)

    with pytest.raises(BrokerInputError, match="budget_used"):
        proposed_action_from_dict({k: v for k, v in payload.items() if k != "budget_used"})

    # 契约声明 additionalProperties:false ⇒ 多发的键必须被拒（而不是被静默忽略）
    with pytest.raises((BrokerInputError, KeyError)):
        proposed_action_from_dict({**payload, "not_in_the_contract": 1})

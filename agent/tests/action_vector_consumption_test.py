"""agent/tests/action_vector_consumption_test.py —— R9-B68（队列 Q53 第③档）。

登记时这一档写的是「Agent 端不消费任何契约向量（`CONSUMER_MANIFEST` 现读 `AG` 命中 0）」，
并留了一句「要不要把红队夹具与 `action-valid/invalid.json` 绑成同一份输入属排期决定」。
本文件就是那次绑定的**契约层**：把两份向量逐条喂进 `ActionContract.payload_violation`
（与 `PolicyBroker.evaluate()` 里 `CONTRACT.violation()` 同一份判定面）。

为什么不断 `PolicyBroker.decide()`：那是「能不能构造成 ProposedAction」的命题，而
Agent 的载荷面比冻结 schema 多要求 `intent`/`budget_used`（见本文件最后一条用例，
它把这条分歧钉住而不是假装没有）。核心形态的向量在那里全部落 `deny_payload`，
断它「非 ALLOW」是零信息量的空心断言——R9-B39 那条「注释不算证据」的纪律同样
适用于「被拒不算判据」。

绑定的第一件产出不是覆盖，是一条真实缺口：`action.schema.json` 给
`document_generation` 声明了 `minimum: 0`，而 `ActionContract.from_schema` 此前从
schema 现算的是 required/type/minLength/pattern/enum，**独独漏收 minimum** ⇒
负代际在 Agent 端契约层放行，只在「与当前代际比对」那道语义门上被拒（同一条向量
在核心得到 deny_schema）。这是 R8-PY-03 记过的「判定面由被证明物自己决定」的
同型缺口另一半：不止「摘 required 会关掉校验」，「schema 声明了却没被派生进面」
同样会。
"""

from __future__ import annotations

import json
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from action_contract import CONTRACT, REPO_ROOT, ActionContract, load_action_schema
from broker import Decision, PolicyBroker

VECTOR_DIR = REPO_ROOT / "contracts" / "vectors"
SCHEMA_DOC = json.loads((REPO_ROOT / "contracts" / "schemas" / "action.schema.json")
                        .read_text(encoding="utf-8"))


def _vectors(name: str) -> list[dict]:
    doc = json.loads((VECTOR_DIR / name).read_text(encoding="utf-8"))
    entries = doc["vectors"]
    assert entries, f"{name} 的 vectors 数组为空——空面不作通过判定"
    return entries


VALID = _vectors("action-valid.json")
INVALID = _vectors("action-invalid.json")


def _id(vector: dict) -> str:
    return vector["note"][:40]


def test_expectations_stay_inside_the_contract_vocabulary() -> None:
    """`expected` 只允许 valid / deny_schema——新词表意味着新判定面，得先写在这里再实现。"""
    assert {v["expected"] for v in VALID} == {"valid"}
    assert {v["expected"] for v in INVALID} == {"deny_schema"}


@pytest.mark.parametrize("vector", VALID, ids=_id)
def test_valid_vectors_pass_the_frozen_contract(vector: dict) -> None:
    assert CONTRACT.payload_violation(vector["action"]) is None


@pytest.mark.parametrize("vector", INVALID, ids=_id)
def test_invalid_vectors_are_rejected_by_the_frozen_contract(vector: dict) -> None:
    reason = CONTRACT.payload_violation(vector["action"])
    assert reason is not None, f"向量被判合法，而契约未拒：{vector['note']}"
    assert reason.strip(), "违背理由为空串——拒绝理由不得空心"


def test_reject_reasons_cover_every_derived_constraint_family() -> None:
    """七条 invalid 向量必须真的各自触到**不同的**派生判据族。

    这条是本文件的承重墙：单看「七条都被拒」，一条 `if not data: return "空"` 就能全过。
    逐族点名之后，「schema 声明了但没被派生进判定面」这一类缺口（本批抓到的 minimum）
    会在这里判红，而不是在某条向量恰好被别的门顺手拒掉时蒙混过去。
    """
    reasons = "\n".join(str(CONTRACT.payload_violation(v["action"])) for v in INVALID)
    for family in ("不在契约 enum 内", "不合契约 pattern", "不得为空",
                   "缺必填字段", "additionalProperties:false", "低于契约 minimum"):
        assert family in reasons, f"判据族「{family}」没有任何向量触到——派生面可能没收到契约里"


def test_widened_schema_copy_moves_the_gate(tmp_path: pathlib.Path) -> None:
    """反证：判定面真的来自 schema 文件而不是硬编码名单（R7-TOOL-02 同型控制）。

    副本里放开 PATCH、摘掉 document_generation 的 minimum、把 additionalProperties
    改成 true ⇒ 副本接受这三条向量，出厂契约仍拒三条。如果这几行逻辑是硬编码，
    两侧会同时接受或同时拒绝。
    """
    doc = json.loads(json.dumps(SCHEMA_DOC))
    doc["properties"]["method"]["enum"] = sorted(set(doc["properties"]["method"]["enum"]) | {"PATCH"})
    doc["properties"]["document_generation"].pop("minimum")
    doc["additionalProperties"] = True
    path = tmp_path / "action.schema.json"
    path.write_text(json.dumps(doc), encoding="utf-8")
    widened = ActionContract.from_schema(load_action_schema(path))

    patched = next(v for v in INVALID if "PATCH" in v["note"])
    negative = next(v for v in INVALID if "负数" in v["note"])
    extra = next(v for v in INVALID if "额外字段" in v["note"])
    for vector in (patched, negative, extra):
        assert widened.payload_violation(vector["action"]) is None, vector["note"]
        assert CONTRACT.payload_violation(vector["action"]) is not None, vector["note"]


def test_payload_shape_branches_without_vectors_are_still_enforced() -> None:
    """两条没有对应向量的形体分支，也必须被测到而不是留着当「没人走的路」。

    `action-invalid.json` 七条覆盖的是 schema 声明的六族判据；「载荷不是映射」与
    「字符串字段给了非字符串」这两条分支不在任何向量里。没有向量的分支要么被测，
    要么就该删——留一条不可达分支就是给下一轮的自己挖「以为拦住了」的坑。
    """
    assert CONTRACT.payload_violation(["not", "a", "mapping"]) is not None
    broken = json.loads(json.dumps(VALID[0]["action"]))
    broken["origin"] = 5
    assert "必须为字符串" in str(CONTRACT.payload_violation(broken))


def test_agent_payload_face_is_wider_than_the_frozen_schema() -> None:
    """钉住一条已知分歧，别让它被「向量已消费」这句话盖过去（⇒ 台账 Q65）。

    Agent 的 `ProposedAction` 还要求 `intent`/`budget_used`（红队夹具与扩展 IPC 的
    载荷面），冻结 schema 里没有这两个字段 ⇒ 核心形态的向量在
    `PolicyBroker.decide()` 处**全部**落 `deny_payload`，连 valid 三条也一样。
    「把红队夹具与 action-*.json 绑成同一份输入」要动的是这条 IPC 载荷契约，
    属排期决定，不在本批。
    """
    broker = PolicyBroker()
    for vector in VALID + INVALID:
        assert broker.decide(vector["action"]) == Decision.DENY_PAYLOAD, vector["note"]
    assert {"intent", "budget_used"} - set(SCHEMA_DOC["required"]), "两张载荷面已经并成一张——本用例该改写"

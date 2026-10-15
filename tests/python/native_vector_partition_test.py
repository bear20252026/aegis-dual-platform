"""原生 C-ABI 向量的信封与 `platform_decidable` 分区判据（第九轮 R9-B59 / §四 第 11 项 ② + Q21）。

这块要防的不是「某个裁决错了」，而是**词表本身悄悄变成两套真相**：

- 分区标签如果是自由填写的布尔，它就只是第二份可以各自漂移的陈述——所以中心判据是
  「标签必须能由该条的期望值推导」（推导式登记在 `verify_vectors.py:NATIVE_VECTORS`），
  并且两半都要非空（全 true / 全 false 都判红：塌成一块的分区不描述任何事实）。
- 信封此前是实测不一致的：`native-navigation-decision.json` 有 `version`+`description` 而无
  `protocol`，`native-navigation-confirmation.json` 只有 `protocol`，还把修订号焊在字符串尾巴
  （`...-v3`）。同一 ABI 的两份向量没有共同头部 ⇒ 任何「按信封识别向量」的工具都要写两套解析。
  现在判**键集合**，不只判值。
- 改名 `expected_deny_code → expected_evaluate_code` 要**两侧同批**：只改向量文件，Rust 消费者
  就会拿 `Value::Null` 去比对——红在运行期而不是红在门禁，等于把一次词表变更藏进 CI 日志。

每条注入都断言**是哪条规则红的**（措辞进判据），并各配正面控制——本仓已经记过四次
「判据自己喂绿」，而 R9-B58 那条更狠的形态是「文件被改坏也会让测试变红」。
"""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path
from typing import Callable

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from text_anchors import strip_comments  # 注释剔法单源（R9-B45 / Q59）
from verify_vectors import (
    NATIVE_ENVELOPE_KEYS,
    NATIVE_VECTORS,
    check_native_vector,
)

DECISION = ROOT / "contracts" / "vectors" / "native-navigation-decision.json"
CONFIRMATION = ROOT / "contracts" / "vectors" / "native-navigation-confirmation.json"
RUST_CONSUMER = ROOT / "core" / "rust-policy-core" / "src" / "c_abi" / "tests" / "vectors_decision.rs"
GATE_SCRIPT = ROOT / "scripts" / "verify_vectors.py"


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def judge(data: dict, path: Path) -> list[str]:
    failures: list[str] = []
    check_native_vector(data, path, failures)
    return failures


@pytest.fixture(scope="session")
def docs() -> dict[str, dict]:
    return {path.name: load(path) for path in (DECISION, CONFIRMATION)}


# ---------------------------------------------------------------- 现树事实

def test_both_native_vectors_satisfy_the_gate(docs: dict[str, dict]) -> None:
    for path in (DECISION, CONFIRMATION):
        assert not judge(docs[path.name], path), f"{path.name}: 信封/分区判据不通过"


def test_envelope_shape_is_exactly_the_registered_one(docs: dict[str, dict]) -> None:
    for path in (DECISION, CONFIRMATION):
        data = docs[path.name]
        assert set(data) == NATIVE_ENVELOPE_KEYS, (
            f"{path.name}: 信封键集合应为 {sorted(NATIVE_ENVELOPE_KEYS)}，实得 {sorted(data)}")
        spec = NATIVE_VECTORS[path.name]
        assert data["protocol"] == spec["protocol"], f"{path.name}: protocol 漂了"
        assert data["version"] == spec["version"], f"{path.name}: version 漂了"
        assert isinstance(data["description"], str) and data["description"].strip()


def test_partition_is_the_measured_thirteen_and_thirty(docs: dict[str, dict]) -> None:
    """现读形状：53 条里 35 true / 18 false（R9-B66 加了 10 条 IPv6 策略向量，
    其中 5 条 require_confirmation 因此按推导式落进 false），确认面 5 条全 false。

    钉数字不是为了让数字不能变，是为了让「变数字」必须与「改推导式」同批发生
    （R9-B66 就是走这条路改的：新增向量 → 计数同批 → 三端跑同一份表）。
    """
    vectors = docs[DECISION.name]["vectors"]
    flags = [vector["platform_decidable"] for vector in vectors]
    assert len(vectors) == 53 and sum(flags) == 35 and flags.count(False) == 18
    confirmation = docs[CONFIRMATION.name]["vectors"]
    assert len(confirmation) == 5 and all(v["platform_decidable"] is False for v in confirmation)


def test_label_is_derivable_not_declared(docs: dict[str, dict]) -> None:
    """每条标签都必须等于「该条期望值推导出的值」——这条是整个设计的内容。"""
    for path in (DECISION, CONFIRMATION):
        predicate = NATIVE_VECTORS[path.name]["decidable_when"]
        for vector in docs[path.name]["vectors"]:
            assert vector["platform_decidable"] == bool(predicate(vector)), (
                f"{path.name}/{vector['name']}: 标签与期望值不自洽")


def test_rename_landed_on_both_sides(docs: dict[str, dict]) -> None:
    """数据面没有残留旧字段，消费者**代码面**读的是新字段（剔注释后判）。"""
    for data in docs.values():
        for vector in data["vectors"]:
            assert "expected_deny_code" not in vector
    code = strip_comments(RUST_CONSUMER.read_text(encoding="utf-8"), str(RUST_CONSUMER))
    assert "expected_evaluate_code" in code, (
        "Rust 消费者没读新字段——只改向量文件的话，红会出现在运行期而不是门禁里")
    assert "expected_deny_code" not in code, "消费者还在读旧字段名"


def test_gate_helper_is_actually_wired() -> None:
    """`check_native_vector` 必须被 main() 调用——一份没人调的正确判据等于没有判据。"""
    text = strip_comments(GATE_SCRIPT.read_text(encoding="utf-8"), str(GATE_SCRIPT))
    assert text.count("check_native_vector(") == 2, (
        "定义与调用应各一处：只剩一处说明调用点被摘掉，多于两处说明判定面被复制")


def test_rule_is_scoped_by_name_not_by_glob(tmp_path: Path) -> None:
    """不在 NATIVE_VECTORS 里的文件必须**零判定**，否则这条规则会悄悄扩到另外 19 份向量。"""
    stranger = tmp_path / "url-origin-valid.json"
    assert judge({"nope": 1}, stranger) == []


# ---------------------------------------------------------------- 注入证伪

def mutated(mutate: Callable[[dict], None]) -> dict:
    data = copy.deepcopy(load(DECISION))
    mutate(data)
    return data


@pytest.mark.parametrize(("mutate", "rule"), [
    (lambda d: d["vectors"][0].pop("platform_decidable"), "缺 platform_decidable"),
    (lambda d: d["vectors"][0].__setitem__("platform_decidable", "true"), "必须是布尔"),
    (lambda d: d["vectors"][0].__setitem__("platform_decidable", False), "按该条期望值推导应为"),
    (lambda d: d["vectors"][0].__setitem__("expected_deny_code", "nonce_replay"), "仍用旧字段"),
    (lambda d: d.pop("protocol"), "信封键集合应为"),
    (lambda d: d.__setitem__("version", 2), "与登记表"),
    (lambda d: d.__setitem__("description", "   "), "description 为空"),
])
def test_each_rule_fires_on_its_own_violation(mutate: Callable[[dict], None], rule: str) -> None:
    failures = judge(mutated(mutate), DECISION)
    assert failures, f"注入 {rule} 之后没有判红"
    assert any(rule in line for line in failures), (
        f"红了，但不是这条规则红的（实得：{failures}）——措辞要对得上，"
        "否则「门禁变红」和「判据抓到」是两件事（R9-B58 §3.58 第 3 条同型）")


def test_collapse_fires_while_labels_stay_self_consistent() -> None:
    """分区塌成一块：把每条的期望值与标签**一起**改成 true——推导式仍然成立，只有塌缩判据能红。

    这是本文件唯一一条「必须靠那条专门的规则」的注入：否则塌缩用例会被推导式顺手抓住，
    塌缩规则本身就成了没人作证的声明。
    """
    def flatten(data: dict) -> None:
        for vector in data["vectors"]:
            vector["expected_evaluate"] = "allow"
            vector["platform_decidable"] = True
            vector.pop("expected_evaluate_code", None)
    failures = judge(mutated(flatten), DECISION)
    assert any("分区塌成一块" in line for line in failures), (
        f"全 true 没有触发塌缩判据（实得：{failures}）")


def test_confirmation_true_label_fires() -> None:
    """确认面整份是「宿主产不出」那一族：标成 true 必须红（它的推导式是常量 false，与 decision 不同形）。"""
    data = copy.deepcopy(load(CONFIRMATION))
    data["vectors"][0]["platform_decidable"] = True
    assert any("按该条期望值推导应为" in line for line in judge(data, CONFIRMATION))


def test_positive_control_valid_shape_still_passes() -> None:
    """正面控制：追加一条**合法**的 require_confirmation 向量（标 false）必须仍然通过。

    没有这条，上面的注入就可能只是「任何改动都红」——那与判据成立是两件事。
    """
    data = mutated(lambda d: None)
    data["vectors"].append({
        "name": "positive_control_confirmation",
        "platform_decidable": False,
        "register_session": True,
        "generation": 0,
        "url": "https://169.254.169.254/positive-control",
        "scope": "navigation",
        "expected_evaluate": "require_confirmation",
    })
    assert judge(data, DECISION) == []

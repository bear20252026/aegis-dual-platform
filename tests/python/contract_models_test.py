# contract_models_test.py —— R7-SH-01（第七轮 2026-10-04）：新增两项契约门禁的
# 可失败性自证。
#
# 背景：第六轮建了 REAL_MODEL_CONTRACTS / DESIGN_NOTATION_MIRRORS 两张表并写了注释，
# 但既无函数读取、也无测试驱动——表与注释沦为死数据，门禁仍是「schema ↔ 自身生成
# 镜像」自证。本文件把新落地的 check_real_models / check_mirror_consumption 的
# **每一条失败分支**都单独钉住：只测「通过」的门禁等于没有门禁。
from __future__ import annotations

import json
import pathlib

import pytest


@pytest.fixture()
def tree(tmp_path, monkeypatch):
    """最小合成契约树：ROOT 重定向后，镜像目录/模型路径都随之落在 tmp 内。"""
    import verify_contract_compatibility as vcc

    repo = tmp_path / "repo"
    contracts = repo / "contracts"
    (contracts / "schemas").mkdir(parents=True)
    (contracts / "vectors").mkdir(parents=True)
    cs = repo / "windows/src/Aegis.Windows.App/Contracts/Generated"
    cs.mkdir(parents=True)
    kt = repo / "android/contracts/src/main/kotlin/com/aegis/contracts/generated"
    kt.mkdir(parents=True)
    monkeypatch.setattr(vcc, "ROOT", contracts)
    monkeypatch.setattr(vcc, "SCHEMAS", contracts / "schemas")
    monkeypatch.setattr(vcc, "VECTORS", contracts / "vectors")
    return vcc, repo, contracts, cs, kt


def _write(path: pathlib.Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


# ---------- check_real_models ----------


def test_matching_model_passes(tree, monkeypatch):
    vcc, repo, contracts, *_ = tree
    _write(contracts / "schemas/approval.schema.json",
           json.dumps({"required": ["origin", "expires_at", "nonce"]}))
    _write(repo / "windows/src/Aegis.Windows.App/Broker/Decision.cs",
           "public sealed record ApprovalRequest(\n"
           "    string Origin,\n    string Scope,\n"
           "    DateTime ExpiresAt,\n    string Nonce);\n")
    monkeypatch.setattr(vcc, "REAL_MODEL_CONTRACTS", {
        "approval.schema.json": (
            "windows/src/Aegis.Windows.App/Broker/Decision.cs", "cs", "ApprovalRequest")})
    assert vcc.check_real_models() == []


def test_renamed_field_is_detected(tree, monkeypatch):
    """字段改名必须红——这是「名实对账」的判定力本身。"""
    vcc, repo, contracts, *_ = tree
    _write(contracts / "schemas/approval.schema.json",
           json.dumps({"required": ["nonce"]}))
    _write(repo / "windows/src/Aegis.Windows.App/Broker/Decision.cs",
           "public sealed record ApprovalRequest(string NonceX);\n")
    monkeypatch.setattr(vcc, "REAL_MODEL_CONTRACTS", {
        "approval.schema.json": (
            "windows/src/Aegis.Windows.App/Broker/Decision.cs", "cs", "ApprovalRequest")})
    found = vcc.check_real_models()
    assert len(found) == 1 and "字段漂移" in found[0], found


def test_missing_type_declaration_is_detected(tree, monkeypatch):
    vcc, repo, contracts, *_ = tree
    _write(contracts / "schemas/approval.schema.json", json.dumps({"required": ["nonce"]}))
    _write(repo / "windows/src/Aegis.Windows.App/Broker/Decision.cs",
           "public sealed record SomethingElse(string Nonce);\n")
    monkeypatch.setattr(vcc, "REAL_MODEL_CONTRACTS", {
        "approval.schema.json": (
            "windows/src/Aegis.Windows.App/Broker/Decision.cs", "cs", "ApprovalRequest")})
    assert any("类型未找到" in f for f in vcc.check_real_models())


def test_missing_model_file_is_detected(tree, monkeypatch):
    vcc, repo, contracts, *_ = tree
    _write(contracts / "schemas/approval.schema.json", json.dumps({"required": ["nonce"]}))
    monkeypatch.setattr(vcc, "REAL_MODEL_CONTRACTS", {
        "approval.schema.json": ("windows/nope/Decision.cs", "cs", "ApprovalRequest")})
    assert any("真实模型缺失" in f for f in vcc.check_real_models())


def test_missing_referenced_schema_is_detected(tree, monkeypatch):
    """删掉被对账表引用的 schema 必须红——旧门禁对「减契约面」完全无感（R7-SH-07 同族）。"""
    vcc, repo, contracts, *_ = tree
    monkeypatch.setattr(vcc, "REAL_MODEL_CONTRACTS", {
        "approval.schema.json": (
            "windows/src/Aegis.Windows.App/Broker/Decision.cs", "cs", "ApprovalRequest")})
    assert any("schema 不可读" in f for f in vcc.check_real_models())


def test_rust_snake_case_member_is_matched_exactly(tree, monkeypatch):
    """lang="rust" 不做 Pascal 转换——`max_uses` 必须原样比对。"""
    vcc, repo, contracts, *_ = tree
    _write(contracts / "schemas/capability.schema.json",
           json.dumps({"required": ["scope", "max_uses"]}))
    _write(repo / "core/capability.rs",
           "pub struct Capability {\n    pub scope: u8,\n    pub max_uses: u32,\n}\n")
    monkeypatch.setattr(vcc, "REAL_MODEL_CONTRACTS", {
        "capability.schema.json": ("core/capability.rs", "rust", "Capability")})
    assert vcc.check_real_models() == []
    _write(repo / "core/capability.rs", "pub struct Capability {\n    pub scope: u8,\n}\n")
    assert any("max_uses" in f for f in vcc.check_real_models())


# ---------- check_mirror_consumption ----------


def test_exempted_mirrors_pass(tree, monkeypatch):
    vcc, _repo, _contracts, cs, _kt = tree
    monkeypatch.setattr(vcc, "DESIGN_NOTATION_MIRRORS", {"ApprovalContract"})
    _write(cs / "ApprovalContract.cs", "public sealed record ApprovalContract(string Nonce);")
    assert vcc.check_mirror_consumption() == []


def test_unconsumed_unlisted_mirror_is_detected(tree, monkeypatch):
    """不在豁免清单、又无端侧引用的镜像必须红（防「无人消费的假保证」）。"""
    vcc, _repo, _contracts, cs, _kt = tree
    monkeypatch.setattr(vcc, "DESIGN_NOTATION_MIRRORS", set())
    _write(cs / "ApprovalContract.cs", "public sealed record ApprovalContract(string N);")
    found = vcc.check_mirror_consumption()
    assert len(found) == 1 and "无真实消费方" in found[0], found


def test_mirror_with_real_consumer_is_accepted(tree, monkeypatch):
    vcc, repo, _contracts, cs, _kt = tree
    monkeypatch.setattr(vcc, "DESIGN_NOTATION_MIRRORS", set())
    _write(cs / "ApprovalContract.cs", "public sealed record ApprovalContract(string N);")
    _write(repo / "windows/src/Aegis.Windows.App/Chrome/Uses.cs",
           'var x = new ApprovalContract("n");')
    assert vcc.check_mirror_consumption() == []


def test_test_only_reference_is_not_a_consumer(tree, monkeypatch):
    """只有测试引用不算承重消费方——否则镜像可以靠自我引用蒙过门禁。"""
    vcc, repo, _contracts, cs, _kt = tree
    monkeypatch.setattr(vcc, "DESIGN_NOTATION_MIRRORS", set())
    _write(cs / "ApprovalContract.cs", "public sealed record ApprovalContract(string N);")
    _write(repo / "windows/tests/ApprovalContractTests.cs",
           'class T { void M() { var x = new ApprovalContract("n"); } }')
    assert any("无真实消费方" in f for f in vcc.check_mirror_consumption())


def test_dead_exemption_entry_is_detected(tree, monkeypatch):
    """豁免清单里残留已不存在的镜像必须红（清单不得堆积死条目）。

    镜像面必须非空才有意义：整棵树消失时 `check_mirror_consumption` 给的是更准确的
    「镜像目录缺失」判定（见下一条），不重复报 6 条死条目。
    """
    vcc, _repo, _contracts, cs, _kt = tree
    monkeypatch.setattr(vcc, "DESIGN_NOTATION_MIRRORS", {"ApprovalContract", "GhostContract"})
    _write(cs / "ApprovalContract.cs", "public sealed record ApprovalContract(string N);")
    found = vcc.check_mirror_consumption()
    assert len(found) == 1 and "死条目" in found[0] and "GhostContract" in found[0], found


def test_missing_mirror_dir_is_env_failure(tree, monkeypatch):
    """镜像目录整个消失不得静默放行——空扫描面即失败。"""
    import shutil

    vcc, repo, _contracts, _cs, _kt = tree
    shutil.rmtree(repo / "windows/src/Aegis.Windows.App/Contracts/Generated")
    monkeypatch.setattr(vcc, "DESIGN_NOTATION_MIRRORS", set())
    found = vcc.check_mirror_consumption()
    assert any("镜像目录缺失" in f for f in found), found


# ---------- 真实仓库口径 ----------


def test_real_repo_is_clean_and_tables_nonempty():
    """现网必须绿；且两张表非空（空表会让上面两个检查同时变成恒真）。"""
    import verify_contract_compatibility as vcc

    assert vcc.REAL_MODEL_CONTRACTS, "对账表被清空——检查将空转"
    assert vcc.DESIGN_NOTATION_MIRRORS, "豁免清单被清空——检查将空转"
    assert vcc.check_real_models() == []
    assert vcc.check_mirror_consumption() == []
    assert vcc.main() == 0


def test_capability_mapping_was_dropped_deliberately():
    """第七轮核实：Rust `capability.rs::Capability` 是运行时能力对象，字段与
    capability.schema.json 的 required（scope/actions/resources）不是同一事物，
    第六轮的映射是误接——已删除并在此钉住，防止下一轮又被「补回去」。"""
    import verify_contract_compatibility as vcc

    assert "capability.schema.json" not in vcc.REAL_MODEL_CONTRACTS
    assert "CapabilityContract" in vcc.DESIGN_NOTATION_MIRRORS


@pytest.mark.parametrize("bad", ["record", "class", "struct"])
def test_decl_body_handles_all_three_kinds(bad):
    import verify_contract_compatibility as vcc

    text = (f"public sealed {bad} ApprovalRequest\n" if bad != "struct"
            else "pub struct Capability")
    body = ("{\n string Nonce;\n}" if bad == "class" else "(string Nonce, int X)")
    assert "Nonce" in vcc._decl_body(text + body, {
        "record": "ApprovalRequest", "class": "ApprovalRequest",
        "struct": "Capability"}[bad])
    assert vcc._decl_body("nothing here", "ApprovalRequest") is None

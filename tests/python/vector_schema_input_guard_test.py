# vector_schema_input_guard_test.py —— R7-SH-07（第七轮 2026-10-04）。
#
# 从 codegen_and_catalog_test.py 拆出（该文件已在行数基线内，只许减不许增）。
# 本文件钉的是 `validate_vector_schemas.py` 的**输入完整性**：
# ① `update-manifest-invalid.json` 缺失此前被 `if invalid_path.exists() else []`
#    静默跳过——deny_schema 双向断言整段消失且 exit 0，删一个文件即可在 CI 绿灯
#    下摘掉「schema 削弱检测」；
# ② 失效向量的语义级豁免此前完全由条目自述 `expected` 决定，改成任意字符串即
#    从「必须被 schema 拒」降级为 info，无取值上界。
from __future__ import annotations

import json
from pathlib import Path

import pytest
import validate_vector_schemas as vvs


@pytest.fixture()
def synthetic(tmp_path, monkeypatch):
    """最小可用面：schema + valid + invalid 三份输入落在 tmp 内。"""
    schemas = tmp_path / "schemas"
    schemas.mkdir()
    (schemas / "update-manifest.schema.json").write_text(
        json.dumps({"type": "object"}), encoding="utf-8")
    vectors = tmp_path / "vectors"
    vectors.mkdir()
    (vectors / "update-manifest-valid.json").write_text(
        json.dumps({"vectors": []}), encoding="utf-8")
    monkeypatch.setattr(vvs, "SCHEMAS", schemas)
    monkeypatch.setattr(vvs, "VECTORS", vectors)
    return schemas, vectors


def _write_invalid(vectors: Path, vectors_body: list[dict]) -> None:
    (vectors / "update-manifest-invalid.json").write_text(
        json.dumps({"vectors": vectors_body}), encoding="utf-8")


def test_missing_invalid_vectors_is_fail_closed(synthetic, capsys):
    """①：invalid 向量文件被删/改名 → 必须 fail-closed，不得静默跳过。"""
    _schemas, vectors = synthetic
    assert not (vectors / "update-manifest-invalid.json").exists()
    assert vvs.main() == 1
    assert "update-manifest-invalid.json" in capsys.readouterr().err


def test_unknown_expected_value_is_rejected(synthetic, capsys):
    """②：expected 自述任意字符串不得换取豁免。"""
    _schemas, vectors = synthetic
    _write_invalid(vectors, [{"case": "c1", "expected": "whatever",
                             "manifest": {"a": 1}}])
    assert vvs.main() == 1
    printed = capsys.readouterr()
    assert "expected 取值未知" in (printed.out + printed.err)


def test_known_expected_values_are_not_flagged(synthetic, capsys):
    """反向对照：白名单内的既有语义级取值不得被误杀（防「一律拒绝」式假修复）。

    合成树没有 action/capability/audit-event 六份双向向量，main() 因缺失文件返回 1
    ——本用例只判定「新检查没变成噪声」，故断言输出不含「expected 取值未知」。
    """
    _schemas, vectors = synthetic
    _write_invalid(vectors, [
        {"case": n, "expected": n, "manifest": {"a": 1}}
        for n in ("deny_rollback", "deny_threshold", "deny_expired")])
    vvs.main()
    printed = capsys.readouterr()
    assert "expected 取值未知" not in (printed.out + printed.err)


def test_deny_schema_still_requires_schema_rejection(synthetic, capsys):
    """deny_schema 是**必须被 schema 拒**的取值：schema 放行即红（原语义不回退）。"""
    _schemas, vectors = synthetic
    # schema 是 {"type":"object"}——任何 object 都通过，故 deny_schema 向量必红
    _write_invalid(vectors, [{"case": "c", "expected": "deny_schema",
                             "manifest": {"a": 1}}])
    assert vvs.main() == 1
    printed = capsys.readouterr()
    assert "deny_schema" in (printed.out + printed.err)


def test_known_deny_expected_whitelist_is_bounded():
    """白名单必须是**有界常量**且含实测在用的四个取值（集合扩大须显式提交）。"""
    assert vvs.KNOWN_DENY_EXPECTED == frozenset({
        "deny_schema", "deny_rollback", "deny_threshold", "deny_expired"})
    assert getattr(vvs, "KNOWN_DENY_EXPECTED", None) is not None

# ---------------------------------------------------------------- R8-PY-02
# 「缺 manifest」有两面：真实树里 4 条场景型向量本就没有 manifest（语义面在
# core/rust-policy-core/tests/vectors.rs），一律拒绝是噪声；一律放过则是掏空面
# ——把任一 manifest 键改名即零判定。以下用例钉住「有界登记」这个中间口径。


def test_unregistered_manifestless_vector_is_flagged(synthetic, capsys):
    """未登记的缺 manifest 条目必须红（改名/删除 manifest 键的掏空面）。"""
    _schemas, vectors = synthetic
    _write_invalid(vectors, [{"case": "brand_new_shape", "expected": "deny_threshold"}])
    assert vvs.main() == 1
    printed = capsys.readouterr()
    assert "未登记为场景型" in (printed.out + printed.err)


def test_registered_scenario_case_is_not_flagged(synthetic, capsys):
    """反向对照：已登记的场景型条目不得被误杀（防「一律拒绝」式假修复）。"""
    _schemas, vectors = synthetic
    _write_invalid(vectors, [{"case": "rollback", "expected": "deny_rollback",
                             "version": "0.9.0", "min_version": "1.0.0"}])
    vvs.main()
    printed = capsys.readouterr()
    assert "未登记为场景型" not in (printed.out + printed.err)
    assert "无 manifest 实例" not in (printed.out + printed.err)


def test_scenario_case_claiming_deny_schema_is_flagged(synthetic, capsys):
    """场景型条目自称 deny_schema 仍须红：schema 级主张却不给待拒实例＝无人判定。"""
    _schemas, vectors = synthetic
    _write_invalid(vectors, [{"case": "rollback", "expected": "deny_schema"}])
    assert vvs.main() == 1
    printed = capsys.readouterr()
    assert "无 manifest 实例" in (printed.out + printed.err)


def test_scenario_registry_has_zero_headroom_against_real_tree():
    """登记集与真实面**逐字相等**：新增缺 manifest 条目不登记即红；条目补上
    manifest 后登记集里的残留同样红（登记集不得变成长期豁免洞）。"""
    body = json.loads(
        (vvs.VECTORS / "update-manifest-invalid.json").read_text(encoding="utf-8")
    )["vectors"]
    manifestless = {v.get("case") for v in body
                    if not isinstance(v.get("manifest"), dict)}
    assert manifestless == set(vvs.SCENARIO_ONLY_CASES), (
        "真实树缺 manifest 的条目与登记集不同步："
        f"{sorted(manifestless)} vs {sorted(vvs.SCENARIO_ONLY_CASES)}")


def test_real_tree_passes_schema_validation():
    """真实面整体必须为绿——上面的反证用例只证「能红」，这条证「没变噪声」，
    同时钉住 singular_signature_field 现在真的向 schema 出了一个被拒实例。"""
    assert vvs.main() == 0


# ---------------------------------------------------------------- PY-272
class TestValidateVectorSchemasInputGuard:
    """PY-272（2026-10-02 审计）：valid 侧 _load 无守卫——schema 本体/valid
    向量缺失或坏 JSON 此前裸 FileNotFoundError/JSONDecodeError 栈。三处
    （schema/valid/invalid）统一包守卫 → 干净报告 + return 1。"""

    def test_missing_schema_file_returns_1_no_traceback(self, tmp_path, monkeypatch, capsys):
        import validate_vector_schemas as vvs
        # 空合成树：SCHEMAS/VECTORS 指向 tmp（update-manifest.schema.json 缺失）
        monkeypatch.setattr(vvs, "SCHEMAS", tmp_path / "schemas")
        monkeypatch.setattr(vvs, "VECTORS", tmp_path / "vectors")
        assert vvs.main() == 1
        err = capsys.readouterr().err
        assert "输入文件读取/解析失败" in err

    def test_corrupt_valid_vectors_returns_1(self, tmp_path, monkeypatch, capsys):
        import json as _json

        import validate_vector_schemas as vvs
        schemas = tmp_path / "schemas"
        schemas.mkdir()
        # 合法 schema 本体（最小可构造）+ 损坏的 valid 向量文件
        (schemas / "update-manifest.schema.json").write_text(
            _json.dumps({"type": "object"}), encoding="utf-8")
        vectors = tmp_path / "vectors"
        vectors.mkdir()
        (vectors / "update-manifest-valid.json").write_text("{ broken", encoding="utf-8")
        monkeypatch.setattr(vvs, "SCHEMAS", schemas)
        monkeypatch.setattr(vvs, "VECTORS", vectors)
        assert vvs.main() == 1
        assert "update-manifest-valid.json" in capsys.readouterr().err

    def test_corrupt_dual_direction_vector_counted_as_failure(
            self, tmp_path, monkeypatch, capsys):
        # PY-272 第三处：action/capability/audit-event 双向向量的 _load 同守卫
        # ——坏文件计入 failures 干净退出（不裸栈）
        import json as _json

        import validate_vector_schemas as vvs
        schemas = tmp_path / "schemas"
        schemas.mkdir()
        (schemas / "update-manifest.schema.json").write_text(
            _json.dumps({"type": "object"}), encoding="utf-8")
        vectors = tmp_path / "vectors"
        vectors.mkdir()
        (vectors / "update-manifest-valid.json").write_text(
            _json.dumps({"vectors": []}), encoding="utf-8")
        # R7-SH-07 之后 invalid 向量文件也是**必需要素**（缺失即 fail-closed，
        # 不再静默跳过），故合成树要把它补上，才能让断言落在本用例真正想测的
        # 「双向向量坏文件」分支上。
        (vectors / "update-manifest-invalid.json").write_text(
            _json.dumps({"vectors": []}), encoding="utf-8")
        (vectors / "action-valid.json").write_text("not json at all", encoding="utf-8")
        monkeypatch.setattr(vvs, "SCHEMAS", schemas)
        monkeypatch.setattr(vvs, "VECTORS", vectors)
        assert vvs.main() == 1
        err = capsys.readouterr().err
        assert "action-valid.json" in err and "读取/解析失败" in err

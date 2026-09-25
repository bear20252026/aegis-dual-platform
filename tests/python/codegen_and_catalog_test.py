# codegen_and_catalog_test.py —— contracts/codegen 生成器与静态分析器单测（pytest）。
# 覆盖审计条目：
#   PY-125 cs_type 表驱动
#   PY-126 generate 快照断言
#   PY-127 contract_name 用例
#   PY-128 陈旧清理回归（锁 PY-016）
#   PY-129 kt_type 表驱动
#   PY-130 尾逗号锁定（ktlint trailing-comma-on-declaration-site）
#   PY-131 contract_name 三副本一致性
#   PY-132 verify_bridge_guard.norm
#   PY-133 _first_diff
#   PY-134 Kotlin 占位符归一化端到端
#   PY-135 analyze_action_catalog 重复名检测
#   PY-136 scope 冲突检测
#   PY-137 audit/redteam_fixtures 缺失检测
#   PY-138 坏 yaml 解析路径
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "contracts" / "codegen"))

import analyze_action_catalog as aac  # noqa: E402
import generate_csharp as gcs  # noqa: E402
import generate_kotlin as gkt  # noqa: E402
import verify_bridge_guard as vbg  # noqa: E402
from verify_contract_compatibility import contract_name as contract_name_compat  # noqa: E402

# ---------------------------------------------------------------- PY-125
class TestCsType:
    @pytest.mark.parametrize("prop,expected", [
        ({"type": "string"}, "string"),
        ({"type": "integer"}, "long"),
        ({"type": "number"}, "decimal"),
        ({"type": "boolean"}, "bool"),
        ({"type": "object"}, "object"),
        ({"type": "array", "items": {"type": "string"}}, "List<string>"),
    ])
    def test_known_types(self, prop, expected):
        # PY-125：6 类型显式映射（number 不再降级 object——PY-099 锁定）
        assert gcs.cs_type(prop) == expected

    def test_unknown_type_fails_closed(self):
        with pytest.raises(ValueError, match="fail-closed"):
            gcs.cs_type({"type": "float"})


# ---------------------------------------------------------------- PY-126
SCHEMA = {
    "required": ["id"],
    "properties": {
        "id": {"type": "string"},
        "count": {"type": "integer"},
        "note": {"type": "string"},
    },
}


class TestGenerateCSharp:
    def test_snapshot(self):
        # PY-126：快照断言——必选在前、可选默认 null、无尾逗号（C# 语法）
        assert gcs.generate(SCHEMA, "Demo") == (
            "// 由 contracts/codegen/generate_csharp.py 生成（蓝图阶段 B——契约事实来源——请勿手工编辑）\n"
            "using System.Collections.Generic;\n"
            "namespace Aegis.Windows.Contracts.Generated;\n"
            "\n"
            "public sealed record Demo(\n"
            "    string id,\n"
            "    long? count = null,\n"
            "    string? note = null\n"
            ");"
        )


# ---------------------------------------------------------------- PY-127/131
class TestContractName:
    @pytest.mark.parametrize("stem,expected", [
        ("action", "ActionContract"),
        ("audit-event", "AuditEventContract"),
        ("update-manifest", "UpdateManifestContract"),
        ("release", "ReleaseContract"),
    ])
    def test_mapping(self, stem, expected):
        # PY-127：stem → 类型名稳定映射
        f = Path(f"{stem}.schema.json")
        assert gcs.contract_name(f) == expected

    def test_three_copies_identical(self):
        # PY-131：contract_name 在三个模块各有一份——语义必须一致（漂移即门禁假绿）
        for stem in ("action", "audit-event", "update-manifest"):
            f = Path(f"{stem}.schema.json")
            expected = gcs.contract_name(f)
            assert gkt.contract_name(f) == expected
            assert contract_name_compat(f) == expected


# ---------------------------------------------------------------- PY-128
class TestStaleCleanup:
    def test_stale_contract_file_removed(self, tmp_path, monkeypatch):
        # PY-128：陈旧清理回归（锁 PY-016）——被删除 schema 的旧生成文件
        # 必须被差集删除，不得永久残留
        out = tmp_path / "generated"
        out.mkdir()
        (out / "GhostContract.cs").write_text("// stale\n", encoding="utf-8")
        (out / "GhostContract.kt").write_text("// stale\n", encoding="utf-8")
        monkeypatch.setattr(gcs, "OUT", out)
        monkeypatch.setattr(gkt, "OUT", tmp_path / "generated_kt")
        gcs.main()
        gkt.main()
        assert not (out / "GhostContract.cs").exists()
        assert not (tmp_path / "generated_kt" / "GhostContract.kt").exists()
        # 真实 schema 生成物在位
        assert (out / "ActionContract.cs").is_file()
        assert (tmp_path / "generated_kt" / "ActionContract.kt").is_file()


# ---------------------------------------------------------------- PY-129/130
class TestKotlinGenerator:
    @pytest.mark.parametrize("prop,expected", [
        ({"type": "string"}, "String"),
        ({"type": "integer"}, "Long"),
        ({"type": "number"}, "Double"),
        ({"type": "boolean"}, "Boolean"),
        ({"type": "object"}, "Any"),
        ({"type": "array", "items": {"type": "integer"}}, "List<Long>"),
    ])
    def test_known_types(self, prop, expected):
        assert gkt.kt_type(prop) == expected

    def test_unknown_type_fails_closed(self):
        with pytest.raises(ValueError, match="fail-closed"):
            gkt.kt_type({"type": "decimal"})

    def test_trailing_comma_locked(self):
        # PY-130：尾逗恒定输出（ktlint trailing-comma-on-declaration-site 门禁）
        text = gkt.generate(SCHEMA, "Demo")
        val_lines = [ln for ln in text.splitlines() if ln.strip().startswith("val ")]
        assert len(val_lines) == 3
        for ln in val_lines:
            assert ln.rstrip().endswith(","), f"尾逗缺失: {ln}"
        # 可选参数：可空 + 默认 null
        assert "val note: String? = null," in text
        assert "val id: String," in text


# ---------------------------------------------------------------- PY-132/133
class TestBridgeGuardHelpers:
    def test_norm_unifies_newlines(self):
        # PY-132：CRLF / 裸 CR 统一 LF
        assert vbg.norm("a\r\nb\rc\nd") == "a\nb\nc\nd"

    def test_first_diff_pinpoints_line(self):
        # PY-133：首个差异行号 + 双侧内容
        msg = vbg._first_diff("l1\nl2\nl3", "l1\nlX\nl3")
        assert "第 2 行" in msg and "'l2'" in msg and "'lX'" in msg

    def test_first_diff_length_mismatch(self):
        assert "第 3 行" in vbg._first_diff("l1\nl2\nl3", "l1\nl2")
        assert "<EOF>" in vbg._first_diff("l1", "l1\nextra")

    def test_first_diff_identical_returns_marker(self):
        assert vbg._first_diff("a\nb", "a\nb") == "未知差异"


# ---------------------------------------------------------------- PY-134
CANONICAL_JS = (
    "// REQUIRED_SINKS: window.fetch = function|XMLHttpRequest.prototype.open\n"
    "const HOSTS = __AEGIS_HOSTS__;\n"
    "const REQUIRE_HTTPS = __AEGIS_REQUIRE_HTTPS__;\n"
    "if (!window.fetch) { XMLHttpRequest.prototype.open; }\n"
)


class TestKotlinPlaceholderNormalizationEndToEnd:
    def _write_env(self, tmp_path: Path, kt_template: str) -> None:
        template = tmp_path / "bridge_guard.template.js"
        template.write_text(CANONICAL_JS, encoding="utf-8")
        rust = tmp_path / "bridge_guard.rs"
        rust.write_text('static SCRIPT: &str = include_str!("bridge_guard.template.js");\n',
                        encoding="utf-8")
        (tmp_path / "WebViewHardening.kt").write_text(
            "object H {\n"
            '    val BRIDGE_GUARD_JS: String\n'
            '        get() = """' + kt_template + '""".trimIndent()\n'
            "}\n",
            encoding="utf-8",
        )
        vbg.CANONICAL = template
        vbg.RUST = rust
        vbg.KOTLIN = tmp_path / "WebViewHardening.kt"

    KT_OK = (
        "\n// REQUIRED_SINKS: window.fetch = function|XMLHttpRequest.prototype.open\n"
        "const HOSTS = [$allowedHostsJson];\n"
        "const REQUIRE_HTTPS = $requireHttpsJson;\n"
        "if (!window.fetch) { XMLHttpRequest.prototype.open; }\n"
    )

    def test_placeholders_normalized_and_match(self, tmp_path, monkeypatch):
        # PY-134：Kotlin 插值占位符归一化后与规范逐行一致 → 通过
        monkeypatch.setattr(vbg, "failures", [])
        self._write_env(tmp_path, self.KT_OK)
        assert vbg.main() == 0

    def test_unregistered_interpolation_detected(self, tmp_path, monkeypatch):
        # 未登记的新增占位符 $newPh（替换 Kotlin 插值 $requireHttpsJson）→
        # 归一化后残留 $ → 门禁失败（防占位符漏登记）
        monkeypatch.setattr(vbg, "failures", [])
        self._write_env(tmp_path, self.KT_OK.replace("$requireHttpsJson", "$newPh"))
        rc = vbg.main()
        assert rc == 1
        assert any("未登记插值" in f for f in vbg.failures)

    def test_drift_pinpointed(self, tmp_path, monkeypatch):
        monkeypatch.setattr(vbg, "failures", [])
        self._write_env(tmp_path, self.KT_OK + "// extra line\n")
        assert vbg.main() == 1
        assert any("不一致" in f for f in vbg.failures)


# ---------------------------------------------------------------- PY-135..138
def _action(name: str, scope: str, risk: str = "low") -> str:
    return (f"  - name: {name}\n"
            f"    scope: {scope}\n"
            f"    risk: {risk}\n"
            f"    audit: true\n"
            f"    redteam_fixtures: [x]\n")


class TestAnalyzeActionCatalog:
    def test_duplicate_name_detected(self):
        # PY-135：重复 action name → 报错并指出首次出现位置
        src = "actions:\n" + _action("op", "s1") + _action("op", "s2")
        errors = aac.analyze(src)
        assert any("重复 action name 'op'" in e for e in errors)

    def test_scope_risk_conflict_detected(self):
        # PY-136：同 scope 不同 risk → 冲突
        src = "actions:\n" + _action("a1", "s1", "low") + _action("a2", "s1", "high")
        errors = aac.analyze(src)
        assert any("存在多种 risk 等级" in e for e in errors)

    def test_missing_audit_and_fixtures_detected(self):
        # PY-137：audit / redteam_fixtures 缺失各自独立报告
        src = ("actions:\n"
               "  - name: bad\n"
               "    scope: s1\n"
               "    risk: low\n")
        errors = aac.analyze(src)
        assert any("缺少 audit" in e for e in errors)
        assert any("缺少 redteam_fixtures" in e for e in errors)

    def test_bad_yaml_reported_not_raised(self):
        # PY-138：坏 YAML → 返回解析错误列表（不抛异常）
        errors = aac.analyze("actions: [ {unclosed")
        assert errors and errors[0].startswith("YAML 解析错误")

    def test_clean_catalog_passes(self):
        src = "actions:\n" + _action("ok1", "s1") + _action("ok2", "s2")
        assert aac.analyze(src) == []

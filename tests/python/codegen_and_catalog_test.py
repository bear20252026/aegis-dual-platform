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
#   PY-188 enum/const 值域元数据 + PY-195 行号定位 + PY-197 required 未知属性
#   PY-215 锚点缺失严格单源（本批次新增）
# SP-161（2026-09-26 审计）：sys.path 注入统一走 conftest.py。
from __future__ import annotations

from pathlib import Path

import analyze_action_catalog as aac
import generate_csharp as gcs
import generate_kotlin as gkt
import pytest
import verify_bridge_guard as vbg
from verify_contract_compatibility import (
    contract_name as contract_name_compat,
)


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
        # PY-248：using 条件输出——本 schema 无数组属性，不再注入未用 using
        assert gcs.generate(SCHEMA, "Demo") == (
            "// 由 contracts/codegen/generate_csharp.py 生成（蓝图阶段 B——契约事实来源——请勿手工编辑）\n"
            "namespace Aegis.Windows.Contracts.Generated;\n"
            "\n"
            "public sealed record Demo(\n"
            "    string id,\n"
            "    long? count = null,\n"
            "    string? note = null\n"
            ");"
        )


# ---------------------------------------------------------------- PY-243/248
ARRAY_SCHEMA = {
    "required": ["id", "items"],
    "properties": {
        "id": {"type": "string"},
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["name"],
                "properties": {
                    "name": {"type": "string"},
                    "kind": {"type": "string", "enum": ["a", "b"]},
                    "note": {"type": "string"},
                },
            },
        },
    },
}


class TestNestedArrayModels:
    """PY-243：数组 items(object+properties) 生成嵌套子模型；PY-248：条件 using。"""

    def test_cs_nested_model_and_conditional_using(self):
        out = gcs.generate(ARRAY_SCHEMA, "Demo")
        assert "using System.Collections.Generic;" in out  # 有数组属性 → 保留 using
        assert "List<DemoItem> items" in out  # 强类型化，不再 List<object>
        assert "public sealed record DemoItem(" in out  # 嵌套 record 同文件
        assert "string name,\n    string? kind = null,\n    string? note = null\n);" in out  # 必选在前、可选可空
        assert "public static class DemoItemValues" in out  # 嵌套 enum 亦获锚点
        assert 'KindA = "a"' in out  # 常量名随属性名（Kind 而非 Platform）

    def test_kt_nested_model_mirrors_cs(self):
        out = gkt.generate(ARRAY_SCHEMA, "Demo")
        assert "val items: List<DemoItem>," in out  # 与 C# 同名单源（ident.py）
        assert "data class DemoItem(" in out
        assert "object DemoItemValues {" in out
        assert "const val KIND_A: String = \"a\"" in out

    def test_free_form_object_items_stay_loose(self):
        # 无 properties 的自由 object 无锚定面——保持原降级行为（向后兼容）
        schema = {"required": ["xs"],
                  "properties": {"xs": {"type": "array", "items": {"type": "object"}}}}
        assert "List<object> xs" in gcs.generate(schema, "Demo")
        assert "val xs: List<Any>," in gkt.generate(schema, "Demo")

    def test_array_of_object_requires_nested_model(self):
        # cs_type/kt_type 裸调用缺嵌套类型名即 fail-closed（禁止静默降级回 List<object>）
        with pytest.raises(ValueError, match="fail-closed"):
            gcs.cs_type(ARRAY_SCHEMA["properties"]["items"])
        with pytest.raises(ValueError, match="fail-closed"):
            gkt.kt_type(ARRAY_SCHEMA["properties"]["items"])

    def test_no_array_no_using(self):
        # PY-248：无数组属性的四份生成文件不再携带未用 using
        assert "using System.Collections.Generic;" not in gcs.generate(SCHEMA, "Demo")


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


# ---------------------------------------------------------------- PY-197
class TestRequiredUnknownPropertyFailClosed:
    def test_csharp_unknown_required_raises(self):
        # PY-197：required 引用未定义属性 → ValueError（此前静默丢弃必选约束）
        schema = {"required": ["id", "ghost"], "properties": {"id": {"type": "string"}}}
        with pytest.raises(ValueError, match="ghost"):
            gcs.generate(schema, "Demo")

    def test_kotlin_unknown_required_raises(self):
        schema = {"required": ["ghost"], "properties": {"id": {"type": "string"}}}
        with pytest.raises(ValueError, match="ghost"):
            gkt.generate(schema, "Demo")

    def test_known_required_still_passes(self):
        schema = {"required": ["id"], "properties": {"id": {"type": "string"}}}
        assert "string id" in gcs.generate(schema, "Demo")
        assert "val id: String" in gkt.generate(schema, "Demo")


# ---------------------------------------------------------------- PY-188
class TestEnumValueDomainDegraded:
    def test_csharp_and_kotlin_value_domain_metadata(self):
        # PY-188（降级）：enum/const 值域以元数据 API 暴露——不产出 enum
        # 类型（取舍说明见 generate_csharp.describe_value_domain 文档注释）
        prop = {"type": "string", "enum": ["GET", "POST", "DELETE"]}
        assert gcs.describe_value_domain(prop) == "enum: GET | POST | DELETE"
        assert gkt.describe_value_domain(prop) == "enum: GET | POST | DELETE"
        assert gcs.describe_value_domain({"const": "Aegis"}) == "const: Aegis"
        assert gkt.describe_value_domain({"const": 1}) == "const: 1"
        assert gcs.describe_value_domain({"type": "string"}) == ""

    def test_real_schema_enum_domains_locked(self):
        # PY-188 单测锁定：真实 schema 的 enum 值域（防止 schema 静默改动值域）
        import json
        schemas = Path(__file__).resolve().parents[2] / "contracts" / "schemas"
        action = json.loads((schemas / "action.schema.json").read_text(encoding="utf-8"))
        assert gcs.describe_value_domain(action["properties"]["method"]) == (
            "enum: GET | POST | PUT | DELETE | NAVIGATE | DOWNLOAD")
        update = json.loads((schemas / "update-manifest.schema.json").read_text(encoding="utf-8"))
        assert gkt.describe_value_domain(update["properties"]["channel"]) == (
            "enum: stable | beta | nightly")

    def test_constants_class_generated_alongside_plain_string(self):
        # PY-188 完整化（收尾批）：属性保持基础类型（不破坏镜像消费方），
        # 另生成 {Name}Values 常量类/常量 object——值域编译期锚点，schema 单源
        schema = {"properties": {"method": {"type": "string",
                                            "enum": ["GET", "POST"]}}}
        cs = gcs.generate(schema, "Demo")
        assert "string? method = null" in cs  # 属性类型不升级（消费方兼容）
        assert 'public const string MethodGET = "GET"' in cs
        assert 'public const string MethodPOST = "POST"' in cs
        kt = gkt.generate(schema, "Demo")
        assert "val method: String? = null" in kt
        assert 'const val METHOD_GET: String = "GET"' in kt
        assert 'const val METHOD_POST: String = "POST"' in kt

    def test_const_literal_and_non_string_types(self):
        # const（含非字符串字面量）→ 单常量；integer const → long/Long
        schema = {"properties": {"schema_version": {"const": 1}}}
        cs = gcs.generate(schema, "Demo")
        assert "public const long SchemaVersion = 1;" in cs
        kt = gkt.generate(schema, "Demo")
        assert "const val SCHEMA_VERSION: Long = 1" in kt

    def test_no_enum_no_values_class(self):
        # 无 enum/const 的 schema 不产出 Values 类（镜像形状不变）
        schema = {"properties": {"url": {"type": "string"}}}
        assert "Values" not in gcs.generate(schema, "Demo")
        assert "Values" not in gkt.generate(schema, "Demo")


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
# PY-236（2026-10-01 审计）：body 行必须真实承载锚点声明的每个 sink——
# 合成模板补 sink 实现行（与真实 bridge_guard.template.js 同构），
# 否则新 body 检查正确地拒绝空心化模板。
CANONICAL_JS = (
    "// REQUIRED_SINKS: window.fetch = function|XMLHttpRequest.prototype.open\n"
    "const HOSTS = __AEGIS_HOSTS__;\n"
    "const REQUIRE_HTTPS = __AEGIS_REQUIRE_HTTPS__;\n"
    "window.fetch = function (...args) { guard(args); };\n"
    "if (!window.fetch) { XMLHttpRequest.prototype.open; }\n"
)


class TestKotlinPlaceholderNormalizationEndToEnd:
    def _write_env(self, tmp_path: Path, monkeypatch, kt_template: str) -> None:
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
        # PY-231（2026-10-01 审计）：CANONICAL/RUST/KOTLIN 此前直接改模块全局
        # 不经 monkeypatch——测试泄漏污染同进程后续用例（真实仓库路径被
        # 覆盖后不还原）。三处统一走 monkeypatch.setattr（自动还原）。
        monkeypatch.setattr(vbg, "CANONICAL", template)
        monkeypatch.setattr(vbg, "RUST", rust)
        monkeypatch.setattr(vbg, "KOTLIN", tmp_path / "WebViewHardening.kt")

    KT_OK = (
        "\n// REQUIRED_SINKS: window.fetch = function|XMLHttpRequest.prototype.open\n"
        "const HOSTS = [$allowedHostsJson];\n"
        "const REQUIRE_HTTPS = $requireHttpsJson;\n"
        "window.fetch = function (...args) { guard(args); };\n"
        "if (!window.fetch) { XMLHttpRequest.prototype.open; }\n"
    )

    def test_placeholders_normalized_and_match(self, tmp_path, monkeypatch):
        # PY-134：Kotlin 插值占位符归一化后与规范逐行一致 → 通过
        monkeypatch.setattr(vbg, "failures", [])
        self._write_env(tmp_path, monkeypatch, self.KT_OK)
        assert vbg.main() == 0

    def test_unregistered_interpolation_detected(self, tmp_path, monkeypatch):
        # 未登记的新增占位符 $newPh（替换 Kotlin 插值 $requireHttpsJson）→
        # 归一化后残留 $ → 门禁失败（防占位符漏登记）
        monkeypatch.setattr(vbg, "failures", [])
        self._write_env(tmp_path, monkeypatch, self.KT_OK.replace("$requireHttpsJson", "$newPh"))
        rc = vbg.main()
        assert rc == 1
        assert any("未登记插值" in f for f in vbg.failures)

    def test_drift_pinpointed(self, tmp_path, monkeypatch):
        monkeypatch.setattr(vbg, "failures", [])
        self._write_env(tmp_path, monkeypatch, self.KT_OK + "// extra line\n")
        assert vbg.main() == 1
        assert any("不一致" in f for f in vbg.failures)

    def test_hollowed_body_rejected(self, tmp_path, monkeypatch):
        # PY-236（2026-10-01 审计）：锚点行声明的 sink 此前对 canonical 全文
        # 查包含——锚点行自身含 sink 名，把 body 实现代码删光（守卫空心化）
        # 门禁仍绿。现对剔除锚点行后的 body 检查——空心化必须失败。
        monkeypatch.setattr(vbg, "failures", [])
        # 模板只剩锚点行 + 占位符声明（无任何 sink 实现代码）
        hollow = (
            "// REQUIRED_SINKS: window.fetch = function|XMLHttpRequest.prototype.open\n"
            "const HOSTS = __AEGIS_HOSTS__;\n"
            "const REQUIRE_HTTPS = __AEGIS_REQUIRE_HTTPS__;\n"
        )
        (tmp_path / "bridge_guard.template.js").write_text(hollow, encoding="utf-8")
        rust = tmp_path / "bridge_guard.rs"
        rust.write_text('static SCRIPT: &str = include_str!("bridge_guard.template.js");\n',
                        encoding="utf-8")
        kt = tmp_path / "WebViewHardening.kt"
        kt.write_text(
            "object H {\n"
            '    val BRIDGE_GUARD_JS: String\n'
            '        get() = """\n' + hollow + '""".trimIndent()\n'
            "}\n",
            encoding="utf-8",
        )
        monkeypatch.setattr(vbg, "CANONICAL", tmp_path / "bridge_guard.template.js")
        monkeypatch.setattr(vbg, "RUST", rust)
        monkeypatch.setattr(vbg, "KOTLIN", kt)
        assert vbg.main() == 1
        assert any("body 含拦截点" in f for f in vbg.failures)

    def test_module_paths_restored_after_run(self, tmp_path, monkeypatch):
        # PY-231：模块级路径经 monkeypatch 注入后必须自动还原——
        # 同进程后续用例不得读到 tmp 覆盖值（测试泄漏回归锚）
        import contracts.codegen.verify_bridge_guard as fresh
        before = (vbg.CANONICAL, vbg.RUST, vbg.KOTLIN)
        monkeypatch.setattr(vbg, "failures", [])
        self._write_env(tmp_path, monkeypatch, self.KT_OK)
        assert vbg.main() == 0
        monkeypatch.undo()
        assert (vbg.CANONICAL, vbg.RUST, vbg.KOTLIN) == before
        assert fresh.CANONICAL.is_absolute()


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

    def test_duplicate_reports_real_yaml_line(self):
        # PY-195：重复报告的"首次出现行"必须是真实 YAML 行号（start_mark.line+1），
        # 不再是列表下标。第一个 action 在源文本第 2 行（actions: 占第 1 行）。
        src = "actions:\n" + _action("op", "s1") + _action("op", "s2")
        first_line = next(
            i for i, ln in enumerate(src.splitlines(), start=1) if "name: op" in ln)
        errors = aac.analyze(src)
        dup = next(e for e in errors if "重复 action name 'op'" in e)
        assert f"首次出现行 {first_line}" in dup, dup
        assert "列表下标 0" not in dup

    def test_line_mark_fallback_labels_index(self):
        # PY-195：行号不可得时文案必须标注"列表下标"——不让定位信息撒谎
        from unittest import mock
        src = "actions:\n" + _action("op", "s1") + _action("op", "s2")
        with mock.patch.object(aac, "_action_start_lines",
                               return_value=[(None, False), (None, False)]):
            errors = aac.analyze(src)
        dup = next(e for e in errors if "重复 action name 'op'" in e)
        assert "首次出现列表下标 0" in dup, dup


# ---------------------------------------------------------------- PY-215
class TestBridgeGuardNoFallback:
    def test_missing_anchor_is_failure_not_fallback(self, tmp_path, monkeypatch):
        # PY-215：REQUIRED_SINKS_FALLBACK 已删除——模板锚点缺失直接计
        # failures（main 返回 1），不再回退内置清单（严格单源）
        monkeypatch.setattr(vbg, "failures", [])
        template = tmp_path / "bridge_guard.template.js"
        # 合法模板但缺 REQUIRED_SINKS 锚点行
        template.write_text(
            "const HOSTS = __AEGIS_HOSTS__;\n"
            "const REQUIRE_HTTPS = __AEGIS_REQUIRE_HTTPS__;\n",
            encoding="utf-8")
        rust = tmp_path / "bridge_guard.rs"
        rust.write_text('static SCRIPT: &str = include_str!("bridge_guard.template.js");\n',
                        encoding="utf-8")
        kt = tmp_path / "WebViewHardening.kt"
        kt.write_text(
            "object H {\n"
            '    val BRIDGE_GUARD_JS: String\n'
            '        get() = """\n'
            "const HOSTS = [$allowedHostsJson];\n"
            "const REQUIRE_HTTPS = $requireHttpsJson;\n"
            '""".trimIndent()\n'
            "}\n",
            encoding="utf-8")
        monkeypatch.setattr(vbg, "CANONICAL", template)
        monkeypatch.setattr(vbg, "RUST", rust)
        monkeypatch.setattr(vbg, "KOTLIN", kt)
        assert vbg.main() == 1
        assert any("REQUIRED_SINKS 锚点行" in f for f in vbg.failures)

    def test_no_fallback_constant_left(self):
        # PY-215：第二事实源已物理移除
        assert not hasattr(vbg, "REQUIRED_SINKS_FALLBACK")

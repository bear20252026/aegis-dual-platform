# coverage_round2_test.py —— 覆盖率报告驱动补测第二轮（SP-258）。
# 首轮 CI 实测缺口：verify_versions.py 54%（主对账体 70-132 行零覆盖）、
# verify_contract_compatibility.py 28%（check_* 全分支零覆盖）。
# 本文件补齐两脚本的通过/漂移/缺文件/tag/applicationId 取舍分支（tmp 树隔离）。
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import pytest

# 仓库根锚定（不依赖 pytest 调用 CWD——CI 与本地同口径；tests/python→tests→根）
REPO = Path(__file__).resolve().parents[2]


# ---------------- verify_versions.py ----------------

PROPS_FULL = (
    "VERSION_NAME=2.2.0\n"
    "VERSION_CODE=20248\n"
    "WINDOWS_PACKAGE_VERSION=2.2.0.0\n"
    "WINDOWS_PACKAGE_IDENTITY=com.aegisidentity\n"
    "DISPLAY_NAME=Aegis\n"
    "ANDROID_APPLICATION_ID=com.aegis.browser\n"
)
GRADLE_WIRED = (
    'android {\n'
    '    versionName = versionNameFromProperties\n'
    '    versionCode = versionCodeFromProperties\n'
    '    applicationId = "com.aegis.browser"\n'
    '}\n'
)
GRADLE_HARDCODED = GRADLE_WIRED.replace(
    'versionName = versionNameFromProperties', 'versionName = "2.2.0"')


@pytest.fixture()
def vv_tree(tmp_path, monkeypatch):
    """构建三端一致的最小版本树，并注入被测模块 ROOT/argv。"""
    import verify_versions as vv
    (tmp_path / "shared").mkdir(parents=True)
    (tmp_path / "android" / "app").mkdir(parents=True)
    csproj_dir = tmp_path / "windows" / "src" / "Aegis.Windows.App"
    csproj_dir.mkdir(parents=True)
    monkeypatch.setattr(vv, "ROOT", tmp_path)
    monkeypatch.setattr(sys, "argv", ["verify_versions.py"])

    def build(*, props=PROPS_FULL, gradle=GRADLE_WIRED, csproj=None, release=None):
        (tmp_path / "shared" / "version.properties").write_text(props, encoding="utf-8")
        (tmp_path / "android" / "app" / "build.gradle.kts").write_text(gradle, encoding="utf-8")
        (csproj_dir / "Aegis.Windows.App.csproj").write_text(
            csproj
            or ("<Project>\n"
                "  <Version>2.2.0</Version>\n"
                "  <AssemblyVersion>2.2.0.0</AssemblyVersion>\n"
                "  <FileVersion>2.2.0.0</FileVersion>\n"
                "  <PackageId>com.aegisidentity</PackageId>\n"
                "  <Product>Aegis</Product>\n"
                "</Project>\n"),
            encoding="utf-8")
        (tmp_path / "shared" / "release.json").write_text(
            release
            or json.dumps({"version": "2.2.0", "versionCode": 20248,
                           "android": {"applicationId": "com.aegis.browser"}}),
            encoding="utf-8")

    return vv, build


def test_verify_versions_happy_path(vv_tree, capsys):
    vv, build = vv_tree
    build()
    assert vv.main() == 0
    assert "Version verification passed: v2.2.0" in capsys.readouterr().out


def test_verify_versions_detects_csproj_drift(vv_tree, capsys):
    vv, build = vv_tree
    build(csproj="<Project>\n  <Version>9.9.9</Version>\n</Project>\n")
    assert vv.main() == 1
    out = capsys.readouterr().out
    assert "Windows Version" in out and "9.9.9" in out


def test_verify_versions_tag_mismatch_and_match(vv_tree, capsys, monkeypatch):
    vv, build = vv_tree
    build()
    monkeypatch.setattr(sys, "argv", ["verify_versions.py", "--tag", "v9.9.9"])
    assert vv.main() == 1
    assert "Release tag: found 'v9.9.9', expected 'v2.2.0'" in capsys.readouterr().out
    monkeypatch.setattr(sys, "argv", ["verify_versions.py", "--tag", "v2.2.0"])
    assert vv.main() == 0


def test_verify_versions_without_app_id_skips_reconciliation(vv_tree):
    # PY-230：ANDROID_APPLICATION_ID 缺键不强制——applicationId 对账整体跳过
    vv, build = vv_tree
    build(
        props=PROPS_FULL.replace("ANDROID_APPLICATION_ID=com.aegis.browser\n", ""),
        gradle='android {\n    versionName = versionNameFromProperties\n'
               '    versionCode = versionCodeFromProperties\n}\n',
        release=json.dumps({"version": "2.2.0", "versionCode": 20248}),
    )
    assert vv.main() == 0


def test_verify_versions_flags_hardcoded_android_version(vv_tree, capsys):
    vv, build = vv_tree
    build(gradle=GRADLE_HARDCODED)
    assert vv.main() == 1
    # 硬编码回潮 → wiring 判 False（报告标签为 expected 字典键 "Android versionName"）
    assert "Android versionName: found False, expected True" in capsys.readouterr().out


def test_verify_versions_missing_file_and_key(vv_tree, capsys):
    vv, build = vv_tree
    build()
    # 缺文件：干净报错（PY-028 口径）
    (vv.ROOT / "windows" / "src" / "Aegis.Windows.App" / "Aegis.Windows.App.csproj").unlink()
    assert vv.main() == 1
    assert "required file missing" in capsys.readouterr().out
    # 缺必需键：required/missing 汇总（PY-027 口径）
    build(props=PROPS_FULL.replace("DISPLAY_NAME=Aegis\n", ""))
    assert vv.main() == 1
    out = capsys.readouterr().out
    assert "missing version properties" in out and "DISPLAY_NAME" in out


def test_expected_xml_value_unescapes_and_assignment_forms():
    import verify_versions as vv
    assert vv.expected_xml_value("<Product>A &amp; B</Product>", "Product") == "A & B"
    assert vv.expected_xml_value("<Version>1.2.3</Version>", "Version") == "1.2.3"
    assert vv.expected_xml_value("<Version></Version>", "Version") is None
    assert vv.expected_assignment('applicationId = "com.aegis"', "applicationId") == "com.aegis"
    assert vv.expected_assignment("versionCode = 20248", "versionCode") == "20248"
    assert vv.expected_assignment("versionName = versionNameFromProperties", "versionName") is None


# ---------------- verify_contract_compatibility.py ----------------


@pytest.fixture()
def vcc_tree(tmp_path, monkeypatch):
    """真实 schemas/vectors 拷入 tmp 契约树；生成物目录按需产出。

    审计第七轮（R7-SH-01 新增 check_real_models）：合成树必须同时带上被对账的
    **手写模型原件**（Decision.cs / AuditEvent.cs），否则新检查在合成树里读不到
    文件、happy path 恒失败——那不是门禁严格，是合成树不完整。
    """
    import verify_contract_compatibility as vcc
    repo = tmp_path / "repo"
    contracts = repo / "contracts"
    shutil.copytree(REPO / "contracts" / "schemas", contracts / "schemas")
    shutil.copytree(REPO / "contracts" / "vectors", contracts / "vectors")
    for rel_schema, (rel_model, _lang, _type) in vcc.REAL_MODEL_CONTRACTS.items():
        src = REPO / rel_model
        if not src.is_file():
            # 表内登记的模型文件在真实仓库里不存在——这本身就是缺陷，让测试炸
            raise AssertionError(f"REAL_MODEL_CONTRACTS 指向的模型文件缺失：{rel_model}")
        dst = repo / rel_model
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dst)
    # 生成目录本身在真实仓库里恒存在——合成树也要建（空目录=有镜像面但无镜像），
    # 否则 check_mirror_consumption 会把「目录不存在」报成缺陷，掩盖被测语义本身。
    (repo / "windows" / "src" / "Aegis.Windows.App" / "Contracts" / "Generated").mkdir(
        parents=True, exist_ok=True)
    (repo / "android" / "contracts" / "src" / "main" / "kotlin" / "com" / "aegis"
     / "contracts" / "generated").mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(vcc, "ROOT", contracts)
    monkeypatch.setattr(vcc, "SCHEMAS", contracts / "schemas")
    monkeypatch.setattr(vcc, "VECTORS", contracts / "vectors")
    return vcc, repo, contracts


def _materialize_models(vcc, repo, contracts, only=None):
    """按生成器现算内容写出期望生成物（黄金在飞——diff 逻辑独立于硬编码样本）。"""
    cs_dir = repo / "windows" / "src" / "Aegis.Windows.App" / "Contracts" / "Generated"
    kt_dir = repo / "android" / "contracts" / "src" / "main" / "kotlin" / "com" / "aegis" / "contracts" / "generated"
    cs_dir.mkdir(parents=True, exist_ok=True)
    kt_dir.mkdir(parents=True, exist_ok=True)
    for f in sorted(vcc.SCHEMAS.glob("*.json")):
        if f.name in vcc.SKIP_SCHEMAS or (only and f.name != only):
            continue
        schema = json.loads(f.read_text(encoding="utf-8"))
        name = vcc.contract_name(f)
        (cs_dir / f"{name}.cs").write_text(
            vcc.generate_cs_model(schema, name) + "\n", encoding="utf-8")
        (kt_dir / f"{name}.kt").write_text(
            vcc.generate_kt_model(schema, name) + "\n", encoding="utf-8")


def test_contract_name_normalization():
    import verify_contract_compatibility as vcc

    assert vcc.contract_name(Path("update-manifest.schema.json")) == "UpdateManifestContract"
    assert vcc.contract_name(Path("approval.json")) == "ApprovalContract"


def test_contract_compatibility_happy_path(vcc_tree, capsys):
    vcc, repo, contracts = vcc_tree
    _materialize_models(vcc, repo, contracts)
    assert vcc.main() == 0
    assert "契约兼容性验证通过" in capsys.readouterr().out


def test_contract_compatibility_detects_drift(vcc_tree, capsys):
    vcc, repo, contracts = vcc_tree
    _materialize_models(vcc, repo, contracts, only="approval.schema.json")
    # 其余 schema 未物化 → 缺失失败；approval 手改 → 漂移失败（两类同屏）
    cs = (repo / "windows" / "src" / "Aegis.Windows.App" / "Contracts" / "Generated"
          / "ApprovalContract.cs")
    cs.write_text(cs.read_text(encoding="utf-8").replace("public", "public // drift"), encoding="utf-8")
    assert vcc.main() == 1
    out = capsys.readouterr().out
    assert "C# 模型与 schema 漂移: ApprovalContract.cs" in out
    assert "C# 模型缺失" in out and "Kotlin 模型缺失" in out


def test_contract_compatibility_skip_schema_needs_no_model(vcc_tree, capsys, monkeypatch):
    vcc, repo, contracts = vcc_tree
    skip = sorted(vcc.SKIP_SCHEMAS)[0]
    for f in list(vcc.SCHEMAS.glob("*.json")):
        if f.name != skip:
            f.unlink()
    for f in list(vcc.VECTORS.glob("*.json")):
        f.unlink()
    # 本用例只测 PY-102 跳过集语义，因此把合成树删到只剩一个 SKIP 集 schema。
    # R7-SH-01 的 check_real_models 会因 approval/audit-event schema 被删而报
    # 「真实模型对账无法进行」——那是**正确**判定（删 schema 文件确实减了契约面，
    # 旧门禁对此完全无感，见 contract_models_test.py::test_missing_referenced_schema
    # 专门钉这条），只是与 PY-102 无关，故此处把对账表清空以隔离被测语义。
    monkeypatch.setattr(vcc, "REAL_MODEL_CONTRACTS", {})
    # 仅剩 SKIP 集内 schema——不生成模型也应通过（PY-102 跳过集单源口径）
    assert vcc.main() == 0


def test_contract_compatibility_bad_json_failures_collected(vcc_tree, capsys):
    vcc, repo, contracts = vcc_tree
    (vcc.SCHEMAS / "broken.schema.json").write_text("{not json", encoding="utf-8")
    (vcc.VECTORS / "broken.json").write_text("{bad", encoding="utf-8")
    assert vcc.main() == 1
    out = capsys.readouterr().out
    assert "schema JSON 无效: broken.schema.json" in out
    assert "vector JSON 无效: broken.json" in out

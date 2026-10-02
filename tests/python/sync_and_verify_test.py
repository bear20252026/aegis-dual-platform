# sync_and_verify_test.py —— 版本同步/校验链单测（pytest）。
# 覆盖审计条目：
#   PY-103 load_properties（注释/空行/值含=）
#   PY-104 replace_assignment（count/缩进/引号）——PY-265：函数已迁本文件
#         测试侧（生产零调用——PY-216 起 gradle 字面量写入删除）
#   PY-105 replace_xml_value（缺失抛错/首匹配）
#   PY-106 expected_xml_value
#   PY-107 expected_assignment
#   PY-108 dedup_release_assets 主逻辑三用例
#   PY-186 replace_xml_value 转义 + 函数式替换（本批次新增）
#   PY-198 VERSION_CODE isdigit 校验（本批次新增）
# SP-161（2026-09-26 审计）：sys.path 注入统一走 conftest.py
#（保留 ROOT——dedup 脚本 subprocess 路径仍需它）。
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]

import sync_versions
from atomic_write import atomic_write_text
from sync_versions import (
    load_properties,
    replace_xml_value,
)
from verify_versions import expected_assignment, expected_xml_value


# ---------------------------------------------------------------- PY-265
def replace_assignment(path: Path, name: str, value: str, quoted: bool) -> None:
    """PY-265（2026-10-02 审计）：自 scripts/sync_versions.py 迁入测试侧——
    PY-216 起 gradle 字面量写入已删除（AD-100 构建期消费 properties），
    生产零调用（唯一消费方是本文件的 PY-104/PY-224 回归用例）。
    保留原实现与原子写接线（PY-278 同口径——函数体行为不变受测）。"""
    text = path.read_text(encoding="utf-8")
    assignment = f'{name} = "{value}"' if quoted else f"{name} = {value}"
    pattern = rf"(?m)^(?P<indent>[ \t]*){re.escape(name)}\s*=\s*(?:\"[^\"]*\"|\d+)\s*$"
    # PY-224（2026-10-01 审计）：函数式替换（lambda）——替换内容不经过
    # backslash 模板解析（值含 \1 不再被当组引用）
    updated, count = re.subn(pattern, lambda m: m.group("indent") + assignment, text, count=1)
    if count != 1:
        raise RuntimeError(f"expected {name} assignment not found in {path}")
    atomic_write_text(path, updated)


# ---------------------------------------------------------------- PY-103
class TestLoadProperties:
    def test_comments_and_blank_lines_skipped(self, tmp_path):
        p = tmp_path / "v.properties"
        p.write_text(
            "# 顶部注释\n"
            "\n"
            "   \n"
            "VERSION_NAME=2.2.0-beta.49\n"
            "  # 缩进注释\n"
            "VERSION_CODE = 20248\n",
            encoding="utf-8",
        )
        assert load_properties(p) == {"VERSION_NAME": "2.2.0-beta.49", "VERSION_CODE": "20248"}

    def test_value_containing_equals_kept_whole(self, tmp_path):
        # split("=", 1)——值中的 "=" 不拆分（如 base64/URL 参数）
        p = tmp_path / "v.properties"
        p.write_text("TOKEN=a=b=c\n", encoding="utf-8")
        assert load_properties(p) == {"TOKEN": "a=b=c"}

    def test_missing_equals_raises_with_path_and_lineno(self, tmp_path):
        # PY-026：无 "=" 非法行 → RuntimeError 带文件路径与行号（不再裸 ValueError）
        p = tmp_path / "v.properties"
        p.write_text("GOOD=1\nBROKEN_LINE\n", encoding="utf-8")
        with pytest.raises(RuntimeError) as excinfo:
            load_properties(p)
        msg = str(excinfo.value)
        assert "v.properties" in msg and ":2:" in msg and "BROKEN_LINE" in msg


# ---------------------------------------------------------------- PY-104
class TestReplaceAssignment:
    def test_unquoted_and_quoted_replacement(self, tmp_path):
        p = tmp_path / "build.gradle.kts"
        p.write_text('versionCode = 1\nversionName = "0.0.1"\n', encoding="utf-8")
        replace_assignment(p, "versionCode", "42", quoted=False)
        replace_assignment(p, "versionName", "2.2.0", quoted=True)
        text = p.read_text(encoding="utf-8")
        assert "versionCode = 42" in text
        assert 'versionName = "2.2.0"' in text

    def test_indentation_preserved(self, tmp_path):
        p = tmp_path / "build.gradle.kts"
        p.write_text("android {\n    versionCode = 1\n}\n", encoding="utf-8")
        replace_assignment(p, "versionCode", "9", quoted=False)
        assert "    versionCode = 9" in p.read_text(encoding="utf-8")

    def test_replaces_first_occurrence_only(self, tmp_path):
        p = tmp_path / "f.txt"
        p.write_text("versionCode = 1\nversionCode = 2\n", encoding="utf-8")
        replace_assignment(p, "versionCode", "7", quoted=False)
        lines = p.read_text(encoding="utf-8").splitlines()
        assert lines[0] == "versionCode = 7" and lines[1] == "versionCode = 2"

    def test_missing_assignment_raises(self, tmp_path):
        p = tmp_path / "f.txt"
        p.write_text("other = 1\n", encoding="utf-8")
        with pytest.raises(RuntimeError, match="versionCode"):
            replace_assignment(p, "versionCode", "7", quoted=False)
        # 失败不落盘（原文件保持原样——fail-closed 不写半截）
        assert "other = 1" in p.read_text(encoding="utf-8")

    def test_backslash_value_not_treated_as_backreference(self, tmp_path):
        # PY-224（2026-10-01 审计）：值含 \1（正则反向引用形态）必须按字面
        # 写入——函数式替换后替换串不再经过 backslash 模板解析
        #（此前 re.error "bad escape" 或静默错位）
        p = tmp_path / "f.txt"
        p.write_text("suffix = \"old\"\n", encoding="utf-8")
        replace_assignment(p, "suffix", r"C:\1\2", quoted=True)
        assert 'suffix = "C:\\1\\2"' in p.read_text(encoding="utf-8")


# ---------------------------------------------------------------- PY-105
class TestReplaceXmlValue:
    def test_replaces_first_match(self, tmp_path):
        p = tmp_path / "a.csproj"
        p.write_text(
            "<Project><Version>0.0.1</Version><Version>0.0.2</Version></Project>",
            encoding="utf-8",
        )
        replace_xml_value(p, "Version", "2.2.0")
        assert "<Version>2.2.0</Version><Version>0.0.2</Version>" in p.read_text(encoding="utf-8")

    def test_missing_element_raises(self, tmp_path):
        p = tmp_path / "a.csproj"
        p.write_text("<Project><Other>x</Other></Project>", encoding="utf-8")
        with pytest.raises(RuntimeError, match="Version"):
            replace_xml_value(p, "Version", "2.2.0")


# ---------------------------------------------------------------- PY-186
class TestReplaceXmlValueEscaping:
    def test_xml_metachars_escaped(self, tmp_path):
        # PY-186：DISPLAY_NAME 含 &/< 时必须转义——否则生成非法 csproj
        p = tmp_path / "a.csproj"
        p.write_text("<Project><Product>old</Product></Project>", encoding="utf-8")
        replace_xml_value(p, "Product", "Aegis & Bros <Pro>")
        text = p.read_text(encoding="utf-8")
        assert "<Product>Aegis &amp; Bros &lt;Pro&gt;</Product>" in text

    def test_backslash_value_not_treated_as_regex_backreference(self, tmp_path):
        # PY-186：值含 \1（正则反向引用形态）必须按字面写入——函数式替换
        # 不再经过 backslash 模板解析（此前 re.error / 静默错位）
        p = tmp_path / "a.csproj"
        p.write_text("<Project><Product>old</Product></Project>", encoding="utf-8")
        replace_xml_value(p, "Product", r"C:\1\2 & co")
        text = p.read_text(encoding="utf-8")
        assert "<Product>C:\\1\\2 &amp; co</Product>" in text


# ---------------------------------------------------------------- PY-106/107
class TestExpectedValueExtractors:
    def test_expected_xml_value(self):
        text = "<Project><Version>  2.2.0-beta.49 </Version></Project>"
        assert expected_xml_value(text, "Version") == "2.2.0-beta.49"
        assert expected_xml_value("<Project></Project>", "Version") is None

    def test_expected_xml_value_regex_metachars_in_element(self):
        # 元素名经 re.escape——含正则元字符的元素名不得崩
        assert expected_xml_value("<a.b>1</a.b>", "a.b") == "1"

    def test_expected_xml_value_unescapes_entities(self):
        # PY-223（2026-10-01 审计）：磁盘 XML 文本节点是转义形态——取值须
        # unescape 还原再比较（此前 DISPLAY_NAME 含 & 时 csproj 写入 "&amp;"
        # 而单源值是 "&"，逐位比较必误报漂移）。与 sync_versions.escape() 对偶。
        assert expected_xml_value(
            "<Product>Aegis &amp; Bros</Product>", "Product") == "Aegis & Bros"
        assert expected_xml_value("<P>a &lt; b &gt; c</P>", "P") == "a < b > c"
        # 对偶边界：unescape 只还原写侧 escape() 会产生的三实体
        #（&amp;/&lt;/&gt;——文本节点契约；&quot;/&apos; 是属性值形态，
        # 写侧不产生，读侧亦不误动）
        assert expected_xml_value(
            "<P>q &quot;w&quot;</P>", "P") == "q &quot;w&quot;"

    def test_xml_roundtrip_escape_unescape(self, tmp_path):
        # PY-223 往返锁定：sync_versions 写入（escape）→ verify_versions 读出
        # （unescape）——含 & 的 DISPLAY_NAME 全链零漂移
        import sync_versions as sv
        import verify_versions as vv
        p = tmp_path / "a.csproj"
        p.write_text("<Project><Product>old</Product></Project>", encoding="utf-8")
        sv.replace_xml_value(p, "Product", "A & B <C>")
        text = p.read_text(encoding="utf-8")
        assert expected_xml_value(text, "Product") == vv.expected_xml_value(text, "Product") == "A & B <C>"

    def test_expected_assignment_quoted_and_numeric(self):
        text = 'versionName = "2.2.0"\nversionCode = 20248\n  versionCode = 77\n'
        assert expected_assignment(text, "versionName") == "2.2.0"
        assert expected_assignment(text, "versionCode") == "20248"  # 首个匹配
        assert expected_assignment(text, "nope") is None


# ---------------------------------------------------------------- PY-267
class TestSyncVersionsReleaseJsonGuard:
    """PY-267（2026-10-02 审计）：release.json 缺失/损坏此前裸栈
    （FileNotFoundError / json.JSONDecodeError traceback）——现包守卫转
    RuntimeError 带文件名（干净 fail-fast 报告）。"""

    @staticmethod
    def _make_tree(tmp_path: Path, release_json: str | None) -> Path:
        """合成最小同步树：合法 properties + 含全部五个目标元素的 csproj。"""
        props = tmp_path / "shared" / "version.properties"
        props.parent.mkdir(parents=True, exist_ok=True)
        props.write_text(
            "VERSION_NAME=2.2.0\nVERSION_CODE=20248\nWINDOWS_PACKAGE_VERSION=2.2.0.0\n"
            "WINDOWS_PACKAGE_IDENTITY=i\nDISPLAY_NAME=d\n",
            encoding="utf-8",
        )
        csproj = tmp_path / "windows" / "src" / "Aegis.Windows.App" / "Aegis.Windows.App.csproj"
        csproj.parent.mkdir(parents=True, exist_ok=True)
        csproj.write_text(
            "<Project><Version>0</Version><AssemblyVersion>0</AssemblyVersion>"
            "<FileVersion>0</FileVersion><PackageId>i</PackageId><Product>d</Product></Project>",
            encoding="utf-8",
        )
        if release_json is not None:
            (tmp_path / "shared" / "release.json").write_text(release_json, encoding="utf-8")
        return tmp_path

    def test_missing_release_json_raises_runtime_error_with_filename(
            self, tmp_path, monkeypatch):
        root = self._make_tree(tmp_path, release_json=None)
        monkeypatch.setattr(sync_versions, "PROPS", root / "shared" / "version.properties")
        monkeypatch.setattr(sync_versions, "ROOT", root)
        with pytest.raises(RuntimeError, match="无法读取.*release\\.json"):
            sync_versions.main()

    def test_corrupt_release_json_raises_runtime_error(
            self, tmp_path, monkeypatch):
        root = self._make_tree(tmp_path, release_json="{ broken")
        monkeypatch.setattr(sync_versions, "PROPS", root / "shared" / "version.properties")
        monkeypatch.setattr(sync_versions, "ROOT", root)
        with pytest.raises(RuntimeError, match="无法读取"):
            sync_versions.main()


# ---------------------------------------------------------------- PY-278
class TestAtomicWriteText:
    """PY-278（2026-10-02 审计）：原子写单源（scripts/atomic_write.py——
    同目录临时文件 + os.replace）——内容往返/无残骸/覆写既有文件/LF 锁定。"""

    def test_roundtrip_content_and_no_temp_leftovers(self, tmp_path):
        target = tmp_path / "out.json"
        atomic_write_text(target, '{"a": 1}\n')
        assert target.read_text(encoding="utf-8") == '{"a": 1}\n'
        # 同目录不留 .tmp 残骸
        assert [p.name for p in tmp_path.iterdir()] == ["out.json"]

    def test_overwrite_existing_file(self, tmp_path):
        target = tmp_path / "out.txt"
        target.write_text("OLD", encoding="utf-8")
        atomic_write_text(target, "NEW")
        assert target.read_text(encoding="utf-8") == "NEW"
        assert [p.name for p in tmp_path.iterdir()] == ["out.txt"]

    def test_lf_locked_on_windows(self, tmp_path):
        # newline 默认 LF——显式 \n 不被 Windows 文本模式翻译为 CRLF
        target = tmp_path / "lines.txt"
        atomic_write_text(target, "a\nb\n")
        assert b"a\nb\n" == target.read_bytes()  # 字节级无 \r

    def test_write_failure_leaves_target_intact_and_no_debris(self, tmp_path, monkeypatch):
        # 写入抛错：目标保持旧内容、无 .tmp 残骸（失败清理路径）
        import atomic_write
        target = tmp_path / "keep.txt"
        target.write_text("OLD", encoding="utf-8")

        def boom(fd, *a, **k):
            import os
            os.close(fd)
            raise OSError("disk full (simulated)")

        monkeypatch.setattr(atomic_write.os, "fdopen", boom)
        with pytest.raises(OSError, match="disk full"):
            atomic_write_text(target, "NEW")
        assert target.read_text(encoding="utf-8") == "OLD"
        assert [p.name for p in tmp_path.iterdir()] == ["keep.txt"]


# ---------------------------------------------------------------- PY-198
class TestVersionCodeDigitCheck:
    def test_sync_versions_rejects_non_numeric_version_code(self, tmp_path, monkeypatch):
        # PY-198：载入后即校验 isdigit——非数字 RuntimeError 汇总报错
        #（此前在 int(values["VERSION_CODE"]) 处炸原始 ValueError 栈）
        props = tmp_path / "version.properties"
        props.write_text(
            "VERSION_NAME=2.2.0\nVERSION_CODE=2b48\nWINDOWS_PACKAGE_VERSION=2.2.0.0\n"
            "WINDOWS_PACKAGE_IDENTITY=i\nDISPLAY_NAME=d\n",
            encoding="utf-8",
        )
        monkeypatch.setattr(sync_versions, "PROPS", props)
        with pytest.raises(RuntimeError, match="must be numeric.*VERSION_CODE"):
            sync_versions.main()

    def test_verify_versions_rejects_non_numeric_version_code(self, tmp_path, monkeypatch, capsys):
        import verify_versions as vv
        (tmp_path / "shared").mkdir(parents=True)
        (tmp_path / "shared" / "version.properties").write_text(
            "VERSION_NAME=2.2.0\nVERSION_CODE=abc\nWINDOWS_PACKAGE_VERSION=2.2.0.0\n"
            "WINDOWS_PACKAGE_IDENTITY=i\nDISPLAY_NAME=d\n",
            encoding="utf-8",
        )
        gradle = tmp_path / "android" / "app"
        gradle.mkdir(parents=True)
        (gradle / "build.gradle.kts").write_text("", encoding="utf-8")
        csproj_dir = tmp_path / "windows" / "src" / "Aegis.Windows.App"
        csproj_dir.mkdir(parents=True)
        (csproj_dir / "Aegis.Windows.App.csproj").write_text("", encoding="utf-8")
        (tmp_path / "shared" / "release.json").write_text("{}", encoding="utf-8")
        monkeypatch.setattr(vv, "ROOT", tmp_path)
        # main() 内 argparse 读 sys.argv——测试注入最小 argv
        monkeypatch.setattr(sys, "argv", ["verify_versions.py"])
        # PY-198：isdigit 校验失败 → 汇总报错返回 1（不再 int() 原始栈）
        assert vv.main() == 1
        assert "must be numeric" in capsys.readouterr().out

    def test_sync_versions_accepts_numeric_version_code(self, tmp_path, monkeypatch):
        # 合法数字 VERSION_CODE 通过新校验（走到后续同步步骤才失败）
        # ROOT 一并指向 tmp——绝不触碰真实仓库的 gradle/csproj/release.json
        props = tmp_path / "version.properties"
        props.write_text(
            "VERSION_NAME=2.2.0\nVERSION_CODE=20248\nWINDOWS_PACKAGE_VERSION=2.2.0.0\n"
            "WINDOWS_PACKAGE_IDENTITY=i\nDISPLAY_NAME=d\n",
            encoding="utf-8",
        )
        monkeypatch.setattr(sync_versions, "PROPS", props)
        monkeypatch.setattr(sync_versions, "ROOT", tmp_path)
        with pytest.raises(OSError):
            sync_versions.main()  # 通过 isdigit 后因 tmp 树缺 csproj 文件失败——预期


# ---------------------------------------------------------------- PY-216
class TestSyncVersionsMainIntegration:
    """PY-216（2026-10-01 审计·P1）集成测试：对真实仓库布局跑 main()。

    gradle 版本已改构建期消费 properties（AD-100 单源接线）后，
    sync_versions 仍按字面量正则替换 versionCode/versionName——对真实
    build.gradle.kts 必抛 RuntimeError（自 09-23 起整脚本不可用）。修复
    删除两行 gradle 写入；本集成测试锁定：main() 在真实 csproj/properties
    输入下全程不抛、csproj/release.json 正确更新、android 目录零依赖
    （不存在也不影响——若有人回加 gradle 写入，此处立即红）。
    """

    def test_main_real_repo_layout_no_gradle_dependency(self, tmp_path, monkeypatch, capsys):
        real = ROOT
        # 真实输入：csproj/release.json 自真实仓库拷贝，PROPS 不重定向
        #（main() 读真实 shared/version.properties 单源值）
        csproj_dst = tmp_path / "windows" / "src" / "Aegis.Windows.App"
        csproj_dst.mkdir(parents=True)
        real_csproj = real / "windows" / "src" / "Aegis.Windows.App" / "Aegis.Windows.App.csproj"
        (csproj_dst / "Aegis.Windows.App.csproj").write_text(
            real_csproj.read_text(encoding="utf-8"), encoding="utf-8")
        shared_dst = tmp_path / "shared"
        shared_dst.mkdir()
        (shared_dst / "release.json").write_text(
            (real / "shared" / "release.json").read_text(encoding="utf-8"),
            encoding="utf-8")
        # PY-216 核心：tmp 树刻意不放 android/——main() 不得再触碰 gradle
        assert not (tmp_path / "android").exists()
        monkeypatch.setattr(sync_versions, "ROOT", tmp_path)
        # 不抛即通过（修复前此处对真实 gradle 必抛 RuntimeError）
        sync_versions.main()
        out = capsys.readouterr().out
        assert "synchronized" in out
        # csproj 已按真实 properties 更新
        props = load_properties(real / "shared" / "version.properties")
        updated = (csproj_dst / "Aegis.Windows.App.csproj").read_text(encoding="utf-8")
        import json as _json

        from verify_versions import expected_xml_value
        assert expected_xml_value(updated, "Version") == props["VERSION_NAME"]
        assert expected_xml_value(updated, "AssemblyVersion") == props["WINDOWS_PACKAGE_VERSION"]
        assert expected_xml_value(updated, "Product") == props["DISPLAY_NAME"]
        # release.json 版本字段同步（versionCode 转 int）
        release_json = _json.loads((shared_dst / "release.json").read_text(encoding="utf-8"))
        assert release_json["version"] == props["VERSION_NAME"]
        assert release_json["versionCode"] == int(props["VERSION_CODE"])
        # 全程未创建/读取 android 路径
        assert not (tmp_path / "android").exists()


# ---------------------------------------------------------------- PY-108
SCRIPT = ROOT / "scripts" / "dedup_release_assets.py"


class TestDedupReleaseAssets:
    def _run(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(SCRIPT), *args],
            capture_output=True, text=True, timeout=60, check=False,
            # PLW1510：被测脚本以退出码为断言对象——不把非零当异常
        )

    def test_second_occurrence_renamed_with_platform_prefix(self, tmp_path):
        win, android = tmp_path / "dist-windows", tmp_path / "dist-android"
        (win / "sub").mkdir(parents=True)
        android.mkdir(parents=True)
        (win / "sub" / "build-metadata.json").write_text("{}", encoding="utf-8")
        (android / "build-metadata.json").write_text("{}", encoding="utf-8")
        proc = self._run(str(win), str(android))
        assert proc.returncode == 0, proc.stderr
        # 首目录为基准不改名；后目录同名加平台前缀
        assert (win / "sub" / "build-metadata.json").exists()
        assert (android / "dist-android-build-metadata.json").exists()
        assert not (android / "build-metadata.json").exists()

    def test_dry_run_reports_without_modifying(self, tmp_path):
        win, android = tmp_path / "win", tmp_path / "android"
        win.mkdir()
        android.mkdir()
        (win / "a.json").write_text("{}", encoding="utf-8")
        (android / "a.json").write_text("{}", encoding="utf-8")
        proc = self._run("--dry-run", str(win), str(android))
        assert proc.returncode == 0
        assert "[dry-run]" in proc.stdout
        # 落盘零变更
        assert (android / "a.json").exists()
        assert not (android / "android-a.json").exists()

    def test_rename_collision_fails_closed(self, tmp_path):
        # 极端情况：前缀改名目标本身已存在 → 报错退出（不静默覆盖）
        win, android = tmp_path / "win", tmp_path / "android"
        win.mkdir()
        android.mkdir()
        (win / "a.json").write_text("{}", encoding="utf-8")
        (android / "a.json").write_text("{}", encoding="utf-8")
        (android / "android-a.json").write_text("{}", encoding="utf-8")
        proc = self._run(str(win), str(android))
        assert proc.returncode == 1
        assert "rename target exists" in proc.stderr

    def test_renamed_artifact_registered_in_seen(self, tmp_path):
        # PY-219（2026-10-01 审计）：改名产物不写 seen——第三方目录原生同名
        # 资产（本就有 <platform>-x）再冲突时不再改名，最终上传仍撞名 404
        #（防的正是该场景）。改名即入账：后续同名继续加前缀。
        win, android, core = tmp_path / "win", tmp_path / "android", tmp_path / "core"
        for d in (win, android, core):
            d.mkdir()
        (win / "x.bin").write_bytes(b"w")          # 基准：win/x.bin
        (android / "x.bin").write_bytes(b"a")      # → android/android-x.bin（改名产物）
        (core / "android-x.bin").write_bytes(b"c")  # 原生同名——必须也被改名
        proc = self._run(str(win), str(android), str(core))
        assert proc.returncode == 0, proc.stderr
        # 三方最终文件名互不冲突
        assert (win / "x.bin").exists()
        assert (android / "android-x.bin").exists()
        assert (core / "core-android-x.bin").exists()
        assert not (core / "android-x.bin").exists()

    def test_not_a_directory_rejected(self, tmp_path):
        proc = self._run(str(tmp_path / "ghost"))
        assert proc.returncode == 1
        assert "not a directory" in proc.stderr

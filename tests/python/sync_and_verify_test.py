# sync_and_verify_test.py —— 版本同步/校验链单测（pytest）。
# 覆盖审计条目：
#   PY-103 load_properties（注释/空行/值含=）
#   PY-104 replace_assignment（count/缩进/引号）
#   PY-105 replace_xml_value（缺失抛错/首匹配）
#   PY-106 expected_xml_value
#   PY-107 expected_assignment
#   PY-108 dedup_release_assets 主逻辑三用例
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from sync_versions import load_properties, replace_assignment, replace_xml_value  # noqa: E402
from verify_versions import expected_assignment, expected_xml_value  # noqa: E402


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


# ---------------------------------------------------------------- PY-106/107
class TestExpectedValueExtractors:
    def test_expected_xml_value(self):
        text = "<Project><Version>  2.2.0-beta.49 </Version></Project>"
        assert expected_xml_value(text, "Version") == "2.2.0-beta.49"
        assert expected_xml_value("<Project></Project>", "Version") is None

    def test_expected_xml_value_regex_metachars_in_element(self):
        # 元素名经 re.escape——含正则元字符的元素名不得崩
        assert expected_xml_value("<a.b>1</a.b>", "a.b") == "1"

    def test_expected_assignment_quoted_and_numeric(self):
        text = 'versionName = "2.2.0"\nversionCode = 20248\n  versionCode = 77\n'
        assert expected_assignment(text, "versionName") == "2.2.0"
        assert expected_assignment(text, "versionCode") == "20248"  # 首个匹配
        assert expected_assignment(text, "nope") is None


# ---------------------------------------------------------------- PY-108
SCRIPT = ROOT / "scripts" / "dedup_release_assets.py"


class TestDedupReleaseAssets:
    def _run(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(SCRIPT), *args],
            capture_output=True, text=True, timeout=60,
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

    def test_not_a_directory_rejected(self, tmp_path):
        proc = self._run(str(tmp_path / "ghost"))
        assert proc.returncode == 1
        assert "not a directory" in proc.stderr

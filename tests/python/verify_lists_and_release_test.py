# verify_lists_and_release_test.py —— 资源/清单校验器单测（pytest）。
# 覆盖审计条目：
#   PY-117 verify_xaml_resources.collect_keys
#   PY-118 缺失键定位（行号）
#   PY-119 wallpapers_from_asset_scheme
#   PY-120 wallpapers_from_start_html
#   PY-121 wallpapers_from_kotlin
#   PY-122 引擎表解析三端
#   PY-123 validate_release.check_lock_file（抽函数后单测）
#   PY-124 validate_release.check_required_cs_files
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import verify_cross_end_lists as vcel  # noqa: E402
import verify_xaml_resources as vxr  # noqa: E402
from validate_release import check_lock_file, check_required_cs_files  # noqa: E402


# ---------------------------------------------------------------- PY-117/118
class TestXamlResources:
    def _make_tree(self, tmp_path: Path) -> None:
        (tmp_path / "x").mkdir()
        (tmp_path / "x" / "res.xaml").write_text(
            '<ResourceDictionary>\n  <SolidColorBrush x:Key="BrushA"/>\n'
            '  <SolidColorBrush x:Key="BrushB"/>\n</ResourceDictionary>\n',
            encoding="utf-8",
        )
        (tmp_path / "x" / "code.xaml.cs").write_text(
            'var b = FindResource("BrushA");\n'
            'var c = TryFindResource("BrushB");\n'
            'var d = Resources["Ghost"];\n',
            encoding="utf-8",
        )

    def test_collect_keys_scans_all_xaml(self, tmp_path, monkeypatch):
        self._make_tree(tmp_path)
        monkeypatch.setattr(vxr, "SRC", tmp_path / "x")
        assert vxr.collect_keys() == {"BrushA", "BrushB"}

    def test_missing_key_located_with_line_and_kind(self, tmp_path, monkeypatch, capsys):
        # PY-118：缺失键报告必须含 文件:行号 与引用类别（FindResource/索引器）
        self._make_tree(tmp_path)
        monkeypatch.setattr(vxr, "SRC", tmp_path / "x")
        rc = vxr.main()
        assert rc == 1
        out = capsys.readouterr().out
        assert "Ghost" in out
        assert "code.xaml.cs:3" in out, "行号必须定位到引用行"
        assert "索引器" in out, "Resources[] 索引器引用须标注类别（PY-036）"

    def test_all_keys_defined_passes(self, tmp_path, monkeypatch):
        (tmp_path / "x").mkdir()
        (tmp_path / "x" / "res.xaml").write_text('<ResourceDictionary><Brush x:Key="Only"/></ResourceDictionary>', encoding="utf-8")
        (tmp_path / "x" / "code.xaml.cs").write_text('var a = FindResource("Only");\n', encoding="utf-8")
        monkeypatch.setattr(vxr, "SRC", tmp_path / "x")
        assert vxr.main() == 0


# ---------------------------------------------------------------- PY-119..122
@pytest.fixture()
def vcel_clean(monkeypatch):
    """每个用例独立 failures 列表 + 合成 _read。"""
    monkeypatch.setattr(vcel, "failures", [])
    return monkeypatch


class TestWallpaperExtractors:
    def test_asset_scheme_multi_suffix(self, vcel_clean):
        # PY-119：jpg/jpeg/png/webp 多后缀（PY-035 扩展锁定）
        vcel_clean.setattr(
            vcel, "_read",
            lambda rel: 'WALLPAPERS = ("a.jpg", "b.jpeg", "c.png", "d.webp", "skip.txt")')
        assert vcel.wallpapers_from_asset_scheme() == {"a.jpg", "b.jpeg", "c.png", "d.webp"}

    def test_asset_scheme_block_missing_fails_closed(self, vcel_clean):
        vcel_clean.setattr(vcel, "_read", lambda rel: "no wallpaper here")
        assert vcel.wallpapers_from_asset_scheme() == set()
        assert vcel.failures and "asset_scheme.py" in vcel.failures[0]

    def test_start_html_name_list(self, vcel_clean):
        # PY-120：start.main.js 的 name:'...' 锚点
        vcel_clean.setattr(
            vcel, "_read",
            lambda rel: "var WALLPAPERS = [\n{name:'a.jpg',url:'u'},\n{name:'b.png',url:'u'},\n];")
        assert vcel.wallpapers_from_start_html() == {"a.jpg", "b.png"}

    def test_kotlin_setof(self, vcel_clean):
        # PY-121：Kotlin setOf 白名单
        vcel_clean.setattr(
            vcel, "_read",
            lambda rel: 'val WALLPAPERS = setOf("a.jpg", "b.png")')
        assert vcel.wallpapers_from_kotlin() == {"a.jpg", "b.png"}


class TestEngineExtractors:
    def test_url_utils_python_dict(self, vcel_clean):
        vcel_clean.setattr(
            vcel, "_read",
            lambda rel: 'SEARCH_ENGINES = {\n    "baidu": "https://baidu.com",\n    "bing": "https://bing.com",\n}')
        assert vcel.engines_from_url_utils() == {"baidu", "bing"}

    def test_kotlin_engine_urls_mapof(self, vcel_clean):
        vcel_clean.setattr(
            vcel, "_read",
            lambda rel: 'val ENGINE_URLS = mapOf(\n    "baidu" to "https://b",\n    "bing" to "https://bi")')
        assert vcel.engines_from_kotlin() == {"baidu", "bing"}

    def test_csharp_dictionary_with_extension_gate(self, vcel_clean):
        # PY-122：C# 索引器条目提取；扩展白名单语义单测
        vcel_clean.setattr(
            vcel, "_read",
            lambda rel: 'EngineUrls = new Dictionary<string, string>\n{\n    ["baidu"] = "https://b",\n    ["duckduckgo"] = "https://d"\n};')
        assert vcel.engines_from_csharp() == {"baidu", "duckduckgo"}
        # duckduckgo 在扩展白名单——不报；so360 不在 C# 表——报缺失
        core = {"baidu", "bing"}
        cs = vcel.engines_from_csharp()
        assert not (cs - core) - vcel.CS_ENGINE_EXTENSIONS
        ghosts = vcel.CS_ENGINE_EXTENSIONS - cs
        assert ghosts == {"so360", "brave", "startpage", "ecosia", "yandex"}


# ---------------------------------------------------------------- PY-123/124
class TestValidateReleaseGates:
    def test_lock_file_missing(self, tmp_path):
        problems = check_lock_file(tmp_path)
        assert len(problems) == 1 and "缺 requirements-lock.txt" in problems[0]

    def test_lock_file_without_hash(self, tmp_path):
        lock = tmp_path / "requirements-lock.txt"
        lock.write_text("pyyaml==6.0.2  # no hash\n", encoding="utf-8")
        problems = check_lock_file(tmp_path)
        assert len(problems) == 1 and "无 hash" in problems[0]

    def test_lock_file_with_hash_passes(self, tmp_path):
        lock = tmp_path / "requirements-lock.txt"
        lock.write_text("pyyaml==6.0.2 \\\n    --hash=sha256:abc\n", encoding="utf-8")
        assert check_lock_file(tmp_path) == []

    def test_csproj_missing(self, tmp_path):
        problems = check_required_cs_files(tmp_path / "ghost.csproj")
        assert len(problems) == 1 and "缺正典 C# 工程" in problems[0]

    def test_missing_key_file_listed_one_by_one(self, tmp_path):
        csproj = tmp_path / "Aegis.Windows.App.csproj"
        csproj.write_text("<Project/>", encoding="utf-8")
        problems = check_required_cs_files(csproj)
        # 5 个关键文件全缺——逐条列出（含子目录路径）
        assert len(problems) == 5
        assert any("Chrome/MainWindow.xaml.cs" in p for p in problems)
        assert any("Broker/BrowserPolicyBroker.cs" in p for p in problems)

    def test_all_present_passes(self, tmp_path):
        csproj = tmp_path / "Aegis.Windows.App.csproj"
        csproj.write_text("<Project/>", encoding="utf-8")
        for rel in ("App.xaml.cs", "Chrome/MainWindow.xaml", "Chrome/MainWindow.xaml.cs",
                    "Broker/BrowserPolicyBroker.cs", "WebView/HostWebView.cs"):
            f = tmp_path / rel
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text("//", encoding="utf-8")
        assert check_required_cs_files(csproj) == []

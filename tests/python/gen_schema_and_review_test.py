# gen_schema_and_review_test.py —— jsapi schema 生成器 + 评审包生成器单测（pytest）。
# 覆盖审计条目：
#   PY-109 _doc_first_line
#   PY-110 build_schema
#   PY-111 mixin 提取回归（PY-005 锁定）
#   PY-112 _match_excluded 表驱动
#   PY-113 collect_sources
#   PY-114 git_commit_and_head 降级
#   PY-115 stamp_readme 两用例
#   PY-116 check_reviewed 三类报告
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import build_review_package as brp  # noqa: E402
from gen_jsapi_schema import _doc_first_line, build_schema  # noqa: E402


# ---------------------------------------------------------------- PY-109
class TestDocFirstLine:
    def test_none_and_empty(self):
        assert _doc_first_line(None) == ""
        assert _doc_first_line("") == ""

    def test_first_line_extracted_and_stripped(self):
        assert _doc_first_line("  用途说明。\n\n细节第二段\n") == "用途说明。"
        assert _doc_first_line("   \n 第二行才是内容\n") == "第二行才是内容"


# ---------------------------------------------------------------- PY-110/111
API_SRC = '''
_JS_EXPOSED = frozenset({"ping", "echo", "bridge_call"})

class TabMixin:
    def ping(self, tab_id):
        """标签心跳。"""
        return tab_id

class Api(TabMixin, BridgeMixin):
    def echo(self, msg="hi"):
        """回声测试。"""
        return msg

    def _private_helper(self):
        return 1
'''

MIXIN_SRC = '''
class BridgeMixin:
    def bridge_call(self, name):
        """跨桥调用。"""
        return name
'''


class TestBuildSchema:
    def test_whitelist_and_required_flags(self):
        schema = build_schema(API_SRC)
        # 白名单来自 _JS_EXPOSED 全量收集（未提供 mixin 源时 bridge_call 无定义体——不在 methods）
        assert schema["properties"]["js_exposed_methods"] == ["bridge_call", "echo", "ping"]
        methods = schema["properties"]["methods"]
        assert set(methods) == {"echo", "ping"}
        # echo(msg="hi")：带默认值 → required=False（PY-040 语义）
        assert methods["echo"]["params"] == [{"name": "msg", "required": False}]
        assert methods["echo"]["n_required_params"] == 0
        # 私有方法不暴露
        assert "_private_helper" not in methods

    def test_doc_first_line_in_description(self):
        methods = build_schema(API_SRC)["properties"]["methods"]
        assert methods["echo"]["description"] == "回声测试。"

    def test_mixin_methods_merged_with_provenance(self):
        # PY-111 / PY-005 回归：mixin 方法必须入 schema 且 defined_in 正确溯源
        schema = build_schema(API_SRC, {"app/bridge/tab.py": MIXIN_SRC})
        methods = schema["properties"]["methods"]
        assert "bridge_call" in methods
        assert methods["bridge_call"]["defined_in"] == "BridgeMixin"
        assert methods["ping"]["defined_in"] == "TabMixin"
        assert methods["echo"]["defined_in"] == "Api"

    def test_derived_class_shadows_base(self):
        # 同名方法以更派生类（Api 本体）为准
        override_src = '''
class Base:
    def op(self):
        """base doc"""
        return 1

class Api(Base):
    def op(self):
        """api doc"""
        return 2
'''
        methods = build_schema(override_src)["properties"]["methods"]
        assert methods["op"]["description"] == "api doc"
        assert methods["op"]["defined_in"] == "Api"


# ---------------------------------------------------------------- PY-112
class TestMatchExcluded:
    CASES = [
        (Path("src/bin/obj/x.cs"), True, "父目录命中 EXCLUDE_DIRS"),
        (Path("src/__pycache__/m.pyc"), True, "缓存目录"),
        (Path("app/node_modules/lib.js"), True, "node_modules"),
        (Path("docs/notes.pyc"), True, "后缀命中"),
        (Path("assets/fonts-bundle.zip"), True, "EXCLUDE_NAMES 命中"),
        (Path("shared/shell/start.html"), False, "正常源码保留"),
        (Path("README.md"), False, "文档保留"),
        (Path("core/src/lib.rs"), False, "Rust 源码保留"),
    ]

    def test_table_driven(self):
        # PY-112：8 用例表驱动——排除规则回归锁定
        for rel, expected, reason in self.CASES:
            assert brp._match_excluded(rel) is expected, f"{rel} ({reason})"


# ---------------------------------------------------------------- PY-113
class TestCollectSources:
    def test_deterministic_and_excludes_build_artifacts(self):
        # PY-113：在真实仓库根上运行——结果确定性（排序去重）+ 无构建产物
        sources = brp.collect_sources()
        keys = [p.as_posix() for p in sources]
        assert keys == sorted(keys), "输出必须按 posix 路径排序（确定性）"
        assert len(keys) == len(set(keys)), "输出必须去重"
        for key in keys:
            assert not key.endswith(".pyc")
            assert "__pycache__" not in key
            assert "node_modules" not in key
        # 关键单源资产必须在清单内
        assert "shared/shell/start.html" in keys
        assert "README.md" in keys


# ---------------------------------------------------------------- PY-114
class TestGitCommitAndHead:
    def test_real_repo_returns_sha_and_subject(self):
        short, subject = brp.git_commit_and_head()
        assert short != "unknown" and len(short) >= 7
        assert subject and subject != "unknown"

    def test_git_failure_degrades_to_placeholder(self, monkeypatch):
        # PY-114：非 git 环境（如发布包解压后）降级为占位，不抛异常
        import subprocess

        def boom(*a, **k):
            raise subprocess.CalledProcessError(128, "git")

        monkeypatch.setattr(brp.subprocess, "run", boom)
        assert brp.git_commit_and_head() == ("unknown", "unknown")


# ---------------------------------------------------------------- PY-115
class TestStampReadme:
    def test_existing_readme_header_replaced_body_preserved(self, tmp_path):
        readme = tmp_path / "README-专家评审.txt"
        readme.write_text(
            "# 生成时间: OLD\n# 版本: 0.0.1\n# 提交: deadbeef (old)\n# 源码文件数: 1\n"
            "\n正文段落——手工维护内容\n",
            encoding="utf-8",
        )
        brp.stamp_readme(tmp_path, "2.2.0", "abc1234", "new subject", "NOW", 99)
        text = readme.read_text(encoding="utf-8")
        assert "# 生成时间: NOW" in text and "OLD" not in text
        assert "# 版本: 2.2.0" in text
        assert "# 提交: abc1234 (new subject)" in text
        assert "# 源码文件数: 99" in text
        assert "正文段落——手工维护内容" in text, "正文必须原样保留"

    def test_missing_readme_generates_template(self, tmp_path):
        brp.stamp_readme(tmp_path, "2.2.0", "abc1234", "subj", "NOW", 5)
        text = (tmp_path / "README-专家评审.txt").read_text(encoding="utf-8")
        assert "# 版本: 2.2.0" in text and "# 源码文件数: 5" in text


# ---------------------------------------------------------------- PY-116
@pytest.fixture()
def tiny_source(monkeypatch):
    """把 collect_sources 收窄为单文件——check_reviewed 测试免全仓复制。"""
    monkeypatch.setattr(brp, "collect_sources", lambda: [Path("shared/release.json")])


class TestCheckReviewed:
    def test_missing_manifest_reported(self, tmp_path, tiny_source):
        ok, problems = brp.check_reviewed(tmp_path)
        assert not ok
        assert any("缺少 manifest.json" in p for p in problems)

    def test_content_drift_reported(self, tmp_path, tiny_source):
        pkg = tmp_path / "pkg"
        pkg.mkdir()
        brp.build(pkg, apply_edit=False)
        committed = json.loads((pkg / "manifest.json").read_text(encoding="utf-8"))
        committed["files"][0]["sha256"] = "0" * 64  # 模拟内容漂移
        (pkg / "manifest.json").write_text(
            json.dumps(committed, ensure_ascii=False, indent=2), encoding="utf-8")
        ok, problems = brp.check_reviewed(pkg)
        assert not ok
        assert any("内容漂移" in p for p in problems)

    def test_committed_extra_file_reported(self, tmp_path, tiny_source):
        pkg = tmp_path / "pkg"
        pkg.mkdir()
        brp.build(pkg, apply_edit=False)
        committed = json.loads((pkg / "manifest.json").read_text(encoding="utf-8"))
        committed["files"].append(
            {"path": "ghost/removed-from-source.txt", "sha256": "a" * 64, "bytes": 1})
        (pkg / "manifest.json").write_text(
            json.dumps(committed, ensure_ascii=False, indent=2), encoding="utf-8")
        ok, problems = brp.check_reviewed(pkg)
        assert not ok
        assert any("已提交但源码不存在" in p for p in problems)
        assert any("文件数不一致" in p for p in problems)

    def test_in_sync_package_passes(self, tmp_path, tiny_source):
        pkg = tmp_path / "pkg"
        pkg.mkdir()
        brp.build(pkg, apply_edit=False)
        # apply_edit=False 时 build 仍写 manifest.json 但不写 README 戳记——
        # check 只比对 manifest 内文件集，需剔除 README 期望差（KEEP_FILES 语义）
        ok, problems = brp.check_reviewed(pkg)
        assert ok, problems


# 脚本可独立运行（无 pytest 环境时的最低验证）
if __name__ == "__main__":
    rc = subprocess.run([sys.executable, "-m", "pytest", __file__, "-q"]).returncode
    sys.exit(rc)

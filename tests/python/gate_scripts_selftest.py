# gate_scripts_selftest.py —— 两个新门禁脚本的自测（SP-258 覆盖率报告驱动补测）。
# 背景：2026-10-03 覆盖率报告（contracts job --cov 实测）显示 SP-255/SP-256
# 两个门禁自身 0% 覆盖——门禁的正确性（ratchet 判定/死链判定）零回归锚。
# 本文件补齐：check_file_sizes.py（行数红线）与 check_markdown_links.py
# （Markdown 死链）的核心分支，tmp git 仓 + 模块常量 monkeypatch 驱动。
from __future__ import annotations

import json

import check_file_sizes as cfs
import check_markdown_links as cml
import pytest


@pytest.fixture()
def tmp_repo(tmp_path, monkeypatch):
    """临时 git 仓——两脚本的扫描面均由 git ls-files 收口，monkeypatch ROOT/
    BASELINE_PATH 后即可在隔离树内驱动全流程。"""
    import subprocess

    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    monkeypatch.setattr(cfs, "ROOT", repo)
    monkeypatch.setattr(cfs, "BASELINE_PATH", repo / "file_size_baseline.json")
    monkeypatch.setattr(cml, "ROOT", repo)
    return repo


def _add(repo, rel, text=""):
    path = repo / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode("utf-8"))
    import subprocess

    subprocess.run(["git", "add", "-A", "."], cwd=repo, check=True,
                   capture_output=True)
    return path


# ---------------- check_file_sizes（SP-255 行数红线） ----------------


def test_count_lines_matches_wc_l(tmp_path):
    assert cfs.count_lines(_make(tmp_path, b"a\nb\n")) == 2
    assert cfs.count_lines(_make(tmp_path, b"a\r\nb\r\n")) == 2
    assert cfs.count_lines(_make(tmp_path, b"a\nb")) == 1  # 无尾换行：wc -l 同口径


def _make(tmp_path, content):
    p = tmp_path / "f.txt"
    p.write_bytes(content)
    return p


def test_baseline_missing_is_env_error(tmp_repo):
    with pytest.raises(SystemExit) as exc:
        cfs.run_check()
    assert exc.value.code == 2


def test_baseline_corrupted_is_env_error(tmp_repo):
    cfs.BASELINE_PATH.write_text("{not json", encoding="utf-8")
    with pytest.raises(SystemExit) as exc:
        cfs.run_check()
    assert exc.value.code == 2


def test_new_file_over_limit_fails_under_limit_passes(tmp_repo):
    _add(tmp_repo, "src/small.py", "\n" * 300)
    assert cfs.run_check() == 0
    _add(tmp_repo, "src/big.py", "\n" * 301)
    result = cfs.run_check()
    assert result == 1


def test_baseline_ratchet_blocks_growth_allows_shrink(tmp_repo):
    _add(tmp_repo, "src/legacy.py", "\n" * 305)
    cfs.BASELINE_PATH.write_text(
        json.dumps({"files": {"src/legacy.py": 305}}), encoding="utf-8")
    _add(tmp_repo, "src/legacy.py", "\n" * 400)
    assert cfs.run_check() == 1  # 基线内增长 → 红
    _add(tmp_repo, "src/legacy.py", "\n" * 250)
    assert cfs.run_check() == 0  # 基线内缩减 → 绿（ratchet 单向）


def test_generated_prefix_excluded_from_face(tmp_repo):
    _add(tmp_repo, "windows/src/Aegis.Windows.App/Contracts/Generated/g.cs", "\n" * 500)
    _add(tmp_repo, "android/contracts/src/main/kotlin/com/aegis/contracts/generated/g.kt",
         "\n" * 500)
    assert cfs.run_check() == 0  # 生成物目录不入红线面


def test_write_baseline_snapshots_then_check_passes(tmp_repo):
    _add(tmp_repo, "src/big.py", "\n" * 350)
    _add(tmp_repo, "src/small.py", "\n" * 50)
    assert cfs.write_baseline() == 0
    data = json.loads(cfs.BASELINE_PATH.read_text(encoding="utf-8"))
    assert data["files"] == {"src/big.py": 350}  # 只登记超限文件
    assert cfs.run_check() == 0  # 快照即基线——同树复查绿


# ---------------- check_markdown_links（SP-256 死链门禁） ----------------


def test_is_skippable_branches():
    assert cml.is_skippable("")
    assert cml.is_skippable("#anchor")
    assert cml.is_skippable("//cdn.example/x")
    assert cml.is_skippable("https://example.com/a.md")
    assert cml.is_skippable("mailto:a@b.c")
    assert not cml.is_skippable("a.md")
    assert not cml.is_skippable("./x/y.md")


def test_extract_target_strips_angle_and_title():
    assert cml.extract_target("  a.md  ") == "a.md"
    assert cml.extract_target("<a.md>") == "a.md"
    # 尖括号含空格路径 + "标题" 后缀（markdown 合法形态——原实现误解析 '<a'）
    assert cml.extract_target('<a b.md> "标题"') == "a b.md"


def test_resolve_target_relative_root_anchor_percent():
    md = tmp_md_path()
    assert cml.resolve_target(md, "x/y.md") == (md.parent / "x/y.md").resolve()
    assert cml.resolve_target(md, "/docs/a.md") == (cml.ROOT / "docs/a.md").resolve()
    assert cml.resolve_target(md, "a.md#sec") == (md.parent / "a.md").resolve()
    assert cml.resolve_target(md, "my%20file.md") == (md.parent / "my file.md").resolve()


def tmp_md_path():
    return cml.ROOT / "docs" / "readme.md"


def test_check_file_reports_dead_links_skips_fences(tmp_repo):
    md = _add(
        tmp_repo,
        "docs/readme.md",
        "\n".join([
            "[ok](other.md)",
            "[dead](ghost.md)",
            "[anchor](#sec)",
            "[external](https://example.com/x)",
            "```",
            "[in fence](also-dead.md)",
            "```",
            "[ref]: missing-target.md",
        ]),
    )
    dead = cml.check_file(md)
    assert any("readme.md:2" in item for item in dead), dead
    assert any("missing-target.md" in item for item in dead), dead
    assert len(dead) == 2, dead  # ok 行/锚点/外链/围栏内均不入面


def test_check_file_percent_decoded_target_exists(tmp_repo):
    _add(tmp_repo, "docs/my file.md", "x")
    md = _add(tmp_repo, "docs/index.md", "[link](my%20file.md)")
    assert cml.check_file(md) == []


def test_main_fails_closed_on_dead_link(tmp_repo):
    _add(tmp_repo, "README.md", "[dead](ghost.md)")
    assert cml.main([]) == 1

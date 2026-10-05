# gate_hollowness_test.py —— 第八轮 B5（R8-PY-02 / R8-PY-08 / R8-PY-11）：
# 三道门禁「掏空面」的可失败自证。
#
# 共同失效模式：门禁判的是「东西在不在」，而不是「东西还剩多少」——
#   * verify_vectors 只数文件数（MIN_FILES），把某个 vectors 数组清空即零判定；
#   * check_markdown_links 把「文件系统上存在」当「可达」，且扫到 0 个 .md 也 exit 0；
#   * validate_release 的锁门禁只断「文本里出现过一次 --hash=」。
# 本文件不验证「现在绿」，只验证「掏空它会红」——这是本仓对每个新门禁的固定要求
# （R7-TOOL-04/R7-SH-03 同一口径），否则门禁自身就是下一个假绿源。
#
# 导入面：validate_release.py 在仓库根，ruff（src=.）判 first-party，须与
# scripts/ 下两个门禁（判 third-party）分段——I001 实测口径。
from __future__ import annotations

import json

import check_markdown_links as cml
import verify_vectors as vv

import validate_release as vr


# ---------------------------------------------------------------- verify_vectors
def _synthetic_vectors_tree(tmp_path, vectors_payload):
    root = tmp_path
    schemas = root / "contracts" / "schemas"
    vectors = root / "contracts" / "vectors"
    schemas.mkdir(parents=True, exist_ok=True)
    vectors.mkdir(parents=True, exist_ok=True)
    (schemas / "dummy.json").write_text(json.dumps({"$schema": "https://json-schema.org/draft/2020-12/schema"}), encoding="utf-8")
    (vectors / "case.json").write_text(json.dumps(vectors_payload), encoding="utf-8")
    return root


def test_empty_vectors_array_is_not_silently_green(tmp_path, monkeypatch, capsys):
    root = _synthetic_vectors_tree(tmp_path, {"description": "x", "vectors": []})
    monkeypatch.setattr(vv, "ROOT", root)
    monkeypatch.setattr(vv, "MIN_FILES", {"schemas": 1, "vectors": 1})
    monkeypatch.setattr(vv, "MIN_VECTOR_ENTRIES", 1)
    assert vv.main() == 1, "vectors 数组被清空后门禁仍判通过——掏空面未闭合"
    assert "vectors 数组为空" in capsys.readouterr().out


def test_total_entry_floor_catches_content_slimming(tmp_path, monkeypatch, capsys):
    root = _synthetic_vectors_tree(tmp_path, {"description": "x", "vectors": [{}, {}]})
    monkeypatch.setattr(vv, "ROOT", root)
    monkeypatch.setattr(vv, "MIN_FILES", {"schemas": 1, "vectors": 1})
    monkeypatch.setattr(vv, "MIN_VECTOR_ENTRIES", 5)
    monkeypatch.setattr(vv, "OVERSIZE_ANCHOR", "no-such-anchor")
    assert vv.main() == 1
    assert "低于下界" in capsys.readouterr().out


def test_real_tree_meets_declared_entry_floor():
    # 下界不能是拍脑袋的数字：与当前真实面一致（缩减须显式核减并说明）
    total = 0
    for path in sorted((vv.ROOT / "contracts" / "vectors").glob("*.json")):
        total += len(json.loads(path.read_text(encoding="utf-8")).get("vectors", []))
    assert total == vv.MIN_VECTOR_ENTRIES, f"真实向量条目 {total} 与下界 {vv.MIN_VECTOR_ENTRIES} 不同步"


# ------------------------------------------------------------- check_markdown_links
def test_link_pointing_outside_repo_is_flagged(tmp_path, monkeypatch):
    monkeypatch.setattr(cml, "ROOT", tmp_path)
    md = tmp_path / "docs" / "a.md"
    md.parent.mkdir(parents=True, exist_ok=True)
    outside = cml.target_outside_repo(md, "/../../Windows/win.ini")
    inside = cml.target_outside_repo(md, "/docs/a.md")
    assert outside is True, "仓外目标被判在仓库内——门禁会按构建机文件系统放行死链"
    assert inside is False


def test_empty_markdown_surface_is_env_error(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(cml, "ROOT", tmp_path)
    monkeypatch.setattr(cml, "list_markdown_files", lambda: [])
    assert cml.main([]) == 2, "扫到 0 个 .md 仍判通过（R7-TOOL-04 同族）"
    assert "扫描面为空" in capsys.readouterr().err


# ------------------------------------------------------------------ validate_release
LOCK_WITH_ONE_HASH = """\
# comment
ruff==0.16.9 \\
    --hash=sha256:aaaa
bandit==1.9.4 \\
    --hash=sha256:bbbb
pytest==9.1.1
"""

LOCK_ALL_HASHED = """\
ruff==0.16.9 \\
    --hash=sha256:aaaa
bandit==1.9.4 \\
    --hash=sha256:bbbb
"""


def test_unhashed_pin_is_detected(tmp_path):
    source = tmp_path / "requirements-ci.in"
    source.write_text("ruff==0.16.9\nbandit==1.9.4\n", encoding="utf-8")
    problems = vr.check_lock_structure(LOCK_WITH_ONE_HASH, source)
    assert any("缺 hash" in p for p in problems), f"未带 hash 的钉版条目未被发现：{problems}"


def test_source_pin_missing_from_lock_is_detected(tmp_path):
    source = tmp_path / "requirements-ci.in"
    source.write_text("cryptography==50.0.1\n", encoding="utf-8")
    problems = vr.check_lock_structure(LOCK_ALL_HASHED, source)
    assert any("未逐字出现在锁内" in p for p in problems), f".in 与锁不一致未被发现：{problems}"


def test_consistent_lock_yields_no_problems(tmp_path):
    source = tmp_path / "requirements-ci.in"
    source.write_text("ruff==0.16.9\nbandit==1.9.4\n# 注释忽略\n", encoding="utf-8")
    assert vr.check_lock_structure(LOCK_ALL_HASHED, source) == []


def test_real_lock_passes_the_structural_check():
    root = vr.Path(__file__).resolve().parents[2]
    text = (root / "requirements-ci.txt").read_text(encoding="utf-8")
    problems = vr.check_lock_structure(text, root / "requirements-ci.in")
    assert problems == [], f"真实锁未通过结构判定：{problems}"

# py312_compat_test.py —— 本地/CI 解释器版本差异门禁的回归锚（第七轮）。
#
# 触发事实：PR #82 的 CI 首跑在 `contract-source-of-truth` job 直接红——
# `TypeError: Path.read_text() got an unexpected keyword argument 'newline'`。
# 本地 Python 3.14 全绿，workflow 钉的是 3.12，而 `Path.read_text` 的 newline
# 关键字是 3.13 才加的。这类缺陷的共性是：**只在更高版本成立的写法在活跃树里
# 静默存活，直到某次 CI 才炸**——本门禁按 CI 钉版扫面，本文件钉门禁自己会红。
from __future__ import annotations

import pathlib
import re

import active_tree_gates as atg
import pytest

REPO = pathlib.Path(__file__).resolve().parents[2]


def _write(tmp_path: pathlib.Path, name: str, body: str) -> pathlib.Path:
    path = tmp_path / name
    path.write_text(body, encoding="utf-8")
    return path


def test_active_tree_is_compatible_with_ci_pinned_python():
    files = atg._python_files(atg.RUFF_TARGETS)
    assert len(files) > 40, f"扫描面塌缩到 {len(files)} 个文件——门禁已空心化"
    assert atg.compat_violations(files) == []


def test_planted_313_only_api_is_detected(tmp_path):
    path = _write(tmp_path, "bad.py", 'x = p.re' + 'ad_text(encoding="utf-8", newline="")\n')
    problems = atg.compat_violations([path])
    assert any("需 3.13+" in p for p in problems), problems


def test_comment_mention_is_not_flagged(tmp_path):
    # 说明性注释里提到该 API 不算违规（门禁扫的是代码列）
    path = _write(tmp_path, "ok.py", "# 别用 p.re" + 'ad_text(newline="")，CI 钉 3.12\n')
    assert atg.compat_violations([path]) == []


def test_empty_scan_surface_is_not_a_pass(monkeypatch, tmp_path, capsys):
    """扫描面为空 ⇒ 非零退出——否则"没东西可查"会被读成"查过了且干净"。"""
    empty = tmp_path / "nothing"
    empty.mkdir()
    monkeypatch.setattr(atg, "ROOT", tmp_path)
    monkeypatch.setattr(atg, "RUFF_TARGETS", ["nothing"])
    assert atg.run_compat() == 2
    assert "扫描面为空" in capsys.readouterr().out or "空面" in capsys.readouterr().out


def test_ci_pin_and_gate_target_agree():
    """门禁的钉版口径必须与 workflow 实际 python-version 一致——否则门禁自己漂移。"""
    versions = set()
    for workflow in sorted((REPO / ".github" / "workflows").glob("*.yml")):
        for line in workflow.read_text(encoding="utf-8").splitlines():
            if "python-version" in line:
                versions.add(line.split("python-version:")[-1].strip().strip("'\""))
    assert versions, "workflow 里找不到 python-version——钉版声明已消失"
    assert versions == {"3.12"}, f"CI 钉版出现分叉：{sorted(versions)}"


def test_compat_gate_is_wired_into_the_required_contracts_job():
    workflow = (REPO / ".github" / "workflows" / "contracts.yml").read_text(encoding="utf-8")
    assert "active_tree_gates.py compat" in workflow


# 每条规则的违规样例（样例用相邻字面量拆分书写——否则本文件会被自家门禁扫出）
_SAMPLES = {
    "read_text_newline": 'p.re' + 'ad_text(encoding="utf-8", newline="")',
    "walk_recurse_on_error": 'root.w' + 'alk(topdown=True, recurse_on_error=False)',
    "path_fromuri": 'pathlib.Path.from' + 'uri("file:///tmp/x")',
}


@pytest.mark.parametrize("rule_id", sorted(_SAMPLES))
def test_every_rule_has_a_matching_sample(rule_id):
    """每条规则都得有样例且样例真的命中——防「规则写着玩」与「加了规则没人测」。"""
    matches = [pattern for rid, pattern, _ in atg.HIGH_VERSION_APIS if rid == rule_id]
    assert len(matches) == 1, f"规则 {rule_id} 应恰好对应一条，实际 {len(matches)}"
    assert re.search(matches[0], _SAMPLES[rule_id]), matches[0]


def test_rule_count_matches_sample_count():
    assert len(atg.HIGH_VERSION_APIS) == len(_SAMPLES), (
        "规则表与自检样例面失配——有条款永远测不到")


def test_ci_pinned_apis_are_not_false_positives():
    """3.12 就成立的写法不得被扫出来（否则门禁天天红，最终被人删掉）。"""
    allowed = [
        'p.write_text("x", encoding="utf-8", newline="")',   # write_text 的 newline 早于 3.10
        'with open("f", encoding="utf-8", newline="") as h: h.read()',
        "root.walk(topdown=True)",                            # Path.walk 本身 3.12 可用
    ]
    for body in allowed:
        assert not any(re.search(pattern, body) for _, pattern, _ in atg.HIGH_VERSION_APIS), body

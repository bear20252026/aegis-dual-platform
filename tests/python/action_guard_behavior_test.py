# action_guard_behavior_test.py —— R7-SH-03 / R7-SH-04（第七轮 2026-10-04）。
#
# 起因：`.github/actions/prepare-geogebra/action.yml` 的 zip-slip 防护由
# `tests/ui-regression/start_page.test.mjs` 以**文本邻接**锚定
#（`/zip-slip[\s\S]{0,220}sys\.exit\(1\)/`）。变异实测：把 containment 结果整行
# 改成 `bad = []`，token 与 `sys.exit(1)` 都还在原位，门禁仍全绿——锚的是字面，
# 不是行为（R6-04/R6-05 同一失效类）。本文件改为**行为级**回归：从 action.yml
# 抽出内嵌 Python 块，在临时目录里对真实构造的恶意 zip 跑一遍，断言非零退出
# 且越目录文件未被写出；同时用一份干净 zip 断言零退出（防「一律拒绝」的假修复）。
#
# 第二部分（R7-SH-04）：活跃树裸 `assert` 禁令扩展。原禁令只作用 action.yml 一个
# 文件，而 `bandit.yaml` 全局 `skips: ["B101", ...]`，故 scripts/release/contracts/
# agent 的非测试 Python 无任何第二张网；且旧正则 `/^\s*assert\s+\S/m` 连
# `assert(x)`（无空格）都抓不到——那同样是 `-O` 下被整体剥离的裸断言。
from __future__ import annotations

import re
import subprocess
import sys
import textwrap
import zipfile
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
ACTION = REPO / ".github" / "actions" / "prepare-geogebra" / "action.yml"
ACTIVE_ROOTS = ("scripts", "release", "contracts", "agent")

# `assert` 语句：允许 `assert x`、`assert(x)`、`assert (x)`、`assert\tx` 全部形态
BARE_ASSERT_RE = re.compile(r"^\s*assert\b", re.MULTILINE)
HEREDOC_RE = re.compile(r"<<'PYEOF'\r?\n(.*?)\r?\n[ \t]*PYEOF", re.DOTALL)


def _embedded_blocks(text: str) -> list[str]:
    """取 action 内嵌的全部 python heredoc 块（去公共缩进后可直接执行）。"""
    return [textwrap.dedent(m) for m in HEREDOC_RE.findall(text)]


def _zip_guard_block() -> str:
    blocks = [b for b in _embedded_blocks(ACTION.read_text(encoding="utf-8"))
              if "zipfile.ZipFile" in b]
    assert len(blocks) == 1, (
        f"zip-slip 防护块应恰好 1 个，实得 {len(blocks)}——"
        "action.yml 的 heredoc 形态变了，行为级回归失去判定对象")
    return blocks[0]


def _run_guard(tmp_path: Path, member_names: list[str]) -> subprocess.CompletedProcess:
    """在 tmp_path 内构造 geogebra.zip 并跑抽取出的防护块。"""
    (tmp_path / "guard.py").write_text(_zip_guard_block(), encoding="utf-8")
    with zipfile.ZipFile(tmp_path / "geogebra.zip", "w") as zf:
        for name in member_names:
            zf.writestr(name, "payload")
    return subprocess.run(
        [sys.executable, "guard.py"], cwd=tmp_path, capture_output=True, text=True,
        timeout=120, check=False,  # 返回码由用例本身断言（PLW1510）
    )


# ---------- R7-SH-03 行为级 zip-slip 回归 ----------


@pytest.mark.parametrize("member", [
    "../evil.txt",                    # 回溯出解压根
    "/etc/evil.txt",                  # 绝对路径
    "C:/evil.txt",                    # Windows 盘符
    "..\\evil.txt",                   # 反斜杠形态
    "sub/../../evil.txt",             # 深层再回溯
])
def test_suspect_member_is_rejected(tmp_path, member):
    res = _run_guard(tmp_path, [member])
    assert res.returncode == 1, (
        f"恶意成员 {member!r} 未被拒绝（exit={res.returncode}）"
        f" stdout={res.stdout!r} stderr={res.stderr!r}")
    assert "zip-slip" in (res.stderr + res.stdout).lower()
    # 决定性证据：越目录文件必须不存在（tmp_path 的父目录里不得多出 evil*）
    leaked = list(tmp_path.parent.glob("evil.txt"))
    assert not leaked, f"防护失效并已写出越目录文件：{leaked}"


def test_clean_members_are_accepted(tmp_path):
    """反向对照：正常成员必须放行——否则「一律拒绝」也能骗过上面的用例。"""
    res = _run_guard(tmp_path, ["HTML5/5.0/html5-geo.html", "images/logo.png"])
    assert res.returncode == 0, f"{res.stdout}\n{res.stderr}"
    assert (tmp_path / "HTML5" / "5.0" / "html5-geo.html").is_file()


def test_neutered_containment_is_caught_by_behavior_not_tokens(tmp_path):
    """本用例证明「行为锚」比「token 锚」强：把判定结果整行掏空后，
    zip-slip 字样与 sys.exit(1) 仍原样在位（旧文本门禁恒绿），但真跑必须红。"""
    guarded = _zip_guard_block()
    neutered = guarded.replace("if suspect(n)]", "if False]")
    assert "zip-slip" in neutered and "sys.exit(1)" in neutered, "变异前提不成立"
    (tmp_path / "guard.py").write_text(neutered, encoding="utf-8")
    with zipfile.ZipFile(tmp_path / "geogebra.zip", "w") as zf:
        zf.writestr("../evil.txt", "payload")
    res = subprocess.run([sys.executable, "guard.py"], cwd=tmp_path,
                         capture_output=True, text=True, timeout=120, check=False)
    assert res.returncode == 0, "变异后仍被拒——说明块里还有第二道判定（本用例前提需更新）"
    real = _run_guard(tmp_path, ["../evil.txt"])
    assert real.returncode == 1, "同一输入下原块必须拒绝（行为锚的判定力本身）"


# ---------- R7-SH-04 活跃树裸 assert 禁令 ----------


def _active_non_test_files() -> list[Path]:
    out: list[Path] = []
    for base in ACTIVE_ROOTS:
        root = REPO / base
        assert root.is_dir(), f"活跃树根缺失：{base}/（禁令扫描面塌缩）"
        for p in sorted(root.rglob("*.py")):
            norm = p.as_posix()
            if "test" in p.name.lower() or "/tests/" in norm:
                continue
            out.append(p)
    return out


def test_active_tree_has_no_bare_assert():
    """生产/门禁 Python 不得用裸 assert 表达安全判定（`-O` 下整体剥离）。

    实测本轮改动前该面为 0 命中——所以这不是一次「先放行再收口」，
    而是一条当下就绿、且能拦住未来回潮的禁令。
    """
    files = _active_non_test_files()
    # 实测面 38 个非测试 Python（scripts/release/contracts/agent）。
    # 下界取 30：新增文件不会误红，但整目录消失/大面积移出立即红。
    assert len(files) >= 30, f"扫描面异常（仅 {len(files)} 个文件）——禁令在空转"
    offenders = []
    for p in files:
        text = p.read_text(encoding="utf-8", errors="replace")
        for m in BARE_ASSERT_RE.finditer(text):
            line = text.count("\n", 0, m.start()) + 1
            offenders.append(f"{p.as_posix()}:{line}")
    assert not offenders, f"活跃树出现裸 assert（-O 剥离面）：{offenders[:10]}"


def test_bare_assert_regex_covers_no_space_form():
    """旧正则 `/^\\s*assert\\s+\\S/` 漏掉 `assert(x)`——本用例钉住新正则的覆盖面。"""
    for form in ("assert x\n", "assert(x)\n", "assert (x)\n", "assert\tx\n",
                 "    assert isinstance(v, dict), v\n"):
        assert BARE_ASSERT_RE.search(form), form
    # 不得误伤：属性访问、字符串内容、注释
    for ok in ("result.assertion = 1\n", "# assert 不可用\n", 's = "assert x"\n',
               "            assert_thing = 1\n"):
        assert not BARE_ASSERT_RE.search(ok), ok


def test_action_embedded_python_has_no_bare_assert():
    """复合 action 的两段内嵌 python 同样禁用裸 assert（zip 来自外部下载=不可信输入）。"""
    text = ACTION.read_text(encoding="utf-8")
    blocks = _embedded_blocks(text)
    assert len(blocks) >= 2, f"内嵌 python 块数异常：{len(blocks)}"
    for i, block in enumerate(blocks):
        hits = [ln for ln in block.splitlines() if BARE_ASSERT_RE.match(ln)]
        assert not hits, f"action.yml 内嵌块 #{i} 出现裸 assert：{hits}"


def test_exit_match_accepts_raise_systemexit():
    """行为锚不得把「sys.exit(1) 改写成 raise SystemExit(1)」判成缺陷——
    文本门禁要允许等价的正确改形（原锚只认 sys\\.exit\\(1\\) 会假红）。"""
    text = _zip_guard_block()
    assert "sys.exit(1)" in text
    alt = text.replace("sys.exit(1)", "raise SystemExit(1)")
    assert "raise SystemExit" in alt and re.search(
        r"(sys\.exit\(1\)|raise\s+SystemExit)", alt)

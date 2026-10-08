"""Dependency-Retlock 的 Python 重锁步骤必须真的做「增量重锁」（第八轮 B7 前置）。

`requirements-ci.in` 头注写的规程是「复用既有 pin 做增量（最小 diff）」，而这个机制
在 pip-compile 里不是开关、是**输出文件本身**：它从 `--output-file` 指向的既有文件读回
现有 pin。本步骤初版把输出写到全新的 `.relock-body.txt`，`cp` 出来的 staging 副本无人
使用 ⇒ pip-compile 看不到任何既有 pin，于是整棵传递依赖树按「当前最新」重解：
mypy/ruff 两行 bump 会连带换掉一片无关包（cyclonedx 系就在那里），而 `.in` 注释里
#27/#35/#39 三连坏 PR 的根因正是「锁变了但没人能审」。

文本锚的由来：这一步只在 `workflow_dispatch` 里跑，PR 门禁里永远不执行——行为面无法
用用例覆盖，就只能钉结构，且必须**先证明注入会红**（把 output-file 改回全新文件即红）。
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github" / "workflows" / "dependency-relock.yml"
INPUT_SOURCE = ROOT / "requirements-ci.in"


def relock_step_run() -> str:
    """取「Python 重锁」步骤的 bash 正文（步骤改名或删掉都必须报红，不是静默跳过）。"""
    doc = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    steps = doc["jobs"]["relock"]["steps"]
    matches = [s for s in steps if "Python 重锁" in str(s.get("name", ""))]
    assert len(matches) == 1, f"Python 重锁步骤必须恰好一个，实得 {len(matches)}"
    run = matches[0]["run"]
    assert isinstance(run, str) and run.strip(), "Python 重锁步骤没有 run 正文"
    return run


def test_pip_compile_writes_into_the_copy_of_the_current_lock() -> None:
    run = relock_step_run()
    seeded = re.findall(r"cp\s+requirements-ci\.txt\s+(\S+)", run)
    outputs = re.findall(r"--output-file\s+(\S+)", run)
    assert len(seeded) == 1, f"必须恰好一份 staging 副本，实得 {seeded}"
    assert len(outputs) == 1, f"必须恰好一个 pip-compile 输出面，实得 {outputs}"
    # 唯一让「增量」成立的等式：输出面 == 由当前锁拷出来的那份 staging 副本
    assert outputs[0] == seeded[0], (
        f"pip-compile 输出面（{outputs[0]}）必须就是当前锁的副本（{seeded[0]}）——"
        "写进全新文件等于整棵传递树重解，最小 diff 的规程就成了假账"
    )


def test_every_intermediate_lock_file_is_both_written_and_read() -> None:
    run = relock_step_run()
    names = sorted(set(re.findall(r"\.relock-[a-z][a-z-]*\.txt", run)))
    assert names, "步骤里一个中间产物都没有——多半是解析口径错了"
    for name in names:
        hits = len(re.findall(re.escape(name), run))
        assert hits >= 2, (
            f"{name} 只出现 {hits} 次：写出后无人读回，等价于产物漂移的死角"
            "（要么它该是指向锁的副本，要么它本不该存在）"
        )


def test_header_block_is_reattached_from_the_recomputed_file() -> None:
    run = relock_step_run()
    seeded = re.findall(r"cp\s+requirements-ci\.txt\s+(\S+)", run)[0]
    reads = re.findall(r'Path\("([^"]+)"\)\.read_text', run)
    assert seeded in reads, f"头注回贴读的不是重算后的文件（reads={reads}）"
    assert 'Path("requirements-ci.txt").read_text' in run, "头注来源必须是原锁文件的头注块"


def test_input_source_still_documents_the_incremental_procedure() -> None:
    # 三处同述才是规程：.in 里的文字、workflow 的实现、上面的结构锚。
    # .in 被改成别的口径（例如故意要整树升级）时本用例报红，逼着两边一起想清楚。
    text = INPUT_SOURCE.read_text(encoding="utf-8")
    assert "复用既有 pin" in text, "requirements-ci.in 的 SOP 记载缺失——判据来源没了"

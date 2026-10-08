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


def code_only(text: str) -> str:
    """只留代码行。本仓的注记里会**逐字抄着**被禁的旧形态（`|| true`、
    `.relock-body.txt`……），不剔注释，锚判的就是自己的说明而不是代码——
    这个坑第八轮撞过两次，这里统一在入口剔掉。"""
    return "\n".join(
        line for line in text.splitlines() if not line.strip().startswith("#")
    )


def relock_step_run() -> str:
    """取「Python 重锁」步骤的 bash 正文（步骤改名或删掉都必须报红，不是静默跳过）。"""
    doc = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    steps = doc["jobs"]["relock"]["steps"]
    matches = [s for s in steps if "Python 重锁" in str(s.get("name", ""))]
    assert len(matches) == 1, f"Python 重锁步骤必须恰好一个，实得 {len(matches)}"
    run = matches[0]["run"]
    assert isinstance(run, str) and run.strip(), "Python 重锁步骤没有 run 正文"
    return code_only(run)


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
    reads = re.findall(r'Path\("([^"]+)"\)\.(?:read_text|open)', run)
    assert seeded in reads, f"头注回贴读的不是重算后的文件（reads={reads}）"
    assert 'Path("requirements-ci.txt")' in run, "头注来源必须是原锁文件的头注块"


def test_writeback_step_cannot_swallow_a_failed_git_add() -> None:
    """写回是本 job 唯一能造成的副作用——它静默失败就等于整个执行面是空的。

    初版这里写 `git add -A windows packages.lock.json ... || true`，而仓库根没有
    `packages.lock.json`（三把锁在 windows/**/ 下）：git 对不存在的 pathspec 直接
    fatal 并放弃**整条**命令，`|| true` 吞掉退出码 ⇒ index 全空 ⇒
    `git diff --cached --quiet` 恒真 ⇒ job 高高兴兴打印「✅ 重锁无差异」收工
    （run 37796042636 实测）。所以这里判两条：一步都不许 `|| true`，
    且逐字列出的 pathspec 必须真实存在。"""
    doc = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    steps = doc["jobs"]["relock"]["steps"]
    matches = [s for s in steps if "写回分支" in str(s.get("name", ""))]
    assert len(matches) == 1, f"写回步骤必须恰好一个，实得 {len(matches)}"
    # 判代码不判注释：这一步的注记里逐字抄着被禁的旧命令行（含 `|| true`）
    code = code_only(str(matches[0]["run"]))
    assert "|| true" not in code, "写回步骤里出现 `|| true`——git add 失败会被静默吞掉"
    loops = re.findall(r"for pathspec in ([^;]+); do", code)
    assert len(loops) == 1, f"应恰好一个 pathspec 清单，实得 {len(loops)}"
    listed = loops[0].split()
    assert listed, "pathspec 清单为空"
    missing = [name for name in listed if not (ROOT / name).exists()]
    assert not missing, f"清单里的 pathspec 在仓库里不存在（git 会 fatal 并放弃整条 add）: {missing}"
    assert "git add" in code and 'add -A -- "$pathspec"' in code, "必须逐 pathspec 调用 git add -A --"


def test_header_preservation_is_newline_robust_and_verified_after_write() -> None:
    """头注回贴必须按**字节行**读，且写完要回读核对。

    `requirements-ci.txt` 的 blob 是 CRLF 并夹 16 处 `\\r\\r\\n`（git 把它判成 -text，
    `.gitattributes` 的 `eol=lf` 对它不成立——台账 R8-CI-19）。Python 的通用换行会在
    每个头注行后凭空造出一行空行，于是「取头部连续注释块」的循环第 2 行就断：
    run 37796042636 实测打出「头注块已保留（1 行）」——真按它写回去，PY-178/221/258
    那三段来源注记就静默没了。判三条：读必须 `newline=""`、不许再用
    `.replace("\\r\\n", "\\n")` 这种把 `\\r\\r\\n` 当 `\\n` 的口径、写完必须回读核对。
    """
    code = relock_step_run()
    assert 'newline=""' in code, "头注来源按通用换行读——\\r\\r\\n 会被折成空行"
    assert '.replace("\\r\\n", "\\n")' not in code, (
        "又用 replace 折 CRLF 的旧口径：它对 `\\r\\r\\n` 恰好留一个空行，正是要禁的形态"
    )
    assert "written =" in code and "missing" in code, "写完没有回读核对——丢头注会静默成功"


def test_input_source_still_documents_the_incremental_procedure() -> None:
    # 三处同述才是规程：.in 里的文字、workflow 的实现、上面的结构锚。
    # .in 被改成别的口径（例如故意要整树升级）时本用例报红，逼着两边一起想清楚。
    text = INPUT_SOURCE.read_text(encoding="utf-8")
    assert "复用既有 pin" in text, "requirements-ci.in 的 SOP 记载缺失——判据来源没了"


def _jobs(doc: dict) -> list[tuple[str, dict]]:
    return [(str(name), job) for name, job in (doc.get("jobs") or {}).items()]


def test_inline_python_heredoc_on_windows_declares_utf8_stdio() -> None:
    """Windows runner 上 Python 的 stdout 被重定向进日志管道时按 ANSI 代码页编码
    （实测 cp1252）。含中文/✅❌ 的 print 直接抛 UnicodeEncodeError——本 workflow
    的「Python 重锁」步骤就在首次 dispatch 时死在 `print("头注块已保留（…）")`
    上（run 37793334416），而报错发生在**文件已经写好之后**，看上去像「随机失败」。
    判据：任何在 windows runner 上内嵌 python heredoc 且正文含非 ASCII 的 job，
    必须显式声明 PYTHONIOENCODING=utf-8（job 级或 step 级都算）。"""
    offenders: list[str] = []
    for workflow in sorted(WORKFLOW.parent.glob("*.yml")):
        doc = yaml.safe_load(workflow.read_text(encoding="utf-8"))
        for job_name, job in _jobs(doc):
            if "windows" not in str(job.get("runs-on", "")).lower():
                continue
            runs = [code_only(str(step.get("run", ""))) for step in job.get("steps", []) or []]
            heredocs = [run for run in runs if "<<'PY'" in run or "<<PY" in run]
            if not heredocs or not any(ord(ch) > 127 for run in heredocs for ch in run):
                continue
            declared = {"PYTHONIOENCODING"} <= set(job.get("env") or {}) or any(
                "PYTHONIOENCODING" in (step.get("env") or {}) for step in job.get("steps", []) or []
            )
            if not declared:
                offenders.append(f"{workflow.name}::{job_name}")
    assert not offenders, f"内嵌 python heredoc 含非 ASCII 却未声明 PYTHONIOENCODING: {offenders}"


def test_relock_job_sets_io_encoding_for_whole_job() -> None:
    # 不只 heredoc：本 job 还跑 scripts/verify_lock_rids.py（4 处中文 print）。
    # 逐步加 env 会漏，所以要求 job 级一次性声明，且值必须是 utf-8。
    doc = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    job = doc["jobs"]["relock"]
    env = job.get("env") or {}
    assert env.get("PYTHONIOENCODING") == "utf-8", f"relock job 缺 PYTHONIOENCODING（env={env}）"

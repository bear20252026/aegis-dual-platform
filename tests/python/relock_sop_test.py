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
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github" / "workflows" / "dependency-relock.yml"
INPUT_SOURCE = ROOT / "requirements-ci.in"
sys.path.insert(0, str(ROOT / "scripts"))

from text_anchors import drop_line_comments  # 整行注释剔法的唯一出处（R9-B45 / R9-B50）


def code_only(text: str) -> str:
    """只留代码行。本仓的注记里会**逐字抄着**被禁的旧形态（`|| true`、
    `.relock-body.txt`……），不剔注释，锚判的就是自己的说明而不是代码——
    这个坑第八轮撞过两次，这里统一在入口剔掉。

    走 `drop_line_comments` 而不是 `strip_comments`：被判的是 workflow 的 shell 正文，
    那里 `/*`（glob）与 `*/`（路径形态）都是合法字符，块注释匹配会把中间的真语句删掉
    ——R9-B50 写 gradle_verification_test 时实测撞出来的，同一课两边共用一个口径。
    """
    return drop_line_comments(text)


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


# ── Gradle 面（项 10 / AEG-011，2026-10-11 启用 STRICT；R9-B32 改成按模型枚举覆盖面）──
# 这些步骤只在 workflow_dispatch 里跑，PR 面永不执行 ⇒ 只能钉结构，
# 且每条都必须证明「注入会红」。

GRADLE_JOB = "gradle-relock"
QUALITY_WORKFLOW = ROOT / ".github" / "workflows" / "android-quality.yml"
# 锁覆盖检查与全配置解析这两个任务名就是判据本身：写它们的地方只有 root 构建脚本，
# 任何一处改名/删掉，本文件与 gradle_locking_test.py 都要判红。
COVERAGE_TASK = "verifyDependencyLockCoverage"
RESOLVE_TASK = "resolveAllConfigurations"


def gradle_job_doc() -> dict:
    doc = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    assert GRADLE_JOB in doc["jobs"], f"dependency-relock 缺 {GRADLE_JOB} job"
    return doc["jobs"][GRADLE_JOB]


def gradle_relock_run() -> str:
    """取 gradle 面全部 bash 正文的拼接（剔注释——注记里逐字写着旧任务的形态）。

    R9-B53 起这一步不再是一个大步骤：装配与「校验和文件面」抽进了 composite action
    （两条平台的腿必须跑同一条命令），workflow 里剩图面与覆盖自证两条。判据要的只是
    「这些命令合起来形态对」，所以按 job 收集，不认步骤名——认步骤名会让改名变成一条
    无声的绕过（本文件其余判据也是同一个理由）。
    """
    steps = gradle_job_doc().get("steps", []) or []
    bodies = [str(s["run"]) for s in steps if isinstance(s.get("run"), str)]
    assert bodies, "gradle-relock job 一条 run 正文都没有——提取口径坏了"
    return code_only(chr(10).join(bodies))


def write_locks_line(run_text: str) -> str:
    """纯函数：取重锁正文里带 `--write-locks` 的那一条命令（恰好一条，否则判红）。"""
    lines = [ln.strip() for ln in run_text.splitlines() if "--write-locks" in ln]
    assert len(lines) == 1, f"必须恰好一条 --write-locks 命令，实得 {lines}"
    return lines[0]


def coverage_line(run_text: str) -> str:
    """纯函数：取跑覆盖检查的那一条（不带 --write-locks，带着就是自己写自己判）。"""
    lines = [
        ln.strip() for ln in run_text.splitlines()
        if COVERAGE_TASK in ln and "--write-locks" not in ln
    ]
    assert len(lines) == 1, f"覆盖检查必须恰好一条且不带 --write-locks，实得 {lines}"
    return lines[0]


def test_gradle_surface_is_selected_only_when_asked() -> None:
    doc = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    options = doc["on"]["workflow_dispatch"]["inputs"]["ecosystem"]["options"]
    assert "gradle" in options, f"ecosystem 输入里没有 gradle 选项（实有 {options}）"
    gradle_if = str(gradle_job_doc().get("if", ""))
    assert "gradle" in gradle_if and "all" in gradle_if, (
        f"gradle-relock job 必须同时在 ecosystem=gradle 与 all 下运行（if={gradle_if}）"
    )
    # 另一半：windows 的 relock job 不能跟着跑 gradle 面——它没有 Android SDK，
    # 且它的写回 pathspec 不含 android/，跑了就是「写不回任何东西的成功」。
    relock_if = str(doc["jobs"]["relock"].get("if", ""))
    assert "gradle" in relock_if, f"relock job 必须排除 ecosystem=gradle（if={relock_if}）"


def test_gradle_relock_resolves_every_configuration_not_a_task_list() -> None:
    """重锁面必须是「模型里全部可解析配置」，不能是手抄的任务清单。

    R9-B32 的实测教训：`:app:androidTestUtil` 由 AGP 的 UTP **构建监听器**解析，
    不属于任何 gradlew 任务名称面。照任务清单抄必然漏它，而漏写的后果不在 PR 面上红，
    是在 master 的依赖图生成作业上红（同期所有 PR 门禁全绿）。集合定义代替清单，
    这一类失效就没有出口：解析面 ⊇ 任何任务清单是数学事实，不是纪律。"""
    cmd = write_locks_line(gradle_relock_run())
    assert RESOLVE_TASK in cmd, f"--write-locks 必须解析 {RESOLVE_TASK}（全配置枚举），实得 {cmd}"
    assert " gradlew" in cmd or "./gradlew" in cmd, f"命令形态不对：{cmd}"
    # 反向：旧设计（逐条列 assemble*/ktlint* 任务）必须被判掉
    stale = [tok for tok in (":app:assembleRelease", ":app:lintDebug") if tok in cmd]
    assert not stale, f"重锁面又回到抄任务清单了（{stale}）——清单必然漏监听器解析的配置"


def test_written_locks_are_verified_before_writeback() -> None:
    """写完锁必须在同一个 job 里自证覆盖，否则「重锁成功」只是「Gradle 没报错」。"""
    cmd = coverage_line(gradle_relock_run())
    assert COVERAGE_TASK in cmd, f"缺覆盖自证：{cmd}"


def test_coverage_gate_is_wired_into_the_pr_face() -> None:
    """覆盖判据还得在 PR 面跑——只在 dispatch 里跑的判据等于没有判据（R9-SH-7 同课）。"""
    doc = yaml.safe_load(QUALITY_WORKFLOW.read_text(encoding="utf-8"))
    steps = doc["jobs"]["android-quality"]["steps"]
    runs = [code_only(str(s.get("run", ""))) for s in steps if s.get("run")]
    hits = [r for r in runs if COVERAGE_TASK in r]
    assert len(hits) == 1, f"android-quality 必须恰好一步跑 {COVERAGE_TASK}，实得 {len(hits)}"
    assert "--write-locks" not in hits[0], (
        "PR 面那一步绝不能带 --write-locks——带着就是「自己写自己判」，恒绿"
    )


def test_dropping_either_gradle_step_turns_the_gate_red() -> None:
    """反向锚（内存态注入，不改工作树）：删掉解析步或自证步，判据必须判红。

    判据抽成纯函数（`write_locks_line` / `coverage_line`）就是为了能做这种注入——
    否则「步骤还在」这件事本身恒真，删掉内容也测不出来。"""
    run = gradle_relock_run()
    without_resolve = chr(10).join(ln for ln in run.splitlines() if RESOLVE_TASK not in ln)
    with pytest.raises(AssertionError):
        write_locks_line(without_resolve)
    without_verify = chr(10).join(ln for ln in run.splitlines() if COVERAGE_TASK not in ln)
    with pytest.raises(AssertionError):
        coverage_line(without_verify)


def test_gradle_writeback_still_needs_its_own_guard_and_lock_only_diff() -> None:
    """写回步骤不许 `|| true`、必须自带 deps/* 守卫，且「有 diff 但没锁文件」要判红。"""
    steps = gradle_job_doc().get("steps", []) or []
    writeback = [s for s in steps if "写回分支" in str(s.get("name", ""))]
    assert len(writeback) == 1, f"gradle 面写回步骤必须恰好一个，实得 {len(writeback)}"
    code = code_only(str(writeback[0]["run"]))
    assert "|| true" not in code, "写回步骤里出现 `|| true`——git add 失败会被静默吞掉"
    assert "deps/*)" in code, "写回步骤必须自带 deps/* 二次守卫（不依赖前一步存在）"
    assert "gradle.lockfile" in code, (
        "必须校验「diff 里确实有一把锁文件」——否则顺手改了版本目录也会被推上去"
    )
    loops = re.findall(r"for pathspec in ([^;]+); do", code)
    assert len(loops) == 1, f"应恰好一个 pathspec 清单，实得 {len(loops)}"
    listed = loops[0].split()
    absent = [name for name in listed if not (ROOT / name).exists()]
    assert not absent, f"清单里的 pathspec 在仓库里不存在（git 会 fatal 并放弃整条 add）: {absent}"

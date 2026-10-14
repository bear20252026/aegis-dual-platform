#!/usr/bin/env python3
"""verify_workflow_script_paths.py —— workflow 里每条 `python <路径>.py` 必须在其**生效 cwd** 下存在。

要防的形状（第九轮 R9-B60 实测抓到的就是它）：`gradle-dependency-insight.yml` 的
「工具类路径闭包」步骤写的是 `python scripts/verify_gradle_alert_scope_boundary.py`，
而这个 job 的 `defaults.run.working-directory: android` ⇒ runner 上真正找的是
`android/scripts/…`，不存在 ⇒ 步骤 exit 2。同一批还有一行
`grep … android/*/gradle.lockfile`，glob 展不开时 grep 报错、`|| echo "(零命中)"`
**把失败印成一条看起来像结论的陈述**。这条流自 R9-B49 加进来起从没跑通过，而它是
dispatch-only 诊断面——PR 面全绿，没人会去看它红。

所以本门禁判的不是「脚本存在」，而是「**调用点能不能执行**」（§3.58 同一课：
守卫搬到仓库脚本后站在 checkout 之前，判据数的是调用点存在）。

口径与边界：
- 只判显式 `python [<cwd 相对路径>].py` 调用（`python3` 与 `-m` 形式不算路径调用）。
- 生效 cwd ＝ step 的 `working-directory` → job 的 `defaults.run` → workflow 的
  `defaults.run`；`../` 按该 cwd 解析（跨层逃逸允许，只要落点真实存在）。
- `${{ … }}` 表达式里的路径不判（展开期才可知），但会在报告里点名，方便人复核。
- 判定面塌缩（一份 workflow 都读不到 / workflow 目录缺失）⇒ exit 2，不判「通过」。

退出码：0=全部可执行 / 1=存在不可执行的调用点 / 2=环境或判定面异常。
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_DIR = ROOT / ".github" / "workflows"

# `python foo.py` / `python ./foo.py` / `python ../scripts/foo.py`——捕获整段相对路径。
PYTHON_CALL = re.compile(r"(?<![?\w-])python[3]?\s+(\./|\.\./)?[\w./-]*\.py")
# `python` 后面紧跟带 ${{ }} 的参数：展开期才可知路径，本门禁判不到——点名而不是放过
# （放过的话，「把路径挪进表达式」就成了绕过这条判据的合法通道）。
PYTHON_EXPRESSION_ARG = re.compile(r"(?<![?\w-])python[3]?\s+\S*\$\{\{")


def effective_cwd(step: dict, job: dict, workflow: dict) -> str:
    """step → job.defaults.run → workflow.defaults.run；缺省＝仓库根。"""
    for candidate in (
        (step.get("working-directory") or ""),
        str(((job.get("defaults") or {}).get("run") or {}).get("working-directory") or ""),
        str(((workflow.get("defaults") or {}).get("run") or {}).get("working-directory") or ""),
    ):
        if candidate:
            return candidate
    return "."


def check_run(body: str, cwd: str, where: str) -> list[str]:
    problems: list[str] = []
    for match in PYTHON_CALL.finditer(body):
        rel = match.group(0).split(None, 1)[1]
        target = (ROOT / cwd / rel).resolve()
        # resolve() 而不是拼接：`android/../scripts/x.py` 与 `scripts/x.py` 要判成同一个落点
        if not target.is_file():
            shown = target.relative_to(ROOT) if target.is_relative_to(ROOT) else target
            problems.append(
                f"{where}: `python {rel}` 在生效 cwd `{cwd}` 下不存在（找的是 {shown}）")
    for match in PYTHON_EXPRESSION_ARG.finditer(body):
        problems.append(
            f"{where}: {match.group(0).strip()!r} 的路径来自 ${{{{ }}}} 展开——"
            "本门禁判不到它落点是否存在，请人工核（或改成字面路径）")
    return problems


def check_document(workflow: dict, path: Path) -> list[str]:
    problems: list[str] = []
    jobs = workflow.get("jobs") or {}
    if not jobs:
        return [f"{path.name}: 没有 jobs——解析口径不对，不是「没问题」"]
    for job_name, job in jobs.items():
        if not isinstance(job, dict):
            continue
        for index, step in enumerate(job.get("steps") or []):
            if not isinstance(step, dict):
                continue
            body = step.get("run")
            if not isinstance(body, str):
                continue
            where = f"{path.name} :: {job_name} :: 第 {index} 步 {step.get('name', '')!r}"
            problems += check_run(body, effective_cwd(step, job, workflow), where)
    return problems


def run() -> int:
    if not WORKFLOW_DIR.is_dir():
        print(f"::error:: 找不到 workflow 目录：{WORKFLOW_DIR}", file=sys.stderr)
        return 2
    import yaml  # 延迟导入：环境里没有 pyyaml 时报环境错，而不是伪装成「通过」

    files = sorted(WORKFLOW_DIR.glob("*.yml")) + sorted(WORKFLOW_DIR.glob("*.yaml"))
    if not files:
        print("::error:: workflow 目录里一份定义都没有——判定面塌缩", file=sys.stderr)
        return 2
    problems: list[str] = []
    checked_steps = 0
    for path in files:
        try:
            workflow = yaml.safe_load(path.read_text(encoding="utf-8"))
        except yaml.YAMLError as exc:
            problems.append(f"{path.name}: YAML 解析失败（{exc}）")
            continue
        if not isinstance(workflow, dict):
            problems.append(f"{path.name}: 顶层不是映射——没法判 jobs")
            continue
        for job in (workflow.get("jobs") or {}).values():
            if isinstance(job, dict):
                checked_steps += sum(
                    1 for s in (job.get("steps") or [])
                    if isinstance(s, dict) and isinstance(s.get("run"), str))
        problems += check_document(workflow, path)
    if checked_steps == 0:
        print("::error:: 一个带 run 的步骤都没数到——提取口径坏了", file=sys.stderr)
        return 2
    if problems:
        for line in problems:
            print(f"::error:: {line}", file=sys.stderr)
        print(f"❌ workflow 脚本调用点不可执行（{len(problems)} 处）", file=sys.stderr)
        return 1
    print(f"[ok] {len(files)} 份 workflow / {checked_steps} 个 run 步骤里的"
          "每条 `python <路径>.py` 都在其生效 cwd 下真实存在")
    return 0


if __name__ == "__main__":
    sys.exit(run())

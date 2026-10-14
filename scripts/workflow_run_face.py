#!/usr/bin/env python3
"""workflow_run_face.py —— 「一个 workflow 的 `run:` 正文到底调用了哪些脚本」的提取单源（R9-B62）。

为什么单独一份：`verify_gate_execution_face.py` 要判「门禁脚本在哪个面上被执行」，而它的第一半
就是把执行点从 workflow 里取出来。这件事有两个非显然的口径，各对应一次实测事故：
- **只取 `run:` 正文**，不取原文。`verify_artifact_set` 在 `release.yml` 里只出现在 191-195 行的
  注记中（195 行是把命令抄成注释的那一行）——按原文正则判「它有 CI 执行点」会当场假绿（R9-B60）。
- **沿本地 `uses:` 传递**（composite action 与仓内可复用 workflow）。动作步骤里的 python 调用
  也是这个 workflow 的执行面，漏掉它就把真跑着的门禁判成不可达。

`calls_by_workflow()` 返回的生效 cwd 口径复用 `verify_workflow_script_paths.effective_cwd`
（step → job.defaults → workflow.defaults），所以「路径写对了但站在错的 cwd 里」那种形状
（R9-B60 本尊）在这里同样会落成不存在的文件，不会混进执行面。

本模块不做判定，只做提取——判定与判据口径都留在引用它的门禁里。
"""
from __future__ import annotations

from pathlib import Path

import yaml
from verify_ci_trigger_surface import WORKFLOWS
from verify_workflow_script_paths import PYTHON_CALL, effective_cwd

ROOT = Path(__file__).resolve().parents[1]


def load_document(path: Path) -> dict:
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    return document if isinstance(document, dict) else {}


def run_steps(document: dict, is_action: bool) -> list[dict]:
    """run 步骤正文；composite action 没有 job/workflow 层 defaults，生效 cwd 只取 step 自己的。"""
    if is_action:
        steps = (document.get("runs") or {}).get("steps") or []
    else:
        steps = [step for job in (document.get("jobs") or {}).values() if isinstance(job, dict)
                 for step in (job.get("steps") or [])]
    return [s for s in steps if isinstance(s, dict) and isinstance(s.get("run"), str)]


def local_uses(document: dict) -> list[Path]:
    """`uses: ./.github/actions/<dir>` 与 `uses: ./.github/workflows/<file>`——本地复用面。"""
    used = [str(step.get("uses") or "") for job in (document.get("jobs") or {}).values()
            if isinstance(job, dict) for step in (job.get("steps") or []) if isinstance(step, dict)]
    actions = [ROOT / u[len("./"):] / "action.yml" for u in used if u.startswith("./.github/actions/")]
    workflows = [ROOT / u[len("./"):] for u in used if u.startswith("./.github/workflows/")]
    return actions + workflows


def documents_of(workflow_name: str) -> list[tuple[dict, bool]]:
    """workflow 本体 ＋ 沿本地 `uses:` 传递可达的 composite action / 可复用 workflow（按路径去重）。"""
    docs: list[tuple[dict, bool]] = []
    seen: set[Path] = set()
    stack: list[tuple[Path, bool]] = [(WORKFLOWS / f"{workflow_name}.yml", False)]
    while stack:
        path, is_action = stack.pop()
        if path in seen:
            continue
        seen.add(path)
        document = load_document(path)
        if not document:
            continue
        docs.append((document, is_action))
        if not is_action:
            stack += [(target, target.parts[-2] == "actions")
                      for target in local_uses(document) if target.is_file()]
    return docs


def calls_by_workflow(names: set[str]) -> dict[str, set[Path]]:
    """每个 workflow 的 `run:` 正文（含本地复用面）在其生效 cwd 下真正调用到的脚本路径。"""
    out: dict[str, set[Path]] = {}
    for name in sorted(names):
        paths: set[Path] = set()
        for document, is_action in documents_of(name):
            for step in run_steps(document, is_action):
                cwd = effective_cwd(step, {}, {})
                for match in PYTHON_CALL.finditer(step["run"]):
                    candidate = (ROOT / cwd / match.group(0).split(None, 1)[1]).resolve()
                    if candidate.is_file():
                        paths.add(candidate)
        out[name] = paths
    return out

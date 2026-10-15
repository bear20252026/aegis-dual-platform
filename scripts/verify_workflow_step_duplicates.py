#!/usr/bin/env python3
"""verify_workflow_step_duplicates.py —— 同一个 job 里不得有两个**逐字相同**的步骤（R9-B61 现读发现）。

触发形状是 R9-B60 自己留下的：`contracts.yml` 的 `contract-source-of-truth` 里
「Workflow python call-site path gate」那一步连同上面 6 行注记被写了两遍。后果不是红，
而是**门禁跑两遍**——两份会在不同批次里各自被改，而台账 §3.60 写着「接进 contracts.yml」，
读的人以为只有一处。第八轮 §六 与 CHANGELOG 处理过同族形态（同一 ID 两条不同文案），
这里是它在 workflow 面上的对应物。

口径（另外两种备选为什么被否）：
- 判**同一 job 内**：`dependency-relock.yml` 有三个「检出目标分支」，分属三个持写权限的
  job——守卫必须写在每个 job 里（R9-CI-2 同口径），跨 job 同体不是重复。
- 判**整步骤同体**（剔掉 `name`/`id` 后逐字相同）而不是「同一条 python 调用出现两次」：
  后者会误伤合法形态——`active_tree_gates.py` 在同一 job 里被调多次是因为参数不同
  （ruff / bandit / py312），实树里另有几处同类。整步骤同体才是「没有第二份语义」的那一种。
- 不判「同名不同体」：Actions 允许步骤重名，「注记同一段话抄两遍」不在本判据射程里，
  别为了它把判据放宽成误报机器。

判定面塌缩（workflow 目录缺失 / 一个步骤都没数到）⇒ exit 2，不判「通过」。
退出码：0=无重复 / 1=存在同 job 内的重复步骤 / 2=环境或判定面异常。
"""
from __future__ import annotations

import sys
from pathlib import Path

import yaml  # 缺 pyyaml 时直接崩在这里：非零退出，而不是伪装成「通过」

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_DIR = ROOT / ".github" / "workflows"

# 身份无关的键：name 是人写的标签，id 必须唯一，二者都不算「这一步做什么」
IDENTITY_KEYS = ("name", "id")


def step_fingerprint(step: dict) -> str:
    body = {k: v for k, v in step.items() if k not in IDENTITY_KEYS}
    return yaml.safe_dump(body, sort_keys=True, allow_unicode=True)


def duplicates_in(job_steps: list) -> list[str]:
    """按指纹归组，返回「第 N、M 步是同一份内容」的问题行（空=该 job 干净）。"""
    positions: dict[str, list[tuple[int, dict]]] = {}
    for index, step in enumerate(job_steps, start=1):
        if isinstance(step, dict):
            positions.setdefault(step_fingerprint(step), []).append((index, step))
    problems: list[str] = []
    for copies in positions.values():
        if len(copies) < 2:
            continue
        label = copies[0][1].get("name", "<无名>")
        numbers = "、".join(str(index) for index, _ in copies)
        problems.append(
            f"第 {numbers} 步是同一份内容的第 {len(copies)} 次出现：{label!r}"
            "——同 job 内的第二份副本没有新语义，只会在下一批改动里单独漂移")
    return problems


def scan(workflows: dict[str, dict]) -> list[str]:
    """workflows: 相对路径名 → 解析后的 workflow 映射。返回问题清单（空=通过）。"""
    problems: list[str] = []
    for source, workflow in workflows.items():
        for job_name, job in (workflow.get("jobs") or {}).items():
            if not isinstance(job, dict):
                continue
            found = duplicates_in(job.get("steps") or [])
            problems += [f"{source} :: {job_name} :: {line}" for line in found]
    return problems


def load_workflows() -> dict[str, dict]:
    loaded: dict[str, dict] = {}
    for path in sorted(WORKFLOW_DIR.glob("*.yml")) + sorted(WORKFLOW_DIR.glob("*.yaml")):
        loaded[path.name] = yaml.safe_load(path.read_text(encoding="utf-8"))
    return loaded


def run() -> int:
    if not WORKFLOW_DIR.is_dir():
        print(f"::error:: 找不到 workflow 目录：{WORKFLOW_DIR}", file=sys.stderr)
        return 2
    workflows = load_workflows()
    if not workflows:
        print("::error:: workflow 目录里一份定义都没有——判定面塌缩", file=sys.stderr)
        return 2
    steps = sum(
        len((job or {}).get("steps") or [])
        for workflow in workflows.values()
        for job in (workflow.get("jobs") or {}).values()
        if isinstance(job, dict)
    )
    if steps == 0:
        print("::error:: 一个步骤都没数到——提取口径坏了", file=sys.stderr)
        return 2
    problems = scan(workflows)
    if problems:
        for line in problems:
            print(f"::error:: {line}", file=sys.stderr)
        print(f"❌ 同 job 内有重复步骤（{len(problems)} 处）", file=sys.stderr)
        return 1
    print(f"[ok] {len(workflows)} 份 workflow / {steps} 个步骤：同一 job 内没有"
          "第二份逐字相同的步骤")
    return 0


if __name__ == "__main__":
    sys.exit(run())

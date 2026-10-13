#!/usr/bin/env python3
"""verify_ci_trigger_surface.py —— CI 触发面与 workflow 分类的**双向对账**门禁（R9-B46 / Q48）。

起因不是「过滤不干净」而是**一句永不变红的陈述**：ADR-007 D3 写「门禁型 workflow 已全部移除
`paths:` 过滤」，而第九轮 R9-DOC-03 实测 `ci`=8、`core-rust`=3、`agent-redteam`=5、
`supply-chain`=11 四处仍在过滤 ⇒ 未列路径的改动在**合并后的 master 复验面**上静默不触发，
而检查名看起来「已过」。本批按 ADR 自己的理由（省时收益 << 漏检成本）把四处收掉，
并把「谁算门禁型、谁许过滤」从散文变成登记表 `contracts/ci/workflow-categories.yaml`。

判据（每条都在 tests/python/ci_trigger_surface_test.py 里以内存态注入证伪）：
1. `.github/workflows/` 里每个 workflow 必须**恰好归一类**；登记了不存在的文件、
   或新增 workflow 没归类——两种都判红（R9-SH-7 的双向不变量）。
2. `gates`（判定质量面）：`push` 与 `pull_request` 都不得带 `paths`/`paths-ignore`/
   `branches-ignore`，且**必须有 `pull_request` 触发**——没有 PR 面的门禁等于不存在。
3. `probes`（周检/手动维护面）：不得有 `pull_request` 触发。它们进 PR 面只会把必需检查
   集合撑成跑不完的样子（R8-CI-01 的 `Expected — Waiting for status` 事故同族）。
4. `builds`（产物链）：允许按需过滤——它们产生产物而非判定质量。

退出码：0=通过 / 1=违规 / 2=环境错误（workflows 目录或登记表缺失、YAML 解析失败）。
"""
from __future__ import annotations

import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"
REGISTRY = ROOT / "contracts" / "ci" / "workflow-categories.yaml"

CATEGORIES = ("gates", "builds", "probes")
FILTER_KEYS = ("paths", "paths-ignore", "branches-ignore")


def triggers_of(document: object) -> dict:
    """取 `on:` 块——YAML 1.1 把裸 `on` 解析成 True，两种键都要认。"""
    if not isinstance(document, dict):
        return {}
    raw = document.get("on", document.get(True))
    if raw is None:
        return {}
    if isinstance(raw, str):          # `on: push` 这种标量形态
        return {raw: {}}
    return {key: (body or {}) for key, body in raw.items()}


def filtered_events(triggers: dict) -> list[str]:
    """返回带路径/分支过滤的触发事件名。"""
    out: list[str] = []
    for event, body in triggers.items():
        if isinstance(body, dict) and any(key in body for key in FILTER_KEYS):
            out.append(str(event))
    return out


def load_registry() -> dict[str, list[str]]:
    doc = yaml.safe_load(REGISTRY.read_text(encoding="utf-8"))
    if not isinstance(doc, dict):
        raise ValueError("workflow-categories.yaml 顶层必须是映射")
    return {name: list(doc.get(name) or []) for name in CATEGORIES}


def violations(workflow_names: set[str], registry: dict[str, list[str]],
               triggers_by_name: dict[str, dict]) -> list[str]:
    problems: list[str] = []
    registered = {name for names in registry.values() for name in names}

    for name in sorted(registered - workflow_names):
        problems.append(f"登记表引用了不存在的 workflow：{name}.yml（分类要跟着实树走）")
    for name in sorted(workflow_names - registered):
        problems.append(f"新增 workflow 未归类：{name}.yml（gates/builds/probes 三选一）")
    for name in sorted(workflow_names):
        in_categories = [c for c in CATEGORIES if name in (registry.get(c) or [])]
        if len(in_categories) > 1:
            problems.append(f"{name}.yml 被归进多类（{', '.join(in_categories)}）——每个 workflow 恰好一类")

    gates = set(registry.get("gates") or [])
    probes = set(registry.get("probes") or [])
    for name in sorted(workflow_names):
        triggers = triggers_by_name.get(name, {})
        filtered = filtered_events(triggers)
        if name in gates:
            if filtered:
                problems.append(
                    f"门禁型 {name}.yml 仍带触发过滤（{', '.join(filtered)}）"
                    "——未列路径的改动会在 PR 面或 master 复验面上静默不触发")
            if "pull_request" not in triggers:
                problems.append(f"门禁型 {name}.yml 没有 pull_request 触发——不在 PR 面上判的门禁等于不存在")
        if name in probes and "pull_request" in triggers:
            problems.append(
                f"探测/维护型 {name}.yml 出现 pull_request 触发——它会进必需检查集合，"
                "而周检面在 PR 上未必跑得完（R8-CI-01 卡 merge box 的同型形状）")
    return problems


def workflow_files() -> set[str]:
    return {p.stem for p in WORKFLOWS.glob("*.yml")}


def parsed_triggers(names: set[str]) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for name in names:
        out[name] = triggers_of(yaml.safe_load((WORKFLOWS / f"{name}.yml").read_text(encoding="utf-8")))
    return out


def run() -> int:
    if not WORKFLOWS.is_dir():
        print(f"[环境错误] 缺 workflows 目录：{WORKFLOWS}", file=sys.stderr)
        return 2
    if not REGISTRY.is_file():
        print(f"[环境错误] 缺登记表：{REGISTRY}", file=sys.stderr)
        return 2
    try:
        registry = load_registry()
        names = workflow_files()
        triggers = parsed_triggers(names)
    except (yaml.YAMLError, ValueError) as exc:
        print(f"[环境错误] 解析失败：{exc}", file=sys.stderr)
        return 2
    if not names:
        print("[环境错误] workflows 目录为空", file=sys.stderr)
        return 2
    problems = violations(names, registry, triggers)
    if problems:
        for line in problems:
            print(f"❌ {line}")
        print(f"共 {len(problems)} 条违规（判据见本文件 docstring）")
        return 1
    counts = {c: len(v) for c, v in registry.items()}
    print(f"[ok] 触发面与分类一致（{len(names)} 个 workflow：gates {counts['gates']} 无过滤且上 PR，"
          f"builds {counts['builds']} 可按需，probes {counts['probes']} 不进 PR 面）")
    return 0


if __name__ == "__main__":
    sys.exit(run())

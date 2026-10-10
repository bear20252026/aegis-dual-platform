# release_concurrency_test.py —— 13(b)（第九轮 2026-10-10 定稿项 13）：
# 「既可被 workflow_call 又可 workflow_dispatch」的交付链必须有顶层 concurrency，
# 且不得 cancel-in-progress。
#
# 为什么这类 workflow 会自我重叠：两条触发路径（编排器调用 + 手动 dispatch）各自开一个
# run，两个 run 都在给**同一个版本号**做 build → sbom → attestations → 发布资产。
# PY-007/008 当年消掉的是「tag 直推 + 编排器」双触发，dispatch 这条侧门一直在。
# 半路取消更糟：制品写了一半、attestation 已签发，下一次重跑面对的是脏状态——
# 所以判据是「必须排队」而不是「允许抢占」。
#
# 边界必须说清（别把这条读成整条发布链的串行锁）：GitHub 的 concurrency 组是
# **per-workflow** 的，跨 workflow 不互斥。父级 release.yml 的组管父级排队，
# 本条只管「同一个交付链不自我重叠」。
from __future__ import annotations

import pathlib

import yaml

REPO = pathlib.Path(__file__).resolve().parents[2]
WORKFLOWS = REPO / ".github" / "workflows"

# PyYAML 把裸 `on:` 解析成布尔键 True（YAML 1.1），本仓两种写法都在用。
_TRIGGERS = ("on", True)


def triggers(doc: dict) -> dict:
    for key in _TRIGGERS:
        if isinstance(doc.get(key), dict):
            return doc[key]
    return {}


def violations(doc: dict) -> list[str]:
    """单份 workflow 定义的判定（供实树扫描与故障注入共用）。"""
    called = "workflow_call" in triggers(doc)
    dispatchable = "workflow_dispatch" in triggers(doc)
    if not (called and dispatchable):
        return []
    concurrency = doc.get("concurrency")
    if concurrency is None:
        return ["既可 workflow_call 又可 workflow_dispatch，却无顶层 concurrency"]
    if not isinstance(concurrency, dict):
        return []  # 字符串简写形态（只有 group）：GitHub 默认 cancel-in-progress=false，合规
    if concurrency.get("cancel-in-progress") is True:
        return ["发布链 concurrency 允许取消在跑的运行（半截制品 + 已签 attestation）"]
    return []


def scan() -> tuple[int, list[str]]:
    """返回 (在判定面内的 workflow 数, 违规列表)。"""
    checked = 0
    offenders: list[str] = []
    for path in sorted(list(WORKFLOWS.glob("*.yml")) + list(WORKFLOWS.glob("*.yaml"))):
        doc = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(doc, dict):
            continue
        called = "workflow_call" in triggers(doc)
        if called:
            checked += 1
        for problem in violations(doc):
            offenders.append(f"{path.name}: {problem}")
    return checked, offenders


def test_real_tree_has_no_overlapping_release_entrypoints():
    checked, offenders = scan()
    assert checked >= 3, f"扫描面塌缩：只判了 {checked} 份 workflow_call 交付链（基线 ≥3）"
    assert not offenders, "；".join(offenders)


def test_gate_flags_missing_and_preemptive_concurrency():
    dual = {"on": {"workflow_call": {}, "workflow_dispatch": {}}}
    assert violations(dual), "双触发面无 concurrency 必须判违规——否则本锚是摆设"
    assert not violations({**dual, "concurrency": {"group": "x", "cancel-in-progress": False}})
    assert not violations({**dual, "concurrency": "x-${{ github.ref }}"}), "字符串简写形态不得误判"
    assert violations({**dual, "concurrency": {"group": "x", "cancel-in-progress": True}})
    assert not violations({"on": {"workflow_call": {}}}), "只可被调用的 workflow 不在判定面"
    assert not violations({"on": {"workflow_dispatch": {}, "push": {}}}), "不可被调用的不在判定面"


def test_three_subworkflows_declare_a_non_preemptive_group():
    for rel, expected_group in (
        ("release-core.yml", "release-core"),
        ("release-android.yml", "release-android"),
        ("release-windows.yml", "release-windows"),
        ("release.yml", "release"),
    ):
        doc = yaml.safe_load((WORKFLOWS / rel).read_text(encoding="utf-8"))
        concurrency = doc.get("concurrency")
        assert isinstance(concurrency, dict), rel
        assert concurrency["group"] == f"{expected_group}-${{{{ github.ref }}}}", rel
        assert concurrency["cancel-in-progress"] is False, rel

# dotnet_suite_composite_wiring_test.py —— 定稿项 13(a)（R9-B16）：dotnet test 执行面
# 单源**之后**的接线锚。
#
# 抽取前的形态是八条 dotnet test 在四个 workflow 里各抄一整行命令（compat / contracts /
# native-policy-artifacts / release-windows），后跟一条发现数下界断言（R9-CI-9）。命令面
# 复制八份的失败形态很具体：给其中一份补参数，其余七份静默保持旧口径。
#
# 抽取把判定面搬到了两个新位置，因此锚也必须跟着搬——否则「门禁写好了但没接线」这类
# 第四种失效（R9-CI-9 当初记的那一种）会以新的形态重现：
# · 调用点少一个输入 / 下界被人顺手调松 / 两个套件共用 results 目录 ⇒ 这里判红；
# · **原生模式的环境导出被漏掉** ⇒ native-policy 与 release-windows 那四个调用点会退化成
#   「托管模式又跑一遍」，而发现数下界照样达标（本文件第 6 条专防这条）；
# · 抽取只搬了一半、workflow 里还留着 dotnet test ⇒ 第 8 条判红（两份口径并存＝回到原点）。
from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml
from workflow_exit_code_test import _run_blocks

ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = ROOT / ".github" / "workflows"
ACTION_PATH = ROOT / ".github" / "actions" / "dotnet-test-suite" / "action.yml"

REQUIRED_INPUTS = ("project", "results-dir", "trx-name", "label", "minimum")
EXPECTED_FLOORS = {"core": 700, "broker": 160}
NATIVE_ENV = "AEGIS_REQUIRE_NATIVE_POLICY_CORE"
# 以原生模式跑测试的两个 job——它们的调用点必须有环境导出在前。
NATIVE_WORKFLOWS = ("native-policy-artifacts.yml", "release-windows.yml")


def _suite_of(token: str) -> str:
    lowered = str(token).lower()
    for suite in EXPECTED_FLOORS:
        if suite in lowered:
            return suite
    return "?"


def _load(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def call_sites() -> list[tuple[str, str, str, dict]]:
    """(workflow 文件名, job, 步骤名, with) ——实树里全部 composite 调用点。"""
    sites: list[tuple[str, str, str, dict]] = []
    for path in sorted(WORKFLOWS.glob("*.yml")) + sorted(WORKFLOWS.glob("*.yaml")):
        for jid, spec in (_load(path).get("jobs") or {}).items():
            for step in (spec or {}).get("steps", []) or []:
                if "dotnet-test-suite" in str(step.get("uses", "")):
                    sites.append((path.name, jid, str(step.get("name", "")),
                                  dict(step.get("with") or {})))
    return sites


def site_problems(workflow: str, site: dict) -> list[str]:
    """单个调用点的判定：输入齐不齐、下界对不对、工程与套件对不对。"""
    problems: list[str] = []
    missing = [key for key in REQUIRED_INPUTS if not site.get(key)]
    if missing:
        problems.append(f"{workflow} 调用点缺输入 {missing}（composite 的输入都是必填）")
    label = str(site.get("label", ""))
    suite = _suite_of(label)
    if suite == "?":
        problems.append(f"label {label!r} 认不出套件")
    else:
        if int(site.get("minimum", -1)) != EXPECTED_FLOORS[suite]:
            problems.append(
                f"{suite} 下界 {site.get('minimum')} 与登记值 {EXPECTED_FLOORS[suite]} 漂移")
        if suite not in str(site.get("project", "")).lower():
            problems.append(f"project 与 label 不是同一套件：{site.get('project')} / {label}")
    if not str(site.get("results-dir", "")).startswith("TestResults/"):
        problems.append("results-dir 不在 TestResults/ 下（.gitignore 与门禁口径都按此处收）")
    return problems


def native_export_problems(workflow: str, doc: dict) -> list[str]:
    """原生调用点前面必须有 env 导出——否则那两条测试退化成托管模式重跑，
    而下界断言看不出来（它只数发现数，不数 P/Invoke 往返）。"""
    problems: list[str] = []
    for jid, spec in (doc.get("jobs") or {}).items():
        steps = (spec or {}).get("steps", []) or []
        seen_export = False
        for step in steps:
            body = str(step.get("run") or "")
            if f"{NATIVE_ENV}=1" in body or f"{NATIVE_ENV} = \"1\"" in body:
                seen_export = True
            if "dotnet-test-suite" in str(step.get("uses", "")) and not seen_export:
                problems.append(
                    f"{jid}：{step.get('name')} 在 {NATIVE_ENV} 导出之前调用测试套件"
                    "⇒ 该调用点实为托管模式重跑")
    return problems


# ---------------------------------------------------------------- 现树

def test_call_sites_are_eight_across_four_workflows():
    """台账实测 8 条 dotnet test（四 workflow × 2）。数量对不上＝抽取漏了一处或
    解析面漏了形态（matrix、job 级 defaults、composite 套 composite）。"""
    sites = call_sites()
    assert len(sites) == 8, f"实见 {len(sites)} 个调用点，与台账 8 个不符"
    assert len({name for name, _jid, _n, _w in sites}) == 4, "调用点应分布在四个 workflow"


def test_every_call_site_is_clean():
    problems = [f"{name}·{label}: {p}"
                for name, _jid, label, with_ in call_sites()
                for p in site_problems(name, with_)]
    assert not problems, problems


def test_results_dirs_do_not_collide_within_a_workflow():
    """同 workflow 内两个套件共用 results 目录 ⇒ 计数互相污染（R9-CI-9 的独立目录口径）。"""
    seen: dict[tuple[str, str], list[str]] = {}
    for name, jid, _step, with_ in call_sites():
        seen.setdefault((name, jid), []).append(str(with_.get("results-dir")))
    dupes = {key: dirs for key, dirs in seen.items() if len(set(dirs)) != len(dirs)}
    assert not dupes, f"同一 job 内复用 results-dir：{dupes}"


def test_native_call_sites_are_preceded_by_the_env_export():
    problems: list[str] = []
    for wf in NATIVE_WORKFLOWS:
        problems += native_export_problems(wf, _load(WORKFLOWS / wf))
    assert not problems, problems


def test_composite_body_is_the_single_source_of_the_flags():
    """命令面只在 action 正文里出现一次，且带全套 TRX/下界/退出码处置。"""
    doc = _load(ACTION_PATH)
    blocks = [run for _where, _name, run in _run_blocks(doc)]
    assert len(blocks) == 1, f"composite 应只有一个执行块，实见 {len(blocks)}"
    body = blocks[0]
    required = ("dotnet test", "--configuration Release", "-r win-x64",
                "-p:RestoreLockedMode=true", "--results-directory", "trx;",
                "assert_test_counts.py", "--minimum", "--label")
    missing = [token for token in required if token not in body]
    assert not missing, f"composite 正文缺参数 {missing}"
    assert body.count("$LASTEXITCODE") >= 2, "两条原生命令都必须各自断退出码（R7-TOOL-01）"


def test_composite_passes_inputs_through_env_not_run_text():
    """R9-CI-2 口径：`${{ }}` 在 shell 解析之前完成文本替换——正文里出现输入表达式即注入面。"""
    doc = _load(ACTION_PATH)
    for _where, _name, run in _run_blocks(doc):
        assert "${{" not in run, "run 正文里不得直接插值 inputs"
    env_blob = yaml.safe_dump(doc)
    for key in REQUIRED_INPUTS:
        assert key.upper().replace("-", "_") in env_blob.upper(), f"输入 {key} 未经 env 中转"


def test_no_dotnet_test_survives_in_workflows():
    """抽取不能只做一半：workflow 里再出现 dotnet test ＝ 两份口径并存。"""
    leftovers = []
    for path in sorted(WORKFLOWS.glob("*.yml")):
        for _where, name, run in _run_blocks(_load(path)):
            if any(line.strip().startswith("dotnet test") for line in run.splitlines()):
                leftovers.append(f"{path.name}::{name}")
    assert not leftovers, f"仍有 workflow 自己写 dotnet test：{leftovers}"


# ---------------------------------------------------------------- 反向锚（内存态注入）

def test_loosened_floor_is_detected():
    bad = {"project": "windows/tests/Aegis.Windows.Core.Tests/Aegis.Windows.Core.Tests.csproj",
           "results-dir": "TestResults/core", "trx-name": "core-tests.trx",
           "label": "Core", "minimum": 1}
    found = site_problems("compat.yml", bad)
    assert any("下界" in p for p in found), found


def test_missing_input_is_detected():
    bad = {"project": "x.csproj", "results-dir": "TestResults/core",
           "label": "Core", "minimum": 700}
    found = site_problems("compat.yml", bad)
    assert any("缺输入" in p for p in found), found


def test_suite_project_mismatch_is_detected():
    bad = {"project": "windows/tests/Aegis.Windows.Broker.Tests/B.csproj",
           "results-dir": "TestResults/core", "trx-name": "c.trx",
           "label": "Core", "minimum": 700}
    found = site_problems("compat.yml", bad)
    assert any("不是同一套件" in p for p in found), found


def test_missing_native_export_is_detected():
    """把 env 导出步删掉 ⇒ 必须判出「调用点实为托管模式重跑」，而不是静默通过。"""
    doc = _load(WORKFLOWS / "release-windows.yml")
    for jid, spec in doc["jobs"].items():
        spec["steps"] = [s for s in spec.get("steps", [])
                         if "Export the native bridge test environment" not in str(s.get("name"))]
    found = native_export_problems("release-windows.yml", doc)
    assert found, "删掉原生环境导出后判定面必须给出问题"
    assert any("托管模式重跑" in p for p in found), found


def test_dropped_flag_in_composite_is_detected(tmp_path, monkeypatch):
    body = ACTION_PATH.read_text(encoding="utf-8")
    monkeypatch.setattr(sys.modules[__name__], "ACTION_PATH", tmp_path / "action.yml")
    (tmp_path / "action.yml").write_text(
        body.replace("-p:RestoreLockedMode=true ", ""), encoding="utf-8")
    with pytest.raises(AssertionError) as exc:
        test_composite_body_is_the_single_source_of_the_flags()
    assert "RestoreLockedMode" in str(exc.value)

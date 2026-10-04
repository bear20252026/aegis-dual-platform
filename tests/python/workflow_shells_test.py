# workflow_shells_test.py —— R7-TOOL-01（第七轮 2026-10-04）：pwsh 步骤退出码门禁自测。
#
# 为什么需要这个文件：门禁脚本本身若写错（正则永不匹配、目录读空即放行），
# 它保护的缺陷就会以「常绿」形态复活——这正是本轮要消灭的那一类。故此处
# ① 断言真实仓库当前无违规，② 断言植入违规必被抓（能失败），
# ③ 断言 workflow 目录缺失是环境错误（exit 2）而非放行（exit 0）。
from __future__ import annotations

import check_workflow_shells as cws
import yaml

REAL_WORKFLOWS = cws.WORKFLOWS


def _write_workflow(tmp_path, name: str, doc: dict) -> None:
    (tmp_path / name).write_text(yaml.dump(doc, sort_keys=False), encoding="utf-8")


def test_real_repo_has_no_unasserted_native():
    """现网口径：全部 pwsh 步骤的原生命令都必须在后续命令前断退出码。"""
    assert REAL_WORKFLOWS.is_dir(), f"workflow 目录缺失：{REAL_WORKFLOWS}"
    assert cws.violations(REAL_WORKFLOWS) == []


def test_scanned_surface_is_not_silently_empty():
    """扫描面为空即恒真是本仓门禁的经典失效形态——这里钉住「确实扫到了 pwsh 步骤」。

    若哪天 workflow 被改名/移动导致 glob 落空，`violations() == []` 会空洞地成立；
    本用例把「至少扫到 4 个 pwsh 步骤」做成下界锚（同 bridge_ops.test.mjs 的反腐烂锚口径）。
    """
    pwsh_steps = 0
    for f in sorted(REAL_WORKFLOWS.glob("*.yml")):
        doc = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
        for job in (doc.get("jobs") or {}).values():
            for step in (job.get("steps") or []):
                if isinstance(step, dict) and step.get("shell") == "pwsh" and step.get("run"):
                    pwsh_steps += 1
    assert pwsh_steps >= 4, f"pwsh 步骤样本过少（{pwsh_steps}）——门禁覆盖面已漂移，需核实"


def test_planted_unasserted_native_is_detected(tmp_path):
    """能失败：测试红 + 后续构建绿且不断退出码 ⇒ 必须判违规。"""
    _write_workflow(tmp_path, "planted.yml", {"jobs": {"b": {"steps": [
        {"name": "n", "shell": "pwsh",
         "run": "dotnet test a.csproj\ndotnet publish a.csproj\n"},
    ]}}})
    found = cws.violations(tmp_path)
    assert len(found) == 1, found
    assert "dotnet test" in found[0]


def test_last_native_needs_no_trailing_check(tmp_path):
    """末条原生命令的退出码即步骤退出码，不要求再补断言（防误报）。"""
    _write_workflow(tmp_path, "ok.yml", {"jobs": {"b": {"steps": [
        {"name": "n", "shell": "pwsh", "run": "cargo build --release\n"},
    ]}}})
    assert cws.violations(tmp_path) == []


def test_explicit_exitcode_check_satisfies_gate(tmp_path):
    _write_workflow(tmp_path, "ok.yml", {"jobs": {"b": {"steps": [
        {"name": "n", "shell": "pwsh",
         "run": "dotnet test a.csproj\n"
                "if ($LASTEXITCODE -ne 0) { throw \"test failed\" }\n"
                "dotnet publish a.csproj\n"},
    ]}}})
    assert cws.violations(tmp_path) == []


def test_comment_only_guard_does_not_satisfy_gate(tmp_path):
    """注释里出现 $LASTEXITCODE 不算处置——防「写个注释当门禁」。"""
    _write_workflow(tmp_path, "bad.yml", {"jobs": {"b": {"steps": [
        {"name": "n", "shell": "pwsh",
         "run": "dotnet test a.csproj\n# 这里应当检查 $LASTEXITCODE\n"
                "dotnet publish a.csproj\n"},
    ]}}})
    assert len(cws.violations(tmp_path)) == 1


def test_bash_steps_are_out_of_scope(tmp_path):
    """bash 侧由 run-bash 包装的 set -eo pipefail 兜住，不属本门禁。"""
    _write_workflow(tmp_path, "bash.yml", {"jobs": {"b": {"steps": [
        {"name": "n", "shell": "bash", "run": "cargo test\ncargo build\n"},
    ]}}})
    assert cws.violations(tmp_path) == []


def test_missing_workflow_dir_is_env_error(tmp_path):
    """目录缺失 → exit 2（环境错误），绝不 0（静默放行）。"""
    assert cws.run_check(tmp_path / "nope") == 2


def test_unparsable_yaml_is_env_error(tmp_path):
    (tmp_path / "broken.yml").write_text("jobs: [ { :::\n", encoding="utf-8")
    assert cws.run_check(tmp_path) == 2


def test_self_test_passes_on_real_repo():
    """脚本自带故障注入自证——它本身也必须为 0。"""
    assert cws.self_test() == 0


def test_control_flow_lines_are_not_treated_as_native_calls(tmp_path):
    """`if (...) {` / 赋值行不得被当原生命令统计（防把门禁稀释成噪声）。"""
    _write_workflow(tmp_path, "cf.yml", {"jobs": {"b": {"steps": [
        {"name": "n", "shell": "pwsh",
         "run": "$dll = (Resolve-Path x).Path\n"
                "if ($env:T -eq \"tag\") { Write-Host tag }\n"
                "cargo test\n"},
    ]}}})
    assert cws.violations(tmp_path) == []

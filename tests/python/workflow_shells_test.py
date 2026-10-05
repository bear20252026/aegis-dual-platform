# workflow_shells_test.py —— R7-TOOL-01（第七轮 2026-10-04）+ R8-CI-03（第八轮）：
# pwsh 步骤退出码门禁的自测。
#
# 为什么需要这个文件：门禁脚本本身若写错（正则永不匹配、目录读空即放行），
# 它保护的缺陷就会以「常绿」形态复活——这正是本轮要消灭的那一类。故此处
# ① 断言真实仓库当前无违规且**确实扫到了 pwsh 步骤**（扫描面计数由门禁自身
#    单源提供，不再像第七轮那样在测试里另写一遍口径不同的扫描——那正是
#    R8-CI-03 的盲区连下界锚都抓不到的原因），
# ② 逐种形态植入违规断言必被抓（能失败），
# ③ 断言 workflow 目录缺失/解析失败/扫描面空转都是环境错误（exit 2）而非放行。
from __future__ import annotations

import check_workflow_shells as cws
import yaml

REAL_WORKFLOWS = cws.WORKFLOWS


def _write_workflow(tmp_path, name: str, doc: dict) -> None:
    (tmp_path / name).write_text(yaml.dump(doc, sort_keys=False), encoding="utf-8")


def test_real_repo_has_no_unasserted_native():
    """现网口径：全部 pwsh 步骤的原生命令都必须在后续命令前断退出码。"""
    assert REAL_WORKFLOWS.is_dir(), f"workflow 目录缺失：{REAL_WORKFLOWS}"
    assert cws.violations(REAL_WORKFLOWS, cws.ACTIONS) == []


def test_scanned_surface_is_not_silently_empty():
    """扫描面为空即恒真是本仓门禁的经典失效形态——这里钉住「确实扫到了 pwsh 步骤」。

    R8-CI-03：计数改取门禁自己的 `scan()` 返回值（单源）。第七轮版在测试里另写一遍
    `step.get("shell") == "pwsh"` 的精确匹配，与门禁的 `"pwsh" in lower()` 口径不同源，
    于是「job 级 defaults 声明 pwsh」「windows 隐式默认 pwsh」这两类步骤既不进门禁
    也不进锚——漏扫面完全不可见（legacy-python-guard 的两处吞失败因此活了五轮）。
    """
    _violations, pwsh_steps, windows_jobs = cws.scan(REAL_WORKFLOWS, cws.ACTIONS)
    assert pwsh_steps >= 4, f"pwsh 步骤样本过少（{pwsh_steps}）——门禁覆盖面已漂移，需核实"
    assert windows_jobs >= 1, f"扫不到 windows job（{windows_jobs}）——runs-on 判定漂移"


def test_planted_unasserted_native_is_detected(tmp_path):
    """能失败：测试红 + 后续构建绿且不断退出码 ⇒ 必须判违规。"""
    _write_workflow(tmp_path, "planted.yml", {"jobs": {"b": {"steps": [
        {"name": "n", "shell": "pwsh",
         "run": "dotnet test a.csproj\ndotnet publish a.csproj\n"},
    ]}}})
    found = cws.violations(tmp_path)
    assert len(found) == 1, found
    assert "dotnet test" in found[0]


def test_job_level_defaults_shell_is_in_scope(tmp_path):
    """R8-CI-03 第 1 项：Actions 的 job 级默认 shell 写在 defaults.run.shell——必须受检。"""
    _write_workflow(tmp_path, "defaults.yml", {"jobs": {"b": {
        "defaults": {"run": {"shell": "pwsh"}},
        "steps": [{"name": "n", "run": "cargo test\ncargo build\n"}],
    }}})
    found = cws.violations(tmp_path)
    assert len(found) == 1, found
    assert "cargo test" in found[0]


def test_windows_runner_implicit_pwsh_is_in_scope(tmp_path):
    """R8-CI-03 第 2 项：windows runner 未写 shell 时默认即 pwsh（runner 源码 DefaultShell）
    ——第七轮把这类步骤整段当成「不归我管」，legacy-python-guard 的吞失败因此存活。"""
    _write_workflow(tmp_path, "implicit.yml", {"jobs": {"b": {
        "runs-on": "windows-latest",
        "steps": [{"name": "n", "run": "pip install -r a.txt\npython selftest_x.py\n"}],
    }}})
    found = cws.violations(tmp_path)
    assert len(found) == 1, found
    assert "pip install" in found[0]


def test_call_operator_native_is_in_scope(tmp_path):
    """R8-CI-03 第 3 项：`& \"C:\\...\\signtool.exe\"` 首 token 是 `&`，命令表须认得。"""
    _write_workflow(tmp_path, "callop.yml", {"jobs": {"b": {"steps": [
        {"name": "n", "shell": "pwsh",
         "run": "& \"C:\\Program Files\\signtool.exe\" sign a.pfx\niscc installer.iss\n"},
    ]}}})
    assert len(cws.violations(tmp_path)) == 1


def test_python_toolchain_commands_are_in_scope(tmp_path):
    """R8-CI-03 第 3 项（表）：ruff/bandit/mypy/pip-audit 这类命令第七轮表里没有。"""
    _write_workflow(tmp_path, "tools.yml", {"jobs": {"b": {"steps": [
        {"name": "n", "shell": "pwsh", "run": "ruff check .\nbandit -r app -q\n"},
    ]}}})
    assert len(cws.violations(tmp_path)) == 1


def test_composite_action_steps_are_in_scope(tmp_path):
    """R8-CI-03 第 4 项：.github/actions/*/action.yml 的 runs.steps 同受检。"""
    action_dir = tmp_path / "actions" / "plug"
    action_dir.mkdir(parents=True)
    (action_dir / "action.yml").write_text(yaml.dump(
        {"runs": {"using": "composite", "steps": [
            {"name": "n", "shell": "pwsh",
             "run": "dotnet test a.csproj\ndotnet build a.csproj\n"}]}},
        sort_keys=False), encoding="utf-8")
    wf = tmp_path / "wf"
    wf.mkdir()
    found = cws.violations(wf, tmp_path / "actions")
    assert len(found) == 1, found


def test_empty_scan_surface_is_env_error(tmp_path):
    """R8-CI-03：windows job 在场却扫不到 pwsh 步骤 ⇒ 门禁自身失灵，exit 2 不放行。"""
    _write_workflow(tmp_path, "only_bash.yml", {"jobs": {"b": {
        "runs-on": "windows-latest",
        "steps": [{"name": "n", "shell": "bash", "run": "cargo test\ncargo build\n"}],
    }}})
    assert cws.run_check(tmp_path, tmp_path / "no_actions") == 2


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
    assert cws.run_check(tmp_path / "nope", tmp_path / "no_actions") == 2


def test_unparsable_yaml_is_env_error(tmp_path):
    (tmp_path / "broken.yml").write_text("jobs: [ { :::\n", encoding="utf-8")
    assert cws.run_check(tmp_path, tmp_path / "no_actions") == 2


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


def test_windows_implicit_pwsh_with_single_native_command_is_clean(tmp_path):
    """隐式 pwsh + 单条原生命令：末条即步骤退出码，能红，不得误报（现网 12 处此形态）。"""
    _write_workflow(tmp_path, "single.yml", {"jobs": {"b": {
        "runs-on": "windows-latest",
        "steps": [{"name": "n", "run": "dotnet build src/A.csproj\n"}],
    }}})
    _violations, pwsh_steps, _jobs = cws.scan(tmp_path)
    assert pwsh_steps == 1
    assert cws.violations(tmp_path) == []

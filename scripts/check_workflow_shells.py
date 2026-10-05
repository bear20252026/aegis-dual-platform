#!/usr/bin/env python3
"""check_workflow_shells.py —— R7-TOOL-01（第七轮审计 2026-10-04）：pwsh 步骤退出码门禁。

背景：`shell: pwsh` 的 GitHub Actions 步骤把 `$ErrorActionPreference` 设为 `stop`，
但该偏好**只约束 cmdlet 错误**——原生命令（cargo/dotnet/python/...）非零退出既不中断
脚本，也不产生 PowerShell 错误（`$PSNativeCommandUseErrorActionPreference` 在 PS 7.3
引入时仍标 experimental，Actions 包装脚本不设置它）。于是步骤退出码取自**末条**原生
命令：第六轮的 `release-windows.yml` 里 `dotnet test` 之后紧跟 `dotnet publish`，
测试红 + 构建绿 ⇒ 步骤绿 ⇒ 正典安装包照常产出。同类实例共 3 处，已逐条补
`if ($LASTEXITCODE -ne 0) { throw }`。

第八轮（R8-CI-03）补四处结构性盲区——第七轮版只认「步骤上写了 `shell: pwsh`」这一种
形态，而实测 GitHub runner 的真实语义宽得多：

1. **job 级默认 shell 的键路径写错**：真实位置是 `jobs.<id>.defaults.run.shell`，
   第七轮读的是 `jobs.<id>.shell`（Actions 无此键）⇒ 按 defaults 声明 pwsh 的 job
   整段不进扫描面。
2. **windows runner 未写 `shell:` 时默认就是 pwsh**（`ScriptHandler.cs` 的
   `DefaultShell` 对 Windows 返回 pwsh/powershell）⇒ 只扫显式 `shell:` 会把这类步骤
   全部当成「不归我管」，而 `legacy-python-guard.yml` 的两处吞失败残留（R8-CI-02）
   正是从这个口子活下来的。
3. **调用运算符形态** `& "C:\\...\\signtool.exe"`：首 token 是 `&`，命令表永不匹配。
4. **composite action 不在面内**：`.github/actions/*/action.yml` 的 `runs.steps`
   同样能写 `shell: pwsh`。

判定规则（未变）：pwsh 步骤里任一原生命令**不是**块内最后一条原生命令时，它与下一条
原生命令之间（或到块尾）必须出现退出码处置——`$LASTEXITCODE` / `throw` / `exit` /
`|| exit` / `$PSNativeCommandUseErrorActionPreference`。缺失即违规。

扫描面为空即失败：windows runner 在场却扫不到任何 pwsh 步骤 ⇒ 门禁自身失灵（R7-TOOL-04
的「空扫描面恒绿」同族），按环境错误 exit 2，不放行。

用法：
    python scripts/check_workflow_shells.py                 # 门禁检查（CI/本地同口径）
    python scripts/check_workflow_shells.py --self-test     # 故障注入自证

退出码：0=通过 / 1=存在未断退出码的原生命令 / 2=环境错误（目录缺失、YAML 不可解析、
扫描面空转——环境错误绝不静默放行）。
"""
from __future__ import annotations

import argparse
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"
ACTIONS = ROOT / ".github" / "actions"

# pwsh 下以退出码表达成败、且不受 $ErrorActionPreference 约束的外部命令。
# R8-CI-03：补齐本仓实际使用而第七轮表里没有的命令（ruff/bandit/mypy/pip-audit/
# pytest/nm/readelf/unzip/tar/apktool/…），否则「命令表漏一项 = 门禁漏一处」。
NATIVE_RE = re.compile(
    r"^(cargo|rustc|rustup|dotnet|dotnet-cli|dotnet-ef|msbuild|nuget|vstest|"
    r"python|py|pip|pip3|pip-compile|pip-audit|ruff|bandit|mypy|pytest|"
    r"node|npm|npx|yarn|pnpm|signtool|make|cmake|ninja|gcc|clang|"
    r"choco|winget|curl|wget|gh|git|java|javac|keytool|apksigner|zipalign|adb|"
    r"mvn|gradle|gradlew|mvnw|7z|unzip|tar|iscc|innosetup|nm|readelf|objdump|"
    r"rsync|scp|ssh|bash|pwsh|powershell|cmd|call|apktool|flutter|xcodebuild)\b|"
    r"^\./",
    re.IGNORECASE,
)
# 调用运算符形态：`& "C:\path\tool.exe" args` / `& tool.exe`——R8-CI-03 第 3 项。
CALL_OPERATOR_RE = re.compile(r"^&\s*['\"]?[^'\"\s]+")
# 退出码处置标记（任一出现即视为该原生命令的成败已被判定）
HANDLED_RE = re.compile(r"\$LASTEXITCODE|\bthrow\b|\|\|\s*exit\b|\bexit\s+\$?[0-9P]\w*|"
                        r"\$PSNativeCommandUseErrorActionPreference")
# 排除误报：赋值右侧、`if (`/`} else {` 等控制流行本身不是原生命令调用
CONTROL_LINE_RE = re.compile(r"^\s*(if|elseif|else|foreach|while|switch|param|function)\b|"
                             r"^\s*[A-Za-z_][A-Za-z0-9_]*\s*=")
WINDOWS_RUNNER_RE = re.compile(r"windows", re.IGNORECASE)


class ShellGateError(RuntimeError):
    """环境错误（workflow 缺失/YAML 不可解析/扫描面空转）——不得计入'通过'。"""


def _code_lines(run: str) -> list[str]:
    """折反引号续行、丢纯注释行，返回可判定行（保留缩进无关的原文）。"""
    joined = run.replace("`", " ")
    out: list[str] = []
    for line in joined.splitlines():
        if line.lstrip().startswith("#"):
            continue
        out.append(line)
    return out


def _is_native(line: str) -> bool:
    if CONTROL_LINE_RE.match(line):
        return False
    stripped = line.strip()
    if CALL_OPERATOR_RE.match(stripped):
        return True
    return bool(NATIVE_RE.match(stripped))


def _job_default_shell(job: dict) -> str | None:
    """R8-CI-03 第 1 项：job 级默认 shell 的真实键路径是 defaults.run.shell。"""
    defaults = job.get("defaults")
    if isinstance(defaults, dict):
        run_defaults = defaults.get("run")
        if isinstance(run_defaults, dict) and isinstance(run_defaults.get("shell"), str):
            return run_defaults["shell"]
    # 兼容历史上写在 job 顶层的形态（Actions 不识别，但值存在时应继续受检）
    legacy = job.get("shell")
    return legacy if isinstance(legacy, str) else None


def _is_pwsh(shell: str | None) -> bool:
    return isinstance(shell, str) and ("pwsh" in shell.lower() or "powershell" in shell.lower())


def _step_violations(source: str, job: str, idx: int, name: str, run: str) -> list[str]:
    code = _code_lines(run)
    native_at = [i for i, ln in enumerate(code) if _is_native(ln)]
    if not native_at:
        return []
    out: list[str] = []
    for k, i in enumerate(native_at):
        if i == native_at[-1]:
            continue  # 末条原生命令：其退出码即步骤退出码
        upto = native_at[k + 1] if k + 1 < len(native_at) else len(code)
        tail = "\n".join(code[i + 1 : upto + 1])
        if not HANDLED_RE.search(tail):
            out.append(
                f"{source} :: {job} :: step {idx} '{name}' :: "
                f"pwsh 原生命令后未断退出码（其后仍有其他命令）: {code[i].strip()[:80]}"
            )
    return out


def _load(path: Path) -> dict:
    import yaml  # 延迟导入：环境错误由 run_check 归 2

    try:
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as exc:
        raise ShellGateError(f"YAML 解析失败: {path}: {exc}") from exc


def scan(workflow_dir: Path, actions_dir: Path | None = None) -> tuple[list[str], int, int]:
    """返回 (违规列表, pwsh 步骤数, windows job 数)——后两项供空面判定与锚点复用。

    扫描面：`workflow_dir/*.yml|*.yaml` 的 `jobs.*.steps`（含 job 级 defaults.run.shell
    与 windows runner 隐式 pwsh），以及 `actions_dir/*/action.yml` 的 `runs.steps`。
    """
    found: list[str] = []
    pwsh_steps = 0
    windows_jobs = 0

    for f in sorted(workflow_dir.glob("*.yml")) + sorted(workflow_dir.glob("*.yaml")):
        doc = _load(f)
        jobs = (doc or {}).get("jobs") or {}
        for job_name, job in jobs.items():
            if not isinstance(job, dict):
                continue
            job_shell = _job_default_shell(job)
            runs_on = job.get("runs-on")
            # R8-CI-03 第 2 项：windows runner 且未显式声明 shell ⇒ 默认 pwsh
            effective_job_shell = job_shell
            if effective_job_shell is None and isinstance(runs_on, str) and \
                    WINDOWS_RUNNER_RE.search(runs_on):
                effective_job_shell = "pwsh"
            if isinstance(runs_on, str) and WINDOWS_RUNNER_RE.search(runs_on):
                windows_jobs += 1
            for idx, step in enumerate(job.get("steps") or [], start=1):
                if not isinstance(step, dict) or not isinstance(step.get("run"), str):
                    continue
                shell = step.get("shell", effective_job_shell)
                if not isinstance(shell, str):
                    continue
                if not _is_pwsh(shell):
                    continue
                pwsh_steps += 1
                found += _step_violations(
                    f.name, job_name, idx, str(step.get("name") or "?"), step["run"])

    if actions_dir is not None and actions_dir.is_dir():
        # R8-CI-03 第 4 项：composite action（其默认 shell 是 bash，故只受检显式 pwsh）
        for action_file in sorted(actions_dir.glob("*/action.yml")):
            doc = _load(action_file)
            runs = doc.get("runs") or {}
            for idx, step in enumerate(runs.get("steps") or [], start=1):
                if not isinstance(step, dict) or not isinstance(step.get("run"), str):
                    continue
                if not _is_pwsh(step.get("shell")):
                    continue
                pwsh_steps += 1
                found += _step_violations(
                    action_file.parent.name, "composite", idx,
                    str(step.get("name") or "?"), step["run"])

    return found, pwsh_steps, windows_jobs


def violations(workflow_dir: Path, actions_dir: Path | None = None) -> list[str]:
    """返回违规描述列表（空 = 通过）。目录缺失/YAML 不可解析由调用方归 2。"""
    return scan(workflow_dir, actions_dir)[0]


def run_check(workflow_dir: Path = WORKFLOWS, actions_dir: Path | None = ACTIONS) -> int:
    if not workflow_dir.is_dir():
        print(f"❌ workflow 目录缺失：{workflow_dir}", file=sys.stderr)
        return 2
    try:
        import yaml  # noqa: F401  # 依赖预检：缺失属环境错误
    except ImportError as exc:  # pragma: no cover - 环境错误路径
        print(f"❌ 缺 pyyaml，无法解析 workflow：{exc}", file=sys.stderr)
        return 2
    try:
        found, pwsh_steps, windows_jobs = scan(workflow_dir, actions_dir)
    except ShellGateError as exc:
        print(f"❌ {exc}", file=sys.stderr)
        return 2
    # R8-CI-03：空扫描面不放行——windows job 在场却扫不到 pwsh 步骤，说明门禁
    # 自己失灵（键路径/默认 shell 推断再度漂移），与它要防的缺陷同型。
    if pwsh_steps == 0:
        print(f"❌ pwsh 步骤扫描面为空转（windows job {windows_jobs} 个，pwsh 步骤 0 个）"
              "——门禁自身失灵，须先修扫描面", file=sys.stderr)
        return 2
    if found:
        print(f"❌ pwsh 步骤退出码门禁失败（{len(found)} 处，扫描 {pwsh_steps} 个 pwsh 步骤 / "
              f"{windows_jobs} 个 windows job）：", file=sys.stderr)
        for item in found:
            print(f"  - {item}", file=sys.stderr)
        print("修复：在该原生命令后紧跟 if ($LASTEXITCODE -ne 0) { throw ... }，"
              "或把该步骤改 shell: bash（bash 侧有 set -eo pipefail）。", file=sys.stderr)
        return 1
    print(f"✅ pwsh 步骤退出码门禁通过（扫描 {pwsh_steps} 个 pwsh 步骤，"
          f"含 job 级 defaults 与 windows 隐式默认；{windows_jobs} 个 windows job）")
    return 0


def _planted_cases() -> list[tuple[str, dict, int]]:
    """(用例名, workflow/job 文档, 期望违规数)——每种第七轮扫描面漏掉的形态各一条。"""
    return [
        (
            "显式 shell: pwsh 中段失败",
            {"jobs": {"b": {"steps": [
                {"name": "n", "shell": "pwsh",
                 "run": "dotnet test a.csproj\ndotnet publish a.csproj\n"}]}}},
            1,
        ),
        (
            "job 级 defaults.run.shell: pwsh",
            {"jobs": {"b": {"defaults": {"run": {"shell": "pwsh"}}, "steps": [
                {"name": "n", "run": "cargo test\ncargo build\n"}]}}},
            1,
        ),
        (
            "windows runner 隐式默认 pwsh",
            {"jobs": {"b": {"runs-on": "windows-latest", "steps": [
                {"name": "n", "run": "pip install -r a.txt\npython selftest_x.py\n"}]}}},
            1,
        ),
        (
            "调用运算符 & \"tool.exe\"（后接另一条原生命令）",
            {"jobs": {"b": {"steps": [
                {"name": "n", "shell": "pwsh",
                 "run": "& \"C:\\Program Files\\signtool.exe\" sign a.pfx\n"
                        "iscc installer.iss\n"}]}}},
            1,
        ),
        (
            "工具链命令 ruff/bandit 同受检",
            {"jobs": {"b": {"steps": [
                {"name": "n", "shell": "pwsh",
                 "run": "ruff check .\nbandit -r app -q\n"}]}}},
            1,
        ),
        (
            "已断退出码不得误报",
            {"jobs": {"b": {"steps": [
                {"name": "n", "shell": "pwsh",
                 "run": "dotnet test a.csproj\n"
                        "if ($LASTEXITCODE -ne 0) { throw \"test failed\" }\n"
                        "dotnet publish a.csproj\n"}]}}},
            0,
        ),
        (
            "windows runner 显式 bash 不属本门禁",
            {"jobs": {"b": {"runs-on": "windows-latest", "steps": [
                {"name": "n", "shell": "bash", "run": "cargo test\ncargo build\n"}]}}},
            0,
        ),
    ]


def self_test() -> int:
    """故障注入自证：每种形态单独植入并断言被抓/不误报，且真实仓库必须为 0。"""
    import yaml

    real, real_steps, _ = scan(WORKFLOWS, ACTIONS)
    if real:
        print(f"❌ 自检失败：真实仓库存在 {len(real)} 处未断退出码的 pwsh 原生命令")
        for item in real:
            print(f"  - {item}")
        return 1
    if real_steps == 0:
        print("❌ 自检失败：真实仓库扫不到任何 pwsh 步骤")
        return 1

    failures: list[str] = []
    with tempfile.TemporaryDirectory() as td:
        for i, (label, doc, expected) in enumerate(_planted_cases()):
            case_dir = Path(td) / f"case{i}"
            case_dir.mkdir()
            (case_dir / "planted.yml").write_text(
                yaml.dump(doc, sort_keys=False), encoding="utf-8")
            found = violations(case_dir)
            if len(found) != expected:
                failures.append(f"{label}：期望 {expected} 处违规，实得 {len(found)}：{found}")

        # composite action 面也必须进扫描
        act_dir = Path(td) / "actions" / "plugged"
        act_dir.mkdir(parents=True)
        (act_dir / "action.yml").write_text(yaml.dump(
            {"runs": {"using": "composite", "steps": [
                {"name": "n", "shell": "pwsh",
                 "run": "dotnet test a.csproj\ndotnet build a.csproj\n"}]}},
            sort_keys=False), encoding="utf-8")
        empty_wf = Path(td) / "wf"
        empty_wf.mkdir()
        found = violations(empty_wf, Path(td) / "actions")
        if len(found) != 1:
            failures.append(f"composite action 面：期望 1 处违规，实得 {len(found)}：{found}")

    if failures:
        print("❌ 自检失败（故障注入未达预期）：", file=sys.stderr)
        for item in failures:
            print(f"  - {item}", file=sys.stderr)
        return 1
    print(f"✅ 自检通过：{len(_planted_cases())} 种步骤形态 + composite 面逐个验证，"
          f"真实仓库 {real_steps} 个 pwsh 步骤零违规")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="pwsh 步骤原生命令退出码门禁（R7-TOOL-01 / R8-CI-03）")
    parser.add_argument("--self-test", action="store_true",
                        help="故障注入自证：每种形态植入违规必须被抓到")
    parser.add_argument("--workflows", default=str(WORKFLOWS),
                        help="workflow 目录（默认 .github/workflows）")
    parser.add_argument("--actions", default=str(ACTIONS),
                        help="composite action 目录（默认 .github/actions）")
    args = parser.parse_args(argv)
    if args.self_test:
        return self_test()
    return run_check(Path(args.workflows), Path(args.actions))


if __name__ == "__main__":
    raise SystemExit(main())

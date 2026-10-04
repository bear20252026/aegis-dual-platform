#!/usr/bin/env python3
"""check_workflow_shells.py —— R7-TOOL-01（第七轮审计 2026-10-04）：pwsh 步骤退出码门禁。

背景：`shell: pwsh` 的 GitHub Actions 步骤把 `$ErrorActionPreference` 设为 `stop`，
但该偏好**只约束 cmdlet 错误**——原生命令（cargo/dotnet/python/...）非零退出既不中断
脚本，也不产生 PowerShell 错误（`$PSNativeCommandUseErrorActionPreference` 在 PS 7.3
引入时仍标 experimental，Actions 包装脚本不设置它）。于是步骤退出码取自**末条**原生
命令：第六轮的 `release-windows.yml` 里 `dotnet test` 之后紧跟 `dotnet publish`，
测试红 + 构建绿 ⇒ 步骤绿 ⇒ 正典安装包照常产出。同类实例共 3 处，已逐条补
`if ($LASTEXITCODE -ne 0) { throw }`。

本脚本把该口径固化为门禁（防回归），判定规则：

- 扫描全部 `.github/workflows/*.yml` 中显式 `shell: pwsh` 的步骤；
- 取其 `run` 脚本，剔除纯注释行与反引号续行折行；
- 识别「原生命令行」（首 token 命中命令表，且不在 `if (...) {` 之类的表达式位）；
- 任一原生命令**不是**块内最后一条原生命令时，它与下一条原生命令之间（或到块尾）
  必须出现退出码处置：`$LASTEXITCODE` / `throw` / `exit` / `|| exit` /
  `$PSNativeCommandUseErrorActionPreference`。缺失即违规。

用法：
    python scripts/check_workflow_shells.py                 # 门禁检查（CI/本地同口径）
    python scripts/check_workflow_shells.py --self-test     # 故障注入自证（见下）

退出码：0=通过 / 1=存在未断退出码的原生命令 / 2=环境错误（workflow 目录缺失、
YAML 解析失败——环境错误绝不静默放行）。

`--self-test` 是本仓「门禁必须能失败」口径的落实：在临时目录植入一个「测试后接
构建」的 pwsh 步骤，断言扫描器判 1 违规，并断言真实仓库判 0。缺了这一步，
扫描器写错（例如正则永不匹配）时门禁恒绿，与它要防的缺陷同型。
"""
from __future__ import annotations

import argparse
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"

# pwsh 下以退出码表达成败、且不受 $ErrorActionPreference 约束的外部命令
NATIVE_RE = re.compile(
    r"^(cargo|dotnet|python|pip|node|npm|npx|yarn|pnpm|signtool|make|msbuild|dotnet-cli|"
    r"choco|curl|wget|gh|git|java|mvn|gradle|7z|iscc|innosetup|rsync|scp|ssh|"
    r"\./gradlew|\./mvnw)\b",
    re.IGNORECASE,
)
# 退出码处置标记（任一出现即视为该原生命令的成败已被判定）
HANDLED_RE = re.compile(r"\$LASTEXITCODE|\bthrow\b|\|\|\s*exit\b|\bexit\s+\$?[0-9P]\w*|"
                        r"\$PSNativeCommandUseErrorActionPreference")
# 排除误报：赋值右侧、`if (`/`} else {` 等控制流行本身不是原生命令调用
CONTROL_LINE_RE = re.compile(r"^\s*(if|elseif|else|foreach|while|switch|param|function)\b|"
                             r"^\s*[A-Za-z_][A-Za-z0-9_]*\s*=")


def _code_lines(run: str) -> list[str]:
    """折反引号续行、丢纯注释行，返回可判定行（保留缩进无关的原文）。"""
    joined = run.replace("`", " ")
    out: list[str] = []
    for line in joined.splitlines():
        if line.lstrip().startswith("#"):
            continue
        out.append(line)
    return out


def violations(workflow_dir: Path) -> list[str]:
    """返回违规描述列表（空 = 通过）。目录缺失/YAML 不可解析由调用方归 2。"""
    found: list[str] = []
    for f in sorted(workflow_dir.glob("*.yml")) + sorted(workflow_dir.glob("*.yaml")):
        import yaml  # 延迟导入：环境错误由 run_check 归 2

        try:
            doc = yaml.safe_load(f.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError) as exc:
            raise ShellGateError(f"workflow YAML 解析失败: {f.name}: {exc}") from exc
        jobs = (doc or {}).get("jobs") or {}
        for job_name, job in jobs.items():
            if not isinstance(job, dict):
                continue
            job_shell = job.get("shell")
            for idx, step in enumerate(job.get("steps") or [], start=1):
                if not isinstance(step, dict):
                    continue
                shell = step.get("shell", job_shell)
                run = step.get("run")
                if not isinstance(run, str) or not isinstance(shell, str):
                    continue
                if "pwsh" not in shell.lower() and "powershell" not in shell.lower():
                    continue
                found += _step_violations(f.name, job_name, idx, step.get("name") or "?", run)
    return found


class ShellGateError(RuntimeError):
    """环境错误（workflow 缺失/YAML 不可解析）——不得计入'通过'。"""


def _step_violations(fname: str, job: str, idx: int, name: str, run: str) -> list[str]:
    code = _code_lines(run)
    native_at = [i for i, ln in enumerate(code)
                 if not CONTROL_LINE_RE.match(ln) and NATIVE_RE.match(ln.strip())]
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
                f"{fname} :: {job} :: step {idx} '{name}' :: "
                f"pwsh 原生命令后未断退出码（其后仍有其他命令）: {code[i].strip()[:80]}"
            )
    return out


def run_check(workflow_dir: Path = WORKFLOWS) -> int:
    if not workflow_dir.is_dir():
        print(f"❌ workflow 目录缺失：{workflow_dir}", file=sys.stderr)
        return 2
    try:
        import yaml  # noqa: F401  # 依赖预检：缺失属环境错误
    except ImportError as exc:  # pragma: no cover - 环境错误路径
        print(f"❌ 缺 pyyaml，无法解析 workflow：{exc}", file=sys.stderr)
        return 2
    try:
        found = violations(workflow_dir)
    except ShellGateError as exc:
        print(f"❌ {exc}", file=sys.stderr)
        return 2
    if found:
        print(f"❌ pwsh 步骤退出码门禁失败（{len(found)} 处）：", file=sys.stderr)
        for item in found:
            print(f"  - {item}", file=sys.stderr)
        print("修复：在该原生命令后紧跟 if ($LASTEXITCODE -ne 0) { throw ... }，"
              "或把该步骤改 shell: bash（bash 侧有 set -eo pipefail）。", file=sys.stderr)
        return 1
    n = len(list(workflow_dir.glob("*.yml"))) + len(list(workflow_dir.glob("*.yaml")))
    print(f"✅ pwsh 步骤退出码门禁通过（扫描 {n} 个 workflow）")
    return 0


def self_test() -> int:
    """故障注入自证：植入违规必须被抓到，真实仓库必须为 0。"""
    import yaml

    real = violations(WORKFLOWS)
    if real:
        print(f"❌ 自检失败：真实仓库存在 {len(real)} 处未断退出码的 pwsh 原生命令")
        for item in real:
            print(f"  - {item}")
        return 1
    with tempfile.TemporaryDirectory() as td:
        bad = Path(td) / "wf"
        bad.mkdir()
        planted = {
            "jobs": {"build": {"steps": [
                {"name": "test then publish", "shell": "pwsh",
                 "run": "dotnet test a.csproj\ndotnet publish a.csproj\n"},
                {"name": "guarded", "shell": "pwsh",
                 "run": "dotnet test a.csproj\n"
                        "if ($LASTEXITCODE -ne 0) { throw \"test failed\" }\n"
                        "dotnet publish a.csproj\n"},
            ]}}
        }
        (bad / "planted.yml").write_text(
            yaml.dump(planted, sort_keys=False), encoding="utf-8")
        found = violations(bad)
    if len(found) != 1:
        print(f"❌ 自检失败：植入 1 处违规应恰好抓到 1 处，实得 {len(found)}：{found}",
              file=sys.stderr)
        return 1
    print("✅ 自检通过：植入的未断退出码步骤被抓到；已加 $LASTEXITCODE 断言的步骤未误报")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="pwsh 步骤原生命令退出码门禁（R7-TOOL-01）")
    parser.add_argument("--self-test", action="store_true",
                        help="故障注入自证：植入违规必须被抓到")
    parser.add_argument("--workflows", default=str(WORKFLOWS),
                        help="workflow 目录（默认 .github/workflows）")
    args = parser.parse_args(argv)
    if args.self_test:
        return self_test()
    return run_check(Path(args.workflows))


if __name__ == "__main__":
    raise SystemExit(main())

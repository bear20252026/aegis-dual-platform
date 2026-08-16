#!/usr/bin/env python3
"""bootstrap-dev-environment —— 蓝图 scripts/bootstrap-dev-environment。

开发环境引导：检查 .NET 10（Windows 壳——阶段 C）、Rust cargo（core——阶段 F）、
Python 3.12（contracts/codegen/agent 测试）。环境不满足时输出修复指引。
"""

from __future__ import annotations

import shutil
import subprocess
import sys


def _check(tool: str, version_cmd: list[str]) -> tuple[bool, str]:
    exe = shutil.which(tool)
    if exe is None:
        return False, f"{tool} 未安装"
    try:
        out = subprocess.run(version_cmd, capture_output=True, text=True, timeout=15)
        return True, out.stdout.strip().splitlines()[0] if out.stdout else f"{tool} 可用"
    except Exception as e:
        return False, f"{tool} 检查失败: {e}"


def main() -> int:
    print("=== Aegis 开发环境引导（蓝图 scripts/bootstrap-dev-environment）===")
    checks = [
        ("dotnet", ["dotnet", "--version"], ".NET 10（Windows 壳——dotnet build）"),
        ("cargo", ["cargo", "--version"], "Rust（core/rust-policy-core——cargo test）"),
        ("python", [sys.executable, "--version"], "Python 3.12（contracts/codegen + agent 测试）"),
    ]
    ok = True
    for tool, cmd, note in checks:
        passed, detail = _check(tool, cmd)
        print(f"  {'✅' if passed else '❌'} {tool}: {detail}（{note}）")
        ok = ok and passed
    print("环境检查完成——全部就绪" if ok else "环境不完整——按提示安装缺失工具")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())

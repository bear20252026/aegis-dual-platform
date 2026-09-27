#!/usr/bin/env python3
"""bootstrap-dev-environment —— 蓝图 scripts/bootstrap-dev-environment。

开发环境引导：检查 .NET 10（Windows 壳——阶段 C）、Rust cargo（core——阶段 F）、
Python 3.12（contracts/codegen/agent 测试）。环境不满足时输出修复指引。
"""

from __future__ import annotations

import shutil
import subprocess
import sys

# PY-201（2026-09-26 审计）：Python 最低版本单源（此前注释声称 3.12 而实际
# 不校验版本——检查错位）
MIN_PYTHON = (3, 12)


def _check(tool: str, version_cmd: list[str]) -> tuple[bool, str]:
    exe = shutil.which(tool)
    if exe is None:
        return False, f"{tool} 未安装"
    try:
        out = subprocess.run(version_cmd, capture_output=True, text=True, timeout=15, check=False)
        return True, out.stdout.strip().splitlines()[0] if out.stdout else f"{tool} 可用"
    except (subprocess.SubprocessError, OSError) as e:
        return False, f"{tool} 检查失败: {e}"


def _check_python() -> tuple[bool, str]:
    """统一对 sys.executable 做 which + 版本断言（PY-201）。

    此前 _check("python") 用 shutil.which("python") 判存在、却运行
    sys.executable——PATH 上的 python 与实际解释器可能是两个东西；且只跑
    --version 展示、从不校验 >= 3.12。现修正：① which 直接定位
    sys.executable（真实解释器）；② 以 sys.version_info 断言 >= (3, 12)。
    """
    exe = shutil.which(sys.executable)
    if exe is None:
        return False, f"当前解释器不可定位: {sys.executable}"
    major, minor, micro = sys.version_info[:3]
    label = f"Python {major}.{minor}.{micro}"
    if (major, minor) < MIN_PYTHON:
        return False, f"{label}（{exe}）——低于要求的 >= {MIN_PYTHON[0]}.{MIN_PYTHON[1]}"
    return True, f"{label}（{exe}）"


def main() -> int:
    print("=== Aegis 开发环境引导（蓝图 scripts/bootstrap-dev-environment）===")
    checks = [
        ("dotnet", ["dotnet", "--version"], ".NET 10（Windows 壳——dotnet build）"),
        ("cargo", ["cargo", "--version"], "Rust（core/rust-policy-core——cargo test）"),
        # SP-036（审计 2026-09-23 清单·SP1 批）：补 Node.js 检查——
        # node --test UI 回归门禁此前不在引导面（漏检）
        ("node", ["node", "--version"], "Node.js >= 21（tests/ui-regression——node --test glob）"),
    ]
    # SP-082（审计 2026-09-23 清单·SP1 批）：可选工具检查（缺失不阻断——
    # 仅发布打包需要；ISCC = Inno Setup 编译器，release-windows 云端打包用）
    optional_checks = [
        ("ISCC", ["ISCC", "/?"], "Inno Setup（仅本地出包需要——CI 云端已内置）"),
    ]
    ok = True
    for tool, cmd, note in checks:
        passed, detail = _check(tool, cmd)
        print(f"  {'✅' if passed else '❌'} {tool}: {detail}（{note}）")
        ok = ok and passed
    for tool, cmd, note in optional_checks:
        passed, detail = _check(tool, cmd)
        print(f"  {'✅' if passed else '⚪ 可选'} {tool}: {detail}（{note}）")
    # PY-201：Python 行不再复用 _check("python", ...)——统一走 _check_python
    passed, detail = _check_python()
    print(f"  {'✅' if passed else '❌'} python: {detail}"
          f"（Python >= {MIN_PYTHON[0]}.{MIN_PYTHON[1]}——contracts/codegen + agent 测试）")
    ok = ok and passed
    # SP-081（审计 2026-09-23 清单·SP1 批）：失败附安装入口指引——此前仅
    # 一句"按提示安装"无落点
    if not ok:
        print(
            "环境不完整——安装指引：\n"
            "  · dotnet  → https://dotnet.microsoft.com/download（.NET 10 SDK）\n"
            "  · cargo   → https://rustup.rs\n"
            "  · node    → https://nodejs.org（LTS >= 21，启用 node --test glob）\n"
            "  · python  → https://www.python.org/downloads/（>= 3.12）")
        return 1
    print("环境检查完成——全部就绪")
    return 0


if __name__ == "__main__":
    sys.exit(main())

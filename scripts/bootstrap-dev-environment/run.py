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
# PY-233（2026-10-01 审计）：dotnet/node 此前只验存在不验版本下限——
# .NET 10 / Node 21 是构建面真实约束（dotnet build / node --test glob），
# 版本不足时工具存在但构建必失败。下限与注释口径对齐（cargo 无对应
# 门禁约束，保持只验存在——如需下限在此追加）。
MIN_DOTNET = (10,)
MIN_NODE = (21,)


def _version_floor_ok(first_line: str, floor: tuple[int, ...]) -> bool:
    """版本输出首行（如 '10.0.100'/'v21.7.0'）按数字段与下限比较。

    解析首段数字序列做逐段比较：任一高位段已超下限即通过，同位相等则
    比下一位。无法解析任何数字段时按不达标处理（fail-closed——版本
    不可判定的工具不可信）。
    """
    import re as _re
    segments = tuple(int(s) for s in _re.findall(r"\d+", first_line))
    if not segments:
        return False
    for have, want in zip(segments, floor):
        if have != want:
            return have > want
    # 前导段全相等（或输出段数少于下限段数）——已比到的段不低即达标
    return True


def _check(tool: str, version_cmd: list[str],
           floor: tuple[int, ...] | None = None) -> tuple[bool, str]:
    """存在性 + 版本下限双检查（PY-233：floor 非 None 时校验下限）。"""
    exe = shutil.which(tool)
    if exe is None:
        return False, f"{tool} 未安装"
    try:
        out = subprocess.run(version_cmd, capture_output=True, text=True, timeout=15, check=False)
    except (subprocess.SubprocessError, OSError) as e:
        return False, f"{tool} 检查失败: {e}"
    first = out.stdout.strip().splitlines()[0] if out.stdout else ""
    if floor is not None and not _version_floor_ok(first, floor):
        return False, f"{first or '（无版本输出）'}——低于要求的 >= {'.'.join(map(str, floor))}"
    return True, first if first else f"{tool} 可用"


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
        ("dotnet", ["dotnet", "--version"], ".NET 10（Windows 壳——dotnet build）", MIN_DOTNET),
        ("cargo", ["cargo", "--version"], "Rust（core/rust-policy-core——cargo test）", None),
        # SP-036（审计 2026-09-23 清单·SP1 批）：补 Node.js 检查——
        # node --test UI 回归门禁此前不在引导面（漏检）
        # PY-233：注释口径 ">= 21" 落为版本下限断言（此前只验存在）
        ("node", ["node", "--version"], "Node.js >= 21（tests/ui-regression——node --test glob）", MIN_NODE),
    ]
    # SP-082（审计 2026-09-23 清单·SP1 批）：可选工具检查（缺失不阻断——
    # 仅发布打包需要；ISCC = Inno Setup 编译器，release-windows 云端打包用）
    optional_checks = [
        ("ISCC", ["ISCC", "/?"], "Inno Setup（仅本地出包需要——CI 云端已内置）"),
    ]
    ok = True
    for tool, cmd, note, floor in checks:
        passed, detail = _check(tool, cmd, floor)
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

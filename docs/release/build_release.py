#!/usr/bin/env python
"""build_release.py —— Aegis 发布期构建脚本（B1 混淆隔离实施，骨架）。

发布期实施产物（docs/release/——不触碰开发分支 windows/aegis_source/）。
基于全球调研（PyArmor 官方 CI + Nuitka 官方 --module + GitHub #2049 实际命令）：
- 核心敏感模块 → Nuitka 编译（.pyd——编译级保护）
- 其余模块 → PyArmor 混淆（--enable-rft 源级 + --exclude 核心避免双重处理）
- dist/ 产物与 src/ 源码物理隔离（发布期——开发分支 master 永远源码）

用法（发布期，在 master-obf 分支/独立发布环境执行）：
    python docs/release/build_release.py
产物：dist/core/*.pyd + dist/obfuscated/*（组装后交 sign job 签名）
"""

import subprocess
import sys
from pathlib import Path

# 核心敏感模块（Nuitka 编译——.pyd 编译级保护）
CORE_MODULES = [
    "app/security.py",
    "app/credential_guard.py",
    "app/threat_feed.py",
    "app/mcp.py",
]
# PyArmor 混淆排除（避免核心模块被双重处理）
EXCLUDE_CORE = [f"app/{Path(m).stem}" for m in CORE_MODULES]

ROOT = Path(__file__).resolve().parents[2]  # 仓库根（aegis_dual_platform）
DIST = ROOT / "dist"


def run(cmd: list[str]) -> None:
    print(f"==> {' '.join(cmd)}")
    subprocess.run(cmd, cwd=ROOT, check=True)


def main() -> int:
    """两步构建：Nuitka 编译核心 + PyArmor 混淆其余 + dist 组装。"""
    (DIST / "core").mkdir(parents=True, exist_ok=True)
    (DIST / "obfuscated").mkdir(parents=True, exist_ok=True)

    # 步骤 0：PyArmor 兼容配置（与 Nuitka 组合——GitHub #2049 确认）
    run(["pyarmor", "cfg", "restrict_module", "0"])

    # 步骤 1：Nuitka 编译核心敏感模块（.pyd——编译级保护）
    for mod in CORE_MODULES:
        run(["python", "-m", "nuitka", "--module", mod,
             f"--output-dir={DIST / 'core'}"])

    # 步骤 2：PyArmor 混淆其余模块（--enable-rft 源级 + --exclude 核心）
    excludes = [f"--exclude={e}" for e in EXCLUDE_CORE]
    run(["pyarmor", "gen", "--enable-rft", *excludes,
         f"-O{DIST / 'obfuscated'}", "app/", "main_webview.py"])

    print("==> B1 发布期构建完成：dist/core/*.pyd + dist/obfuscated/*")
    print("==> 产物交 sign job 签名（B2）——见 docs/release/release.yml")
    return 0


if __name__ == "__main__":
    sys.exit(main())

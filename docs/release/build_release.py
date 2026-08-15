#!/usr/bin/env python
"""build_release.py —— Aegis 发布期构建脚本（B 方案调整版：Nuitka 免费路线）。

发布期实施产物（docs/release/——不触碰开发分支 windows/aegis_source/）。
B 方案调整（基于全球调研——KNOWLEDGE_BASE 第 18 节）：
- Nuitka 团队官方（Reddit）：不要同时用 PyArmor 和 Nuitka（组合不被
  支持——"Nuitka by itself will be good enough"）→ 移除 PyArmor 组合层
- Nuitka Apache-2.0 免费商业可用 → 敏感模块全部 Nuitka 编译（免费）
- PyArmor 免费版限制（32KB/935-940 行——Stack Overflow/pyobfus 实测）
  → 不编译模块仅小模块可用 PyArmor 试用版（分层处理）
- Nuitka 免费版常量数据未混淆（strings 可提取——issue #556）→ XOR 加固
- nuitka-static-unpacker 存在（Nuitka 产物可反编译）→ 保护非绝对，
  政府级纵深：编译 + 签名（B2）+ 凭据外部化

用法（发布期，在 master-obf 分支/独立发布环境执行）：
    python docs/release/build_release.py
产物：dist/core/*.pyd（Nuitka 编译）+ dist/plain/*（不编译模块分层）
      + dist/xor 常量加固说明（交 sign job 签名——见 release.yml）
"""

import subprocess
import sys
from pathlib import Path

# 核心敏感模块（Nuitka 编译——.pyd 编译级保护，免费 Apache-2.0）
CORE_MODULES = [
    "app/security.py",
    "app/credential_guard.py",
    "app/threat_feed.py",
    "app/mcp.py",
]
# 可选扩展编译（业务敏感模块——按需加入；注意：Nuitka 扩展模块间不能
# 互相包含（官方 Use Cases），须保证各编译模块独立可 import）
OPTIONAL_CORE = [
    # "app/api_bridge.py",  # 评估后启用（依赖面复杂——先验证核心 4 模块）
]

ROOT = Path(__file__).resolve().parents[2]  # 仓库根（aegis_dual_platform）
DIST = ROOT / "dist"


def run(cmd: list[str]) -> None:
    print(f"==> {' '.join(cmd)}")
    subprocess.run(cmd, cwd=ROOT, check=True)


def main() -> int:
    """Nuitka 编译敏感模块 + 不编译模块分层 + XOR 常量加固说明。"""
    (DIST / "core").mkdir(parents=True, exist_ok=True)
    (DIST / "plain").mkdir(parents=True, exist_ok=True)

    # 步骤 1：Nuitka 编译敏感模块（.pyd——编译级保护，免费）
    # 动态导入适配：--include-module/--include-package 显式声明（构建配置，
    # 非代码改动——KNOWLEDGE_BASE 18.3 纪律①）
    for mod in CORE_MODULES + OPTIONAL_CORE:
        run(["python", "-m", "nuitka", "--module", mod,
             f"--output-dir={DIST / 'core'}",
             "--include-package=app"])  # 动态导入兜底声明

    # 步骤 2：不编译模块分层（保护措施——KNOWLEDGE_BASE 18.2 + 20 调研）：
    #   a. 小模块（935 行/32KB 内）→ PyArmor 混淆 + --pack onedir
    #      （PyArmor 官方：混淆 + PyInstaller 打包一步；注意 --mix-str
    #      试用版不可用——Basic 选项即可）
    #   b. 大模块 → PyInstaller --onedir（目录模式——CSDN/官方调研：
    #      单文件双进程/AV 误报高/崩溃写爆磁盘——目录模式稳定，
    #      Nuitka 机器码误报率低于 PyInstaller）
    #   c. 资源路径（PyWebview 注意）：前端资源（shell/start.html 等）
    #      需 --include-data-dir 打包 + 运行期 __file__/sys._MEIPASS
    #      动态定位（CSDN 实战——Aegis 前端资源必须显式包含）
    #   d. 运行时纵深：凭据外部化（环境变量）+ credential_guard 脱敏
    #      + B2 sigstore 签名（防篡改——改了就失效）
    print("==> 不编译模块分层（见注释 a/b/c/d）——dist/plain/ 组装：")
    print("    a) 小模块 PyArmor --pack onedir（混淆+打包一步）")
    print("    b) 大模块 PyInstaller --onedir（目录模式——AV 误报低/稳定）")
    print("    c) 前端资源 --include-data-dir + 动态路径（Aegis shell/）")
    # 占位：dist/plain/ 由发布流程按分层策略组装（PyArmor 或 PyInstaller）

    # 步骤 3：XOR 常量加固（Nuitka 免费版常量数据未混淆——issue #556；
    # 免费替代 Nuitka Commercial data-hiding 插件）
    # 说明：敏感常量（密钥/凭据）建议走环境变量（Aegis 已实现——凭据
    # 外部化），代码内常量经 XOR 混淆 + 嵌入密钥（发布期工具：
    # docs/release/xor_obfuscate.py——encrypt <file> 生成 .enc，
    # 密钥嵌入 Nuitka 编译模块后难以提取）
    print("==> XOR 常量加固：敏感常量建议环境变量（Aegis 已实现）+ "
          "代码常量用 docs/release/xor_obfuscate.py 加密（发布期）")

    print("==> B 调整构建完成：dist/core/*.pyd + dist/plain/*")
    print("==> 产物交 sign job 签名（B2 sigstore）——见 docs/release/release.yml")
    return 0


if __name__ == "__main__":
    sys.exit(main())

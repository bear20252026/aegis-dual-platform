# ruff: noqa: BLE001 —— 验证脚本捕获文件/JSON/XML 解析异常是设计性盲捕
#（政府级：验证脚本须报告一切解析失败，不因异常类型收窄而漏报）
# S-06 整改（国防级审查）：本脚本为开发期快速检查（AST/JSON/XML 语法）；
# 发布期实际验证（build/测试/SBOM/签名/provenance 对账）由 release.yml
# verify job 覆盖（B0-S 整改——docs/release/release.yml fail-closed）

from __future__ import annotations

import ast
import json
import re
import sys
from pathlib import Path

# S1-6 修复（H1）：此前硬编码打包机路径 /home/ubuntu/aegis_dual_platform，
# 在任意其他机器上运行必然 FileNotFoundError。改为基于本文件位置的
# 相对路径，跨平台可移植（Windows/Linux/macOS 均生效）。
ROOT = Path(__file__).resolve().parent


# ABC 级闭环（B3 依赖 hash 锁定）：锁文件门禁——requirements-lock.txt 必须
# 存在且含 hash（pip-compile --generate-hashes 生成——可复现安装前提——
# 张显达实践：改依赖未更新锁文件 → 直接失败）
# PY-123（审计 2026-09-25）：抽函数化——原为模块级内联代码不可单测
def check_lock_file(windows_dir: Path) -> list[str]:
    problems: list[str] = []
    lock_file = windows_dir / 'requirements-lock.txt'
    if not lock_file.is_file():
        problems.append('缺 requirements-lock.txt（pip-compile --generate-hashes 生成）')
    elif '--hash=' not in lock_file.read_text(encoding='utf-8'):
        problems.append('requirements-lock.txt 无 hash（--generate-hashes 重新生成）')
    return problems


# PY-124（审计 2026-09-25）：C# 关键文件断言抽函数化——单测可直接对
# 合成目录树断言，不必依赖真实仓库布局
def check_required_cs_files(csproj: Path) -> list[str]:
    problems: list[str] = []
    if not csproj.is_file():
        problems.append('缺正典 C# 工程 windows/src/Aegis.Windows.App/Aegis.Windows.App.csproj')
        return problems
    cs_root = csproj.parent
    required_cs = [
        'App.xaml.cs',
        'Chrome/MainWindow.xaml',
        'Chrome/MainWindow.xaml.cs',
        'Broker/BrowserPolicyBroker.cs',
        'WebView/HostWebView.cs',
    ]
    for rel in required_cs:
        if not (cs_root / rel).is_file():
            problems.append(f'缺 C# 关键文件 windows/src/Aegis.Windows.App/{rel}')
    return problems


# SP-166（2026-09-26 审计）：shared/shell 单源清单与实际文件对账。
# WB-103（2026-09-26 审计）：已接线到 main()——manifest.txt 四张壁纸补齐后
# 差集为空，门禁生效（此前仅登记 1 张壁纸时接线即红，故 PY 批暂缓）。
def check_shell_manifest_consistency(root: Path) -> list[str]:
    """shared/shell/manifest.txt 与 shared/shell 实际文件差集非空即 fail。

    排除 manifest.txt 自身（清单本体）与 snake.test.js（测试桩，非发布资产）。
    """
    problems: list[str] = []
    shell_dir = root / 'shared' / 'shell'
    manifest_path = shell_dir / 'manifest.txt'
    if not manifest_path.is_file():
        problems.append('缺跨端资产清单 shared/shell/manifest.txt')
        return problems
    listed = {
        line.strip()
        for line in manifest_path.read_text(encoding='utf-8').splitlines()
        if line.strip() and not line.strip().startswith('#')
    }
    actual = {
        p.relative_to(shell_dir).as_posix()
        for p in shell_dir.rglob('*')
        if p.is_file()
        and p.name != 'manifest.txt'
        and p.name != 'snake.test.js'
    }
    for missing in sorted(actual - listed):
        problems.append(f'shared/shell 实际文件未登记 manifest.txt: {missing}')
    for ghost in sorted(listed - actual):
        problems.append(f'manifest.txt 登记的文件不存在: shared/shell/{ghost}')
    return problems


# WB-054（审计 2026-09-23 清单·W5 批）：csproj 的 shared/shell Content 打包
# 必须显式排除 snake.test.js——排除声明被拆掉时测试桩（约 470 行 JS）会随
# MSIX/发布产物进入 ntp 虚拟主机（Android 侧对应排除由 build.gradle.kts
# 锁定，WB-115）。此处按「shell 通配 Include 行须携带 snake.test.js 排除」
# 断言，排除声明缺失/改形即 fail-closed。
def check_csproj_shell_test_excluded(csproj: Path) -> list[str]:
    problems: list[str] = []
    if not csproj.is_file():
        return problems  # csproj 缺失已由 check_required_cs_files 报告
    text = csproj.read_text(encoding='utf-8')
    shell_includes = re.findall(
        r'<Content\s+Include="[^"]*shared\\shell\\[^"]*"[^>]*>', text)
    if not shell_includes:
        problems.append('csproj 缺 shared\\shell 单源资产 Content 打包声明')
        return problems
    for inc in shell_includes:
        if not re.search(r'Exclude="[^"]*snake\.test\.js[^"]*"', inc):
            problems.append(
                'csproj 的 shared\\shell Content 打包必须排除 snake.test.js'
                '（测试桩不得随包进入 ntp 虚拟主机）——WB-054')
    return problems


# PY-123/124 配套（审计 2026-09-25）：主流程包进 main()——原模块级
# raise SystemExit 在 pytest 收集 import 时直接退出（INTERNALERROR），
# 单测无法导入本模块
def main() -> int:
    failures: list[str] = []
    root = ROOT
    windows = root / 'legacy' / 'windows-pywebview'
    python_files = list(windows.rglob('*.py'))
    # PY-037：AST 语法检查仅覆盖 legacy 子树——scripts/contracts/release 三个
    # 活跃 Python 目录（CI 门禁与发布链路的实际执行方）此前零语法检查
    # SP-165（2026-09-26 审计）：元组补 'agent'——ruff 门禁面含 agent，两门
    # 禁口径此前不一（agent/ 零 AST 语法检查）
    for scan_dir in ('scripts', 'contracts', 'release', 'agent'):
        python_files.extend((root / scan_dir).rglob('*.py'))
    for path in python_files:
        try:
            ast.parse(path.read_text(encoding='utf-8'), filename=str(path))
        except Exception as exc:  # noqa: BLE001（验证脚本盲捕是设计）
            failures.append(f'Python {path.relative_to(root)}: {exc}')
    try:
        json.loads((root / 'shared' / 'release.json').read_text(encoding='utf-8'))
    except Exception as exc:  # noqa: BLE001（验证脚本盲捕是设计）
        failures.append(f'JSON shared/release.json: {exc}')
    # SP-166（2026-09-26 审计）：MSIX/appinstaller 路线模板（*.template）已
    # 确认死资产后删除（此前全仓仅退役 PyInstaller 管线 build-windows.ps1
    # 引用——该脚本本身引用的 windows/aegis_source 目录已不存在）；PY-160
    # （2026-09-23 审计·V1 核验批）将 build-windows.ps1 一并删除，退役
    # PyInstaller/MSIX 打包链至此无残留。模板校验不再有任何可校验对象。
    if (windows / 'aegis_webview.nsi').exists():
        failures.append('Deprecated NSIS script still exists in the Windows working copy')
    failures.extend(check_lock_file(windows))

    # 审计修复：正典 C# 栈存在性断言（此前脚本只看 legacy 栈——C# 代码不经
    # 任何检查；发布资源断言在 release-windows.yml，这里是仓库级快速门禁）
    csproj = root / 'windows' / 'src' / 'Aegis.Windows.App' / 'Aegis.Windows.App.csproj'
    failures.extend(check_required_cs_files(csproj))
    # WB-054（审计 2026-09-23 清单·W5 批）：csproj 排除 snake.test.js 断言
    failures.extend(check_csproj_shell_test_excluded(csproj))
    # PY-038：资产清单与 release-windows.yml 平行维护（改一处漏一处）——
    # 抽 shared/shell/manifest.txt 共享单源，两处共同消费
    shell_manifest = root / 'shared' / 'shell' / 'manifest.txt'
    if not shell_manifest.is_file():
        failures.append('缺跨端资产清单 shared/shell/manifest.txt')
    else:
        shell_assets = [
            line.strip()
            for line in shell_manifest.read_text(encoding='utf-8').splitlines()
            if line.strip() and not line.strip().startswith('#')
        ]
        for shell_asset in shell_assets:
            if not (root / 'shared' / 'shell' / shell_asset).is_file():
                failures.append(f'缺跨端单源首页资产 shared/shell/{shell_asset}')
    # SP-166 + WB-103（2026-09-26 审计）：清单差集对账接线——manifest.txt
    # 漏登记（如壁纸只列 1/4）或登记幽灵文件均 fail-closed
    failures.extend(check_shell_manifest_consistency(root))
    print(f'python_files={len(python_files)}')
    print(f'failures={len(failures)}')
    for failure in failures:
        print(failure)
    return 1 if failures else 0


if __name__ == '__main__':
    sys.exit(main())

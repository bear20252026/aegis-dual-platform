# ruff: noqa: BLE001 —— 验证脚本捕获文件/JSON/XML 解析异常是设计性盲捕
#（政府级：验证脚本须报告一切解析失败，不因异常类型收窄而漏报）
# S-06 整改（国防级审查）：本脚本为开发期快速检查（AST/JSON/XML 语法）；
# 发布期实际验证（build/测试/SBOM/签名/provenance 对账）由 release.yml
# verify job 覆盖（B0-S 整改——docs/release/release.yml fail-closed）

from __future__ import annotations

import ast
import json
import xml.etree.ElementTree as ET
from pathlib import Path

# S1-6 修复（H1）：此前硬编码打包机路径 /home/ubuntu/aegis_dual_platform，
# 在任意其他机器上运行必然 FileNotFoundError。改为基于本文件位置的
# 相对路径，跨平台可移植（Windows/Linux/macOS 均生效）。
root = Path(__file__).resolve().parent
windows = root / 'legacy' / 'windows-pywebview'
failures: list[str] = []
python_files = list(windows.rglob('*.py'))
for path in python_files:
    try:
        ast.parse(path.read_text(encoding='utf-8'), filename=str(path))
    except Exception as exc:  # noqa: BLE001（验证脚本盲捕是设计）
        failures.append(f'Python {path.relative_to(root)}: {exc}')
try:
    json.loads((root / 'shared' / 'release.json').read_text(encoding='utf-8'))
except Exception as exc:  # noqa: BLE001（验证脚本盲捕是设计）
    failures.append(f'JSON shared/release.json: {exc}')
for path in (root / 'windows' / 'packaging').glob('*.template'):
    try:
        ET.parse(path)
    except Exception as exc:  # noqa: BLE001（验证脚本盲捕是设计）
        failures.append(f'XML {path.relative_to(root)}: {exc}')
if (windows / 'aegis_webview.nsi').exists():
    failures.append('Deprecated NSIS script still exists in the Windows working copy')
# ABC 级闭环（B3 依赖 hash 锁定）：锁文件门禁——requirements-lock.txt 必须
# 存在且含 hash（pip-compile --generate-hashes 生成——可复现安装前提——
# 张显达实践：改依赖未更新锁文件 → 直接失败）
lock_file = windows / 'requirements-lock.txt'
if not lock_file.is_file():
    failures.append('缺 requirements-lock.txt（pip-compile --generate-hashes 生成）')
elif '--hash=' not in lock_file.read_text(encoding='utf-8'):
    failures.append('requirements-lock.txt 无 hash（--generate-hashes 重新生成）')

# 审计修复：正典 C# 栈存在性断言（此前脚本只看 legacy 栈——C# 代码不经
# 任何检查；发布资源断言在 release-windows.yml，这里是仓库级快速门禁）
csproj = root / 'windows' / 'src' / 'Aegis.Windows.App' / 'Aegis.Windows.App.csproj'
if not csproj.is_file():
    failures.append('缺正典 C# 工程 windows/src/Aegis.Windows.App/Aegis.Windows.App.csproj')
else:
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
            failures.append(f'缺 C# 关键文件 windows/src/Aegis.Windows.App/{rel}')
for shell_asset in ('start.html', 'start.css', 'start.snake.js', 'start.import.js'):
    if not (root / 'shared' / 'shell' / shell_asset).is_file():
        failures.append(f'缺跨端单源首页资产 shared/shell/{shell_asset}')
print(f'python_files={len(python_files)}')
print(f'failures={len(failures)}')
for failure in failures:
    print(failure)
raise SystemExit(1 if failures else 0)

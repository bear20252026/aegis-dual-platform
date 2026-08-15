# ruff: noqa: BLE001 —— 验证脚本捕获文件/JSON/XML 解析异常是设计性盲捕
#（政府级：验证脚本须报告一切解析失败，不因异常类型收窄而漏报）

from __future__ import annotations

import ast
import json
import xml.etree.ElementTree as ET
from pathlib import Path

# S1-6 修复（H1）：此前硬编码打包机路径 /home/ubuntu/aegis_dual_platform，
# 在任意其他机器上运行必然 FileNotFoundError。改为基于本文件位置的
# 相对路径，跨平台可移植（Windows/Linux/macOS 均生效）。
root = Path(__file__).resolve().parent
windows = root / 'windows' / 'aegis_source'
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
print(f'python_files={len(python_files)}')
print(f'failures={len(failures)}')
for failure in failures:
    print(failure)
raise SystemExit(1 if failures else 0)

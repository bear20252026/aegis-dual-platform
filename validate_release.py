from __future__ import annotations

import ast
import json
from pathlib import Path
import xml.etree.ElementTree as ET

root = Path('/home/ubuntu/aegis_dual_platform')
windows = root / 'windows' / 'aegis_source'
failures: list[str] = []
python_files = list(windows.rglob('*.py'))
for path in python_files:
    try:
        ast.parse(path.read_text(encoding='utf-8'), filename=str(path))
    except Exception as exc:
        failures.append(f'Python {path.relative_to(root)}: {exc}')
try:
    json.loads((root / 'shared' / 'release.json').read_text(encoding='utf-8'))
except Exception as exc:
    failures.append(f'JSON shared/release.json: {exc}')
for path in (root / 'windows' / 'packaging').glob('*.template'):
    try:
        ET.parse(path)
    except Exception as exc:
        failures.append(f'XML {path.relative_to(root)}: {exc}')
if (windows / 'aegis_webview.nsi').exists():
    failures.append('Deprecated NSIS script still exists in the Windows working copy')
print(f'python_files={len(python_files)}')
print(f'failures={len(failures)}')
for failure in failures:
    print(failure)
raise SystemExit(1 if failures else 0)

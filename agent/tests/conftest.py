"""agent/tests conftest（SP-069，审计 2026-09-23 清单·SP1 批）。

pytest 收集锚点：保证 `python -m pytest agent/tests -q` 与任意工作目录下
`pytest <repo>/agent/tests` 收集一致；agent/tests 内模块（redteam_test /
redteam_e2e_test）可被未来跨文件复用（sys.path 注入本目录）。
"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

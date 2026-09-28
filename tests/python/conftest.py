# conftest.py —— SP-161（2026-09-26 审计）：tests/python 统一 sys.path 注入。
# 此前六个测试文件各自重复 ROOT=+sys.path.insert 样板（且各注各的子目录）；
# 现统一在此注入仓库根与全部被测模块目录，测试文件不再自带样板。
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

for _p in (
    ROOT,
    ROOT / "release",
    ROOT / "release" / "tools" / "verify_artifact_set",
    ROOT / "release" / "tools" / "verify_manifest",
    ROOT / "release" / "tools" / "verify_provenance",
    ROOT / "release" / "tools" / "generate_sbom",
    ROOT / "scripts",
    ROOT / "contracts" / "codegen",
):
    _sp = str(_p)
    if _sp not in sys.path:
        sys.path.insert(0, _sp)

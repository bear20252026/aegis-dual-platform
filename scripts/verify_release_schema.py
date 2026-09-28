#!/usr/bin/env python3
"""verify_release_schema.py —— PY-102 整改（2026-09-25 审计）。

shared/release.json 此前仅由 verify_versions.py 对账 version/versionCode
两字段，其余 14 字段（displayName/architecture/distribution/runtime/
applicationId/updateManifest 等）无任何 schema 校验——漂移无门禁（PY-101
arm64 虚假声明即是此类漂移的实例）。本脚本把 release.json 接入
release.schema.json（additionalProperties false + 枚举/模式收敛）。

挂载：contracts.yml（jsonschema 工具链已在该 workflow 安装）。
退出码：0=通过 / 1=校验失败 / 2=环境错误。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

try:
    import jsonschema
except ImportError:
    print("[fail] 缺依赖 jsonschema——CI 步骤须先 pip install", file=sys.stderr)
    sys.exit(2)

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "contracts" / "schemas" / "release.schema.json"
TARGET_PATH = ROOT / "shared" / "release.json"


def main() -> int:
    try:
        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        target = json.loads(TARGET_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        print(f"[fail] 读取失败（{exc}）", file=sys.stderr)
        return 1

    validator = jsonschema.Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(target), key=lambda e: e.json_path)
    if errors:
        for e in errors:
            print(f"[fail] {e.json_path}: {e.message}", file=sys.stderr)
        return 1
    print("[ok] shared/release.json 通过 release.schema.json 全字段校验（PY-102）")
    return 0


if __name__ == "__main__":
    sys.exit(main())

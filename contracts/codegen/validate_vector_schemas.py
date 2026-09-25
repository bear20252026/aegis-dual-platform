#!/usr/bin/env python3
"""validate_vector_schemas.py —— PY-013 整改（2026-09-24 审计）。

此前 contracts.yml 的校验只断言向量协议字段（expected/expected_*）——
7 份 JSON Schema 纯装饰，向量负载从不过 JSON Schema 本体。本脚本把
「schema 可判定的向量」接入 jsonschema 校验：

- update-manifest-valid.json   → manifest 必须通过 update-manifest.schema.json
- update-manifest-invalid.json → manifest 必须被 schema 拒绝（若其失效
  原因恰为 schema 级——语义级失效向量允许通过 schema，不误报）
- action-valid/invalid.json        → PY-094 双向（schema 级严格：valid 必过/invalid 必拒）
- capability-valid/invalid.json    → PY-095 双向（同上）
- audit-event-valid/invalid.json   → PY-096 双向（同上）

其余向量文件（url-origin / native-navigation / approvals）为多步流
协议脚本（step 脚本而非 schema 实例），不适用直接校验——由 Rust/
Android 一致性测试消费。

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

ROOT = Path(__file__).resolve().parents[2]
SCHEMAS = ROOT / "contracts" / "schemas"
VECTORS = ROOT / "contracts" / "vectors"

# PY-094..096：向量文件 → 实例键 → schema 文件映射
SCHEMA_VECTOR_FILES = {
    "action-valid.json": "action",
    "action-invalid.json": "action",
    "capability-valid.json": "capability",
    "capability-invalid.json": "capability",
    "audit-event-valid.json": "audit_event",
    "audit-event-invalid.json": "audit_event",
}
SCHEMA_FOR_KEY = {
    "action": "action.schema.json",
    "capability": "capability.schema.json",
    "audit_event": "audit-event.schema.json",
}


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    schema = _load(SCHEMAS / "update-manifest.schema.json")
    validator = jsonschema.Draft202012Validator(
        schema, format_checker=jsonschema.FormatChecker(),
    )
    failures: list[str] = []

    # 合法向量：schema 校验必须通过
    for i, vector in enumerate(_load(VECTORS / "update-manifest-valid.json").get("vectors", [])):
        manifest = vector.get("manifest")
        if not isinstance(manifest, dict):
            failures.append(f"valid 向量 #{i} 缺 manifest 对象")
            continue
        errors = sorted(validator.iter_errors(manifest), key=lambda e: e.json_path)
        if errors:
            failures.append(f"valid 向量 #{i} 应通过 schema: {errors[0].message}")

    # 非法向量：schema 级失效必须被拒绝；语义级失效（schema 通过）为合法设计
    invalid_path = VECTORS / "update-manifest-invalid.json"
    if invalid_path.exists():
        for i, vector in enumerate(_load(invalid_path).get("vectors", [])):
            manifest = vector.get("manifest")
            if not isinstance(manifest, dict):
                continue
            if validator.is_valid(manifest):
                print(f"[info] invalid 向量 #{i} 为语义级失效（schema 通过——不误报）")

    # PY-094..096（审计 2026-09-25）：action / capability / audit-event 双向向量
    # ——严格 schema 级：valid 必须全过、invalid 必须全拒（不设语义级豁免，
    # 三者均为纯数据契约，schema 可判定性完整）
    validators: dict[str, jsonschema.Draft202012Validator] = {}
    for fname, key in SCHEMA_VECTOR_FILES.items():
        path = VECTORS / fname
        if not path.exists():
            failures.append(f"缺失向量文件: {fname}（PY-094..096 契约）")
            continue
        if key not in validators:
            validators[key] = jsonschema.Draft202012Validator(
                _load(SCHEMAS / SCHEMA_FOR_KEY[key]),
                format_checker=jsonschema.FormatChecker(),
            )
        v = validators[key]
        expect_reject = fname.endswith("invalid.json")
        for i, vector in enumerate(_load(path).get("vectors", [])):
            instance = vector.get(key)
            if not isinstance(instance, dict):
                failures.append(f"{fname} 向量 #{i} 缺 {key} 对象")
                continue
            is_valid = v.is_valid(instance)
            if expect_reject and is_valid:
                failures.append(f"{fname} 向量 #{i} 应被 schema 拒绝（{vector.get('note', '')}）")
            elif not expect_reject and not is_valid:
                errors = sorted(v.iter_errors(instance), key=lambda e: e.json_path)
                failures.append(f"{fname} 向量 #{i} 应通过 schema: {errors[0].message}")

    if failures:
        for f in failures:
            print(f"[fail] {f}", file=sys.stderr)
        return 1
    print("[ok] 契约向量 JSON Schema 校验通过（update-manifest + action/capability/audit-event 双向）")
    return 0


if __name__ == "__main__":
    sys.exit(main())

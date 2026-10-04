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
# R7-SH-07（第七轮 2026-10-04）：update-manifest-invalid.json 的 expected 取值白名单。
# "deny_schema" = schema 级失效（必须被 schema 拒）；其余三个属语义层失效
#（rollback 门/阈值门/过期门——schema 通过是合法设计，判定在 update_verifier）。
# 取值集合 = 本轮实测面（9 deny_schema / 1 deny_rollback / 1 deny_expired /
# 3 deny_threshold，合计 14 条）。新增拒绝理由必须同时在这里登记，避免
# 「改个 expected 字符串就静默摘掉一条断言」。
KNOWN_DENY_EXPECTED = frozenset({
    "deny_schema", "deny_rollback", "deny_threshold", "deny_expired",
})

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
    failures: list[str] = []
    # PY-272（2026-10-02 审计）：update-manifest 三处输入 _load（schema 本体/
    # valid 向量/invalid 向量）此前无守卫——缺文件裸 FileNotFoundError 栈、
    # 坏 JSON 裸 JSONDecodeError 栈（门禁脚本必须干净报告+非零退出）。
    # 统一包 (OSError, json.JSONDecodeError) → 带文件路径干净报告 + return 1
    #（校验失败语义）。
    invalid_path = VECTORS / "update-manifest-invalid.json"

    def _fail_load(path: Path, exc: Exception) -> int:
        print(f"[fail] 输入文件读取/解析失败: {path}（{exc}——fail-closed）",
              file=sys.stderr)
        return 1

    try:
        schema = _load(SCHEMAS / "update-manifest.schema.json")
    except (OSError, json.JSONDecodeError) as exc:
        return _fail_load(SCHEMAS / "update-manifest.schema.json", exc)
    try:
        valid_vectors = _load(VECTORS / "update-manifest-valid.json").get("vectors", [])
    except (OSError, json.JSONDecodeError) as exc:
        return _fail_load(VECTORS / "update-manifest-valid.json", exc)
    # R7-SH-07（第七轮 2026-10-04）：invalid 向量此前是「文件不存在→空列表→
    # 双向断言整段消失且 exit 0」，而同文件对 action/capability/audit-event 六个
    # 向量却是「缺失计入 failures」——同文件两套口径。删/改名一个向量文件即可
    # 在 CI 绿灯下摘掉 schema 削弱检测。现与 schema/valid 同走无条件 _load。
    try:
        invalid_vectors = _load(invalid_path).get("vectors", [])
    except (OSError, json.JSONDecodeError) as exc:
        return _fail_load(invalid_path, exc)
    validator = jsonschema.Draft202012Validator(
        schema, format_checker=jsonschema.FormatChecker(),
    )

    # 合法向量：schema 校验必须通过
    for i, vector in enumerate(valid_vectors):
        manifest = vector.get("manifest")
        if not isinstance(manifest, dict):
            failures.append(f"valid 向量 #{i} 缺 manifest 对象")
            continue
        errors = sorted(validator.iter_errors(manifest), key=lambda e: e.json_path)
        if errors:
            failures.append(f"valid 向量 #{i} 应通过 schema: {errors[0].message}")

    # 非法向量：按 expected 声明分流（PY-241，2026-10-01 审计）
    # - expected == "deny_schema"：schema 级失效——必须被 schema 拒绝
    #   （此前对全部 invalid 向量只打 info 零断言——schema 削弱即枚举收窄、
    #   pattern 放宽时门禁仍绿，失效向量全部沦为"语义级"豁免）
    # - 其他 expected（deny_rollback/deny_threshold/deny_expired 等）：语义级
    # 失效（schema 通过是合法设计——判定在 update_verifier 语义层），
    # 打 info 不误报
    for i, vector in enumerate(invalid_vectors):
        manifest = vector.get("manifest")
        if not isinstance(manifest, dict):
            continue
        # R7-SH-07：语义级豁免的**取值**必须有界。此前任何非 "deny_schema" 的
        # expected 都降级为 info——把值改成 "whatever" 即可把一条本该被 schema
        # 拒绝的失效向量变成零断言。现只接受实测在用的四个拒绝理由，
        # 新理由须显式登记（同时意味着要有人核对它确实属语义层失效）。
        expected_value = vector.get("expected")
        if expected_value not in KNOWN_DENY_EXPECTED:
            failures.append(
                f"invalid 向量 #{i}（{vector.get('case', '?')}）expected 取值未知："
                f"{expected_value!r}——语义级豁免不得由条目自述任意字符串，"
                f"须先登记进 KNOWN_DENY_EXPECTED（{sorted(KNOWN_DENY_EXPECTED)}）")
            continue
        schema_level = expected_value == "deny_schema"
        is_valid = validator.is_valid(manifest)
        if schema_level and is_valid:
            failures.append(
                f"invalid 向量 #{i}（{vector.get('case', '?')}）声明 deny_schema "
                f"但 schema 放行——schema 已削弱或向量失效原因漂移（fail-closed）")
        elif not schema_level and is_valid:
            print(f"[info] invalid 向量 #{i}（{vector.get('case', '?')}）为语义级失效"
                  f"（schema 通过——判定在 update_verifier 语义层，不误报）")

    # PY-094..096（审计 2026-09-25）：action / capability / audit-event 双向向量
    # ——严格 schema 级：valid 必须全过、invalid 必须全拒（不设语义级豁免，
    # 三者均为纯数据契约，schema 可判定性完整）
    validators: dict[str, jsonschema.Draft202012Validator] = {}
    for fname, key in SCHEMA_VECTOR_FILES.items():
        path = VECTORS / fname
        if not path.exists():
            failures.append(f"缺失向量文件: {fname}（PY-094..096 契约）")
            continue
        # PY-272：双向向量/schema 的 _load 同守卫——坏文件计入 failures
        # 干净退出（不裸栈）
        try:
            if key not in validators:
                validators[key] = jsonschema.Draft202012Validator(
                    _load(SCHEMAS / SCHEMA_FOR_KEY[key]),
                    format_checker=jsonschema.FormatChecker(),
                )
            vector_doc = _load(path).get("vectors", [])
        except (OSError, json.JSONDecodeError) as exc:
            failures.append(f"{fname} 读取/解析失败: {exc}")
            continue
        v = validators[key]
        expect_reject = fname.endswith("invalid.json")
        for i, vector in enumerate(vector_doc):
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

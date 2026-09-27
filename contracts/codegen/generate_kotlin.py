#!/usr/bin/env python3
"""generate_kotlin.py —— contracts/codegen（蓝图阶段 B——由契约生成 Kotlin 模型）。

从 contracts/schemas/*.json 生成 Kotlin data class（与阶段 D android/contracts
对齐——不手工维护平行 Schema——蓝图）。属性由 schema required/properties 驱动。
"""

from __future__ import annotations

import json
import pathlib
import sys

SCHEMAS = pathlib.Path(__file__).resolve().parents[1] / "schemas"
# PY-102：发布事实声明（release.schema.json 校验 shared/release.json 用）
# 不是跨语言消息契约——不参与模型生成
SKIP_SCHEMAS = {"release.schema.json"}
OUT = (pathlib.Path(__file__).resolve().parents[1] / ".." / "android" / "contracts"
       / "src" / "main" / "kotlin" / "com" / "aegis" / "contracts" / "generated")


# PY-100：Kotlin 类型映射（与 generate_csharp.cs_type 对偶）——number 不再
# 降级 Any；未知类型 fail-closed
KT_TYPE_MAP = {
    "string": "String",
    "integer": "Long",
    "number": "Double",
    "boolean": "Boolean",
    "object": "Any",
}


def kt_type(prop: dict) -> str:
    t = prop.get("type", "string")
    if t == "array":
        items = prop.get("items", {}).get("type", "string")
        if items not in KT_TYPE_MAP:
            raise ValueError(f"数组 items 类型不支持: {items!r}（fail-closed——禁止静默降级）")
        return f"List<{KT_TYPE_MAP[items]}>"
    if t not in KT_TYPE_MAP:
        raise ValueError(f"schema 类型不支持: {t!r}（fail-closed——禁止静默降级 Any）")
    return KT_TYPE_MAP[t]


# PY-188（2026-09-26 审计）：enum/const 值域元数据（与 generate_csharp 对偶）
# ——降级取舍的完整说明见 generate_csharp.describe_value_domain：首选
# enum/常量类生成需同步重生成 windows/src 与 android/ 落盘产物（本批次
# 范围外），退化为「值域元数据 + 单测锁定」。
def describe_value_domain(prop: dict) -> str:
    """提取属性的 enum/const 值域描述（enum → "enum: A | B"；const → "const: X"）。"""
    if "enum" in prop:
        values = prop["enum"]
        rendered = " | ".join(str(v) for v in values)
        return f"enum: {rendered}"
    if "const" in prop:
        return f"const: {prop['const']}"
    return ""


def generate(schema: dict, name: str) -> str:
    props = schema.get("properties", {})
    required = set(schema.get("required", []))
    # PY-197（2026-09-26 审计）：required 引用未定义属性此前被静默丢弃——
    # 必填约束无声丢失（fail-open）。先算 unknown 集合，非空抛 ValueError
    #（fail-closed——与 generate_csharp 同口径）。
    unknown = required - set(props)
    if unknown:
        raise ValueError(
            f"required 引用未定义属性: {sorted(unknown)}（schema={name}——fail-closed）")
    # PY-100：required 区分——必选在前（与 C# 对偶，构造可读性），组内保持
    # schema 声明序；非必选生成可空类型 + 默认 null
    ordered = [k for k in props if k in required] + [k for k in props if k not in required]
    lines = [
        "// 由 contracts/codegen/generate_kotlin.py 生成（蓝图阶段 B——契约事实来源——请勿手工编辑）",
        "package com.aegis.contracts.generated",
        "",
        f"data class {name}(",
    ]
    for pname in ordered:
        p = props[pname]
        t = kt_type(p)
        # 尾逗恒定输出（ktlint trailing-comma-on-declaration-site——A-2 门禁扩面）
        if pname in required:
            lines.append(f"    val {pname}: {t},")
        else:
            lines.append(f"    val {pname}: {t}? = null,")
    lines.append(")")
    return "\n".join(lines)


def contract_name(schema_file: pathlib.Path) -> str:
    """将 action.schema.json 转为稳定且合法的 ActionContract 类型名。"""
    stem = schema_file.stem.removesuffix(".schema")
    return "".join(part[:1].upper() + part[1:] for part in stem.split("-")) + "Contract"


def main() -> int:
    # AD-244（2026-09-26 审计）：Approval/AuditEvent/Capability/UpdateManifest/
    # Version 五份 Kotlin 生成物在 Android 代码中当前零消费——保留生成的原因
    # 是「跨语言契约镜像完整性」（与 C# 镜像同构对账，schema 漂移即门禁红）；
    # 收窄生成范围会让镜像失去对账意义，故保留（取舍说明同步
    # verify_contract_compatibility.check_generated_models）。
    out_dir = OUT
    out_dir.mkdir(parents=True, exist_ok=True)
    generated: set[str] = set()
    for f in sorted(SCHEMAS.glob("*.json")):
        if f.name in SKIP_SCHEMAS:
            continue
        schema = json.loads(f.read_text(encoding="utf-8"))
        name = contract_name(f)
        (out_dir / f"{name}.kt").write_text(generate(schema, name) + "\n", encoding="utf-8")
        generated.add(f"{name}.kt")
        print(f"  ✅ 生成 Kotlin 模型: {name}.kt")
    # 陈旧清理（差集删除）：此前 glob("*.schema.kt") 与生成名 {Name}Contract.kt
    # 永不匹配——清理是 no-op，被删除 schema 的旧生成文件永久残留
    for stale in out_dir.glob("*Contract.kt"):
        if stale.name not in generated:
            stale.unlink()
            print(f"  🗑 移除陈旧生成文件: {stale.name}")
    print(f"Kotlin 模型生成完成（{len(generated)} 个——contracts 事实来源）")
    return 0


if __name__ == "__main__":
    sys.exit(main())

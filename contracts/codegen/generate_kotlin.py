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
OUT = (pathlib.Path(__file__).resolve().parents[1] / ".." / "android" / "contracts"
       / "src" / "main" / "kotlin" / "com" / "aegis" / "contracts" / "generated")


def kt_type(prop: dict) -> str:
    t = prop.get("type", "string")
    if t == "string":
        return "String"
    if t == "integer":
        return "Long"
    if t == "boolean":
        return "Boolean"
    if t == "array":
        items = prop.get("items", {}).get("type", "string")
        return f"List<{kt_type({'type': items})}>"
    return "Any"


def generate(schema: dict, name: str) -> str:
    props = schema.get("properties", {})
    lines = [
        "// 由 contracts/codegen/generate_kotlin.py 生成（蓝图阶段 B——契约事实来源——请勿手工编辑）",
        "package com.aegis.contracts.generated",
        "",
        f"data class {name}(",
    ]
    properties = list(props.items())
    for pname, p in properties:
        # 尾逗恒定输出（ktlint trailing-comma-on-declaration-site——A-2 门禁扩面）
        lines.append(f"    val {pname}: {kt_type(p)},")
    lines.append(")")
    return "\n".join(lines)


def contract_name(schema_file: pathlib.Path) -> str:
    """将 action.schema.json 转为稳定且合法的 ActionContract 类型名。"""
    stem = schema_file.stem.removesuffix(".schema")
    return "".join(part[:1].upper() + part[1:] for part in stem.split("-")) + "Contract"


def main() -> int:
    out_dir = OUT
    out_dir.mkdir(parents=True, exist_ok=True)
    generated: set[str] = set()
    for f in sorted(SCHEMAS.glob("*.json")):
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

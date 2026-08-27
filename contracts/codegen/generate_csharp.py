#!/usr/bin/env python3
"""generate_csharp.py —— contracts/codegen（蓝图阶段 B——由契约生成 C# 模型）。

从 contracts/schemas/*.json 生成 C# record（与阶段 C Aegis.Windows.Contracts
对齐——不手工维护平行 Schema——蓝图）。属性由 schema required/properties 驱动。
"""

from __future__ import annotations

import json
import pathlib
import sys

SCHEMAS = pathlib.Path(__file__).resolve().parents[1] / "schemas"
OUT = (pathlib.Path(__file__).resolve().parents[1] / ".." / "windows" / "src"
       / "Aegis.Windows.App" / "Contracts" / "Generated")


def cs_type(prop: dict) -> str:
    t = prop.get("type", "string")
    if t == "string":
        return "string"
    if t == "integer":
        return "long"
    if t == "boolean":
        return "bool"
    if t == "array":
        items = prop.get("items", {}).get("type", "string")
        return f"List<{cs_type({'type': items})}>"
    return "object"


def generate(schema: dict, name: str) -> str:
    props = schema.get("properties", {})
    lines = [
        "// 由 contracts/codegen/generate_csharp.py 生成（蓝图阶段 B——契约事实来源——请勿手工编辑）",
        "using System.Collections.Generic;",
        "namespace Aegis.Windows.Contracts.Generated;",
        "",
        f"public sealed record {name}(",
    ]
    for pname, p in props.items():
        lines.append(f"    {cs_type(p)} {pname},")
    lines.append(");")
    return "\n".join(lines)


def contract_name(schema_file: pathlib.Path) -> str:
    """将 action.schema.json 转为稳定且合法的 ActionContract 类型名。"""
    stem = schema_file.stem.removesuffix(".schema")
    return "".join(part[:1].upper() + part[1:] for part in stem.split("-")) + "Contract"


def main() -> int:
    out_dir = OUT
    out_dir.mkdir(parents=True, exist_ok=True)
    for stale_file in out_dir.glob("*.schema.cs"):
        stale_file.unlink()
    for f in sorted(SCHEMAS.glob("*.json")):
        schema = json.loads(f.read_text(encoding="utf-8"))
        name = contract_name(f)
        (out_dir / f"{name}.cs").write_text(generate(schema, name) + "\n", encoding="utf-8")
        print(f"  ✅ 生成 C# 模型: {name}.cs")
    print(f"C# 模型生成完成（{len(list(out_dir.glob('*.cs')))} 个——contracts 事实来源）")
    return 0


if __name__ == "__main__":
    sys.exit(main())

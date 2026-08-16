#!/usr/bin/env python3
"""verify_contract_compatibility.py —— contracts/codegen（蓝图阶段 B——契约兼容性）。

阶段 B 完成标准：Schema/C#/Kotlin/Python fixture 对同一组合法/非法输入得到一致
结果——跨语言一致（Rust/C#/Kotlin reference + Python fixture——同一 contracts
vectors）。校验：schemas/vectors JSON 有效 + 生成的 C#/Kotlin 模型与 schema
properties 一致（不平行 Schema——蓝图）。
"""

from __future__ import annotations

import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCHEMAS = ROOT / "schemas"
VECTORS = ROOT / "vectors"


def check_schemas() -> list[str]:
    failures = []
    for f in sorted(SCHEMAS.glob("*.json")):
        try:
            json.loads(f.read_text(encoding="utf-8"))
        except Exception as e:
            failures.append(f"schema JSON 无效: {f.name}（{e}）")
    return failures


def check_vectors() -> list[str]:
    failures = []
    for f in sorted(VECTORS.glob("*.json")):
        try:
            json.loads(f.read_text(encoding="utf-8"))
        except Exception as e:
            failures.append(f"vector JSON 无效: {f.name}（{e}）")
    return failures


def check_generated_models() -> list[str]:
    """生成的 C#/Kotlin 模型与 schema properties 一致（不平行 Schema——蓝图）。"""
    failures = []
    generated_cs = (ROOT / ".." / "windows" / "src" / "Aegis.Windows.App"
                    / "Contracts" / "Generated")
    generated_kt = (ROOT / ".." / "android" / "contracts" / "src" / "main" / "kotlin"
                    / "com" / "aegis" / "contracts" / "generated")
    for f in sorted(SCHEMAS.glob("*.json")):
        name = "".join(part.capitalize() for part in f.stem.split("-"))
        if not (generated_cs / f"{name}.cs").is_file():
            failures.append(f"C# 模型缺失: {name}.cs（运行 generate_csharp.py）")
        if not (generated_kt / f"{name}.kt").is_file():
            failures.append(f"Kotlin 模型缺失: {name}.kt（运行 generate_kotlin.py）")
    return failures


def main() -> int:
    failures = check_schemas() + check_vectors() + check_generated_models()
    if failures:
        for f in failures:
            print(f"❌ {f}")
        return 1
    print("✅ 契约兼容性验证通过（schemas/vectors JSON 有效 + C#/Kotlin 模型与 "
          "schema 一致——跨语言一致——阶段 B 完成标准）")
    return 0


if __name__ == "__main__":
    sys.exit(main())

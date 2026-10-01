"""value_domain.py —— 契约生成器共享的 enum/const 值域描述（单源）。

PY-242（2026-10-01 审计）：describe_value_domain 此前在 generate_csharp.py
与 generate_kotlin.py 逐字重复两份——任何一侧修改都会让 C#/Kotlin 生成物
的值域注释口径分叉。抽本模块单源，两生成器共同消费（行为不变——
generate() 输出字节零漂移，verify_contract_compatibility 对账锁定）。
"""

from __future__ import annotations


def describe_value_domain(prop: dict) -> str:
    """提取属性的 enum/const 值域描述（enum → "enum: A | B | C"；const → "const: X"）。"""
    if "enum" in prop:
        values = prop["enum"]
        rendered = " | ".join(str(v) for v in values)
        return f"enum: {rendered}"
    if "const" in prop:
        return f"const: {prop['const']}"
    return ""

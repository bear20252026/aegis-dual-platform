"""ident.py —— 契约生成器共享的 schema→标识符 命名规则（单源）。

PY-243（2026-10-01 审计）：嵌套子模型命名（{Contract}{Item}）需要两生成器
使用同一套 PascalCase/单数化规则——命名分叉会让 C#/Kotlin 嵌套类型名对不上、
跨语言镜像失去同构性。抽本模块单源，generate_csharp 与 generate_kotlin
共同消费。
"""

from __future__ import annotations

import re


def pascal(value: str) -> str:
    """schema 值 → PascalCase 标识符段：require_confirmation→RequireConfirmation，
    GET→GET（全大写词保留），非字母数字作分隔。"""
    tokens = [t for t in re.split(r"[^A-Za-z0-9]+", value) if t]
    out = "".join(t if t.isupper() else t[:1].upper() + t[1:] for t in tokens)
    return out or "Value"


def singular_pascal(value: str) -> str:
    """复数属性名 → 单数 PascalCase 类型名段：artifacts→Artifact、
    entries→Entry、buses→Bus（-ss 结尾不动）、address→Addres 的退化由
    调用方回避（非 -s 结尾原样 Pascal）。规则确定性优先于语言学完备。"""
    out = pascal(value)
    if out.endswith("ies"):
        return out[:-3] + "y"
    if out.endswith("s") and not out.endswith("ss"):
        return out[:-1]
    return out

#!/usr/bin/env python3
"""rust_code_reader.py —— 门禁读 Rust 源的四件通用事（键 / 剔注释 / 函数体 / usize 常量）。

按文本判源码的门禁都要这几样：给判定面取一个不会撞车的键、把注释剔干净再判、
按大括号配平取一个函数体、把 `const NAME: usize = 表达式` 解成整数。同一件事写在
每个门禁里就是漂移面（R9-B61 的第二判据拦的正是「同一件事写两遍」），收在这一份里。

剔注释的口径本身不在这里维护——单源 `scripts/text_anchors.py`（R9-B45），本模块只是
把它和「读文件」这一步接起来：注释里的形态不算证据（R9-B39 那课：注记里逐字写着
被禁形态时，不剔注释的判据会被自己的注记打绿）。

`fn_body` / `const_value` 找不到锚点时一律返回 None，由调用方按「判定面塌缩」处理
（函数被改名或换了写法时，「没发现问题」不代表「没有问题」）。
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from text_anchors import strip_comments  # 剔注释口径单源（R9-B45）


def key(path: Path) -> str:
    """判定面的键 = 相对路径——`mod.rs` 与 `broker.rs` 各有两份，文件名不够唯一。"""
    return path.relative_to(ROOT).as_posix()


def code_only(path: Path) -> str:
    """读一份源文件并剔注释——注释里的形态不算证据（R9-B39）。"""
    return strip_comments(path.read_text(encoding="utf-8", errors="ignore"), key(path))


def load_texts(paths) -> dict[str, str]:
    """读多份受管文件 → {键: 正文}；读不到的直接不进面（由调用方判塌缩）。"""
    return {key(p): code_only(p) for p in paths if p.exists()}


def const_value(texts: dict[str, str], path: Path, name: str) -> int | None:
    """解一个 `usize` 常量的值；解不开当缺失返回 None，而不是按 0 参与比较。"""
    body = texts.get(key(path), "")
    match = re.search(rf"const\s+{name}\s*:\s*usize\s*=\s*([^;\n]+);", body)
    if not match:
        return None
    expr = match.group(1).strip()
    if not re.fullmatch(r"\d+(?:\s*\*\s*\d+)*", expr):
        return None
    product = 1
    for factor in re.split(r"\s*\*\s*", expr):
        product *= int(factor)
    return product


def fn_body(text: str, name: str) -> str | None:
    """取函数体（大括号配平）。找不到函数头返回 None=判定面塌缩。"""
    header = re.search(rf"\bfn\s+{re.escape(name)}\s*(?:<[^>]*>)?\s*\(", text)
    if not header:
        return None
    brace = text.find("{", header.end())
    if brace < 0:
        return None
    depth = 0
    for index in range(brace, len(text)):
        char = text[index]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[brace + 1 : index]
    return None

#!/usr/bin/env python3
"""rust_code_reader.py —— 门禁读 Rust 源的通用件（键 / 剔注释 / 块体配平 / 函数体 / usize 常量）。

按文本判源码的门禁都要这几样：给判定面取一个不会撞车的键、把注释剔干净再判、
按大括号配平取一个块体或函数体、把 `const NAME: usize = 表达式` 解成整数。同一件事写在
每个门禁里就是漂移面（R9-B61 的第二判据拦的正是「同一件事写两遍」），收在这一份里。
消费方两份：`verify_ffi_input_bounds.py`（R9-B61/B63）与 `verify_uniffi_binding_surface.py`
（R9-RS-2，R9-B64 把它的 `_brace_body` 并到这里）。

剔注释的口径本身不在这里维护——单源 `scripts/text_anchors.py`（R9-B45），本模块只是
把它和「读文件」这一步接起来：注释里的形态不算证据（R9-B39 那课：注记里逐字写着
被禁形态时，不剔注释的判据会被自己的注记打绿）。

`fn_body` / `const_value` 找不到锚点时一律返回 None，由调用方按「判定面塌缩」处理
（函数被改名或换了写法时，「没发现问题」不代表「没有问题」）；`brace_body` 的失败值
由调用方决定，两份语义写在它自己的说明里。
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


def brace_body(text: str, from_index: int) -> str | None:
    """取 `from_index` 之后第一个**配对**花括号的内部；配不上返回 None。

    这是「读一段 Rust 块」的唯一一遍大括号配平（R9-B64 前它还有第二份，形如
    `_brace_body`）。失败值由调用方定，两份语义各写明在此：
    - `fn_body` 把 None 原样传出去 = 「函数不在位」，调用方按判定面塌缩处理；
    - `verify_uniffi_binding_surface` 要的是「这一段里没有语句」，把 None 折成空串，
      与空体同值——整个模块读不出任何导出时由它自己的「零导出不作通过判定」兜住。
    """
    start = text.find("{", from_index)
    if start < 0:
        return None
    depth = 0
    for index in range(start, len(text)):
        char = text[index]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start + 1 : index]
    return None


def fn_body(text: str, name: str) -> str | None:
    """取函数体（配平原语见 `brace_body`）。找不到函数头返回 None=判定面塌缩。"""
    header = re.search(rf"\bfn\s+{re.escape(name)}\s*(?:<[^>]*>)?\s*\(", text)
    if header is None:
        return None
    return brace_body(text, header.end())

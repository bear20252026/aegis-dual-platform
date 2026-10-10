"""injected_js_text.py —— 从宿主源码里把「注入给页面的 JS 函数体」取出来并规范化。

`verify_injected_js_parity.py` 的解释层（三端各自抄写的那段 JS 怎么读、怎么比）。
单独成模块的两个理由：① 门禁本体讲判据（哪些函数必须同形、豁免表怎么核对），
不该同时讲词法；② 本仓「新文件 ≤300 行」的红线（第八轮 R8-CS-SEC-14 同型拆分）。

难点只有一个：这些 JS 嵌在宿主语言的字符串字面量里（Kotlin 三引号、C# 原语字符串、
Rust 的 `format!` 转义）。所以花括号配对必须**只在函数体内部**按 JS 语义走——
整份宿主文件一起扫，宿主自己的引号会被当成 JS 串起点，结构从此不可信（第一版就是把
aegisHostFromOrigin 读丢在这上面）。
"""
from __future__ import annotations

import pathlib
import re

_FUNCTION_HEAD = re.compile(r"function\s+([A-Za-z_$][\w$]*)\s*\(")
_DECLARATION = re.compile(r"\b(?:var|let|const)\s+")
# 种子访问器是各端自己的宿主接线（种子由宿主下发），不属于共享逻辑：
# C#/Rust 叫 aegisCanvasSeed()、Kotlin 叫 noiseSeed()，比较时归一成一个记号。
_SEED_ACCESSOR = re.compile(r"\b(?:aegisCanvasSeed|noiseSeed)\(\)")
# R9-RS-9（第九轮 2026-10-10）：注册器**取用路径**同理归一——三端各用自己的名字，
# 而注册逻辑本身在三处已对齐（链式包装传递解析 + hops 上限，见 R9-AD-1）：
#   Windows `registerProxy`＝ToStringGuard 闭包内的**本地函数**（有意不发布到 window：
#             比 Rust/Android 的 Symbol 键入口更严，页面脚本拿不到注册句柄）；
#   Android  `__aegisReg` ＝段首缓存的 `window[Symbol.for('proxy.register.v1')]`；
#   Rust     内联读同一 Symbol 键，源码里键名还是 format! 占位符 `{reg_sym}`
#             （实例化值由 tostring_guard::REGISTER_SYMBOL 钉为同名，且
#              shield/tests.rs 常驻钉「五处注册行全部 try 包裹」）。
# **刻意不用通配 `window[Symbol.for(…)]`**：那会让 close 键 `proxy.register.close.v1`
# 被静默当成注册器通过。别名表只认这两个键名，新增键名必须显式加进来并说明理由。
_REGISTER_ACCESSOR = re.compile(
    r"\b(?:registerProxy|__aegisReg)\b"
    r"|window\[Symbol\.for\('(?:proxy\.register\.v1|\{reg_sym\})'\)\]")
_PUNCT_BEFORE = re.compile(r"\s+([)}\];,])")
_PUNCT_AFTER = re.compile(r"([({[;,])\s+")


def read(path: pathlib.Path) -> str:
    """按原样读入（保留换行符）。

    `newline=""` 是本仓工作副本是 CRLF 时的必备口径——归一成 LF 再写回的话，
    故障注入流程会顺手污染源文件（与 verify_seed_framing_parity.read 同口径）。
    带 newline 参数的 read_text 要 3.13+（CI 钉 3.12），所以这里显式走 open。
    """
    if not path.is_file():
        raise SystemExit(f"❌ 门禁输入缺失：{path}")
    with path.open(encoding="utf-8", newline="") as handle:
        return handle.read()


def _skip_js_string(text: str, at: int) -> int:
    """返回 JS 字符串字面量结束后的下标；串内花括号不参与配对。"""
    quote = text[at]
    index, n = at + 1, len(text)
    while index < n:
        if text[index] == "\\":
            index += 2
            continue
        if text[index] == quote:
            return index + 1
        index += 1
    return n


def _match_braces(text: str, open_at: int) -> int | None:
    """自 `open_at` 的 `{` 起做深度配对，返回配对的 `}` 下标；不闭合返回 None。"""
    depth, index, n = 0, open_at, len(text)
    while index < n:
        ch = text[index]
        if ch in "\"'":
            index = _skip_js_string(text, index)
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return index
        index += 1
    return None


def extract_functions(text: str) -> dict[str, str]:
    """函数名 → 函数体原文（含首尾大括号）。同名取第一次出现。"""
    found: dict[str, str] = {}
    for match in _FUNCTION_HEAD.finditer(text):
        open_at = text.find("{", match.end() - 1)
        if open_at < 0:
            continue
        close_at = _match_braces(text, open_at)
        if close_at is None:
            continue
        found.setdefault(match.group(1), text[open_at:close_at + 1])
    return found


def strip_comments(text: str) -> str:
    """去注释，但**保留字符串字面量内容**（`'://'` 这类要参与比较）。

    逐字符走而不是一次正则：JS 串里出现 `//`（`s.indexOf('://')`）不能被当行注释吃掉。
    """
    out: list[str] = []
    index, n = 0, len(text)
    while index < n:
        ch = text[index]
        pair = text[index:index + 2]
        if pair == "//":
            newline = text.find("\n", index)
            index = n if newline < 0 else newline
        elif pair == "/*":
            closed = text.find("*/", index + 2)
            index = n if closed < 0 else closed + 2
            out.append(" ")
        elif ch in "\"'`":
            quote = ch
            out.append(ch)
            index += 1
            while index < n:
                if text[index] == "\\":
                    out.append(text[index:index + 2])
                    index += 2
                    continue
                out.append(text[index])
                index += 1
                if text[index - 1] == quote:
                    break
        else:
            out.append(ch)
            index += 1
    return "".join(out)


def canonicalize(body: str, end: str) -> str:
    """宿主形态无关的逻辑序列：解 Rust 转义 → 去注释 → 接线名与声明关键字归一 → 压空白。

    声明关键字（var/let/const）归一是**刻意不判**的一条：三端确在 `const orig` 与
    `var orig` 上分歧，无行为差（都不再赋值），判了只会诱使人把门禁调松。
    标点旁的空白也去掉：`catch (e) {}` 与 `catch (e) { }` 是同一个空块而不是两种逻辑。
    """
    if end == "Rust":
        body = body.replace("{{", "{").replace("}}", "}")
    body = _SEED_ACCESSOR.sub("__SEED__()", strip_comments(body))
    body = _REGISTER_ACCESSOR.sub("__REG__", body)
    body = _DECLARATION.sub("var ", body)
    body = " ".join(body.split())
    body = _PUNCT_BEFORE.sub(r"\1", body)
    return _PUNCT_AFTER.sub(r"\1", body)

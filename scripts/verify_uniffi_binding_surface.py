#!/usr/bin/env python3
"""verify_uniffi_binding_surface.py —— R9-RS-2：UniFFI 导出面 ↔ 入库 Python 绑定名实对账。

**要关的风险**：`core/rust-policy-core/bindings/aegis_policy_core.py` 是入库的生成物，
由 `6c8d6cd`（2026-08-22）产出、`495a49c`（2026-10-03）最后一次重 derive。此后
`607d7a1`（2026-10-04）给 `FfiBroker` 加了 `#[uniffi::export] update_host_denylist`，
入库件里没有它，而**任何门禁都不红**：`core-rust.yml:63` 的 `test -s` 判的是刚生成的
Kotlin 文件非空（那半边是 APK 真正消费的绑定，随构建产出、不入库），
`contracts.yml` 的「Fail if generated bindings are stale」只 diff 两个**契约**生成目录。
于是这份 Python 镜像的「跨语言绑定单源」是一个无人核验的陈述——导出面少一个方法，
读它的人（或未来接它的代码）会按不存在的 ABI 写。

判定口径与限制如实声明：本门禁比的是**导出面名字集合**（方法/构造子/自由函数），
不是逐字节 diff。原因有两条，都不是偷懒：
①逐字节要把生成时刻的 OS 与 uniffi 版本一起钉死，而本仓没有 Python 绑定的生成 job
   （现树里它只能手跑），入库件与任何一次重生成之间总有行尾差异（`.gitattributes`
   归一 LF、Windows 工作副本是 CRLF）；
②真正会咬人的缺陷形态就是「少一个导出 / 多一个已删导出」，名字面恰好覆盖它。
方法体漂移（参数增删）由 `core-rust.yml --generated` 模式兜：同一次 cargo 构建里
同时生成 Kotlin 与 Python 绑定，再拿**权威生成结果**与本文件比对——那是工具链自己
说话，不受本机环境影响。

退出码：0=一致 / 1=任一方向漂移 / 2=扫描面为空（src 无导出或绑定无符号——
「没东西可查」不作通过判定，与 check_file_sizes/verify_lock_rids 同口径）。
"""
from __future__ import annotations

import argparse
import pathlib
import re
import sys

REPO = pathlib.Path(__file__).resolve().parents[1]
SRC_DIR_REL = "core/rust-policy-core/src"
BINDING_REL = "core/rust-policy-core/bindings/aegis_policy_core.py"
NS = "aegis_policy_core"

EXPORT_ATTR = "#[uniffi::export]"
CTOR_ATTR = "#[uniffi::constructor]"
# Rust 源里 `//` 与 `///` 行会出现属性字面量（`ffi/mod.rs:253` 的注记原文就写着
# 「未做 `#[uniffi::export]`」）——不剔注释会把文档里的反例当成导出面（本轮已在
# CSS/JS 切片上栽过一次，同一课）。
_COMMENT = re.compile(r"^\s*(?://|/\*|\*)")
_FN_AFTER_ATTR = re.compile(r"\s*(?:pub\s+)?fn\s+(\w+)")
_IMPL_AFTER_ATTR = re.compile(r"\s*(?:pub\s+)?impl(?:\s*<[^>]*>)?\s*(\w+)")

_METHOD_SYM = re.compile(rf"uniffi_{NS}_fn_method_([a-z][a-z0-9]*)_([a-z0-9_]+)")
_CTOR_SYM = re.compile(rf"uniffi_{NS}_fn_constructor_([a-z][a-z0-9]*)_([a-z0-9_]+)")
_FUNC_SYM = re.compile(rf"uniffi_{NS}_fn_func_([a-z0-9_]+)")


def _code(text: str) -> str:
    """注释行置换成空行（保留行号，便于人肉对照 file:line）。"""
    return "\n".join("" if _COMMENT.match(line) else line for line in text.splitlines())


def _brace_body(text: str, from_index: int) -> str:
    """取 `from_index` 之后第一个配对花括号的**内部**；配不上返回空串（调用方计漂移）。"""
    start = text.find("{", from_index)
    if start < 0:
        return ""
    depth = 0
    for i in range(start, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return text[start + 1:i]
    return ""


def exports_from_src(text: str) -> tuple[dict[str, set[str]], dict[str, set[str]], set[str]]:
    """解析一份 Rust 源文本的 `#[uniffi::export]` 面。

    返回 `(方法: {对象: {名}}, 构造子: {对象: {名}}, 自由函数: {名})`。
    `#[uniffi::export]` 挂在 `impl` 上时，该 impl 内**所有** `pub fn` 都计入 FFI 面
    （`ffi/broker.rs:316` 的注记原文即此口径），`#[uniffi::constructor]` 标记的那些
    另计一组——绑定里的符号前缀不同（`fn_constructor_` vs `fn_method_`）。
    """
    methods: dict[str, set[str]] = {}
    ctors: dict[str, set[str]] = {}
    funcs: set[str] = set()
    code = _code(text)
    for hit in re.finditer(re.escape(EXPORT_ATTR), code):
        tail = code[hit.end():]
        impl = _IMPL_AFTER_ATTR.match(tail)
        if impl:
            obj = impl.group(1)
            body = _brace_body(tail, impl.end())
            for stmt in re.finditer(r"(#\[uniffi::constructor\][^\n]*)?\n?\s*(?:pub\s+)?fn\s+(\w+)", body):
                name = stmt.group(2)
                bucket = ctors if stmt.group(1) else methods
                bucket.setdefault(obj, set()).add(name)
            continue
        func = _FN_AFTER_ATTR.match(tail)
        if func:
            funcs.add(func.group(1))
    return methods, ctors, funcs


def surface_from_binding(text: str) -> tuple[dict[str, set[str]], dict[str, set[str]], set[str]]:
    """从生成的 Python 绑定里抽同一形状的面（按符号名，不依赖格式化）。"""
    methods: dict[str, set[str]] = {}
    ctors: dict[str, set[str]] = {}
    funcs: set[str] = set()
    for obj, name in _METHOD_SYM.findall(text):
        methods.setdefault(obj, set()).add(name)
    for obj, name in _CTOR_SYM.findall(text):
        ctors.setdefault(obj, set()).add(name)
    funcs.update(_FUNC_SYM.findall(text))
    return methods, ctors, funcs


def _by_key(surface: dict[str, set[str]]) -> dict[str, set[str]]:
    """按绑定符号的对象键归组：uniffi 把 Rust 类型名**小写拼接**（`FfiBroker`→`ffibroker`），
    不归一两侧永远互相判「缺 / 多」（首轮实测就是这样把 9 个方法各报两遍）。"""
    out: dict[str, set[str]] = {}
    for obj, names in surface.items():
        out.setdefault(obj.lower(), set()).update(names)
    return out


def _diff(src: tuple, bound: tuple) -> list[str]:
    src_m, src_c, src_f = src
    b_m, b_c, b_f = bound
    problems: list[str] = []
    for kind, sym, s_raw, b_raw in (("方法", "fn_method", src_m, b_m),
                                    ("构造子", "fn_constructor", src_c, b_c)):
        s, b = _by_key(s_raw), _by_key(b_raw)
        rust_case = {o.lower(): o for o in s_raw}
        for obj in sorted(set(s) | set(b)):
            for name in sorted(s.get(obj, set()) - b.get(obj, set())):
                problems.append(
                    f"绑定缺{kind}：{rust_case.get(obj, obj)}::{name} 在 Rust 侧已 {EXPORT_ATTR}，"
                    f"入库 Python 绑定无对应 `{sym}` 符号")
            for name in sorted(b.get(obj, set()) - s.get(obj, set())):
                problems.append(
                    f"绑定多{kind}：入库 Python 绑定含 {obj}::{name}，而 Rust 侧无此导出"
                    "（绑定超前于源码或落后于删除——读它的人会按不存在的 ABI 写）")
    for name in sorted(src_f - b_f):
        problems.append(f"绑定缺自由函数：{name} 在 Rust 侧已 {EXPORT_ATTR}，入库绑定无 `fn_func_{name}`")
    for name in sorted(b_f - src_f):
        problems.append(f"绑定多自由函数：入库绑定含 `fn_func_{name}` 而 Rust 侧无此导出")
    return problems


def _empty(surface: tuple) -> bool:
    methods, ctors, funcs = surface
    return not (methods or ctors or funcs)


def check(repo_root: pathlib.Path, generated: pathlib.Path | None = None) -> list[str]:
    """实树对账；`generated` 给定时额外比「权威生成结果 ↔ 入库件」。"""
    problems: list[str] = []
    src_dir = repo_root / SRC_DIR_REL
    binding = repo_root / BINDING_REL
    if not src_dir.is_dir() or not binding.is_file():
        raise SystemExit(f"❌ 扫描面缺失：{src_dir} 或 {binding}")
    src: tuple[dict[str, set[str]], dict[str, set[str]], set[str]] = ({}, {}, set())
    for path in sorted(src_dir.rglob("*.rs")):
        m, c, f = exports_from_src(path.read_text(encoding="utf-8"))
        for obj, names in m.items():
            src[0].setdefault(obj, set()).update(names)
        for obj, names in c.items():
            src[1].setdefault(obj, set()).update(names)
        src[2].update(f)
    if _empty(src):
        raise SystemExit(f"❌ Rust 侧零 `#[uniffi::export]`（扫描面 {src_dir}）——判定不成立")
    bound = surface_from_binding(binding.read_text(encoding="utf-8"))
    if _empty(bound):
        raise SystemExit(f"❌ 入库绑定零导出符号（{binding}）——判定不成立")
    problems += _diff(src, bound)
    if generated is not None:
        gen = surface_from_binding(generated.read_text(encoding="utf-8"))
        if _empty(gen):
            raise SystemExit(f"❌ 重生成绑定零导出符号（{generated}）——判定不成立")
        for msg in _diff(gen, bound):
            problems.append(f"权威生成 vs 入库件：{msg}（重跑生成并入库）")
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="UniFFI 导出面与入库 Python 绑定名实对账（R9-RS-2）")
    parser.add_argument("--repo-root", default=str(REPO))
    parser.add_argument("--generated", default=None,
                        help="可选：重生成绑定的路径，额外比它与入库件（core-rust.yml 用）")
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)
    problems = check(pathlib.Path(args.repo_root),
                     pathlib.Path(args.generated) if args.generated else None)
    if problems:
        for p in problems:
            print(f"❌ {p}")
        return 1
    print("✅ UniFFI 导出面与入库 Python 绑定一致（R9-RS-2——名字集合双向对账）")
    return 0


if __name__ == "__main__":
    sys.exit(main())

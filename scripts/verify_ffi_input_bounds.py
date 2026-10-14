#!/usr/bin/env python3
"""verify_ffi_input_bounds.py —— 宿主直传输入的规模上限必须待在**分配之前**（R8-RS-13 / R9-B61）。

起因是台账里一条挂了三轮没动的登记（第八轮 §七 R8-RS-13，第九轮 §六 尾部记为「仍未修」）：
`hex_seed_to_bytes` 把长度判定放在解码**之后**，而 `util::hex_decode` 对任意偶数长度先
`Vec::with_capacity(len/2)` 再全量扫描。C ABI 面有 `read_utf8` 的 64 KiB 有界扫描兜底，
uniffi 面收到的是宿主直传 `String`——`ffi/mod.rs` 自己就写着「解析器自身的前置上限是唯一防线」
（RS-173 注记），而那一面当时没有这道防线。黑名单的 `update_host_denylist(Vec<String>)` 同理。

为什么不写成行为用例：两种写法的**返回值完全相同**（超长种子两边都得到 None），按返回值判顺序
只会得到一条恒真的用例。顺序不是可观察行为，但它是可**读**的——所以这里按文本判源码，
剔注释口径单源 `scripts/text_anchors.py`（R9-B39 / R9-B45 那两条课：注记里逐字写着被禁形态，
不剔注释的判据会被自己的注记打绿）。

判据（每条都在 tests/python/ffi_input_bounds_test.py 里以内存注入证伪）：
1. `hex_seed_to_bytes` 里必须有一条走 `hex.len()` 的前置判定，位置在 `hex_decode(` **之前**；
   且它比的数必须能从返回类型 `[u8; N]` 推出来（N×2）——写死一个别的数即红，防「护栏和契约
   不是同一个数」这种假落地。
2. 黑名单两条上限都要在位：单条长度判在 `entry_shape_ok` 里，批次总字节判在 `apply` 里且
   **走在 trim/lowercase 那趟 O(n) 变换之前**（拒收一批不该先把它整趟读一遍）。
3. 三个 64 KiB 常量（`c_abi::FFI_INPUT_MAX_BYTES` / `ffi::MAX_FFI_URL_BYTES` /
   `denylist::MAX_BATCH_BYTES`）必须同值。「同值」是 RS-173 写进注记的口径，三面各抄一份就是
   漂移面；本判据**现读三份再比**，不在代码里写字面 65536。
4. 单条上限必须与 `ffi` 面的 host 长度口径（管线 domain / scope / 会话键 / 脱敏 host）同值——
   同样现读现比。

退出码：0=通过 / 1=任一判据不成立 / 2=判定面塌缩（受管文件读不到、锚点找不到——函数被改名或
文件被换，此时「没发现问题」不代表「没有问题」）。
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT / "core" / "rust-policy-core" / "src"

SEED_FILE = CORE / "ffi" / "mod.rs"
CABI_FILE = CORE / "c_abi" / "mod.rs"
BROKER_FILE = CORE / "ffi" / "broker.rs"
DENYLIST_FILE = CORE / "ffi" / "broker" / "denylist.rs"
TEXTS = (SEED_FILE, CABI_FILE, BROKER_FILE, DENYLIST_FILE)

# 「一批能送多少」的同一口径，写在三个文件里（判据 3）
BIG_BATCH_CONSTS = (
    (CABI_FILE, "FFI_INPUT_MAX_BYTES"),
    (SEED_FILE, "MAX_FFI_URL_BYTES"),
    (DENYLIST_FILE, "MAX_BATCH_BYTES"),
)
# 「一个 host 能多长」的同一口径（判据 4）；denylist 那份是被比对者
HOST_LEN_CONSTS = (
    (SEED_FILE, "MAX_PIPELINE_DOMAIN_BYTES"),
    (BROKER_FILE, "MAX_SCOPE_BYTES"),
    (BROKER_FILE, "MAX_SESSION_KEY_BYTES"),
    (BROKER_FILE, "MAX_REDACT_HOST_BYTES"),
)
ENTRY_CAP_CONST = "MAX_ENTRY_BYTES"

sys.path.insert(0, str(ROOT / "scripts"))
from text_anchors import strip_comments  # 剔注释口径单源（R9-B45）


def key(path: Path) -> str:
    """判定面的键 = 相对路径——`mod.rs` 与 `broker.rs` 各有两份，文件名不够唯一。"""
    return path.relative_to(ROOT).as_posix()


def code_only(path: Path) -> str:
    """读一份源文件并剔注释——注释里的形态不算证据（R9-B39）。"""
    return strip_comments(path.read_text(encoding="utf-8", errors="ignore"), key(path))


def load_texts(paths=TEXTS) -> dict[str, str]:
    return {key(p): code_only(p) for p in paths if p.exists()}


def const_value(texts: dict[str, str], path: Path, name: str) -> int | None:
    """读 `const NAME: usize = <表达式>;`，只认十进制与 `*`（够本仓这几个常量用）。

    解不开就当缺失返回 None——调用方按「判定面塌缩」处理，而不是按 0 参与比较。
    """
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


def seed_problems(seed: str) -> list[str]:
    """判据 1：定长判定走在解码之前，且比的数由返回类型推出。"""
    body = fn_body(seed, "hex_seed_to_bytes")
    if body is None:
        return ["`hex_seed_to_bytes` 不在位——判据面已失效，请连同本文件一起改"]
    decoded = body.find("hex_decode(")
    if decoded < 0:
        return ["`hex_seed_to_bytes` 不再经 `hex_decode` 解码——换了解码面，请重判这条"]
    guard = re.search(r"(\w+)\.len\(\)\s*(?:!=|==|<=?|>=?)\s*([A-Za-z_]\w*)", body[:decoded])
    if not guard:
        return [
            "长度判定没有走在 `hex_decode` 之前：任意偶数长度的宿主输入会先换来一次 "
            "`with_capacity(len/2)` 的等长分配（R8-RS-13 的缺陷形态原样回来）"
        ]
    width = re.search(r"->\s*Option<\[u8;\s*(\d+)\]>", seed)
    if not width:
        return ["`hex_seed_to_bytes` 的返回类型读不出来——判据 1 的第二半无从推出"]
    expected = int(width.group(1)) * 2
    actual = const_value({key(SEED_FILE): seed}, SEED_FILE, guard.group(2))
    if actual is None:
        return [f"长度判定比的 `{guard.group(2)}` 不是本文件里可解开的 `usize` 常量"]
    if actual != expected:
        return [
            f"长度判定比的是 {actual}，而契约要求的定长是 {expected}"
            f"（返回 [u8; {width.group(1)}] 的 hex 字符数）——护栏与契约不是同一个数"
        ]
    return []


def denylist_problems(texts: dict[str, str]) -> list[str]:
    """判据 2：两条上限在位，且批次判在 O(n) 变换之前。"""
    denylist = texts[key(DENYLIST_FILE)]
    shape = fn_body(denylist, "entry_shape_ok")
    apply = fn_body(denylist, "apply")
    if shape is None or apply is None:
        return ["黑名单的 `entry_shape_ok`/`apply` 不在位——判据面已失效，请连同本文件一起改"]
    problems: list[str] = []
    if ENTRY_CAP_CONST not in shape:
        problems.append(
            f"`entry_shape_ok` 不再引用 `{ENTRY_CAP_CONST}`：超长条目会进表，"
            "而它不可能命中任何被规范化的 host（死条目形态）"
        )
    cap_at = apply.find("MAX_BATCH_BYTES")
    transform_at = apply.find("host.trim()")
    if cap_at < 0:
        problems.append("`apply` 里没有了批次总字节判定：uniffi 面的 Vec<String> 没有任何外层上限")
    elif transform_at >= 0 and cap_at > transform_at:
        problems.append(
            "批次上限走在 trim/lowercase 之后：拒收一批之前先把它整趟读了一遍，"
            "判据 2 要的是**先拒再算**"
        )
    return problems


def parity_problems(texts: dict[str, str]) -> list[str]:
    """判据 3+4：同一口径的常量组必须同值（现读现比，不抄字面）。"""
    problems: list[str] = []
    groups = (("64 KiB 批次口径", BIG_BATCH_CONSTS), ("host 长度口径", HOST_LEN_CONSTS))
    for label, group in groups:
        values = {name: const_value(texts, path, name) for path, name in group}
        missing = sorted(name for name, value in values.items() if value is None)
        if missing:
            problems.append(f"{label}读不出值：{missing}（常量被改名或换了写法，判据需重判）")
            continue
        if len(set(values.values())) > 1:
            detail = "、".join(f"{name}={value}" for name, value in sorted(values.items()))
            problems.append(f"{label}出现分叉：{detail}")
    entry = const_value(texts, DENYLIST_FILE, ENTRY_CAP_CONST)
    family = {name: const_value(texts, path, name) for path, name in HOST_LEN_CONSTS}
    if entry is None:
        problems.append(f"`{ENTRY_CAP_CONST}` 读不出值——单条上限不在位")
    elif None not in family.values() and len(set(family.values()) | {entry}) > 1:
        detail = "、".join(f"{name}={value}" for name, value in sorted(family.items()))
        problems.append(f"`{ENTRY_CAP_CONST}={entry}` 与 ffi 面的 host 长度口径分叉：{detail}")
    return problems


def check(texts: dict[str, str]) -> list[str]:
    """全部判据；返回问题清单（空=通过）。受管文件读不到按判定面塌缩报。"""
    missing = [key(p) for p in TEXTS if key(p) not in texts]
    if missing:
        return [f"受管源文件读不到，判定面塌缩：{missing}"]
    return (
        seed_problems(texts[key(SEED_FILE)])
        + denylist_problems(texts)
        + parity_problems(texts)
    )


def run() -> int:
    texts = load_texts()
    if len(texts) < len(TEXTS):
        missing = sorted(key(p) for p in TEXTS if key(p) not in texts)
        print(f"[环境错误] 受管源文件读不到：{missing}", file=sys.stderr)
        return 2
    problems = check(texts)
    if problems:
        for line in problems:
            print(f"❌ {line}")
        print(f"共 {len(problems)} 条（口径见本文件 docstring）")
        return 1
    batch = const_value(texts, SEED_FILE, "MAX_FFI_URL_BYTES")
    entry = const_value(texts, DENYLIST_FILE, ENTRY_CAP_CONST)
    print(
        f"[ok] FFI 前置上限判据通过：批次口径三面同值 {batch} 字节；"
        f"单条 host 上限 {entry} 字节（与 ffi 面 host 长度口径同值）"
    )
    return 0


if __name__ == "__main__":
    sys.exit(run())

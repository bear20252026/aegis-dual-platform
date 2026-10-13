#!/usr/bin/env python3
"""verify_core_unwired_modules.py —— 核心「已编译但未接线」模块的声明对账（R9-B36 / Q28）。

失效模式：`README.md` 把「Ed25519 阈值验证」等能力列进策略核心的**运行时裁决面**，而
`update_manifest` 这类模块其实**没有任何 C ABI/UniFFI 入口**、宿主一次也没调用过
（出货路径的清单验证在 Python 发布链 `release/update_verifier.py`）。文档这样写的代价不是
「不美观」：下一批会按「核心已经判了」去做接线取舍，或直接引用它当安全保证。

判据只用**可sound化的三类事实**，不做自制的可达性分析（第一版尝试用 BFS 推可达集，
`super::` 引用与目录型模块把它推成了错结论——那种判据看着像但不准，本仓不收）：

1. 登记表里的每个模块必须仍是 `pub mod`（改名/删除要同批改表）；
2. 接入层（`src/c_abi/**`、`src/ffi/**`）**剔注释后不得出现模块名的 token**——
   真要把模块接进运行时链，必然先在这里出现一次引用（这是双向不变量：
   登记了却已被接线 ⇒ 判红，必须删登记并同步 README，同 `verify_vector_consumers.py`）；
3. 模块自身文件里不得有 `#[no_mangle]` / `uniffi::export`（导出即接线，同样要改表）；
4. README 的那一行必须逐字含由登记表生成的模块名清单（陈述与实树同一集合）；
5. README 里凡提到「Ed25519 阈值验证」的那一条必须同时给出执行路径
   （`update_verifier`）——两处失实陈述（策略核心表行、目录树）都由这条兜。

接线时的坑（本门禁把 `https_only` 判为未接线，有人照 README 接上去就会撞）：`HttpsOnlyState::upgrade()` 只判运营者手工白名单，**不含** B8 的回环/RFC1918/CGNAT/`.local` 段豁免 ⇒ 直接接进导航链会把 `http://192.168.1.1` 升 https，复现 R8-AD-01；用户 2026-10-04 的「本机与内网必须能打开」裁决不可回退。
（写在这里而不是模块头注记里：`https_only.rs`/`update_manifest.rs` 都在 `check_file_sizes` 的零余量基线上，加注记即增行判红。）

退出码：0=一致 / 1=失实或漂移 / 2=环境或扫描面塌缩。
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

# R9-B45 / Q59：剔注释口径单源。本文件此前自己写的是「`//` 切到行尾」，那是**过剔**——
# 字符串里的 `https://` 会连同后半行一起吃掉。换成整行形态后，与向量消费面门禁、
# Kotlin 的 withoutComments()、C# 的 SourceTextAnchors.CodeOnly 同口径。
# 传入文件路径：`#` 只在其语言的注释里剔，Rust 的 `#[unsafe(no_mangle)]` 是代码
# （R9-B45 第一版无差别剔 `#`，把「接入层长出导出属性＝接线」的注入用例由红变绿）。
from text_anchors import strip_comments

ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT / "core" / "rust-policy-core" / "src"
LIB_RS = CORE / "lib.rs"
README = ROOT / "README.md"

# 接入层：宿主唯一能碰到的两面（C ABI 与 UniFFI 绑定都在这些目录里落地）
INTERFACE_DIRS = ("c_abi", "ffi")

# README 里那句陈述的锚——改这句话必须让本门禁与 README 一起改，二者不能各说各的
README_MARKER = "无 C ABI/UniFFI 入口、运行时零调用"

# 实测登记（2026-10-12：以下模块在 src/ 内除自身文件/自身目录与自身测试外**零引用**，
# 且不在任何导出面上）。逐条人工复核过，不是 BFS 结论。
UNWIRED = (
    "adblock",
    "bridge_guard",
    "executor",
    "https_only",
    "js_inject",
    "oracle",
    "session_state",
    "update_manifest",
)


def rel(path: Path) -> str:
    """报告用相对路径。`relative_to` 在路径不同根时会抛——门禁必须**报告**而不是
    抛栈（用例注入假目录时实测撞出来过）。"""
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def expected_readme_fragment() -> str:
    return README_MARKER + "：" + "、".join(f"`{m}`" for m in sorted(UNWIRED))


def interface_sources() -> list[Path]:
    out: list[Path] = []
    for d in INTERFACE_DIRS:
        base = CORE / d
        if not base.is_dir():
            raise FileNotFoundError(f"接入层目录缺失：{base}")
        out.extend(sorted(base.rglob("*.rs")))
    return out


def declared_modules(lib_text: str) -> list[str]:
    return re.findall(r"^pub mod ([a-z_][a-z0-9_]*)\s*;", lib_text, re.MULTILINE)


def wiring_hits(mod: str, texts: dict[Path, str]) -> list[str]:
    token = re.compile(rf"\b{re.escape(mod)}\b")
    hits: list[str] = []
    for path, body in texts.items():
        if token.search(body):
            hits.append(rel(path))
    return hits


def export_attrs_in(mod: str) -> list[str]:
    files = [CORE / f"{mod}.rs"]
    if (CORE / mod).is_dir():
        files.extend(sorted((CORE / mod).rglob("*.rs")))
    found: list[str] = []
    for f in files:
        if not f.is_file():
            continue
        body = strip_comments(f.read_text(encoding="utf-8", errors="ignore"), f.name)
        if "#[no_mangle]" in body or "unsafe(no_mangle)" in body or "uniffi::export" in body:
            found.append(rel(f))
    return found


def check(lib_text: str, interface_texts: dict[Path, str], readme_text: str) -> list[str]:
    problems: list[str] = []
    declared = set(declared_modules(lib_text))
    for mod in UNWIRED:
        if mod not in declared:
            problems.append(f"{mod}：登记表说它是核心模块，lib.rs 里却没有 `pub mod {mod};`")
        if wiring_hits(mod, interface_texts):
            problems.append(
                f"{mod}：接入层已出现引用（{', '.join(wiring_hits(mod, interface_texts))}）"
                "——它不再属于「未接线」面，必须删登记并同步 README 的陈述")
        if export_attrs_in(mod):
            problems.append(
                f"{mod}：自身文件里有导出属性（{', '.join(export_attrs_in(mod))}）"
                "——导出即接线，README 的「运行时零调用」就是失实陈述")
    fragment = expected_readme_fragment()
    if fragment not in readme_text:
        problems.append(
            f"README 缺逐字锚（陈述必须与登记表同一集合）：应含「{fragment}」")
    # README 里凡提到「Ed25519 阈值验证」，同一条里必须给出**执行路径**——
    # 失实形态就是把核心里那个未接线的实现当成出货链上在做的那件事（本条就是这么来的：
    # 策略核心表行与目录树两处都把它列成核心裁决面，而实际执行在发布链）。
    for lineno, line in enumerate(readme_text.splitlines(), start=1):
        if "Ed25519" in line and "update_verifier" not in line:
            problems.append(
                f"README.md:{lineno} 提到 Ed25519 阈值验证却没写执行路径"
                f"（应含 `release/update_verifier.py`）——核心那份未接 ABI")
    return problems


def main() -> int:
    if not LIB_RS.is_file() or not README.is_file():
        print("[fail] lib.rs 或 README.md 缺失", file=sys.stderr)
        return 2
    lib_text = LIB_RS.read_text(encoding="utf-8", errors="ignore")
    readme_text = README.read_text(encoding="utf-8", errors="ignore")
    files = interface_sources()
    interface_texts = {p: strip_comments(p.read_text(encoding="utf-8", errors="ignore"), p.name) for p in files}
    # 扫描面塌缩守卫：接入层空 / 模块声明面异常小 ⇒ 判据本身不可信（exit 2）
    if not files or len(declared_modules(lib_text)) < 10 or not UNWIRED:
        print(f"[fail] 扫描面塌缩：接入层 {len(files)} 文件、"
              f"lib.rs 声明 {len(declared_modules(lib_text))} 个（判据面不可信）", file=sys.stderr)
        return 2
    problems = check(lib_text, interface_texts, readme_text)
    if problems:
        for p in problems:
            print(f"[fail] {p}", file=sys.stderr)
        return 1
    print(f"[ok] 核心未接线面与 README 同一集合（{len(UNWIRED)} 个模块、"
          f"接入层 {len(files)} 文件零引用、导出面零命中）")
    return 0


if __name__ == "__main__":
    sys.exit(main())

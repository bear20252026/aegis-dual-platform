#!/usr/bin/env python3
"""verify_injected_js_parity.py —— 第九轮 2026-10-10 定稿项 9 步 1：三端注入 JS 同形对账。

钉的是「三端各自抄写的那段共享 JS，逻辑序列必须一致」。现有两道门禁都不判这个：

* `verify_seed_framing_parity.py` 只查每端**是否含**几个要件 token（`var anc =
  location.ancestorOrigins;` 等），有人改算法它照样绿；
* `core/rust-policy-core/tests/canvas_read_channels.rs` 对两端只查 5 段片段（第九轮
  R9-RS-7 记的正是这个余量），删掉一条守卫不会红。

解释层（怎么从宿主源码里把 JS 函数体取出来、怎么规范化）在 `injected_js_text.py`——
本文件只讲判据。口径与边界（**逐 token 而不是逐字节**，为什么不能更严）：

1. 逐字节今天做不到：三端的 JS 各自嵌在宿主语言的字面量里（Rust `format!` 的
   `{{`/`}}` 转义、C# 12 空格缩进的原语串、Kotlin 6 空格缩进）。真要逐字节，得有一端
   出**生成物**——那是定稿项 9 步 2，已交用户定稿。本门禁比的是「剥掉宿主形态后的
   逻辑序列」：注释、缩进、标点旁空白不参与，**字符串字面量与标识符参与比较**。
2. 声明关键字 var/let/const 归一后再比（三端确有 `const orig` vs `var orig` 的分歧，
   无行为差，判它只会让人调松门禁）；种子访问器 `aegisCanvasSeed()` / `noiseSeed()`
   与**注册器取用路径** `registerProxy` / `__aegisReg` / `window[Symbol.for('…')]`
   同理归一——那是各端的宿主接线（别名表逐条写明并限定键名，见 `injected_js_text`）。
3. 只比**三端共有**的函数名。单端独有的（实测 Kotlin 15 个、C# 5 个、Rust 2 个，
   各自宿主接口不同）不在判定面，写在这里是为了下轮别把它们当漂移。
4. `SHARED_CORE` 是**下界钉表**：三端少掉任何一个 ⇒ 判「共有面塌缩」而不是「通过」。
   这与本仓所有门禁的「扫到 0 项即环境错误」同口径。
5. `DIVERGENT_REGISTERED` 是显式挂起表（R9-RS-9 之后**为空**——两条 read 包装已收编，
   见下面注释）。它**不是**普通白名单：`violations()` 会核对表里每一条**确实仍然不同形**——
   哪天被修齐，本门禁就判红一次并要求收编。豁免悄悄长大是所有白名单式门禁的
   通用失效形态，`--self-test` 里专门有一条注入用例证这件事判得出。

退出码：0=一致 / 1=任一端漂移或豁免表失真 / 2=环境错误（文件缺失、解析不到函数）。
用法：
    python contracts/codegen/verify_injected_js_parity.py
    python contracts/codegen/verify_injected_js_parity.py --self-test
"""
from __future__ import annotations

import pathlib
import sys

from injected_js_text import canonicalize, extract_functions, read

ROOT = pathlib.Path(__file__).resolve().parents[2]

# 每端注入文本的落点。canvas 段在第八轮 ⑦ 之后各自外迁（见 verify_seed_framing_parity
# 同侧注记）。路径写成模块级变量：测试要能 monkeypatch 单个属性来做故障注入。
RS_FILES = (
    "core/rust-policy-core/src/shield.rs",
    "core/rust-policy-core/src/shield/canvas.rs",
)
CS_FILES = (
    "windows/src/Aegis.Windows.App/WebView/FingerprintShield.cs",
    "windows/src/Aegis.Windows.App/WebView/FingerprintShield.Canvas.cs",
    "windows/src/Aegis.Windows.App/WebView/FingerprintShield.Seed.cs",
)
KT_FILES = (
    "android/app/src/main/java/com/aegis/browser/WebViewHardening.kt",
    "android/app/src/main/java/com/aegis/browser/WebViewHardeningStagesSeed.kt",
    "android/app/src/main/java/com/aegis/browser/WebViewHardeningStagesShield.kt",
    "android/app/src/main/java/com/aegis/browser/WebViewHardeningCanvas.kt",
)

# 必须三端同形、且任何一个都不许从共有面消失（第九轮实测的共有集全体）。
# aegisNoiseRectangle / aegisNoiseMix / aegisNudge = 像素噪声本体（⑦ 的三条出口共用）；
# aegisHostFromOrigin / aegisTopLevelHostname = 顶层站框定（R7-CS1-05 的命门）。
SHARED_CORE = (
    "aegisHostFromOrigin",
    "aegisNoiseMix",
    "aegisNoiseRectangle",
    "aegisNudge",
    "aegisTopLevelHostname",
    "aegisWrapReadPixels",
    "aegisWrapRectRead",
)

# 显式挂起表。**R9-RS-9 之后为空**——两条像素直读包装已在第九轮收编：
#   · 注册尾三端同形：`try { if (REG) REG(proxy, orig); } catch (e) {}`
#     （C# 此前裸调 registerProxy、Kotlin 此前裸调 __aegisReg——注册器抛异常会中断整个
#      包裹安装，那等于把「不加噪的原文直读」重新放出来；现在两端都补了 try）；
#   · Kotlin rect-read 的 catch 体此前自带 `return orig.apply(...)`，与 Rust/C# 的
#     「空 catch + 落到统一 return」行为相同而写法不同，现改成同形写法；
#   · 三端**注册器取用路径**仍各自不同，由 `injected_js_text._REGISTER_ACCESSOR` 归一
#     （Windows 用 ToStringGuard 闭包内的本地 `registerProxy`，有意不发布到 window——
#      比 Rust/Android 的 `Symbol.for('proxy.register.v1')` 入口更严，页面脚本拿不到
#      注册句柄。把 Windows 也统一到 window 键上是**放宽出货面**，属安全姿态变更，
#      已列台账第四节待用户定稿，不在本批顺手做）。
# 本表若非空，`violations()` 会核对每一条**确实仍然不同形**——哪天修齐就判红并要求
# 收编（豁免悄悄长大是所有白名单式门禁的通用失效形态，`--self-test` 有专门用例）。
DIVERGENT_REGISTERED: tuple[str, ...] = ()


def ends_specs() -> dict[str, tuple[pathlib.Path, ...]]:
    """端 → 该端注入文本所在文件。做成函数而非常量表：路径须经模块属性解析，
    故障注入时改属性才有效（常量表在导入期就把路径钉死）。"""
    return {
        "Rust": tuple(ROOT / rel for rel in RS_FILES),
        "C#": tuple(ROOT / rel for rel in CS_FILES),
        "Kotlin": tuple(ROOT / rel for rel in KT_FILES),
    }


def per_end_tables() -> dict[str, dict[str, str]]:
    tables: dict[str, dict[str, str]] = {}
    for end, paths in ends_specs().items():
        text = "\n".join(read(path) for path in paths)
        tables[end] = extract_functions(text)
    return tables


def shared_names(tables: dict[str, dict[str, str]]) -> set[str]:
    return set.intersection(*[set(table) for table in tables.values()])


def divergent_shared_names(tables: dict[str, dict[str, str]]) -> set[str]:
    """三端规范化后**确实不同形**的共有函数名（豁免表真实性核对用）。"""
    diverging: set[str] = set()
    for name in shared_names(tables):
        forms = {canonicalize(table[name], end) for end, table in tables.items()}
        if len(forms) != 1:
            diverging.add(name)
    return diverging


def violations() -> list[str]:
    tables = per_end_tables()
    counts = {end: len(table) for end, table in tables.items()}
    if min(counts.values()) == 0:
        raise SystemExit(f"❌ 某端解析到 0 个函数（扫描面塌缩，不作通过）：{counts}")
    shared = shared_names(tables)
    lost = sorted(set(SHARED_CORE) - shared)
    if lost:
        return [f"三端共有面缺核心函数：{lost}（被改名或删除？共有集现含 {sorted(shared)}）"]
    problems: list[str] = []
    stale = sorted(name for name in DIVERGENT_REGISTERED if name not in divergent_shared_names(tables))
    if stale:
        problems.append(f"已登记的不同形项现在已同形，必须从 DIVERGENT_REGISTERED 删掉并收进比较面：{stale}")
    for name in sorted(shared - set(DIVERGENT_REGISTERED)):
        forms = {end: canonicalize(table[name], end) for end, table in tables.items()}
        if len(set(forms.values())) == 1:
            continue
        reference = forms["Rust"]
        detail = [
            f"{end}：{_first_difference(reference, forms[end])}"
            for end in ("C#", "Kotlin")
            if forms[end] != reference
        ]
        problems.append(f"{name} 三端不同形——" + "；".join(detail))
    return problems


def _first_difference(reference: str, other: str, context: int = 70) -> str:
    for index, (left, right) in enumerate(zip(reference, other)):
        if left != right:
            start = max(0, index - 24)
            return (
                f"第 {index} 字符起分叉 ｜ 参照 …{reference[start:index + context]}… "
                f"｜ 本端 …{other[start:index + context]}…"
            )
    extra = reference[len(other):] if len(reference) > len(other) else other[len(reference):]
    return f"前 {min(len(reference), len(other))} 字符相同但长度不同（{len(reference)} vs {len(other)}）｜ 差段 …{extra[:context]}…"


def _find_holder(end: str, mutate) -> pathlib.Path | None:
    """选出含注入锚点的那个文件——各端函数分散在多个文件里，随便挑一个会「注入了但没改动」。"""
    for path in ends_specs()[end]:
        text = read(path)
        if mutate(text) != text:
            return path
    return None


def self_test() -> int:
    """注入四类失真，逐条确认真的会红（恒绿门禁不算门禁）。"""
    cases = [
        ("C# 改一个分支", "C#", lambda s: s.replace("if (current === 255) return 254;",
                                                    "if (current === 255) return 253;", 1),
         "aegisNudge"),
        ("Rust 改顶层框定", "Rust", lambda s: s.replace("anc && anc.length > 0",
                                                        "anc && anc.length > 1", 1),
         "aegisTopLevelHostname"),
        ("Kotlin 核心函数改名", "Kotlin", lambda s: s.replace("function aegisNoiseMix(",
                                                              "function aegisNoiseMixKt("),
         "缺核心函数"),
        # R9-RS-9 收编后的两条正向判据：注册尾**形状**与别名表**键名边界**。
        ("C# 注册尾丢掉 try", "C#", lambda s: s.replace(
            "try { if (registerProxy) registerProxy(owner.readPixels, orig); } catch (e) {}",
            "registerProxy(owner.readPixels, orig);", 1),
         "aegisWrapReadPixels"),
        ("Rust 换成未登记的 Symbol 键", "Rust", lambda s: s.replace(
            "window[Symbol.for('{reg_sym}')](owner.readPixels, orig)",
            "window[Symbol.for('{close_sym}')](owner.readPixels, orig)", 1),
         "aegisWrapReadPixels"),
    ]
    failures = 0
    # 反「豁免悄悄长大」：把一条**实际已同形**的函数塞进登记豁免表，必须被判出。
    # 这条不碰源文件——它测 violations() 里对 DIVERGENT_REGISTERED 的真实性核对。
    saved = DIVERGENT_REGISTERED
    try:
        globals()["DIVERGENT_REGISTERED"] = tuple(saved) + ("aegisNudge",)
        stale_hit = any("已登记的不同形项现在已同形" in problem for problem in violations())
    finally:
        globals()["DIVERGENT_REGISTERED"] = saved
    mark = "✅" if stale_hit else "❌"
    print(f"{mark} 自证 豁免表塞进一条已同形函数 → 必须判红")
    failures += 0 if stale_hit else 1

    for name, end, mutate, expect in cases:
        target = _find_holder(end, mutate)
        if target is None:
            print(f"❌ 自证 {name}：找不到含锚点的文件（注入点失配）")
            failures += 1
            continue
        original = read(target)
        mutated = mutate(original)
        target.write_text(mutated, encoding="utf-8", newline="")
        try:
            found = violations()
        finally:
            target.write_text(original, encoding="utf-8", newline="")
        if read(target) != original:
            print(f"❌ 自证 {name}：未能逐字节还原 {target.name}——拒绝在污染工作树的状态下宣称通过")
            return 1
        hit = any(expect in problem for problem in found)
        print(f"{'✅' if hit else '❌'} 自证 {name} → {found[:1] or '未检出（门禁恒绿）'}")
        failures += 0 if hit else 1
    return 1 if failures else 0


def main(argv: list[str]) -> int:
    if "--self-test" in argv:
        return self_test()
    try:
        problems = violations()
    except SystemExit as exc:
        print(exc)
        return 2
    shared = shared_names(per_end_tables())
    if problems:
        print(f"❌ 三端注入 JS 同形对账失败 {len(problems)} 处：")
        for problem in problems:
            print("   -", problem)
        return 1
    compared = sorted(shared - set(DIVERGENT_REGISTERED))
    exempt = (f"；另有 {len(DIVERGENT_REGISTERED)} 个已登记不同形、不在比较面"
              f"（{' '.join(DIVERGENT_REGISTERED)}）") if DIVERGENT_REGISTERED else ""
    print(
        f"✅ 三端注入 JS 同形对账通过：比较 {len(compared)} 个共有函数（{' '.join(compared)}）"
        f"{exempt}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

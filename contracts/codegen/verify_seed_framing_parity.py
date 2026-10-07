#!/usr/bin/env python3
"""verify_seed_framing_parity.py —— 第七轮 R7-CS1-05 / R7-CS2-10 的对账门禁。

钉两件事（都是「三端各写一份」必然漂移的面）：

1. **站点框定口径**：指纹噪声种子必须按**顶层站** eTLD+1 派生（Brave 原文
   "Third party frames and script share the seed value of the top level eTLD+1
   domain"，见 core/rust-policy-core/src/per_site_seed.rs:17-19）。按本帧
   hostname 派生时，同一第三方跟踪帧在该用户的所有宿主站点上产出同一种子——
   加噪后的画布哈希本身就成了跨站持久标识符。三端（C#/Kotlin/Rust）都必须经
   aegisTopLevelHostname + ancestorOrigins 通道，且缺陷调用形态不得回归。

2. **公共后缀清单单源**：`contracts/policy/public-suffix-list.txt` 是唯一权威。
   Rust 端 `include_str!` 直接生成（零手抄）；C#/Kotlin 各持一份内嵌副本
   （运行期零 I/O 的代价），本门禁把两份副本与权威清单逐项对账。第七轮实测
   三份手抄表是 54/51/31 条：`user.github.io` 在含托管域条目的一侧 eTLD+1 是
   `user.github.io`，在不含的一侧是 `github.io` —— 同一用户的全部 GitHub Pages
   站点共享一种子，跨站关联面正好从侧门回来。

退出码：0=一致 / 1=任一端漂移 / 2=环境错误（文件缺失、锚点解析不到、清单为空——
绝不因"扫到 0 条"而判通过）。
"""

from __future__ import annotations

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
LIST_PATH = ROOT / "contracts" / "policy" / "public-suffix-list.txt"

CS_SEED = ROOT / "windows/src/Aegis.Windows.App/WebView/FingerprintShield.Seed.cs"
CS_MAIN = ROOT / "windows/src/Aegis.Windows.App/WebView/FingerprintShield.cs"
# R8-CS-SEC-14（第八轮）：WebViewHardening 的 9 阶段注入文本按 Stage 边界外迁成两个文件，
# `KT` 因此指代表体所在的**种子段**（Stage 1-3），框定要件横跨三段 ⇒ 下面按三段之和判定。
KT_MAIN = ROOT / "android/app/src/main/java/com/aegis/browser/WebViewHardening.kt"
KT = ROOT / "android/app/src/main/java/com/aegis/browser/WebViewHardeningStagesSeed.kt"
KT_TAIL = ROOT / "android/app/src/main/java/com/aegis/browser/WebViewHardeningStagesShield.kt"
# ⑦（第八轮）：Kotlin 的 Stage 3 canvas 文本、Rust/C# 的 canvas 段各自再外迁一份，
# 要件横跨这些文件 ⇒ 面必须跟着长，少读一份就是「读残缺面仍恒绿」。
KT_CANVAS = ROOT / "android/app/src/main/java/com/aegis/browser/WebViewHardeningCanvas.kt"
RS = ROOT / "core/rust-policy-core/src/shield.rs"
RS_CANVAS = ROOT / "core/rust-policy-core/src/shield/canvas.rs"
CS_CANVAS = ROOT / "windows/src/Aegis.Windows.App/WebView/FingerprintShield.Canvas.cs"

# 表体下限：权威清单条目数低于此值即视为「解析塌陷/清单被清空」，判环境错误
MIN_ENTRIES = 40

# 每端的顶层框定要求：必须出现的通道 + 不得回归的缺陷调用形态。
# C# 的模板分两爿（主体 + Seed.cs 的注入片段），产出的脚本是两者拼接结果，
# 故对 C# 读两爿之和——只查主体会漏掉 helper 本体。
# 写成函数而非模块常量：路径经模块级变量解析，测试才能 monkeypatch 出故障注入
# （常量表把路径在导入期固死，注入就变成"改了副本、门禁仍读原件"的假红/假绿）。
# 要件串一律取**代码形态**（`var anc = location.ancestorOrigins;`）——只写
# `location.ancestorOrigins` 时，一句注释就能顶掉整条要件（锚点空心化）。
REQUIRED_CHANNEL = ("var anc = location.ancestorOrigins;", "return location.hostname;")
FORBIDDEN_FRAME_ONLY = ("getETLD1(location.hostname)", "aegisEtldPlus1(location.hostname")


def framing_specs() -> dict[str, tuple[list[pathlib.Path], tuple[str, ...], tuple[str, ...]]]:
    return {
        "C#": ([CS_MAIN, CS_SEED, CS_CANVAS],
               ("getETLD1(aegisTopLevelHostname())",) + REQUIRED_CHANNEL,
               FORBIDDEN_FRAME_ONLY),
        "Kotlin": ([KT_MAIN, KT, KT_TAIL, KT_CANVAS],
                   ("getETLD1(aegisTopLevelHostname())",) + REQUIRED_CHANNEL,
                   FORBIDDEN_FRAME_ONLY),
        "Rust": ([RS, RS_CANVAS],
                 ("aegisEtldPlus1(aegisTopLevelHostname() || '')",) + REQUIRED_CHANNEL,
                 FORBIDDEN_FRAME_ONLY),
    }


def read(path: pathlib.Path) -> str:
    if not path.is_file():
        raise SystemExit(f"❌ 门禁输入缺失：{path}")
    # newline=""：保留原文件换行符（本仓库工作副本是 CRLF——若归一成 LF 再写回，
    # 自证流程会把整份文件的行尾改掉，等于门禁自己污染源文件）。
    # 用 open 而非 Path.read_text(newline=)：后者要 Python 3.13+，CI 钉 3.12。
    with path.open(encoding="utf-8", newline="") as handle:
        return handle.read()


def authoritative_entries() -> list[str]:
    lines = [line.strip() for line in read(LIST_PATH).splitlines()]
    entries = [line for line in lines if line and not line.startswith("#")]
    if len(entries) < MIN_ENTRIES:
        raise SystemExit(f"❌ 权威清单仅 {len(entries)} 条（<{MIN_ENTRIES}）——判环境错误，不放行")
    if len(set(entries)) != len(entries):
        dupes = sorted({e for e in entries if entries.count(e) > 1})
        raise SystemExit(f"❌ 权威清单含重复条目：{dupes}")
    bad = [e for e in entries if not re.fullmatch(r"[a-z0-9][a-z0-9.-]*\.[a-z]{2,}", e)]
    if bad:
        raise SystemExit(f"❌ 权威清单条目形态非法：{bad[:5]}")
    return entries


def _slice(text: str, opener: str, closer: str, label: str) -> str:
    start = text.find(opener)
    if start < 0:
        raise SystemExit(f"❌ 解析不到 {label} 的表体起点（锚点失配即门禁失效，不静默跳过）")
    end = text.find(closer, start)
    if end < 0:
        raise SystemExit(f"❌ 解析不到 {label} 的表体终点")
    return text[start:end + len(closer)]


def kotlin_entries(text: str) -> list[str]:
    body = _slice(text, "var PUBLIC_SUFFIXES = [", "];", "Kotlin")
    return re.findall(r"'([^']+)'", body)


def csharp_entries(text: str) -> list[str]:
    body = _slice(text, "PublicSuffixes =", "];", "C#")
    return re.findall(r'"([^"]+)"', body)


def rust_uses_single_source(text: str) -> list[str]:
    """Rust 端不再手抄：必须 include_str! 权威清单，且 JS 表体由变量注入。"""
    problems = []
    if "../../../contracts/policy/public-suffix-list.txt" not in text:
        problems.append("Rust 未 include_str! 权威清单（改回手抄表？）")
    if "var AEGIS_PUBLIC_SUFFIXES = {psl};" not in text:
        problems.append("Rust JS 表体不是由单源清单渲染（{psl} 锚点失配）")
    # 手抄条目检测不能按行首锚定：把整张表写在一行上同样算回退到手抄
    #（第七轮自证实测——行首锚定时一行式手抄表静默过关）。
    # 只扫非注释行：文档注释里的示例（`{ 'co.uk': 1, … }`）不是表体，
    # 把它算进来会让门禁永远红着，从而被下一次"顺手放宽"吃掉。
    code = "\n".join(line for line in text.splitlines() if not line.strip().startswith("//"))
    hand_copied = re.findall(r"'[a-z0-9][a-z0-9.-]*': ?1", code)
    if hand_copied:
        problems.append(f"Rust 仍残留手抄表条目 {len(hand_copied)} 处")
    return problems


def _diff(label: str, mine: list[str], authoritative: list[str]) -> list[str]:
    mine_set, ref = set(mine), set(authoritative)
    if not mine_set:
        return [f"{label} 表体解析为 0 条（塌陷）"]
    problems = []
    missing = sorted(ref - mine_set)
    extra = sorted(mine_set - ref)
    if missing:
        problems.append(f"{label} 缺 {len(missing)} 条：{missing}")
    if extra:
        problems.append(f"{label} 多出 {len(extra)} 条：{extra}")
    if len(mine) != len(mine_set):
        problems.append(f"{label} 表内含重复条目")
    return problems


def violations() -> list[str]:
    authoritative = authoritative_entries()
    problems: list[str] = []
    problems += _diff("Kotlin", kotlin_entries(read(KT)), authoritative)
    problems += _diff("C#", csharp_entries(read(CS_SEED)), authoritative)
    problems += rust_uses_single_source(read(RS))
    for label, (paths, required, forbidden) in framing_specs().items():
        text = "".join(read(path) for path in paths)
        for token in required:
            if token not in text:
                problems.append(f"{label} 缺顶层框定要件：{token}")
        for token in forbidden:
            if token in text:
                problems.append(f"{label} 残留本帧口径缺陷形态：{token}")
    return problems


def self_test() -> int:
    """故障注入：植入四类漂移，逐条确认本门禁真的会红（恒绿门禁不算门禁）。"""
    cases = [
        ("Kotlin 少一条", lambda s: s.replace("'co.il',", "", 1), ["Kotlin 缺"]),
        ("C# 多一条", lambda s: s.replace('"co.uk",', '"co.uk","zq.example",', 1), ["C# 多出"]),
        ("Rust 回退手抄", lambda s: s.replace("var AEGIS_PUBLIC_SUFFIXES = {psl};",
                                             "var AEGIS_PUBLIC_SUFFIXES = {'co.uk': 1};"),
         ["{psl} 锚点失配"]),
        ("C# 退回本帧口径", lambda s: s.replace("getETLD1(aegisTopLevelHostname())",
                                                "getETLD1(location.hostname)", 1),
         ["残留本帧口径缺陷形态"]),
    ]
    planted = 0
    for name, mutate, expect in cases:
        if name.startswith("Kotlin"):
            target, text = KT, read(KT)
        elif name.startswith("C# 多"):
            target, text = CS_SEED, read(CS_SEED)
        elif name.startswith("Rust"):
            target, text = RS, read(RS)
        else:
            target, text = CS_MAIN, read(CS_MAIN)
        backup = text
        original_bytes = target.read_bytes()
        target.write_text(mutate(text), encoding="utf-8", newline="")
        try:
            found = violations()
        finally:
            target.write_text(backup, encoding="utf-8", newline="")
        if target.read_bytes() != original_bytes:
            print(f"❌ 自证未能逐字节还原 {target.name}——拒绝在污染工作树的状态下宣称通过")
            return 1
        hit = any(all(frag in problem for frag in expect) for problem in found)
        print(f"{'✅' if hit else '❌'} 自证 {name} → {found[:1] or '未检出（门禁恒绿）'}")
        planted += 0 if hit else 1
    return 1 if planted else 0


def main(argv: list[str]) -> int:
    if "--self-test" in argv:
        return self_test()
    try:
        problems = violations()
    except SystemExit as exc:
        print(exc)
        return 2
    if problems:
        print(f"❌ 种子框定/后缀清单漂移 {len(problems)} 处：")
        for problem in problems:
            print("   -", problem)
        return 1
    print(f"✅ 三端顶层框定一致、后缀清单与权威 {len(authoritative_entries())} 条逐项对账通过")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

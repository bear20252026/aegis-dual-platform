#!/usr/bin/env python3
"""verify_text_anchor_helpers.py —— 「按文本判源码前剔注释」这条纪律的**单源**门禁（R9-B45 / Q59）。

判什么：仓里每一处「自己写一遍注释过滤」的实现都会被数出来。收敛前这条纪律散在 14+ 份、
三种覆盖等级（具名 9 + 无具名内联 ≥5），其中「太窄」（只剔整行 `//`，块注释与星号续行不剔）
与「太宽」（切到行尾，连字符串里的 `https://` 一起吃掉）两种错法同时存在；而更根本的问题是
**没有任何东西会因为它散而变红**。

四条判据（每条都在 tests/python/text_anchor_helpers_test.py 里以内存态注入证伪）：
1. 实现点集合必须等于 ALLOWED——多一处（有人又写一份就地过滤）判红，少一处（白名单里的
   实现被改名/删掉，登记过期）同样判红（R9-SH-7 的双向不变量：过期声明与悄悄扩面同等致命）。
2. Kotlin 的 `withoutComments()` 定义必须恰好两份（`:app`/`:broker` 测试源集各一份——跨模块
   共享要动 Gradle testFixtures＝构建面，本仓故意留两份），且两份从定义行起除 package 外
   逐字相同；行为同形另由 `SourceTextAnchorSupportTest` 的同一组语料自证。
3. C# 那份共享实现必须以「链接源码」形式挂在**两个**测试工程上，否则它只是没人编译的死文件。
4. 命中口径本身先剔注释：本门禁若不过滤，就会把实现文件自己 docstring 里引用的被禁形态
   数成第二处命中（假红）——那正是这条纪律要防的事；所以本文件里的被匹配原文也全部
   **拼接构造**，不在此成串出现，否则门禁数到自己。

被禁形态的**写法面**也在长：MARKERS 起初只认「行前缀比较」那一类调用，认不出把过滤
写进正则常量的形态（R9-B64 / Q63——现树里唯一这样写的那处已并进单源，所以这条今天是
零命中的绊线，不是修一个已发生的漏网）。它在 `MARKERS` 下方写明自己判不到的三种写法，
不要当成全覆盖。

扫描面：`git ls-files` 的源码扩展名（与 check_file_sizes 同口径），只取「判据面」
（门禁脚本 + 各语言测试目录）——主源码与 vendor 产物里的行注释字面量是产品逻辑，不是锚口径。
退出码：0=通过 / 1=违规 / 2=环境或扫描面异常。
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))

from text_anchors import strip_comments  # 与被判对象同口径，不自建第二份

SOURCE_EXTENSIONS = (".py", ".cs", ".kt", ".kts", ".rs", ".js", ".mjs")
EXCLUDED_PARTS = ("/target/", "/obj/", "/bin/", "/node_modules/", "/build/", "/dist/")
GATE_ROOTS = ("scripts/", "tests/", "contracts/codegen/", "release/", "agent/")

_LINE = "/" + "/"
_HELPER = "without" + "Comments"
# 正则里写块注释起点是「斜杠 + 反斜杠 + 星号」三个字节；这里逐字节拼出**去匹配它自己**
# 的模式，本文件因此不成串出现该形态（判据 4 的同一条自豁免口径）。
_BLOCK_IN_RE = "/" + "\\\\" + "\\*"
# 一处「自己写了一份注释过滤」的长相：任一命中即算一个实现点。
MARKERS = (
    re.compile(r"def strip_" + "comments\\("),
    re.compile(r"public static string CodeOnly\("),
    re.compile(r'StartsWith\("' + _LINE + r'"\s*,'),
    re.compile(r'startsWith\("' + _LINE + r'"\s*\)'),
    re.compile(r'starts_with\("' + _LINE + r'"\)'),
    re.compile(r"fun String\." + _HELPER + r"\(\)"),
    # 过滤形态写进**正则常量**而不是行前缀调用（R9-B64 / Q63）：这一支之前看不见，
    # 于是「把三份就地过滤合并成一份正则常量」也能躲过本门禁。认的是「同一次 compile
    # 调用里、同一行内同时出行注释与块注释两种形态」。
    re.compile(r"compile\((?=[^\n]*" + _LINE + r")(?=[^\n]*" + _BLOCK_IN_RE + r")[^\n]*\)"),
)
# 判不到的残余形态如实写在这里，免得下一轮把它当成已覆盖：①两种形态分在**两次**
# compile 调用里；②块形态写成字符类（如 `[` 斜杠 星 `]`）而不是转义形态；③一行里两种
# 形态之间隔着别的右括号。为什么取「两种形态同现」而不是「含任一形态就算」：现读对照
# 是把 HEAD 那份未合并的门禁塞回内存态面再数——两条在今天**同样准**（各 1 处命中且就是
# 那一处；判据面上无关的正则里没有含双斜杠或字面块起点的）。取窄的那条是因为它对
# 「行注释形态单独出现」零敏感：URL／glob 类正则里出现 `//` 是合法产品逻辑，宽版迟早
# 给自己造假红。反例也记一条：把 `(?:` 当证据的写法实测 14 处命中、11 份文件里 13 处
# 与注释无关（本仓正则大量用非捕获组），那条处方已记进本轮 §六。

# 允许存在实现的位置：每语言一份源码锚口径 + 一条写明例外的 JS 文本面
# （注入用的 JS 原文，语料本身就是注释——套源码锚口径会把判据删变形，那是另一种模式）
ALLOWED = {
    "scripts/text_anchors.py",
    "contracts/codegen/injected_js_text.py",
    "windows/tests/Aegis.Windows.TestSupport/SourceTextAnchors.cs",
    "android/app/src/test/kotlin/com/aegis/browser/SourceTextAnchorSupport.kt",
    "android/broker/src/test/kotlin/com/aegis/broker/SourceTextAnchorSupport.kt",
}

KOTLIN_HELPER = "internal fun String." + _HELPER + "()"
CS_SHARED_LINK_NAME = "SourceText" + "Anchors.cs"
CS_PROJECTS = (
    "windows/tests/Aegis.Windows.Core.Tests/Aegis.Windows.Core.Tests.csproj",
    "windows/tests/Aegis.Windows.Broker.Tests/Aegis.Windows.Broker.Tests.csproj",
)
KOTLIN_COPY_MIN = 2


def is_judging_surface(rel: str) -> bool:
    """判据面：门禁脚本 + 各语言的测试面。"""
    if rel.startswith(GATE_ROOTS):
        return True
    return "/tests/" in f"/{rel}" or "/src/test/" in f"/{rel}"


def in_surface(rel: str) -> bool:
    return not any(part in f"/{rel}" for part in EXCLUDED_PARTS) and is_judging_surface(rel)


def implementation_sites(texts: dict[str, str]) -> set[str]:
    """纯函数：给定 path → 原文，返回「自己写了一份注释过滤」的判据面文件。"""
    return {
        rel
        for rel, raw in texts.items()
        if in_surface(rel) and any(marker.search(strip_comments(raw, rel)) for marker in MARKERS)
    }


def kotlin_helper_bodies(texts: dict[str, str]) -> dict[str, str]:
    """`withoutComments()` 定义所在文件 → 从定义行起的文本（用于逐字比对两副本）。"""
    return {
        rel: raw[raw.index(KOTLIN_HELPER):]
        for rel, raw in texts.items()
        if rel.endswith(".kt") and "/src/test/" in f"/{rel}" and KOTLIN_HELPER in raw
    }


def linked_projects(project_texts: dict[str, str]) -> list[str]:
    """列出把 C# 共享实现链接进来的测试工程（缺一个就是「写了没人编译」）。"""
    return [rel for rel in CS_PROJECTS if CS_SHARED_LINK_NAME in project_texts.get(rel, "")]


def violations(texts: dict[str, str], project_texts: dict[str, str]) -> list[str]:
    problems: list[str] = []
    hits = implementation_sites(texts)
    for extra in sorted(hits - ALLOWED):
        problems.append(f"新写了一份就地注释过滤（应引用各语言的单源 helper）：{extra}")
    for stale in sorted(ALLOWED - hits):
        problems.append(f"白名单里的实现点已不成立（登记过期，请同步本表）：{stale}")

    bodies = kotlin_helper_bodies(texts)
    if len(bodies) != KOTLIN_COPY_MIN:
        problems.append(f"Kotlin {_HELPER}() 定义数应为 {KOTLIN_COPY_MIN} 份，实为 {len(bodies)}")
    normalized = {re.sub(r"^package .*$", "", body, flags=re.M).strip() for body in bodies.values()}
    if len(bodies) == KOTLIN_COPY_MIN and len(normalized) != 1:
        problems.append(f"Kotlin 两份 {_HELPER}() 已各漂各的（除 package 行外必须逐字相同）")

    missing = sorted(set(CS_PROJECTS) - set(linked_projects(project_texts)))
    if missing:
        problems.append(f"C# 共享剔注释实现未被两个测试工程链接（缺：{', '.join(missing)}）")
    return problems


def managed_sources() -> list[str]:
    result = subprocess.run(
        ["git", "ls-files", "--", *(f"*{ext}" for ext in SOURCE_EXTENSIONS)],
        cwd=str(ROOT),
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if result.returncode != 0:
        raise RuntimeError(f"git ls-files 失败：{result.stderr.strip()}")
    return [rel for rel in result.stdout.splitlines() if rel.strip()]


def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8", errors="ignore")


def run() -> int:
    try:
        files = managed_sources()
    except RuntimeError as exc:
        print(f"[环境错误] {exc}", file=sys.stderr)
        return 2
    if not files:
        print("[环境错误] git ls-files 返回空面", file=sys.stderr)
        return 2
    texts = {rel: read(rel) for rel in files if in_surface(rel)}
    projects = {rel: read(rel) for rel in CS_PROJECTS if (ROOT / rel).is_file()}
    problems = violations(texts, projects)
    if problems:
        for line in problems:
            print(f"❌ {line}")
        print(f"共 {len(problems)} 条违规（口径见本文件 docstring）")
        return 1
    print(f"[ok] 剔注释口径单源（实现点 {len(ALLOWED)} 处：Python 源码锚/JS 文本面/C#/Kotlin 两份）")
    return 0


if __name__ == "__main__":
    sys.exit(run())

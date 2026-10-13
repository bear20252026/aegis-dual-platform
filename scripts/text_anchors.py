"""「按文本判源码」的唯一剔注释口径（R9-B45 / §五 Q59 R9-SH-17）。

这条纪律在本仓曾经**散了 14 份、三种覆盖等级**（具名 9 + 无具名的内联行过滤 ≥5），
其中两支各错各的：`verify_core_unwired_modules.py` 旧写法切「`//` 到行尾」，会把字符串里的
`https://` 一起吃掉＝**过剔**；C# 那五处内联过滤只剔整行 `//`，块注释与 ` * ` 续行**根本不剔**
＝太窄。同一件事有两种错法正是「没有单一出处」的症状，所以这里收一份，两边都引用它。

收敛过程中被自家套件抓出来的两笔（不是设想，是实测）：

1. **`#` 只对「哈希注释语言」成立**。把四种形态无差别套到 Rust 上，`#[unsafe(no_mangle)]`
   这类属性行会被当注释删掉——`core_unwired_modules_test` 的「接入层长出导出属性＝接线」
   注入用例当场由红变绿。所以 `strip_comments` 收 `path`，`#` 形态按扩展名生效。
2. **docstring 不是注释**。Python 的模块/函数 docstring 是字符串字面量，任何按行的剔除都
   够不着它——本文件第一版在 docstring 里逐字写了某份契约向量的文件名，于是
   `verify_vector_consumers` 立刻报出「该向量新增 PY 端消费者」。写这里的说明时
   **不要逐字写被观察的文件名/被禁形态**，那不是注记，是代码。

为什么不并进来的面有两处：① JS 文本面（`contracts/codegen/injected_js_text.py`）——那里的输入是
**注入用的 JS 文本**，正则不认识字符串边界，JS 自己的 `//` 与 `/* */` 就是它要处理的语料，
套这份「源码锚」口径会把判据删变形，那是另一种模式（文本面），不是这条纪律的第 15 份副本；
② shell / `.properties` 面（`drop_line_comments`）——glob 正文里的 `/*` 与 `*/` 是合法形态，
块注释匹配会删掉中间的真语句，理由与实测见那个函数自己的说明。
"""

from __future__ import annotations

import re

__all__ = ["drop_line_comments", "strip_comments"]

# 整行 `#` 只在这些扩展名里是注释；Rust 的属性行、C# 的预处理指令都不是。
_HASH_COMMENT_SUFFIXES = (".py", ".pyi", ".yml", ".yaml", ".toml", ".sh", ".bash", ".cfg", ".conf")


def strip_comments(text: str, path: str = "") -> str:
    """剔掉注释，只留代码——注释里的文件名/旧形态**不算证据**（R9-B39 / Q53）。

    两个方向都会坏：只在注记里出现的形态会让正向锚假绿；而本仓注记里逐字抄着被禁形态
    是传统（`InstalledBuildMarkerTests`、`ReservedAddressBoundaryTests` 这些文件的说明里
    就写着历史写法），不剔注释的反向锚会被自己的注记打红，为变绿最容易被做的是**删注记**
    ——丢掉的正是防止回归的那段上下文。所以判代码不判注释。

    形态顺序也是判据的一部分：**先剔整行注释，再剔块注释**。反过来做会吃掉真代码——
    `WebViewHardening.kt:41` 那句说明里写着 `"https://*"`，其中的第二个 `/` 紧跟 `*`
    就构成一个假块注释起点，一路匹配到下一个 `*/` 会把第 46 行的真语句一起删掉
    （R9-B45 收敛时实测撞出来：`DocumentStartInjectionRegressionTest` 的正面控制当场判红）。

    `path` 传相对路径（只为决定 `#` 形态是否生效；不参与别的判定）。
    行注释只认**整行**形态，不认行尾形态——后者会连字符串里的 `https://` 一起删。
    与 Kotlin 测试源集的 `withoutComments()`、C# 测试源集的 `SourceTextAnchors.CodeOnly`
    同口径（后两者都不处理 `#`：它们各自的源面里 `#` 整行不成串出现）。
    """
    text = re.sub(r"(?m)^\s*//.*$", "", text)          # 整行行注释（先做，见上面「顺序」）
    if path.endswith(_HASH_COMMENT_SUFFIXES):
        text = re.sub(r"(?m)^\s*#.*$", "", text)       # .py / .yml 等哈希注释
    text = re.sub(r"/\*[\s\S]*?\*/", "", text)         # C 系块注释（.cs/.kt/.js/.rs）
    text = re.sub(r"(?m)^\s*\*.*$", "", text)          # 块注释续行的对齐星号
    return text


def drop_line_comments(text: str, prefix: str = "#") -> str:
    """只按**整行前缀**剔注释，不做块匹配——给「正文里合法出现 /* 与 */」的面用。

    为什么单开一个函数而不是复用 `strip_comments`：shell 的 case/glob 正文里 `deps/*)` 与
    `*/gradle.lockfile)` 是同一段文本里的两个合法形态，块注释正则会把它们当成一个块的起止，
    **中间的真实语句一起删掉**——R9-B50 写 `tests/python/gradle_verification_test.py` 时实测
    撞出来：写回守卫的 `case "$changed" in` 整段消失，判据于是改在判空气（而且是**静默**消失，
    不报任何错）。那个面的语料里没有 C 系块注释，块匹配在这里只有破坏性。

    分工：源码面（.cs/.kt/.js/.rs）块注释真实存在，用 `strip_comments`；workflow 的 run 正文、
    `.properties` 这类只有「整行注释」一种形态，用本函数。两种口径各有唯一出处。
    """
    return "\n".join(line for line in text.splitlines() if not line.strip().startswith(prefix))


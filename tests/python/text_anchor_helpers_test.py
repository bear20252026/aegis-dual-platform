# text_anchor_helpers_test.py —— R9-B45（第九轮 Q59 / R9-SH-17）的门禁用例。
#
# 四条判据都要**能红**，所以每条配内存态注入的反向锚（不改工作树）：①多一处就地过滤；
# ②白名单里的实现点消失（登记过期）；③Kotlin 两副本数量或形状漂移；④C# 共享实现没被两个
# 测试工程链接。另配两条正面控制：现树必须全绿、且**本测试文件自己不能算实现点**——
# 用例里出现的被禁形态全部拼接构造，否则「测单源纪律」这件事自己就成了第二份副本（R9-B39
# 的同一条课：判据文本自己也是被扫的源码）。
#
# R9-B64（Q63）在①下加了一类写法面：过滤形态写进**正则常量**而不是行前缀调用。它配了
# 三个用例——能认出、只含一种形态时不算（URL/glob 正则是无关命中）、写在注释里不算。
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import verify_text_anchor_helpers as g

# 拼接构造：本文件里不成串出现被禁形态
_LINE = "/" + "/"
_HELPER = "without" + "Comments"
# 正则里写块注释起点是「斜杠 + 反斜杠 + 星号」；用 chr(92) 取反斜杠，本文件才不会被
# 自己新加的那条 MARKERS 数成实现点（判据 4 的同一条自豁免）
_BLOCK_FORM = "/" + chr(92) + "*"


def one_compile_line(inner: str) -> str:
    """包成一行 `re.compile("…")`——被测的是行内的注释形态，不是引号风格。"""
    return f'    _X = re.compile("{inner}")\n'


def regex_comment_filter() -> str:
    """「过滤形态写进正则常量」那一类就地实现的一行（R9-B64 / Q63 新认的形态）。"""
    return one_compile_line("(?:" + _LINE + "|" + _BLOCK_FORM + ")")


def cs_inline_filter(indent: str = "                ") -> str:
    return (
        "var code = string.Join(\"\\n\",\n"
        f"                text.Split('\\n')\n"
        f'{indent}.Where(line => !line.TrimStart().StartsWith("{_LINE}", StringComparison.Ordinal)));\n'
    )


def kotlin_helper(package: str, extra: str = "") -> str:
    return (
        f"package {package}\n\n"
        f"internal fun String.{_HELPER}(): String =\n"
        "    this\n"
        "        .replace(Regex(\"/\\\\*[\\\\s\\\\S]*?\\\\*/\"), \"\")\n"
        + extra
    )


def real_texts() -> dict[str, str]:
    files = g.managed_sources()
    return {rel: g.read(rel) for rel in files if g.in_surface(rel)}


def real_projects() -> dict[str, str]:
    return {rel: g.read(rel) for rel in g.CS_PROJECTS if (g.ROOT / rel).is_file()}


@pytest.fixture(scope="module")
def corpus() -> tuple[dict[str, str], dict[str, str]]:
    return real_texts(), real_projects()


def test_real_tree_passes(corpus) -> None:
    texts, projects = corpus
    assert g.violations(texts, projects) == []
    assert g.run() == 0


def test_scan_surface_is_not_collapsed(corpus) -> None:
    """现树若一张牌都不命中，上面那条绿灯就只是在判空气。"""
    texts, projects = corpus
    assert g.implementation_sites(texts) == g.ALLOWED
    assert len(g.implementation_sites(texts)) == 5
    assert len(g.kotlin_helper_bodies(texts)) == g.KOTLIN_COPY_MIN
    assert len(g.linked_projects(projects)) == len(g.CS_PROJECTS)


def test_the_test_file_itself_is_not_an_implementation_site(corpus) -> None:
    """正面控制的另一半：本文件写了被禁形态的**构造方法**，但不该被数成实现点。"""
    here = "tests/python/text_anchor_helpers_test.py"
    assert here in corpus[0]
    assert g.implementation_sites({here: corpus[0][here]}) == set()


def test_new_inline_filter_is_reported(corpus) -> None:
    texts, projects = corpus
    injected = dict(texts)
    injected["windows/tests/Aegis.Windows.Core.Tests/SneakyTests.cs"] = (
        "namespace Aegis.Windows.Core.Tests;\n\n"
        "internal static class Sneaky\n{\n"
        f"    private static string Code(string text) =>\n        {cs_inline_filter()}\n}}\n"
    )
    problems = g.violations(injected, projects)
    assert any("SneakyTests.cs" in p and "就地注释过滤" in p for p in problems), problems


def test_comment_mention_of_the_forbidden_form_is_not_an_implementation(corpus) -> None:
    """判据 4 的正面控制：同一句形态写在注释里不算实现，写在代码里才算。"""
    comment_only = {
        "windows/tests/Aegis.Windows.Core.Tests/Notes.cs": (
            "// 旧写法是 \n// " + cs_inline_filter().replace("\n", "\n// ") + "\n"
        )
    }
    assert g.implementation_sites(comment_only) == set()
    in_code = {
        "windows/tests/Aegis.Windows.Core.Tests/Notes.cs":
            "var x = " + cs_inline_filter("        ")
    }
    assert g.implementation_sites(in_code) == {"windows/tests/Aegis.Windows.Core.Tests/Notes.cs"}


def test_regex_constant_filter_is_reported(corpus) -> None:
    """R9-B64 / Q63：过滤形态写进**正则常量**而不是行前缀调用，也得数成实现点。

    这条之前是本门禁的空心处——「把就地过滤合并成一份正则常量」正好落在 MARKERS 的
    写法面之外。合并掉的那份实现现读回来时必须判红（本批实测：把 HEAD 的那份塞回内存态
    面，多出的实现点恰好是它自己）。
    """
    texts, projects = corpus
    injected = dict(texts)
    injected["scripts/SneakyRegexGate.py"] = (
        "import re\n\n" + regex_comment_filter() + "\ndef code_only(text):\n    return [l for l in text.splitlines() if not re.search(_CMT, l)]\n"
    )
    problems = g.violations(injected, projects)
    assert any("SneakyRegexGate.py" in p and "就地注释过滤" in p for p in problems), problems


def test_a_regex_that_is_not_a_comment_filter_is_not_reported(corpus) -> None:
    """正面控制：只含一种形态的正则不算——判据取「同一次调用里两种形态同现」。

    现读对照（把 HEAD 那份未合并的门禁塞回内存态面再数）：「含任一注释形态」与本判据
    今天**同样准**（各命中那一处、无关正则为 0），取窄版是因为它对「双斜杠单独出现」零
    敏感——URL／glob 类正则里 `//` 是合法产品逻辑，宽版迟早给自己造假红。把 `(?:` 也算
    证据的写法实测 14 处命中、13 处无关，已记 §六。这里钉的是窄版不该成立的两侧。
    """
    line_only = {"scripts/Url.py": one_compile_line("https:" + _LINE + "[w.-]+")}
    block_only = {"scripts/Glob.py": one_compile_line("x" + _BLOCK_FORM + "y")}
    assert g.implementation_sites(line_only) == set(), line_only
    assert g.implementation_sites(block_only) == set(), block_only


def test_regex_form_inside_a_comment_is_not_an_implementation(corpus) -> None:
    """判据 4 对新形态同样成立：同一行写法出现在注释里不算实现（先剔注释再判）。"""
    in_code = {"scripts/Notes.py": "import re\n\n" + regex_comment_filter()}
    assert g.implementation_sites(in_code) == {"scripts/Notes.py"}
    commented = {"scripts/Notes.py": "import re\n\n# 旧写法：" + regex_comment_filter().strip() + "\n"}
    assert g.implementation_sites(commented) == set(), commented


def test_stale_registration_is_reported(corpus) -> None:
    """白名单里的实现被改名＝登记过期，必须红（否则覆盖面声明会继续引用一个不存在的出处）。"""
    texts, projects = corpus
    renamed = {
        (rel.replace("SourceTextAnchorSupport.kt", "RenamedHelper.kt")): body
        for rel, body in texts.items()
    }
    problems = g.violations(renamed, projects)
    assert any("登记过期" in p for p in problems), problems


def test_kotlin_copies_diverging_is_reported(corpus) -> None:
    texts, projects = corpus
    drifted = dict(texts)
    broker_key = "android/broker/src/test/kotlin/com/aegis/broker/SourceTextAnchorSupport.kt"
    drifted[broker_key] = kotlin_helper("com.aegis.broker", extra="        .replace(\"x\", \"y\")\n")
    drifted["android/app/src/test/kotlin/com/aegis/browser/SourceTextAnchorSupport.kt"] = kotlin_helper(
        "com.aegis.browser"
    )
    problems = g.violations(drifted, projects)
    assert any("各漂各的" in p for p in problems), problems


def test_kotlin_copy_count_is_reported(corpus) -> None:
    texts, projects = corpus
    only_one = {
        rel: body
        for rel, body in texts.items()
        if rel != "android/broker/src/test/kotlin/com/aegis/broker/SourceTextAnchorSupport.kt"
    }
    problems = g.violations(only_one, projects)
    assert any("定义数应为 2" in p for p in problems), problems


def test_missing_csproj_link_is_reported(corpus) -> None:
    """共享实现没被工程链接＝写了没人编译的死文件。"""
    texts, projects = corpus
    unlinked = {rel: body for rel, body in projects.items() if not rel.endswith("Broker.Tests.csproj")}
    problems = g.violations(texts, unlinked)
    assert any("未被两个测试工程链接" in p for p in problems), problems


def test_line_comment_holding_a_fake_block_open_does_not_eat_code() -> None:
    """顺序判据（R9-B45 实测撞出来的）：整行注释里的 `"https://*"` 含一个 `/`+`*` 假块起点。

    先做块匹配就会一路吃到下一个 `*/`，把中间的真语句删掉——端侧
    `DocumentStartInjectionRegressionTest` 的正面控制当场就是这么判红的。
    """
    from text_anchors import strip_comments

    corpus = (
        '        // allowedOriginRules 不接受 "https://*" 这种全域通配\n'
        '        val allowedOrigins = setOf("*")\n'
        '        // 下一个块收尾 */ 只是文本\n'
    )
    assert "val allowedOrigins" in corpus
    assert "val allowedOrigins" in strip_comments(corpus, "android/a/WebViewHardening.kt")


def test_hash_rule_is_scoped_to_hash_comment_languages() -> None:
    """`#` 只在其语言里是注释：Rust 的属性行、C# 的预处理指令都是代码。"""
    from text_anchors import strip_comments

    rust = '#[unsafe(no_mangle)]\npub extern "C" fn aegis_adblock() {}\n'
    assert "#[unsafe(no_mangle)]" in strip_comments(rust, "core/rust-policy-core/src/adblock.rs")
    py = "# 参照说明\nx = 1\n"
    assert "参照说明" not in strip_comments(py, "agent/a.py")


def test_vendor_and_main_source_are_out_of_the_judging_surface() -> None:
    """判据面不收主源码与 vendor：`//` 字面量在那里是产品逻辑，收进来只会让门禁抱怨第三方产物。"""
    assert not g.is_judging_surface("dist/geogebra-cache/HTML5/5.0/web/a.cache.js")
    assert not g.is_judging_surface("windows/src/Aegis.Windows.App/Chrome/SourceFetcher.cs")
    assert g.is_judging_surface("android/app/src/test/kotlin/com/aegis/browser/XTest.kt")
    assert g.is_judging_surface("scripts/verify_text_anchor_helpers.py")

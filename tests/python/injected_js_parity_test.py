# injected_js_parity_test.py —— 定稿项 9 步 1（第九轮 2026-10-10）：三端注入 JS 同形
# 对账门禁自己的回归面。
#
# 两道既有门禁都不判「三端抄的同一段 JS 是否还是同一段」：verify_seed_framing_parity 只
# 查要件 token 在不在，canvas_read_channels.rs 当时只查 5 段片段（R9-RS-7 已在 R9-B14
# 补到 8 段——本文件的现树锚与那条 Rust 用例是同一条判据的两个语言面）。
# 本文件钉门禁的几件事：现树真的对齐、钉表是下界、**豁免表必须仍然失真**（这条是
# 白名单式门禁的通用失效口）、收编后的两条 read 包装确实在比较面、注册器别名表按键名
# 收口不被 close 键冒充、解释层不被宿主引号带偏，以及 Q57-② 那条判定所依赖的**前提**
# （三端都不覆写 `Object.defineProperty`，见文件末尾）。
from __future__ import annotations

import pathlib
import re

import injected_js_text as ijt
import pytest
import verify_injected_js_parity as vip

REPO = pathlib.Path(__file__).resolve().parents[2]


def _tables(**bodies_by_end: dict[str, str]) -> dict[str, dict[str, str]]:
    """按 (端, 函数名) 造表；未指定的函数默认三端同形。"""
    tables: dict[str, dict[str, str]] = {end: {} for end in ("Rust", "C#", "Kotlin")}
    for name in vip.SHARED_CORE:
        for end in tables:
            tables[end][name] = "{ var shared = 1; }"
    for end, overrides in bodies_by_end.items():
        tables[end].update(overrides)
    return tables


# ---------------------------------------------------------------- 现树

def test_current_tree_is_parity_clean():
    assert vip.violations() == []


def test_registered_divergences_are_really_divergent():
    """豁免表不是装饰品：登记的每一条必须**仍然**不同形，否则就该收编（门禁自己会判红）。"""
    tables = vip.per_end_tables()
    diverging = vip.divergent_shared_names(tables)
    assert set(vip.DIVERGENT_REGISTERED) <= diverging, (
        f"登记项已同形但未收编：{sorted(set(vip.DIVERGENT_REGISTERED) - diverging)}")


def test_pixel_read_wrappers_are_collected_after_r9_rs_9():
    """R9-RS-9 收编锚：两条像素直读包装曾挂豁免表（注册尾三端不同形），
    现在必须**不在**豁免表且**确实**同形——退化回原写法本条与门禁一起判红。"""
    tables = vip.per_end_tables()
    diverging = vip.divergent_shared_names(tables)
    for name in ("aegisWrapReadPixels", "aegisWrapRectRead"):
        assert name not in vip.DIVERGENT_REGISTERED, name
        assert name not in diverging, f"{name} 又分叉了：{sorted(diverging)}"


def test_register_accessor_alias_is_key_bounded():
    """别名表只认登记过的取用路径；未登记的 Symbol 键（close 键）不得被归一冒充注册器。"""
    forms = [
        "try { if (window[Symbol.for('proxy.register.v1')]) window[Symbol.for('proxy.register.v1')](a, b); } catch (e) {}",
        "try { if (window[Symbol.for('{reg_sym}')]) window[Symbol.for('{reg_sym}')](a, b); } catch (e) {}",
        "try { if (registerProxy) registerProxy(a, b); } catch (e) {}",
        "try { if (__aegisReg) __aegisReg(a, b); } catch (e) {}",
    ]
    canonical = {ijt.canonicalize(form, "Rust") for form in forms}
    assert len(canonical) == 1 and "__REG__" in canonical.pop(), canonical
    assert "__REG__" not in ijt.canonicalize(
        "window[Symbol.for('proxy.register.close.v1')](a, b)", "Rust")


def test_shared_core_is_a_floor_not_a_ceiling():
    """钉表条目必须都在现树共有面里（有人改名/删除时本条与门禁一起响）。"""
    assert set(vip.SHARED_CORE) <= vip.shared_names(vip.per_end_tables())


def test_gate_is_wired_into_the_required_contracts_job():
    workflow = (REPO / ".github/workflows/contracts.yml").read_text(encoding="utf-8")
    assert "verify_injected_js_parity.py" in workflow


# ---------------------------------------------------------------- 判定逻辑（故障注入）

def test_body_difference_is_reported_with_a_position(monkeypatch):
    monkeypatch.setattr(vip, "per_end_tables", lambda: _tables(
        Kotlin={"aegisNoiseMix": "{ var shared = 2; }"}))
    found = vip.violations()
    assert any("aegisNoiseMix 三端不同形" in problem for problem in found), found
    assert any("第" in problem and "字符起分叉" in problem for problem in found)


def test_missing_core_function_is_reported(monkeypatch):
    tables = _tables()
    for table in tables.values():
        table.pop("aegisNudge")
    monkeypatch.setattr(vip, "per_end_tables", lambda: tables)
    assert any("缺核心函数" in p and "aegisNudge" in p for p in vip.violations())


def test_exemption_that_stops_being_divergent_is_flagged(monkeypatch):
    """把已同形的函数留在豁免表里 ⇒ 必须判红（否则豁免会悄悄长成了永久盲区）。

    R9-RS-9 之后现树登记表为空（两条 read 包装已收编），所以这里显式注入一个**已同形**
    的名字来驱动那条反向判据——不能因为表现在是空的就跳过它。
    """
    monkeypatch.setattr(vip, "per_end_tables", lambda: _tables())
    monkeypatch.setattr(vip, "DIVERGENT_REGISTERED", ("aegisNudge",))
    assert any("已登记的不同形项现在已同形" in p for p in vip.violations())


def test_empty_parse_surface_is_environment_error(monkeypatch):
    monkeypatch.setattr(vip, "per_end_tables", lambda: {"Rust": {}, "C#": {"a": "{}"}, "Kotlin": {"a": "{}"}})
    with pytest.raises(SystemExit) as exc:
        vip.violations()
    assert "扫描面塌缩" in str(exc.value)


def test_missing_input_file_is_environment_error(monkeypatch, tmp_path):
    monkeypatch.setattr(vip, "RS_FILES", ("no/such/shield.rs",))
    with pytest.raises(SystemExit) as exc:
        vip.violations()
    assert "门禁输入缺失" in str(exc.value)


# ---------------------------------------------------------------- 解释层

def test_host_quotes_do_not_break_brace_pairing():
    """宿主三引号在函数体**之外**：整份文件一起按 JS 串扫会把结构读丢（第一版实测）。"""
    source = 'val js = """\n  function aegisX(a) { if (a) { return "}" ; } }\n""";\nval other = "}"'
    bodies = ijt.extract_functions(source)
    assert bodies["aegisX"].endswith("}"), bodies["aegisX"]
    assert "{ return \"}\" ; }" in bodies["aegisX"]


def test_canonicalize_absorbs_host_form_but_not_logic():
    rust = ijt.canonicalize("function f() {{ var x = aegisCanvasSeed(); /* 注 */ try { } catch (e) {} }}", "Rust")
    kotlin = ijt.canonicalize("function f() { const x = noiseSeed(); try {\n } catch (e) { } }", "Kotlin")
    assert rust == kotlin, f"{rust!r} != {kotlin!r}"


def test_string_payloads_still_participate_in_comparison():
    """注释与空白不参与，但 `'://'` 这类串内容必须参与——否则真实的逻辑差会被抹平。"""
    left = ijt.canonicalize("function f() { var i = s.indexOf('://'); }", "Rust")
    right = ijt.canonicalize("function f() { var i = s.indexOf('/xx'); }", "Rust")
    assert left != right


def test_declaration_keyword_drift_is_deliberately_not_judged():
    """这条**是**记录口径而不是漏洞：三端在 const/var 上确有分歧且无行为差，
    判它只会诱导下一次「顺手放宽门禁」。真正的对齐另批处理。"""
    assert ijt.canonicalize("function f() { const a = 1; }", "Rust") == \
        ijt.canonicalize("function f() { var a = 1; }", "C#")

# ---------------------------------------------------------------- Q57-② 的前提
# 台账 §3.55 把 Q57-②（「三端用哪一份定义器不同形，要统一到 Windows 的 origDefineProp」）
# 判成**不是缺口**。那个判定靠两条现读事实，而不是靠读那段推理的人同意：
# ①没有任何一端覆写 `Object.defineProperty`；②Windows 之所以提前捕获它，是因为同一段里
# 还覆写了 `getOwnPropertyDescriptor`/`getOwnPropertyNames`（那是 Windows 独有的一层反检测），
# 捕获只是那一段的写法习惯。两条都变了，结论就得重判——所以这里把前提做成能红的判据。

# 出货注入文本的全部落点（现取，不是手抄名单：门禁的比较面只覆盖三端共用的那几个函数，
# 而这条判的是「装防护时用的是哪一份定义器」，它在 installer 里，不在那几个函数里）。
JS_SHIPPING_GLOBS = (
    "core/rust-policy-core/src/*.rs",
    "core/rust-policy-core/src/shield/*.rs",
    "windows/src/Aegis.Windows.App/WebView/FingerprintShield*.cs",
    "android/app/src/main/java/com/aegis/browser/WebViewHardening*.kt",
)

# `=(?!=)` 只认赋值，不认 `==`；`Object.defineProperty;` 这种「取用」也不在判面内。
DEFINER_ASSIGN = re.compile(r"Object\s*\.\s*defineProperty\s*=(?!=)")
PROTOTYPE_PROBE_ASSIGN = re.compile(r"Object\s*\.\s*getOwnProperty(?:Descriptor|Names)\s*=(?!=)")


def shipping_js_surfaces() -> dict[pathlib.Path, str]:
    """全部出货注入文本面的代码（剔注释——本仓的注记会把被禁形态逐字抄一遍）。"""
    found: dict[pathlib.Path, str] = {}
    for pattern in JS_SHIPPING_GLOBS:
        for path in sorted(REPO.glob(pattern)):
            found[path] = ijt.strip_comments(path.read_text(encoding="utf-8", errors="ignore"))
    assert found, "一个出货注入面都没扫到——提取口径坏了，下面的判据就是假绿"
    return found


def test_nobody_overwrites_the_definer_the_ends_use():
    """前提①：三端都不覆写 `Object.defineProperty`。
    既然没人换掉它，而注入又都在 document-start（Windows `AddScriptToExecuteOnDocumentCreatedAsync`、
    Android `WebViewCompat.addDocumentStartJavaScript`——页面脚本此刻还没机会跑），
    那么 Windows 提前捕获的 `origDefineProp` 与核心/Android 的直接引用等价 ⇒
    「必须统一」那条处方不成立（§3.55）。哪天有人真去包它，这条会红，逼着重判而不是靠记性。"""
    offenders = [
        f"{path.as_posix()}:{match.start()}"
        for path, code in shipping_js_surfaces().items()
        for match in DEFINER_ASSIGN.finditer(code)
    ]
    assert not offenders, (
        f"有出货注入面开始覆写 Object.defineProperty 了：{offenders}——"
        "§3.55 的等价前提失效，Q57-② 必须重新判（那时『统一形态』就不再是纯外观问题）")


def test_the_same_pattern_sees_what_windows_really_overwrites():
    """正面控制（前提②）：同一个模式必须认出 Windows 确实覆写了 `getOwnProperty*`。
    没有这条，上面那个 Empty 可能只是模式瞎了——它瞎的方向恰好是让「不用统一」永远成立。"""
    hits = [
        path.as_posix()
        for path, code in shipping_js_surfaces().items()
        if PROTOTYPE_PROBE_ASSIGN.search(code)
    ]
    assert any("FingerprintShield.cs" in hit for hit in hits), (
        f"Windows 不再覆写 getOwnProperty*（实得 {hits}）——§3.55 那段『捕获只是写法习惯』的解释要重写")

def test_the_definer_pattern_is_narrow_and_genuine():
    """模式自己的单位控制：赋值要认，**取用与比较不能认**。
    `var origDefineProp = Object.defineProperty;` 是 Windows 的那次捕获（等号在左边另一侧），
    `Object.defineProperty(performance, 'now', d)` 是取用——把它认成覆写会让上面那条判据
    在正常代码上假红，而下一次「让它变绿」的动作就是放松前提。"""
    assert DEFINER_ASSIGN.search("Object.defineProperty = function () {};")
    assert DEFINER_ASSIGN.search("Object .defineProperty  =  wrapper;")
    assert not DEFINER_ASSIGN.search("var origDefineProp = Object.defineProperty;")
    assert not DEFINER_ASSIGN.search("Object.defineProperty(performance, 'now', d);")
    assert not DEFINER_ASSIGN.search("if (Object.defineProperty === native) return true;")

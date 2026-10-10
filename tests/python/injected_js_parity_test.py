# injected_js_parity_test.py —— 定稿项 9 步 1（第九轮 2026-10-10）：三端注入 JS 同形
# 对账门禁自己的回归面。
#
# 两道既有门禁都不判「三端抄的同一段 JS 是否还是同一段」：verify_seed_framing_parity 只
# 查要件 token 在不在，canvas_read_channels.rs 只查 5 段片段（R9-RS-7）。本文件钉新门禁
# 的四件事：现树真的对齐、钉表是下界、**豁免表必须仍然失真**（这条是白名单式门禁的
# 通用失效口）、解释层不被宿主引号带偏。
from __future__ import annotations

import pathlib

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
    """把已同形的函数留在豁免表里 ⇒ 必须判红（否则豁免会悄悄长成了永久盲区）。"""
    monkeypatch.setattr(vip, "per_end_tables", lambda: _tables())
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

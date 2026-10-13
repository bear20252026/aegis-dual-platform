# core_unwired_modules_test.py —— R9-B36（第九轮 Q28 / R9-RS-4）的门禁用例。
#
# 三条不变量都必须**能红**，所以每条都配注入式反向锚（内存态，不改工作树）：
# ① 登记表与 lib.rs 的模块声明同一集合；② 接入层（c_abi/ffi）不得出现模块名——
# 接线即红；③ README 的那句陈述必须逐字含由登记表生成的清单。
# 另有一条正面控制：现树必须全绿，否则上面三条可能是在判空气（R7-TOOL-04 同口径）。
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import verify_core_unwired_modules as g


@pytest.fixture(scope="module")
def real():
    lib_text = (g.CORE / "lib.rs").read_text(encoding="utf-8")
    readme = g.README.read_text(encoding="utf-8")
    texts = {p: g.strip_comments(p.read_text(encoding="utf-8", errors="ignore"), p.name)
             for p in g.interface_sources()}
    return lib_text, texts, readme


def test_real_tree_is_consistent(real):
    lib_text, texts, readme = real
    assert g.check(lib_text, texts, readme) == []


def test_scan_surface_is_not_collapsed(real):
    """正面控制的另一半：三个集合都非空——空面会让 check() 变成恒真。"""
    lib_text, texts, readme = real
    assert len(g.UNWIRED) >= 3
    assert len(texts) >= 20, f"接入层文件数异常：{len(texts)}"
    assert len(g.declared_modules(lib_text)) >= 20
    assert g.README_MARKER in readme


def test_wiring_a_registered_module_turns_the_gate_red(real):
    """反向锚：接入层出现一次 `update_manifest` 引用 ⇒ 必须判红并点名文件。"""
    lib_text, texts, readme = real
    victim = next(iter(texts))
    injected = dict(texts)
    injected[victim] = injected[victim] + "\nuse crate::update_manifest::verify_threshold;\n"
    problems = g.check(lib_text, injected, readme)
    assert any("update_manifest" in p and "接入层已出现引用" in p for p in problems), problems


def test_unwiring_a_module_by_deleting_its_declaration_is_red(real):
    lib_text, texts, readme = real
    shrunk = lib_text.replace("pub mod oracle;", "// pub mod oracle;")
    assert shrunk != lib_text, "注入锚点失配（lib.rs 形态变了，本条会恒绿）"
    problems = g.check(shrunk, texts, readme)
    assert any("oracle" in p and "pub mod" in p for p in problems), problems


def test_readme_fragment_must_name_the_whole_registered_set(real):
    """README 少列一个模块 = 陈述与实树不同一集合（不是「少写一个名字」那么轻）。"""
    lib_text, texts, readme = real
    truncated = readme.replace("`session_state`、", "", 1)
    assert truncated != readme, "注入锚点失配"
    problems = g.check(lib_text, texts, truncated)
    assert any("README 缺逐字锚" in p for p in problems), problems


def test_readme_ed25519_claim_must_name_the_execution_path(real):
    """反向锚：README 提 Ed25519 却不写执行路径 ⇒ 判红（本批就是被这句逼出来的）。"""
    lib_text, texts, readme = real
    stripped = chr(10).join(
        line.replace("release/update_verifier.py", "另一处") if "Ed25519" in line else line
        for line in readme.splitlines())
    assert stripped != readme, "注入锚点失配（README 里那句的形态变了，本条会恒绿）"
    problems = g.check(lib_text, texts, stripped)
    assert any("Ed25519 阈值验证却没写执行路径" in p_ for p_ in problems), problems


def test_export_inside_an_unwired_module_is_red(tmp_path, monkeypatch):
    """模块自己长出导出属性＝接线，README 的「运行时零调用」当场失实。"""
    fake_core = tmp_path / "src"
    (fake_core / "c_abi").mkdir(parents=True)
    (fake_core / "ffi").mkdir(parents=True)
    (fake_core / "c_abi" / "mod.rs").write_text("fn a() {}\n", encoding="utf-8")
    (fake_core / "ffi" / "mod.rs").write_text("fn b() {}\n", encoding="utf-8")
    lib = "\n".join(f"pub mod {m};" for m in g.UNWIRED)
    (fake_core / "lib.rs").write_text(lib, encoding="utf-8")
    mod = fake_core / "adblock.rs"
    mod.write_text("#[unsafe(no_mangle)]\npub extern \"C\" fn aegis_adblock() {}\n", encoding="utf-8")
    monkeypatch.setattr(g, "CORE", fake_core)
    texts = {p: g.strip_comments(p.read_text(encoding="utf-8"), p.name) for p in g.interface_sources()}
    problems = g.check(lib, texts, g.expected_readme_fragment())
    assert any("导出即接线" in p for p in problems), problems


def test_missing_interface_dir_exits_2(tmp_path, monkeypatch):
    """接入层目录缺失不能被判成「零引用所以全绿」。"""
    monkeypatch.setattr(g, "CORE", tmp_path)
    with pytest.raises(FileNotFoundError):
        g.interface_sources()

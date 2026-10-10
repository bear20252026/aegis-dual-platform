"""uniffi_binding_surface_test.py —— R9-RS-2：UniFFI 导出面 ↔ 入库绑定对账的常驻锚。

要钉住的失效形态是台账里那个实测事实：`update_host_denylist`（`607d7a1`，2026-10-04）
进了 `#[uniffi::export]`，入库 Python 绑定没有它，而**没有任何门禁红**——`test -s` 判
的是刚生成的 Kotlin 文件非空，「stale bindings」那步只 diff 两个契约生成目录。
"""
from __future__ import annotations

import pathlib

import pytest
import verify_uniffi_binding_surface as vubs

REPO = pathlib.Path(__file__).resolve().parents[2]

RUST = """
#[uniffi::export]
impl FfiBroker {
    /// 创建 Broker。注记里写 `#[uniffi::constructor]` 只是文档，不改变形状。
    #[uniffi::constructor]
    pub fn new(policy_version: String) -> Self { Self {} }

    /// 评估导航意图。
    pub fn evaluate_navigation(&self, raw_url: String) -> bool { true }

    pub fn destroy_session(&self) -> bool { true }
}

// #[uniffi::export] 的 impl 会把其中所有方法计入 FFI 面
impl Note {
    pub fn mentioned_only_in_comment(&self) {}
}

/// 未做 `#[uniffi::export]`——宿主经 FFI 拿不到（ffi/mod.rs:253 的注记原文形态）。
impl Ghost {
    pub fn not_exported(&self) {}
}

#[uniffi::export]
pub fn try_parse_external(raw_url: String) -> Option<u32> { None }
"""

BINDING = """
_UniffiLib.uniffi_aegis_policy_core_fn_constructor_ffibroker_new.argtypes = ()
_UniffiLib.uniffi_aegis_policy_core_fn_method_ffibroker_evaluate_navigation.restype = 1
_UniffiLib.uniffi_aegis_policy_core_fn_method_ffibroker_destroy_session.restype = 1
_UniffiLib.uniffi_aegis_policy_core_fn_func_try_parse_external.restype = 1
uniffi_aegis_policy_core_fn_free_ffibroker.argtypes = ()
uniffi_aegis_policy_core_fn_clone_ffibroker.argtypes = ()
"""


def _pair(rust: str = RUST, binding: str = BINDING) -> list[str]:
    return vubs._diff(vubs.exports_from_src(rust), vubs.surface_from_binding(binding))


def test_real_tree_surfaces_match():
    """现树锚：入库件已按当前 src 重 derive——这条红就说明有人加了导出没重生成。"""
    assert vubs.check(REPO) == []


def test_export_surface_shape_is_parsed():
    methods, ctors, funcs = vubs.exports_from_src(RUST)
    assert sorted(methods["FfiBroker"]) == ["destroy_session", "evaluate_navigation"]
    assert sorted(ctors["FfiBroker"]) == ["new"]
    assert funcs == {"try_parse_external"}


def test_comment_and_doc_lines_are_not_exports():
    """注释里的属性字面量不得算导出——否则文档反例会把对账判成「绑定缺方法」。"""
    methods, ctors, funcs = vubs.exports_from_src(RUST)
    all_names = {n for s in methods.values() for n in s} | {n for s in ctors.values() for n in s} | funcs
    for absent in ("mentioned_only_in_comment", "not_exported"):
        assert absent not in all_names


def test_object_name_case_difference_is_not_drift():
    """uniffi 把 `FfiBroker` 写成 `ffibroker`——不归一就会 9 个方法各报两遍（首轮实测）。"""
    assert _pair() == []


def test_missing_method_in_binding_is_detected():
    trimmed = "\n".join(
        line for line in BINDING.splitlines() if "evaluate_navigation" not in line)
    found = _pair(binding=trimmed)
    assert len(found) == 1 and "绑定缺方法" in found[0] and "evaluate_navigation" in found[0], found


def test_extra_method_in_binding_is_detected():
    """Rust 侧删了导出而入库件没重生成——读绑定的人会按不存在的 ABI 写。"""
    without_export = "\n".join(
        line for line in RUST.splitlines() if "destroy_session" not in line)
    found = _pair(rust=without_export)
    assert len(found) == 1 and "绑定多方法" in found[0] and "destroy_session" in found[0], found


def test_missing_constructor_is_detected():
    trimmed = "\n".join(
        line for line in BINDING.splitlines() if "fn_constructor" not in line)
    found = _pair(binding=trimmed)
    assert len(found) == 1 and "绑定缺构造子" in found[0], found


def test_missing_free_function_is_detected():
    trimmed = "\n".join(line for line in BINDING.splitlines() if "fn_func_" not in line)
    found = _pair(binding=trimmed)
    assert len(found) == 1 and "绑定缺自由函数" in found[0], found


def test_generated_mode_reports_drift_with_prefix(tmp_path):
    root = tmp_path / "repo"
    (root / "core" / "rust-policy-core" / "src").mkdir(parents=True)
    binding_dir = root / "core" / "rust-policy-core" / "bindings"
    binding_dir.mkdir(parents=True)
    (root / "core" / "rust-policy-core" / "src" / "ffi.rs").write_text(RUST, encoding="utf-8")
    (binding_dir / "aegis_policy_core.py").write_text(BINDING, encoding="utf-8")
    good = binding_dir / "regenerated.py"
    good.write_text(BINDING, encoding="utf-8")
    assert vubs.check(root, generated=good) == []
    bad = binding_dir / "regenerated.py"
    bad.write_text(BINDING + "\nuniffi_aegis_policy_core_fn_method_ffibroker_brand_new.restype = 1\n",
                   encoding="utf-8")
    found = vubs.check(root, generated=bad)
    assert len(found) == 1 and found[0].startswith("权威生成 vs 入库件：绑定缺方法"), found
    assert "brand_new" in found[0] and "重跑生成并入库" in found[0], found


def test_empty_src_surface_is_environment_error(tmp_path):
    """扫描面为空不放行（与 check_file_sizes/verify_lock_rids 同口径）。"""
    root = tmp_path / "repo"
    (root / "core" / "rust-policy-core" / "src").mkdir(parents=True)
    binding_dir = root / "core" / "rust-policy-core" / "bindings"
    binding_dir.mkdir(parents=True)
    (root / "core" / "rust-policy-core" / "src" / "empty.rs").write_text("fn a() {}\n", encoding="utf-8")
    (binding_dir / "aegis_policy_core.py").write_text(BINDING, encoding="utf-8")
    with pytest.raises(SystemExit):
        vubs.check(root)


def test_empty_binding_surface_is_environment_error(tmp_path):
    root = tmp_path / "repo"
    (root / "core" / "rust-policy-core" / "src").mkdir(parents=True)
    binding_dir = root / "core" / "rust-policy-core" / "bindings"
    binding_dir.mkdir(parents=True)
    (root / "core" / "rust-policy-core" / "src" / "ffi.rs").write_text(RUST, encoding="utf-8")
    (binding_dir / "aegis_policy_core.py").write_text("class FfiBroker: pass\n", encoding="utf-8")
    with pytest.raises(SystemExit):
        vubs.check(root)


def test_missing_directories_are_environment_errors(tmp_path):
    with pytest.raises(SystemExit):
        vubs.check(tmp_path / "nonexistent")


def test_exit_code_is_one_on_drift(tmp_path, capsys):
    root = tmp_path / "repo"
    src = root / "core" / "rust-policy-core" / "src"
    src.mkdir(parents=True)
    (root / "core" / "rust-policy-core" / "bindings").mkdir(parents=True)
    (src / "ffi.rs").write_text(RUST, encoding="utf-8")
    (root / "core" / "rust-policy-core" / "bindings" / "aegis_policy_core.py").write_text(
        "\n".join(line for line in BINDING.splitlines() if "destroy_session" not in line),
        encoding="utf-8")
    assert vubs.main(["--repo-root", str(root)]) == 1
    assert "绑定缺方法" in capsys.readouterr().out

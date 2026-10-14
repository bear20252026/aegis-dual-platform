# ffi_input_bounds_test.py —— R9-B61（R8-RS-13 落地）的门禁用例。
#
# 四条不变量全部以**内存注入**证伪（不改工作树），口径与
# core_unwired_modules_test.py 同：先证现树全绿，再逐条把判据要拦的形态摆上去看它红不红。
# 这里拦的不是「返回值对不对」而是「判定排在分配之前没有」——两种写法的返回值逐字相同，
# 所以顺序只能按文本判（剔注释口径单源 scripts/text_anchors.py，R9-B39 / R9-B45）。
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import verify_ffi_input_bounds as g

SEED_GUARD = "    if hex.len() != HEX_SEED_CHARS {\n        return None;\n    }\n"
DECODE_LINE = "    crate::util::hex_decode(hex)?.as_slice().try_into().ok()\n"
BATCH_BLOCK = (
    "        if hosts.iter().map(|host| host.len()).sum::<usize>() > MAX_BATCH_BYTES {\n"
    "            return ApplyReport::refused(mode, self.served_count());\n"
    "        }\n"
)
TRIM_LINE = "            .map(|host| host.trim().to_ascii_lowercase())\n"
ENTRY_GUARD = "        && host.len() <= MAX_ENTRY_BYTES\n"


@pytest.fixture(scope="module")
def texts():
    return g.load_texts()


def swap(texts: dict[str, str], path: Path, value: str) -> dict[str, str]:
    mutated = dict(texts)
    mutated[g.key(path)] = value
    return mutated


def test_real_tree_satisfies_every_rule(texts):
    assert g.check(texts) == []


def test_scan_surface_is_not_collapsed(texts):
    """正面控制的另一半：四个文件、七个常量、三个函数体都得读得出来——
    任何一面空了，上面那条断言就可能是在判空气（R7-TOOL-04 同口径）。"""
    assert len(texts) == len(g.TEXTS)
    for path, name in g.BIG_BATCH_CONSTS:
        assert g.const_value(texts, path, name) is not None, name
    for path, name in g.HOST_LEN_CONSTS:
        assert g.const_value(texts, path, name) is not None, name
    assert g.fn_body(texts[g.key(g.SEED_FILE)], "hex_seed_to_bytes") is not None
    denylist = texts[g.key(g.DENYLIST_FILE)]
    assert g.fn_body(denylist, "entry_shape_ok") is not None
    assert g.fn_body(denylist, "apply") is not None


def test_seed_guard_after_the_decode_is_red(texts):
    """R8-RS-13 的原始形态：先解后判。"""
    seed = texts[g.key(g.SEED_FILE)]
    assert SEED_GUARD in seed and DECODE_LINE in seed
    mutated = seed.replace(
        SEED_GUARD + DECODE_LINE,
        "    let decoded = crate::util::hex_decode(hex)?;\n"
        "    if decoded.len() != 32 {\n        return None;\n    }\n"
        "    decoded.as_slice().try_into().ok()\n",
    )
    problems = g.check(swap(texts, g.SEED_FILE, mutated))
    assert any("走在" in p and "hex_decode" in p for p in problems), problems


def test_a_commented_out_guard_is_not_evidence(texts):
    """注记里写着护栏 ≠ 护栏在位（R9-B39：按文本判源码必须先剔注释）。"""
    seed = texts[g.key(g.SEED_FILE)]
    commented = seed.replace(SEED_GUARD, "// if hex.len() != HEX_SEED_CHARS {\n" "//        return None;\n" "//    }\n")
    stripped = g.strip_comments(commented, g.key(g.SEED_FILE))
    problems = g.check(swap(texts, g.SEED_FILE, stripped))
    assert any("走在" in p for p in problems), problems


def test_seed_guard_numbering_must_follow_the_return_type(texts):
    """护栏比的数必须能从 `[u8; N]` 推出——写成别的数就是「护栏和契约不是一个数」。"""
    seed = texts[g.key(g.SEED_FILE)].replace(
        "const HEX_SEED_CHARS: usize = 64;", "const HEX_SEED_CHARS: usize = 66;"
    )
    problems = g.check(swap(texts, g.SEED_FILE, seed))
    assert any("护栏与契约不是同一个数" in p for p in problems), problems


def test_entry_length_cap_removed_is_red(texts):
    denylist = texts[g.key(g.DENYLIST_FILE)]
    assert ENTRY_GUARD in denylist
    problems = g.check(swap(texts, g.DENYLIST_FILE, denylist.replace(ENTRY_GUARD, "")))
    assert any("死条目" in p for p in problems), problems


def test_batch_cap_after_the_o_n_transform_is_red(texts):
    """拒收一批之前不该先把它整趟读一遍——同一条上限，位置即语义。"""
    denylist = texts[g.key(g.DENYLIST_FILE)]
    assert BATCH_BLOCK in denylist and TRIM_LINE in denylist
    moved = denylist.replace(BATCH_BLOCK, "", 1).replace(TRIM_LINE, TRIM_LINE + BATCH_BLOCK, 1)
    body = g.fn_body(moved, "apply")
    assert body is not None
    assert body.find("MAX_BATCH_BYTES") > body.find("host.trim()"), "注入本身没生效"
    problems = g.check(swap(texts, g.DENYLIST_FILE, moved))
    assert any("先拒再算" in p for p in problems), problems


def test_batch_cap_removed_is_red(texts):
    denylist = texts[g.key(g.DENYLIST_FILE)]
    problems = g.check(swap(texts, g.DENYLIST_FILE, denylist.replace(BATCH_BLOCK, "", 1)))
    assert any("批次总字节判定" in p for p in problems), problems


def test_a_single_face_drift_on_the_batch_size_is_red(texts):
    """三面同值这条是注记里的口径（RS-173）：只改一份必须红，改三份一起改才是口径变更。"""
    denylist = texts[g.key(g.DENYLIST_FILE)].replace(
        "const MAX_BATCH_BYTES: usize = 64 * 1024;", "const MAX_BATCH_BYTES: usize = 32 * 1024;"
    )
    problems = g.check(swap(texts, g.DENYLIST_FILE, denylist))
    assert any("批次口径出现分叉" in p for p in problems), problems
    together = swap(texts, g.DENYLIST_FILE, denylist)
    together[g.key(g.SEED_FILE)] = together[g.key(g.SEED_FILE)].replace(
        "const MAX_FFI_URL_BYTES: usize = 64 * 1024;",
        "const MAX_FFI_URL_BYTES: usize = 32 * 1024;",
    )
    together[g.key(g.CABI_FILE)] = together[g.key(g.CABI_FILE)].replace(
        "const FFI_INPUT_MAX_BYTES: usize = 64 * 1024;",
        "const FFI_INPUT_MAX_BYTES: usize = 32 * 1024;",
    )
    # 反向对照：三面一起改 ⇒ 判据不响。这条判的是「同值」，不是「必须等于 64 KiB」。
    assert g.check(together) == []


def test_entry_cap_drift_from_the_host_family_is_red(texts):
    denylist = texts[g.key(g.DENYLIST_FILE)].replace(
        "pub(crate) const MAX_ENTRY_BYTES: usize = 256;",
        "pub(crate) const MAX_ENTRY_BYTES: usize = 512;",
    )
    problems = g.check(swap(texts, g.DENYLIST_FILE, denylist))
    assert any("host 长度口径分叉" in p for p in problems), problems


def test_a_renamed_anchor_reports_collapse_not_pass(texts):
    seed = texts[g.key(g.SEED_FILE)].replace("hex_seed_to_bytes", "seed_to_bytes")
    problems = g.check(swap(texts, g.SEED_FILE, seed))
    assert any("不在位" in p for p in problems), problems


def test_missing_file_is_reported_as_collapse():
    assert any("判定面塌缩" in p for p in g.check({"mod.rs": ""}))

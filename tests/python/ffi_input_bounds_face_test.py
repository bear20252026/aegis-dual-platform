# ffi_input_bounds_face_test.py —— R9-B63：判据 5「存」与判据 6「回声」两面的门禁用例。
#
# 同一个门禁脚本拆两个文件，依据是判据所属的面：`ffi_input_bounds_test.py` 判的是
# 「判定排在分配之前」（R8-RS-13 / R9-B61 立的那条通则），这一份判 R9-B63 补的两面——
# 「存」（构造期版本串会被 clone 进每一条签发的授权）与「回声」（未判长的宿主原串
# 会不会整串进 deny 文案）。换面用的 `swap` 取自那份文件，同一口径不写第二份。
#
# 为什么不能只靠 Rust 行为用例：可观察的一半（载荷里生效的版本串、deny 文案的长度与
# 内容、账本有没有被碰）落在 `ffi/broker/ffi_navigation_tests/input_bounds.rs`；
# 「同一件事只许写一遍」和「判定位置」这两半从返回值看不出来。
#
# 注入锚点的逐字形态一律从 `load_texts` 的**剔注释**文本里取——门禁读的就是那份，
# 带注释的锚点 replace 会静默失配，用例就退化成「什么都没注入也通过」。`inject` 把
# 这条自查写成断言：换不动立刻红，不让假绿冒充证据。
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import verify_ffi_input_bounds as g
from ffi_input_bounds_test import swap  # 注入用的换面函数（同口径不重写第二份）
from text_anchors import strip_comments

VERSION_GUARD = "        !value.is_empty() && value.len() <= MAX_POLICY_VERSION_BYTES\n"
VERSION_BLOCK = (
    "        let policy_version = if Self::policy_version_ok(&policy_version) {\n"
    "            policy_version\n        } else {\n"
    "            DEFAULT_POLICY_VERSION.to_string()\n        };\n"
)
CABI_CALL = "        if !FfiBroker::policy_version_ok(&policy_version) {\n"
GUARD_BLOCK = (
    "        if let Some(refusal) =\n"
    "            input_bounds::navigation_entry_refusal(&session_id, &tab_id, &scope, &raw_url)\n"
    "        {\n            return refusal;\n        }\n"
)
PARSE_LINE = "        let canonical_url = match crate::origin::canonicalize_external(&raw_url) {\n"
URL_CALL = (
    "        if let Some(refusal) = input_bounds::url_entry_refusal(&raw_url) {\n"
    "            return refusal;\n        }\n"
)
ECHO_DETAIL = (
    '                "会话键超长（session {} 字节 / tab {} 字节，上限 {MAX_SESSION_KEY_BYTES}）",\n'
    "                session_id.len(),\n"
    "                tab_id.len()\n"
)


@pytest.fixture(scope="module")
def texts():
    """门禁读的那份判定面（剔注释后的正文），口径与主文件同一个 `load_texts`。"""
    return g.load_texts(g.TEXTS)


@pytest.fixture(scope="module")
def bounds(texts) -> str:
    return texts[g.key(g.BOUNDS_FILE)]


@pytest.fixture(scope="module")
def broker(texts) -> str:
    return texts[g.key(g.BROKER_FILE)]


def inject(text: str, old: str, new: str) -> str:
    """把一处形态换成另一处——锚点与现读源码对不上就立刻红，不让空注入冒充证据。"""
    assert old in text, "注入锚点与现读源码对不上"
    return text.replace(old, new, 1)


def test_policy_version_without_the_length_term_is_red(texts, bounds):
    """只判空、不判长 ⇒ 红：这正是本批之前的形态（版本串被 clone 进每条签发授权）。"""
    problems = g.check(
        swap(texts, g.BOUNDS_FILE, inject(bounds, VERSION_GUARD, "        !value.is_empty()\n"))
    )
    assert any("clone 进" in p for p in problems), problems


def test_a_commented_out_version_guard_is_not_evidence(texts, bounds):
    """R9-B39 那课在新面上的复写：注释里逐字写着守卫，也不算守卫在位。"""
    commented = inject(
        bounds,
        VERSION_GUARD,
        "        // !value.is_empty() && value.len() <= MAX_POLICY_VERSION_BYTES\n",
    )
    problems = g.check(
        swap(texts, g.BOUNDS_FILE, strip_comments(commented, g.key(g.BOUNDS_FILE)))
    )
    assert any("clone 进" in p for p in problems), problems


def test_either_face_stopping_short_of_the_shared_predicate_is_red(texts, broker):
    """两面各写一份就是漂移面：任一面退回自己判 is_empty，都要红。"""
    bare = inject(
        broker,
        VERSION_BLOCK,
        "        let policy_version = if !policy_version.is_empty() {\n"
        "            policy_version\n        } else {\n"
        "            DEFAULT_POLICY_VERSION.to_string()\n        };\n",
    )
    problems = g.check(swap(texts, g.BROKER_FILE, bare))
    assert any("两面各写一份" in p for p in problems), problems
    cabi = inject(texts[g.key(g.CABI_FILE)], CABI_CALL, "        if policy_version.is_empty() {\n")
    problems = g.check(swap(texts, g.CABI_FILE, cabi))
    assert any("两面各写一份" in p for p in problems), problems


def test_judging_the_version_after_the_struct_is_built_is_red(texts, broker):
    """同一条判定，位置即语义：先存进字段再判，等于没判。"""
    assert VERSION_BLOCK + "        Self {\n" in broker, "注入锚点与现读源码对不上"
    moved = broker.replace(VERSION_BLOCK + "        Self {\n", "        Self {\n" + VERSION_BLOCK, 1)
    problems = g.check(swap(texts, g.BROKER_FILE, moved))
    assert any("走在结构体构造之前" in p for p in problems), problems


def test_a_lone_drift_on_the_identifier_family_is_red(texts, bounds):
    def bump(text: str, name: str) -> str:
        return inject(text, f"const {name}: usize = 256;", f"const {name}: usize = 512;")

    lone = swap(texts, g.BOUNDS_FILE, bump(bounds, "MAX_POLICY_VERSION_BYTES"))
    problems = g.check(lone)
    assert any("短标识符长度口径出现分叉" in p for p in problems), problems
    # 反向对照：整族一起改 ⇒ 判据不响——它判的是同值，不是等于 256
    for path, name in g.IDENT_LEN_CONSTS:
        if name != "MAX_POLICY_VERSION_BYTES":
            lone[g.key(path)] = bump(lone[g.key(path)], name)
    lone[g.key(g.DENYLIST_FILE)] = bump(lone[g.key(g.DENYLIST_FILE)], g.ENTRY_CAP_CONST)
    assert g.check(lone) == []


def test_reinlined_url_cap_in_the_broker_is_red(texts, broker):
    """同一条上限写回两遍就是漂移面（R9-B61 第二判据拦的形态在新面上的复写）。"""
    reinlined = inject(
        broker,
        URL_CALL,
        "        if raw_url.len() > MAX_FFI_URL_BYTES {\n"
        '            return ffi_deny("ffi_url_too_long", "", "");\n        }\n',
    )
    problems = g.check(swap(texts, g.BROKER_FILE, reinlined))
    assert any("又内联了" in p for p in problems), problems


def test_an_entry_that_drops_the_shared_guard_is_red(texts, broker):
    problems = g.check(swap(texts, g.BROKER_FILE, inject(broker, GUARD_BLOCK, "")))
    assert any("`evaluate_navigation` 不再经 `input_bounds::`" in p for p in problems), problems


def test_the_guard_must_precede_the_deep_parse_is_red(texts, broker):
    """同一条守卫挪到 `canonicalize_external` 之后：深解析已经发生了。"""
    assert 0 <= broker.find(GUARD_BLOCK) < broker.find(PARSE_LINE), "现读顺序与判据假设不符"
    moved = inject(broker, GUARD_BLOCK, "").replace(PARSE_LINE, PARSE_LINE + GUARD_BLOCK, 1)
    assert moved.count(GUARD_BLOCK) == 1, "注入本身没生效"
    problems = g.check(swap(texts, g.BROKER_FILE, moved))
    assert any("深解析或文案拼装已经发生了" in p for p in problems), problems


def test_a_key_handed_to_the_deny_text_whole_is_red(texts, bounds):
    """把守卫的文案改回 core 里 `session_not_found` 那形态（整串回显）——
    这条判的不是「有没有上限」，是「超长输入的原样会不会被回显」。"""
    echoed = inject(
        bounds,
        ECHO_DETAIL,
        '                "会话 {} 不存在或已过期",\n                session_id,\n',
    )
    problems = g.check(swap(texts, g.BOUNDS_FILE, echoed))
    assert any("以整串形态出现" in p and "session_id" in p for p in problems), problems


def test_inline_interpolation_of_the_key_is_red_too(texts, bounds):
    """同一件事的第二种写法：内插参数藏在字面量里，字面量剔除法看不见它，所以另有判据。
    反向对照：这条必须只响内插那条，不响整串那条——否则两条判据在判同一件事，是重复。"""
    interpolated = inject(
        bounds,
        ECHO_DETAIL,
        '                "会话 {session_id} 超长",\n'
        "                session_id.len(),\n"
        "                tab_id.len()\n",
    )
    problems = g.check(swap(texts, g.BOUNDS_FILE, interpolated))
    assert any("内插了 `session_id` 整串" in p for p in problems), problems
    assert not any("以整串形态出现" in p for p in problems), problems


def test_renamed_r9_b63_anchors_report_collapse_not_pass(texts, bounds):
    for old, new in (
        ("policy_version_ok", "version_shape_ok"),
        ("navigation_entry_refusal", "entry_refusal"),
    ):
        problems = g.check(swap(texts, g.BOUNDS_FILE, bounds.replace(old, new)))
        assert any("不在位" in p for p in problems), (old, problems)

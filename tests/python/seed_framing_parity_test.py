# seed_framing_parity_test.py —— R7-CS1-05 / R7-CS2-10 门禁自身的回归面（第七轮）。
#
# 门禁 verify_seed_framing_parity.py 钉的是「三端种子按顶层框定 + 后缀清单单源」。
# 本文件钉门禁自己：植入的每一类漂移都必须让它变红，且**解析塌陷/清单读空一律
# 判环境错误而非通过**（R7-TOOL-04 同型：能扫 0 项的门禁等于没有门禁）。
from __future__ import annotations

import pathlib

import pytest
import verify_seed_framing_parity as vsp

REPO = pathlib.Path(__file__).resolve().parents[2]


def _copy_with(monkeypatch, tmp_path, attr: str, mutate) -> None:
    src: pathlib.Path = getattr(vsp, attr)
    with src.open(encoding="utf-8", newline="") as handle:   # read_text(newline=) 要 3.13+
        text = handle.read()
    mutated = mutate(text)
    assert mutated != text, f"故障注入未改动 {attr}（锚点失配——用例自己会恒绿）"
    target = tmp_path / src.name          # pytest 托管目录，不污染工作树
    target.write_text(mutated, encoding="utf-8", newline="")
    monkeypatch.setattr(vsp, attr, target)


def test_current_tree_is_parity_clean():
    assert vsp.violations() == []


def test_kotlin_missing_entry_is_flagged(monkeypatch, tmp_path):
    _copy_with(monkeypatch, tmp_path, "KT", lambda s: s.replace("'co.il',", "", 1))
    assert any("Kotlin 缺" in p and "co.il" in p for p in vsp.violations())


def test_csharp_extra_entry_is_flagged(monkeypatch, tmp_path):
    _copy_with(monkeypatch, tmp_path, "CS_SEED", lambda s: s.replace('"co.uk",', '"co.uk","zq.example",', 1))
    assert any("C# 多出" in p and "zq.example" in p for p in vsp.violations())


def test_csharp_duplicate_entry_is_flagged(monkeypatch, tmp_path):
    _copy_with(monkeypatch, tmp_path, "CS_SEED", lambda s: s.replace('"co.uk",', '"co.uk","co.uk",', 1))
    assert any("C# 表内含重复条目" in p for p in vsp.violations())


def test_rust_reverting_to_hand_copied_table_is_flagged(monkeypatch, tmp_path):
    # 两重：{psl} 锚点失配 + 残留手抄条目——手抄表回来就是漂移面回来
    _copy_with(monkeypatch, tmp_path, "RS", lambda s: s.replace(
        "var AEGIS_PUBLIC_SUFFIXES = {psl};",
        "var AEGIS_PUBLIC_SUFFIXES = {'co.uk': 1, 'org.uk': 1};"))
    problems = vsp.violations()
    assert any("{psl} 锚点失配" in p for p in problems)
    assert any("手抄表条目" in p for p in problems)


def test_frame_only_seed_key_is_flagged(monkeypatch, tmp_path):
    # R7-CS1-05 缺陷形态回归：本帧 hostname 直接当站点键
    _copy_with(monkeypatch, tmp_path, "CS_MAIN", lambda s: s.replace(
        "getETLD1(aegisTopLevelHostname())", "getETLD1(location.hostname)", 1))
    problems = vsp.violations()
    assert any("缺顶层框定要件" in p for p in problems)
    assert any("残留本帧口径缺陷形态" in p for p in problems)


def test_missing_ancestor_channel_is_flagged(monkeypatch, tmp_path):
    # 要件取代码形态：只留一句注释提到 ancestorOrigins 不算通过（锚点空心化）
    _copy_with(monkeypatch, tmp_path, "KT",
               lambda s: s.replace("var anc = location.ancestorOrigins;",
                                   "// location.ancestorOrigins（注释顶不掉要件）", 1))
    assert any("Kotlin 缺顶层框定要件：var anc = location.ancestorOrigins;" in p
               for p in vsp.violations())


def test_collapsed_kotlin_table_is_environment_error(monkeypatch, tmp_path):
    """锚点解析不到 = 环境错误（exit 2），绝不因"扫到 0 条"判通过。"""
    _copy_with(monkeypatch, tmp_path, "KT", lambda s: s.replace("var PUBLIC_SUFFIXES = [", "var RENAME_ME = [", 1))
    with pytest.raises(SystemExit) as exc:
        vsp.violations()
    assert "解析不到" in str(exc.value)


def test_empty_authoritative_list_is_environment_error(monkeypatch, tmp_path):
    empty = tmp_path / "public-suffix-list.txt"
    empty.write_text("# 只剩注释\n\n", encoding="utf-8")
    monkeypatch.setattr(vsp, "LIST_PATH", empty)
    with pytest.raises(SystemExit) as exc:
        vsp.violations()
    assert "判环境错误" in str(exc.value)


def test_missing_input_file_is_environment_error(monkeypatch, tmp_path):
    monkeypatch.setattr(vsp, "KT", tmp_path / "gone.kt")
    with pytest.raises(SystemExit) as exc:
        vsp.violations()
    assert "门禁输入缺失" in str(exc.value)


def test_authoritative_entries_are_well_formed():
    entries = vsp.authoritative_entries()
    assert len(entries) >= vsp.MIN_ENTRIES
    assert len(set(entries)) == len(entries)
    # 三端曾各持的条目都在（漂移的具体代价被钉住）
    for entry in ("github.io", "co.il", "edu.cn", "appspot.com"):
        assert entry in entries, entry


def test_gate_is_wired_into_the_required_contracts_job():
    """门禁必须挂在常跑 job 里——存在但从不运行的门禁等于没有（R6-26 教训）。"""
    workflow = (REPO / ".github" / "workflows" / "contracts.yml").read_text(encoding="utf-8")
    assert "verify_seed_framing_parity.py" in workflow

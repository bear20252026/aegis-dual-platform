"""engine_metadata_test.py —— 第九轮 R9-SH-9：引擎「展示名 + 默认值」跨端判据的回归面。

判据本体在 `scripts/engine_metadata.py`（由 `verify_cross_end_lists.py` 调用）。
本文件钉四件事：现树一致、现树扫描面非空（空面＝恒绿）、四类漂移各判得出、
legacy 缺失时是降级而不是放行。
"""
from __future__ import annotations

import pathlib

import engine_metadata as em
import pytest

REPO = pathlib.Path(__file__).resolve().parents[2]
CORE = {"baidu", "bing", "google", "sogou"}


def _tree(**overrides: str) -> dict[str, str]:
    """一套四端一致的合成树；overrides 按文件名替换正文。"""
    base = {
        em._URL_UTILS: 'DEFAULT_ENGINE = "baidu"\n'
                       'SEARCH_ENGINES = {\n'
                       '    "baidu":  ("百度", "https://www.baidu.com/s?wd={}"),\n'
                       '    "bing":   ("必应", "https://www.bing.com/search?q={}"),\n'
                       '    "google": ("谷歌", "https://www.google.com/search?q={}"),\n'
                       '    "sogou":  ("搜狗", "https://www.sogou.com/web?query={}"),\n'
                       '}\n',
        em._KOTLIN: 'const val DEFAULT_ENGINE: String = "baidu"\n'
                    'internal val ENGINE_NAMES: Map<String, String> =\n'
                    '    mapOf("baidu" to "百度", "bing" to "必应",'
                    ' "google" to "谷歌", "sogou" to "搜狗")\n',
        em._CSHARP: 'public const string DefaultEngine = "baidu";\n'
                    'public static readonly IReadOnlyDictionary<string, string> EngineNames =\n'
                    '    new Dictionary<string, string>(StringComparer.Ordinal)\n'
                    '    {\n'
                    '        ["baidu"] = "百度",\n'
                    '        ["bing"] = "必应",\n'
                    '        ["google"] = "谷歌",\n'
                    '        ["sogou"] = "搜狗",\n'
                    '        ["so360"] = "360搜索",\n'
                    '    };\n',
        em._SHELL: "function engineFallback() {\n"
                   "  return { engine: 'baidu', engines: [\n"
                   "    { key: 'baidu', name: '百度' },\n"
                   "    { key: 'bing', name: '必应' },\n"
                   "    { key: 'google', name: '谷歌' },\n"
                   "    { key: 'sogou', name: '搜狗' }\n"
                   "  ]};\n"
                   "}\n",
        em._HTML: '<span id="engineName">百度</span>\n',
    }
    base.update(overrides)
    return base


def _read(tree: dict[str, str]):
    def read(rel: str) -> str:
        return tree.get(rel, "")
    return read


def _exists(tree: dict[str, str]):
    """「文件在不在」——与对面门禁的 (ROOT / rel).is_file() 同语义（SP-154 降级判据）。"""
    return lambda rel: rel in tree


def _fails(tree: dict[str, str]) -> list[str]:
    return [msg for msg, kind in em.check(CORE, _read(tree), _exists(tree)) if kind == "fail"]


# ---------------------------------------------------------------- 现树

def test_real_tree_is_consistent():
    read = lambda rel: (REPO / rel).read_text(encoding="utf-8")  # noqa: E731
    exists = lambda rel: (REPO / rel).is_file()  # noqa: E731
    assert em.check(CORE, read, exists) == []


def test_real_tree_scan_surface_is_not_empty():
    """四端都必须真的解析出东西——空表在对面门禁里计 fail，但这里直接钉住
    「判据有输入」，防止路径改名让整条判据退化成恒绿。"""
    read = lambda rel: (REPO / rel).read_text(encoding="utf-8")  # noqa: E731
    names = em.extract_names(read)
    assert sorted(names) == sorted(label for label, *_ in em._NAME_SLOTS)
    assert all(len(table) >= 4 for table in names.values()), names
    defaults = em.extract_defaults(read)
    assert len(defaults) == len(em._DEFAULT_SLOTS), defaults
    assert em.html_initial_label(read), "start.html 初始标签解析不到＝该项从不参与判定"


def test_slot_paths_exist_in_repo():
    """表里写的文件路径必须还在（本仓反复出现「锚指向已挪走的文件」的失配）。"""
    rels = {rel for _label, rel, *_rest in em._NAME_SLOTS}
    rels |= {rel for _label, rel, _p, _h in em._DEFAULT_SLOTS}
    rels.add(em._HTML)
    missing = [rel for rel in sorted(rels) if not (REPO / rel).is_file()]
    assert not missing, f"判据面指向不存在的文件：{missing}"


# ---------------------------------------------------------------- 四类漂移

def test_display_name_drift_is_detected():
    tree = _tree()
    tree[em._KOTLIN] = tree[em._KOTLIN].replace('"baidu" to "百度"', '"baidu" to "百渡"')
    found = _fails(tree)
    assert len(found) == 1 and "引擎展示名不一致: baidu" in found[0], found


def test_extension_engine_names_are_out_of_scope():
    """C# 扩展引擎（so360）只有 C# 与 legacy 有——不进面，否则判据会逼壳层猜名字。"""
    assert "so360" not in CORE
    assert _fails(_tree()) == []


def test_default_engine_drift_is_detected():
    tree = _tree()
    tree[em._CSHARP] = tree[em._CSHARP].replace('DefaultEngine = "baidu"', 'DefaultEngine = "bing"')
    found = _fails(tree)
    assert len(found) == 1 and found[0].startswith("默认引擎不一致"), found
    assert "windows/UrlNormalizer.cs=bing" in found[0], found


def test_default_engine_must_be_a_core_engine():
    tree = _tree()
    for key in (em._URL_UTILS, em._KOTLIN, em._CSHARP, em._SHELL):
        tree[key] = tree[key].replace("baidu", "qwant")
    found = _fails(tree)
    assert any("不在核心引擎集" in msg for msg in found), found


def test_html_initial_label_must_match_the_default_engine_name():
    tree = _tree()
    tree[em._HTML] = '<span id="engineName">必应</span>\n'
    found = _fails(tree)
    assert len(found) == 1 and "胶囊初始文字" in found[0] and "≠ 默认引擎展示名" in found[0], found


def test_missing_table_is_a_failure_not_a_skip():
    tree = _tree()
    tree[em._SHELL] = "// engineFallback 被删了\n"
    found = _fails(tree)
    assert any("未找到引擎展示名表" in msg for msg in found), found
    assert any("找不到默认引擎字面量" in msg for msg in found), found


def test_all_tables_unparseable_is_not_green():
    tree = {key: "" for key in _tree()}
    found = [msg for msg, kind in em.check(CORE, _read(tree), _exists(tree)) if kind == "fail"]
    assert any("四端全部解析失败" in msg for msg in found), found


def test_legacy_missing_degrades_with_a_warning_not_a_silence():
    """SP-154 同口径：legacy 归档端缺失 ⇒ 现役三端继续判 + 一条告警（不是整条判据失效）。"""
    tree = _tree()
    del tree[em._URL_UTILS]          # 归档端文件不在了（SP-154：降级，不断链）
    results = em.check(CORE, _read(tree), _exists(tree))
    assert [kind for _msg, kind in results] == ["warn"], results
    assert "现役三端" in results[0][0], results

    tree[em._URL_UTILS] = ""          # 文件在、表解析不出来 ⇒ 除告警外还必须有 fail
    results = em.check(CORE, _read(tree), _exists(tree))
    assert any(kind == "fail" for _msg, kind in results), results


def test_csharp_extension_names_never_trigger_drift():
    """C# 表里多出来的扩展引擎名字，不影响核心集判据（对照：核心名一改就红）。"""
    tree = _tree()
    tree[em._CSHARP] = tree[em._CSHARP].replace('["so360"] = "360搜索",', '["so360"] = "叁陆零",')
    assert _fails(tree) == []


@pytest.mark.parametrize("slot", list(em._NAME_SLOTS))
def test_every_end_is_represented_in_the_name_surface(slot):
    """槽表逐项驱动：每端都必须能被解析出核心四引擎的名字（少一端＝判据面缺端）。"""
    label, rel, _block_re, _pair_re = slot
    names = em.extract_names(_read(_tree()))
    assert label in names
    assert set(names[label]) >= CORE, f"{label} 缺核心引擎展示名：{sorted(names[label])}"
    assert rel in _tree(), f"{label} 的合成夹具缺文件，测不到它"

def test_empty_core_degrades_with_a_warning_not_a_cascade():
    """核心集为空 ⇒ 比对无从进行（对面门禁此时已因 key 集为空而 fail）——
    这里必须只出一条告警，不能叠三条「缺表」把同一次失败伪装成多个缺陷。"""
    results = em.check(set(), _read(_tree()), _exists(_tree()))
    assert [kind for _msg, kind in results] == ["warn"], results
    assert "无从判定" in results[0][0], results

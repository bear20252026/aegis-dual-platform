# vector_consumers_test.py —— AEG-006（外部第三轮审计 2026-10-11）向量**逐端消费分布**门禁的常驻锚。
#
# 两件事分开做：
# ① 现树事实（21 份向量 / 13 份有端侧执行者 / 8 份只在 schema 层被判 / 2 份真两端同跑）
#    （R9-B35 加 6 份：release/version 四条为实例级、只由 schema 层判；
#     semver-form 两条由 tests/python/semver_schema_parity_test.py 逐案执行）
#    被钉成断言——数字漂了必须是有意识的动作，改登记表要同批在台账写理由；
# ② 门禁的每条判据都在这里被注入证伪。这部分原本写在脚本的 `--self-test` 里，本批搬进
#    pytest：一条要人主动敲 flag 的自证就是「跑不动的判据」（R9-SH-7 的同一课）。
#
# 「消费者」不包括 markdown 提及（那是声明），也不包括元层 META_LEVEL 那五个文件——
# 它们（含本门禁自己与它的用例）按名遍历整个向量目录，判的是形状/expected，# 不是「哪端实现了这个裁决」。
from __future__ import annotations

import importlib.util
import re
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "verify_vector_consumers.py"


def load():
    spec = importlib.util.spec_from_file_location("verify_vector_consumers", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="session")
def real():
    """实树扫描一次给多个用例复用（单遍 ≈1.5s；逐用例重扫会把 PR 面拖成分钟级）。"""
    vvc = load()
    texts = vvc.scan_surface(vvc.tracked_files())
    vectors = vvc.vector_files()
    violations, report = vvc.check(texts, vectors)
    return vvc, texts, vectors, violations, report


def ends_of(vvc, texts, vectors, name):
    return frozenset({vvc.end_of(h) for h in vvc.collect_consumers(texts, vectors)[name]})


def test_real_tree_matches_the_registered_manifest(real):
    _, _, _, violations, _ = real
    assert not violations, "向量逐端消费面违规：" + "；".join(violations)


def test_registered_manifest_covers_every_vector_file(real):
    vvc, _, vectors, _, _ = real
    assert set(vvc.CONSUMER_MANIFEST) == {p.name for p in vectors}, (
        "登记表与 contracts/vectors 目录不再是同一集合——增删向量必须同批改表")


def test_current_coverage_facts_are_11_4_2(real):
    """11 份有端侧执行者 / 4 份仅 schema 级 / 2 份 CS∧AD 同跑——AEG-006 的实证口径。"""
    vvc, texts, vectors, _, report = real
    consumers = vvc.collect_consumers(texts, vectors)
    executable = sum(1 for hits in consumers.values() if hits)
    schema_only = sorted(name for name, hits in consumers.items() if not hits)
    cross = sorted(name for name, hits in consumers.items()
                   if {"CS", "AD"} <= {vvc.end_of(h) for h in hits})
    assert (executable, len(vectors)) == (13, 21), f"端侧执行面变了：{executable}/{len(vectors)}"
    assert schema_only == [
        "audit-event-invalid.json", "audit-event-valid.json",
        "capability-invalid.json", "capability-valid.json",
        "release-invalid.json", "release-valid.json",
        "version-invalid.json", "version-valid.json"], f"仅 schema 级的集合变了：{schema_only}"
    assert cross == ["url-origin-invalid.json", "url-origin-valid.json"], (
        f"两端同跑的向量变了：{cross}——这正是「跨端同一裁决」的全部支点")
    assert len(report) == 21


def test_url_origin_family_is_the_only_cross_end_pillar(real):
    vvc, texts, vectors, _, _ = real
    assert ends_of(vvc, texts, vectors, "url-origin-invalid.json") >= {"CS", "AD", "RS"}
    # 反向控制：native-navigation-decision 只到 C#+Rust，不许被读成「跨端已覆盖」。
    assert "AD" not in ends_of(vvc, texts, vectors, "native-navigation-decision.json")


def test_losing_the_android_consumer_turns_the_gate_red(real):
    """支点下界不是摆设：从语料里摘掉 Android 侧消费者，门禁必须判红。"""
    vvc, texts, vectors, _, _ = real
    stripped = {k: v for k, v in texts.items() if not k.startswith("android/")}
    violations, _ = vvc.check(stripped, vectors)
    assert any("消费面漂移" in v and "url-origin" in v for v in violations), (
        "摘掉 Android 消费者却仍绿＝这条判据是装饰")
    assert any("支点" in v for v in violations), "跨端支点归零必须单独报错（不随登记表松动）"


def test_single_pass_equals_the_naive_per_vector_scan(real):
    """合并正则（单遍）与朴素逐向量扫描必须给出同一个消费者集——
    否则本批把 12.4s 降到 ≈1s 的「提速」本身就改了判据。"""
    vvc, texts, vectors, _, _ = real
    fast = {k: sorted(v) for k, v in vvc.collect_consumers(texts, vectors).items()}
    slow: dict[str, list[str]] = {p.name: [] for p in vectors}
    for rel, text in texts.items():
        if rel in set(vvc.META_LEVEL):
            continue
        for path in vectors:
            if re.search(r"(?<![\w.-])" + re.escape(path.stem) + r"(?![\w-])", text):
                slow[path.name].append(rel)
    assert fast == {k: sorted(v) for k, v in slow.items()}


def test_surface_collapse_exits_2(tmp_path, monkeypatch):
    vvc = load()
    thin = tmp_path / "vectors"
    thin.mkdir()
    for name in ("a.json", "b.json"):
        (thin / name).write_text("[]", encoding="utf-8")
    monkeypatch.setattr(vvc, "VECTORS_DIR", thin)
    assert vvc.run() == 2, "向量面塌缩必须判「扫描面不可用」而不是通过"


def test_empty_scan_surface_exits_2(monkeypatch, capsys):
    vvc = load()
    monkeypatch.setattr(vvc, "tracked_files", lambda: ["README.md"])
    assert vvc.run() == 2, "受管源码面为空＝没有判定面，不能报绿"
    assert "没有判定面" in capsys.readouterr().err


def test_missing_vectors_dir_exits_2(tmp_path, monkeypatch):
    vvc = load()
    monkeypatch.setattr(vvc, "VECTORS_DIR", tmp_path / "nope")
    assert vvc.run() == 2


# ===== 判据的注入式自证（从脚本的 --self-test 搬进常跑面）=====
# 一个要人主动敲 flag 的自证＝「跑不动的判据」；放在 pytest 里才是每条 PR 都执行。

END_SAMPLE = {
    "CS": "windows/tests/Sample.cs", "AD": "android/app/src/test/Sample.kt",
    "RS": "core/rust-policy-core/tests/samples.rs", "PY": "tests/python/samples_test.py",
    "CI": ".github/workflows/samples.yml", "AG": "agent/samples.py",
}


def fake_corpus(vvc):
    """按登记表生成语料：正向用例要「按构造成立」，而不是碰巧凑出来。
    额外塞一条元层命中——它必须被排除在端侧之外，否则 capability/audit-event
    的空端集就不成立，正向用例会因别的原因报错。"""
    texts = {vvc.META_LEVEL[0]: 'capability-valid.json\naudit-event-valid.json'}
    for name, ends in vvc.CONSUMER_MANIFEST.items():
        for end in ends:
            path = END_SAMPLE[end]
            texts[path] = texts.get(path, "") + f'\nread("{name}")\n'
    return texts


def fake_vectors(vvc, *extra):
    return [Path("contracts/vectors") / n
            for n in (*sorted(vvc.CONSUMER_MANIFEST), *extra)]


def vectors_named(*names):
    return [Path("contracts/vectors") / n for n in names]


def test_synthetic_corpus_satisfies_the_manifest():
    vvc = load()
    violations, report = vvc.check(fake_corpus(vvc), fake_vectors(vvc))
    assert not violations, "登记表与按表构造的语料不自洽：" + "；".join(violations)
    assert len(report) == len(vvc.CONSUMER_MANIFEST)


def test_unregistered_new_vector_is_red():
    vvc = load()
    violations, _ = vvc.check(fake_corpus(vvc), fake_vectors(vvc, "brand-new-family.json"))
    assert any("brand-new-family.json" in v and "不在 CONSUMER_MANIFEST" in v
               for v in violations), "新增向量不登记也能绿＝覆盖面可以随便扩"


def test_gaining_an_end_without_editing_the_manifest_is_red():
    vvc = load()
    gained = dict(fake_corpus(vvc), **{"agent/executor.py": 'read("glob-match.json")'})
    violations, _ = vvc.check(gained, fake_vectors(vvc))
    assert any("glob-match.json" in v and "消费面漂移" in v for v in violations), \
        "凭空多出一端执行没被抓＝悄悄扩面进不了台账"


def test_stale_registration_is_red():
    vvc = load()
    violations, _ = vvc.check(fake_corpus(vvc), vectors_named("glob-match.json"))
    assert any("过期登记" in v for v in violations), "表里有、实树没有＝过期声明必须响"


def test_stem_must_be_a_whole_word():
    vvc = load()
    vectors = fake_vectors(vvc)
    assert not vvc.collect_consumers(
        {"agent/odd.py": "url-origin-validfoo"}, vectors)["url-origin-valid.json"], \
        "子串命中也算消费者＝任何提到它的文本都会冒充成执行者"
    # 反向控制：同一语料写全名必须算命中，否则上一条是恒真断言。
    assert vvc.collect_consumers(
        {"agent/odd.py": "url-origin-valid.json"}, vectors
    )["url-origin-valid.json"] == ["agent/odd.py"]


def test_comment_only_citation_is_not_a_consumer():
    """R9-B39 / Q53：注释里写出向量文件名**不算消费者**。

    起因是本仓自己的一次过度登记：`native-navigation-decision.json` 被记成
    「CS+RS 都在跑」，而 CS 那一面只来自 `BrowserPolicyBrokerNativeGateTests.cs`
    的一句解释性注释——没有任何代码读那份向量。覆盖面是靠「这端跑过」这句话立起来的，
    让注记冒充执行者等于把门禁改成自我声明。
    """
    vvc = load()
    vectors = fake_vectors(vvc)
    cited = "url-origin-valid.json"
    nl = chr(10)
    cases = (
        ("windows/src/A.cs", "    // 与 " + cited + " 同口径" + nl + "        Assert.True(true);"),
        ("android/a/K.kt", "    /* 见 " + cited + " 的期望值 */" + nl + "    val x = 1"),
        ("core/r/r.rs", "/* 注记" + nl + " * 提到 " + cited + nl + " */" + nl + "fn f() {}"),
        ("agent/a.py", "# 参照 " + cited + nl + "x = 1"),
        ("shared/s.mjs", "  * KDoc 续行 " + cited + nl + "const a = 1;"),
    )
    for path, body in cases:
        stripped = vvc.strip_comments(body, path)
        assert cited in body, f"语料本身没造出来：{path}"
        assert cited not in stripped, f"{path} 的注释形态没被剔净 ⇒ 它会冒充消费者"
        assert not vvc.collect_consumers({path: stripped}, vectors)[cited], path
    # 正面控制：同一文件名写进代码行必须算命中（否则上面全是恒真断言）。
    code = f'const v = load("{cited}");'
    assert vvc.collect_consumers(
        {"shared/s.mjs": vvc.strip_comments(code, "shared/s.mjs")}, vectors)[cited] == ["shared/s.mjs"]


def test_cross_end_pillar_floor_does_not_move_with_the_manifest():
    """把跨端两份改成单端登记，支点下界仍要判红——否则 AEG-006 可以靠改表被说反。"""
    vvc = load()
    saved = dict(vvc.CONSUMER_MANIFEST)
    try:
        vvc.CONSUMER_MANIFEST = {
            **saved,
            "url-origin-valid.json": frozenset({"RS"}),
            "url-origin-invalid.json": frozenset({"RS"}),
        }
        violations, _ = vvc.check({"core/x/tests/a.rs": "url-origin-valid"},
                                 vectors_named("url-origin-valid.json"))
        assert any("支点" in v for v in violations)
    finally:
        vvc.CONSUMER_MANIFEST = saved


def test_meta_level_path_drift_is_reported():
    vvc = load()
    assert vvc.check_meta_paths_exist(
        list(vvc.CONSUMER_MANIFEST) + list(vvc.META_LEVEL)) == []
    assert any("META_LEVEL 集合过期" in v
               for v in vvc.check_meta_paths_exist(["scripts/other.py"]))


def test_gate_runs_on_the_pr_triggered_contract_surface():
    doc = yaml.safe_load((ROOT / ".github" / "workflows" / "contracts.yml").read_text(encoding="utf-8"))
    holders = []
    for job_name, spec in (doc.get("jobs") or {}).items():
        for step in (spec or {}).get("steps") or []:
            if "verify_vector_consumers.py" in str(step.get("run") or ""):
                holders.append((job_name, str(spec.get("runs-on")),
                                list((doc.get("on") or {}).keys())))
    assert holders, "门禁没接进任何 job——登记了却不执行，正是本批要消灭的形态"
    job_name, runs_on, triggers = holders[0]
    assert "pull_request" in triggers, f"{job_name} 不在 PR 触发面上"
    assert "ubuntu" in (runs_on or "").lower(), f"接线 job 异常：{job_name} runs-on={runs_on}"

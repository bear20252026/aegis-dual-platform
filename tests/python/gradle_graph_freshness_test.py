# gradle_graph_freshness_test.py —— R9-B47（第九轮 Q56 / R9-CI-14）的门禁用例。
#
# 这条判据存在的理由不是「图不够新」，而是**图静默停止更新时全仓没有一张牌会红**：
# gradle-dependency-graph.yml 只在 master push / 周检 / 手动触发，PR 面零执行。
# 所以每条都要能红（内存态注入，不联网、不改工作树），并有一条正面控制证明
# 解析面不是空的——空对空永远一致。
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import verify_gradle_graph_freshness as g


def sbom_doc(names: list[str]) -> dict:
    return {"sbom": {"packages": [{"name": n} for n in names]}}


def test_real_lock_surface_is_not_collapsed() -> None:
    """正面控制：锁解析必须真的给出几百条坐标，否则「零个缺失」是恒真。"""
    locked = g.lock_coordinates()
    assert len(locked) >= 200, f"锁面异常：{len(locked)} 条"
    assert "androidx.webkit:webkit" in locked, "解析形状不对（认不出 group:name）"


def pad_graph(extra: set[str]) -> set[str]:
    """合成图必须过面塌缩下界——否则「绿」用例其实在测另一条判据。"""
    filler = {f"pad{i}:art" for i in range(g.MIN_GRAPH_COORDINATES)}
    return extra | filler


def test_matching_graph_is_green() -> None:
    problems, code = g.verdict({"a:b", "c:d"}, pad_graph({"a:b", "c:d", "e:f"}))
    assert problems == [] and code == 0


def test_coordinate_missing_from_graph_is_red() -> None:
    """锁里有、图里没有＝提交链没跑成或没落图——正是本判据要抓的那一件事。"""
    problems, code = g.verdict({"a:b", "ghost:coord"}, {"a:b"} | {f"x{i}:y" for i in range(250)})
    assert code == 1
    assert any("ghost:coord" in p and "依赖图" in p for p in problems), problems


def test_empty_graph_is_red_not_green() -> None:
    problems, code = g.verdict({"a:b"}, set())
    assert code == 1 and any("为空" in p for p in problems), problems


def test_collapsed_graph_surface_is_red() -> None:
    """面塌缩（图只剩几十条）比「有缺失」更危险——不能读成通过。"""
    small = {f"g{i}:n" for i in range(g.MIN_GRAPH_COORDINATES - 5)}
    problems, code = g.verdict(set(), small)
    assert code == 2 and problems, problems          # 锁面为空＝环境错误，优先于图面判定
    problems, code = g.verdict({"a:b"}, small | {"a:b"})
    assert code == 1 and any("面塌缩" in p for p in problems), problems


def test_report_is_bounded_but_counts_everything() -> None:
    locked = {f"grp{i}:art" for i in range(30)}
    graph = {f"grp{i}:art" for i in range(10)} | {f"x{i}:y" for i in range(300)}
    problems, code = g.verdict(locked, graph)
    assert code == 1
    text = " ".join(problems)
    assert f"共 {len(locked - graph)} 条" in text, text
    assert text.count("grp") <= g.MAX_REPORTED + 1, "报告必须截断，否则日志被坐标列表淹没"


def test_malformed_sbom_is_environment_error(tmp_path) -> None:
    bad = tmp_path / "sbom.json"
    bad.write_text(json.dumps({"unexpected": 1}), encoding="utf-8")
    assert g.run(str(bad)) == 2, "形状不对的 SPDX 必须判环境错误，不能判「图里零坐标＝红」的假信号"


def test_offline_document_round_trip(tmp_path) -> None:
    """`--sbom` 的本地复跑口径：绿与红都要能从同一个入口出来。"""
    everything = sorted(g.lock_coordinates())
    good = tmp_path / "good.json"
    good.write_text(json.dumps(sbom_doc(sorted(pad_graph(set(everything))))), encoding="utf-8")
    assert g.run(str(good)) == 0
    partial = tmp_path / "partial.json"
    partial.write_text(json.dumps(sbom_doc(sorted(pad_graph(set(everything[:-1]))))),
                       encoding="utf-8")
    assert g.run(str(partial)) == 1


def test_missing_token_is_environment_error(monkeypatch) -> None:
    """取不到图 ≠ 图是新鲜的——必须 exit 2（这是「门禁永远不红」最常见的成因）。"""
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("AEGIS_GRAPH_TOKEN", raising=False)
    monkeypatch.delenv("GITHUB_REPOSITORY", raising=False)
    assert g.run("") == 2


def test_min_floor_is_below_today_reality() -> None:
    """下界必须留余量：图今天有几百条，把它调到实际值以下才叫判据而不是快照。"""
    assert g.MIN_GRAPH_COORDINATES < 300
    assert g.MAX_REPORTED < 20

def test_retry_gives_the_graph_time_before_going_red(monkeypatch) -> None:
    """落图是最终一致的：第一次判红必须复判，重试耗尽才红。

    把「慢」读成「坏」的判据，教会人的是忽略红灯——那比没有判据更贵。
    """
    everything = sorted(g.lock_coordinates())
    calls = {"n": 0}

    def flaky(token: str, repository: str) -> dict:
        calls["n"] += 1
        if calls["n"] == 1:
            return sbom_doc(sorted(pad_graph(set(everything[:-1]))))   # 还差最后一条
        return sbom_doc(sorted(pad_graph(set(everything))))

    monkeypatch.setattr(g, "fetch_sbom", flaky)
    monkeypatch.setenv("GITHUB_TOKEN", "t")
    monkeypatch.setenv("GITHUB_REPOSITORY", "o/r")
    assert g.run("", attempts=3, delay=0.0) == 0
    assert calls["n"] == 2

    calls["n"] = 0
    assert g.run("", attempts=1, delay=0.0) == 1, "不重试时同一份迟到数据必须判红——判据不能被重试掩掉"

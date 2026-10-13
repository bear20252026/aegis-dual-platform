# gradle_alert_scope_test.py —— R9-B49（分诊文档 §三那 9 条 dismiss 的边界）的门禁用例。
#
# dismiss 一个 Dependabot 告警是对该仓安全姿态的正式声明，而它依赖的事实
# （「这些坐标只在构建/测试工具类路径里」）会被一次普通的 `implementation` 依赖变更推翻。
# 所以每条判据都要能红：越界到出货面、越界到装机面、坐标消失（登记过期）、面塌缩。
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import verify_gradle_alert_scope_boundary as g


@pytest.fixture(scope="module")
def locked() -> dict[str, set[str]]:
    return g.locked_configurations()


def test_real_tree_passes(locked) -> None:
    assert g.violations(locked) == []
    assert g.run() == 0


def test_registry_is_not_vacuous(locked) -> None:
    """正面控制：登记表里每个坐标都必须真的在锁里，且出现的都是工具/测试面。"""
    for coordinate in g.DISMISSED_TOOLING_ONLY:
        configs = locked.get(coordinate)
        assert configs, f"{coordinate} 不在锁里——登记表与实树已经不一致"
        assert not any(g.is_shipped(c) for c in configs), f"{coordinate} 已进出货面：{configs}"
    assert len(locked) >= 200, f"锁面异常：{len(locked)} 条坐标"


@pytest.mark.parametrize("configuration,shipped", [
    ("releaseRuntimeClasspath", True),
    ("debugRuntimeClasspath", True),
    ("releaseCompileClasspath", True),
    ("debugAndroidTestRuntimeClasspath", True),      # 装进设备的那份也算暴露面
    ("androidLintTool", False),
    ("ktlint", False),
    ("detekt", False),
    ("debugUnitTestRuntimeClasspath", False),
    ("debugUnitTestCompileClasspath", False),
    ("debugUnitTestLintChecksClasspath", False),
    ("releaseLintChecksClasspath", False),
    ("kotlinCompilerClasspath", False),
])
def test_configuration_classification(configuration: str, shipped: bool) -> None:
    assert g.is_shipped(configuration) is shipped


def test_coordinate_moving_into_shipped_classpath_is_red(locked) -> None:
    tampered = {k: set(v) for k, v in locked.items()}
    tampered["org.bouncycastle:bcprov-jdk18on"].add("releaseRuntimeClasspath")
    problems = g.violations(tampered)
    assert any("出货/装机面" in p and "bcprov" in p for p in problems), problems


def test_coordinate_moving_into_installed_instrumentation_is_red(locked) -> None:
    """`androidTest` 会装到设备上跑，暴露面与 APK 同级——不能因为它不是产品就放过。"""
    tampered = {k: set(v) for k, v in locked.items()}
    tampered["ch.qos.logback:logback-core"].add("debugAndroidTestRuntimeClasspath")
    assert any("logback" in p for p in g.violations(tampered))


def test_vanished_coordinate_is_reported_as_stale(locked) -> None:
    """上游把节点移除＝dismiss 的载体消失，登记表要同步而不是继续挂着。"""
    tampered = {k: set(v) for k, v in locked.items()
                if k != "org.apache.httpcomponents:httpclient"}
    problems = g.violations(tampered)
    assert any("已不存在" in p and "httpclient" in p for p in problems), problems


def test_empty_lock_surface_is_environment_error() -> None:
    problems, = (g.violations({}),)
    assert problems and "锁面为空" in problems[0]


def test_missing_doc_exits_2(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(g, "DOC", tmp_path / "nope.md")
    assert g.run() == 2
    monkeypatch.setattr(g, "DOC", ROOT / "docs" / "security" / "android-build-classpath-triage.md")
    monkeypatch.setattr(g, "LOCK_GLOBS", ("nowhere/*/gradle.lockfile",))
    assert g.run() == 2


def test_triage_doc_still_lists_every_registered_coordinate(locked) -> None:
    """文档与代码的登记表也要一致：dismiss 理由写在文档里，坐标名必须逐条能在文档中找到。"""
    text = g.DOC.read_text(encoding="utf-8")
    for coordinate in g.DISMISSED_TOOLING_ONLY:
        artifact = coordinate.split(":")[1]
        assert artifact in text, f"{artifact} 在分诊文档里找不到——文档与本门禁已经各说各话"

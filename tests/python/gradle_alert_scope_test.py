# gradle_alert_scope_test.py —— Android 工具/测试面边界门禁（R9-B49 起，R9-B93 v2）的用例。
#
# 判据建在两个事实上：**坐标落在哪条 configuration**，以及**地板 ⇄ 登记块 ⇄ 锁是否一致**。
# 两个都不是「看一眼就知道」的东西，所以每条都要能红：越界到出货面、越界到装机面、坐标消失、
# 登记面比证据面窄、地板被删、地板改了而锁没改、地板空转、登记块读不出、锁面塌缩。
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import verify_gradle_alert_scope_boundary as g

BCPROV = "org.bouncycastle:bcprov-jdk18on"
BCUTIL = "org.bouncycastle:bcutil-jdk18on"
HTTPCLIENT = "org.apache.httpcomponents:httpclient"
LOGBACK_CLASSIC = "ch.qos.logback:logback-classic"
LOGBACK_CORE = "ch.qos.logback:logback-core"


@pytest.fixture(scope="module")
def locked() -> dict[str, set[str]]:
    return g.locked_configurations()


@pytest.fixture(scope="module")
def registered() -> list[str]:
    return g.registered_coordinates()


def test_real_tree_passes(locked, registered) -> None:
    assert g.violations(locked, registered) == []
    assert g.floor_problems(g.floor_versions(), registered, g.floor_resolutions()) == []
    assert g.run() == 0


def test_registry_is_not_vacuous(locked, registered) -> None:
    """正面控制：登记块里每个坐标都必须真的在锁里，且出现的都是工具/测试面。"""
    assert len(registered) >= 7, f"登记块只读出 {len(registered)} 条，与 §3.93 记录的规模不符"
    for coordinate in registered:
        configs = locked.get(coordinate)
        assert configs, f"{coordinate} 不在锁里——登记块与实树已经不一致"
        assert not any(g.is_shipped(c) for c in configs), f"{coordinate} 已进出货面：{configs}"
    assert len(locked) >= 200, f"锁面异常：{len(locked)} 条坐标"


def test_the_two_blind_spots_b93_found_are_now_registered(registered) -> None:
    """本批那个洞的墓碑：旧版代码里那份五元组漏了这两条，而它们一直在锁的工具面上。
    门禁对**没登记的坐标一条都不判**，所以「边界有人守着」这句话当时只对 5/7 成立。"""
    assert BCUTIL in registered and LOGBACK_CLASSIC in registered, registered
    assert BCPROV in g.floor_versions(), "地板里没有 bcprov——B89 那条 force 被改了？"


def test_registry_is_read_from_the_doc_not_copied_into_code() -> None:
    """单源检查：登记面来自分诊文档那段围栏块（代码里再有第二份就会各漂各的）。"""
    text = g.DOC.read_text(encoding="utf-8")
    assert g.registry(text) == g.registered_coordinates()
    assert "tooling-only-coordinates" in text, "分诊文档里的登记块被删——门禁会 exit 2，这里先给出原因"


@pytest.mark.parametrize("configuration,shipped", [
    ("releaseRuntimeClasspath", True),
    ("debugRuntimeClasspath", True),
    ("releaseCompileClasspath", True),
    ("debugAndroidTestRuntimeClasspath", True),      # 装进设备的那份也算暴露面——不能因为它不是产品就放过
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


def test_coordinate_moving_into_shipped_classpath_is_red(locked, registered) -> None:
    tampered = {k: set(v) for k, v in locked.items()}
    tampered[BCPROV].add("releaseRuntimeClasspath")
    problems = g.violations(tampered, registered)
    assert any("出货/装机面" in p and "bcprov" in p for p in problems), problems


def test_coordinate_moving_into_installed_instrumentation_is_red(locked, registered) -> None:
    """`androidTest` 会装到设备上跑，暴露面与 APK 同级——不能因为它不是产品就放过。"""
    tampered = {k: set(v) for k, v in locked.items()}
    tampered[LOGBACK_CORE].add("debugAndroidTestRuntimeClasspath")
    assert any("logback" in p for p in g.violations(tampered, registered))


def test_vanished_coordinate_is_reported_as_stale(locked, registered) -> None:
    """上游把节点移除＝分诊结论的载体消失，登记块要同步而不是继续挂着。"""
    tampered = {k: set(v) for k, v in locked.items() if k != HTTPCLIENT}
    problems = g.violations(tampered, registered)
    assert any("已不存在" in p and "httpclient" in p for p in problems), problems


def test_empty_lock_surface_is_environment_error(registered) -> None:
    problems = g.violations({}, registered)
    assert problems and "锁面为空" in problems[0]


# ------------------------------------------------------------------ 地板 ⇄ 登记块 ⇄ 锁（R9-B93 新增）
def test_floor_version_drift_from_lock_is_red(registered) -> None:
    """B89 实测：删掉 force 后例行 `--write-locks` 会把锁退回 1.80.2。
    「地板还在、锁已经旧了」和反过来都是这条判据的对象——PR 面此前两者都抓不到。"""
    floor = dict(g.floor_versions())
    resolutions = {k: set(v) for k, v in g.floor_resolutions().items()}
    resolutions[BCPROV] = {"1.80.2"}
    problems = g.floor_problems(floor, registered, resolutions)
    assert any("1.80.2" in p and "1.86" in p and BCPROV in p for p in problems), problems
    # 同一坐标同时解析到地板版和旧版也算不一致（不是「有一个对得上就行」）
    resolutions[BCPROV] = {"1.86", "1.80.2"}
    problems = g.floor_problems(floor, registered, resolutions)
    assert any(BCPROV in p for p in problems), problems


def test_floor_coordinate_outside_the_registry_is_red(registered) -> None:
    floor = dict(g.floor_versions())
    floor["com.example:brand-new"] = "9.9.9"
    problems = g.floor_problems(floor, registered, g.floor_resolutions())
    assert any("brand-new" in p and "不在分诊文档的登记面内" in p for p in problems), problems


def test_floor_that_pins_nothing_is_red(registered) -> None:
    """地板空转：force 写在那儿，但 `androidLintTool` 面里根本没有这个构件——读起来像防护，实际没咬住。"""
    resolutions = {k: set(v) for k, v in g.floor_resolutions().items()}
    del resolutions[BCUTIL]
    problems = g.floor_problems(g.floor_versions(), registered, resolutions)
    assert any("空转" in p and "bcutil" in p for p in problems), problems


def test_dropping_one_force_line_is_red_even_though_locks_look_right(registered) -> None:
    """反向那条判据的对象：删掉 bcutil 的 force，入库锁**此刻仍然写着 1.86**，
    只看「地板说的版本锁里有没有」会全绿；下一次例行 `--write-locks` 才把它退回 1.80.2。"""
    floor = dict(g.floor_versions())
    del floor[BCUTIL]
    problems = g.floor_problems(floor, registered, g.floor_resolutions())
    assert any(BCUTIL in p and "没有地板顶着" in p for p in problems), problems
    # 红的原因是「这条坐标没人顶」，不是「锁与地板版本不一致」——后者才会列出解析到的版本
    assert not any("解析到" in p for p in problems), problems


def test_unregistered_lint_tooling_dependency_does_not_demand_a_floor(registered) -> None:
    """不哭狼：`androidLintTool` 面里本来就有几十条与分诊无关的构件（sdklib 的传递依赖等），
    反向判据只管**登记面内**的坐标，否则这条门禁会把整个工具链都要求钉地板。"""
    resolutions = dict(g.floor_resolutions())
    resolutions["com.android.tools:lintonics-workaround"] = {"9.9"}
    problems = g.floor_problems(g.floor_versions(), registered, resolutions)
    assert problems == [], problems


def test_missing_registry_block_is_environment_error(tmp_path: Path,
                                                     monkeypatch: pytest.MonkeyPatch) -> None:
    real = g.DOC
    doc = tmp_path / "triage.md"
    doc.write_text("## 三、剩余告警处置\n\n判定：tolerable_risk\n", encoding="utf-8")
    monkeypatch.setattr(g, "DOC", doc)
    assert g.run() == 2, "登记块缺失＝判定面塌缩，不能读成「没有要判的坐标」"
    doc.write_text("```tooling-only-coordinates\n\n```\n", encoding="utf-8")
    assert g.run() == 2, "登记块在但一行坐标都没有，同样算塌缩"
    monkeypatch.setattr(g, "DOC", real)
    assert g.run() == 0, "还原后必须回到通过（否则上面的红可能是别的原因）"


def test_missing_floor_block_is_red(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """地板被整段删掉＝分诊结论的一半没了。判红而不是判绿：这条判据的存在意义就是「地板不能静默消失」。"""
    real = g.BUILD
    monkeypatch.setattr(g, "BUILD", tmp_path / "build.gradle.kts")
    assert g.floor_versions() == {}
    assert g.run() == 1, "没有地板时本门禁不许输出「通过」"
    monkeypatch.setattr(g, "BUILD", real)
    assert g.run() == 0


def test_missing_doc_exits_2(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    real_doc, real_globs = g.DOC, g.LOCK_GLOBS
    monkeypatch.setattr(g, "DOC", tmp_path / "nope.md")
    assert g.run() == 2
    monkeypatch.setattr(g, "DOC", real_doc)
    monkeypatch.setattr(g, "LOCK_GLOBS", ("nowhere/*/gradle.lockfile",))
    assert g.run() == 2, "锁面一把都读不到＝环境错误，不是「没有暴露」"
    monkeypatch.setattr(g, "LOCK_GLOBS", real_globs)


def test_triage_doc_still_lists_every_registered_coordinate(registered) -> None:
    """文档正文与登记块也要一致：每条坐标的构件名都必须能在文档里找到证据出处。"""
    text = g.DOC.read_text(encoding="utf-8")
    for coordinate in registered:
        artifact = coordinate.split(":")[1]
        assert artifact in text, f"{artifact} 在分诊文档里找不到——文档与登记块已经各说各话"


def test_gate_is_on_the_pr_face() -> None:
    face = (ROOT / ".github" / "workflows" / "contracts.yml").read_text(encoding="utf-8")
    assert "verify_gradle_alert_scope_boundary.py" in face, "本门禁没接进 PR 常跑面"
    registry = (ROOT / "contracts" / "ci" / "gate-execution-face.yaml").read_text(encoding="utf-8")
    assert "verify_gradle_alert_scope_boundary.py" not in registry, "已可达的门禁不得留在登记表里"

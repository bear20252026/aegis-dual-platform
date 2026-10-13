"""Gradle 校验和文档的**平台覆盖**判据（第九轮 R9-B51 / 台账 Q61 = R9-AD-15）。

被钉住的失效形状只有一句话：**校验和文档只能记录本次落盘的字节，而平台相关的构件
在不同 runner 上落的是不同文件**。R9-B50 的实测现场是 `com.android.tools.build:aapt2`——
本机（windows）那一轮只产出 `-windows.jar`，`-linux` 零命中，而 CI 的 android-quality
与依赖图作业跑在 ubuntu 上。那一半字节当时是靠**人工在 ubuntu 上再跑一次生成面**补上的
（`dependency-relock.yml` 的 gradle 面），而「再人工跑一次」正是会漏的那种步骤：
下一次 bump 谁在哪台机器上重算，文档就只有哪个平台，且**当时没有任何判据会变红**。

这里的判据从 workflow 的 `runs-on` 现取需求平台（不手抄 runner 名单），要求每个平台相关
坐标覆盖全部需求平台。配套用例分三类：注入必红（缺 linux / 只有一个版本 / 多出 macos runner）、
正面控制（真树必须认得出 aapt2，否则「通过」只是解析口径坏了），以及豁免表自身的不变量
（无理由的豁免、指向已消失坐标的豁免都要红——见 `exemption_problems`）。
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import verify_gradle_platform_coverage as g

AAPT2_LINUX = '<artifact name="aapt2-9.4.1-15978811-linux.jar">'
NEEDERS = ("linux", "windows")


def real_metadata() -> str:
    return g.METADATA.read_text(encoding="utf-8")


def drop_artifact(text: str, name: str) -> str:
    """删掉某个 artifact 的整块（含它的 sha256）——注入「这个平台的字节从没落过盘」。"""
    dropped = re.sub(rf"\s*<artifact name=\"{re.escape(name)}\">.*?</artifact>", "", text, count=1, flags=re.S)
    assert dropped != text, f"注入没落到文本上（{name}）——用例判的是空气"
    return dropped


def test_runner_platforms_are_read_from_the_workflows() -> None:
    """需求集合来自 workflow，而不是代码里抄的名单。"""
    found = g.runner_platforms(g.load_workflow_texts())
    assert found == set(NEEDERS), f"从 runs-on 现取到的平台集合实为 {sorted(found)}——与本批台账不符就改这里"


@pytest.mark.parametrize("runner_text,expected", [
    ("    runs-on: ubuntu-latest\n", {"linux"}),
    ("    runs-on: windows-2025\n", {"windows"}),
    ("    runs-on: macos-14\n", {"macos"}),
    ("    runs-on: ['ubuntu-24.04']\n", {"linux"}),
    ("    runs-on: self-hosted\n", set()),
    ("    # runs-on: windows-2025 这是注记\n    runs-on: ubuntu-latest\n", {"linux"}),
])
def test_runs_on_parsing_shapes(runner_text: str, expected: set[str]) -> None:
    assert g.runner_platforms({"w.yml": runner_text}) == expected


def test_real_tree_passes_and_is_not_vacuous() -> None:
    """正面控制：真树必须绿，**而且**必须真的认得出平台相关坐标——零命中是塌缩不是通过。"""
    families = g.platform_families_by_component(real_metadata())
    assert g.run() == 0
    assert families, "文档里一个平台后缀构件都没认出来——解析口径坏了，上一条的「通过」就是假绿"
    assert ("com.android.tools.build", "aapt2", "9.4.1-15978811") in families, f"现读到的平台坐标是 {sorted(families)}"


def test_dropping_the_linux_artifact_is_red() -> None:
    """本机那一轮的现场：只落了 windows 形态。"""
    families = g.platform_families_by_component(drop_artifact(real_metadata(), "aapt2-9.4.1-15978811-linux.jar"))
    problems = g.violations(set(NEEDERS), families)
    assert len(problems) == 1, f"缺 linux 必须判红一条，实得 {problems}"
    assert "['linux']" in problems[0] and "生成面" in problems[0], problems[0]


def test_dropping_the_windows_artifact_is_red() -> None:
    families = g.platform_families_by_component(drop_artifact(real_metadata(), "aapt2-9.4.1-15978811-windows.jar"))
    problems = g.violations(set(NEEDERS), families)
    assert len(problems) == 1 and "['windows']" in problems[0], problems


def test_single_version_missing_a_platform_is_red() -> None:
    """旧写法（同坐标版本间取并集再比）在这里会**恒绿**：只有一个版本时并集就是它自己。

    这正是下一次 bump 的真实形状——新版本只在一台机器上重算过。所以判据必须是
    「需求平台 = workflow 现取的集合」，不是「版本之间的相对完整」。
    """
    families = {("com.example", "tool", "2.0.0"): {"linux"}}
    problems = g.violations(set(NEEDERS), families)
    assert len(problems) == 1 and "['windows']" in problems[0], problems


def test_a_new_macos_runner_widens_the_requirement_without_editing_the_gate() -> None:
    """需求集合来自 workflow ⇒ 加 macos runner 不需要改判据代码，判据自己会开始要求 macos。"""
    families = g.platform_families_by_component(real_metadata())
    problems = g.violations({"linux", "windows", "macos"}, families)
    assert len(problems) == 1 and "macos" in problems[0], problems


@pytest.mark.parametrize("artifact,expected", [
    ("aapt2-9.4.1-15978811-linux.jar", "linux"),
    ("aapt2-9.4.1-15978811-windows.jar", "windows"),
    # 平台段之后还有版本号/架构段的形态（protoc / kotlin-native 的真实命名）
    ("kotlin-native-prebuilt-macos-aarch64-2.2.10.zip", "macos"),
    ("protoc-3.25.3-osx-x86_64.exe", "macos"),
    ("some-tool-1.0-linux-x86_64.tar.gz", "linux"),
    ("library-1.0.jar", ""),
    # 扩展名不认识就不进判定：AGP 侧目前没有这类形态，先不外推（外推的代价是假红）
    ("thing-1.0-linux.deb", ""),
])
def test_artifact_platform_recognition(artifact: str, expected: str) -> None:
    assert g.artifact_platform(artifact) == expected, f"{artifact} → {g.artifact_platform(artifact)!r}"


def test_collapse_and_missing_file_are_environment_errors(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """判定面塌缩 / 文档缺失 ⇒ 退出 2，绝不判「通过」。"""
    monkeypatch.setattr(g, "WORKFLOW_DIR", tmp_path)
    (tmp_path / "w.yml").write_text("jobs:\n  j:\n    runs-on: ubuntu-latest\n", encoding="utf-8")

    missing = tmp_path / "nope.xml"
    monkeypatch.setattr(g, "METADATA", missing)
    assert g.run() == 2

    no_platform = tmp_path / "flat.xml"
    no_platform.write_text(
        '<verification-metadata xmlns="https://schema.gradle.org/dependency-verification">'
        "<components></components></verification-metadata>",
        encoding="utf-8",
    )
    monkeypatch.setattr(g, "METADATA", no_platform)
    assert g.run() == 2

    broken = tmp_path / "broken.xml"
    broken.write_text("<verification-metadata", encoding="utf-8")
    monkeypatch.setattr(g, "METADATA", broken)
    assert g.run() == 2


def test_exemption_table_judges_itself(monkeypatch: pytest.MonkeyPatch) -> None:
    """豁免表不是「写了就放松」：无理由、指向已消失坐标，两条都要红；合法豁免才真的免掉缺平台。"""
    families = {("com.example", "tool", "1.0.0"): {"linux"}}
    assert g.PLATFORM_EXCLUSIVE == {}, "豁免表当前应为空——本批没有单平台坐标；要加就走「带理由 + 仍在文档里」"
    monkeypatch.setattr(g, "PLATFORM_EXCLUSIVE", {"com.example:tool": ""})
    problems = g.exemption_problems(families)
    assert any("没有理由" in p for p in problems), problems
    monkeypatch.setattr(g, "PLATFORM_EXCLUSIVE", {"com.example:gone": "只发 linux"})
    assert any("已经找不到" in p or "没有任何平台后缀构件" in p for p in g.exemption_problems(families))
    monkeypatch.setattr(g, "PLATFORM_EXCLUSIVE", {"com.example:tool": "上游只发 linux 包"})
    assert g.exemption_problems(families) == []
    assert g.violations({"linux", "windows"}, families) == [], "合法豁免后不该再要求 windows"


def test_docs_state_the_platform_union_requirement() -> None:
    """判据之外，这句话也得有据可查：SECURITY.md 必须写明「字节面跟平台走」。"""
    security = (ROOT / "SECURITY.md").read_text(encoding="utf-8")
    for needle in ("aapt2", "并集", "Q61"):
        assert needle in security, f"SECURITY.md 缺「{needle}」——平台并集这件事的对外口径没了"

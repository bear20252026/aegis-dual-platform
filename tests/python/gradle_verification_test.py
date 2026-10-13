"""Gradle 依赖校验（dependency verification）的**配置面与对外口径**判据（R9-B50 / 台账 Q55）。

本文件只管「这一刀到底有没有落下」：档位落在属性面还是命令行、有没有第二条悄悄放宽的路、
以及对外文档跟不跟得上实树。**重算面**（校验和的那两条 gradle 命令、两条平台的腿、写回守卫）
判在 `gradle_relock_surface_test.py`，**文档本体**（`verification-metadata.xml` 的形状与摘要）
判在 `gradle_verification_document_test.py`。三份各判各的，是因为它们会被分别做坏：
开关能被命令行绕过，生成面能少一条腿或抄两份命令，文档能被换成一个不像它的文件。

为什么不是行为用例：真被校验的是 Maven 构件字节，端到端证伪要一个可控的仓库镜像（基建批）。
这里的证伪口径是「注入必红」，两侧都有实测记录（`android/settings.gradle.kts` 决策记录 ③）：
改一个 sha256 字符 ⇒ 不带参数的 `:broker:testDebugUnitTest` 45s 内 BUILD FAILED 并点名该构件；
删掉整个组件块 ⇒ 重锁那条命令 BUILD SUCCESSFUL 并把条目补了回来。
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

# 整行注释剔法的唯一出处（与 relock_sop_test 同口径）：判 workflow 的 shell 正文时不能做
# C 系块注释匹配——glob 里的 /* 与 */ 会把中间的真语句删掉（见该函数自己的说明）。
from text_anchors import drop_line_comments

ANDROID = ROOT / "android"
PROPERTIES = ANDROID / "gradle.properties"
WORKFLOW_DIR = ROOT / ".github" / "workflows"

VERIFICATION_KEY = "org.gradle.dependency.verification"
ALLOWED_VALUES = frozenset({"strict", "lenient", "off"})
# 两面口径的任务名：版本按**图**、字节按**文件**。词表放这里是因为「两面不同」这句话的
# 单源就在 settings.gradle.kts 的决策记录里，本文件末尾那条判据正是判它的。
FILES_TASK = "resolveAllConfigurationFiles"
RESOLVE_GRAPH_TASK = "resolveAllConfigurations"


def property_assignments(text: str) -> list[tuple[str, str]]:
    """gradle.properties 的键值对（先剔整行注释——注记里逐字写着被禁的取值）。"""
    pairs: list[tuple[str, str]] = []
    for line in drop_line_comments(text).splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("!"):
            continue
        key, sep, value = stripped.partition("=")
        if sep:
            pairs.append((key.strip(), value.strip()))
    return pairs


def verification_directive(pairs: list[tuple[str, str]]) -> str:
    """唯一生效的校验档位——缺失、重复、取值不认识、或不是 strict，全部判红。"""
    hits = [value for key, value in pairs if key == VERIFICATION_KEY]
    if not hits:
        raise AssertionError(f"{VERIFICATION_KEY} 没有赋值——校验退回「自带参数才校验」")
    if len(set(hits)) > 1:
        raise AssertionError(f"{VERIFICATION_KEY} 有互斥的多取值：{hits}")
    if hits[0] not in ALLOWED_VALUES:
        raise AssertionError(f"{VERIFICATION_KEY}={hits[0]} 不是 gradle 认的档位")
    if hits[0] != "strict":
        raise AssertionError(f"{VERIFICATION_KEY}={hits[0]}：lenient 只警告、off 不校验，都让「字节已验」这句对外话失效")
    return hits[0]


def gradle_command_lines() -> list[str]:
    """全部 workflow 里的 gradlew 命令行（反斜线续行先并成一条；剔整行注释——注记里抄着历史命令行）。"""
    commands: list[str] = []
    for workflow in sorted(WORKFLOW_DIR.glob("*.yml")):
        doc = yaml.safe_load(workflow.read_text(encoding="utf-8"))
        for job in (doc.get("jobs") or {}).values():
            for step in job.get("steps", []) or []:
                run = step.get("run")
                if not isinstance(run, str):
                    continue
                pending = ""
                for raw in drop_line_comments(run).splitlines():
                    line = (pending + " " + raw).strip() if pending else raw.strip()
                    if line.endswith("\\"):
                        pending = line[:-1]
                        continue
                    pending = ""
                    if "gradlew" in line:
                        commands.append(line)
    return commands


def test_verification_is_strict_at_the_properties_face() -> None:
    assert verification_directive(property_assignments(PROPERTIES.read_text(encoding="utf-8"))) == "strict"


@pytest.mark.parametrize("weakening", ["off", "lenient", "removed"])
def test_an_injected_relaxation_of_the_property_is_red(weakening: str) -> None:
    text = PROPERTIES.read_text(encoding="utf-8")
    if weakening == "removed":
        text = "\n".join(line for line in text.splitlines() if not line.startswith(VERIFICATION_KEY))
    else:
        text = text.replace(f"{VERIFICATION_KEY}=strict", f"{VERIFICATION_KEY}={weakening}")
    assert text != PROPERTIES.read_text(encoding="utf-8"), "注入没落到文本上——用例判的是空气"
    with pytest.raises(AssertionError):
        verification_directive(property_assignments(text))


def test_a_commented_assignment_is_not_counted_and_a_duplicate_is_red() -> None:
    """判据是「恰好一个取值」，而 gradle.properties 的注记按本仓传统会把被禁形态逐字写一遍
    （`off/lenient`）——整行 `#` 不剔就多出假取值，反向锚被自己的注记打红（R9-B39 同课）。
    """
    assert property_assignments(f"# {VERIFICATION_KEY}=off\n{VERIFICATION_KEY}=strict\n") == [(VERIFICATION_KEY, "strict")]
    with pytest.raises(AssertionError):
        verification_directive(property_assignments(f"{VERIFICATION_KEY}=strict\n{VERIFICATION_KEY}=off\n"))


def test_no_gradle_invocation_relaxes_verification_by_flag() -> None:
    """属性面生效之后，命令行再单独放宽就是「谁都能悄悄关掉」的第二条路。

    另一种做坏的形态是本批启用前实测过的：只在命令行加 `--dependency-verification=strict`——
    那个口径下任何一条**不带参数**的 gradlew 调用都不校验，而 CI 与本地大量调用正是这样。
    """
    offenders = [line for line in gradle_command_lines() if re.search(r"--dependency-verification\s*=\s*(lenient|off)", line)]
    assert not offenders, f"workflow 里出现了放宽校验的 gradlew 调用：{offenders}"


def test_security_md_no_longer_declares_verification_absent() -> None:
    """启用前写的是「本仓未做」；启用后留着那句话就是把对外覆盖面写小了。

    这里判 prose 是故意的：被观察对象就是那份文档本身，不是「注释污染了源码锚」。
    """
    security = (ROOT / "SECURITY.md").read_text(encoding="utf-8")
    assert "verification-metadata.xml" in security, "SECURITY.md 没提校验和文档——还是启用前的口径"
    for stale in ("本仓未做", "本批不做", "不含校验和"):
        assert stale not in security, f"SECURITY.md 里还留着启用前的说法：{stale}"


def test_settings_decision_record_states_the_two_faces_differently() -> None:
    """覆盖面口径的单源在 `android/settings.gradle.kts`：版本按集合、校验和按文件面。

    这条不是给注释挑错字：两面口径不同正是「文件面允许抄清单」的全部理由。注记被删掉之后，
    下一个人会照 ② 的集合口径去「顺手统一」两面，结果是校验和静默漏项。
    """
    record = (ANDROID / "settings.gradle.kts").read_text(encoding="utf-8")
    for needle in (
        "verification-metadata.xml",
        RESOLVE_GRAPH_TASK,
        FILES_TASK,
        "--refresh-dependencies",
        "detached 配置",
        "补录",
        "verify-signatures",
    ):
        assert needle in record, f"settings.gradle.kts 的决策记录缺「{needle}」——单源没了，口径就会各写一份"
    assert "那一刀，本仓未做" not in record, "决策记录 ③ 还写着未做——与实树冲突"

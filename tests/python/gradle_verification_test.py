"""Gradle 依赖校验（dependency verification）的**配置面**判据（第九轮 R9-B50 / 台账 Q55）。

文档本体（`android/gradle/verification-metadata.xml` 的形状与摘要）判在
`gradle_verification_document_test.py`；这里只管三件会被单独做坏的事：

1. **开关真的在属性面**。本批实测过另一种形态：只在命令行加 `--dependency-verification=strict`
   ——那个口径下任何一条**不带参数**的 gradlew 调用都不校验，而 CI 与本地大量调用正是这样。
   属性把判据落到每一次解析，命令行参数于是只剩「重锁那一次的放宽」。
2. **重算面真的能重算**。校验和的证据面**按文件**下载（图解析只取 .pom/.module，不下
   .jar/.aar），所以它不能像版本锁那样靠 `resolveAllConfigurations` 的集合定义，只能列任务
   清单。清单会漂，于是这里从 workflow 原文**现读** CI 任务面来对账，而不是再手抄一份。
   它与 R9-B32 的失效方向相反：漏条目的表现是下一个用到该构件的作业当场红，不是静默放松。
3. **文档口径跟得上实树**。启用前 SECURITY.md 写的是「本仓未做」；启用后还留着那句话，
   就是把对外声明的覆盖面写**小**了——那是 R9-DOC 那批失实的镜像面。

为什么不是行为用例：真被校验的是 Maven 构件字节，端到端证伪需要一个可控的仓库镜像（基建批）。
这里的证伪口径是「注入必红」，两侧都有实测记录（`android/settings.gradle.kts` 决策记录 ③）：
把某条 sha256 末位改一个字符后，不带任何参数的 `:broker:testDebugUnitTest` 45s 内 BUILD FAILED
并点名该构件；删掉整个组件块后跑重锁那条命令 BUILD SUCCESSFUL 并把条目补了回来。
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
RELOCK = WORKFLOW_DIR / "dependency-relock.yml"

VERIFICATION_KEY = "org.gradle.dependency.verification"
ALLOWED_VALUES = frozenset({"strict", "lenient", "off"})
# 不落**构件文件**的调用：图解析的 .pom/.module 由重锁的图面那条覆盖，纯锁对账不下任何东西。
# 加一条就要在台账里写清它为什么不落文件——这份豁免就是清单与集合之间的那道缝。
NON_ARTIFACT_FILE_FACE = frozenset({"verifyDependencyLockCoverage", ":app:dependencies", ":app:dependencyInsight"})
# shell 里的非任务词。名单是**保守的**：漏一个的后果是把工具名当任务要求进文件面，
# 那条红灯会带着完整清单出现，不是静默放松。
NON_TASK_WORDS = frozenset(
    "awk bash bat cat cd cut done echo else export false fi for gradlew grep head if python python3 "
    "sed set sh sort tail tee then timeout true uniq".split()
)
# 带值的 gradle 选项：不跳过其值，`--write-verification-metadata sha256` 的 `sha256`
# 与 `--configuration debugRuntimeClasspath` 的配置名都会被当成任务词。
OPTION_WITH_VALUE = frozenset({"--configuration", "--dependency", "--tests", "--write-verification-metadata"})
# `(?::[\w.-]+)*` 里的 `*` 是必须的：写成 `?` 时 `:app:ktlintCheck` 整体不匹配（少一层模块前缀
# 的形态），于是所有带模块前缀的任务词**静默**消失，判据退化成只看得见 5 个裸任务——实测撞过。
TASK_TOKEN = re.compile(r"(?::[\w.-]+)*[A-Za-z]\w*")


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


def task_tokens(lines: list[str]) -> set[str]:
    """命令行里的 gradle **任务**词（选项、选项值、shell 关键字、路径形态都不算）。"""
    found: set[str] = set()
    for line in lines:
        previous = ""
        for token in line.split():
            skip = previous in OPTION_WITH_VALUE or token.startswith("-") or token in NON_TASK_WORDS
            if not skip and TASK_TOKEN.fullmatch(token):
                found.add(token)
            previous = token
    return found


def relock_steps() -> list[dict]:
    return yaml.safe_load(RELOCK.read_text(encoding="utf-8"))["jobs"]["gradle-relock"]["steps"]


def step_body(steps: list[dict], marker: str) -> str:
    """按步骤名取 run 正文（改名或删掉都必须判红，不是静默跳过）。"""
    hits = [str(s.get("run", "")) for s in steps if marker in str(s.get("name", ""))]
    if len(hits) != 1:
        raise AssertionError(f"名为「{marker}」的步骤必须恰好一个，实得 {len(hits)}")
    return drop_line_comments(hits[0])


def checksum_surface_lines(run: str) -> list[str]:
    return [line.strip() for line in run.splitlines() if "--write-verification-metadata" in line]


def file_face_line(run: str) -> str:
    """文件面那一条：带 `--write-verification-metadata` 而不带 `--write-locks`（后者归图面）。"""
    lines = [line for line in checksum_surface_lines(run) if "--write-locks" not in line]
    if len(lines) != 1:
        raise AssertionError(f"校验和的文件面命令必须恰好一条，实得 {len(lines)} 条：{lines}")
    return lines[0]


def case_patterns(run: str) -> list[str]:
    """写回守卫 `case "$changed" in … esac` 里逐条列出的路径形态（顺序即语义，`*` 是拒绝支）。"""
    block = re.search(r'case "\$changed" in(.*?)esac', run, re.S)
    if not block:
        raise AssertionError('写回步骤里没有 `case "$changed" in … esac`——守卫形态变了，这里必须同步改')
    return [m.group(1) for m in re.finditer(r"^\s*(\S+)\)\s", block.group(1), re.M)]


def accepted_by_guard(patterns: list[str], path: str) -> bool:
    """按 shell case 的 glob 语义判断路径会不会被放行（默认支 `*` 是拒绝，不是放行）。"""
    for pattern in patterns:
        if pattern == "*":
            return False
        if re.fullmatch(pattern.replace(".", r"\.").replace("*", ".*"), path):
            return True
    return False


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
    """属性面生效之后，命令行再单独放宽就是「谁都能悄悄关掉」的第二条路。"""
    offenders = [line for line in gradle_command_lines() if re.search(r"--dependency-verification\s*=\s*(lenient|off)", line)]
    assert not offenders, f"workflow 里出现了放宽校验的 gradlew 调用：{offenders}"


def test_relock_regenerates_checksums_on_both_faces() -> None:
    run = step_body(relock_steps(), "Gradle 重锁")
    surface = checksum_surface_lines(run)
    if len(surface) != 2:
        raise AssertionError(f"校验和的重算命令必须恰好两条（图面 + 文件面），实得 {len(surface)}")
    graph = [line for line in surface if "--write-locks" in line]
    if len(graph) != 1 or "resolveAllConfigurations" not in graph[0]:
        raise AssertionError(f"图面必须与 --write-locks 同条且走集合解析，实得 {graph}")


def test_file_face_checksum_surface_covers_every_ci_gradle_task() -> None:
    run = step_body(relock_steps(), "Gradle 重锁")
    surface = task_tokens(checksum_surface_lines(run))
    ci = task_tokens(gradle_command_lines())
    if len(ci) < 20:
        raise AssertionError(f"从 workflow 只提出 {len(ci)} 个任务词——提取口径坏了，这条判据就是假绿：{sorted(ci)}")
    missing = sorted(ci - surface - NON_ARTIFACT_FILE_FACE)
    assert not missing, (
        f"CI 跑过这些任务而校验和的文件面没覆盖（{missing}）——它们解析到的构件字节可能根本不在文档里，"
        "表现是下一个用到的作业当场红。补进 dependency-relock.yml 的文件面，"
        "或加进 NON_ARTIFACT_FILE_FACE 并写清为什么不落文件"
    )
    # dependency-submission 的隐式默认任务在 workflow 文本里看不见，只能显式钉住
    assert "assemble" in surface, "文件面没有 bare `assemble`——那是 gradle-dependency-graph.yml 的隐式任务"


def test_dropping_the_file_face_line_turns_the_gate_red() -> None:
    """内存态注入：删掉文件面那条，判据必须判红而不是「少一条也算过」。"""
    run = step_body(relock_steps(), "Gradle 重锁")
    without = "\n".join(line for line in run.splitlines() if "--write-verification-metadata" not in line or "--write-locks" in line)
    with pytest.raises(AssertionError):
        file_face_line(without)
    assert len(checksum_surface_lines(without)) == 1, "注入后剩下的应当只有图面那一条"


def test_writeback_guard_accepts_metadata_and_still_rejects_strays() -> None:
    """写回守卫必须放行校验和文档，否则重锁作业红在自己的守卫上；同时继续拒绝杂项。"""
    patterns = case_patterns(step_body(relock_steps(), "写回分支"))
    assert accepted_by_guard(patterns, "android/gradle.lockfile"), "四把版本锁被守卫拒了"
    assert accepted_by_guard(patterns, "android/gradle/verification-metadata.xml"), (
        "校验和文档不在写回合法面里——R9-B50 之后同一次重锁必然同时产出它，守卫会把合法重锁判成「写回面错了」"
    )
    for stray in ("android/gradle/libs.versions.toml", "android/app/build.gradle.kts", "docs/README.md"):
        assert not accepted_by_guard(patterns, stray), f"守卫放行了非依赖证据文件：{stray}"
    without = [p for p in patterns if "verification-metadata" not in p]
    assert not accepted_by_guard(without, "android/gradle/verification-metadata.xml"), "注入形态本身没被拒绝——判据在判空气"


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
    for needle in ("verification-metadata.xml", "resolveAllConfigurations", "补录", "verify-signatures"):
        assert needle in record, f"settings.gradle.kts 的决策记录缺「{needle}」——单源没了，口径就会各写一份"
    assert re.search(r"按\*{0,2}文件\*{0,2}重算", record), "决策记录缺「校验和按文件面重算」——两面不同的那句没了"
    assert "那一刀，本仓未做" not in record, "决策记录 ③ 还写着未做——与实树冲突"

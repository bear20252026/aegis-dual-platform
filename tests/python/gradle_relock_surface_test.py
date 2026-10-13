"""Gradle 依赖校验的**重算面**判据（R9-B50 / Q55 起，R9-B53 / Q61 补第二条腿）。

本文件只管一件事：**「重算校验和」这句命令话能不能兑现**。开关那一面（`gradle.properties`
的 strict、命令行不得放宽、对外文档口径）判在 `gradle_verification_test.py`；
文档本体判在 `gradle_verification_document_test.py`。分成三份不是因为题材多，而是
这三件事各自会被单独做坏：

1. **重算的是字节而不是图**：产物文件面走 `resolveAllConfigurationFiles`（图解析只下
   `.pom`/`.module`，一个 `.jar`/`.aar` 都不落盘）；工具类路径是任务执行时现建的 detached
   配置，不在 `project.configurations` 里，那一小份任务清单不能省（逐 token 判）。
2. **每条生成面都强制重取字节**：`--refresh-dependencies`。PR #189 实测本地三条命令全绿、
   CI 两个平台的干净 runner 同红 6 个构件（配置名 `classpath`）——长命的 `~/.gradle`
   元数据缓存能让一批描述文件永不落盘，而「没有条目」在生成模式下也不报错。
3. **平台的腿都要跑到，且只跑一份命令**（R9-B53）：字节面跟平台走（`aapt2` 在 windows 落
   `-windows.jar`、ubuntu 落 `-linux.jar`，两个不同 sha256），所以生成面是两条腿**串行**；
   而命令一旦抄成两份，两条腿就会漂——漂移的表现是某个平台的构件字节静默缺失。

证伪口径是「注入必红」（真端到端要一个可控 Maven 镜像，属基建批）：两侧都有实测记录，
见 `android/settings.gradle.kts` 决策记录 ③ 与台账 §3.50、§3.53。
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from gradle_verification_test import (
    FILES_TASK,
    RESOLVE_GRAPH_TASK,
    gradle_command_lines,
)
from text_anchors import drop_line_comments

ANDROID = ROOT / "android"
ROOT_SCRIPT = ANDROID / "build.gradle.kts"
RELOCK = ROOT / ".github" / "workflows" / "dependency-relock.yml"
FILE_FACE_ACTION = ROOT / ".github" / "actions" / "gradle-checksum-file-face" / "action.yml"
TOOLCHAIN_ACTION = "gradle-android-toolchain"
FILE_FACE_ACTION_NAME = "gradle-checksum-file-face"
UBUNTU_LEG = "gradle-relock"
WINDOWS_LEG = "gradle-checksum-windows"

# 不落**构件文件**的调用：图解析（.pom/.module）由重锁的图面那条覆盖，纯锁对账不下任何东西。
NON_ARTIFACT_FILE_FACE = frozenset({"verifyDependencyLockCoverage", ":app:dependencies", ":app:dependencyInsight"})
# 由**集合口径**覆盖的构建任务：它们吃的 classpath 文件就是本项目那些 canBeResolved 配置，
# `resolveAllConfigurationFiles` 已经逐个解析过。这份豁免是清单与集合之间那道缝的另一半——
# 加一条要在台账里写清「它的文件确实来自项目配置」，否则它就成了第二个「靠漏抄变绿」的洞。
SET_COVERED_TASKS = frozenset({
    "assemble", ":app:assembleDebug", ":app:assembleRelease", ":app:assembleDebugAndroidTest",
    ":contracts:assembleDebug", ":broker:compileDebugKotlin", ":webview-adapter:compileDebugKotlin",
})
# shell 里的非任务词。名单是**保守的**：漏一个的后果是把工具名当任务要求进文件面，
# 那条红灯会带着完整清单出现，不是静默放松。
NON_TASK_WORDS = frozenset(
    "awk bash bat cat cd cut done echo else export false fi for gradlew grep head if python python3 "
    "sed set sh sort tail tee then timeout true uniq".split())
# 带值的 gradle 选项：其值必须跳过，否则 `sha256`、`debugRuntimeClasspath` 会被当成任务词。
OPTION_WITH_VALUE = frozenset({"--configuration", "--dependency", "--tests", "--write-verification-metadata"})
# `(?::[\w.-]+)*` 里的 `*` 是必须的：写成 `?` 时 `:app:ktlintCheck` 整体不匹配（少一层模块前缀
# 的形态），于是所有带模块前缀的任务词**静默**消失，判据退化成只看得见 5 个裸任务——实测撞过。
TASK_TOKEN = re.compile(r"(?::[\w.-]+)*[A-Za-z]\w*")


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


def relock_jobs() -> dict:
    return yaml.safe_load(RELOCK.read_text(encoding="utf-8"))["jobs"]


def job_steps(job: str) -> list[dict]:
    if job not in relock_jobs():
        raise AssertionError(f"dependency-relock 缺 {job} job——两条平台的腿少了一条就是覆盖面缺口")
    return relock_jobs()[job].get("steps", []) or []


def step_body(steps: list[dict], marker: str) -> str:
    """按步骤名取 run 正文（改名或删掉都必须判红，不是静默跳过）。"""
    hits = [str(s.get("run", "")) for s in steps if marker in str(s.get("name", ""))]
    if len(hits) != 1:
        raise AssertionError(f"名为「{marker}」的步骤必须恰好一个，实得 {len(hits)}")
    return drop_line_comments(hits[0])


def uses_markers(job: str, action: str) -> int:
    """某 job 里 `uses: ./.github/actions/<action>` 的次数（composite 消费的判据口径）。"""
    return sum(1 for s in job_steps(job) if str(s.get("uses", "")).endswith(action))


def file_face_action_text() -> str:
    if not FILE_FACE_ACTION.is_file():
        raise AssertionError(f"文件面 composite action 不存在：{FILE_FACE_ACTION}")
    doc = yaml.safe_load(FILE_FACE_ACTION.read_text(encoding="utf-8"))
    bodies = [str(s["run"]) for s in doc["runs"]["steps"] if isinstance(s.get("run"), str)]
    return drop_line_comments(chr(10).join(bodies))


def generation_corpus() -> str:
    """重算命令的全部出处：两条腿的 workflow 正文 + 文件面 composite action。

    拼成一个语料再数，是因为「同一份命令被抄到第二条腿上」正是本批抽 composite 要防的事：
    分开数会各数各的，合起来数才数得出漂移。
    """
    legs = [
        chr(10).join(str(s.get("run", "")) for s in job_steps(job) if isinstance(s.get("run"), str))
        for job in (UBUNTU_LEG, WINDOWS_LEG)
    ]
    return drop_line_comments(chr(10).join(legs + [file_face_action_text()]))


def checksum_surface_lines(corpus: str | None = None) -> list[str]:
    text = generation_corpus() if corpus is None else corpus
    return [line.strip() for line in text.splitlines() if "--write-verification-metadata" in line]


def file_face_line(corpus: str | None = None) -> str:
    """文件面那一条：带 `--write-verification-metadata` 而不带 `--write-locks`（后者归图面）。"""
    lines = [line for line in checksum_surface_lines(corpus) if "--write-locks" not in line]
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


def test_checksum_generation_faces_force_fresh_bytes_and_the_file_set() -> None:
    """两条生成面都必须带 `--refresh-dependencies`，文件面必须走集合口径的那个新任务。

    `--refresh-dependencies` 不是保守起见：PR #189 实测本地三条命令全绿而 CI 两个平台的
    runner 同红 6 个构件（guava-parent、junit-bom×3、kotlin-gradle-plugins-bom×2，配置名
    `classpath`）——本地那份元数据缓存让这些描述文件**永不落盘**，于是文档里根本没有条目，
    而「没有条目」在生成模式下也不报错。不强制重取字节，「重算校验和」这句就是假账。
    """
    lines = checksum_surface_lines()
    if len(lines) != 2:
        raise AssertionError(f"校验和的重算命令必须恰好两条（图面 + 文件面），实得 {len(lines)}")
    for name, line in zip(("图面", "文件面"), lines, strict=True):
        assert "--refresh-dependencies" in line, f"{name}没带 --refresh-dependencies——缓存里没落盘的那批字节不会进文档"
    graph, file_face = lines
    if "--write-locks" not in graph or RESOLVE_GRAPH_TASK not in graph:
        raise AssertionError(f"图面必须与 --write-locks 同条且走集合解析，实得 {graph}")
    for needle in (FILES_TASK, "buildEnvironment"):
        assert needle in file_face, f"文件面缺 {needle}——前者是产物文件的集合口径，后者是脚本类路径"
    script = ROOT_SCRIPT.read_text(encoding="utf-8")
    assert f'tasks.register("{FILES_TASK}")' in script, (
        f"root 脚本里没有 {FILES_TASK}——重锁面敲一个不存在的任务，只会在那次 dispatch 里红"
    )


def test_tool_task_surface_covers_every_ci_gradle_task() -> None:
    surface = task_tokens(checksum_surface_lines())
    ci = task_tokens(gradle_command_lines())
    if len(ci) < 20:
        raise AssertionError(f"从 workflow 只提出 {len(ci)} 个任务词——提取口径坏了，这条判据就是假绿：{sorted(ci)}")
    missing = sorted(ci - surface - NON_ARTIFACT_FILE_FACE - SET_COVERED_TASKS)
    assert not missing, (
        f"CI 跑过这些任务而校验和的重算面没覆盖（{missing}）——工具类路径（ktlint/detekt/lint/测试）"
        "是任务执行时现建的 detached 配置，不在 project.configurations 里，只有跑它们才落盘；"
        "补进文件面的 composite action，或说明它为什么属于 NON_ARTIFACT_FILE_FACE / SET_COVERED_TASKS"
    )
    stale = sorted(task_tokens([file_face_line()]) & SET_COVERED_TASKS)
    assert not stale, (
        f"构建任务清单又回到文件面了（{stale}）——那一路的 classpath 文件归 {FILES_TASK} 的集合口径管；"
        "两处各写一份就是两份真相，且清单必然漏（R9-B32 那条课的另一半）"
    )


def test_dropping_the_file_face_line_turns_the_gate_red() -> None:
    """内存态注入：删掉文件面那条，判据必须判红而不是「少一条也算过」。"""
    without = chr(10).join(
        line for line in generation_corpus().splitlines()
        if "--write-verification-metadata" not in line or "--write-locks" in line
    )
    with pytest.raises(AssertionError):
        file_face_line(without)
    assert len(checksum_surface_lines(without)) == 1, "注入后剩下的应当只有图面那一条"


def test_file_face_command_has_exactly_one_source_and_two_consumers() -> None:
    """文件面命令只有一份（composite action），两条腿各消费一次。

    这是 R9-B53 抽 action 的全部理由：命令一抄两份，两条腿就会漂（一条带
    `--refresh-dependencies`、另一条不带；或任务清单少一项），而漂移的表现是
    「某个平台的构件字节静默缺失」——正是本批要根除的那类失效。
    """
    occurrences = sum(
        1 for line in generation_corpus().splitlines()
        if FILES_TASK in line and "--write-verification-metadata" in line
    )
    assert occurrences == 1, f"文件面命令出现在 {occurrences} 处——应当只有 composite action 那一份"
    for job in (UBUNTU_LEG, WINDOWS_LEG):
        assert uses_markers(job, FILE_FACE_ACTION_NAME) == 1, f"{job} 没有恰好一次消费文件面 action"
        assert uses_markers(job, TOOLCHAIN_ACTION) == 1, f"{job} 的装配口径没走单源 action"


def test_windows_leg_is_serialized_after_the_ubuntu_leg_and_cannot_write_locks() -> None:
    """两条腿并发推同一个文件必然互相覆盖；而 windows 腿不带 --write-locks，也不该写锁。"""
    job = relock_jobs().get(WINDOWS_LEG)
    assert job is not None, "dependency-relock 缺 windows 腿——Q61 的缺口就又回来了"
    needs = job.get("needs")
    assert needs == UBUNTU_LEG or (isinstance(needs, list) and UBUNTU_LEG in needs), (
        f"windows 腿没有 needs: {UBUNTU_LEG}（实得 {needs}）——并发写同一分支会互相覆盖"
    )
    # 锁只由 ubuntu 腿重算一次：整份重锁语料里 `--write-locks` 必须恰好一条命令。
    # （比「windows 腿正文里不含这个词」强——那里它出现在注记与报错文案里，是 prose 不是命令。）
    lock_faces = [line for line in generation_corpus().splitlines() if "--write-locks" in line and "gradlew" in line]
    assert len(lock_faces) == 1, f"重算锁的命令应当恰好一条（ubuntu 图面），实得 {len(lock_faces)}"
    writeback = step_body(job.get("steps", []), "写回分支")
    assert "gradlew" not in writeback, "windows 腿的写回步骤里出现了 gradlew 调用——这条腿只搬运字节证据，不跑生成面"
    patterns = case_patterns(writeback)
    assert accepted_by_guard(patterns, "android/gradle/verification-metadata.xml")
    assert not accepted_by_guard(patterns, "android/app/gradle.lockfile"), (
        "windows 腿的写回守卫放行了版本锁——这条腿不重算锁，出现锁 diff 就是写回面错了"
    )


def test_writeback_guard_accepts_metadata_and_still_rejects_strays() -> None:
    """写回守卫必须放行校验和文档，否则重锁作业红在自己的守卫上；同时继续拒绝杂项。"""
    patterns = case_patterns(step_body(job_steps(UBUNTU_LEG), "写回分支"))
    assert accepted_by_guard(patterns, "android/gradle.lockfile"), "四把版本锁被守卫拒了"
    assert accepted_by_guard(patterns, "android/gradle/verification-metadata.xml"), (
        "校验和文档不在写回合法面里——R9-B50 之后同一次重锁必然同时产出它，守卫会把合法重锁判成「写回面错了」"
    )
    for stray in ("android/gradle/libs.versions.toml", "android/app/build.gradle.kts", "docs/README.md"):
        assert not accepted_by_guard(patterns, stray), f"守卫放行了非依赖证据文件：{stray}"
    without = [p for p in patterns if "verification-metadata" not in p]
    assert not accepted_by_guard(without, "android/gradle/verification-metadata.xml"), "注入形态本身没被拒绝——判据在判空气"

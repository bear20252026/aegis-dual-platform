"""入库 `gradle.lockfile` 的形态与覆盖面门禁（第九轮项 10 / AEG-011 的锁文件半边）。

声明侧（root 的 `subprojects` 锁块、模块零副本、settings 与 SECURITY.md 的口径）在
`gradle_locking_test.py`；本文件只管**锁文件本身可读、可用、覆盖得全**：

- 形态：必须是 Gradle 生成的（三行头注），条目必须是 `group:name:version=配置名`，
  版本必须是精确值——`1.+` / `latest.release` / `-SNAPSHOT` 出现即「钉了个没钉的」。
- 覆盖面：CI 会解析的配置名必须真的在锁里出现，否则 STRICT 下红的是下一个用到它的作业，
  而不是这次改动。R9-B32 之后又加了一类：`:app:androidTestUtil` 这种
  **由 AGP 构建监听器解析、不属于任何任务名**的配置——照任务清单抄重锁面必然漏它。
- 口径：判代码不判注释、切片有边界、每条锚配注入式反向锚（本文件的注入全在内存里做）。
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ANDROID = ROOT / "android"
SETTINGS = ANDROID / "settings.gradle.kts"

# Gradle 自己写在锁文件头部的三行——它们缺失即「这不是机器生成的锁，是手抄的」。
LOCK_HEADER_MARKERS = (
    "# This is a Gradle generated file for dependency locking.",
    "# Manual edits can break the build and are not advised.",
    "# This file is expected to be part of source control.",
)

# 至少要有这些配置进锁：CI 的装配/测试/静态分析面都会解析它们（缺一条就是
# 「重锁时没跑到那条配置」，STRICT 下当场红——宁可在这里红，也不要红在 PR 面）。
# `:contracts` 只要求 debug 面：CI 对它只跑 `:contracts:assembleDebug`（contracts.yml），
# 且它是零外部依赖的生成物模块——没有东西可锁到 release 面，硬要求 release 条目
# 就是把判据写成永远过不了的样子。
REQUIRED_CONFIGURATIONS = {
    "app": ("debugRuntimeClasspath", "releaseRuntimeClasspath",
            "debugUnitTestRuntimeClasspath", "debugAndroidTestCompileClasspath",
            "debugLintChecksClasspath"),
    "broker": ("debugRuntimeClasspath", "releaseRuntimeClasspath",
               "debugUnitTestRuntimeClasspath"),
    "webview-adapter": ("debugRuntimeClasspath", "releaseRuntimeClasspath",
                        "debugUnitTestRuntimeClasspath"),
    "contracts": ("debugCompileClasspath", "debugRuntimeClasspath"),
}

# R9-B32（2026-10-12）：这几个配置是「照任务清单抄重锁面」必然漏掉的那一类——它们不由任何
# gradlew 任务解析，而是 AGP 的 UTP / Kotlin / lint 在**构建监听器**里解析的。实测红灯：
# `Locking strict mode: Configuration ':app:androidTestUtil' is locked but does not have
# lock state`（Gradle-Dependency-Graph 在 master 连红两次，而同期每条 PR 门禁全绿）。
LISTENER_ONLY_CONFIGURATIONS = {
    "app": ("androidTestUtil", "coreLibraryDesugaring", "kotlinCompilerClasspath", "lintPublish"),
    "broker": ("androidTestUtil", "coreLibraryDesugaring", "kotlinCompilerClasspath"),
    "webview-adapter": ("androidTestUtil", "coreLibraryDesugaring", "kotlinCompilerClasspath"),
    "contracts": ("androidTestUtil", "coreLibraryDesugaring", "kotlinCompilerClasspath"),
}

# 质量工具链的解析面（ktlint 规则集、detekt 插件都是依赖）——不锁就等于质量门禁每次可换版
QUALITY_TOOL_CONFIGURATIONS = ("ktlint", "ktlintRuleset", "detekt", "detektPlugins")

# 动态版本形态：Gradle 允许 `1.+` / `latest.release` / `+`，锁里出现即「钉了个没钉的」
_DYNAMIC_VERSION = re.compile(r"(^|[.\-])(?:\+|latest\.release|latest\.integration)$")


def module_names() -> list[str]:
    """模块清单从 settings 现取——不在测试里另抄一份名单（抄了就判不到新增模块）。

    同款定位器在 gradle_locking_test.py 里也有一份：那是 6 行的读法，
    抽公共模块会让两个用例文件互相牵连，本仓测试文件的既有形态就是各自自带定位器。"""
    text = SETTINGS.read_text(encoding="utf-8")
    return sorted(set(re.findall(r'include\(":([A-Za-z0-9_\-]+)"\)', text)))


def lock_text(name: str) -> str:
    return (ANDROID / name / "gradle.lockfile").read_text(encoding="utf-8")


def locked_configurations(text: str) -> set[str]:
    """锁里出现过状态的配置名（坐标条目的配置列表 + `empty=` 里列出的空配置）。"""
    configs: set[str] = set()
    for line in text.splitlines():
        if line.startswith("#"):
            continue
        _, sep, tail = line.partition("=")
        if sep:
            configs.update(name for name in tail.split(",") if name)
    return configs


def lockfile_problems(text: str) -> list[str]:
    """纯函数：锁文件形态判定（头注 + 每条版本都是精确版）。"""
    problems: list[str] = []
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if not lines:
        return ["锁文件为空"]
    for marker in LOCK_HEADER_MARKERS:
        if marker not in text:
            problems.append(f"缺 Gradle 生成头注行：{marker[:32]}…")
    entries = [ln for ln in lines if not ln.startswith("#")]
    if not entries:
        return problems + ["锁文件里零条目"]
    unpinned: list[str] = []
    for line in entries:
        if line.startswith("empty="):
            continue  # Gradle 对「已锁但无依赖」的配置写 empty=，不是漂移
        head, sep, configs = line.partition("=")
        if not sep or not configs:
            unpinned.append(f"形态异常：{line[:60]}")
            continue
        parts = head.split(":")
        if len(parts) != 3:
            unpinned.append(f"坐标段数不是 group:name:version：{head[:60]}")
            continue
        version = parts[2]
        if _DYNAMIC_VERSION.search(version) or "," in version:
            unpinned.append(f"版本不是精确值：{head}")
    problems += [f"条目不可解析/未钉版：{u}" for u in unpinned]
    return problems


def missing_required(name: str, required: tuple[str, ...]) -> list[str]:
    have = locked_configurations(lock_text(name))
    return [f":{name} 缺配置 {cfg}" for cfg in required if cfg not in have]


def test_every_locked_module_has_a_gradle_shaped_lockfile() -> None:
    offenders: list[str] = []
    for name in module_names():
        lock = ANDROID / name / "gradle.lockfile"
        if not lock.exists():
            offenders.append(f":{name} 无 gradle.lockfile（锁声明了但没落盘=不会有人红）")
            continue
        offenders += [f":{name} {p}" for p in lockfile_problems(lock.read_text(encoding="utf-8"))]
    assert not offenders, f"锁文件形态不合格：{offenders}"


def test_ci_resolved_configurations_are_present_in_the_locks() -> None:
    missing: list[str] = []
    for name, required in REQUIRED_CONFIGURATIONS.items():
        missing += missing_required(name, required)
    assert not missing, f"锁未覆盖 CI 会解析的配置（STRICT 下这些面会当场红）：{missing}"


def test_quality_tool_configurations_are_locked_too() -> None:
    """ktlint/detekt 的规则集是依赖——不锁的话「Android 依赖已锁版本」就漏掉整条质量门禁链。"""
    offenders: list[str] = []
    for name in module_names():
        offenders += missing_required(name, QUALITY_TOOL_CONFIGURATIONS)
    assert not offenders, f"质量工具面未进锁：{offenders}"


def test_listener_resolved_configurations_have_lock_state() -> None:
    """R9-B32 的常驻判据：监听器解析的配置（不属于任何任务名）必须有锁状态。

    重锁面一旦退回「抄 CI 任务清单」，这些条目就会消失，本用例当场判红。"""
    offenders: list[str] = []
    for name, required in LISTENER_ONLY_CONFIGURATIONS.items():
        offenders += missing_required(name, required)
    assert not offenders, (
        "这些配置没有锁状态——重锁面又退回「照任务清单解析」了：" + "、".join(offenders)
    )


def test_dropping_a_listener_entry_from_the_lock_turns_the_check_red() -> None:
    """反向锚（内存态注入，不改工作树）：抹掉 androidTestUtil 必须**只**归因到它。"""
    text = lock_text("app")
    stripped = "\n".join(
        ln.replace(",androidTestUtil", "").replace("androidTestUtil,", "")
        for ln in text.splitlines()
    )
    assert "androidTestUtil" not in stripped, "注入没生效（删不掉就证明不了判据在判它）"
    have = locked_configurations(stripped)
    offenders = [c for c in LISTENER_ONLY_CONFIGURATIONS["app"] if c not in have]
    assert offenders == ["androidTestUtil"], f"归因跑偏：{offenders}"


def test_locks_pin_exact_versions_not_ranges() -> None:
    for name in module_names():
        text = lock_text(name)
        assert "SNAPSHOT" not in text, f":{name} 锁里有 -SNAPSHOT 版本"
        entries = [ln for ln in text.splitlines() if ln and not ln.startswith("#")]
        assert len(entries) >= 5, f":{name} 锁条目只有 {len(entries)} 条，不像完整解析结果"

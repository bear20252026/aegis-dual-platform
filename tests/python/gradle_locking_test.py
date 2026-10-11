"""项 10 / AEG-011（第九轮，2026-10-11 用户定稿「全部完成」）：Android 依赖锁定的结构门禁。

启用 `dependencyLocking` 之后，「谁被锁了」与「锁得住吗」这两件事都需要机器判：

- **覆盖面**：锁块单源写在 root `android/build.gradle.kts` 的 `subprojects` 作用域里
  （声明一次即覆盖全部现有与后续子模块；逐模块各写一份的话，「新增第五个模块忘记加锁」
  是静默的 fail-open）。这里两道都判：root 必须有那份锁块且只有一份，模块脚本必须
  **没有**自己的副本；模块清单从 `settings.gradle.kts` 的 `include(...)` 现取
  （不是脚本里再抄一份名单），逐个要求「目录里有锁文件」。
- **锁的形态**：Gradle 的锁文件记的是「group:name:version=配置名」，**不含校验和**。
  所以判据只能是形态级的（精确版本、无动态区间），哈希验证是 dependency verification
  那一刀，本仓没做就不许在文档里声称做了。
- **文本锚的口径**（本仓反复踩过的三件套）：判代码不判注释（注记里逐字抄着被禁形态）、
  切片有边界、每条锚都配注入式反向锚（把锁块删掉必须判红）。
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ANDROID = ROOT / "android"
SETTINGS = ANDROID / "settings.gradle.kts"
ROOT_SCRIPT = ANDROID / "build.gradle.kts"

# root 脚本里那份锁块（注释不参与比对——注记会各自措辞，代码形态漂移才是真问题：
# 少了 lockMode 就退化成「靠缺省值」）。它写在 `subprojects` 作用域里，声明一次即覆盖
# 全部现有与后续子模块；模块脚本里**不该**再有自己的副本（两份真相必然漂移）。
# 比对按**去缩进**形态做：块在 `subprojects {}` 里必然带缩进，写死四空格就是比排版
# 而不是比内容。注入也用同一正则（容忍任意缩进），否则「删掉某行」会删不掉⇒锚恒真。
LOCKING_BLOCK = """dependencyLocking {
    lockAllConfigurations()
    lockMode = LockMode.STRICT
}"""
_BLOCK_RE = re.compile(
    r"^[ \t]*dependencyLocking \{\n"
    r"[ \t]*lockAllConfigurations\(\)\n"
    r"[ \t]*lockMode = LockMode\.STRICT\n"
    r"[ \t]*\}[ \t]*\n",
    re.MULTILINE)
_MODE_RE = re.compile(r"\n[ \t]*lockMode = LockMode\.STRICT(?=\n)")
# 比对用的去缩进形态（常量的排版和 `subprojects {}` 里的实际排版必然不同）
LOCKING_BLOCK_FLAT = "\n".join(line.strip() for line in LOCKING_BLOCK.splitlines())


def dedent_code(text: str) -> str:
    """`kotlin_code` 之后再逐行去掉行首缩进（只用于块形态比对）。"""
    return "\n".join(line.strip() for line in kotlin_code(text).splitlines())

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

# 动态版本形态：Gradle 允许 `1.+` / `latest.release` / `+`，锁里出现即「钉了个没钉的」
_DYNAMIC_VERSION = re.compile(r"(^|[.\-])(?:\+|latest\.release|latest\.integration)$")


def kotlin_code(text: str) -> str:
    """剔掉 `//` 行注释（口径见模块 docstring：注记里抄着被禁形态）。"""
    kept: list[str] = []
    for line in text.splitlines():
        if line.strip().startswith("//"):
            continue
        kept.append(line)
    return "\n".join(kept)


def module_names() -> list[str]:
    text = SETTINGS.read_text(encoding="utf-8")
    return sorted(set(re.findall(r'include\(":([A-Za-z0-9_\-]+)"\)', text)))


def locking_problems(root_text: str) -> list[str]:
    """纯函数：给定 root 构建脚本，返回「锁没到位」的问题列表（便于内存态注入）。"""
    code = kotlin_code(root_text)
    flat = dedent_code(root_text)
    problems: list[str] = []
    if "subprojects {" not in code:
        problems.append("锁块没写在 subprojects 作用域里（新增模块会静默不锁＝fail-open）")
    if LOCKING_BLOCK_FLAT not in flat:
        problems.append("缺 lockAllConfigurations() + LockMode.STRICT 的锁块")
    if code.count("dependencyLocking") > 1:
        problems.append("root 里有两份锁块——单源就是单源")
    if "lockMode" in code and "LockMode.STRICT" not in code:
        problems.append("写了 lockMode 但不是 STRICT（靠缺省值＝缺省一变即静默放松）")
    return problems


def duplicate_locking_copies() -> list[str]:
    """模块脚本里出现自己的 `dependencyLocking` 副本 ⇒ 判红（两份真相必然漂移）。"""
    offenders: list[str] = []
    for name in module_names():
        script = ANDROID / name / "build.gradle.kts"
        if not script.exists():
            offenders.append(f":{name} 的构建脚本不存在")
        elif "dependencyLocking" in kotlin_code(script.read_text(encoding="utf-8")):
            offenders.append(f":{name} 自带锁副本")
    return offenders


def lockfile_problems(lock_text: str) -> list[str]:
    """纯函数：锁文件形态判定（头注 + 每条版本都是精确版）。"""
    problems: list[str] = []
    lines = [ln for ln in lock_text.splitlines() if ln.strip()]
    if not lines:
        return ["锁文件为空"]
    for marker in LOCK_HEADER_MARKERS:
        if marker not in lock_text:
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


def locked_configurations(lock_text: str) -> set[str]:
    configs: set[str] = set()
    for line in lock_text.splitlines():
        if line.startswith("#"):
            continue
        _, sep, tail = line.partition("=")
        if sep:
            configs.update(name for name in tail.split(",") if name)
    return configs


def test_module_list_comes_from_settings_not_a_hardcoded_copy() -> None:
    names = module_names()
    assert names, "settings.gradle.kts 里一条 include 都没解析到——扫描面塌了"
    assert {"app", "broker", "webview-adapter", "contracts"} <= set(names), (
        f"四个已知模块必须在 settings 的清单里（实得 {names}）——本门禁的覆盖面定义"
    )


def test_root_declares_locking_once_and_modules_carry_no_copies() -> None:
    assert not locking_problems(ROOT_SCRIPT.read_text(encoding="utf-8")), (
        "root 构建脚本里的锁块不合格（须在 subprojects 作用域内、"
        "含 lockAllConfigurations() 与 LockMode.STRICT、且只有一份）"
    )
    dupes = [o for o in duplicate_locking_copies() if "自带锁副本" in o or "不存在" in o]
    assert not dupes, f"模块脚本面不干净（单源被破坏）：{dupes}"


def test_deleting_the_locking_block_turns_the_gate_red() -> None:
    """反向锚（内存态注入，不改工作树）：把锁块拆开必须判红。

    只判「脚本里有没有那段文本」的用例，最常见的失效形态是判据本身恒真——
    这里用真脚本的副本做注入，证明判定真的落在代码上。"""
    real = ROOT_SCRIPT.read_text(encoding="utf-8")
    assert locking_problems(real) == [], "真脚本本身就该通过（否则上一条用例在判空气）"
    match = _BLOCK_RE.search(real)
    assert match, "root 脚本里正则匹配不到那段锁块——注入会因「删不掉」而假装通过"
    injections = {
        "拆掉 subprojects 包裹": real.replace("subprojects {", "{", 1),
        "删掉 lockMode 行": _MODE_RE.sub("", real),
        "删掉整块": _BLOCK_RE.sub("", real),
        "复制成两份": real.replace(match.group(0), match.group(0) * 2, 1),
    }
    for name, injected in injections.items():
        assert locking_problems(injected), f"注入「{name}」后必须判红——否则这条锚恒真"


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
        lock = ANDROID / name / "gradle.lockfile"
        if not lock.exists():
            missing.append(f":{name} 无锁文件")
            continue
        have = locked_configurations(lock.read_text(encoding="utf-8"))
        missing += [f":{name} 缺配置 {cfg}" for cfg in required if cfg not in have]
    assert not missing, f"锁未覆盖 CI 会解析的配置（STRICT 下这些面会当场红）：{missing}"


def test_locks_pin_exact_versions_not_ranges() -> None:
    for name in module_names():
        lock = ANDROID / name / "gradle.lockfile"
        text = lock.read_text(encoding="utf-8")
        assert "SNAPSHOT" not in text, f":{name} 锁里有 -SNAPSHOT 版本"
        entries = [ln for ln in text.splitlines() if ln and not ln.startswith("#")]
        assert len(entries) >= 5, f":{name} 锁条目只有 {len(entries)} 条，不像完整解析结果"


def test_quality_tool_configurations_are_locked_too() -> None:
    """ktlint/detekt 的工具依赖也要进锁——它们每条 PR 都解析，最容易被当成「构建期的事」。

    这两个插件把规则集当依赖解析（`ktlintRuleset`/`detektPlugins`）。不锁的话
    「Android 依赖已锁版本」这句话的覆盖面就悄悄少了整条质量门禁链。"""
    offenders: list[str] = []
    for name in module_names():
        have = locked_configurations(
            (ANDROID / name / "gradle.lockfile").read_text(encoding="utf-8"))
        offenders += [
            f":{name} 缺 {cfg}" for cfg in ("ktlint", "ktlintRuleset", "detekt", "detektPlugins")
            if cfg not in have
        ]
    assert not offenders, f"质量工具面未进锁：{offenders}"


def test_settings_records_the_relock_sop_and_the_uncovered_surface() -> None:
    """决策记录必须写明两件容易被读错的事：锁不覆盖脚本类路径，锁里不含校验和。"""
    text = SETTINGS.read_text(encoding="utf-8")
    assert "buildscript" in text, "settings 没登记 buildscript/plugins 类路径不在锁内"
    assert "校验和" in text, "settings 没登记锁不含校验和（哈希验证是另一刀）"
    assert "dependency-relock.yml" in text, "settings 没指回重锁执行面"
    assert "gradle.lockfile" in text, "settings 没说锁文件落在哪儿（重锁后要有人找它）"


def test_security_doc_matches_the_tree() -> None:
    text = (ROOT / "SECURITY.md").read_text(encoding="utf-8")
    assert "Gradle 依赖无 lock 文件" not in text, "SECURITY.md 仍声称 Android 无锁文件"
    assert "gradle.lockfile" in text, "SECURITY.md 没登记四把 gradle 锁"
    assert "不含校验和" in text, "SECURITY.md 必须如实写「版本锁定不含 hash」"

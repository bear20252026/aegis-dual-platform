#!/usr/bin/env python3
"""verify_gradle_alert_scope_boundary.py —— Android 工具/测试面依赖的**边界**门禁（R9-B49 起，R9-B93 v2）。

判的是什么事实：`docs/security/android-build-classpath-triage.md` 的分诊结论是「这些坐标只存在于
构建/lint 工具类路径，产品运行时零暴露」。这句话不是分诊完就永远真——任何一次普通的
`implementation("org.bouncycastle:bcprov-jdk18on")` 都会把它变成失实陈述，而那时同一份
「tolerable_risk」的证据就是在**掩盖一个真告警**。所以本门禁常驻判坐标归属。

R9-B93 改掉三处，都是实测撞出来的，不是风格问题：
1. **登记表不再抄第二份**。旧版在代码里硬写一个五元组，而分诊文档 §三 的证据面里其实有七个坐标
   （`bcutil-jdk18on`、`logback-classic` 都在四把锁的 `androidLintTool`／`ktlint` 面上，却不在代码
   登记表里）⇒ 那两条哪天插进出货面，本门禁**一条都不判**。现在登记面的单源是分诊文档里那段
   `tooling-only-coordinates` 围栏块，本文件直接读它；读不出＝exit 2，不判「通过」。
2. **措辞不再说「被 dismiss 的 5 个坐标」**。R9-B89 之后这几条不是靠 dismiss 站着而是靠常驻 force
   地板站着，而 2026-10-17T16:00Z 现读 Dependabot 告警面是 `open=0 / fixed=12`（`dismissed` 同为 0）
   ⇒「被 dismiss」描述的状态早已不存在；硬编码的「5」同时也是一条会自己过期的抄写（R9-DOC-24 同族）。
   现在输出的是由实树派生的事实：登记几条、每条落在哪些 configuration、哪些由地板顶住。
3. **补一条会静默发生的洞**：R9-B89 实测「删掉 force 只留锁 ⇒ 下一次例行 `--write-locks` 把锁退回
   1.80.2」（1m3s）。而地板本身此前没有任何 PR 面判据守着。现在判**双向**：地板说的每条坐标必须在
   `androidLintTool` 面真的咬住构件、且锁里解析到的版本恰好等于地板钉的版本（正向）；反过来，登记面内
   且已落在 `androidLintTool` 面的坐标必须有地板顶着（反向）。反向那条抓的是最阴的形状——force 少一条
   时入库锁**此刻还是对的**，只看正向会全绿，而危险挪到下一次例行重锁：那时它静默退回旧版，没人知道。

判定面塌缩（一把锁都读不到、解析出零条坐标、文档或登记块缺失、地板块读不出）一律 exit 2 或判红：
「什么都没判到」不等于「判过了且没问题」。

退出码：0=通过 / 1=越界、登记过期或地板与锁不一致 / 2=环境错误或判定面塌缩。
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOCK_GLOBS = ("android/*/gradle.lockfile",)
DOC = ROOT / "docs" / "security" / "android-build-classpath-triage.md"
BUILD = ROOT / "android" / "build.gradle.kts"
REGISTRY_FENCE = re.compile(r"^```tooling-only-coordinates\n(.*?)^```", re.M | re.S)
# 地板只认 `androidLintTool` 那一条 `resolutionStrategy.force(...)` 里的坐标（出货面不由这块管）。
FLOOR_BLOCK = re.compile(
    r'configurations\.matching \{ it\.name == "androidLintTool" \}\.all \{\s*'
    r'resolutionStrategy\.force\((.*?)\)\s*\}',
    re.S,
)
FORCED_ENTRY = re.compile(r'"([^"]+)"')
LOCK_LINE = re.compile(r"^([\w.\-]+):([\w.\-]+):([\w.\-]+)=(.*)$")
FLOOR_CONFIGURATION = "androidLintTool"

# 出货面：APK 里的 dex 来源，以及装进设备的那份。
SHIPPED_PATTERNS = (
    re.compile(r"^releaseRuntimeClasspath$"),
    re.compile(r"^releaseCompileClasspath$"),
    re.compile(r"^debugRuntimeClasspath$"),
    re.compile(r"^debugCompileClasspath$"),
    re.compile(r"^debugAndroidTest.*Classpath$"),
    re.compile(r"^release.*AndroidTest.*Classpath$"),
)


def is_shipped(configuration: str) -> bool:
    return any(pattern.match(configuration) for pattern in SHIPPED_PATTERNS)


def registry(text: str) -> list[str]:
    """分诊文档 §三 的登记块 → `group:artifact` 列表（单源；本函数不猜、不补默认值）。"""
    match = REGISTRY_FENCE.search(text)
    if not match:
        return []
    return [line.strip() for line in match.group(1).splitlines()
            if line.strip() and not line.lstrip().startswith("#")]


def registered_coordinates() -> list[str]:
    """登记面单源＝分诊文档的围栏块。读不出任何一条时调用方必须走塌缩分支，不能当成「没有要判的」。"""
    if not DOC.is_file():
        return []
    return registry(DOC.read_text(encoding="utf-8", errors="ignore"))


def lock_entries() -> list[tuple[str, str, set[str]]]:
    """每条锁行 → (`group:artifact`, version, configurations)。"""
    entries: list[tuple[str, str, set[str]]] = []
    for path in sorted(ROOT.glob(LOCK_GLOBS[0])):
        for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
            match = LOCK_LINE.match(line.strip())
            if not match:
                continue
            group, artifact, version, configs = match.groups()
            entries.append((f"{group}:{artifact}", version,
                            {c.strip() for c in configs.split(",") if c.strip()}))
    return entries


def locked_configurations() -> dict[str, set[str]]:
    """坐标（group:name）→ 它出现过的全部 configuration 集合（四把锁并集）。"""
    out: dict[str, set[str]] = {}
    for coordinate, _version, configs in lock_entries():
        out.setdefault(coordinate, set()).update(configs)
    return out


def floor_versions() -> dict[str, str]:
    """`androidLintTool` 的常驻 force 地板 → {`group:artifact`: 钉住的版本}。"""
    if not BUILD.is_file():
        return {}
    match = FLOOR_BLOCK.search(BUILD.read_text(encoding="utf-8", errors="ignore"))
    if not match:
        return {}
    out: dict[str, str] = {}
    for token in FORCED_ENTRY.findall(match.group(1)):
        parts = token.split(":")
        if len(parts) == 3:
            out[f"{parts[0]}:{parts[1]}"] = parts[2]
    return out


def floor_resolutions() -> dict[str, set[str]]:
    """四把锁里 `androidLintTool` 面实际解析到的版本：坐标 → 版本集合。"""
    out: dict[str, set[str]] = {}
    for coordinate, version, configs in lock_entries():
        if FLOOR_CONFIGURATION in configs:
            out.setdefault(coordinate, set()).add(version)
    return out


def violations(locked: dict[str, set[str]], registered: list[str]) -> list[str]:
    problems: list[str] = []
    if not locked:
        return [f"锁面为空：{'、'.join(LOCK_GLOBS)} 没解析出任何坐标——判定面塌了"]
    for coordinate in registered:
        configs = locked.get(coordinate)
        if configs is None:
            problems.append(
                f"登记表里的坐标在四把锁中已不存在：{coordinate}"
                "——分诊结论的载体消失了，登记块与文档要同步（不要留着误导下一个读者）")
            continue
        shipped = sorted(config for config in configs if is_shipped(config))
        if shipped:
            problems.append(
                f"{coordinate} 出现在**出货/装机面** configuration：{', '.join(shipped)}"
                "——「仅构建工具面」的分诊结论已不成立，须重新分诊"
                "（若此前按 tolerable_risk dismiss 过，还要撤销那条 dismiss）")
    return problems


def floor_problems(floor: dict[str, str], registered: list[str],
                   resolutions: dict[str, set[str]]) -> list[str]:
    """地板 ⇄ 登记表 ⇄ 锁 三方一致（R9-B93 新增；B89 那条「删 force 就退回旧版」逼出来的）。"""
    problems: list[str] = []
    for coordinate, pinned in sorted(floor.items()):
        if coordinate not in registered:
            problems.append(
                f"地板顶住了 {coordinate}，但它不在分诊文档的登记面内——"
                "要么它属于分诊面（补进登记块），要么这条 force 是来路不明的构建变更")
        versions = resolutions.get(coordinate)
        if not versions:
            problems.append(
                f"地板 force 了 {coordinate}，但四把锁的 `{FLOOR_CONFIGURATION}` 面里一条都没有"
                "——地板空转：它没咬住任何东西，读起来像防护，实际是装饰")
            continue
        if versions != {pinned}:
            problems.append(
                f"{coordinate} 在 `{FLOOR_CONFIGURATION}` 面解析到 {sorted(versions)}，地板钉的是 {pinned}"
                "——不一致通常是 force 被删/被改而锁没跟着重算，或反过来；"
                "B89 实测删掉 force 后例行 `--write-locks` 会把锁退回 1.80.2，所以两边都得判")
    # 反方向：只判「地板说的锁对不对」会漏掉最阴的那种——force 少一条时锁**此刻还是对的**，
    # 于是三方一致全绿，而危险挪到下一次例行 `--write-locks`：那时锁静默退回旧版，PR 面没人知道。
    for coordinate in sorted(resolutions):
        if coordinate in registered and coordinate not in floor:
            problems.append(
                f"{coordinate} 在登记面内、且就在 `{FLOOR_CONFIGURATION}` 面上，却没有地板顶着——"
                "入库锁此刻看着没问题，但它是被例行 `--write-locks` 维护的："
                "少一条 force 的下一次重锁就是静默退回（B89 实测退回 1.80.2）")
    return problems


def run() -> int:
    if not DOC.is_file():
        print(f"[环境错误] 分诊文档缺失：{DOC}", file=sys.stderr)
        return 2
    registered = registry(DOC.read_text(encoding="utf-8", errors="ignore"))
    if not registered:
        print(f"[环境错误] {DOC.name} 读不出 `tooling-only-coordinates` 登记块"
              "——判定面塌了，不作通过判定", file=sys.stderr)
        return 2
    locked = locked_configurations()
    if not locked:
        print(f"[环境错误] {'、'.join(LOCK_GLOBS)} 一把都读不到", file=sys.stderr)
        return 2
    floor = floor_versions()
    problems = violations(locked, registered)
    if floor:
        problems += floor_problems(floor, registered, floor_resolutions())
    else:
        problems.append(f"没读到 `androidLintTool` 的 force 地板（{BUILD.name} 里那段块形状变了或被删）"
                        "——地板是分诊结论的一半，读不到不等于「不需要它」")
    if problems:
        for line in problems:
            print(f"❌ {line}")
        print(f"共 {len(problems)} 条违规（口径见本文件 docstring）")
        return 1
    floored = "、".join(sorted(f"{name}@{version}" for name, version in floor.items()))
    print(f"[ok] 登记 {len(registered)} 个坐标全部只在工具/测试面（分诊结论由坐标归属撑着，"
          "不依赖任何告警状态）：" + "；".join(
              f"{name}←{', '.join(sorted(locked[name]))}" for name in sorted(registered)))
    print(f"[ok] `androidLintTool` 常驻地板与四把锁逐条一致：{floored}")
    return 0


if __name__ == "__main__":
    sys.exit(run())

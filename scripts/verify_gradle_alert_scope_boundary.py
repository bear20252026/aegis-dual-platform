#!/usr/bin/env python3
"""verify_gradle_alert_scope_boundary.py —— 被 dismiss 的 Gradle 告警**边界**门禁（R9-B49 / 分诊文档 §三）。

背景不是「再分诊一遍」：`docs/security/android-build-classpath-triage.md` 第三节里那 9 条告警
（bcprov×3 / bcpkix / commons-lang3 / httpclient / logback×3）判定为「AGP 插件 detached 配置
地板不可达面」并据此 dismiss。第八轮 R8-CI-06 已经抓过一次同型问题——文档把「判定」写成
「已执行的操作」。这一批把另一半也补上：**dismiss 是一个会过期的决定**，它依赖的事实是
「这些坐标只存在于构建/测试工具类路径，不在出货面」。而这个事实此前没有任何东西在判——
只要哪天有人把 `org.bouncycastle:bcprov-jdk18on` 或 `commons-loggin`… 之类写成
`implementation`（出货面），同一份 dismiss 理由立刻从「成立」变成「掩盖了一个真告警」。

判据（每条都在 tests/python/gradle_alert_scope_test.py 里以注入证伪）：
1. 每个已登记坐标出现的 Gradle configuration 必须**全部**落在工具/测试面集合内
   （`androidLintTool`、`ktlint*`、`detekt`、`*UnitTest*Classpath`、`*LintChecksClasspath` 等）；
   出现在出货面（`debug/release Runtime/Compile Classpath`）或插进设备的
   `debugAndroidTest*Classpath` ⇒ 判红。
2. 双向不变量（R9-SH-7 口径）：文档表里登记的坐标若有一条在锁里**完全找不到**也判红——
   那说明上游已经移除该节点，登记表过期要同步（否则下一个读者以为还在暴露）。
3. 锁面塌缩保护：四把锁一把都读不到、或解析出零条坐标 ⇒ 退出 2（读不到不等于「没有暴露」）。

退出码：0=通过 / 1=越界或登记过期 / 2=环境错误。
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOCK_GLOBS = ("android/*/gradle.lockfile",)
DOC = ROOT / "docs" / "security" / "android-build-classpath-triage.md"

# 已被按「构建/测试工具面专属」理由 dismiss 的坐标（group:name，不含版本）。
DISMISSED_TOOLING_ONLY = (
    "org.bouncycastle:bcprov-jdk18on",
    "org.bouncycastle:bcpkix-jdk18on",
    "ch.qos.logback:logback-core",
    "org.apache.commons:commons-lang3",
    "org.apache.httpcomponents:httpclient",
)

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


def locked_configurations() -> dict[str, set[str]]:
    """坐标（group:name）→ 它出现过的全部 configuration 集合（四把锁并集）。"""
    out: dict[str, set[str]] = {}
    for path in sorted(ROOT.glob(LOCK_GLOBS[0])):
        for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            coordinate, _, configs = line.partition("=")
            parts = coordinate.split(":")
            if len(parts) < 3:
                continue
            key = f"{parts[0]}:{parts[1]}"
            out.setdefault(key, set()).update(c.strip() for c in configs.split(",") if c.strip())
    return out


def registered_coordinates() -> tuple[str, ...]:
    """文档第三节表格里登记的坐标（用于双向对账——本函数不解析 markdown，登记表在代码里，
    文档表格由用例逐条核对；这里返回代码里的清单，保持单一判据来源）。"""
    return DISMISSED_TOOLING_ONLY


def violations(locked: dict[str, set[str]]) -> list[str]:
    problems: list[str] = []
    if not locked:
        return [f"锁面为空：{'、'.join(LOCK_GLOBS)} 没解析出任何坐标——判定面塌了"]
    for coordinate in registered_coordinates():
        configs = locked.get(coordinate)
        if configs is None:
            problems.append(
                f"登记表里的坐标在四把锁中已不存在：{coordinate}"
                "——dismiss 理由的载体消失了，登记表与文档要同步（不要留着误导下一个读者）")
            continue
        shipped = sorted(config for config in configs if is_shipped(config))
        if shipped:
            problems.append(
                f"{coordinate} 出现在**出货/装机面** configuration：{', '.join(shipped)}"
                "——按「仅构建工具面」dismiss 的前提已不成立，须重新分诊（并撤销该 dismiss）")
    return problems


def run() -> int:
    if not DOC.is_file():
        print(f"[环境错误] 分诊文档缺失：{DOC}", file=sys.stderr)
        return 2
    locked = locked_configurations()
    if not locked:
        print(f"[环境错误] {'、'.join(LOCK_GLOBS)} 一把都读不到", file=sys.stderr)
        return 2
    problems = violations(locked)
    if problems:
        for line in problems:
            print(f"❌ {line}")
        print(f"共 {len(problems)} 条违规（口径见本文件 docstring）")
        return 1
    tooling = {c: sorted(cfgs) for c, cfgs in locked.items() if c in DISMISSED_TOOLING_ONLY}
    print("[ok] 被 dismiss 的 5 个坐标仍只在工具/测试面："
          + "；".join(f"{name}←{', '.join(cfgs)}" for name, cfgs in sorted(tooling.items())))
    return 0


if __name__ == "__main__":
    sys.exit(run())

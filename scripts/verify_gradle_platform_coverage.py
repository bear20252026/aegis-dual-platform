#!/usr/bin/env python3
"""verify_gradle_platform_coverage.py —— 校验和文档必须覆盖**每个 CI 构建平台**的平台相关构件（R9-B51 / 台账 Q61）。

起因是 R9-B50 自己撞出来的实测事实，不是假想：`gradle/verification-metadata.xml` 登记的是
「本次构建真正落盘的构件字节」，而**平台相关的构件在不同 runner 上落的是不同文件**——
`com.android.tools.build:aapt2` 在 windows 上落 `aapt2-9.4.1-15978811-windows.jar`，
在 ubuntu 上落 `aapt2-9.4.1-15978811-linux.jar`，两者是**两个不同的 sha256**。
本机那一轮只产出了 `-windows.jar`（`-linux` 零命中），而 CI 的 android-quality /
dependency-graph 跑在 ubuntu ⇒ 那一半字节根本不在文档里。
本批先靠 `dependency-relock.yml` 的 gradle 面（ubuntu）再跑一次补齐，但那一次是**人工动作**：
下一次版本 bump 时，谁在 windows 上重算就只补 windows，谁在 ubuntu 上重算就只补 linux，
而缺的那一半不会在任何 PR 面变红——它是「下一个用到该构件的作业当场红」，
那可能是 master push 上的依赖图作业（R9-B32 的同一位置）。**缺一个能红的判据，就得再撞一次。**
R9-B53 把生成面也做成了双腿（ubuntu 锁+字节 → windows 只字节，`needs:` 串行），本判据
因此从「事后追着人补」变成「生成面本身按 `runs-on` 的要求铺满平台」；两条腿的写回面
各自受限（windows 腿不允许写 `gradle.lockfile`），所以补字节不会顺手改动版本真相。

判据（每条都在 tests/python/gradle_platform_coverage_test.py 里以内存注入证伪）：
1. 需要的平台集合**从 workflow 的 `runs-on` 现取**（ubuntu→linux、windows→windows、
   macos→macos），不在代码里手抄 runner 名单——将来加一个 macos runner，这条判据会自动
   要求 macos 形态，而不是继续默默只判两个。
2. 只有「构件名带平台后缀」的坐标进入判定（平台无关坐标本来就是一份字节，无从缺起）。
   对每个这样的坐标版本，要求的平台就是**需求集合本身**：CI 在哪些平台上构建，
   文档里就得有哪些形态。写成「只比同坐标其它版本的并集」是错的——真出事的那一次
   （bump 之后只在 windows 上重算）现场就是「新版本只有 windows、旧版本有两个」，
   按版本并集比会在只有一个版本时恒绿，而那份文档在 ubuntu 上就是缺字节（实测注入过）。
   确实只发单平台包的坐标走 `PLATFORM_EXCLUSIVE`（坐标→理由）：被登记的坐标不再被要求
   「其它平台也要有条目」，而这张表自己也被判（`exemption_problems`）——无理由的条目、
   指向文档里已不存在坐标的条目都要红。豁免必须带理由，否则它就是「放松判据」本身。
3. 平台相关坐标集合为空 ⇒ 退出 2：AGP 构建必然拉 aapt2 的平台包，「零命中」只可能是
   文档被换成了别的东西或解析口径坏了（判定面塌缩按环境错误处理，绝不判「通过」）。

退出码：0=通过 / 1=缺平台形态 / 2=环境或判定面异常。
"""
from __future__ import annotations

import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
METADATA = ROOT / "android" / "gradle" / "verification-metadata.xml"
WORKFLOW_DIR = ROOT / ".github" / "workflows"

NS = "{https://schema.gradle.org/dependency-verification}"
# runner 前缀 → 平台族。键是 workflow 里 `runs-on` 的**前缀**，现读自 workflows/*.yml。
RUNNER_PREFIX_TO_PLATFORM = (("ubuntu", "linux"), ("macos", "macos"), ("windows", "windows"))
# 构件名的平台后缀：`aapt2-9.4.1-15978811-linux.jar`、`protoc-3.25.3-osx-x86_64.exe`、
# `kotlin-native-prebuilt-macos-aarch64-2.2.10.zip`……后缀段之后还可能有版本号，所以不锚行尾，
# 改为「平台段带词边界 + 文件名以已知扩展名结尾」两个条件一起认。
ARTIFACT_PLATFORM = re.compile(
    r"[-_](linux|windows|macos|osx|mac|darwin)(?:[-_.]?(?:x64|x86|arm64|aarch64|amd64|i686|32|64))?\b",
    re.IGNORECASE,
)
ARTIFACT_EXTENSION = re.compile(r"\.(jar|aar|dll|so|dylib|zip|exe|tar\.gz|tgz|7z)$", re.IGNORECASE)
PLATFORM_ALIASES = {"osx": "macos", "darwin": "macos"}


def artifact_platform(artifact_name: str) -> str:
    """构件名 → 平台族（认不出就返回空串＝平台无关，不进判定）。"""
    if not ARTIFACT_EXTENSION.search(artifact_name):
        return ""
    match = ARTIFACT_PLATFORM.search(artifact_name)
    return normalize_platform(match.group(1)) if match else ""


def normalize_platform(token: str) -> str:
    return PLATFORM_ALIASES.get(token.lower(), token.lower())


def runner_platforms(workflow_texts: dict[str, str]) -> set[str]:
    """从 workflow 原文现取「CI 会在哪些平台上构建」——返回平台族集合。"""
    found: set[str] = set()
    for text in workflow_texts.values():
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped.startswith("runs-on:"):
                continue
            value = stripped.split(":", 1)[1].strip().strip("\"'[] ")
            head = value.split(",")[0].strip().strip("\"'").lower()
            for prefix, platform in RUNNER_PREFIX_TO_PLATFORM:
                if head.startswith(prefix):
                    found.add(platform)
    return found


def platform_families_by_component(text: str) -> dict[tuple[str, str, str], set[str]]:
    """校验和文档 → {(group, name, version): 该平台族集合}，只收带平台后缀的构件。"""
    root = ET.fromstring(text)  # nosec B314 —— 信任边界见本文件 docstring：判的是本仓入库文档
    out: dict[tuple[str, str, str], set[str]] = {}
    for component in root.findall(f"{NS}components/{NS}component"):
        key = (component.get("group", ""), component.get("name", ""), component.get("version", ""))
        for artifact in component:
            platform = artifact_platform(artifact.get("name", ""))
            if platform:
                out.setdefault(key, set()).add(platform)
    return out


# 有意为之的空表：某个坐标确实只发一个平台的包（linux 专用的代码生成器之类）时，
# 在这里登记「坐标 → 一句理由」，而不是把判据放松成「只比同坐标的其它版本」。
# 这张表自己也被判（`exemption_problems`）：每条必须有理由，且登记的坐标必须仍在文档里——
# 过期的豁免比缺一条判据更危险，因为它让下一个读者以为「这里被研究过」。
PLATFORM_EXCLUSIVE: dict[str, str] = {}


def violations(needed: set[str], families: dict[tuple[str, str, str], set[str]]) -> list[str]:
    if not needed:
        return ["没从 workflow 的 runs-on 认出任何平台——提取口径坏了，这条判据就是假绿"]
    if not families:
        return []  # 由 run() 按「判定面塌缩」处理，不在这里混成违规
    problems: list[str] = []
    for (group, name, version), present in sorted(families.items()):
        coordinate = f"{group}:{name}"
        if coordinate in PLATFORM_EXCLUSIVE:
            continue  # 豁免的效果就是「不再要求其它平台形态」；它自己是否合法由 exemption_problems 判
        missing = sorted(set(needed) - present)
        if missing:
            problems.append(
                f"{coordinate}:{version} 缺平台形态 {missing}"
                f"（本轮认出它需要 {sorted(needed)}，实际只有 {sorted(present)}）"
                "——校验和只登记本次落盘的字节，请在缺的那个平台上跑一次生成面"
                "（本机 `--refresh-dependencies --write-verification-metadata sha256 ...`"
                " 或 dependency-relock.yml 的 gradle 面）；"
                "若该坐标确实只发一个平台的包，登记进 PLATFORM_EXCLUSIVE 并写理由")
    return problems


def exemption_problems(families: dict[tuple[str, str, str], set[str]]) -> list[str]:
    """豁免表自己的两条不变量：每条要有理由，且登记的坐标必须还在文档里（过期的豁免最危险）。"""
    known = {f"{group}:{name}" for (group, name, _version) in families}
    problems: list[str] = []
    for coordinate, reason in sorted(PLATFORM_EXCLUSIVE.items()):
        if not reason.strip():
            problems.append(f"PLATFORM_EXCLUSIVE 里 {coordinate} 没有理由——没有理由的豁免就是放松判据本身")
        if coordinate not in known:
            problems.append(
                f"PLATFORM_EXCLUSIVE 登记的 {coordinate} 在文档里没有任何平台后缀构件"
                f"（理由：{reason}）——坐标已经不在判定面上，豁免要删掉，别留给下一个读者")
    return problems


def load_workflow_texts() -> dict[str, str]:
    return {path.name: path.read_text(encoding="utf-8", errors="ignore") for path in sorted(WORKFLOW_DIR.glob("*.yml"))}


def coverage_summary(families: dict[tuple[str, str, str], set[str]]) -> str:
    """坐标 → 各版本 ← 平台族，给日志用（判据红时这条就是「现在到底有什么」的现场）。"""
    by_coordinate: dict[tuple[str, str], list[str]] = {}
    for (group, name, version), platforms in families.items():
        by_coordinate.setdefault((group, name), []).append(f"{version}←{','.join(sorted(platforms))}")
    return "；".join(
        f"{group}:{name}[{', '.join(sorted(entries))}]"
        for (group, name), entries in sorted(by_coordinate.items())
    )


def run() -> int:
    if not METADATA.is_file():
        print(f"[环境错误] 校验和文档缺失：{METADATA}——strict 档位下任何解析都会当场红", file=sys.stderr)
        return 2
    if not WORKFLOW_DIR.is_dir():
        print(f"[环境错误] 取不到 workflow 目录：{WORKFLOW_DIR}——需求平台集合无从现取", file=sys.stderr)
        return 2
    try:
        families = platform_families_by_component(METADATA.read_text(encoding="utf-8"))
    except ET.ParseError as exc:
        print(f"[环境错误] 校验和文档不可解析：{exc}", file=sys.stderr)
        return 2
    needed = runner_platforms(load_workflow_texts())
    if not families:
        print(
            f"[环境错误] 文档里没有任何带平台后缀的构件（需要覆盖 {sorted(needed)}）"
            "——AGP 构建必然拉 aapt2 的平台包，零命中说明判定面塌了",
            file=sys.stderr,
        )
        return 2
    problems = violations(needed, families) + exemption_problems(families)
    if problems:
        for line in problems:
            print(f"❌ {line}")
        print(f"共 {len(problems)} 条（口径见本文件 docstring）")
        return 1
    print(f"[ok] 平台并集判据通过：需要覆盖 {sorted(needed)}；平台相关坐标 {coverage_summary(families)}")
    return 0


if __name__ == "__main__":
    sys.exit(run())

#!/usr/bin/env python3
"""verify_gradle_graph_freshness.py —— Gradle 依赖图**内容与锁一致性**的常驻判据（R9-B47 / Q56）。

判的是这条提交面**静默坏掉**的情形。`gradle-dependency-graph.yml` 只在 master push / 周检 / 手动
触发（PR 面零执行），所以它的产物——Android 的 GitHub 依赖图——一旦停止更新，全仓没有一张牌会变红，
而 Dependabot 对 Gradle 侧的漏扫就此失效却无人知晓（第九轮 R9-B31 给 Dependabot 的 #165 跨 major bump
做过一次「先跑一次证明它」，但那是一次性动作，不是判据）。

**为什么不按墙钟时间判**（登记时的建议是「超过 N 天未提交即判红」）：墙钟判据要另一条常跑流水线
去读「最近一次成功运行」，而那条流水线本身也需要有人判它没跑——同一个洞换一层皮。内容对账直接得多：
依赖图必须包含**当前 `android/*/gradle.lockfile` 里的每一个坐标**。锁刚改而图里没有那个坐标，
只可能是「提交链没跑成」或「跑成了但 GitHub 侧没落」——两种都是要红的。周检触发本身就是钟。

判据（每条都在 tests/python/gradle_graph_freshness_test.py 里以注入证伪）：
1. 扫描面塌缩：图里 maven 坐标数 < `MIN_GRAPH_COORDINATES` ⇒ 退出 1（不是「零个缺失」的假绿）；
2. 锁里的坐标在图里找不到 ⇒ 逐条列出（最多 12 条）并判红；
3. 锁面本身为空 ⇒ 退出 2（环境坏了不能判成「依赖图很新鲜」）；
4. 取数失败（无 token / 无仓库名 / HTTP 非 2xx / JSON 形状不对）⇒ 退出 2，**不判绿**。
5. GitHub 落图是最终一致的，所以 `--attempts` 允许在**判红之前**复判几次（默认 1，用例走确定路径）；
   重试耗尽仍缺才红——把「慢」读成「坏」会让人学会忽略这条红灯，那是更贵的失败。


退出码：0=通过 / 1=不一致或面塌缩 / 2=环境错误。
本地复跑（不联网）：`python scripts/verify_gradle_graph_freshness.py --sbom <sbom.json>`
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOCK_GLOBS = ("android/*/gradle.lockfile", "android/gradle.lockfile")
MIN_GRAPH_COORDINATES = 200
MAX_REPORTED = 12


def lock_coordinates() -> set[str]:
    """当前版本锁声明的全部 `group:name` 坐标（四把锁并集，与 R9-B30 的覆盖面同源）。"""
    coords: set[str] = set()
    for pattern in LOCK_GLOBS:
        for path in sorted(ROOT.glob(pattern)):
            for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                parts = line.split("=", 1)[0].split(":")
                if len(parts) >= 3:
                    coords.add(f"{parts[0]}:{parts[1]}")
    return coords


def graph_coordinates(sbom: object) -> set[str]:
    """从 SPDX 文档里取 Gradle/Maven 坐标（`group:name` 形态，与锁同键）。"""
    if not isinstance(sbom, dict):
        raise ValueError("SBOM 顶层不是映射")
    packages = sbom.get("sbom", {}).get("packages")
    if not isinstance(packages, list):
        raise ValueError("SBOM 缺 sbom.packages 列表")
    out: set[str] = set()
    for pkg in packages:
        if not isinstance(pkg, dict):
            continue
        name = pkg.get("name")
        if isinstance(name, str) and ":" in name:
            out.add(name)
    return out


def verdict(locked: set[str], graph: set[str]) -> tuple[list[str], int]:
    """纯判定：返回（问题清单, 退出码）。"""
    if not locked:
        return ([f"锁面为空：{'、'.join(LOCK_GLOBS)} 没解析出任何坐标——判定面塌了"], 2)
    if not graph:
        return (["依赖图为空（0 个 maven 坐标）——Gradle 提交面没有产出，或取到了错的仓库"], 1)
    if len(graph) < MIN_GRAPH_COORDINATES:
        return ([f"依赖图面塌缩：maven 坐标数 {len(graph)} < 下界 {MIN_GRAPH_COORDINATES}"
                 "（图被清空或部分提交比「零个缺失」更危险）"], 1)
    missing = sorted(locked - graph)
    if missing:
        head = "、".join(missing[:MAX_REPORTED])
        more = "" if len(missing) <= MAX_REPORTED else f"…（共 {len(missing)} 条）"
        return ([f"锁里声明而依赖图里没有的坐标 {len(missing)} 条：{head}{more}"
                 "——要么提交链没跑成，要么 GitHub 侧没落图"], 1)
    return ([], 0)


def fetch_sbom(token: str, repository: str) -> object:
    url = f"https://api.github.com/repos/{repository}/dependency-graph/sbom"
    request = urllib.request.Request(url, headers={
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "aegis-graph-freshness",
    })
    # 信任边界：基址是硬编码的 https://api.github.com，唯一变量 GITHUB_REPOSITORY 由 Actions
    # 注入（本仓库自己的 slug），token 只从环境读取、不进 URL 也不打印——B310 关心的是
    # file:/自定义 scheme 与外来 URL，两者在此都不成立。行级注记替代 bandit.yaml 的全局豁免
    # （同 scripts/assert_test_counts.py:59 的 B314 口径：全局豁免会连带放过未来别处的 urlopen）。
    with urllib.request.urlopen(request, timeout=60) as response:  # nosec B310
        return json.load(response)


def judge(document: object) -> int:
    """纯判定入口：文档 → 退出码（用例与重试循环共用同一个判定，不分两套）。"""
    try:
        graph = graph_coordinates(document)
    except ValueError as exc:
        print(f"[环境错误] {exc}", file=sys.stderr)
        return 2
    locked = lock_coordinates()
    problems, code = verdict(locked, graph)
    if code == 2 or problems:
        for line in problems:
            print(f"{'[环境错误]' if code == 2 else '❌'} {line}",
                  file=sys.stderr if code == 2 else sys.stdout)
        return code
    print(f"[ok] 依赖图与当前锁一致（锁 {len(locked)} 条坐标全部在册；图内 maven 坐标 {len(graph)} 个）")
    return 0


def run(sbom_path: str = "", attempts: int = 1, delay: float = 20.0) -> int:
    """GitHub 侧落图是**最终一致**的：提交后立刻读可能还看不到刚 bump 的坐标。
    所以联网判定允许重试到上限——重试耗尽仍缺才判红（`--sbom` 离线口径不重试，用例期望值必须确定）。
    """
    if sbom_path:
        return judge(json.loads(Path(sbom_path).read_text(encoding="utf-8")))
    token = os.environ.get("AEGIS_GRAPH_TOKEN") or os.environ.get("GITHUB_TOKEN", "")
    repository = os.environ.get("GITHUB_REPOSITORY", "")
    if not token or not repository:
        print("[环境错误] 缺 GITHUB_TOKEN / GITHUB_REPOSITORY——取不到依赖图不等于图是新的", file=sys.stderr)
        return 2
    code = 2
    total = max(1, attempts)
    for attempt in range(1, total + 1):
        try:
            document = fetch_sbom(token, repository)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            print(f"[环境错误] 第 {attempt}/{total} 次取数失败：{exc}", file=sys.stderr)
            code = 2
            continue
        code = judge(document)
        if code == 0:
            return 0
        if code == 1 and attempt < total:
            print(f"…依赖图还没反映当前锁（第 {attempt}/{total} 次），{delay}s 后复判", flush=True)
            time.sleep(delay)
    return code


def main() -> int:
    parser = argparse.ArgumentParser(description="Gradle 依赖图与版本锁的一致性判据")
    parser.add_argument("--sbom", default="", help="本地 SPDX JSON（离线复跑/用例用）")
    parser.add_argument("--attempts", type=int, default=1, help="联网判定的重试次数（落图是最终一致的）")
    parser.add_argument("--delay", type=float, default=20.0, help="重试间隔秒数")
    args = parser.parse_args()
    return run(args.sbom, args.attempts, args.delay)


if __name__ == "__main__":
    sys.exit(main())

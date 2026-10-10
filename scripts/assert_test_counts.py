#!/usr/bin/env python3
"""assert_test_counts.py —— R9-CI-9（第九轮 2026-10-10）：测试**发现数**下界门禁。

失效模式：`dotnet test` 的退出码只说「这次跑的都没失败」。如果测试**一个都没被发现**
（适配器版本不匹配、runner 与框架不同代、发现阶段静默零结果），它同样退出 0。
本仓 CI 的八处 `dotnet test`（compat.yml / contracts.yml / native-policy-artifacts.yml /
release-windows.yml）此前都只看退出码 ⇒「绿」的含义是「没有失败的测试」，
不是「跑过 782 个测试（本轮实测）」。

触发点是真实的：把 `xunit.runner.visualstudio` 从 3.1.5 抬到 4.0.1 这类跨 major 的
**测试宿主**升级，一旦发现器与 `xunit` 框架不同代，最坏结果就是零发现全绿——
而同一批 PR 里没有人会察觉。

判据：给定 `--results-dir`，读全部 `*.trx`，按 `counters` 的 total/passed/failed 汇总，
- 目录里没有任何 .trx ⇒ exit 2（**没结果就是没判定**，与 check_file_sizes/
  check_workflow_shells 的空扫描面口径同族，不作通过）；
- 有 .trx 但 total < --minimum ⇒ exit 1；
- failed/error/notExecuted 之外的通过数不足 ⇒ 由 total 下限一并兜住。

用法（CI 与本地同口径）：
    python scripts/assert_test_counts.py \
        --results-dir windows/tests/Aegis.Windows.Core.Tests/TestResults --minimum 700 --label Core

退出码：0=下界达成 / 1=下界未达成或存在失败 / 2=环境错误（缺目录、无 .trx、TRX 不可解析）。
"""

from __future__ import annotations

import argparse
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# TRX 用命名空间；counters 是唯一权威的汇总节点（Total/Passed/Failed/...）
COUNTERS_TAG = "{http://microsoft.com/schemas/VisualStudio/TeamTest/2010}Counters"


def summarize(trx_files: list[Path]) -> tuple[dict[str, int], list[str]]:
    """返回 (汇总计数, 问题列表)。问题列表非空即判定不成立。

    信任边界：只取 counters 的整数属性，不做实体/外部资源解析。输入的 .trx 一律由**同一次
    运行里 dotnet test 自己**写入 `--results-directory` 指定的工作区内目录，不是外来上传物；
    若将来改成「下载他人制品再判定」，此处需换 defusedxml（stdlib expat 不解析外部实体，
    但不禁止内部实体放大）。
    """
    totals: dict[str, int] = {}
    problems: list[str] = []
    for path in trx_files:
        try:
            # 信任边界见本函数 docstring：.trx 由**同一次运行**的 dotnet test 写入工作区内指定
            # 目录，不是外来上传物；恶意 DTD（实体放大/外部实体）在 expat 处走 ET.ParseError
            # ⇒ 本函数判 exit 2，不是静默放行。bandit.yaml 的 PY-270 注记写着「活跃树零
            # ElementTree 使用」——本行是该面第一处，故按 B110/B603 同款口径用**行级注记**，
            # 不把 B314 加回全局 skips。
            tree = ET.parse(path)  # nosec B314
        except (ET.ParseError, OSError) as exc:
            problems.append(f"{path}: TRX 不可解析（{exc}）")
            continue
        counters = tree.getroot().find(f".//{COUNTERS_TAG}")
        if counters is None:
            problems.append(f"{path}: 找不到 counters 节点——结果格式与假设不符")
            continue
        if not any(key.lower() == "total" for key in counters.attrib):
            problems.append(f"{path}: counters 里没有 total 属性——结果格式与假设不符")
            continue
        for key, value in counters.attrib.items():
            try:
                # 属性名按 TRX schema 是小写（total/passed/failed/error/notExecuted）；
                # 归一大小写后查表，免得「查不到键 = 恒 0」把门禁变成恒红或恒绿。
                totals[key.lower()] = totals.get(key.lower(), 0) + int(value)
            except ValueError:
                problems.append(f"{path}: counters[{key}]={value!r} 不是整数")
    return totals, problems


def check(results_dir: Path, minimum: int, label: str) -> int:
    if not results_dir.is_dir():
        print(f"❌ [{label}] 结果目录不存在：{results_dir}（测试未运行或未落 TRX）", file=sys.stderr)
        return 2
    trx_files = sorted(results_dir.glob("*.trx"))
    if not trx_files:
        # 空面 = 没有任何判定输入。此处若放行，就等于「跑没跑测试」无人把关。
        print(f"❌ [{label}] {results_dir} 下没有任何 .trx——不作通过判定", file=sys.stderr)
        return 2
    totals, problems = summarize(trx_files)
    if problems:
        for item in problems:
            print(f"❌ [{label}] {item}", file=sys.stderr)
        return 2
    total = totals.get("total", 0)
    failed = totals.get("failed", 0) + totals.get("error", 0)
    if failed:
        print(f"❌ [{label}] 结果里有 {failed} 条失败/错误（dotnet test 本应已非零退出）")
        return 1
    if total < minimum:
        print(
            f"❌ [{label}] 发现测试数 {total} < 下界 {minimum}——"
            "零发现或大幅缩水通常是**测试宿主/发现器版本不匹配**，不是「代码变好了」",
        )
        return 1
    print(f"✅ [{label}] 发现测试数 {total}（下界 {minimum}），失败 {failed}，共 {len(trx_files)} 份 TRX")
    return 0


def _force_utf8_output() -> None:
    """GitHub Actions 的 Windows 控制台代码页不是 UTF-8（第九轮 PR #137 实测：`dotnet test`
    782/782 全绿、下界达成，脚本却在打印 ✅ 时抛 UnicodeEncodeError ⇒ 退出码 1 ⇒ 门禁在
    **通过**路径上把 job 打红）。与 verify_xaml_resources.py 同口径在入口重配两个流；
    `errors="replace"` 而不是 strict：判定结果绝不能由控制台编码决定。"""
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def main(argv: list[str] | None = None) -> int:
    _force_utf8_output()
    parser = argparse.ArgumentParser(description="TRX 汇总的测试数下界门禁（R9-CI-9）")
    parser.add_argument("--results-dir", required=True, help="含 *.trx 的目录（相对仓库根或绝对路径）")
    parser.add_argument("--minimum", type=int, required=True, help="发现测试数下界（含）")
    parser.add_argument("--label", default="dotnet-test", help="输出前缀（区分多个套件）")
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)
    target = Path(args.results_dir)
    if not target.is_absolute():
        target = ROOT / target
    return check(target, args.minimum, args.label)


if __name__ == "__main__":
    sys.exit(main())

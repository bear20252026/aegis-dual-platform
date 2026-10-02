#!/usr/bin/env python3
"""verify_provenance.py —— 阶段 E（蓝图 release/tools/verify_provenance）：
provenance 逐工件验证（fail-closed——缺失 attestation 是失败不是跳过）。

按调研（gh attestation verify 官方——逐文件 + --signer-workflow 固定 signer
身份（reusable workflow 必需）——默认 slsa.dev/provenance/v1）：对 dist/ 全部
工件逐一验证（NUL 安全——P0-06 模式——不截断 head -200）。任何失败返回非零。
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

PREDICATE_TYPE = "https://slsa.dev/provenance/v1"
# SP-027（审计 2026-09-23 清单·SP1 批）：gh attestation verify 单工件上限
# 120s——网络挂起不再无限阻塞发布门禁（超时按失败计——fail-closed）。
SUBPROCESS_TIMEOUT_SECONDS = 120


def verify_provenance(dist_dir: Path, owner: str, signer_workflow: str) -> list[str]:
    """逐工件 gh attestation verify（官方——固定 signer 身份——fail-closed）。"""
    failures: list[str] = []
    # SP-026（审计 2026-09-23 清单·SP1 批）：目录不存在此前 iterdir() 直接
    # FileNotFoundError traceback 替代干净报告——先 is_dir 检查，缺失即记
    # 失败（无 provenance 证据等于验证失败——fail-closed，与 SP-144 空集同义）。
    if not dist_dir.is_dir():
        failures.append(
            f"dist 目录不存在: {dist_dir}"
            "——无 provenance 可验证即失败（SP-026 fail-closed）")
        return failures
    # SP-029（审计 2026-09-23 清单·SP1 批）：仅迭代顶层——dist/latest-release/
    # 等子目录工件被静默跳过（无 provenance 验证面）。改 rglob 递归（与
    # verify_artifact_set 的 PY-024 递归枚举同口径）。
    targets = [p for p in sorted(dist_dir.rglob("*")) if p.is_file()]
    # SP-144（2026-09-26 审计）：空集恒真退化——dist 目录为空时此前
    # 循环零次、failures=[] 直接打印"全部通过"。空集即失败（没有工件等于
    # 没有任何 provenance 证据——fail-closed）。
    if not targets:
        failures.append(
            f"dist 未枚举任何工件（目录为空: {dist_dir}）"
            "——无 provenance 可验证即失败（SP-144 空集恒真修复）")
        return failures
    for p in targets:
        cmd = [
            "gh", "attestation", "verify", str(p),
            "--owner", owner,
            "--signer-workflow", signer_workflow,
            "--predicate-type", PREDICATE_TYPE,
        ]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True,
                                    check=False, timeout=SUBPROCESS_TIMEOUT_SECONDS)
        except subprocess.TimeoutExpired:
            # SP-027：超时按失败计（不静默放行——fail-closed）
            failures.append(
                f"provenance 验证失败（{SUBPROCESS_TIMEOUT_SECONDS}s 超时——fail-closed）:"
                f" {p.name}")
            continue
        if result.returncode != 0:
            # SP-028（审计 2026-09-23 清单·SP1 批）：失败信息此前不含 stderr——
            # 只报"失败"不给原因，排障需重跑。附 stderr 首行摘要（截断防刷屏，
            # NUL 安全——P0-06 模式）。
            detail = (result.stderr or result.stdout or "").strip().splitlines()
            summary = detail[0][:200] if detail else "无输出"
            failures.append(
                f"provenance 验证失败（缺失 attestation——fail-closed）: {p.name}"
                f" —— gh attestation: {summary}")
    return failures


def _parse_args(argv: list[str]) -> argparse.Namespace:
    """PY-286（2026-10-02 审计）：手工 argv 索引改 argparse——必填 positional
    缺参自动 exit 2（0/1/2 退出码语义不变：用法错误 2、验证失败 1、通过 0）。"""
    parser = argparse.ArgumentParser(
        description="provenance 逐工件验证（gh attestation verify——固定 signer 身份）")
    parser.add_argument("dist_dir", type=Path, help="dist 制品目录")
    parser.add_argument("owner", help="gh attestation --owner（仓库所有者）")
    parser.add_argument("signer_workflow", help="--signer-workflow（固定 signer 身份——SP-143）")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    failures = verify_provenance(args.dist_dir, args.owner, args.signer_workflow)
    if failures:
        for f in failures:
            print(f"❌ {f}")
        print("provenance 验证失败——终止发布（阶段 E——不允许跳过或截断验证）")
        return 1
    print("✅ 全部工件 provenance 验证通过（逐文件——固定 signer 身份）")
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""verify_provenance.py —— 阶段 E（蓝图 release/tools/verify_provenance）：
provenance 逐工件验证（fail-closed——缺失 attestation 是失败不是跳过）。

按调研（gh attestation verify 官方——逐文件 + --signer-workflow 固定 signer
身份（reusable workflow 必需）——默认 slsa.dev/provenance/v1）：对 dist/ 全部
工件逐一验证（NUL 安全——P0-06 模式——不截断 head -200）。任何失败返回非零。
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

PREDICATE_TYPE = "https://slsa.dev/provenance/v1"


def verify_provenance(dist_dir: Path, owner: str, signer_workflow: str) -> list[str]:
    """逐工件 gh attestation verify（官方——固定 signer 身份——fail-closed）。"""
    failures: list[str] = []
    targets = [p for p in sorted(dist_dir.iterdir()) if p.is_file()]
    # SP-144（2026-09-26 审计）：空集恒真退化——dist 目录缺失/为空时此前
    # 循环零次、failures=[] 直接打印"全部通过"。空集即失败（没有工件等于
    # 没有任何 provenance 证据——fail-closed）。
    if not targets:
        failures.append(
            f"dist 未枚举任何工件（目录缺失或为空: {dist_dir}）"
            "——无 provenance 可验证即失败（SP-144 空集恒真修复）")
        return failures
    for p in targets:
        cmd = [
            "gh", "attestation", "verify", str(p),
            "--owner", owner,
            "--signer-workflow", signer_workflow,
            "--predicate-type", PREDICATE_TYPE,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if result.returncode != 0:
            failures.append(f"provenance 验证失败（缺失 attestation——fail-closed）: {p.name}")
    return failures


def main() -> int:
    if len(sys.argv) < 4:
        print("用法: verify_provenance.py <dist_dir> <owner> <signer_workflow>")
        return 2
    failures = verify_provenance(
        Path(sys.argv[1]), sys.argv[2], sys.argv[3])
    if failures:
        for f in failures:
            print(f"❌ {f}")
        print("provenance 验证失败——终止发布（阶段 E——不允许跳过或截断验证）")
        return 1
    print("✅ 全部工件 provenance 验证通过（逐文件——固定 signer 身份）")
    return 0


if __name__ == "__main__":
    sys.exit(main())

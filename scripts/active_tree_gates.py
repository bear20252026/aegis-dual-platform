#!/usr/bin/env python3
"""active_tree_gates.py —— PY-263（2026-10-02 审计）：活跃树质量门禁单源。

背景：legacy-python-guard.yml 中「ruff 检查（根仓库脚本……）」与「bandit
安全扫描（活跃树 scripts/release/contracts/agent——PY-245 接线）」两个步骤
的命令行此前各自内联在 workflow 里（.github 与本地手工复跑双源漂移面），
且只有周六 cron 触发。本脚本把两步的命令参数收拢为可复用单源：

- ruff 门禁：ruff check scripts release contracts agent validate_release.py
  tests core/rust-policy-core/bindings（口径与 workflow 步骤逐字一致）
- bandit 门禁：bandit -c bandit.yaml -r scripts release contracts agent
  validate_release.py tests core/rust-policy-core/bindings -ll -q
  （配置单源根级 bandit.yaml——仅 Medium/High 触发失败；SP-227 面对齐 ruff）

.workflow 后续接线（SP 批承接 .github 变更）直接以
``python scripts/active_tree_gates.py ruff`` / ``... bandit`` 替代内联命令行，
本地亦可随时复跑同一口径。统一经 ``sys.executable -m`` 调用——不依赖
ruff/bandit 在 PATH 中的安装形态（与 pytest 调用口径一致）。

用法：
    python scripts/active_tree_gates.py            # 全部门禁（ruff + bandit）
    python scripts/active_tree_gates.py ruff       # 仅 ruff
    python scripts/active_tree_gates.py bandit     # 仅 bandit

退出码：0=全部通过 / 1=任一门禁失败（子工具退出码透传汇总）。
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# ruff 门禁目标面——与 legacy-python-guard.yml 现行步骤逐字一致
#（SP-208 门禁面：validate_release.py、tests/python、core/rust-policy-core/
#  bindings 均在 lint 范围内；pyproject.toml 的 [tool.ruff] 是规则单源）
RUFF_TARGETS = [
    "scripts", "release", "contracts", "agent",
    "validate_release.py", "tests", "core/rust-policy-core/bindings",
]

# bandit 门禁目标面 + 阈值口径（-ll 仅 Medium/High 失败；豁免单源 bandit.yaml）
# SP-227（2026-10-02 审计）：对齐 SP-208 ruff 面——validate_release.py、tests、
# core/rust-policy-core/bindings 此前不在 SAST 范围（subprocess/哈希操作漏扫）
BANDIT_TARGETS = [
    "scripts", "release", "contracts", "agent",
    "validate_release.py", "tests", "core/rust-policy-core/bindings",
]
BANDIT_EXTRA_ARGS = ["-ll", "-q"]


def _run_gate(name: str, cmd: list[str]) -> int:
    """执行单个门禁子命令——cwd 锚定仓库根，退出码透传。"""
    print(f"[gate] {name}: {' '.join(cmd)}")
    # PLW1510：门禁以子工具退出码为断言对象——显式 check=False 手动判定
    result = subprocess.run(cmd, cwd=str(ROOT), check=False)
    status = "OK" if result.returncode == 0 else f"FAILED (exit {result.returncode})"
    print(f"[gate] {name}: {status}")
    return result.returncode


def run_ruff() -> int:
    """ruff 门禁（规则面单源 pyproject.toml——本脚本只固定目标清单）。"""
    return _run_gate("ruff", [sys.executable, "-m", "ruff", "check", *RUFF_TARGETS])


def run_bandit() -> int:
    """bandit 门禁（豁免面单源 bandit.yaml——本脚本只固定目标与阈值）。"""
    return _run_gate(
        "bandit",
        [sys.executable, "-m", "bandit", "-c", "bandit.yaml",
         "-r", *BANDIT_TARGETS, *BANDIT_EXTRA_ARGS],
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="活跃树（scripts/release/contracts/agent）质量门禁单源"
                    "（ruff + bandit——与 legacy-python-guard 步骤同口径）")
    parser.add_argument(
        "gate", nargs="?", choices=("ruff", "bandit", "all"), default="all",
        help="执行哪个门禁（默认 all=ruff+bandit）")
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)
    if args.gate == "ruff":
        return run_ruff()
    if args.gate == "bandit":
        return run_bandit()
    # all：任一失败即失败（ruff 先行——静态违规通常比 SAST 发现更快定位）
    ruff_rc = run_ruff()
    bandit_rc = run_bandit()
    return 0 if ruff_rc == 0 and bandit_rc == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""run-security-e2e —— 蓝图 scripts/run-security-e2e。

安全端到端入口：一键运行 Agent 红队（redteam_test/redteam_e2e）+ 契约验证
（verify_contract_compatibility）。按蓝图 run-security-e2e——安全回归统一入口。
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def main() -> int:
    # R7-TOOL-06（第七轮 2026-10-04）：被驱动的三个脚本全以裸 `assert` 表达断言。
    # `PYTHONOPTIMIZE` 会被 subprocess 继承，于是 -O 环境下整套安全 e2e 会跑完并
    # 打印「✅ 安全 e2e 通过」而实际零判定——本入口先拒绝该模式。
    if sys.flags.optimize or (os.environ.get("PYTHONOPTIMIZE") or "").strip():
        print("❌ 安全 e2e 不接受 -O / PYTHONOPTIMIZE（被驱动脚本的断言会被剥离，"
              "运行结果无判定力）", file=sys.stderr)
        return 2
    steps = [
        ([str(ROOT / "contracts/codegen/verify_contract_compatibility.py")],
         "契约兼容性（阶段 B）"),
        # R7-TOOL-06（第七轮 2026-10-04）：两份红队套件的手工运行器已删除——
        # 它们以裸 `assert` 表达断言，`python -O <file>.py` 下断言被整体剥离却
        # 打印 ALL OK、exit 0。唯一安全入口是 pytest（重写器使断言在 -O 下仍红，
        # 实测 `-O -m pytest` 照样 failed），故本入口驱动 pytest 而非脚本自身。
        (["-m", "pytest", "-q", "agent/tests/redteam_test.py"],
         "Agent 红队测试（阶段 G）"),
        (["-m", "pytest", "-q", "agent/tests/redteam_e2e_test.py"],
         "Agent 红队 e2e（阶段 G 完成标准）"),
    ]
    for argv_tail, note in steps:
        print(f"--- {note} ---")
        # PY-031：补 timeout + stderr 透传（此前失败诊断信息全丢）
        argv = [sys.executable] + argv_tail
        label = " ".join(argv_tail)
        try:
            r = subprocess.run(argv, cwd=str(ROOT),
                               capture_output=True, text=True, check=False, timeout=180)
        except subprocess.TimeoutExpired:
            print(f"❌ {label} 超时（180s）——安全 e2e 未通过")
            return 1
        # PY-200（2026-09-26 审计）：此前只打印 stdout 最后一行——完整测试
        # 输出被截断（失败归因困难）。改完整透传（对齐 codegen-contracts/run.py）。
        print(r.stdout.strip())
        if r.stderr.strip():
            print(r.stderr.strip(), file=sys.stderr)
        if r.returncode != 0:
            print(f"❌ {label} 失败——安全 e2e 未通过")
            return 1
    print("✅ 安全 e2e 通过（契约一致 + 红队断言拒绝——无未批准副作用）")
    return 0


if __name__ == "__main__":
    sys.exit(main())

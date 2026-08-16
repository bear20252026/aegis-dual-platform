#!/usr/bin/env python3
"""run-security-e2e —— 蓝图 scripts/run-security-e2e。

安全端到端入口：一键运行 Agent 红队（redteam_test/redteam_e2e）+ 契约验证
（verify_contract_compatibility）。按蓝图 run-security-e2e——安全回归统一入口。
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def main() -> int:
    steps = [
        ("contracts/codegen/verify_contract_compatibility.py", "契约兼容性（阶段 B）"),
        ("agent/tests/redteam_test.py", "Agent 红队测试（阶段 G）"),
        ("agent/tests/redteam_e2e_test.py", "Agent 红队 e2e（阶段 G 完成标准）"),
    ]
    for rel, note in steps:
        print(f"--- {note} ---")
        r = subprocess.run([sys.executable, str(ROOT / rel)], capture_output=True, text=True)
        print(r.stdout.strip().splitlines()[-1] if r.stdout else "")
        if r.returncode != 0:
            print(f"❌ {rel} 失败——安全 e2e 未通过")
            return 1
    print("✅ 安全 e2e 通过（契约一致 + 红队断言拒绝——无未批准副作用）")
    return 0


if __name__ == "__main__":
    sys.exit(main())

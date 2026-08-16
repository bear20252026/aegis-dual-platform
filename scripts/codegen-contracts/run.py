#!/usr/bin/env python3
"""codegen-contracts —— 蓝图 scripts/codegen-contracts。

契约代码生成入口（蓝图迁移表：scripts/gen_jsapi_schema.py → contracts/codegen——
替换为生成 C#/Kotlin 模型而非网页 bridge）。一键：生成 C#/Kotlin 模型 +
兼容性验证（阶段 B 完成标准——跨语言一致）。
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

CODEGEN = Path(__file__).resolve().parents[2] / "contracts" / "codegen"


def main() -> int:
    steps = [
        ("generate_csharp.py", "生成 C# 模型"),
        ("generate_kotlin.py", "生成 Kotlin 模型"),
        ("verify_contract_compatibility.py", "契约兼容性（跨语言一致）"),
    ]
    for script, note in steps:
        print(f"--- {note} ---")
        r = subprocess.run([sys.executable, str(CODEGEN / script)], capture_output=True, text=True)
        print(r.stdout.strip())
        if r.returncode != 0:
            print(f"❌ {script} 失败")
            return 1
    print("✅ 契约代码生成完成（C#/Kotlin 模型 + 跨语言一致——阶段 B 完成标准）")
    return 0


if __name__ == "__main__":
    sys.exit(main())

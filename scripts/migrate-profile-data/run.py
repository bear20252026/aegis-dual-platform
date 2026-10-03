#!/usr/bin/env python3
"""migrate-profile-data —— 蓝图 scripts/migrate-profile-data。

profile 数据迁移骨架（蓝图迁移表：bookmark_store/history_store/database →
Windows.Storage/android.storage——加密、最小化、schema migration 与导入审计）。
迁移数据按不可信输入处理（蓝图——导入审计）。骨架——完整迁移按蓝图迭代。

SP-038（审计 2026-09-23 清单·SP1 批）：骨架此前恒返回 0——"虚假成功"（调用
方无法区分「迁移完成」与「骨架未实现」）。改为专用退出码：EXIT_NOT_IMPLEMENTED=3
（与常规失败 1 区分——自动化可据此跳过或提示），迁移真正落地后返回 0。
SP-084：argparse 预留 CLI 形态（--source/--target/--dry-run）——参数已定义并
校验，实现落地后即用；SP-085：四步骤以常量清单声明并逐项断言存在——防止
后续实现遗漏步骤（回归保护锚点）。
"""

from __future__ import annotations

import argparse
import sys

# SP-038：专用退出码——骨架未实现 ≠ 成功
EXIT_NOT_IMPLEMENTED = 3

# SP-085：迁移步骤单源声明——完整实现必须逐项覆盖（回归保护）
MIGRATION_STEPS = (
    "旧存储读取（bookmark/history/database——按不可信输入处理）",
    "加密迁移（Windows Storage——DPAPI / Android——Keystore）",
    "数据最小化（只迁移必要数据——schema migration + 导入审计）",
    "迁移日志脱敏（不记录 token/网页内容——Diagnostics）",
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="migrate-profile-data",
        description="profile 数据迁移（蓝图骨架——加密/最小化/审计）",
    )
    parser.add_argument("--source", help="旧 profile 存储目录（实现落地后必填）")
    parser.add_argument("--target", help="目标存储目录（实现落地后必填）")
    parser.add_argument(
        "--dry-run", action="store_true", help="演练模式：只报告将迁移的内容")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    print("=== profile 数据迁移（蓝图 scripts/migrate-profile-data——骨架）===")
    if args.source or args.target:
        print(
            f"  参数已受理（source={args.source!r} target={args.target!r} "
            f"dry_run={args.dry_run}）——迁移实现按蓝图阶段 C/D 迭代")
    print("步骤（按蓝图迁移表）：")
    for index, step in enumerate(MIGRATION_STEPS, start=1):
        # SP-085：步骤声明非空断言——清单被误改空/截断即在此暴露
        # 审计第六轮（2026-10-03）：改显式 raise——-O/PYTHONOPTIMIZE 剥离断言，
        # MIGRATION_STEPS 损坏将完全不可见（PY-187/SP-209 同型）
        if not step:
            raise SystemExit(f"迁移步骤 {index} 描述为空（MIGRATION_STEPS 损坏）")
        print(f"  {index}. {step}")
    if len(MIGRATION_STEPS) != 4:
        raise SystemExit("蓝图定义迁移必须为四步骤（回归保护）")
    print("骨架——完整迁移实现按蓝图阶段 C/D 迭代（exit 3=未实现）")
    return EXIT_NOT_IMPLEMENTED


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""verify_manifest.py —— 阶段 E（蓝图 release/tools/verify_manifest）：
更新清单验证——复用 release/update_verifier.py（P0-04 已统一：SemVer 字符串/
signatures[]/重复 key_id 只计一次/异常封装 UpdateRejected——TUF 阈值签名对齐）。

发布链独立验证（蓝图阶段 E）：manifest 必须通过签名/回滚/过期/阈值验证——
任何失败返回非零（终止发布——fail-closed——不允许跳过或截断验证）。
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

# 复用 P0-04 更新验证器（契约统一——contracts/schemas/update-manifest.schema.json）
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from release.update_verifier import UpdateRejected, verify_manifest


def main() -> int:
    if len(sys.argv) < 4:
        print("用法: verify_manifest.py <manifest.json> <trusted_keys.json> <min_version>")
        return 2
    manifest = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    trusted = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
    try:
        verify_manifest(manifest, trusted, sys.argv[3], datetime.now(UTC), threshold=2)
    except UpdateRejected as exc:
        print(f"❌ 更新清单验证失败: {exc}（终止发布——fail-closed）")
        return 1
    print("✅ 更新清单验证通过（签名阈值/防回滚/过期——P0-04 契约统一）")
    return 0


if __name__ == "__main__":
    sys.exit(main())

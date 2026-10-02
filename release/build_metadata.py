"""生成 Aegis 发布制品的可追溯构建元数据。

该清单与 SHA-256 摘要一同打入 dist/，将平台制品明确绑定到共享版本源、
Git 提交和 GitHub Actions 运行。它不包含签名私钥、访问令牌或其他敏感信息。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# PY-185（2026-09-26 审计）：本文件与 scripts/sync_versions.py 各有一份
# load_properties（双源）——本副本 `line.split("=", 1)` 对无 "=" 行直接
# ValueError 原始栈，而 sync_versions 副本已修为带 文件:行号 的 RuntimeError。
# 现删除本副本、锚定 sys.path 复用 scripts/sync_versions.load_properties
#（保留行号报错语义——properties 解析规则单源，两处不再漂移）。
sys.path.insert(0, str(ROOT / "scripts"))
from sync_versions import load_properties


def main() -> None:
    parser = argparse.ArgumentParser(description="Write Aegis release build metadata")
    parser.add_argument("--platform", required=True, choices=("android", "windows", "rust-core"))
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    # PY-266（2026-10-02 审计）：缺 version.properties 此前在 load_properties
    # 的 read_text 处裸 FileNotFoundError traceback——前置 is_file 检查，
    # 缺失给干净报错退出 2（环境错误语义——与 SystemExit(1) 的属性缺失
    # 门禁失败区分：前者是仓库/运行时环境不完整，后者是单源属性不全）
    props_path = ROOT / "shared" / "version.properties"
    if not props_path.is_file():
        print(f"缺少共享版本源文件: {props_path}（环境错误——exit 2）", file=sys.stderr)
        raise SystemExit(2)
    values = load_properties(props_path)
    required = ("PRODUCT", "DISPLAY_NAME", "VERSION_NAME", "VERSION_CODE", "WINDOWS_PACKAGE_VERSION")
    missing = [key for key in required if not values.get(key)]
    if missing:
        raise SystemExit(f"缺少共享版本属性: {', '.join(missing)}")

    metadata = {
        "schema_version": 1,
        "product": values["PRODUCT"],
        "display_name": values["DISPLAY_NAME"],
        "platform": args.platform,
        "version_name": values["VERSION_NAME"],
        "version_code": values["VERSION_CODE"],
        "windows_package_version": values["WINDOWS_PACKAGE_VERSION"],
        "source_revision": os.environ.get("GITHUB_SHA", "local-unverified"),
        "source_ref": os.environ.get("GITHUB_REF", "local-unverified"),
        "workflow_run_id": os.environ.get("GITHUB_RUN_ID", "local-unverified"),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    # PY-268（2026-10-02 审计）：newline="\n" 显式锁定——Windows 默认把 \n
    # 翻译为 CRLF，发布产物 build-metadata.json 在 autocrlf 关闭的环境即
    # 行尾漂移（对账/diff 假红）
    args.output.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8", newline="\n")
    # Windows GitHub-hosted runner 默认控制台可能为 cp1252；发布链日志必须可移植。
    print(f"Wrote {args.platform} build metadata: {args.output}")


if __name__ == "__main__":
    main()

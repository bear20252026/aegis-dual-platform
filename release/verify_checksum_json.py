"""严格验证发布目录的 SHA-256 JSON 清单，路径必须相对于发布根目录。"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

# PY-212（2026-09-26 审计）：待摘要文件集合（排除清单自身）此前在本文件
# 与 write_checksum_json.build_manifest 各自推导一份——规则演化必漂移。
# 锚定同目录后复用写侧的共享 iter_release_files（单源）。
from write_checksum_json import iter_release_files, sha256_file

SHA256_HEX = re.compile(r"^[0-9A-F]{64}$")


def verify_manifest(root: Path, manifest_path: Path) -> int:
    """验证完整、唯一且不逃逸 ``root`` 的发布摘要清单。"""
    root = root.resolve()
    manifest_path = manifest_path.resolve()
    if not root.is_dir():
        raise SystemExit(f"发布根目录不存在: {root}")
    if not manifest_path.is_file() or not manifest_path.is_relative_to(root):
        raise SystemExit("摘要清单必须是发布根目录内的普通文件")

    try:
        entries = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise SystemExit(f"摘要清单不是有效 JSON: {error}") from error
    if not isinstance(entries, list) or not entries:
        raise SystemExit("摘要清单必须是非空数组")

    expected = {
        path.relative_to(root).as_posix()
        # PY-212：文件集合与写侧单源（排除清单自身的规则只此一份）
        for path in iter_release_files(root, manifest_path)
    }
    observed: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict):
            raise SystemExit("摘要清单条目必须是对象")
        relative = entry.get("Path")
        expected_hash = entry.get("Hash")
        if not isinstance(relative, str) or not relative or "\\" in relative:
            raise SystemExit("摘要路径必须是非空 POSIX 相对路径")
        if not isinstance(expected_hash, str) or not SHA256_HEX.fullmatch(expected_hash):
            raise SystemExit(f"摘要格式无效: {relative}")
        if relative in observed:
            raise SystemExit(f"摘要清单包含重复路径: {relative}")
        observed.add(relative)

        candidate = (root / relative).resolve()
        if not candidate.is_relative_to(root):
            raise SystemExit(f"摘要路径越出发布根目录: {relative}")
        if not candidate.is_file():
            raise SystemExit(f"摘要清单指向缺失文件: {relative}")
        # PY-191（2026-09-26 审计）：candidate.read_bytes() 整文件进内存——
        # 写入侧已 1MiB 分块流式，校验侧对大安装包同样整读。现对齐共享
        # sha256_file（1MiB 分块摘要——PY-212 一并单源）。
        actual_hash = sha256_file(candidate)
        if actual_hash != expected_hash:
            raise SystemExit(f"SHA-256 不匹配: {relative}")

    missing = expected - observed
    extra = observed - expected
    if missing or extra:
        details = []
        if missing:
            details.append(f"未覆盖文件: {', '.join(sorted(missing))}")
        if extra:
            details.append(f"不存在文件: {', '.join(sorted(extra))}")
        raise SystemExit("; ".join(details))
    return len(observed)


def main() -> int:
    parser = argparse.ArgumentParser(description="验证发布制品 SHA-256 JSON 清单")
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    args = parser.parse_args()
    count = verify_manifest(args.root, args.manifest)
    print(f"Checksum manifest verified: {count} artifact(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

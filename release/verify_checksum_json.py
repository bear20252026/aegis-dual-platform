"""严格验证发布目录的 SHA-256 JSON 清单，路径必须相对于发布根目录。"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

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
        for path in root.rglob("*")
        if path.is_file() and path.resolve() != manifest_path
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
        actual_hash = hashlib.sha256(candidate.read_bytes()).hexdigest().upper()
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

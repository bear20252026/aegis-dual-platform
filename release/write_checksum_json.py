"""以稳定 JSON 结构生成发布目录的 SHA-256 清单。"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections.abc import Iterator
from pathlib import Path

# PY-278（2026-10-02 审计）：原子写单源（scripts/atomic_write.py——同目录
# 临时文件 + os.replace）——此前直接 write_text，写入中断留半截清单
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from atomic_write import atomic_write_text

# 1MiB 分块（PY-039：发布目录可含大体积制品——安装包/库——流式摘要）
_CHUNK = 1 << 20


def iter_release_files(root: Path, manifest_path: Path) -> Iterator[Path]:
    """枚举发布根下参与摘要对账的全部普通文件，排除清单自身。

    PY-212（2026-09-26 审计）：「排除清单自身」的文件集合推导此前在
    write_checksum_json.build_manifest 与 verify_checksum_json.verify_manifest
    各自实现一份——规则演化时两处必漂移（写侧漏一个文件、读侧多验一个
    文件，互相对不上）。现抽共享单源：两侧都经由本函数得到同一文件集合。
    """
    manifest_resolved = manifest_path.resolve()
    for path in sorted(root.rglob("*")):
        if path.is_file() and path.resolve() != manifest_resolved:
            yield path


def sha256_file(path: Path) -> str:
    """1MiB 分块流式 SHA-256（写/读两侧共用——PY-191 对齐）。"""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(_CHUNK), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def build_manifest(root: Path, output: Path) -> list[dict[str, str]]:
    # relative_to 同时承担"输出必须在发布根内"的守卫（越界即 ValueError）
    output.relative_to(root)
    entries = []
    # PY-212：文件集合来自共享 iter_release_files（清单自排除单源）
    for path in iter_release_files(root, output):
        relative = path.relative_to(root)
        # PY-039：整文件 read_bytes 进内存——发布目录可含大体积制品
        #（安装包/库），改 1MiB 分块流式摘要
        entries.append(
            {
                "Hash": sha256_file(path),
                "Path": relative.as_posix(),
            }
        )
    if not entries:
        raise SystemExit("发布目录没有可生成摘要的制品")
    return entries


def main() -> int:
    parser = argparse.ArgumentParser(description="生成发布制品 SHA-256 JSON 清单")
    parser.add_argument("--root", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    root = Path(args.root).resolve()
    output = Path(args.output).resolve()
    try:
        output.relative_to(root)
    except ValueError as error:
        raise SystemExit("输出清单必须位于发布根目录") from error
    # PY-268/278：LF 锁定 + 原子落盘（半截清单消除——newline 与同步侧口径一致）
    atomic_write_text(
        output, json.dumps(build_manifest(root, output), indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

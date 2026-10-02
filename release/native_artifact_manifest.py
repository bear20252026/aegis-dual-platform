#!/usr/bin/env python3
"""生成并校验 Aegis Rust 策略核心的原生制品清单。

此工具只接受 ADR-006 定义的精确制品路径。它拒绝缺失文件、符号链接和空文件，
以确保平台加载器所依赖的库名、ABI 目录及发布哈希均可审计。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

SCHEMA_VERSION = 1
LIBRARY = "aegis_policy_core"
EXPECTED_ARTIFACTS = {
    "windows": (
        {
            "abi": "win-x64",
            "target": "x86_64-pc-windows-msvc",
            "relative_path": "windows/win-x64/aegis_policy_core.dll",
        },
    ),
    "android": (
        {
            "abi": "arm64-v8a",
            "target": "aarch64-linux-android",
            "relative_path": "android/arm64-v8a/libaegis_policy_core.so",
        },
        # 单架构策略（2026-08-30）：仅 arm64-v8a——99% 真机覆盖；
        # armeabi-v7a（32 位老架构）与 x86/x86_64（模拟器）不再构建/分发
    ),
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_manifest(root: Path, required_platforms: list[str]) -> dict[str, object]:
    artifacts: list[dict[str, object]] = []
    for platform in required_platforms:
        for expected in EXPECTED_ARTIFACTS[platform]:
            path = root / expected["relative_path"]
            if path.is_symlink() or not path.is_file():
                raise ValueError(f"缺少或不是普通文件: {expected['relative_path']}")
            size = path.stat().st_size
            if size == 0:
                raise ValueError(f"原生制品不能为空: {expected['relative_path']}")
            artifacts.append(
                {
                    "platform": platform,
                    "abi": expected["abi"],
                    "target": expected["target"],
                    "path": expected["relative_path"],
                    "size_bytes": size,
                    "sha256": sha256_file(path),
                }
            )
    return {
        "schema_version": SCHEMA_VERSION,
        "library": LIBRARY,
        "artifacts": artifacts,
    }


def read_manifest(path: Path) -> dict[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"无法读取清单: {path}: {error}") from error
    if not isinstance(value, dict):
        # ValueError 是本模块清单校验的既定契约（PY-146 用例与调用方
        # 均按 ValueError 处理），不改抛 TypeError。
        # PY-238（2026-10-01 审计）：显式 select 后 TRY004 不在规则面——
        # 该 noqa 成为死指令（RUF100），删除；如日后扩面纳入 TRY004
        # 再按需重新豁免。
        raise ValueError("清单根节点必须是对象")
    return value


# PY-261（2026-10-02 审计）：--require 旗标序无关的规范比较形态——
# artifacts 列表按 (platform, abi, path) 排序（字符串元组序稳定），
# 其余顶层字段原样保留参与相等比较。
def _artifact_sort_key(artifact: object) -> tuple[str, str, str]:
    if not isinstance(artifact, dict):
        return ("", "", "")
    return (str(artifact.get("platform", "")),
            str(artifact.get("abi", "")),
            str(artifact.get("path", "")))


def _canonical_for_compare(manifest: dict[str, object]) -> dict[str, object]:
    canonical = dict(manifest)
    artifacts = canonical.get("artifacts")
    if isinstance(artifacts, list):
        canonical["artifacts"] = sorted(artifacts, key=_artifact_sort_key)
    return canonical


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True, help="原生制品根目录")
    parser.add_argument("--output", type=Path, required=True, help="清单 JSON 输出或待复核文件")
    parser.add_argument(
        "--require",
        action="append",
        choices=sorted(EXPECTED_ARTIFACTS),
        required=True,
        help="必须存在的制品平台；可重复传入",
    )
    parser.add_argument("--verify", action="store_true", help="复算制品并校验现有清单，不写入")
    args = parser.parse_args()

    try:
        manifest = build_manifest(args.root, args.require)
        if args.verify:
            existing = read_manifest(args.output)
            # PY-261（2026-10-02 审计）：比较前按 (platform, abi, path) 排序
            # artifacts——build_manifest 按 --require 旗标序生成，换序重跑
            #（android 在前/windows 在前）会因列表顺序不同被误判「不一致」
            #（制品集合本身相同）。排序归一后比较，只对真实差异（文件/哈希/
            # 字段）失败；清单其余顶层字段仍全量比对。
            if _canonical_for_compare(existing) != _canonical_for_compare(manifest):
                raise ValueError("原生制品清单与当前文件、路径或 SHA-256 不一致")
            print(f"OK: native artifact manifest verified: {args.output}")
        else:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(
                json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            print(f"OK: native artifact manifest written: {args.output}")
    except ValueError as error:
        print(f"ERROR: native artifact manifest rejected: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""verify_artifact_set.py —— 阶段 E（蓝图 release/tools/verify_artifact_set）：
逐工件闭合验证（fail-closed——不允许截断/忽略——蓝图阶段 E 完成标准）。

按调研（gh attestation verify 逐工件官方 + 张显达"部署侧强制校验失败即阻断——
证据包"）：对 dist/ 全部工件与 manifest 做双向集合相等检查（缺失/多余/哈希
不符 → 非零退出终止发布）。任何验证失败返回非零（release.yml 门禁）。
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def verify_artifact_set(dist_dir: Path, manifest: dict) -> list[str]:
    """双向集合相等：manifest 枚举的每个工件必须存在且哈希相符；
    dist 实际工件必须全部在 manifest 中（未列明工件拒绝——蓝图）。"""
    failures: list[str] = []
    manifest_artifacts = manifest.get("artifacts") or []
    if not isinstance(manifest_artifacts, list):
        failures.append("manifest.artifacts 不是数组")
        return failures

    expected: dict[str, str] = {}  # 相对路径 -> sha256
    for art in manifest_artifacts:
        if not isinstance(art, dict):
            failures.append("manifest.artifacts 含非对象条目")
            continue
        rel = art.get("url", "").split("/")[-1] if isinstance(art.get("url"), str) else ""
        sha = art.get("sha256", "")
        if rel and isinstance(sha, str) and len(sha) == 64:
            expected[rel] = sha.lower()
        else:
            failures.append(f"manifest 工件条目无效: {art}")

    actual = {p.name: p for p in dist_dir.iterdir() if p.is_file()}
    # 1) 缺失/哈希不符（manifest 枚举必须全部存在且相符）
    for rel, sha in expected.items():
        p = actual.get(rel)
        if p is None:
            failures.append(f"缺失工件: {rel}")
        elif _sha256(p) != sha:
            failures.append(f"哈希不符: {rel}")
    # 2) 未列明工件（dist 实际必须全在 manifest——双向相等——蓝图）
    for name in actual:
        if name not in expected:
            failures.append(f"未列明工件（应拒绝——dist 与 manifest 双向相等）: {name}")
    return failures


def main() -> int:
    if len(sys.argv) < 3:
        print("用法: verify_artifact_set.py <dist_dir> <manifest.json>")
        return 2
    dist_dir = Path(sys.argv[1])
    manifest = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
    failures = verify_artifact_set(dist_dir, manifest)
    if failures:
        for f in failures:
            print(f"❌ {f}")
        print("发布验证失败——终止发布（fail-closed——阶段 E 完成标准）")
        return 1
    print("✅ 逐工件闭合验证通过（双向集合相等——缺失/哈希不符/未列明均拒绝）")
    return 0


if __name__ == "__main__":
    sys.exit(main())

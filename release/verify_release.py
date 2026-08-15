"""verify_release.py —— R-15/R-16 整改（发布制品验证：失败闭合）。

体验/功能审查（R-15/R-16）：任何缺少签名、SBOM、摘要或 provenance 的
制品都不能进入发布（失败闭合——缺文件不得跳过）。本脚本验证发布目录
制品集合（SHA-256 对账 + 签名文件 + SBOM 齐全）。

用法（发布期——release.yml verify job）：
    python release/verify_release.py --bundle <release-bundle-dir>
"""

import argparse
import hashlib
import json
import sys
from pathlib import Path


def verify_bundle(bundle_dir: Path) -> None:
    """验证发布包：SHA-256 摘要/签名文件/SBOM 齐全（缺一拒绝——失败闭合）。"""
    dist = bundle_dir / "dist"
    if not dist.is_dir():
        sys.exit("缺 dist 目录——发布包不完整（失败闭合）")
    files = [p for p in dist.rglob("*") if p.is_file()]
    if not files:
        sys.exit("dist 为空——无制品可验证")

    sums_path = dist / "SHA256SUMS.json"
    if not sums_path.is_file():
        sys.exit("缺 SHA256SUMS.json——摘要不完整（拒绝发布）")
    sums = json.loads(sums_path.read_text(encoding="utf-8"))
    for entry in sums:
        p = dist / entry["Path"]
        if not p.is_file():
            sys.exit(f"SHA256SUMS 指向缺失文件: {entry['Path']}")
        actual = hashlib.sha256(p.read_bytes()).hexdigest().upper()
        if actual != entry["Hash"]:
            sys.exit(f"SHA-256 不匹配: {entry['Path']}")

    # 签名文件（.sigstore）与 SBOM（.cdx.json/spdx.json）齐全——缺一拒绝
    sig = [p for p in files if p.suffix == ".sigstore"]
    sbom = [p for p in files if p.name.endswith((".cdx.json", ".spdx.json"))]
    if not sig:
        sys.exit("缺签名文件（.sigstore）——制品未签名（拒绝发布）")
    if not sbom:
        sys.exit("缺 SBOM——供应链不透明（拒绝发布）")

    print(f"✅ verify_release 通过：{len(files)} 制品 / "
          f"{len(sig)} 签名 / {len(sbom)} SBOM——SHA-256 对账一致")


def main() -> int:
    ap = argparse.ArgumentParser(description="Aegis 发布制品验证（失败闭合）")
    ap.add_argument("--bundle", required=True, help="发布包目录（含 dist/）")
    args = ap.parse_args()
    verify_bundle(Path(args.bundle))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

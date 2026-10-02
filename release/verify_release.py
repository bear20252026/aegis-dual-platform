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
import re
import sys
from pathlib import Path

# PY-208（2026-09-26 审计）：`from verify_checksum_json import ...` 平铺导入
# 仅在以脚本方式从 release/ 目录运行时才生效（cwd/sys.path 依赖）——CI 或
# 其他工作目录下调用即 ImportError。改 sys.path.insert 锚定到本文件所在
# release/ 目录（同 release/tools/verify_manifest.py:18 的模式）。
sys.path.insert(0, str(Path(__file__).resolve().parent))
from verify_checksum_json import verify_manifest

# PY-199（2026-09-26 审计）：build_metadata.py 本地运行时写入的降级哨兵——
# 一旦本脚本接线，truthy 的哨兵值会被当有效溯源证据通过（证据弱化）。
# 校验侧显式拒绝（与写侧字面量保持同步；写侧见 release/build_metadata.py）。
LOCAL_UNVERIFIED_SENTINEL = "local-unverified"


def _verify_checksum_txt(dist: Path, txt_path: Path) -> int:
    """PY-225（2026-10-01 审计）：core 平台 SHA256SUMS.txt 逐行强校验。

    此前回退路径只数非空行（`sum(1 for line ...)`）——伪造清单一行
    任意文本即过门禁（校验弱）。现对齐 sha256sum 文本格式做三重对账：
    ① 逐行 `<64 位十六进制哈希>␣␣<文件>` 解析（格式非法即拒）；
    ② 每条目 hashlib 重算真实文件哈希比对（防清单与内容脱节）；
    ③ 文件集双向对账（dist 实际文件 ⊖ 清单条目均为失败——缺列/幽灵
       均拒；清单自身与已由 JSON 路径排除的口径一致——自排除）。
    返回受摘要覆盖的条目数（空清单在上游即拒）。
    """
    checksums: dict[str, str] = {}
    for lineno, raw in enumerate(txt_path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw.rstrip("\r")
        if not line.strip():
            continue
        match = re.fullmatch(r"([0-9a-fA-F]{64}) {2}(.+)", line)
        if not match:
            sys.exit(f"SHA256SUMS.txt 第 {lineno} 行格式无效"
                     f"（须为 '<64 位哈希>␣␣<文件>'——sha256sum 文本格式）: {line!r}")
        rel, digest = match.group(2), match.group(1).lower()
        # SP-221（2026-10-01 发布链批 3）：归一化 sha256sum 两种实际形态——
        # `cd dist && sha256sum *` 产裸名、`find -print0 | xargs sha256sum`
        # 产 "./" 前缀（release-core.yml 重生成命令实证）；不归一则 ③ 文件集
        # 对账把每个 "./x" 条目与实际名 "x" 判为不一致，全量误拒。
        rel = rel.replace("\\", "/").removeprefix("./")
        target = (dist / rel).resolve()
        if target != dist.resolve() and not target.is_relative_to(dist.resolve()):
            sys.exit(f"SHA256SUMS.txt 条目越出发布根: {rel}（拒绝发布）")
        if rel in checksums:
            sys.exit(f"SHA256SUMS.txt 重复条目: {rel}（拒绝发布）")
        checksums[rel] = digest
    if not checksums:
        sys.exit("SHA256SUMS.txt 为空——摘要不完整（拒绝发布）")
    # ② 哈希重算比对
    for rel, digest in checksums.items():
        target = dist / rel
        if not target.is_file():
            sys.exit(f"SHA256SUMS.txt 条目文件缺失: {rel}（拒绝发布）")
        actual = hashlib.sha256(target.read_bytes()).hexdigest()
        if actual != digest:
            sys.exit(f"SHA256SUMS.txt 哈希不符: {rel}（清单 {digest[:12]}… vs 实际 {actual[:12]}…——拒绝发布）")
    # ③ 文件集双向对账（清单自身自排除——与 CI 生成口径一致）。
    # SP-221：排除比较须同侧归一——rglob 产出相对路径（dist 传相对路径时）
    # 而右侧是 resolve() 绝对路径，恒不等导致清单自身落入 unlisted 误拒。
    actual_files = {
        p.relative_to(dist).as_posix()
        for p in dist.rglob("*")
        if p.is_file() and p.resolve() != txt_path.resolve()
    }
    unlisted = sorted(actual_files - set(checksums))
    if unlisted:
        sys.exit(f"dist 存在未列入 SHA256SUMS.txt 的文件: {', '.join(unlisted)}（拒绝发布）")
    return len(checksums)


def verify_bundle(bundle_dir: Path) -> None:
    """验证发布包：版本元数据、SHA-256 摘要、签名文件和 SBOM 齐全。"""
    # RS-N1 配套（2026-09-26 审计）：release.yml verify-gate 传的是平台平铺
    # 目录（dist/<platform>，内含 build-metadata.json）——兼容两种布局：
    # <bundle>/dist/（历史文档口径）与 <bundle> 本身即制品目录（CI 实际）。
    nested = bundle_dir / "dist"
    dist = nested if nested.is_dir() else bundle_dir
    if not dist.is_dir() or not any(dist.iterdir()):
        sys.exit("缺 dist 目录——发布包不完整（失败闭合）")
    files = [p for p in dist.rglob("*") if p.is_file()]
    if not files:
        sys.exit("dist 为空——无制品可验证")

    metadata_path = dist / "build-metadata.json"
    if not metadata_path.is_file():
        sys.exit("缺 build-metadata.json——制品无法关联版本与源提交（拒绝发布）")
    # PY-235（2026-10-01 审计）：坏 JSON 此前直接 traceback（json.JSONDecodeError
    # 原始栈）——发布门禁须给出干净报告并失败闭合，不裸抛。
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, UnicodeDecodeError) as exc:
        sys.exit(f"build-metadata.json 无法解析: {exc}（拒绝发布）")
    if not isinstance(metadata, dict):
        sys.exit("build-metadata.json 顶层必须是对象（拒绝发布）")
    required_metadata = ("schema_version", "product", "platform", "version_name", "source_revision", "source_ref")
    missing_metadata = [key for key in required_metadata if not metadata.get(key)]
    if metadata.get("schema_version") != 1 or missing_metadata:
        sys.exit(f"构建元数据无效或缺字段: {', '.join(missing_metadata)}")
    # PY-199：哨兵值显式拒绝（fail-closed）——本地补建的 build-metadata.json
    # 携带 "local-unverified" 溯源占位，不得作为发布证据通过验证
    sentinel_fields = sorted(
        key for key in ("source_revision", "source_ref", "workflow_run_id")
        if metadata.get(key) == LOCAL_UNVERIFIED_SENTINEL
    )
    if sentinel_fields:
        sys.exit(
            "构建元数据含本地未验证哨兵值 "
            f"'{LOCAL_UNVERIFIED_SENTINEL}'（字段: {', '.join(sentinel_fields)}）"
            "——缺 CI 溯源证据，拒绝发布")

    sums_path = dist / "SHA256SUMS.json"
    txt_path = dist / "SHA256SUMS.txt"
    if sums_path.is_file():
        checksum_count = verify_manifest(dist, sums_path)
    elif txt_path.is_file():
        # core 平台产物为纯 .txt 清单（无 per-file JSON manifest）——
        # PY-225：逐行 `<hash>␣␣<file>` 解析 + 哈希重算 + 文件集对账
        #（CI: release-core.yml 只产 SHA256SUMS.txt——sha256sum 文本格式）
        checksum_count = _verify_checksum_txt(dist, txt_path)
    else:
        sys.exit("缺 SHA256SUMS.json——摘要不完整（拒绝发布）")

    # 签名证据模型（PY-009 整改 2026-09-24）：本仓库发布链的签名 =
    # GitHub artifact attestations（Sigstore 背书）——由 release.yml
    # verify-gate 的 `gh attestation verify`（SLSA provenance + SBOM 双
    # predicate）在 CI 内逐工件校验，不在 bundle 内产出 .sigstore 旁路文件
    # （原断言要求 .sigstore——链路不产出、工具零调用，属死门禁）。
    # bundle 级保留 SBOM 齐全断言（供应链透明）。
    sbom = [p for p in files if p.name.endswith((".cdx.json", ".spdx.json"))]
    if not sbom:
        sys.exit("缺 SBOM——供应链不透明（拒绝发布）")

    print(f"✅ verify_release 通过：{metadata['platform']} v{metadata['version_name']} / {checksum_count} 个受摘要覆盖制品 / "
          f"签名经 gh attestation（release.yml verify-gate 校验）/ {len(sbom)} SBOM——SHA-256 对账一致")


def main() -> int:
    ap = argparse.ArgumentParser(description="Aegis 发布制品验证（失败闭合）")
    ap.add_argument("--bundle", required=True, help="发布包目录（含 dist/）")
    args = ap.parse_args()
    verify_bundle(Path(args.bundle))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""verify_artifact_set.py —— 阶段 E（蓝图 release/tools/verify_artifact_set）：
逐工件闭合验证（fail-closed——不允许截断/忽略——蓝图阶段 E 完成标准）。

按调研（gh attestation verify 逐工件官方 + 张显达"部署侧强制校验失败即阻断——
证据包"）：对 dist/ 全部工件与 manifest 做双向集合相等检查（缺失/多余/哈希
不符 → 非零退出终止发布）。任何验证失败返回非零（release.yml 门禁）。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import urllib.parse
from pathlib import Path

# PY-280：SHA-256 hex 形态锚定（64 位十六进制——此前只验长度）
_SHA256_HEX = re.compile(r"[0-9a-fA-F]{64}")


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def verify_artifact_set(dist_dir: Path, manifest: dict) -> list[str]:
    """双向集合相等：manifest 枚举的每个工件必须存在且哈希相符；
    dist 实际工件必须全部在 manifest 中（未列明工件拒绝——蓝图）。

    PY-024：此前以纯 basename 为键——跨平台同名制品互相覆盖静默漏验；
    实际枚举只扫顶层——子目录工件被静默跳过。现改：
    - basename 唯一时直配；同名冲突按 platform 与所在目录名消歧
      （manifest 平台命名 windows-x64 与 dist 目录命名 windows 可能不同——
      消歧不依赖完全相等，冲突且无法消歧即失败，不猜）；
    - 枚举改 rglob 递归（dist/latest-release/ 等子目录全部纳入）。
    """
    failures: list[str] = []
    manifest_artifacts = manifest.get("artifacts") or []
    if not isinstance(manifest_artifacts, list):
        failures.append("manifest.artifacts 不是数组")
        return failures

    expected: list[tuple[str, str, str]] = []  # (platform, basename, sha256)
    for art in manifest_artifacts:
        if not isinstance(art, dict):
            failures.append("manifest.artifacts 含非对象条目")
            continue
        url = art.get("url") if isinstance(art.get("url"), str) else ""
        # PY-210（2026-09-26 审计）：url.split("/")[-1] 不做百分号解码——
        # Release browser_url 对含空格/中文等字符的资产名是 percent-encoded
        #（如 a%20b.zip），与本地文件名 a b.zip 不匹配 → 恒报"缺失工件"。
        # 取尾段后再 unquote 对齐本地名。
        rel = urllib.parse.unquote(url.split("/")[-1]) if url else ""
        platform = art.get("platform", "") if isinstance(art.get("platform"), str) else ""
        sha = art.get("sha256", "")
        # PY-280（2026-10-02 审计）：sha 此前只验长度不验 hex——64 个任意
        # 字符（如 "g"*64 / 空白填充）会被当有效哈希入账，对账必然「哈希
        # 不符」但报错误导读。fullmatch 十六进制形态后，非 hex 直接判
        # 无效条目（与 release workflow 侧 sha256sum 产物口径一致）
        if rel and platform and isinstance(sha, str) and _SHA256_HEX.fullmatch(sha):
            expected.append((platform, rel, sha.lower()))
        else:
            failures.append(f"manifest 工件条目无效: {art}")

    actual: dict[str, list[Path]] = {}  # basename -> 全部路径（递归）
    if dist_dir.is_dir():
        for p in sorted(dist_dir.rglob("*")):
            if p.is_file():
                actual.setdefault(p.name, []).append(p)

    # SP-144（2026-09-26 审计）：空集恒真退化——manifest 未枚举任何工件或
    # dist 未枚举任何文件时，此前 failures=[] 会打印"全部通过"（门禁恒真）。
    # "逐工件闭合 fail-closed"要求：任一侧空集即判定失败（不提前返回——
    # 继续走下方逐项对账，保留缺失/多余明细）。
    if not expected:
        failures.append("manifest 未枚举任何工件（空集——fail-closed，SP-144）")
    if not actual:
        failures.append(f"dist 未枚举任何工件（目录缺失或为空: {dist_dir}——fail-closed，SP-144）")

    consumed: set[Path] = set()
    # 1) manifest 枚举必须全部存在且相符
    for platform, rel, sha in expected:
        candidates = actual.get(rel, [])
        if not candidates:
            failures.append(f"缺失工件: {platform}/{rel}")
            continue
        if len(candidates) == 1:
            chosen = candidates[0]
        else:
            # 跨平台同名：按 platform 前缀与所在目录名匹配（大小写不敏感、
            # 前缀容差 windows-x64↔windows）；无法唯一消歧即失败（不猜）
            plat = platform.lower().replace("-universal", "").replace("-x64", "")
            hits = [c for c in candidates
                    if c.parent.relative_to(dist_dir).parts
                    and c.parent.relative_to(dist_dir).parts[0].lower().startswith(plat.split("-")[0])]
            chosen = hits[0] if len(hits) == 1 else None
            if chosen is None:
                failures.append(f"同名制品无法按平台消歧: {platform}/{rel}")
                continue
        consumed.add(chosen)
        if _sha256(chosen) != sha:
            failures.append(f"哈希不符: {platform}/{rel}")
    # 2) 未列明工件（dist 实际必须全在 manifest——双向相等——蓝图）
    for paths in actual.values():
        for p in paths:
            if p not in consumed:
                failures.append(f"未列明工件（应拒绝——dist 与 manifest 双向相等）: {p.name}")
    return failures


def _parse_args(argv: list[str]) -> argparse.Namespace:
    """PY-286（2026-10-02 审计）：手工 argv 索引改 argparse——必填 positional
    缺参自动 exit 2（0/1/2 退出码语义不变：用法/环境 2、验证失败 1、通过 0）。"""
    parser = argparse.ArgumentParser(
        description="逐工件闭合验证（dist 与 manifest 双向集合相等——fail-closed）")
    parser.add_argument("dist_dir", type=Path, help="dist 制品目录")
    parser.add_argument("manifest", type=Path, help="manifest.json（工件枚举）")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    # SP-155（2026-09-26 审计）：main() 对 manifest JSON json.loads 无异常
    # 处理——坏 JSON 直接 traceback 替代干净报告。包 try/except：exit 2 +
    # 文件名上下文（与环境错误同一退出码语义）。
    try:
        manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        print(f"❌ manifest 读取/解析失败: {args.manifest.name}（{exc}）")
        return 2
    failures = verify_artifact_set(args.dist_dir, manifest)
    if failures:
        for f in failures:
            print(f"❌ {f}")
        print("发布验证失败——终止发布（fail-closed——阶段 E 完成标准）")
        return 1
    print("✅ 逐工件闭合验证通过（双向集合相等——缺失/哈希不符/未列明均拒绝）")
    return 0


if __name__ == "__main__":
    sys.exit(main())

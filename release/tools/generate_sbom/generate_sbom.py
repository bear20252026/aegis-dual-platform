#!/usr/bin/env python3
"""generate_sbom.py —— 阶段 E（蓝图 release/tools/generate_sbom）：
SBOM 生成（CycloneDX——随制品存档——张显达可信交付实践 + 蓝图阶段 E）。

从 manifest 工件枚举生成 CycloneDX JSON（bomFormat: CycloneDX——component/
artifacts——sha256）——随发布制品存档（签名 + SHA256SUMS——BAUER 实践）。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from urllib.parse import unquote


def generate_sbom(manifest: dict) -> dict:
    components = []
    for art in manifest.get("artifacts") or []:
        if not isinstance(art, dict):
            continue
        # PY-226（2026-10-01 审计）：Release browser_url 对含空格/非 ASCII 的
        # 资产名是 percent-encoded——此前不 unquote 直接取尾段，"a%20b.zip"
        # 会作为字面 "a%20b.zip" 进 SBOM，与 verify_artifact_set 的本地文件名
        # 对账必失败。与 PY-210 同款 unquote 后取尾段。
        name = unquote(str(art.get("url", ""))).split("/")[-1] or "artifact"
        components.append({
            "type": "file",
            "name": name,
            "hashes": [{"alg": "SHA-256", "content": art.get("sha256", "")}],
            "properties": [
                {"name": "aegis:platform", "value": art.get("platform", "")},
                {"name": "aegis:format", "value": art.get("format", "")},
            ],
        })
    return {
        "bomFormat": "CycloneDX",
        "specVersion": "1.6",
        "version": 1,
        "components": components,
    }


def _parse_args(argv: list[str]) -> argparse.Namespace:
    """PY-286（2026-10-02 审计）：手工 argv 索引改 argparse——必填 positional
    缺参自动 exit 2（0/2 退出码语义不变：用法/环境错误 2、生成成功 0）。"""
    parser = argparse.ArgumentParser(
        description="SBOM 生成（CycloneDX JSON——随制品存档）")
    parser.add_argument("manifest", type=Path, help="manifest.json（工件枚举）")
    parser.add_argument("output", type=Path, help="输出 *.cdx.json 路径")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    # SP-155（2026-09-26 审计）：main() 对 manifest JSON json.loads 无异常
    # 处理——坏 JSON 直接 traceback。包 try/except：exit 2 + 文件名上下文。
    try:
        manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        print(f"❌ manifest 读取/解析失败: {args.manifest.name}（{exc}）")
        return 2
    sbom = generate_sbom(manifest)
    # PY-268（2026-10-02 审计）：newline="\n" 锁 LF——Windows 默认把 \n 翻译
    # 为 CRLF，SBOM 作为发布产物在 autocrlf 关闭的环境即行尾漂移
    args.output.write_text(
        json.dumps(sbom, indent=2, ensure_ascii=False), encoding="utf-8", newline="\n")
    print(f"✅ SBOM 生成（CycloneDX——{len(sbom['components'])} 个工件）: {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

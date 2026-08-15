#!/usr/bin/env python3
"""generate_sbom.py —— 阶段 E（蓝图 release/tools/generate_sbom）：
SBOM 生成（CycloneDX——随制品存档——张显达可信交付实践 + 蓝图阶段 E）。

从 manifest 工件枚举生成 CycloneDX JSON（bomFormat: CycloneDX——component/
artifacts——sha256）——随发布制品存档（签名 + SHA256SUMS——BAUER 实践）。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def generate_sbom(manifest: dict) -> dict:
    components = []
    for art in manifest.get("artifacts") or []:
        if not isinstance(art, dict):
            continue
        name = str(art.get("url", "")).split("/")[-1] or "artifact"
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


def main() -> int:
    if len(sys.argv) < 3:
        print("用法: generate_sbom.py <manifest.json> <output.cdx.json>")
        return 2
    manifest = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    sbom = generate_sbom(manifest)
    Path(sys.argv[2]).write_text(
        json.dumps(sbom, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"✅ SBOM 生成（CycloneDX——{len(sbom['components'])} 个工件）: {sys.argv[2]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

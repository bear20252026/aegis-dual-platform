"""以稳定 JSON 结构生成发布目录的 SHA-256 清单。"""

import argparse
import hashlib
import json
from pathlib import Path


def build_manifest(root: Path, output: Path) -> list[dict[str, str]]:
    output_relative = output.relative_to(root)
    entries = []
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        relative = path.relative_to(root)
        if relative == output_relative:
            continue
        entries.append(
            {
                "Hash": hashlib.sha256(path.read_bytes()).hexdigest().upper(),
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
    output.write_text(json.dumps(build_manifest(root, output), indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

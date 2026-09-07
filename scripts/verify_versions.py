from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# 平铺导入兜底：脱离 scripts/ 工作目录（如 CI 从仓库根调用）也能导入同目录模块。
sys.path.insert(0, str(Path(__file__).resolve().parent))

from sync_versions import ROOT, load_properties


def expected_xml_value(text: str, element: str) -> str | None:
    match = re.search(rf"<\s*{re.escape(element)}\s*>([^<]+)</\s*{re.escape(element)}\s*>", text)
    return match.group(1).strip() if match else None


def expected_assignment(text: str, name: str) -> str | None:
    match = re.search(rf"(?m)^\s*{re.escape(name)}\s*=\s*(?:\"([^\"]+)\"|(\d+))\s*$", text)
    return (match.group(1) or match.group(2)) if match else None


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify Aegis cross-platform version declarations")
    parser.add_argument("--tag", help="Release tag that must equal vVERSION_NAME")
    args = parser.parse_args()

    values = load_properties(ROOT / "shared" / "version.properties")
    android_text = (ROOT / "android" / "app" / "build.gradle.kts").read_text(encoding="utf-8")
    windows_text = (ROOT / "windows" / "src" / "Aegis.Windows.App" / "Aegis.Windows.App.csproj").read_text(encoding="utf-8")
    # 审计修复：不再校验已死的 Python 时代 AegisSetup.iss——改为校验
    # shared/release.json（此前完全无门禁，漂移三个大版本未被发现）
    release_json = json.loads((ROOT / "shared" / "release.json").read_text(encoding="utf-8"))
    expected = {
        "Android versionCode": (expected_assignment(android_text, "versionCode"), values["VERSION_CODE"]),
        "Android versionName": (expected_assignment(android_text, "versionName"), values["VERSION_NAME"]),
        "Windows Version": (expected_xml_value(windows_text, "Version"), values["VERSION_NAME"]),
        "Windows AssemblyVersion": (expected_xml_value(windows_text, "AssemblyVersion"), values["WINDOWS_PACKAGE_VERSION"]),
        "Windows FileVersion": (expected_xml_value(windows_text, "FileVersion"), values["WINDOWS_PACKAGE_VERSION"]),
        "Windows PackageId": (expected_xml_value(windows_text, "PackageId"), values["WINDOWS_PACKAGE_IDENTITY"]),
        "Windows Product": (expected_xml_value(windows_text, "Product"), values["DISPLAY_NAME"]),
        "release.json version": (release_json.get("version"), values["VERSION_NAME"]),
        "release.json versionCode": (release_json.get("versionCode"), int(values["VERSION_CODE"])),
    }
    failures = [f"{label}: found {actual!r}, expected {wanted!r}" for label, (actual, wanted) in expected.items() if actual != wanted]
    if args.tag and args.tag != f"v{values['VERSION_NAME']}":
        failures.append(f"Release tag: found {args.tag!r}, expected 'v{values['VERSION_NAME']}'")

    if failures:
        print("Version verification failed:", *failures, sep="\n- ")
        return 1
    print(f"Version verification passed: v{values['VERSION_NAME']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

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
    iss_text = (ROOT / "docs" / "release" / "AegisSetup.iss").read_text(encoding="utf-8")
    iss_version = re.search(r'(?m)^#define MyAppVersion "([^"]+)"', iss_text)
    expected = {
        "Android versionCode": (expected_assignment(android_text, "versionCode"), values["VERSION_CODE"]),
        "Android versionName": (expected_assignment(android_text, "versionName"), values["VERSION_NAME"]),
        "Windows Version": (expected_xml_value(windows_text, "Version"), values["VERSION_NAME"]),
        "Windows AssemblyVersion": (expected_xml_value(windows_text, "AssemblyVersion"), values["WINDOWS_PACKAGE_VERSION"]),
        "Windows FileVersion": (expected_xml_value(windows_text, "FileVersion"), values["WINDOWS_PACKAGE_VERSION"]),
        "Windows PackageId": (expected_xml_value(windows_text, "PackageId"), values["WINDOWS_PACKAGE_IDENTITY"]),
        "Windows Product": (expected_xml_value(windows_text, "Product"), values["DISPLAY_NAME"]),
        "Windows Installer MyAppVersion": (iss_version.group(1) if iss_version else None, values["VERSION_NAME"]),
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

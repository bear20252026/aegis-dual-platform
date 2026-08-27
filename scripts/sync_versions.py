from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROPS = ROOT / "shared" / "version.properties"


def load_properties(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def replace_assignment(path: Path, name: str, value: str, quoted: bool) -> None:
    text = path.read_text(encoding="utf-8")
    assignment = f'{name} = "{value}"' if quoted else f"{name} = {value}"
    pattern = rf"(?m)^(?P<indent>[ \t]*){re.escape(name)}\s*=\s*(?:\"[^\"]*\"|\d+)\s*$"
    updated, count = re.subn(pattern, rf"\g<indent>{assignment}", text, count=1)
    if count != 1:
        raise RuntimeError(f"expected {name} assignment not found in {path}")
    path.write_text(updated, encoding="utf-8")


def replace_xml_value(path: Path, element: str, value: str) -> None:
    text = path.read_text(encoding="utf-8")
    pattern = rf"(?m)(<\s*{re.escape(element)}\s*>)[^<]*(</\s*{re.escape(element)}\s*>)"
    updated, count = re.subn(pattern, rf"\g<1>{value}\g<2>", text, count=1)
    if count != 1:
        raise RuntimeError(f"expected <{element}> element not found in {path}")
    path.write_text(updated, encoding="utf-8")


def main() -> None:
    values = load_properties(PROPS)
    required = (
        "VERSION_NAME",
        "VERSION_CODE",
        "WINDOWS_PACKAGE_VERSION",
        "WINDOWS_PACKAGE_IDENTITY",
        "DISPLAY_NAME",
    )
    missing = [key for key in required if not values.get(key)]
    if missing:
        raise RuntimeError(f"missing version properties: {', '.join(missing)}")

    android_gradle = ROOT / "android" / "app" / "build.gradle.kts"
    replace_assignment(android_gradle, "versionCode", values["VERSION_CODE"], quoted=False)
    replace_assignment(android_gradle, "versionName", values["VERSION_NAME"], quoted=True)

    windows_project = ROOT / "windows" / "src" / "Aegis.Windows.App" / "Aegis.Windows.App.csproj"
    replace_xml_value(windows_project, "Version", values["VERSION_NAME"])
    replace_xml_value(windows_project, "AssemblyVersion", values["WINDOWS_PACKAGE_VERSION"])
    replace_xml_value(windows_project, "FileVersion", values["WINDOWS_PACKAGE_VERSION"])
    replace_xml_value(windows_project, "PackageId", values["WINDOWS_PACKAGE_IDENTITY"])
    replace_xml_value(windows_project, "Product", values["DISPLAY_NAME"])

    print("Version declarations synchronized from shared/version.properties")


if __name__ == "__main__":
    main()

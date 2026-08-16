from __future__ import annotations

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


def replace_exact(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    if old not in text:
        raise RuntimeError(f"expected text not found in {path}: {old}")
    path.write_text(text.replace(old, new), encoding="utf-8")


def main() -> None:
    values = load_properties(PROPS)
    android_gradle = ROOT / "android" / "app" / "build.gradle.kts"
    replace_exact(android_gradle, 'versionCode = 20106', f'versionCode = {values["VERSION_CODE"]}')
    replace_exact(android_gradle, 'versionName = "2.1.6"', f'versionName = "{values["VERSION_NAME"]}"')

    print("Version declarations synchronized from shared/version.properties")


if __name__ == "__main__":
    main()

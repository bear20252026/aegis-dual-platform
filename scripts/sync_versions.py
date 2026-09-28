from __future__ import annotations

import json
import re
from pathlib import Path
from xml.sax.saxutils import escape  # PY-186：XML 文本转义单源（& < >）

ROOT = Path(__file__).resolve().parents[1]
PROPS = ROOT / "shared" / "version.properties"


def load_properties(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for lineno, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        # PY-026：无 "=" 的非法行此前直接 ValueError 原始栈——给出文件与行号
        if "=" not in line:
            raise RuntimeError(f"{path}:{lineno}: invalid properties line (missing '='): {line!r}")
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
    # PY-186（2026-09-26 审计）：属性/文本值此前经 rf"\g<1>{value}\g<2>" 原样
    # 拼接——DISPLAY_NAME 含 &/< 会生成非法 csproj；含 \1 会被当正则反向引用
    # 解析（re.error 或静默错位）。改为：① escape() 做 XML 文本转义；
    # ② 函数式替换（lambda）——替换串不再经过 backslash 模板解析。
    escaped = escape(value)
    updated, count = re.subn(
        pattern, lambda m: m.group(1) + escaped + m.group(2), text, count=1)
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

    # PY-198（2026-09-26 审计）：VERSION_CODE 此前在下方 int() 处才炸——
    # 非数字值给原始 ValueError 栈。载入后即校验 isdigit，失败汇总报错
    #（当前数值型键仅 VERSION_CODE；将来扩展逐键加入即可）。
    non_numeric = [key for key in ("VERSION_CODE",)
                   if not str(values.get(key, "")).isdigit()]
    if non_numeric:
        raise RuntimeError(
            "version properties must be numeric: "
            + ", ".join(f"{key}={values.get(key)!r}" for key in non_numeric))

    android_gradle = ROOT / "android" / "app" / "build.gradle.kts"
    replace_assignment(android_gradle, "versionCode", values["VERSION_CODE"], quoted=False)
    replace_assignment(android_gradle, "versionName", values["VERSION_NAME"], quoted=True)

    windows_project = ROOT / "windows" / "src" / "Aegis.Windows.App" / "Aegis.Windows.App.csproj"
    replace_xml_value(windows_project, "Version", values["VERSION_NAME"])
    replace_xml_value(windows_project, "AssemblyVersion", values["WINDOWS_PACKAGE_VERSION"])
    replace_xml_value(windows_project, "FileVersion", values["WINDOWS_PACKAGE_VERSION"])
    replace_xml_value(windows_project, "PackageId", values["WINDOWS_PACKAGE_IDENTITY"])
    replace_xml_value(windows_project, "Product", values["DISPLAY_NAME"])

    # 审计修复：不再同步已死的 Python 时代 AegisSetup.iss（C# 安装器版本由
    # CI 运行时 /D 注入，无写死版本）——改为同步 shared/release.json
    #（此前 sync 不覆盖该文件，漂移无门禁）
    release_json_path = ROOT / "shared" / "release.json"
    release_json = json.loads(release_json_path.read_text(encoding="utf-8"))
    release_json["version"] = values["VERSION_NAME"]
    release_json["versionCode"] = int(values["VERSION_CODE"])
    release_json_path.write_text(json.dumps(release_json, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print("Version declarations synchronized from shared/version.properties")


if __name__ == "__main__":
    main()

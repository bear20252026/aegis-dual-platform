from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from xml.sax.saxutils import unescape as xml_unescape

# 平铺导入兜底：脱离 scripts/ 工作目录（如 CI 从仓库根调用）也能导入同目录模块。
sys.path.insert(0, str(Path(__file__).resolve().parent))

from sync_versions import ROOT, load_properties


def expected_xml_value(text: str, element: str) -> str | None:
    match = re.search(rf"<\s*{re.escape(element)}\s*>([^<]+)</\s*{re.escape(element)}\s*>", text)
    if not match:
        return None
    # PY-223（2026-10-01 审计）：XML 文本节点取值不反转义——csproj 由
    # sync_versions.escape() 写入，DISPLAY_NAME 含 & 时磁盘值是 "&amp;"
    # 而单源值是 "&"，逐位比较必报漂移（写入合法、校验误报）。
    # 与写侧 escape() 对偶做 unescape 还原后再比较（&amp;/&lt;/&gt;/
    # &apos;/&quot;——写侧 escape() 默认全集）。
    return xml_unescape(match.group(1).strip())


def expected_assignment(text: str, name: str) -> str | None:
    match = re.search(rf"(?m)^\s*{re.escape(name)}\s*=\s*(?:\"([^\"]+)\"|(\d+))\s*$", text)
    return (match.group(1) or match.group(2)) if match else None


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify Aegis cross-platform version declarations")
    parser.add_argument("--tag", help="Release tag that must equal vVERSION_NAME")
    args = parser.parse_args()

    # PY-028：缺文件给明确报错（此前 FileNotFoundError 原始栈——版本.properties
    # 缺失是常见的新人克隆后未初始化场景）
    inputs = {
        "shared/version.properties": ROOT / "shared" / "version.properties",
        "android/app/build.gradle.kts": ROOT / "android" / "app" / "build.gradle.kts",
        "windows .../Aegis.Windows.App.csproj": ROOT / "windows" / "src" / "Aegis.Windows.App" / "Aegis.Windows.App.csproj",
        "shared/release.json": ROOT / "shared" / "release.json",
    }
    for label, path in inputs.items():
        if not path.is_file():
            print(f"Version verification failed: required file missing: {label} ({path})")
            return 1

    values = load_properties(inputs["shared/version.properties"])
    # PY-027：必需键缺失给 required/missing 汇总（此前 8 处 values["..."] 下标
    # KeyError 原始栈，一次只暴露一个键且无上下文）
    required = ("VERSION_NAME", "VERSION_CODE", "WINDOWS_PACKAGE_VERSION",
                "WINDOWS_PACKAGE_IDENTITY", "DISPLAY_NAME")
    missing = [key for key in required if not values.get(key)]
    if missing:
        print("Version verification failed: missing version properties:", *missing, sep="\n- ")
        return 1

    # PY-198（2026-09-26 审计）：VERSION_CODE 非数字时此前在下方 int() 处
    # 原始 ValueError 栈——载入后即校验 isdigit，纳入汇总报错（与
    # sync_versions 同口径）。
    if not str(values["VERSION_CODE"]).isdigit():
        print("Version verification failed:",
              f"VERSION_CODE must be numeric, found {values['VERSION_CODE']!r}",
              sep="\n- ")
        return 1

    android_text = inputs["android/app/build.gradle.kts"].read_text(encoding="utf-8")
    windows_text = inputs["windows .../Aegis.Windows.App.csproj"].read_text(encoding="utf-8")
    # 审计修复：不再校验已死的 Python 时代 AegisSetup.iss——改为校验
    # shared/release.json（此前完全无门禁，漂移三个大版本未被发现）
    release_json = json.loads(inputs["shared/release.json"].read_text(encoding="utf-8"))
    # SP1 批跟进（审计 2026-09-23 清单；A6 批 AD-100 配套）：Android 版本
    # 已单源迁移——build.gradle.kts 构建期读取 shared/version.properties
    #（versionNameFromProperties/versionCodeFromProperties），字面量断言失效。
    # 改校验单源接线本身：①defaultConfig 必须消费 properties 派生值；
    # ②不得残留硬编码字面量（防双源回潮）；③本文件已在读取同一
    # version.properties（values 即单源值），接线正确则三端必然一致。
    def android_version_wired(name: str) -> bool:
        return bool(re.search(
            rf"(?m)^\s*{re.escape(name)}\s*=\s*{re.escape(name)}FromProperties\s*$",
            android_text))

    def android_version_hardcoded(name: str) -> bool:
        return expected_assignment(android_text, name) is not None

    android_version_checks = [
        ("Android versionName wiring",
         android_version_wired("versionName") and not android_version_hardcoded("versionName"),
         True),
        ("Android versionCode wiring",
         android_version_wired("versionCode") and not android_version_hardcoded("versionCode"),
         True),
    ]

    expected = {
        "Android versionName": (
            android_version_checks[0][1], android_version_checks[0][2]),
        "Android versionCode": (
            android_version_checks[1][1], android_version_checks[1][2]),
        "Windows Version": (expected_xml_value(windows_text, "Version"), values["VERSION_NAME"]),
        "Windows AssemblyVersion": (expected_xml_value(windows_text, "AssemblyVersion"), values["WINDOWS_PACKAGE_VERSION"]),
        "Windows FileVersion": (expected_xml_value(windows_text, "FileVersion"), values["WINDOWS_PACKAGE_VERSION"]),
        "Windows PackageId": (expected_xml_value(windows_text, "PackageId"), values["WINDOWS_PACKAGE_IDENTITY"]),
        "Windows Product": (expected_xml_value(windows_text, "Product"), values["DISPLAY_NAME"]),
        "release.json version": (release_json.get("version"), values["VERSION_NAME"]),
        "release.json versionCode": (release_json.get("versionCode"), int(values["VERSION_CODE"])),
    }
    # PY-230（2026-10-01 审计）：ANDROID_APPLICATION_ID 此前零消费者（死键），
    # 真实值在 gradle 与 release.json 平行硬编码三处漂移无门禁。不改
    # shared/version.properties（发布事实源），在此把死键复活为三方对账
    # 单源：properties → gradle applicationId → release.json android.applicationId
    # 任一漂移即 fail（缺键不强制——保持既有 required 清单语义）。
    android_app_id = values.get("ANDROID_APPLICATION_ID")
    if android_app_id:
        expected["Android applicationId"] = (
            expected_assignment(android_text, "applicationId"), android_app_id)
        android_block = release_json.get("android")
        expected["release.json android.applicationId"] = (
            android_block.get("applicationId") if isinstance(android_block, dict) else None,
            android_app_id)
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

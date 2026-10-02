from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from xml.sax.saxutils import escape  # PY-186：XML 文本转义单源（& < >）

# PY-278（2026-10-02 审计）：原子写单源（同目录临时文件 + os.replace）——
# 本脚本此前两处直接 write_text，写入中断留半截 csproj/release.json
sys.path.insert(0, str(Path(__file__).resolve().parent))
from atomic_write import atomic_write_text

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


# PY-265（2026-10-02 审计）：删除 replace_assignment——PY-216 起 gradle 字面量
# 写入已移除（AD-100 构建期消费 properties），生产零调用（唯一消费方是
# sync_and_verify_test.py 的单测自身）。函数已迁入测试侧
#（tests/python/sync_and_verify_test.py——PY-224 反向引用回归仍受锁定）；
# verify_versions.expected_assignment 是独立的读侧提取器，不受影响。


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
    # PY-278：原子落盘（半截写入消除）+ LF 锁定（PY-232 口径）
    atomic_write_text(path, updated)


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

    # PY-216（2026-10-01 审计·P1）：删除 android gradle 的 versionCode/
    # versionName 字面量写入（此前两行 replace_assignment 对真实
    # build.gradle.kts 必抛 RuntimeError——AD-100 起 gradle 已构建期消费
    # shared/version.properties（versionCodeFromProperties/
    # versionNameFromProperties 单源接线），本脚本自 09-23 起不可用）。
    # Android 版本不再有第二写入面：properties 是唯一事实源，
    # verify_versions.py 校验接线本身（无字面量残留断言）。

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
    # PY-267（2026-10-02 审计）：release.json 缺失/损坏此前裸栈
    #（FileNotFoundError / json.JSONDecodeError traceback）——包守卫转
    # RuntimeError 带文件名（fail-fast 干净报告，与 PY-026 坏行口径同语义）
    try:
        release_json = json.loads(release_json_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"无法读取 {release_json_path}: {exc}") from exc
    release_json["version"] = values["VERSION_NAME"]
    release_json["versionCode"] = int(values["VERSION_CODE"])
    # PY-268/278：newline="\n" 锁 LF + 原子落盘（半截写入消除）
    atomic_write_text(
        release_json_path, json.dumps(release_json, indent=2, ensure_ascii=False) + "\n")

    print("Version declarations synchronized from shared/version.properties")


if __name__ == "__main__":
    main()

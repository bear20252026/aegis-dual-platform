"""verify_bridge_guard.py —— Bridge 守卫 JS 三端单一事实源校验（合并门禁）。

背景：守卫脚本曾在 Rust 与 Kotlin 各自手工维护一份，已经实际产生过
一次漂移（Kotlin 侧缺失 REQUIRE_HTTPS 段——fail-open 类 bug 的温床）。
ADR-007 起，规范模板唯一存于 contracts/schemas/bridge_guard.template.js：

- Rust：bridge_guard.rs 经 include_str! 编译期嵌入（消费规范文件本身）；
- Kotlin：WebViewHardening.kt 内嵌副本（重构 2026-09-03 自 SecureWebViewFactory.kt
  拆出，模板逐字节未变），占位符经 Kotlin 插值注入，
  本脚本做「占位符归一化 → 逐行比对」校验；
- C#：无注入 JS（走 WebView2 Settings 收紧路径），不在本门禁范围。

用法：python contracts/codegen/verify_bridge_guard.py（仓库根运行）
退出码：0 = 一致；1 = 漂移/缺失（CI 门禁失败）。
"""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CANONICAL = ROOT / "contracts" / "schemas" / "bridge_guard.template.js"
RUST = ROOT / "core" / "rust-policy-core" / "src" / "bridge_guard.rs"
KOTLIN = ROOT / "android" / "app" / "src" / "main" / "java" / "com" / "aegis" / "browser" / "WebViewHardening.kt"

# Kotlin 模板占位符 → 规范占位符（归一化映射）
KOTLIN_PLACEHOLDERS = {
    "[$allowedHostsJson]": "__AEGIS_HOSTS__",
    "$requireHttpsJson": "__AEGIS_REQUIRE_HTTPS__",
}

# PY-043：REQUIRED_SINKS 不再手工副本——自规范模板头部的机器可读注释解析
#（REQUIRED_SINKS: a|b|c 行）。模板是 Rust include_str! 编译期单源，
# 清单随模板演进自动同步；解析失败 fail-closed。
def _required_sinks_from_canonical(canonical_text: str) -> list[str]:
    for line in canonical_text.splitlines():
        if line.startswith("// REQUIRED_SINKS:"):
            payload = line[len("// REQUIRED_SINKS:"):].strip()
            sinks = [s.strip() for s in payload.split("|") if s.strip()]
            if sinks:
                return sinks
    return []


REQUIRED_SINKS_FALLBACK = [
    "window.fetch = function",
    "XMLHttpRequest.prototype.open",
    "navigator.sendBeacon = function",
    "window.WebSocket = function",
    "trustedCaller",
    "location.hostname",
]

failures: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    if not cond:
        failures.append(f"{name}: {detail}")


def norm(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


def main() -> int:
    if not CANONICAL.is_file():
        print(f"FAIL: 规范模板缺失: {CANONICAL}")
        return 1
    # PY-033：Rust/Kotlin 源缺失时此前 read_text 原始栈——与规范模板同口径显式拒绝
    for label, path in (("Rust 源", RUST), ("Kotlin 源", KOTLIN)):
        if not path.is_file():
            print(f"FAIL: {label}缺失: {path}")
            return 1
    canonical = norm(CANONICAL.read_text(encoding="utf-8"))

    # 1) 规范模板自检：占位符与安全属性齐备
    check("规范模板含 HOSTS 占位符", "__AEGIS_HOSTS__" in canonical)
    check("规范模板含 HTTPS 占位符", "__AEGIS_REQUIRE_HTTPS__" in canonical)
    # PY-043：REQUIRED_SINKS 自模板锚点行解析——锚点缺失视为模板漂移 fail-closed
    required_sinks = _required_sinks_from_canonical(canonical)
    if not required_sinks:
        check("规范模板含 REQUIRED_SINKS 锚点行", False, "锚点缺失——回退内置清单")
        required_sinks = REQUIRED_SINKS_FALLBACK
    for sink in required_sinks:
        check(f"规范模板含拦截点/属性: {sink}", sink in canonical)

    # 2) Rust：必须 include_str! 规范文件（编译期单源），禁止再内嵌 r#" 副本
    rust = norm(RUST.read_text(encoding="utf-8"))
    m = re.search(r'include_str!\(\s*"([^"]+)"\s*\)', rust)
    check("Rust 使用 include_str! 消费规范模板", m is not None)
    if m:
        rel = m.group(1)
        resolved = (RUST.parent / rel).resolve()
        check("Rust include 路径指向规范模板", resolved == CANONICAL.resolve(),
              f"resolved={resolved}")
    check("Rust 不再内嵌 r#\" 守卫副本", 'const SCRIPT: &str = r#"' not in rust)

    # 3) Kotlin：内嵌副本归一化后必须与规范逐行一致
    kt = KOTLIN.read_text(encoding="utf-8")
    m = re.search(
        r'BRIDGE_GUARD_JS: String\s*\n\s*get\(\)\s*=\s*"""(.*?)"""\s*\.trimIndent\(\)',
        kt, re.S)
    check("Kotlin 可定位 BRIDGE_GUARD_JS 模板", m is not None)
    if m:
        kt_tpl = norm(m.group(1))
        kt_tpl = kt_tpl.lstrip("\n")
        # Kotlin raw string 末行缩进（""" 前空格）经 trimIndent 后为空白行——
        # 归一化时剥除尾部空白行（与 Kotlin 实际运行值一致）
        kt_tpl = re.sub(r"\n[ \t]+\Z", "\n", kt_tpl)
        for kt_ph, canonical_ph in KOTLIN_PLACEHOLDERS.items():
            kt_tpl = kt_tpl.replace(kt_ph, canonical_ph)
        if kt_tpl.endswith("\n"):
            pass  # 与规范一致的尾部换行
        else:
            kt_tpl += "\n"
        check("Kotlin 模板 ≡ 规范模板（归一化后）", kt_tpl == canonical,
              _first_diff(canonical, kt_tpl))
        # 归一化不得残留未映射的 Kotlin 插值（防新增占位符漏登记）
        check("Kotlin 模板无未登记插值", "$" not in kt_tpl.replace(
            "__AEGIS_HOSTS__", "").replace("__AEGIS_REQUIRE_HTTPS__", ""))

    if failures:
        print("FAIL — bridge_guard 单一事实源校验")
        for f in failures:
            print("  -", f)
        return 1
    print("OK — bridge_guard 三端单一事实源校验通过")
    print(f"  规范模板: {CANONICAL.relative_to(ROOT)}（{len(canonical.splitlines())} 行）")
    print("  Rust: include_str! 消费 ✓ ｜ Kotlin: 归一化逐行一致 ✓")
    return 0


def _first_diff(expected: str, actual: str) -> str:
    el, al = expected.splitlines(), actual.splitlines()
    for i in range(max(len(el), len(al))):
        e = el[i] if i < len(el) else "<EOF>"
        a = al[i] if i < len(al) else "<EOF>"
        if e != a:
            return f"第 {i + 1} 行不一致: expected={e!r} actual={a!r}"
    return "未知差异"


if __name__ == "__main__":
    sys.exit(main())

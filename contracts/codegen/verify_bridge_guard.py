"""verify_bridge_guard.py —— Bridge 守卫 JS 三端单一事实源校验（合并门禁）。

背景：守卫脚本曾在 Rust 与 Kotlin 各自手工维护一份，已经实际产生过
一次漂移（Kotlin 侧缺失 REQUIRE_HTTPS 段——fail-open 类 bug 的温床）。
ADR-007 起，规范模板唯一存于 contracts/schemas/bridge_guard.template.js：

- Rust：bridge_guard.rs 经 include_str! 编译期嵌入（消费规范文件本身）；
- Kotlin：WebViewHardening.kt 内嵌副本（模板逐字节未变），占位符经 Kotlin
  插值注入，本脚本做「占位符归一化 → 逐行比对」校验；
- C#：无注入 JS（走 WebView2 Settings 收紧路径），不在本门禁范围。

审计第六轮（2026-10-03）：拦截点清单（REQUIRED_SINKS）自模板头部注释迁出
至门禁自有策略文件 contracts/policy/bridge-sinks.yaml——被证明物不得书写
自己的检查清单。此前锚点行既声明清单、又被清单回比对同一模板，把某 hook
实现连同其锚点 token 一并删除即恒绿（PY-236 只堵「锚在 body 空」，堵不住
「锚与实现同删」）。现门禁以策略文件为唯一权威清单，双向断言：
(a) 模板 body 承载每个 sink 的 hook 正则（删一个 hook 即红）；
(b) 每个 sink 的 hook 正则同时出现在 Kotlin 归一化副本（Rust 经 include_str!
    直接消费规范文件，(a) 即覆盖 Rust）；
(c) 模板锚点行 token 集合 ⊇ 策略 anchor_token（锚点单独漂移即红）。

用法：python contracts/codegen/verify_bridge_guard.py（仓库根运行）
退出码：0 = 一致且覆盖齐备；1 = 漂移/缺失/空心化（CI 门禁失败）。
"""

import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
CANONICAL = ROOT / "contracts" / "schemas" / "bridge_guard.template.js"
RUST = ROOT / "core" / "rust-policy-core" / "src" / "bridge_guard.rs"
KOTLIN = ROOT / "android" / "app" / "src" / "main" / "java" / "com" / "aegis" / "browser" / "WebViewHardening.kt"
# 审计第六轮（2026-10-03）：sink 清单权威源——门禁自有策略文件（非模板自身注释）。
SINKS_POLICY = ROOT / "contracts" / "policy" / "bridge-sinks.yaml"

# Kotlin 模板占位符 → 规范占位符（归一化映射）
KOTLIN_PLACEHOLDERS = {
    "[$allowedHostsJson]": "__AEGIS_HOSTS__",
    "$requireHttpsJson": "__AEGIS_REQUIRE_HTTPS__",
}

# 审计第六轮（2026-10-03）：failures 此前是「跨 main() 累加」的模块级全局——
# 同一进程两次 main() 会把上一次的失败带到下一次（harness 靠 re-import 模块
# 绕开）。现 main() 起始 clear()：保留模块属性引用（monkeypatch 的列表照常
# 生效），杜绝累加。PY-215/PY-236 时期遗留陷阱就此闭合。
failures: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    if not cond:
        failures.append(f"{name}: {detail}")


def norm(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _load_policy(path: Path) -> dict | None:
    """读取门禁自有 sink 清单。任何读取/解析/结构错误 → None（fail-closed：
    无权威清单可比对时不得默认放行——重蹈「清单来自被证明物」的覆辙）。"""
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError):
        return None
    if not isinstance(raw, dict) or str(raw.get("version")) != "1":
        return None
    sinks = raw.get("sinks")
    if not isinstance(sinks, list) or not sinks:
        return None
    for s in sinks:
        if not isinstance(s, dict) or not all(
                k in s for k in ("id", "anchor_token", "hook_pattern")):
            return None
    if not isinstance(raw.get("required_placeholders"), list) or not raw["required_placeholders"]:
        return None
    # 缺口须文档化：out_of_scope 段缺失/空 = 过度声明「四出口即全覆盖」——fail-closed
    if not isinstance(raw.get("out_of_scope"), dict) or not raw["out_of_scope"]:
        return None
    return raw


def _anchor_tokens(canonical_text: str) -> set[str] | None:
    """模板 "// REQUIRED_SINKS:" 锚点行的 token 集合；无锚点行 → None。"""
    tokens: set[str] | None = None
    for line in canonical_text.splitlines():
        if line.startswith("// REQUIRED_SINKS:"):
            payload = line[len("// REQUIRED_SINKS:"):].strip()
            tokens = tokens or set()
            tokens.update(t.strip() for t in payload.split("|") if t.strip())
    return tokens


def _extract_kotlin_template(kt_text: str) -> str | None:
    """定位并归一化 Kotlin 内嵌副本（占位符映射回规范形式）。"""
    m = re.search(
        r'BRIDGE_GUARD_JS: String\s*\n\s*get\(\)\s*=\s*"""(.*?)"""\s*\.trimIndent\(\)',
        kt_text, re.DOTALL)
    if not m:
        return None
    kt_tpl = norm(m.group(1)).lstrip("\n")
    # Kotlin raw string 末行缩进（""" 前空格）经 trimIndent 后为空白行——
    # 归一化时剥除尾部空白行（与 Kotlin 实际运行值一致）
    kt_tpl = re.sub(r"\n[ \t]+\Z", "\n", kt_tpl)
    for kt_ph, canonical_ph in KOTLIN_PLACEHOLDERS.items():
        kt_tpl = kt_tpl.replace(kt_ph, canonical_ph)
    if not kt_tpl.endswith("\n"):
        kt_tpl += "\n"
    return kt_tpl


def main() -> int:
    failures.clear()  # 审计第六轮：每次调用重置——跨 main() 不再累加陈旧失败
    if not CANONICAL.is_file():
        print(f"FAIL: 规范模板缺失: {CANONICAL}")
        return 1
    # PY-033：Rust/Kotlin 源缺失时此前 read_text 原始栈——与规范模板同口径显式拒绝
    for label, path in (("Rust 源", RUST), ("Kotlin 源", KOTLIN)):
        if not path.is_file():
            print(f"FAIL: {label}缺失: {path}")
            return 1
    canonical = norm(CANONICAL.read_text(encoding="utf-8"))

    # 0) 门禁自有 sink 清单（策略文件）——加载失败即 fail-closed，绝不回退模板注释
    policy = _load_policy(SINKS_POLICY)
    check("门禁 sink 清单策略文件可用: contracts/policy/bridge-sinks.yaml",
          policy is not None,
          f"无法加载/校验 {SINKS_POLICY}（权威清单缺失即 fail-closed，"
          "不以被证明物自身注释为准——审计第六轮）")
    if policy is None:
        return _report(canonical)

    sinks = policy["sinks"]

    # 1) 规范模板自检：占位符齐备（parity 归一化映射依赖）
    for ph in policy["required_placeholders"]:
        check(f"规范模板含占位符 {ph}", ph in canonical)

    # 2) 覆盖双向断言：body 承载 hook 正则 + 锚点行 token 齐备
    #    body = 剔除锚点行后的模板（锚点行含 token 名，不能充当「实现承载」的证据）
    body = "\n".join(
        ln for ln in canonical.splitlines() if not ln.startswith("// REQUIRED_SINKS:"))
    anchor = _anchor_tokens(canonical)
    check("规范模板含 REQUIRED_SINKS 锚点行", anchor is not None,
          "锚点行缺失——清单 anchor_token 无从对账（审计第六轮）")
    for s in sinks:
        sid, pat = s["id"], s["hook_pattern"]
        try:
            rx = re.compile(pat)
        except re.error:
            check(f"sink hook_pattern 可编译: {sid}", False, f"非法正则 {pat!r}")
            continue
        check(f"规范模板 body 含拦截点/正则: {sid}", bool(rx.search(body)),
              "清单声明但 body 无实现承载——守卫被挖空（删一个 hook 实现即红）")
        check(f"模板锚点行含 sink token: {sid}",
              anchor is not None and s["anchor_token"] in anchor,
              f"anchor_token={s['anchor_token']!r} 不在锚点行 token 集合")

    # 3) Rust：必须 include_str! 规范文件（编译期单源），禁止再内嵌 r#" 副本
    #    Rust 副本即规范文件本身 → 步骤 2 的 body 正则已覆盖 Rust 侧。
    rust = norm(RUST.read_text(encoding="utf-8"))
    m = re.search(r'include_str!\(\s*"([^"]+)"\s*\)', rust)
    check("Rust 使用 include_str! 消费规范模板", m is not None)
    if m:
        resolved = (RUST.parent / m.group(1)).resolve()
        check("Rust include 路径指向规范模板", resolved == CANONICAL.resolve(),
              f"resolved={resolved}")
    check("Rust 不再内嵌 r#\" 守卫副本", 'const SCRIPT: &str = r#"' not in rust)

    # 4) Kotlin：内嵌副本归一化后必须与规范逐行一致 + 每个 sink 正则同时命中
    kt = KOTLIN.read_text(encoding="utf-8")
    kt_tpl = _extract_kotlin_template(kt)
    check("Kotlin 可定位 BRIDGE_GUARD_JS 模板", kt_tpl is not None)
    if kt_tpl is not None:
        check("Kotlin 模板 ≡ 规范模板（归一化后）", kt_tpl == canonical,
              _first_diff(canonical, kt_tpl))
        # 归一化不得残留未映射的 Kotlin 插值（防新增占位符漏登记）
        check("Kotlin 模板无未登记插值", "$" not in kt_tpl.replace(
            "__AEGIS_HOSTS__", "").replace("__AEGIS_REQUIRE_HTTPS__", ""))
        for s in sinks:
            check(f"Kotlin 副本含拦截点: {s['id']}",
                  bool(re.search(s["hook_pattern"], kt_tpl)),
                  "Kotlin 内嵌副本缺失该 hook 实现（parity 或 copy 侧丢失）")

    return _report(canonical)


def _report(canonical: str) -> int:
    if failures:
        print("FAIL — bridge_guard 单一事实源校验")
        for f in failures:
            print("  -", f)
        return 1
    print("OK — bridge_guard 三端单一事实源校验通过（覆盖 + parity 双向断言）")
    # PY-134 配套：CANONICAL 可被重定向（单测）——仓库外路径原样输出
    try:
        canon_display = CANONICAL.relative_to(ROOT)
    except ValueError:
        canon_display = CANONICAL
    print(f"  规范模板: {canon_display}（{len(canonical.splitlines())} 行）")
    print("  Rust: include_str! 消费 ✓ ｜ Kotlin: 归一化逐行一致 + 逐 sink 命中 ✓")
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

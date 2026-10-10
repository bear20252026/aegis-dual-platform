"""engine_metadata.py —— 引擎「展示名 + 默认值」的跨端提取与判据（第九轮 R9-SH-9）。

从 `verify_cross_end_lists.py` 拆出来只有一个原因：那条门禁已在 300 行红线上，
而这两份元数据的判据恰好放不下（本仓红线是新文件 ≤300，不靠抬基线绕过）。
拆开后职责也更清楚：本文件只管**怎么取**（四端各自的表形态）与**怎么判**，
fail-closed 的汇总与退出码留在对面的门禁里。

历史缺口：那条引擎对账只比 **key 集合**，两份元数据长期无人判——

* 展示名在 4 处各抄一遍（legacy 元组第 0 位 / Kotlin `ENGINE_NAMES` /
  C# `EngineNames` / 壳层 `engineFallback` 的 `name` 字段）：改一个中文名只落一处
  不会红，而用户在两窗看到的就是不同标签；
* 默认引擎在 5 处各写一遍（legacy `DEFAULT_ENGINE` / Kotlin `DEFAULT_ENGINE` /
  C# `DefaultEngine` / 壳层 `engineFallback` 的 `engine` / `start.html` 胶囊初始文字）：
  换默认值漏改任一处 ⇒ 首页胶囊显示旧引擎、Android 搜索走旧引擎，两窗行为分叉。

SP-154 的同一条边界在这里也成立：legacy 是**归档端**，文件不在 ⇒ 降级为现役三端 +
一条告警（不是整条判据失效，也不是把「读不到」当「读到且一致」）；文件在但表解析不出
⇒ 仍算 fail。现役三端（Kotlin/C#/壳层）任何时候解析不到都是 fail。

判据范围**如实收窄**：展示名只比核心引擎集（`verify_cross_end_lists.py` 算出的
legacy ∪ Kotlin），C# 的扩展引擎（so360/duckduckgo/brave/startpage/ecosia/yandex）
不进面——壳层回退表刻意只覆盖核心四引擎，逼它抄满十个反而让回退表去猜没有登记过
的名字（扩展引擎的 key 集合仍由对面门禁的 `CS_ENGINE_EXTENSIONS` 白名单双向判）。
"""
from __future__ import annotations

import re
from typing import Callable

_READ = Callable[[str], str]

_URL_UTILS = "legacy/windows-pywebview/app/url_utils.py"
_KOTLIN = "android/app/src/main/java/com/aegis/browser/SearchEngines.kt"
_CSHARP = "windows/src/Aegis.Windows.App/Chrome/UrlNormalizer.cs"
_SHELL = "shared/shell/start.js"
_HTML = "shared/shell/start.html"

# (标签, 文件, 表块正则, 条目正则)。Kotlin 用 `"key" to "名"` 形态，与 ENGINE_URLS 同写法；
# legacy 是 `"key": ("名", "模板")`，取元组第 0 位。
_NAME_SLOTS = (
    ("legacy/url_utils", _URL_UTILS, r"SEARCH_ENGINES[^=]*=\s*\{(.*?)\n\}",
     r'"([a-z0-9]+)"\s*:\s*\("([^"]+)"'),
    ("android/SearchEngines.kt", _KOTLIN, r"ENGINE_NAMES[^=]*=\s*mapOf\((.*?)\)",
     r'"([a-z0-9]+)"\s+to\s+"([^"]+)"'),
    ("windows/UrlNormalizer.cs", _CSHARP,
     r"EngineNames\s*=\s*new Dictionary[^{]*\{(.*?)\n\s*\};",
     r'\["([a-z0-9]+)"\]\s*=\s*"([^"]+)"'),
    ("shell/start.js", _SHELL, r"function engineFallback\(\)\s*\{.*?engines:\s*\[(.*?)\]",
     r"key:\s*'([a-z0-9]+)',\s*name:\s*'([^']+)'"),
)

_DEFAULT_SLOTS = (
    ("legacy/url_utils", _URL_UTILS, r'DEFAULT_ENGINE\s*=\s*"([a-z0-9]+)"', _URL_UTILS),
    ("android/SearchEngines.kt", _KOTLIN, r'DEFAULT_ENGINE:\s*String\s*=\s*"([a-z0-9]+)"', _KOTLIN),
    ("windows/UrlNormalizer.cs", _CSHARP, r'DefaultEngine\s*=\s*"([a-z0-9]+)"', _CSHARP),
    ("shell/start.js", _SHELL, r"engine:\s*'([a-z0-9]+)'", _SHELL),
)


def extract_names(read: _READ, present: _READ | None = None) -> dict[str, dict[str, str]]:
    """四端各自的 key→展示名；解析不到表块 ⇒ 该端留空表（调用方计失败）。

    `present` 给出时，文件不存在的端**不去读**（避开对面门禁 `_read` 的「文件缺失」
    fail——legacy 归档端缺失按 SP-154 是降级，不是断链）。
    """
    out: dict[str, dict[str, str]] = {}
    for label, rel, block_re, pair_re in _NAME_SLOTS:
        if present is not None and not present(rel):
            out[label] = {}
            continue
        match = re.search(block_re, read(rel), re.DOTALL)
        out[label] = dict(re.findall(pair_re, match.group(1))) if match else {}
    return out


def extract_defaults(read: _READ, present: _READ | None = None) -> dict[str, str]:
    """四端各自的默认引擎字面量；取不到的端**不出现**在返回体里（调用方计失败）。"""
    out: dict[str, str] = {}
    for label, rel, pattern, _hint in _DEFAULT_SLOTS:
        if present is not None and not present(rel):
            continue
        match = re.search(pattern, read(rel), re.DOTALL)
        if match:
            out[label] = match.group(1)
    return out


def html_initial_label(read: _READ) -> str | None:
    """`start.html` 胶囊的初始文字——它应＝默认引擎的展示名。

    R9-SH-8 之后这一格仍保留硬编码占位（首帧无闪烁的代价），但写错会先闪一个错标签，
    所以并进同一判据，而不是另立一套「HTML 里不许出现引擎名」的规矩。
    """
    match = re.search(r'id="engineName">([^<]*)<', read(_HTML))
    return match.group(1) if match else None


def check(core: set[str], read: _READ, exists: _READ | None = None) -> list[tuple[str, str]]:
    """返回 `(消息, 种类)` 列表，种类 ∈ {"fail", "warn"}——由对面门禁汇总并决定退出码。

    `exists`（可选）给出「文件在不在」的判据：SP-154 要求 legacy 归档端缺失时**降级**
    而不是断链；不传则按「文件都在」处理（合成夹具走这条）。
    """
    present = (lambda rel: True) if exists is None else exists
    results: list[tuple[str, str]] = []
    if not core:
        # 核心引擎集为空 ⇒ 没有可比对的 key，展示名/默认值也无从判。对面门禁在这种情况下
        # 本身就已经 fail（key 集为空意味着引擎表整张没了），所以这里降级为告警，
        # 不给同一次失败叠三条「缺表」噪声；合成夹具（空 core）也走这条分支。
        return [("核心引擎集为空——展示名/默认值对账无从判定", "warn")]
    skipped_legacy = not present(_URL_UTILS)
    if skipped_legacy:
        results.append(("legacy url_utils 缺失——展示名/默认值对账降级为现役三端（SP-154 同口径）",
                        "warn"))
    names = extract_names(read, present)
    for label, rel, _block_re, _pair in _NAME_SLOTS:
        if not names[label] and not (label == "legacy/url_utils" and skipped_legacy):
            results.append((f"{label}: 未找到引擎展示名表（{rel}）", "fail"))
    live = {label: table for label, table in names.items() if table}
    if not live:
        results.append(("引擎展示名四端全部解析失败——不作通过判定", "fail"))
        return results

    for key in sorted(core):
        seen = {label: table.get(key) for label, table in live.items()}
        if len(set(seen.values())) > 1:
            results.append((f"引擎展示名不一致: {key} → "
                            + "；".join(f"{label}={seen[label]!r}" for label in sorted(seen)),
                            "fail"))
    if not skipped_legacy and "legacy/url_utils" not in live:
        # 文件在、表解析不出来：现役三端继续判，但这条降级必须是**告警**而不是放行
        results.append(("legacy url_utils 引擎表解析失败——展示名对账降级为现役三端", "warn"))

    defaults = extract_defaults(read, present)
    for label, _rel, _pattern, hint in _DEFAULT_SLOTS:
        if label not in defaults and not (label == "legacy/url_utils" and skipped_legacy):
            results.append((f"{label}: 找不到默认引擎字面量（{hint}）", "fail"))
    if len(set(defaults.values())) > 1:
        results.append(("默认引擎不一致: "
                        + "；".join(f"{k}={v}" for k, v in sorted(defaults.items())), "fail"))
    elif defaults:
        want = next(iter(defaults.values()))
        if want not in core:
            results.append((f"默认引擎 {want!r} 不在核心引擎集 {sorted(core)} 内", "fail"))
        label = html_initial_label(read)
        if label is None:
            results.append((f'start.html: 未找到 id="engineName" 的初始标签（{_HTML}）', "fail"))
        else:
            shell_name = (names.get("shell/start.js") or {}).get(want)
            if shell_name and label != shell_name:
                results.append((f"start.html 胶囊初始文字 {label!r} ≠ 默认引擎展示名 {shell_name!r}",
                                "fail"))
    return results

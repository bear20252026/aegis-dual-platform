# Aegis 搜索功能全链路审计报告

**审计时间**：2026-08-31 ~ 2026-09-01  
**测试设备**：本地 Windows 仓库 + 真机 Xiaomi（a567fa58，Aegis v2.1.7）  
**审计范围**：Windows 桌面壳、Android App、共享首页 `shared/shell/start.html`、URL 策略层  
**核心问题**：**两端均存在 P0 级搜索/导航失效路径**。

---

## 一、一句话结论

| 端 | 首页搜索框 | 顶部地址栏 | 引擎切换 | 粘贴完整 URL |
|---|---|---|---|---|
| Windows | ✅ 可用 | ❌ **离开首页后完全失效** | ✅ 可用 | ✅ 可用 |
| Android | ⚠️ 可用，但粘贴完整 URL 会坏 | ❌ **无法搜索，只能当网址** | ❌ UI 不更新 | ⚠️ 地址栏可用，首页框会坏 |

---

## 二、Windows 端：地址栏在任意远程页面静默失效

### 2.1 失效路径

`legacy/windows-pywebview/app/bridge/navigation.py::NavigationMixin.navigate()`：

```python
def navigate(self, text: str) -> None:
    if not self._check_trusted_source():   # ← 问题在这里
        ...
        return
    url = normalize_url(text, self._engine)
    if not self._is_navigation_safe_url(url):
        return
    self._load(url)
```

`_check_trusted_source()` 要求当前标签 URL 的 `host == ""`，即只允许 `file://` 本地壳页调用。

但地址栏是**注入到每个页面顶部**的 DOM（`shell_toolbar.py` 的 `aegis-chrome`），因此当用户在任何 `https://` 页面使用地址栏时，`current_url()` 返回的是远程页面 host，**导致 navigate 被静默拒绝**。

### 2.2 本地复现脚本

文件：`C:\Users\17296\WorkBuddy\2026-08-30-02-02-28\_audit_search_repro.py`

直接构造 `Api` 实例并替换 `_load` 为探针，真实走 `navigate()` 代码路径：

| 场景 | 当前页面 | 输入 | 期望结果 | 实际结果 |
|---|---|---|---|---|
| A | `file:///.../start.html` | `今天天气` | 百度搜索 | ✅ 导航到百度 |
| B | `file:///.../start.html` | `example.com` | `https://example.com` | ✅ 导航成功 |
| C | `https://www.baidu.com/` | `今天天气` | 百度搜索 | ❌ **无导航** |
| D | `https://www.baidu.com/` | `example.org` | `https://example.org` | ❌ **无导航** |
| E | `https://www.baidu.com/` | `https://example.net/a b` | 拒绝/处理 | ❌ **无导航** |
| F | `https://example.com/` | `rust uniffi` | Google/百度搜索 | ❌ **无导航** |
| G | `https://example.com/` | `about:blank` | `about:blank` | ❌ **无导航** |

**结论：7 个场景只有 2 个可用，离开首页后地址栏/导航 100% 失效。**

### 2.3 根因

M-2 安全修复把 `_check_trusted_source()` 加在了 `navigate()` 入口，但**地址栏属于浏览器 Chrome UI，不是远程页面**。远程页面本来也无法调用 pywebview 暴露的 JS API（同源策略 + 注入脚本控制），该校验对地址栏是过度拒绝。

### 2.4 修复建议

方案 A（推荐）：地址栏调用使用专用内部入口（如 `_navigate_from_chrome(url)`），跳过来源校验；仅对 `pywebview.api` 被远程页面调用的路径保留校验。

方案 B：`_check_trusted_source()` 区分调用上下文——如果当前页面是浏览器注入的 Chrome 页或地址栏，host 为空即视为受信；否则再校验。实现较绕。

---

## 三、Android 端：原生地址栏无法执行搜索

### 3.1 失效路径

`BrowserViewModel.navigateToAddress()` → `SecureNavigator.navigateExternal(url)` → `BrowserEngine.normalizeExternal(input)`。

`BrowserEngine.normalizeExternal()`：

```kotlin
fun normalizeExternal(input: String): String? =
    input
        .trim()
        .takeIf { it.isNotEmpty() }
        ?.let { candidate -> if (candidate.contains("://")) candidate else "https://$candidate" }
        ?.let(OriginPolicy::tryParseExternal)
        ?.let(::canonicalize)
```

问题：输入没有 `://` 时，直接拼 `https://`，然后按 URL 校验。**没有"搜索词 vs 网址"判断**。

### 3.2 等价代码验证（本地 JVM）

用与 `OriginPolicy` 同等的 `java.net.URI` 逻辑验证：

| 输入 | `normalizeExternal` 结果 | 实际行为 |
|---|---|---|
| `今天天气` | 拒绝（`host` 为 `null`） | 安全提示/无导航 |
| `weather` | `https://weather` | 导航到错误页（DNS 失败） |
| `baidu.com` | `https://baidu.com` | 正常打开百度 |
| `https://www.baidu.com` | `https://www.baidu.com` | 正常打开百度 |

### 3.3 真机证据

在首页地址栏输入 `weather` 后，浏览器导航到了 `https://weathersset/stawea...` 并显示 `ERR_NAME_NOT_RESOLVED`：

- 附件：`C:\Users\17296\WorkBuddy\2026-08-30-02-02-28\_audit_a5.png`
- 结论：输入搜索词后浏览器把它当主机名访问，而不是搜索引擎查询。

> 注：截图中地址栏文本被输入法污染，是因为 adb `input text` 与 Compose TextField 的选中状态交互不稳定；但页面已经证明导航目标是 `https://weather...`，不是搜索引擎结果页。

### 3.4 修复建议

把 `BrowserEngine.normalizeExternal()` 扩展为与 Windows `normalize_url()` 同语义：

```kotlin
fun normalizeExternal(input: String, engineKey: String): String? {
    val text = input.trim()
    if (text.isEmpty()) return null
    if (text.equals("about:blank", ignoreCase = true)) return "about:blank"
    val lowered = text.lowercase()
    if (lowered.startsWith("http://") || lowered.startsWith("https://")) {
        return OriginPolicy.tryParseExternal(text)?.let(::canonicalize)
    }
    return if (text.contains(" ") || "." !in text) {
        val engine = ENGINE_URLS[engineKey] ?: ENGINE_URLS[DEFAULT_ENGINE]!!
        engine + Uri.encode(text)
    } else {
        OriginPolicy.tryParseExternal("https://$text")?.let(::canonicalize)
    }
}
```

并在 `BrowserViewModel` 中把当前引擎 key 传入。

---

## 四、Android 端：首页搜索框的其他问题

### 4.1 粘贴完整 URL 会拼成畸形地址

`AegisHomeBridge.buildTargetUrl()`：

```kotlin
private fun buildTargetUrl(text: String): String? {
    val looksLikeUrl = !text.contains(" ") && text.contains(".") && !text.endsWith(".")
    return if (looksLikeUrl) {
        "https://$text"
    } else {
        val engine = ENGINE_URLS[getEngine()] ?: ENGINE_URLS[DEFAULT_ENGINE]!!
        engine + android.net.Uri.encode(text)
    }
}
```

输入 `https://www.baidu.com` 时，`looksLikeUrl=true` → 返回 `https://https://www.baidu.com` → `OriginPolicy` 拒绝 → 静默失败。

### 4.2 搜索引擎切换 UI 失效

`start.html` 的 `Host.getEngine(cb)` 对 Android 调用 `a.getEngine()`，而 Android 返回 `String`（key）。但 JS 回调期望对象 `{engine, engines:[...]}`：

```js
Host.getEngine(function (data) {
  if (!data) return;
  ENGINES = data.engines || [];   // data 是字符串 -> engines undefined -> []
  ...
});
```

结果：
- `ENGINES = []`
- `cycleEngine()` 直接 `return`（因为 `!ENGINES.length`）
- 引擎 pill 永远显示初始硬编码的"百度"，点击无响应。

修复：把 `AegisHomeBridge.getEngine()` 改为返回 JSON 字符串，与 Windows `get_search_engine()` 同结构：

```kotlin
@JavascriptInterface
fun getEngine(): String =
    JSONObject().apply {
        put("engine", prefs.getString("engine", DEFAULT_ENGINE) ?: DEFAULT_ENGINE)
        put("engines", JSONArray().apply {
            ENGINE_URLS.entries.forEach { (k, _) ->
                put(JSONObject().apply {
                    put("key", k)
                    put("name", ENGINE_NAMES[k])
                })
            }
        })
    }.toString()
```

并在 `start.html` 里对 Android 回调用 `JSON.parse`。

---

## 五、Rust CommandBar 未接线

`core/rust-policy-core/src/command_bar.rs` 实现了统一的命令/搜索面板逻辑（`CommandBar`），但：

- Windows 端未调用 `command_bar` 任何 API；
- Android 端未调用；
- 仅被单元测试覆盖。

即搜索的"策略层"造了轮子，但两端都各自实现了搜索拼接，导致语义漂移。建议在重构搜索入口时统一接入 Rust `CommandBar` 或至少复用同一 normalize 逻辑。

---

## 六、其他细节缺陷

| 编号 | 问题 | 级别 | 说明 |
|---|---|---|---|
| D-1 | Windows `normalize_url` 对带空格 URL 返回原字符串 | P2 | `https://example.net/a b` 含空格直接返回，可能绕过 `is_navigation_safe` |
| D-2 | 双端搜索 URL 编码不一致 | P2 | Windows 用 `urllib.parse.quote`（`/` 不编码），Android 用 `Uri.encode`（`/` 编码） |
| D-3 | 搜索建议未实现 | P3 | `__SEARCH_SUGGEST__` 占位但无实际 suggestions 逻辑 |
| D-4 | Android `AegisHomeBridge.navigate` 参数可为 null | P3 | Kotlin 声明非空，JS 传 null 会抛异常，但会被 JS 层 catch |

---

## 七、修复优先级

1. **P0：Windows 远程页地址栏失效** —— 最高，浏览器基本功能不可用。
2. **P0：Android 原生地址栏无法搜索** —— 最高，搜索入口失效。
3. **P1：Android 首页搜索框粘贴完整 URL 失效** —— 影响网址输入。
4. **P1：Android 引擎切换 UI 失效** —— 功能可用但用户体验断裂。
5. **P2/P3：细节一致性与 CommandBar 接线** —— 随迭代处理。

---

## 八、附件

- Windows 复现脚本：`C:\Users\17296\WorkBuddy\2026-08-30-02-02-28\_audit_search_repro.py`
- Android 真机截图（地址栏输入 weather 后错误页）：`C:\Users\17296\WorkBuddy\2026-08-30-02-02-28\_audit_a5.png`
- Android 首页截图：`C:\Users\17296\WorkBuddy\2026-08-30-02-02-28\_audit_s0.png`

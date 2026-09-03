# Aegis 全面审计报告（2026-09-04）

> 审计范围：代码质量（Windows pywebview 现役栈 / Android / C# 目标栈 / Rust 核心 / contracts / CI 发布链）+ 用户体验 + 与真实浏览器（Chrome/Edge）功能差距。
> 方法：4 路并行全源码审读（约 1.9 万行活跃代码）+ 关键结论本地实证（pywebview 6.2.1 源码比对、Android 逻辑推演、正则验证）。
> 行号以 master@014100b 为准。

---

## 一、总评

**一句话**：这是一个「安全架构理念先进、底层策略核心工程质量高，但浏览器本体（用户可见的那一层）存在系统性『机制建了没接线』问题」的项目。宣称的多数安全加固与安全浏览功能在默认产物中并未生效，而作为「目标发布栈」的 C# 端只完成了约 5% 的浏览器功能。

**三个最重的结论**（均经本地实证）：

1. **Windows 现役栈的原生加固层整体是死代码**。`app/shell_adapter.py:80-86` 的 `core()` 取 `window.gui.webview.CoreWebView2`，但 pywebview 6.2.1 中 `window.gui` 是 `webview.platforms.winforms` **模块对象**（`guilib.py` 的 `initialize()` 返回模块本身），模块上没有 `webview` 属性——该属性在每窗口的 `BrowserView` 实例上（正确路径是 `window.native.webview`）。本机实测 `getattr(module, 'webview', None)` 返回 `None`。后果：`main_webview.py` 中所有 `if core is not None:` 分支（NewWindowRequested 拦截、指纹防护「页面脚本前生效」注入、ESM、磁盘缓存上限、崩溃监听、Mica 背景、能力探测）**从未执行过一次**，且全部被 `except: pass  # 静默降级` 吞掉，日志里连一条降级记录都没有。

2. **`window.open` / `target=_blank` 完全绕过 safe_url 门禁**。因上一条，`main_webview.py:495-538` 的 H-1 白名单拦截器从未注册；实际生效的是 pywebview 自带处理器（`edgechromium.py` `on_new_window_request`：`args.set_Handled(True); self.load_url(uri)`，**零校验**）。CLAUDE.md「所有导航入口都过 safe_url」红线在此入口 100% 失守。实际可达性受 Chromium 自身对 `file://` 跨源导航的防护缓解，但**内网地址（如 169.254.169.254 元数据面）、威胁名单域名经新窗口路径畅通无阻**——威胁拦截只覆盖地址栏/新标签/会话恢复三个入口。

3. **「目标发布栈」C# 端是一个仅能导航的审批演示壳**（约 1,900 行）：单标签、无书签/历史/下载/设置/任何用户功能，`StorageService` 是空类，`KillSwitch`/`ApprovalManager` 全仓无调用点。全部浏览器功能（约 7,000 行）住在语义上叫 `legacy/` 的 Python 目录里，且 CI 质量门禁、发布安装包都围绕 Python 栈运转。双栈退役 ADR 被自己的审计（architecture-audit-2026-08-31 A15）点名要求，至今不存在。

**同样要说的亮点**（避免误判项目成色）：
- Rust 策略核心质量高于平均：C ABI 边界规范（15 处 unsafe 全部带 SAFETY 注释 + `catch_unwind`）、nonce FIFO 有界 + generation 严格递增的 fail-closed 账本、`verify_strict` 的 ed25519-dalek（非自制密码学）、~160 个测试 + 直接消费 contracts 向量。
- contracts codegen 的「重新生成 + git diff --exit-code」陈旧门禁是真实有效的同步机制；bridge_guard 守卫 JS 单源校验结构性消除了此前的跨端漂移。
- 发布链 fail-closed 结构成立：pin-check → 三平台 → provenance/SBOM attestation/SHA-256 逐字节对账 → 受保护 environment publish。
- Android broker 模块（AndroidBroker/OriginPolicy）是仓库质量最高的模块，测试覆盖好。
- 自审文化罕见地强：多轮审计文档、ADR-007 自曝「ktlint 在 master 长期 FAIL 无人发现」、ADR-008 自认「四端重复实现必然漂移」。本报告的许多发现项目自己的审计文档已部分预言——但**承认≠修复**，影子配置、死代码群、文档漂移仍在。

---

## 二、代码质量发现（按严重度）

### P0 — 安全防线失效 / 必然崩溃

| # | 端 | 发现 | 证据 |
|---|---|---|---|
| P0-1 | Win | 原生加固层整体未生效（见总评第 1 条）：NewWindowRequested 拦截、FIX-1 指纹前置注入、AreHostObjectsAllowed/IsWebMessageEnabled 收紧、磁盘缓存上限、ProcessFailed 崩溃监听、Mica、probe 全部静默 no-op | `app/shell_adapter.py:80-86`；`main_webview.py:494-538, 252-357, 541-633`；本机 pywebview 6.2.1 实测 |
| P0-2 | Win | `window.open`/`target=_blank` 绕过全部 URL 门禁（见总评第 2 条） | `main_webview.py:495`（死代码）+ pywebview `edgechromium.py` 默认处理器实测 |
| P0-3 | Win | **下载功能被整体静默禁用**：pywebview 默认 `'ALLOW_DOWNLOADS': False` 且 `on_download_starting` 直接 Cancel，Aegis 从不设置该项。点任何下载链接无反应、无提示。`config.download_dir`/`ask_download_location`/`is_dangerous_download` 全部零消费者 | `main_webview.py:390-394`；`security.py:76`；本机 pywebview 6.2.1 实测 |
| P0-4 | Win | `current_url`/`js_error` 在 `_JS_EXPOSED` 白名单——**任意远程页面可读当前标签完整 URL（含 query/token）**，与 B0-W-01「远程页零敏感读取」整改口径自相矛盾 | `app/api_bridge.py:112`；`app/bridge/navigation.py:99-106, 141-150` |
| P0-5 | Android | 非 config 声明的配置变更（density/字号/locale/折叠屏）触发 Activity 重建时 `onDestroy` 无条件 `suspendAll + tearDown(destroy WebView)`，而 `BrowserViewModel.init()` 早退不重建——**全部标签持有已销毁 WebView，整窗白屏或崩溃**；进程死亡恢复（onSaveInstanceState 消费）完全缺失 | `AndroidManifest.xml:19`；`MainActivity.kt:306-315`；`BrowserViewModel.kt:89-90` |
| P0-6 | Android | 渲染进程崩溃恢复 `rebuildAfterRendererGone` 用 **ApplicationContext** 创建 WebView（正常路径用 Activity context）——恢复后的标签一弹 `<select>` 等原生对话框即崩（token null） | `BrowserViewModel.kt:91, 224-244` |
| P0-7 | 全端 | 默认构建下导航安全 = 仅 scheme 白名单：`REQUIRE_NATIVE_POLICY_CORE=false`、`REQUIRE_NAVIGATION_CONFIRMATION=false` 默认关，http/https 一律放行——宣称的「Rust 核心托管审批」在默认产物里整条链路是死路径（发布构建有 `AEGIS_REQUIRE_NATIVE_POLICY_CORE=1` 兜底，日常/调试构建没有） | `android/broker/build.gradle.kts` defaultConfig；`AndroidBroker.kt:151-179`；`BrowserPolicyBroker.cs:97-113` |

### P1 — 安全/功能严重缺陷

**Windows 现役栈：**
- **页内链接点击完全绕过威胁黑名单/Agent 白名单**：拦截 JS 把点击 `preventDefault` 后 `location.href = a.href` 原生放行，Python 层 `safe_url`/`host_is_blocked` 不参与；且 `a.href.startsWith('#')` 恒为假（`.href` 是绝对 URL），纯锚点链接也被破坏（`fingerprint_pipeline.py:333-342`）。**用户可感知**。
- **威胁情报源只读不更**：`ThreatFeedUpdater.refresh` 零生产调用者，默认安装黑名单恒为空集——safe_browsing 式防护在真实用户机器上不存在（`threat_feed.py:69-196`、`config.py:245`）。
- **标签状态串台竞态**：加载完成回调把 URL 写到「当时的 _current」，用户在加载完成前切标签 → A 页 URL/标题写入 B 标签并落盘，此后切到 B 会加载成 A（`bridge_hooks.py:31-34`、`tab_ops.py:434-444, 306-318`）。
- **历史「只写不读不清」**：`get_history`/`search`/`clear` 等全不在 `_JS_EXPOSED`，无任何 UI——历史无限增长且用户不可见、不可清（隐私合规风险），FTS5 投入全部不可达（`api_bridge.py:98-117`、`history_store.py`）。**用户可感知**。
- 左侧垂直标签栏渲染永久空白：JS 读 `window.__aegis_vtabs_data`（无任何赋值点，真实数据在 `__AEGIS_TABS__`），且页面被 `marginLeft:200px` 挤压（`shell_toolbar.py:381, 361-363`）。**用户可感知**。
- `session.json` 并发写竞争：固定 `.tmp` 路径 + 无锁，js_api 线程与 loaded 回调线程并发保存可落盘损坏 JSON → 会话全丢（`session_store.py:75-96`）。
- 指纹「加固」多项空操作：`wrapWithTiming` 无时序处理、`Object.getOwnPropertyNames` 覆盖原样返回、canvas 噪声 `(seed+i)%2` 一次差分可剥离（`fingerprint_pipeline.py:47-80, 117-128`）。
- **指纹防护污染画布本体**：toDataURL 代理里 `getImageData→加噪→putImageData` **写回可见画布**，图表/画板类站点像素被永久破坏（对比 Brave Farbling 只扰动读路径）。Android 端同样问题（`WebViewHardening.kt:173-183`）。

**Android：**
- **`AegisBridge` JS 接口注入所有页面**（`SecureWebViewFactory.kt:95-98`），bridge-guard 只拦 fetch/XHR 不护注入对象本身——任意远端页面可调 `setEngine`（持久改偏好）/`navigate`/`goBack`，且 `window.AegisBridge` 存在性本身是指纹探针，与 fingerprint-shield 目标自相矛盾。
- **iframe 的 http 导航劫持顶层页面**：`shouldOverrideUrlLoading` 不区分 `isForMainFrame`，iframe 导航被 `authorizeNavigation` 用 `view.loadUrl` 加载进整个 Activity（`AegisWebViewClient.kt:41-56, 158-172`）。
- HTTPS 升级对大小写 scheme 失效：判定处已 lowercase 但升级用大小写敏感的 `replaceFirst("http://")`——`HTTP://EXAMPLE.com` 原样放行明文（现被 network_security_config 兜成静默失败，换环境即穿）（`AegisWebViewClient.kt:41-47, 203-212`）。
- **外链打开被静默丢弃**：Manifest 声明 http/https VIEW intent-filter，但全仓无 `intent?.data` 读取、无 `onNewIntent`——其他 App「用 Aegis 打开」只落到首页（`AndroidManifest.xml:24-30`）。
- 待审批确认跨标签竞态 + 会话续期被旧 pending 卡死：每 client 各持 pending 而 ViewModel 只有一个全局槽，后台标签的 pending 使其会话（TTL 120s）永不再续期 → 返回后导航全部 `session_expired`（`AegisWebViewClient.kt:32, 114-119, 182-187`）。
- **`localhost:8000` / `192.168.1.1:8080` 被判非法 scheme 拒绝**（本次实证：`SCHEME_PREFIX` 正则把 host:port 的 host 部分匹配为 scheme → FORBIDDEN）——开发/内网最高频输入形态被误杀（`SearchEngines.kt:44, 95-108`）。
- `about:blank` 归一层放行、决策层必拒——自相矛盾，用户输 about:blank 得到误导性报错（`SearchEngines.kt:70` vs `OriginPolicy.kt:25`）。
- 下载链路：文件名直接取服务器 Content-Disposition（可含 `..`）后 `setDestinationInExternalPublicDir`，绕过 broker 直连 DownloadManager（与 ADR-002「无 AuthorizedAction 不能下载」矛盾）；`DownloadPolicy.lastPathSegment` 对 `/download?file=x.exe`、`x.exe.`（尾点）漏判（`WebViewDownloadHandler.kt:48, 65-78`、`DownloadPolicy.kt:33-42`）。
- 整页翻译把 **http/内网 URL 原文（含 query token）外发第三方** translatetheweb.com，先于任何 https 升级（`TranslateEntry.kt:26-31`）。

**C# / Rust / 契约：**
- C# 无 `DownloadStarting` 处理——下载完全绕过 Broker 默认放行，与 `BrowserPolicyBroker.cs:7`「没有 AuthorizedAction 不能导航/下载/导出」的注释直接矛盾。
- Rust `update_manifest.rs` 手写 canonical JSON **字符串不转义**（值含 `"`/`\`/控制字符即产生非法/歧义字节），且**不剔除 `signatures` 键**，而 Python 侧 `release/update_verifier.py:29-33` 剔除且正规转义——**两套 canonicalization 无字节级兼容保证、零 golden 向量**；手写 base64 宽松解码（遇 `=` 停、容忍尾部垃圾）。该文件自身 0 个测试。
- 跨端归一化行为分叉且无向量锁定：IPv6（C# System.Uri 收 / Rust 拒）、Unicode 空白（C# 拒 / Rust 收）、空端口（Rust 拒 / WHATWG 视为默认端口）、IDNA 两端都不做（浏览器做）。「同一向量三端同结果」实际只有 Rust 消费共享向量，C#/Kotlin 各测各的硬编码 URL。
- `verify_contract_compatibility.py` 名不副实：docstring 声称校验生成模型与 schema 一致，实现只查 JSON 可解析 + 文件存在（`contracts/codegen/verify_contract_compatibility.py:47-60`）。

### P2 — 正确性 / 性能 / 体验缺陷（要点）

- **双端均无 SSL/加载错误处理页**：Android 无 `onReceivedSslError/onReceivedError` 覆盖，证书错误、DNS 失败一律静默白屏，无审计留痕——「安全浏览器」缺证书错误页是最基本的透明度缺口。
- **双端均无加载进度指示**：Android `onProgressChanged` 只打 log；Windows 标签**标题永不更新为页面 title**（永远显示「新标签页」或搜索词）。
- Android：阅读模式内容跨标签残留（全局单例 `_content`）；退后台不 `pauseTimers`（JS/视频/指纹脚本继续跑）；关闭标签 destroy 先于 detach（Chromium 资源不回收）；返回键无历史直接 finish vs 前进/后退钮不可用时弹 AlertDialog（打断感强、行为不一致）；500ms 导航防抖静默吞输入。
- Windows：每次导航全量重注入 4 段 JS（每次独立线程 + 6s 超时）→ 高延迟站先见内容后见工具栏；每个 HTTP 子资源进 Python 回调（urlparse + 威胁检查 + 每请求重读 env + sitemap 加载）；切标签/关标签全量重载丢滚动/表单/SPA 状态；每导航同步落盘 session.json + 每条日志/每个 SQLite 连接都跑 ACL（`harden_perms`）syscall 放大；`NavQueue.recover()` 排干队列静默丢导航。
- 无障碍：Android 标签关闭钮 28dp、全部图标钮无 contentDescription；「阅/译」用文字 glyph 无语义。
- 性能反模式共享：审计日志无界增长（C# `RecordAudit` 内存 List、Windows event_log、Android logcat 记录页面标题/被拒 URL 全文——**logcat 含浏览足迹**）。

### P3 — 死代码 / 影子配置 / 文档漂移（要点）

- **死代码群**（grep 验证零生产调用者）：Windows `mcp.py`（MCP/Agent 层整体不可达，连带 Agent 白名单防护也是死的）、`agent_sitemap.py`（路径硬编码空串恒跳过）、`tab_state.py`、`fingerprint.py`、`asset_scheme.py` Qt 部分、`webview2_probe` 自检、`credential_guard.redact_url`、历史/书签的 search/clear/export/import 大半 API；Android `VerticalTabBar` 整文件（`_tabsPosition` 恒 "top"）、`Tab.pinned/group` 死 UI；C# `KillSwitch`、`ApprovalManager`、6 个生成 Contract record 无消费者。
- **配置影子字段 30+**：`incognito`、`adblock`、`save_passwords`、`safe_browsing`、`search_suggestions`、`theme`、`default_zoom`、`download_dir`、`use_speed_dial_newtab`、`sync_webdav_url`、`update_url`……config.py:81-88 自认「影子字段」。**用户/审计者会误以为这些开关有效**——项目自己的 privacy-defaults-audit.md 也承认这 6 个隐私字段「开发者会误以为防护已生效」。
- 文档漂移：`supported-features.md` 把已实现的「书签导入」「阅读器」列进「明确不做」、宣称的 Android BrowserState 状态机全仓不存在、Windows「单标签」早已过时；`docs/DESIGN.md` 整份是 Apple.com 设计规范（错放文件）；compat-baselines 承诺每周归档 probe JSON **从未生成过**；README「阶段 A-G 全 ✅」与两天后真机审计「启动 2 分钟后全部导航 session_expired 锁死」并存。
- selftest 质量总体真实（navigation_search/view_source/session_store 断言扎实），但 3 处恒真断言走过场，且**系统性盲区**：没有任何测试走真实 `shell.core()` 路径——P0-1 这类「整体静默降级」测试根本探测不到。

---

## 三、用户体验审计

**新标签页（shared/shell/start.html）——全项目 UX 完成度最高的部分**：跨端 Host 适配层（Windows Promise / Android 同步桥统一包装）、textContent 防 XSS 的 DOM 构建、form+submit 兼容移动端 IME、引擎胶囊持久化、壁纸选择、导入向导、会话恢复入口、修复注释细致（P1-2/P1-12 等回归都留了痕）。仍有硬伤：
1. **空书签状态引导用户「在网页地址栏旁点击『收藏』」——这个按钮不存在**（工具栏全文无收藏入口、`add_bookmark` 无 UI 调用者）。首次用户照做必然找不到，是典型的「承诺性文案」。
2. `renderBookmarks` 用 `setTimeout(200)` 等桥就绪而非 `pywebviewready` 事件——慢机器上书签宫格可能永不渲染。
3. 搜索按钮 1200ms 硬编码复原；导航被确认面板挂起超过 1.2s 后按钮状态与实际不符。
4. start.html 自带 Ctrl+L 处理与注入工具栏的 Ctrl+L 竞争焦点（双端各有一份处理逻辑叠加）。

**核心 UX 缺口（用户第一天就会撞上）**：
- **没有任何错误反馈通道**：SSL 错误白屏、导航被拒弹一个通用「无法通过安全策略验证」、Windows 六处桥方法静默失败、Android 确认挂起期点击「打开」无反应——安全浏览器把「拦截」做成了「看起来坏了」。项目审计文档自己总结过这个模式（P0-B「Deny 白屏无解释」），但两端主链路仍是静默失败。
- **下载完全不可用**（Windows 静默禁用 / Android 直连 DownloadManager 无确认无进度 UI）——真实浏览器 top-3 高频功能缺席。
- **历史与书签管理缺失**：历史能积累但永不衰老、不可查看清除；书签有宫格但加不了（无按钮）、管不了。导入向导能导进来，然后没有地方管理。
- **切标签丢状态**（Windows 单 webview 全量重载）、**标签标题不更新**——标签条基本失去存在意义。
- **安全功能与 UX 互相拆台**：Android 版本检查注释宣称「拒绝外部浏览」实际只是提示；`DownloadPolicy.requiresExplicitConfirmation` 名为确认实为 Toast 拦截；WebViewVersionCheck 对 Chrome/厂商 WebView provider 静默跳过——「安全提示」类 UI 的诚实性存疑。
- 翻译功能把内网/http URL 外发、指纹防护弄脏画布——「隐私/安全优先」的产品在两个功能上主动制造了它声称要防的问题。

---

## 四、与真实浏览器（Chrome/Edge）的实际差距

按普通用户「换用一个浏览器」的决策路径对照：

| 能力 | Chrome/Edge | Aegis Windows（现役栈） | Aegis Android |
|---|---|---|---|
| 多标签 | 独立进程/状态保留/拖拽/固定/分组 | 有标签条；**切标签全量重载丢状态**；垂直标签栏渲染空白；pin/group 仅死 UI | 单 Activity 多 WebView，状态基本保留；但 config 变更即全体销毁（P0-5） |
| 地址栏 | 联想/补全/搜索词判定/粘贴即达 | 无联想（死配置）；点击不选中；search_suggestions 影子字段 | 无法搜索的 bug 已修但 **host:port 误杀**；粘贴 URL 变畸形 bug 有修复记录，草稿生命周期缺失 |
| 下载 | 完整管理器（进度/暂停/续传/安全提示） | **整体禁用，点击无反应** | 直连系统 DownloadManager，无确认/进度 UI，文件名未净化 |
| 书签 | 全功能管理 | 空宫格只读，**无法添加**（无按钮） | 不支持（首页能力面明确排除） |
| 历史 | 全功能+清除+搜索 | **只写不读不清**（FTS 全死） | 不支持 |
| 设置 | 完整设置界面 | **无设置界面**（30+ 配置字段无消费者） | 仅引擎切换 |
| 错误页 | 精细错误页+证书警告+安全浏览拦截页 | 依赖 WebView2 默认页，无 SSL 处理 | 静默白屏 |
| 反钓鱼/安全浏览 | Safe Browsing 常驻 | 影子配置 + 威胁源永不刷新（恒空） | SafeBrowsingEnabled 开启 + onSafeBrowsingHit 回退（这一项真实有效） |
| 页内查找 Ctrl+F | 有 | 无 | 无 |
| 缩放/字体 | 按站点记忆 | 影子字段 | 无 |
| 无痕模式 | 有 | 影子字段 | 无 |
| 密码/自动填充 | 有 | 影子字段 | 无 |
| 扩展 | 有 | 明确不做（自认，WebView2 限制属实） | 明确不做 |
| 打印/PWA/多窗口 | 有 | 无 | 无 |
| 阅读/翻译 | Edge 有 | 无 | 有（翻译有隐私外发问题；阅读模式有性能/残留问题） |
| 导入 | 有 | **有**（Chrome/Edge 书签历史向导——真实亮点） | 无 |
| 会话恢复 | 有 | 有（含手动恢复入口；受并发写竞争威胁） | 无 |

**结论**：对照真实浏览器，Aegis 当前实际可用的能力面 ≈ 「地址栏导航 + 多标签壳 + 书签导入 + 一个精致的新标签页」，其余日常浏览器高频功能（下载、历史、书签管理、设置、查找、错误反馈）要么缺失、要么建了没接线。以「安全浏览器」定位论，安全侧同样存在「宣称与生效」的鸿沟（加固层死代码、威胁源恒空、默认构建无策略核心）——**产品当前的真实形态更接近一个安全架构验证平台，而非可日常使用的浏览器**。

---

## 五、战略风险

1. **双栈永久化**：C# 栈与 Python 栈的功能鸿沟 ≈ 一个完整浏览器（约 7,000 行 + shell UI），无迁移路线图、无进度度量；CI 质量门禁只覆盖 Python 栈；发布链同时出两套 Windows 制品（PyInstaller 安装包 + C# zip），供应链面翻倍。A15 要求的退役里程碑 ADR 缺位。
2. **三端四份策略实现漂移已发生**（IPv6/Unicode 空白/空端口/canonical JSON），共享向量差分只覆盖 Rust 端。ADR-008 自己写了「长期各自演进必然漂移」——已经应验。
3. **承诺超前的文档文化**：supported-features、threat-model（「下载经 broker 判定（已落地）」vs Windows 零调用点）、compat-baselines 三处「写了等于做了」。对一个以「诚实审计」为文化的项目，这是最值得警惕的慢性病。
4. SECURITY.md 作为对外漏洞接收机制不完整：无支持版本表、无响应时限、无 PGP/备用渠道、无 safe-harbor。

---

## 六、修复优先级建议

**立即（安全止血，1-2 天量级）**
1. 修 `shell_adapter.core()` → `window.native.webview.CoreWebView2`（并全部挂接到窗口就绪之后）；或诚实删除这批 no-op 并在 SECURITY.md 声明实际生效面。同时把「静默降级」改为显式日志（P0-1/P0-2 的共因）。
2. C# 栈补 `DownloadStarting` → Broker 判定；Android 下载文件名净化 + 危险扩展判定修复 + 走 broker。
3. `current_url`/`js_error` 移出远程可达白名单；`AegisBridge` 按 URL 白名单注入或方法内校验 `webView.url`。
4. Android：`rebuildAfterRendererGone` 改用 Activity context；`MainActivity.onDestroy` 仅在 `isFinishing` 时 teardown；补 `onReceivedError/onReceivedSslError` 错误页。

**短期（把「建了没接线」接上，1-2 周）**
5. 接通 threat_feed 刷新或删除该功能声明；Android 外链 intent 消费（onNewIntent）；`localhost:port` 分类修复；iframe `isForMainFrame` 区分；HTTPS 升级大小写。
6. Rust canonical JSON 转义 + signatures 剔除对齐 Python，加字节级 golden 向量入 contracts/vectors；C#/Kotlin 纳入共享向量差分。
7. 下载启用决策（Windows 设 `ALLOW_DOWNLOADS` + 最小提示 UI，或明示「不支持下载」）；书签「收藏」按钮或删除误导文案。

**中期（还产品债）**
8. 历史查看/清除最小 UI；标签标题/进度反馈；错误反馈通道统一（拦截必须说明原因）；切标签保活（Windows）；config 影子字段清理（或接线或删除）。
9. 写双栈退役 ADR（里程碑+度量）；redteam 从文档字符串断言升级为对真实 broker 的攻击测试；fuzz 目标接入 CI；update_manifest.rs 补测试。

---

*审计执行：4 路并行子代理全源码审读 + 主线实证（pywebview 6.2.1 本机源码比对、Android 正则/逻辑推演、关键文件复核）。所有 P0 结论均有直接代码证据或本机复现。*

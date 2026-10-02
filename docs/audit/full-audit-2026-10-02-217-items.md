# Aegis 全仓第四轮审计——217 项新发现(2026-10-02)

**范围**:接续 docs/audit/full-audit-2026-10-01-241-items.md(248 项登记/245 项闭环)之后的**新一轮全仓新鲜扫描**——七路并行审计代理逐文件核对当前代码状态(含 beta.52 真机闪退修复之后),凡与已登记条目相同或高度相似的一律剔除;另由云端门禁首跑实证补充 1 项(SP-260,自动依赖提交动态 workflow)。

**方式**:7 路并行审计(Windows C# / Android / Rust 核心 / Python·契约·发布链 / Web 资产·文档 / CI·根配置·盲区 / 提升点专项),每项带 file:line 证据与具体修复方案;修复批按文件所有权 5 路并行(CS/AD/RS/WB/SP)+PY 批,交接项由主审计收尾。

**总量**:**217 行登记(问题 111 / 提升 106)**:登记 216 项 + 云端实证追加 1 项(SP-260);**本轮闭环 214 项**,暂缓 2 项(WB-195/SP-258——需跨端断言面/依赖锁重算,留下轮),待处置 1 项(SP-260——仓库设置层,非文件可修)。P1×0 / P2×26 / P3×191。机器可读索引:full-audit-2026-10-02-217-items.csv(I-23)。

> 编号体系:延续既往(CS=C# 正典栈,AD=Android,RS=Rust 策略核心,PY=Python/CI/契约/发布链,WB=Web 资产+文档,SP=补充盲区/治理)。
> 优先级:P1=必须(缺陷/安全/门禁失效),P2=应该(正确性/一致性/重要测试),P3=可以(打磨/补测/归置)。
> 每行格式:`ID | 优先级 | 类型 | 位置 | 问题 → 方案 | 闭环`。
> 登记前合并:S-09≡WB-178、S-10≡WB-214、S-15≡WB-196、I-11≡WB-199、I-15≡SP-222;批次内合并:SP-232≡WB-196、SP-237=AD-316、SP-238=AD-317、SP-240=RS-309。
> CS 批提交信息所述文件名「…216-items.md」以本文件(217)为准——云端实证追加发生于登记之后。

---

## 0. P2 汇总(18 项)

| ID | 优先级 | 类型 | 位置 | 问题 → 方案 | 闭环 |
|---|---|---|---|---|---|
| CS-377 | P2 | 问题/红线违规 | windows/.../Chrome/MainWindow.xaml.cs | 全文 1424 行,超「改造后 ≤500」红线近 3 倍,9+ 历史缺陷集中地 → partial class 拆 5 文件(Shortcuts/Tabs/Menus/SourceViewer/WindowState),xaml.cs 余 435 行 | ✅ CS批 |
| CS-378 | P2 | 问题/功能缺陷 | windows/.../Chrome/InPrivateWindow.xaml.cs | 无痕窗零处订阅 NavigationDenied——策略拒绝导航零可见反馈(CS-355 只修主窗) → CreateRuntime 补订阅+ShowRejection | ✅ CS批 |
| CS-379 | P2 | 问题/安全(噪声可逆) | windows/.../WebView/FingerprintShield.cs:116-118 | canvas 噪声 `(seed+i)%2` 退化为全图常量 ±1(i 恒 4 倍数、只动 R 通道),减法即还原(RS-249/AD-253 孪生) → mulberry32 逐像素 PRNG+三通道独立扰动 | ✅ CS批 |
| CS-380 | P2 | 问题/安全(读取面绕过) | windows/.../WebView/FingerprintShield.cs:106,126 | 仅包 toDataURL——toBlob/OffscreenCanvas.convertToBlob 原样读出无噪声像素 → 补两出口同款噪声代理(RS-206/RS-082 口径) | ✅ CS批 |
| CS-381 | P2 | 问题/安全(跨站关联) | windows/.../WebView/FingerprintShield.cs:60 | getETLD1 取后两标签——bbc.co.uk 与 shop.co.uk 同种子(RS-257 孪生) → 小型公共后缀清单,命中取后 3 标签 | ✅ CS批 |
| CS-416 | P2 | 提升/文档失实 | windows/README.md:8-12 | 裸 dotnet 命令照做即改写 NuGet 锁(SP-220 地雷,文档面) → 补 `-r win-x64`+锁模式+提示行 | ✅ CS批 |
| AD-297 | P2 | 问题/指纹防护失效 | android/.../WebViewHardening.kt:189,126 | Stage1 注册键 `__AEGIS_REGISTER_PROXY` 与桥守卫读键 `Symbol.for('proxy.register.v1')` 永不匹配——RS-242 四出口 toString 伪装注册全部 no-op,`fetch.toString()` 一行暴露包装源码 → 键收敛(模板/Rust 侧只读,核对无需改) | ✅ AD批 |
| AD-298 | P2 | 问题/防护绕过 | android/.../WebViewHardening.kt:301 | Stage3 仅包 toDataURL——toBlob/convertToBlob 读无噪声原图(RS-082 孪生) → 同型噪声包装 | ✅ AD批 |
| AD-299 | P2 | 问题/跨端策略漂移 | android/broker/.../OriginPolicy.kt:45-54 | host 校验弱——`https://999.1.1.1/` 等共享向量在 Android 放行(Rust/C# 已拒) → 对齐 origin.rs(字符集/八位组≤255/端口0/前导点/../方括号) | ✅ AD批 |
| AD-300 | P2 | 问题/崩溃+功能失效 | android/.../MainDialogs.kt:197 | `for (i in raw.indices - 1)` 实为「移除元素 1」(stdlib 无 IntRange.minus(Int))——chunk-1 边界代理对永不修复+末段索引越界 → `0 until raw.size - 1` | ✅ AD批 |
| AD-301 | P2 | 问题/竞态性能 | android/broker/.../AndroidBroker.kt:93,116,134 | create/renewSession/updateDocumentGeneration 仍全局锁内跨 JNI(AD-200 只修 consumeNavigation)——native 阻塞拖住全部会话 → 锁内快照→锁外 JNI→锁内终态提交 | ✅ AD批 |
| AD-302 | P2 | 问题/外链误丢 | android/.../MainActivity.kt:299-308 | 外链频控时间戳在判 intent.data 前推进——data=null 烧掉窗口丢真实 VIEW 外链 → ExternalIntentRateLimit 独立类+条件推进 | ✅ AD批 |
| RS-275 | P2 | 问题/拦截绕过 | core/.../src/util.rs:58-61 | userinfo 取首个 `@`(WHATWG/本 crate https_only/redact 均取尾)——`https://x@evil@ads.example.com/` 黑名单父域链全漏 → `rfind('@')`+双侧向量 | ✅ RS批 |
| RS-276 | P2 | 问题/防护判定错误 | core/.../src/font_norm.rs:120-121 | check strip 正则样式 token 组不含空白——`italic bold 12px arial` 剥不掉,安全字体被伪装成不可用+行为差异探测点(node 实证) → 对齐同文件 measureText 口径 | ✅ RS批 |
| RS-277 | P2 | 问题/绑定漂移 | core/.../bindings/aegis_policy_core.py:519-533 | Python 绑定落后导出面 7+ 符号(consume_navigation/确认流/advance_document_generation 等)——Python 宿主够不到 fail-closed 流,且无漂移门禁 → aegis-uniffi-bindgen 重生成入库(CI 接线随 SP-239 面) | ✅ RS批 |
| PY-260 | P2 | 问题/e2e 模拟正确性+并发 | agent/tests/redteam_e2e_test.py:198-202 | 会话-tab 绑定写在全部 deny 门之前且在 _state_lock 外——deny 燃烧绑定(违反 SP-066「deny 不消费」不变量)+check-then-set 竞态 → 绑定入锁+置于门禁通过后;补「deny 不燃烧绑定」用例 | ✅ PY批 |
| PY-261 | P2 | 问题/工具正确性 | release/native_artifact_manifest.py:48,103-107 | manifest 比较依赖 --require flag 顺序——换序核对真实清单假报「不一致」 → 排序后比较+换序回归 | ✅ PY批 |
| PY-262 | P2 | 问题/正确性+互操作 | release/update_verifier.py:53-54,109 | 正则放行小写 t/z 但 fromisoformat 拒绝——合法 RFC3339 被误拒且错误归因「结构无效」 → 解析前归一+双向量 | ✅ PY批 |
| PY-263 | P2 | 问题/门禁缺口 | .github/workflows/legacy-python-guard.yml | 活跃树 ruff/bandit/SAST 只有周六 cron——工作日合入的 lint/SAST 回归最长 6 天不可见 → active_tree_gates.py 单源+contracts.yml 接线 | ✅ PY批+SP批 |

## 1. Windows C# 正典栈(CS-377..418,42 行)

| ID | 优先级 | 类型 | 位置 | 问题 → 方案 | 闭环 |
|---|---|---|---|---|---|
| CS-377 | P2 | 问题/红线违规 | Chrome/MainWindow.xaml.cs | (见 §0) | ✅ CS批 |
| CS-378 | P2 | 问题/功能缺陷 | Chrome/InPrivateWindow.xaml.cs | (见 §0) | ✅ CS批 |
| CS-379 | P2 | 问题/安全 | WebView/FingerprintShield.cs:116-118 | (见 §0) | ✅ CS批 |
| CS-380 | P2 | 问题/安全 | WebView/FingerprintShield.cs:106,126 | (见 §0) | ✅ CS批 |
| CS-381 | P2 | 问题/安全 | WebView/FingerprintShield.cs:60 | (见 §0) | ✅ CS批 |
| CS-382 | P3 | 问题/UI 冻结面 | WebView/HostWebView.cs:155 + Core/UrlSafety.cs:246 | 顶层路径冷缓存仍 UI 线程同步 DNS(CS-339 只修帧路径) → 顶层只读缓存+未命中 fail-closed 升级+Task.Run 后台预热 | ✅ CS批 |
| CS-383 | P3 | 问题/健壮性 | Chrome/MainWindow.xaml.cs Star_Click | BookmarkStore.Add/Remove 裸抛→全局异常弹窗(BookmarkManagerWindow 有 CS-164 守卫) → try/catch+ShowFeedback+SecurityLog | ✅ CS批 |
| CS-384 | P3 | 问题/资源泄漏竞态 | Chrome/InPrivateWindow.xaml.cs:87-103 | GetLeaseAsync await 后标签已关仍无条件 Create——重建已关闭标签泄漏至关窗 → tabId 存活校验后再 Create | ✅ CS批 |
| CS-385 | P3 | 问题/正确性 | Chrome/TabRuntime.cs:96-104 | 双重订阅 DownloadStarting——被拒下载以「已取消」幽灵条目入面板 → 处理器开头 `if (e.Handled) return` | ✅ CS批 |
| CS-386 | P3 | 问题/正确性 | Chrome/MainWindow.xaml.cs:64,430-435 | `_pendingDenyMessage` 窗口级单槽——后台标签 deny 后跨标签串扰/丢失 → Dictionary 按 tabId 存取,销毁清槽 | ✅ CS批 |
| CS-387 | P3 | 问题/数据丢失窗口 | Chrome/MainWindow.xaml.cs:61,573-574 | OnClosed 未等 `_historyWriteTail` 写入链——关窗竞态丢最后若干条历史 → 2s 超时同步等待 | ✅ CS批 |
| CS-388 | P3 | 问题/口径互斥 | Chrome/UrlNormalizer.cs:200-201 + WebView/HostWebView.cs:152-159 | 裸内网 IP 被补 http 后又被 HttpsOnly 升级炸——两组件对同一输入结论相反 → 升级豁免扩展到非公网 host(IsPublicHost 取反) | ✅ CS批 |
| CS-389 | P3 | 问题/纵深防御 | WebView/WebView2Hardening.cs:102-104 | `chrome.aegis.local` 白名单条目从未被虚拟主机映射——可被 LLMNR/mDNS 解析为远端源 → 删除条目至真实映射时再加 | ✅ CS批 |
| CS-390 | P3 | 问题/UX 承诺失实 | Chrome/MainWindow.xaml:433 + .cs | 关闭钮 ToolTip「关闭(Esc)」但 Esc 只路由审批面板——查找条打开时 Esc 无处理 → Esc+FindBar 可见即 `_find.Close()` | ✅ CS批 |
| CS-391 | P3 | 问题/主题断裂 | Chrome/MainWindow.xaml:361 | 地址框 `CaretBrush="#FFFFFFFF"` 浅色主题白底白光标 → DynamicResource AccentBrush(与子窗口一致) | ✅ CS批 |
| CS-392 | P3 | 问题/UX 状态机 | Chrome/HistoryWindow.xaml.cs:258-262 | ChipRange Unchecked 空操作——范围取消后面板不收起且后续编辑被静默忽略 → Unchecked 收起+清值+重载 | ✅ CS批 |
| CS-393 | P3 | 问题/UX 一致性 | Core/Tabs/TabManager.cs:130-134 | 关最后一个标签两窗口滞留空壳(无标签无 WebView) → 订阅方 CloseTab 返回 null 即关窗(带会话重建守卫) | ✅ CS批 |
| CS-394 | P3 | 问题/UX 状态失真 | Chrome/DownloadsWindow.xaml:96-98 | 暂停/继续/取消不随 StateKind 禁用——无效操作静默吞零反馈 → DataTrigger 按状态显隐(StateKind internal→public 修绑定可达) | ✅ CS批 |
| CS-403 | P3 | 问题/韧性 | Core/Favicons/FaviconService.cs:71-79 | 负缓存无 TTL——站点瞬时不可达本会话图标永不重试 → Miss 存时间戳+60s TTL | ✅ CS批 |
| CS-395 | P3 | 提升/注释失实 | Chrome/MainWindow.xaml.cs:167-170 | TruncateTitle 叠挂孤儿 summary(被删方法遗留) → 删 | ✅ CS批 |
| CS-396 | P3 | 提升/死代码 | Chrome/HistoryWindow.xaml.cs:68-76 | ApplyFilter 的 ComputeRange+suppress 包裹纯死开销 → 删,直接 LoadPage(1) | ✅ CS批 |
| CS-397 | P3 | 提升/死代码口径 | Core/History/HistoryStore.cs Dates() | 生产零调用无「仅测试保留」注记(CS-313 口径) → 补注释防误删回归 | ✅ CS批 |
| CS-398 | P3 | 提升/死事件 | Core/Settings/SettingsService.cs Changed | 生产零订阅(仅测试) → 删事件+反射断言防回归 | ✅ CS批 |
| CS-399 | P3 | 提升/性能 | Core/History/HistoryImporter.cs:63-75 | 逐条 Add=每条新 SQLite 连接+独立事务(BookmarkStore.Import 已批量化) → HistoryStore.ImportBatch 单连接单事务 | ✅ CS批 |
| CS-400 | P3 | 提升/性能+一致性 | Chrome/BookmarkManagerWindow.xaml.cs + MainWindow | UI 线程同步全表查询(与 CS-031/159 口径相悖) → Task.Run+Dispatcher 回投+代际丢弃 | ✅ CS批 |
| CS-401 | P3 | 提升/一致性 | Chrome/SuggestionController.cs:106,132-137 | SQL 层 url OR title 命中、MergeRows 只留 URL——白查+两层面语义分裂 → HistoryStore.SearchByUrl(SQL 侧 urlOnly,对齐既有锁定口径) | ✅ CS批 |
| CS-402 | P3 | 提升/一致性 | Chrome/InPrivateWindow.xaml.cs:23 | 共享进程级 KillSwitch 但横幅仅主窗有——无痕窗冻结零指示 → 订阅 Engaged 显示横幅 | ✅ CS批 |
| CS-404 | P3 | 提升/可观测 | Broker/BrowserPolicyBroker.cs:429-443 | native deny 审计 origin 恒字面量(managed 记脱敏 URL) → deny 行记 UrlRedactor.Redact(rawUrl) | ✅ CS批 |
| CS-405 | P3 | 提升/日志失真 | WebView/WebView2Hardening.cs:66-77 | 「管道已注入」成功日志写在 ContinueWith 外——失败时矛盾日志并存 → 移入 !IsFaulted 分支 | ✅ CS批 |
| CS-406 | P3 | 提升/补测试 | Chrome/WindowSharedChrome.ApplyTabVisibility | 四属性翻转零直测 → STA 单测(ZIndex/Visibility/IsHitTestVisible/IsEnabled) | ✅ CS批 |
| CS-407 | P3 | 提升/一致性 | Chrome/MainWindow.xaml.cs:719-724 | 重新打开已关闭标签菜单项缺 InputGestureText(CS-258 口径漏项) → 补 Ctrl+Shift+T | ✅ CS批 |
| CS-408 | P3 | 提升/UX 口径 | Chrome/FindBarController.cs:69-89 | 计数 innerText(含隐藏文本) vs 高亮 window.find(可视)——两数不一致 → TreeWalker 可视文本统计+取舍注记 | ✅ CS批 |
| CS-409 | P3 | 提升/注释失实 | Properties/AssemblyInfo.cs:3-7 | 注释称仅开放 C ABI 解析器,实际开放全部 internal 测试面 → 如实改述 | ✅ CS批 |
| CS-410 | P3 | 提升/可测性 | Chrome/SuggestionController.cs:48-49 | 防抖 DispatcherTimer 硬编码不可注入 → 复用 IDebounceTimer(SessionSaveScheduler 先例)+防抖单测 | ✅ CS批 |
| CS-411 | P3 | 提升/一致性 | Chrome/InPrivateWindow.xaml.cs:262-267 | TabClose_Click 裸调(主窗有日志+守卫) → WindowSharedChrome.CloseTabSafely 单源 | ✅ CS批 |
| CS-412 | P3 | 提升/补测试 | windows/tests(XAML Binding 零静态锚) | `{Binding X}` 全靠运行时反射——属性改名编译仍绿、绑定静默空 → XamlBindingStaticAnchorTests 反射锚 | ✅ CS批 |
| CS-413 | P3 | 提升/门禁硬化 | 三个 csproj | 「0 警告」口头基线(CS-374 实证可破) → Directory.Build.props 置 TreatWarningsAsErrors | ✅ CS批 |
| CS-414 | P3 | 提升/门禁对称 | tests/NtpBridgeTests.cs:257-258 | 壁纸断言仅计数+Contains(Kotlin 侧是差集对账)——目录改名 C# 绿 Kotlin 红 → Core.Tests 双向差集对账 | ✅ CS批 |
| CS-415 | P3 | 提升/重构 | 三个 csproj | 公共属性三处重复维护(SP-220 类约束漂移面) → windows/Directory.Build.props 单源(Version 三件套不上提——sync_versions 按 csproj 正则写) | ✅ CS批 |
| CS-416 | P2 | 提升/文档失实 | windows/README.md:8-12 | (见 §0) | ✅ CS批 |
| CS-417 | P3 | 提升/归置 | tests/Broker.Tests/UrlNormalizerTests.cs | 同名测试类两套件分裂,Broker 版测纯 Chrome 类 → 纯用例整迁 Core.Tests,Broker 只留集成断言 | ✅ CS批 |
| CS-418 | P3 | 提升/向量消费 | tests/Core.Tests(contracts/vectors 零消费) | 三端各养内联副本——向量调整仅 Rust 变红 → UrlOriginVectorTests 全量消费;顺带补 OriginPolicy 端口 0/八位组越界缺口(PY-075/RS-228 孪生) | ✅ CS批 |

## 2. Android 端(AD-297..332,36 行)

| ID | 优先级 | 类型 | 位置 | 问题 → 方案 | 闭环 |
|---|---|---|---|---|---|
| AD-297 | P2 | 问题/指纹防护失效 | app/.../WebViewHardening.kt:189,126 | (见 §0) | ✅ AD批 |
| AD-298 | P2 | 问题/防护绕过 | app/.../WebViewHardening.kt:301 | (见 §0) | ✅ AD批 |
| AD-299 | P2 | 问题/跨端策略漂移 | broker/.../OriginPolicy.kt:45-54 | (见 §0) | ✅ AD批 |
| AD-300 | P2 | 问题/崩溃+功能失效 | app/.../MainDialogs.kt:197 | (见 §0) | ✅ AD批 |
| AD-301 | P2 | 问题/竞态性能 | broker/.../AndroidBroker.kt:93,116,134 | (见 §0) | ✅ AD批 |
| AD-302 | P2 | 问题/外链误丢 | app/.../MainActivity.kt:299-308 | (见 §0) | ✅ AD批 |
| AD-303 | P3 | 问题/UX 一致性 | app/.../SearchEngines.kt:192 + BrowserViewModel.kt:329 | 地址栏输入 `tel:` 走恐吓拒绝提示(AD-284 只覆盖页内链接) → 按 scheme 分型走 unsupported_link_scheme Toast | ✅ AD批 |
| AD-305 | P3 | 问题/文件名失真 | app/.../WebViewDownloadHandler.kt:184,306-313 | URL 路径段 decodePercent 把 `+` 按 query 语义解成空格(AD-263 只修 filename*) → 路径段 decodePercentStrict | ✅ AD批 |
| AD-306 | P3 | 问题/跨端口径 | app/.../DownloadPolicy.kt:6-31 | 危险扩展名 23 项 vs Windows 40+——iso/vhd/py/url 等跨端可迁移危险缺失 → 补集+「无执行意义可豁免、可迁移危险不可豁免」口径 | ✅ AD批 |
| AD-307 | P3 | 问题/内存泄漏 | app/.../BrowserViewModel.kt:197-204 | 标签 WebView 持 Activity ctx——density/locale 重建泄漏整个 Activity → applicationContext 创建 | ✅ AD批 |
| AD-308 | P3 | 问题/文本边界 | app/.../LogSanitize.kt:25 | take 按 UTF-16 char 截断劈代理对(AD-109/261/268 口径漏网) → takeAtCharBoundary 提共享 internal | ✅ AD批 |
| AD-309 | P3 | 问题/升级语义不一致 | webview-adapter/.../AegisWebViewClient.kt:120,125-127 | 子框架升级只用于判定、放行仍载原 http——判定 URL≠加载 URL → Allow 即 loadUrl 升级后 URL | ✅ AD批 |
| AD-310 | P3 | 问题/可检测 | app/.../WebViewHardening.kt:453 | MAX_VIEWPORT_DIMS 伪装返回 Float32Array(真机 Int32Array)——instanceof 一行探测 → 改 Int32Array | ✅ AD批 |
| AD-311 | P3 | 问题/可检测 | app/.../WebViewHardening.kt:322-324 | Uint8ClampedArray 在 0/255 clamp 吸收噪声——直方图统计可探注入 → 边界像素噪声取离岸方向 | ✅ AD批 |
| AD-312 | P3 | 问题/状态失真 | app/.../TabManager.kt:153 | 后台标签渲染崩溃重建恒 suspended=false——maxActive 记账虚高 → inheritSuspended 按原态透传 | ✅ AD批 |
| AD-313 | P3 | 问题/注释失实+隐私面 | app/.../TranslateEntry.kt:34-38 | 注释称 fragment 是 OAuth code 唯一载体(标准形态在 query)且整 URL 含 query 外发翻译服务 → 修正注释+code/state/token 剥离 | ✅ AD批 |
| AD-328 | P3 | 问题/输入丢失 | app/.../BrowserViewModel.kt:338-342 | openExternalUrl 无条件覆写地址栏——顶掉用户草稿且被拒后停留未加载 URL → addressDraftActive 跳过+targetOverride | ✅ AD批 |
| AD-329 | P3 | 问题/种子分裂 | app/.../WebViewHardening.kt:202-206 | 迷你 PSL 缺 co.il 等 9 个高频两段后缀——同站实体种子分裂(AD-107 形态) → 补集+例外清单口径 | ✅ AD批 |
| AD-331 | P3 | 问题/名实不符+误杀面 | app/.../WebViewDownloadHandler.kt:119-125 | requiresExplicitConfirmation 承诺「确认」实为硬拦截——`?src=setup.exe` 类合法下载无覆写路径 → 两级拆分(路径/文件名硬拦截,仅查询参数确认) | ✅ AD批 |
| AD-304 | P3 | 提升/外跳覆盖面 | webview-adapter/.../AegisWebViewClient.kt:60 | externalHandlerSchemes 缺 smsto/mmsto/geo——与恶意 scheme 同走静默 Deny → 扩集+分型测试 | ✅ AD批 |
| AD-314 | P3 | 提升/反检测覆盖 | app/.../WebViewHardening.kt:296-489 | Stage3-9 包装未注册 proxyMap——Function.prototype.toString 直接暴露各包装源码(RS-242 只修 Rust 侧) → 11 处 `__aegisReg` 注册+测试逐点断言 | ✅ AD批 |
| AD-315 | P3 | 提升/补测试 | broker/src/test/.../OriginPolicyTest.kt | 共享向量 Kotlin 侧零消费——跨端漂移永久不可见 → 全量消费 url-origin-valid/invalid.json | ✅ AD批 |
| AD-316 | P3 | 提升/CI 缺口 | .github/workflows/android-quality.yml | androidTest 两文件零编译门禁(注释宣称「编译验证即可」却无步骤) → `:app:assembleDebugAndroidTest` | ✅ SP批(=SP-237) |
| AD-317 | P3 | 提升/构建一致性 | .github/workflows/android-quality.yml:61 | SDK pin android-36 vs compileSdk 37 漂移+AGP 版本注释失实 → **云端实证修正**:android-37 平台包不在 sdkmanager stable 渠道(pin 37 必失败),回退 36 基线+「AGP 构建期自动装配」口径注释 | ✅ SP批(=SP-238,云端修正) |
| AD-318 | P3 | 提升/构建单源 | broker/build.gradle.kts:120 | jna `@aar` 脱离 version catalog 单源(5.19.1 双源) → toml 条目+`artifact { type = "aar" }` | ✅ AD批 |
| AD-319 | P3 | 提升/注释失实 | app/.../MainActivity.kt:87 | 注释指向已删除的 lateinit 幂等实现(AD-295 同族重构) → 可空判空口径 | ✅ AD批 |
| AD-320 | P3 | 提升/死代码 | webview-adapter/.../AegisWebViewClient.kt | authorizeNavigation 的 loadWhenAllowed 参数恒 true → 删参数收窄状态空间 | ✅ AD批 |
| AD-321 | P3 | 提升/补测试 | webview-adapter/src/test/... | 缺子框架 RequireConfirmation fail-closed 阻断与 onReceivedError 主/子框架分型两分支 → 各补一测 | ✅ AD批 |
| AD-322 | P3 | 提升/文案单源 | app/.../TabManager.kt:31 + ReaderMode.kt:114 | 「新标签页」「阅读模式」硬编码 Kotlin(AD-045 系列漏网) → R.string 迁移+UI 层兜底 | ✅ AD批 |
| AD-323 | P3 | 提升/补测试 | app/.../AegisHomeBridge.kt:180-197 | navigate() 首页搜索主链路端到端零覆盖 → 投递抽可注入 executor+四用例 | ✅ AD批 |
| AD-324 | P3 | 提升/常量单源 | app/.../TabBar.kt + VerticalTabBar.kt | dp 字面量散落(AD-078/090 UiDimens 谱系外) → 收敛 11 常量 | ✅ AD批 |
| AD-325 | P3 | 提升/无障碍 | app/.../BrowserEngine.kt:84 | textZoom 显式钉 100——大字号用户 web 正文不随系统设置 → 删除回归平台默认+死常量清理 | ✅ AD批 |
| AD-326 | P3 | 提升/数据丢失 | app/.../MainActivity.kt | 进程被系统回收后全部标签丢失(Windows 端有会话恢复) → onSaveInstanceState 存 https URL+activeIndex 最小恢复 | ✅ AD批 |
| AD-327 | P3 | 提升/补测试 | app/src/test/.../BrowserViewModelBehaviorTest.kt | retryCurrentPage/returnToSafeHome/openExternalUrl 三入口零测试 → mock navigator 行为测试 | ✅ AD批 |
| AD-330 | P3 | 提升/可观测性 | webview-adapter/.../AegisWebViewClient.kt:94,307 | 两种 Log tag 混用——`logcat -s` 漏大半客户端日志 → 单一 TAG 常量 | ✅ AD批 |
| AD-332 | P3 | 提升/补测试 | app/.../WebViewEventAssembly.kt:24-179 | 179 行事件装配零测试(internal 可测接缝空挂) → Robolectric+假 Host 8 用例 | ✅ AD批 |

## 3. Rust 策略核心(RS-275..310,36 行)

| ID | 优先级 | 类型 | 位置 | 问题 → 方案 | 闭环 |
|---|---|---|---|---|---|
| RS-275 | P2 | 问题/拦截绕过 | src/util.rs:58-61 | (见 §0) | ✅ RS批 |
| RS-276 | P2 | 问题/防护判定错误 | src/font_norm.rs:120-121 | (见 §0) | ✅ RS批 |
| RS-277 | P2 | 问题/绑定漂移 | bindings/aegis_policy_core.py | (见 §0) | ✅ RS批 |
| RS-278 | P3 | 问题/覆盖缺口 | src/timer_prec.rs:151-158 | performance.mark 返回 entry 未圆整(measure 有处理——同型不对称) → 返回前 aegisRoundEntry | ✅ RS批 |
| RS-279 | P3 | 问题/绕过 | src/timer_prec.rs:152,163,195 | mark/measure/getEntries* 实例级遮蔽——`Performance.prototype.mark.call` 绕过(RS-250 只升三处) → 原型级 defineProperty 保留 descriptor | ✅ RS批 |
| RS-280 | P3 | 问题/剥离绕过 | src/query_strip.rs:214-221 + ext_proxy.rs:164 | `fetch(new URL(...))` 两分支均不命中——追踪参数原样发出(node 实证) → instanceof URL 分支双侧补 | ✅ RS批 |
| RS-281 | P3 | 问题/上限失效 | src/security_policy.rs:115-121 | 扩展名自身超上限时文件名 200 上限被突破 → 截断后二次长度复查(字节边界安全) | ✅ RS批 |
| RS-282 | P3 | 问题/输入无界 | src/ffi/broker.rs:684-699 | evaluate/approve/consume 的 raw_url 无前置上限(URL 三入口有)+redact host 段无界放大 → 64KB 先拒+256B 截断 | ✅ RS批 |
| RS-283 | P3 | 问题/口径漂移 | src/adblock.rs:105 | 入库全 Unicode 折叠 vs 查询侧 ASCII 折叠(RS-259 半面)——İSPAM.com 永不命中 fail-open → to_ascii_lowercase | ✅ RS批 |
| RS-284 | P3 | 问题/双端口径 | src/space_routing.rs:254 | JS matches 对 pattern 无再小写(Rust:103 有防御)——直构大写规则双端判定分叉 → JS 侧 toLowerCase | ✅ RS批 |
| RS-285 | P3 | 问题/兼容 | src/ext_proxy.rs:80,110-111 | endpoint scheme 校验大小写敏感——`HTTPS://` 被静默退化为禁用 → ASCII 不敏感前缀比较 | ✅ RS批 |
| RS-286 | P3 | 问题/语义误导 | src/ffi/broker.rs:440-455 | destroy_session 对不存在 id 也返回 true——拼写错误静默成功 → core 返回 bool(remove().is_some())贯通 FFI | ✅ RS批 |
| RS-287 | P3 | 问题/边界不一致 | src/ffi/broker.rs:278,662 | 惰性清理 `expires_at >= now` 保留已过期条目(RS-156 口径 <= now 即过期) → 统一 pending_expired_at 单源+边界用例 | ✅ RS批 |
| RS-288 | P3 | 问题/口径不一 | src/capability.rs:107-113 | 精确路径不敏感、前缀路径大小写敏感——两分支口径分裂 → 字节级 eq_ignore_ascii_case | ✅ RS批 |
| RS-289 | P3 | 问题/绑定等价类 | src/origin.rs:151-155 | path 无点段折叠/百分号归一——等价编码形态 evaluate/consume 间绑定失败(fail-closed,但与孪生可能分叉) → 契约测试锁定「不归一」+取舍登记 | ✅ RS批 |
| RS-290 | P3 | 问题/双端口径 | src/space_routing.rs:235-240 | JS getHostname(about:blank→'')与 Rust extract_hostname(→'about')对 Domain 规则判定相反 → JS 对齐 Rust 语义 | ✅ RS批 |
| RS-291 | P3 | 问题/类型宽容 | src/executor.rs:172-180 | parameters 非 object 静默落默认空表(RS-229 origin 已类型化) → 类型化错误+三分支用例 | ✅ RS批 |
| RS-292 | P3 | 问题/健壮性 | src/shield.rs:146,173,202,229,242 | canvas 三块+hardwareConcurrency 无 typeof 守卫——worker 注入抛未捕获 ReferenceError(即探测信号) → 守卫+try 包注册行 | ✅ RS批 |
| RS-293 | P3 | 问题/覆盖失效 | src/letterbox.rs:176-183 | DPR 只查 window 自有 descriptor——原型定义引擎静默跳过(innerWidth 组已原型优先) → aegisResolveProp 同款 | ✅ RS批 |
| RS-294 | P3 | 问题/失效陷阱 | src/broker.rs:149-171 | create_session 接受 ttl=0 仍返回 Some——钳制只在 FFI 层,嵌入式直调拿到即刻失效会话 → 核心层 ZERO 拒绝 | ✅ RS批 |
| RS-295 | P3 | 问题/口径漂移 | src/query_strip.rs:191 | changed 分支返回 u.toString()——连带归一 scheme/host 大小写/尾斜杠,超出「仅剥离」语义且与 Rust 手术路径漂移 → 纯字符串手术单源 | ✅ RS批 |
| RS-296 | P3 | 问题/双读不一致 | src/timer_prec.rs:163-198 | 同一 entry 直读与 getEntries* 两次圆整引入不同 jitter——双通道比对即检出 → WeakSet 单次圆整 | ✅ RS批 |
| RS-297 | P3 | 问题/注释残句 | src/c_abi/navigation.rs:65-67 | RS-239 编辑残留断句「宿主缓冲,非 'static)。」 → 删 | ✅ RS批 |
| RS-298 | P3 | 问题/注释失实 | src/broker.rs:212 | 「清理过期会话(LRU 淘汰)」实为 TTL 驱动(RS-108 口径相反) → 如实改述 | ✅ RS批 |
| RS-299 | P3 | 问题/注释失实 | src/letterbox.rs:53-56 | 描述 CSS padding 视觉 letterbox(实现仅圆整 JS 报告值) → 如实+防复发断言 | ✅ RS批 |
| RS-300 | P3 | 提升/补测试 | src/ffi/broker.rs:193-199 | 授权账本容量 fail-closed 只有白盒直测(RS-136)——公共路径零覆盖 → 注入小容量走公共 evaluate | ✅ RS批 |
| RS-301 | P3 | 提升/补测试 | src/ffi/broker.rs:550-570 | consume 成功+满账本收口语义(deny 后二次 consume 为 nonce_replay)零锁定 → 补测试 | ✅ RS批 |
| RS-302 | P3 | 提升/单源 | src/per_site_seed.rs:72-79 | derive_hex 手写逐字节 hex 编码(RS-262 残留) → util::hex_encode | ✅ RS批 |
| RS-303 | P3 | 提升/单源 | src/ffi/mod.rs:284-296 | hex_seed_to_bytes 手写 nibble 循环 → hex_decode+try_into+往返断言 | ✅ RS批 |
| RS-304 | P3 | 提升/一致性 | src/js_inject.rs:146-155 | 可注入名单 8 项 vs 管线 9 阶段——ProtectionMode 不可注入 → 补 impl+PerSiteSeed 参数化取舍登记 | ✅ RS批 |
| RS-305 | P3 | 提升/热路径 | src/command_bar.rs:287-297 | JS 搜索每按键每条目 3 次 toLowerCase(RS-039 孪生) → 构造期预计算小写缓存 | ✅ RS批 |
| RS-306 | P3 | 提升/测试单源 | tests/vectors.rs:89-113 | b64_encode 与 update_manifest 测试模块逐字节重复(25 行×2) → 共享单源 | ✅ RS批 |
| RS-307 | P3 | 提升/性质测试 | src/matcher.rs:262-338 | glob_subsumes 代数性质(传递性/可靠性)零覆盖——性质破坏即策略语义破坏 → proptest 256 cases | ✅ RS批 |
| RS-308 | P3 | 提升/向量消费 | contracts/vectors/approvals-replay-and-expiry.json | 五条重放/过期/换 scope 向量全仓零代码消费(死数据) → Rust 测试全量消费断言 | ✅ RS批 |
| RS-309 | P3 | 提升/可观测 | fuzz/(9 target) | fuzz 编译性只靠审计批次手工验证——target 间腐化无信号 → core-rust.yml 周度 cargo fuzz build 冒烟 job | ✅ SP批(=SP-240) |
| RS-310 | P3 | 提升/安全可观测 | src/c_abi/(12 导出符号) | C ABI 导出面无冻结清单——新增导出静默扩大跨语言攻击面 → include_str 枚举==冻结 Vec 测试 | ✅ RS批 |

## 4. Python/契约/发布链(PY-260..289,30 行)

| ID | 优先级 | 类型 | 位置 | 问题 → 方案 | 闭环 |
|---|---|---|---|---|---|
| PY-260 | P2 | 问题/e2e 模拟正确性+并发 | agent/tests/redteam_e2e_test.py:198-202 | (见 §0) | ✅ PY批 |
| PY-261 | P2 | 问题/工具正确性 | release/native_artifact_manifest.py | (见 §0) | ✅ PY批 |
| PY-262 | P2 | 问题/正确性+互操作 | release/update_verifier.py:53-54,109 | (见 §0) | ✅ PY批 |
| PY-263 | P2 | 问题/门禁缺口 | .github/workflows/legacy-python-guard.yml | (见 §0) | ✅ PY批+SP批 |
| PY-264 | P3 | 提升/一致性 | release/verify_release.py:70 | .txt 强校验路径整文件进内存(PY-191 孪生) → 复用 write_checksum_json.sha256_file 流式 | ✅ PY批 |
| PY-265 | P3 | 提升/死代码 | scripts/sync_versions.py:26 | replace_assignment 生产零调用(PY-216 残留) → 迁测试侧 | ✅ PY批 |
| PY-266 | P3 | 问题/工具健壮性 | release/build_metadata.py:32 | 缺 version.properties 裸 FileNotFoundError 原始栈(PY-028 孪生) → is_file 预检+干净退出 2 | ✅ PY批 |
| PY-267 | P3 | 问题/工具健壮性 | scripts/sync_versions.py:97 | release.json 缺失/损坏裸栈(与本文件 RuntimeError 干净口径相悖) → 包捕获带文件名上下文+负例 | ✅ PY批 |
| PY-268 | P3 | 提升/一致性 | scripts/sync_versions.py:100 等四处 | 四处 JSON 写入缺 `newline="\n"`——Windows 本地重生成即 CRLF 漂移、git diff 假红(PY-232 半面) → 四处统一 | ✅ PY批 |
| PY-269 | P3 | 提升/死配置 | pyproject.toml:52-54 | tests/** 三条 per-file-ignores 不在 select 面——永不生效且注释仍称「测试豁免单源」 → 删除+改述 | ✅ PY批 |
| PY-270 | P3 | 提升/注释失实 | bandit.yaml:13 | B406「ElementTree 存量(sync_versions.py)」为不存在的事实(活跃树零 ElementTree) → 删除 | ✅ PY批 |
| PY-271 | P3 | 提升/重复门禁 | validate_release.py:152-166 | 资产存在性循环与 check_shell_manifest_consistency 重复报错(前者是后者严格子集) → 删循环单点保留 | ✅ PY批 |
| PY-272 | P3 | 问题/守卫不对称 | contracts/codegen/validate_vector_schemas.py:59,66 | valid 侧 _load 裸 loads——缺文件/坏 JSON 原始栈(invalid 侧有守卫) → 三处统一包捕获+负例 | ✅ PY批 |
| PY-273 | P3 | 问题/退出码语义 | release/tools/verify_manifest/verify_manifest.py:131-136 | min_version CLI 输入错误误报「更新清单验证失败」exit 1(违反 SP-024/025 用法=2 约定) → 预校验 exit 2 | ✅ PY批 |
| PY-274 | P3 | 提升/豁免口径 | bandit.yaml:15 | B110(except:pass) 全局面豁免远宽于事实面(现存 1 处) → 行级 nosec+移出 skips | ✅ PY批 |
| PY-275 | P3 | 问题/工具退出语义 | scripts/build_review_package.py:379-380 | 无参调用 print_help 返回 0——CI 误裸调用静默「通过」 → 互斥组 required=True(argparse exit 2) | ✅ PY批 |
| PY-276 | P3 | 提升/文案失实 | scripts/build_review_package.py:296 | 评审包 README 仍宣称「Windows Python」为源代码(ADR-009 已归档) → 改「Windows C#(附 legacy 归档基线)」 | ✅ PY批 |
| PY-277 | P3 | 提升/死条目 | scripts/build_review_package.py:97 | AegisBrowser-Setup-2.1.6.exe 双重死规则(.exe 已被后缀整类排除+版本钉死 2.1.6) → 删+注释 | ✅ PY批 |
| PY-278 | P3 | 提升/写入原子性 | scripts/sync_versions.py:37,52,100 + write_checksum_json.py:69 | Python 侧写文件非原子——中途崩溃留截断 csproj/清单(C# 已有 AtomicWriteAllText 单源) → scripts/atomic_write.py(tempfile 同目录+os.replace) | ✅ PY批 |
| PY-279 | P3 | 问题/校验缺口 | release/update_verifier.py:40 + contracts/schemas/update-manifest.schema.json | semver 预发布段接受空标识符(`2.2.0-beta.` 合法——违反 SemVer §9.3;PY-184 只堵前导零) → 正则收紧+schema 同步+拒绝向量 | ✅ PY批 |
| PY-280 | P3 | 问题/校验弱 | release/tools/verify_artifact_set/verify_artifact_set.py:57 | sha 只验长度不验十六进制——结构损坏误呈现为「内容篡改」 → fullmatch [0-9a-fA-F]{64} | ✅ PY批 |
| PY-281 | P3 | 提升/生成确定性 | scripts/gen_jsapi_schema.py:61,211-216 | 类注册表跨文件同名静默首胜+glob 顺序依赖文件系统——生成漂移「灵异红」(PY-255 只覆盖方法级) → sorted 固定序+撞名 stderr 告警 | ✅ PY批 |
| PY-282 | P3 | 提升/口径一致 | agent/tests/redteam_e2e_test.py:247-251 | e2e 层宽松 fromisoformat(裸日期/无时区一律接受)——真链已收紧(PY-228)模拟器却放行 → 复用 RFC3339 锚定 | ✅ PY批 |
| PY-283 | P3 | 提升/补测试 | tests/python/release_chain_test.py | 「缺 SBOM」退出路径零执行锚(SP-031 元门禁声明无执行) → 补 SystemExit 用例 | ✅ PY批 |
| PY-284 | P3 | 提升/测试锚定 | tests/python/release_chain_test.py:497-506 | IMPLEMENTED 映射纯文案——被引测试改名门禁仍绿 → (module,test_name) 二元组+getattr 反射断言 | ✅ PY批 |
| PY-285 | P3 | 问题/检测逃逸面 | agent/tests/redteam_test.py:37 | expected 正则 `[a-z_]+` 锚定引号——`"allow-v2"` 类值整个声明不匹配、静默逃出全 deny 断言 → 全捕获逐个断言+负例 | ✅ PY批 |
| PY-286 | P3 | 提升/argparse 口径 | release/tools/ 四处 main | 四工具手工 argv 无 -h/--help/类型校验(PY-029 半面) → 迁 argparse 保 0/1/2 退出码语义 | ✅ PY批 |
| PY-287 | P3 | 提升/一致性 | pyproject.toml:61 | 裸 pytest 只收 tests/python 漏 agent/tests 33 项——本地假全集 → testpaths 双根 | ✅ PY批 |
| PY-288 | P3 | 问题/守卫缺失 | contracts/codegen/generate_csharp.py:232 + generate_kotlin.py:220 | 生成器 main 循环裸 json.loads——坏 schema 原始栈(PY-196 同数据已守卫) → 包捕获+fail 报告+负例 | ✅ PY批 |
| PY-289 | P3 | 问题/生成正确性缺口 | contracts/codegen/generate_csharp.py:101 + generate_kotlin.py:106 | enum 常量名派生无去重——`"a-b"`/`"a.b"` 归一后同名,生成成功下游编译才炸 → 生成前查重 ValueError+负例 | ✅ PY批 |

## 5. Web 资产/文档(WB-176..214,38 行)

| ID | 优先级 | 类型 | 位置 | 问题 → 方案 | 闭环 |
|---|---|---|---|---|---|
| WB-176 | P2 | 问题/功能缺陷 | shared/shell/start.import.js:277 | running 态点「关闭」按钮静默中断向导——桥任务照跑结果丢弃(WB-056 只堵 Escape 路径) → close() 开头守卫+runImport 禁用按钮配对 | ✅ WB批 |
| WB-177 | P2 | 问题/数据丢失 | shared/shell/start.snake.js:137-138 | persistBest 盲写内存 best——双 NTP 实例后关者把陈旧 best 覆盖回去 → 写前读盘取 max | ✅ WB批 |
| WB-178 | P3 | 问题/版本失实 | README.md:84 | 当前版本 beta.50 vs 单源 beta.52(漂移两版) → 改「见 shared/version.properties 单源」根治逐版手更 | ✅ WB批 |
| WB-179 | P3 | 问题/语义残留 | shared/shell/start.import.js:234 | modal display:flex 但 hidden 属性残留——语义声明隐藏与视觉可见矛盾(WB-137 同病漏改) → hidden 配对翻转 | ✅ WB批 |
| WB-180 | P3 | 问题/状态机竞态 | shared/shell/start.main.js:47-50 | 慢桥下引擎菜单迟到 getEngine 回调重开已收起菜单+aria 失真 → 代次 token,仅最新 toggle 可展开 | ✅ WB批 |
| WB-181 | P3 | 问题/布局缺陷 | shared/shell/start.css:2 | html,body overflow:hidden——矮视口内容硬裁切不可滚(主流 NTP 均可滚) → overflow-y:auto | ✅ WB批 |
| WB-182 | P3 | 问题/注释与行为失实 | shared/shell/start.css:51 | `.search input` outline:0 特异度压过全局 :focus-visible——WB-109 注释声称「现继承全局焦点描边」不成立 → 删 outline:0 | ✅ WB批 |
| WB-183 | P3 | 问题/错误处理不一致 | shared/shell/start.main.js:179-181 | openUrl 无 try/catch(同文件 go() 有)——Android 桥序列化抛错直接逃逸 → 对齐包捕获+bridgeError 留痕 | ✅ WB批 |
| WB-184 | P3 | 提升/可达性对比度 | shared/shell/start.css:117-118 | .bm-empty/.bm-add 名 1.9:1 远低于 AA(WB-047 只修 footer) → alpha≥0.92+实测值注记 | ✅ WB批 |
| WB-185 | P3 | 提升/可达性对比度 | shared/shell/start.css:303 | .veil-sub 2.5:1 低可视——蛇局操作说明难读 → alpha≥0.88+veil-title 复测注记 | ✅ WB批 |
| WB-186 | P3 | 提升/可达性键盘 | shared/shell/start.snake.js:449-455 | 浮层内聚焦按钮时 Space/Enter 被全局监听抢占为暂停+preventDefault → BUTTON 放行 | ✅ WB批 |
| WB-187 | P3 | 提升/焦点管理 | shared/shell/start.main.js:130-135 | selectEngine 后焦点遗留已隐藏菜单项(WB-045 只修 Escape 路径) → pillEl.focus() 归还 | ✅ WB批 |
| WB-188 | P3 | 提升/状态语义 | shared/shell/start.main.js:229-230 | 壁纸圆点选中态仅类名——读屏无法感知当前壁纸 → aria-pressed 翻转+容器 role=group | ✅ WB批 |
| WB-189 | P3 | 提升/死代码 | shared/shell/start.js:155,149 | importHistory/importBookmarks 死 cb 形参(WB-002 只落地 thenable)+start.import 恒假分支 → 删 | ✅ WB批 |
| WB-190 | P3 | 提升/单源兜底 | shared/shell/start.main.js:165-166 等 | TIMING 兜底字面量与 AegisTiming 单源无一致性门禁——单源改值静默分叉 → deepEqual 锁死三处 | ✅ WB批 |
| WB-191 | P3 | 提升/补测试 | shared/shell/snake.test.js | 静音偏好 localStorage 往返零覆盖 → 补往返用例(预置读取+点击写回) | ✅ WB批 |
| WB-192 | P3 | 提升/测试质量 | shared/shell/snake.test.js:209-215 | 「最高分初始加载」零断言恒通过——伪装覆盖 → 补断言 | ✅ WB批 |
| WB-193 | P3 | 提升/补测试 | tests/ui-regression/start_import.test.mjs | importScan 同步抛错路径无用例(只测 rejected Promise 形态) → 补第三形态 | ✅ WB批 |
| WB-194 | P3 | 问题/注释失实 | tests/ui-regression/helpers.mjs:33 | 「chromium.webview 形态」为 pywebview 时代残留措辞 → 改「bridge.webview(注入为 window.chrome)」 | ✅ WB批 |
| WB-195 | P3 | 提升/一致性收敛 | tests/ui-regression(跨端桥 op 词表) | start.js 14 op 与 NtpBridge.cs/AegisHomeBridge.kt 集合零对账——新增 JS op 漏宿主 case 静默 TTL 兜底(WB-037) → ui-regression 断言集合覆盖 | ⏸ 暂缓(跨端断言面,留下轮) |
| WB-196 | P3 | 问题/文档失实 | tests/README.md:13 | snake.test.js 标「node:test」失实(自研 assert runner,ci.yml:51 直跑) → 改述+正确命令(≡SP-232) | ✅ WB批 |
| WB-197 | P3 | 问题/命令失实 | README.md:55-61 | Windows 命令漏 `cd windows` 前缀(照抄必失败)+Android 漏 :contracts: 模块 → 与 CLAUDE.md 逐字对齐 | ✅ WB批 |
| WB-198 | P3 | 问题/文档失实 | README.md:72-77 | 审计轮次仅列两轮(漏 09-07/10-01),同文件却引用 10-01 编号 → 四轮口径+台账链接 | ✅ WB批 |
| WB-199 | P3 | 问题/索引缺口 | docs/README.md:24-31 | 首轮 09-07 台账两列表均缺席(声称「全部历史审计报告」) → 历史归档补行(≡I-11) | ✅ WB批 |
| WB-200 | P3 | 问题/索引缺口 | docs/README.md:9-20 | KNOWLEDGE_BASE 与 12 份顶层文档在全部索引零引用(声称索引全量) → 现行表补行+调研件点名 | ✅ WB批 |
| WB-201 | P3 | 问题/版本失实复发 | docs/KNOWLEDGE_BASE.md:93-94 | 基线 beta.49 硬编码(SP-054 处方只换字面量,三轮后再漂移) → 引单源删硬编码根治 | ✅ WB批 |
| WB-202 | P3 | 问题/文档失实 | docs/KNOWLEDGE_BASE.md:79-81 | ruff 0.16.3/mypy 2.3.0 是 legacy 锁值+「根 ruff.toml」不存在(活跃配置在 pyproject) → 引 requirements-ci.in+pyproject | ✅ WB批 |
| WB-203 | P3 | 问题/过期硬数据 | docs/KNOWLEDGE_BASE.md:529 | 「正确包大小 49,237,446 字节」版本未限定——按此校验必把新包误判异常 → 以构建日志为准 | ✅ WB批 |
| WB-204 | P3 | 问题/潜伏守卫缺陷 | shared/shell/start.import.js:286 | 弹层未打开时 `style.display('') !== 'none'` 恒真——首次 Escape 即对未开启向导执行 close(WB-133 同模式) → hidden 口径+无副作用用例 | ✅ WB批 |
| WB-205 | P3 | 提升/补测试 | shared/shell/start.js:168-183 | error/unhandledrejection 上报通道零回归锁(WB-140 只移动代码无测试要求) → helpers 记录器注入+三用例(五参/前缀/自抛被吞) | ✅ WB批 |
| WB-206 | P3 | 提升/测试重构 | tests/ui-regression/ 两文件 | el()/timers/document 桩双源语义漂移中(WB-127 只收敛桥桩) → 下沉 helpers.mjs 单源 | ✅ WB批 |
| WB-207 | P3 | 提升/文档补全 | tests/README.md:10-20 | 分层表缺 C# 双套件/Android 四模块/Rust vectors 三端入口 → 补三行 | ✅ WB批 |
| WB-209 | P3 | 提升/治理 | CONTRIBUTING.md:74-80 | 质量门槛缺 contracts.yml 五脚本+agent/tests——本地全绿推 CI 即红 → 补齐(I-10) | ✅ WB批 |
| WB-210 | P3 | 提升/文档补全 | CONTRIBUTING.md | 契约重生成+漂移门禁命令块缺失(S-19 文档面) → 独立命令块 | ✅ WB批 |
| WB-211 | P2 | 提升/文档失实 | docs/runbooks/windows-run-guide.md:12-14 | 裸 dotnet 命令=改写 NuGet 锁地雷(10-01 收尾批漏网,I-26) → -r+锁模式+SP-220 提示行 | ✅ WB批 |
| WB-212 | P3 | 提升/治理 | CONTRIBUTING.md | 云端验证纪律未随新纪律入文 → 「云端验证纪律」摘要块(引 CLAUDE.md 同源) | ✅ WB批 |
| WB-213 | P3 | 提升/威胁建模 | docs/threat-model/trust-boundaries.md:11 | 受信虚拟主机表缺 geo.aegis.local(CS-334 P1 级安全面的文档面) → 补行(资产根映射/Deny 语义/信任假设)+architecture-overview 同步(I-16) | ✅ WB批 |
| WB-214 | P3 | 问题/枚举失实 | README.md:45-47 | workflow 枚举含不存在的「windows」且漏 ci.yml(≡S-10) → 按 13 个实文件改写 | ✅ WB批 |

## 6. CI/根配置/盲区(SP-222..260,35 行)

| ID | 优先级 | 类型 | 位置 | 问题 → 方案 | 闭环 |
|---|---|---|---|---|---|
| SP-222 | P2 | 问题/门禁错位 | .github/workflows/compat.yml | 每周 WebView2 兼容探测对象全是归档栈——正典 C# 零 Runtime 兼容信号(≡I-15) → windows-canonical-stack job(build+双套件周基线) | ✅ SP批 |
| SP-223 | P2 | 问题/发布制品口径漂移 | .github/workflows/release-android.yml:134-145 | 冒烟链 16K 对齐 RUSTFLAGS 未进发布链——发货 .so 与验证制品不一致,Android 15+ 16K 页设备安装失败风险 → RUSTFLAGS+readelf LOAD 段对齐断言 | ✅ SP批 |
| SP-224 | P2 | 问题/文档即地雷 | CONTRIBUTING.md:70-77 | test 行裸 dotnet+cargo 缺 --locked——照文档执行改写 NuGet 锁/Cargo.lock(S-03/S-06 文档面,CLAUDE.md 已修) → 补 -r+锁模式+--locked --all-features | ✅ 主审计收尾 |
| SP-225 | P3 | 问题/门禁覆盖 | .github/workflows/contracts.yml:8-15 | push paths 不含 tests/python——仅改测试的 push 跳过发布链 pytest(PY-222 接线漏触发面) → 补 paths+validate_release.py | ✅ SP批 |
| SP-226 | P3 | 问题/口径漂移 | contracts.yml:97 + release-core.yml:51-52 | cargo test 三口径(缺 --all-features)——feature 门控 bin 在契约/发布链零单测(SP-183 只统一 clippy) → 统一 | ✅ SP批 |
| SP-227 | P3 | 问题/门禁面不一致 | scripts/active_tree_gates.py | bandit 面缺 validate_release.py/tests/bindings(SP-208 ruff 面已含,S-07) → BANDIT_TARGETS 对齐 | ✅ 主审计收尾 |
| SP-228 | P3 | 问题/可观测性 | .github/workflows/supply-chain.yml:59 | dev 锁漏洞 `\|\| true` 静默吞(注释却称「告警」) → `\|\| echo ::warning::` | ✅ SP批 |
| SP-229 | P3 | 问题/注释失实 | .gitignore:50-57 | 「dist/ 无全局规则」失实(:32 即全局)+legacy 子规则冗余 → 删冗余+更正注释 | ✅ SP批 |
| SP-230 | P3 | 问题/注释失实 | legacy-python-guard.yml:95 | 「ignore 随根 pyproject 单源」失实——归档栈扫描就近消费本地 ruff.toml → 更正 | ✅ SP批 |
| SP-231 | P3 | 问题/死步骤 | ci.yml:52-54 | 纯 echo「测试报告」占位步骤(09-02 已删同物种) → 删 | ✅ SP批 |
| SP-233 | P3 | 问题/门禁弱化 | release-windows.yml:186-188 | GeoGebra 缺失 warn-only——上游 prepare fail-closed 打包侧放水,静默无画板发布 → throw | ✅ SP批 |
| SP-234 | P3 | 问题/缓存键失真 | legacy-python-guard.yml:54-56 | cache-dependency-path 含未安装的 requirements.txt 漏主安装输入 requirements-lock.txt → 改 lock+dev | ✅ SP批 |
| SP-235 | P3 | 提升/触发完整性 | ci.yml:16-20 | 13 个 workflow 中唯一无 workflow_dispatch 且 push 无 paths——docs 改动全量跑 → 补 dispatch+paths | ✅ SP批 |
| SP-236 | P3 | 提升/触发完整性 | core-rust.yml:6-8 | push paths 不含其消费的 cargo-audit 复合 action → 补 | ✅ SP批 |
| SP-239 | P2 | 问题/门禁缺口(PY-263 实施面) | contracts.yml + legacy-python-guard.yml | 活跃树 ruff/bandit 接线:两 workflow 调 active_tree_gates.py(ci 锁安装,归档面隔离) | ✅ SP批 |
| SP-241 | P3 | 问题/同型未修完 | native-policy-artifacts.yml:43-99 | build-windows 无 setup-dotnet+无 NuGet 缓存(PY-065/SP-196/204 第五处漏网) → 补 | ✅ SP批 |
| SP-242 | P3 | 提升/韧性 | supply-chain.yml | pip/cargo audit 无 schedule——仓库静默期新披露 CVE 不可见 → 周一 cron | ✅ SP批 |
| SP-243 | P3 | 提升/文档补全 | PULL_REQUEST_TEMPLATE.md | scripts 行缺五契约脚本+agent/tests → 补(S-19 模板面) | ✅ SP批 |
| SP-244 | P3 | 提升/依赖治理 | contracts.yml:107 + release-windows.yml:57 | actions/cache 双主版本并存(v4.3.0 vs v6.1.0)且 v4 无 SP-178 注记 → 统一 v6.1.0(ls-remote 核对) | ✅ SP批 |
| SP-245 | P3 | 提升/依赖治理 | .github/dependabot.yml | 五组无 groups——逐 bump 单 PR 噪声(#27/#35/#39 hash 锁坏 PR 前科) → 四生态 minor-and-patch 分组(pip 除外注明) | ✅ SP批 |
| SP-246 | P3 | 提升/供应链 | supply-chain.yml | 三生态只扫 pip/cargo——NuGet 零漏扫 → dotnet list --vulnerable fail-closed(gradle TODO 登记) | ✅ SP批(云端实证:list 同传 EnableWindowsTargeting) |
| SP-247 | P3 | 提升/治理 | .github/CODEOWNERS | 敏感路径清单缺 /tests/(门禁定义面) → 补 | ✅ SP批 |
| SP-248 | P3 | 提升/忽略缺口 | .gitignore | 缺 .vs//*.user/*.suo/*.log(VS 本地开发必产,SP-097 只补 Python 缓存) → 补 | ✅ SP批 |
| SP-249 | P3 | 提升/制品链完整性 | release.yml:239-242 | 评审包 zip 是唯一不在任何 SHA256SUMS 内的发布资产(仅被 attest 覆盖) → 独立 .sha256 随 publish | ✅ SP批 |
| SP-250 | P3 | 提升/口径钉固 | legacy-python-guard.yml:73 | types-pywin32 完全无 pin——mypy 桩随 PyPI 浮动假红 → 钉 312.0.0.20260928 | ✅ SP批 |
| SP-251 | P3 | 提升/打磨 | 四处 pin-check timeout 45/60/60/40 | 实际 <1 分钟四档不一 → 统一 10(编排)/5(子流) | ✅ SP批 |
| SP-252 | P3 | 提升/成本 | android-quality.yml 头注释 | 「windows-latest 自带 JDK 21」理由已失效(setup-java 显式 temurin) → 更正+ubuntu 迁移 TODO(不实际迁移) | ✅ SP批 |
| SP-253 | P3 | 提升/治理 | android-quality.yml:83 + compat.yml:75 | artifact retention 两套口径(90d 默认 vs 7d)无登记依据 → 排障 14/基线 30 注记 | ✅ SP批 |
| SP-254 | P3 | 提升/一致性 | legacy-python-guard.yml:62-73 | guard 装 dev 锁跑活跃树门禁——PY-220 双源漂移随时间复发 → 活跃面改装 ci 锁(--require-hashes) | ✅ SP批 |
| SP-255 | P3 | 提升/治理(I-03) | 全仓无行数红线门禁 | 「新 ≤300/改造 ≤500」纯口头(AD-101/102 靠人工) → scripts/check_file_sizes.py ratchet+86 项基线+contracts 接线 | ✅ SP批 |
| SP-256 | P3 | 提升/文档工具(I-19) | 70+ 份 md 零链接校验 | WB-033 类死链只能人工发现 → scripts/check_markdown_links.py+contracts 接线 | ✅ SP批 |
| SP-257 | P3 | 提升/一致性(I-24) | 仓库根无 .editorconfig | 五栈行尾/缩进/最终换行零底线约定(仅 android 子目录有) → 根级单源+android 继承微调 | ✅ SP批 |
| SP-258 | P3 | 提升/可观测(I-12) | 三端零覆盖率度量 | pytest/gradle/dotnet 无 coverage——补测优先级只能靠人工审计 → 覆盖率报告起步 | ⏸ 暂缓(coverage.py 入锁需 pip-compile 重锁,留下轮) |
| SP-259 | P3 | 提升/制品链完整性(I-08) | release-android.yml apk_entries | Android 发布链无画板资产断言(Windows 侧有)——prepare 失败静默缺画板出厂 → assets/geogebra/.../GeoGebra.html 断言 | ✅ 主审计收尾 |
| SP-260 | P3 | 问题/供应链可观测 | 仓库设置层(GitHub 动态 workflow「Automatic Dependency Submission (NuGet)」) | 动态依赖提交在 ubuntu restore net10.0-windows 必失败 NETSDK1100(PR #60 云端首跑实证;master 同病)——NuGet 依赖图静默停更 → 仓库设置处置:禁用该面(依赖图 NuGet 以发布 SBOM 为准)或自管 workflow 带 EnableWindowsTargeting;非仓库文件可修 | ⏸ 登记待处置(设置层) |

## 7. 批次日志与闭环统计

| 批 | 提交 | 范围 | 项数 | 闭环 |
|---|---|---|---|---|
| PY 批 | fix(release) | scripts/release/contracts/agent/tests-python/validate_release/pyproject/bandit | 30 | 30 |
| CS 批 | fix(windows) | windows/(含 Directory.Build.props 单源+warnaserror) | 42 | 42 |
| AD 批 | fix(android) | android/ 四模块 | 36 | 36(316/317 由 SP 批实施) |
| RS 批 | fix(rust) | core/rust-policy-core(含 bindgen 重生成入库) | 36 | 36(309 由 SP 批实施) |
| WB 批 | fix(web,docs) | shared/tests-ui-regression/docs/README/CONTRIBUTING | 38 | 37(195 暂缓) |
| SP 批 | fix(ci) | .github/.gitignore/.editorconfig/新门禁脚本 | 34+1 | 33+1(S-08 断言=I-08 收尾;258 暂缓;260 待处置) |
| 纪律批 | docs | CLAUDE.md 验证纪律节+CONTRIBUTING 口径 | — | — |

**云端验证（本 PR #60 起，验证纪律首轮执行）**:Core-Rust/CI/Agent-Redteam 首轮即绿;红灯 2 项(android-37 平台包渠道、dotnet list 缺 EnableWindowsTargeting)当轮修复并回写为 AD-317/SP-246 的实证口径;SP-260 为云端首跑新登记。**经 18 轮推送迭代红灯全清,七 workflow(contracts/ci/core-rust/android-quality/supply-chain/agent-redteam/native-policy-artifacts)全绿**。云端迭代额外产出(均回写代码):proptest 传递性反例实证 covers 缺 ε-转移(RS-307 修根因+性质契约据实改为可靠性/自反性)、AD-303 数字外跳 Toast 分支永不可达(tel:10086 被 port 规则误判,拦截前移)、ExternalIntentRateLimit/NavigateDebounce 冷启动锚点缺陷(吞首条真实外链)、NuGet 漏扫与行数基线四轮校准、盲写测试与真实 API 的十余处错位对齐。

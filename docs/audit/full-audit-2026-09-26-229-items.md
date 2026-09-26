# Aegis 全仓第二轮审计——229 项新发现（2026-09-26）

**范围**：接续 docs/audit/full-audit-2026-09-23-1000-items.md（1115 项，彼时已落地 783）之后的**新一轮全仓新鲜扫描**——六区并行审计代理逐文件核对当前代码状态（含 A5 批之后），凡与 CS-001..290 / AD-001..210 / RS-001..205 / PY-001..172 / WB-001..100 / SP-001..138 已登记条目相同或高度相似的一律剔除。
**方式**：6 路并行审计（Windows C# / Android / Rust 核心 / Python·CI·契约·发布链 / Web 资产·文档 / 补充盲区），每项带 file:line 证据与具体修复方案。
**总量**：**229 项**（CS-291..333 共 43 / AD-211..251 共 41 / RS-206..237 共 32 / PY-173..215 共 43 / WB-101..132 共 32 / SP-139..176 共 38；P1×19 / P2×59 / P3×151）。
**结构说明**：多项发现是既往修复的「孪生半面」（一侧已修、另一侧未同步）或既往声明的「文档失实」——本轮按新位置/新问题独立立项。

> 编号体系：延续 2026-09-23 轮（CS=C# 正典栈，AD=Android，RS=Rust 策略核心，PY=Python/CI/契约/发布链，WB=Web 资产+文档，SP=补充盲区）。
> 优先级：P1=必须（缺陷/安全/门禁失效），P2=应该（正确性/一致性/重要测试），P3=可以（打磨/补测/归置）。
> 每行格式：`ID | 优先级 | 类型 | 位置 | 问题 → 方案`。

---

## 0. P1 汇总（19 项，跨六区）

| ID | 优先级 | 类型 | 位置 | 问题 → 方案 |
|---|---|---|---|---|
| CS-291 | P1 | 安全/fail-open | windows/.../Chrome/InPrivateWindow.xaml.cs:21 + Broker/BrowserPolicyBroker.cs:37 | KillSwitch 是每个 broker 的实例属性：设置窗触发主窗 broker 的开关，每个无痕窗口 `new BrowserPolicyBroker()` 自带独立 KillSwitch 永不触发——紧急终止后无痕窗口导航/下载/批准链完全不受冻结 → KillSwitch 改进程级共享单例（静态状态或单实例注入），补跨窗口联动测试 |
| CS-292 | P1 | 功能缺陷 | windows/.../WebView/HostWebView.cs:75-80 + Chrome/InPrivateWindow.xaml.cs | HostWebView 对 NewWindowRequested 一律 Handled=true 后转发事件，但 InPrivateWindow 零订阅——无痕窗口内 target=_blank 点击无任何反应 → InPrivate CreateRuntime 中订阅 `runtime.NewWindowRequested += url => _tabs.NewTab(url)`+逻辑级测试 |
| AD-211 | P1 | 安全/日志泄敏 | android/.../AegisWebViewClient.kt:240 | denied() 只对 url 参数走 LogRedact，但 reason.detail 本身内嵌完整明文 URL（AndroidBroker deny("url_policy", "拒绝 URL: $rawUrl") 直接拼原文）→ AD-004 脱敏被整链绕过，query 中 token/搜索词仍入 logcat → detail 组装处即用脱敏值，或日志面对 reason.detail 一并 redact+断言测试 |
| AD-212 | P1 | 指纹防护缺陷 | android/.../WebViewHardening.kt:186-196 | toDataURL 噪声用 ctx.putImageData 破坏性写回活画布：二次读同画布结果不同（噪声注入自身可检测，RS-025 修了 Rust 侧 Android 未修）；页面后续渲染被永久污染 → 离屏 canvas 副本加噪后仅用于返回值，不动原 ctx |
| AD-213 | P1 | 安全/URL 混淆 | android/.../OriginPolicy.kt:55-60 | IPv4 备用编码判定漏两类：`0177.0.0.1`（4 段全数字即放行，inet_aton 按八进制=127.0.0.1）、`0x7f.1`（0x 判定仅整串）——Chromium 解析归一后可命中白名单 127.0.0.1 → 数字段前导零且长度>1 拒绝、0x 逐段拒绝；补向量 |
| AD-214 | P1 | 生命周期/泄漏 | android/.../SecureWebViewFactory.kt:144-149 | tearDown 在 destroy() 前未从父容器 detach——关闭激活标签与 onDestroy 全量销毁全部命中「attached destroy」，Chromium 资源泄漏 → 序列首部加 `(webView.parent as? ViewGroup)?.removeView(webView)` |
| RS-206 | P1 | 防护绕过 | core/rust-policy-core/src/shield.rs:90,117,144 | canvas 三通道噪声前置 `const ctx = this.getContext('2d'); if (ctx)` 门禁：WebGL 上下文画布 getContext('2d') 返回 null → 直接无噪声回退（WebGL 画布恰是主流指纹向量）；无上下文画布被永久锁定 2d → 删除该门禁（drawImage(this) 对任意源画布可用，离屏副本自取 2d 上下文），补 WebGL 画布噪声回归 |
| PY-173 | P1 | 门禁失效 | .github/workflows/release.yml:199-207 | 去重后重生成清单探测改名前文件名：dedup 把 SHA256SUMS.json 改名为 android-SHA256SUMS.json 后 `[ -f dist/android/SHA256SUMS.json ]` 永假 → android 摘要清单完全不重生成，发布物仍引用旧名 build-metadata.json，verify_checksum_json 必失败 → 重生成循环探测改名后命名 |
| PY-174 | P1 | 发布链死锁/审批绕过 | .github/workflows/release-windows.yml:154-169 | workflow_call 路径调用方只授 contents: read，`gh release create` 必 403 → build job 失败整链死亡；workflow_dispatch 选 v* tag 时 job 级 contents: write 生效可绕过编排器 verify-gate 与 release environment 审批直接发布 → 删除该步骤，发布统一收口 release.yml publish |
| PY-175 | P1 | 死门禁 | release/verify_release.py | 文档声称 release.yml verify job 使用，全仓零调用——build-metadata 必填字段断言与 bundle 级 SBOM 断言在发布链完全不生效 → verify-gate 对三平台各调一次，或删脚本同步文档 |
| PY-176 | P1 | 供应链验证弱化 | .github/workflows/release.yml:113-130 | `gh attestation verify` 只带 --owner+--predicate-type 未固定 --signer-workflow——仓库内任何 workflow 产生的 attestation 都满足校验；verify_provenance.py 支持该参数却零调用 → 三处改调 verify_provenance.py 或补 --signer-workflow |
| PY-177 | P1 | 门禁可绕过 | .github/workflows/release.yml:36 等 4 处 | pin-check 正则要求 SHA 后必须跟非 hex 字符——行尾短 SHA 不匹配（已实测验证），@develop/@latest 也漏检 → 负向断言匹配非 40 位完整 SHA 的引用 |
| PY-178 | P1 | 供应链 hash 缺口 | contracts.yml:30；agent-redteam.yml:25；supply-chain.yml:26 | PY-010 只修了 ci.yml——三处仍为仅版本 pin 的明文安装，且根级无覆盖活动 Python 工具链的锁文件 → 建根级 requirements-ci.txt（--generate-hashes），三处改 --require-hashes -r |
| SP-139 | P1 | 隐私泄露 | dist/aegis-windows/Aegis.Windows.App.exe.WebView2/ | 发布暂存目录内嵌真实 WebView2 用户配置（浏览历史/登录元数据/表单数据，整树 160MB）——dist 是打包/上传的枚举根，用户数据可入制品链 → 删除该目录；调试运行改用独立 UserDataDirectory |
| SP-140 | P1 | 授权绕过 | agent/tests/redteam_e2e_test.py:58 | `session_id: str = "session-default"` 默认值使省略 session_id 的 action 自带合法会话——deny_session 分支仅显式空串可触发（fail-open 默认）→ 默认改 None 且 None 即 DENY_SESSION，补省略字段用例 |
| SP-141 | P1 | 授权绕过 | agent/tests/redteam_e2e_test.py:56,114-117 | tool_description_hash 默认 None 且真值检查——攻击者省略哈希字段（或传空串）即完全跳过工具描述哈希绑定 → 注册过 approved_descriptions 时哈希必填（缺失/空即 DENY_DESCRIPTION_HASH） |
| SP-142 | P1 | 最小权限失效 | agent/tests/redteam_e2e_test.py:69-72 | intent 与 scope 是两个独立集合分别成员判定——`get_current_origin` 搭配另一 action 的 `tabs:read` 即放行，intent→scope 绑定（catalog 逐条登记）未被执行 → 从 catalog 构建 intent→scope 映射并校验配对一致+跨配对拒绝用例 |
| SP-143 | P1 | 供应链 | .github/workflows/release.yml:113-121 等 4 处 | 四处 attestation 验证均未固定 --signer-workflow——仓库内任何持 id-token 的 workflow 产生的 attestation 均可通过（与 PY-176 同源，分别在编排器与平台子流）→ 接入 verify_provenance.py 或补参数 |

## 1. Windows C# 正典栈（CS-291..333，43 项）

| ID | 优先级 | 类型 | 位置 | 问题 → 方案 |
|---|---|---|---|---|
| CS-291 | P1 | 安全/fail-open | windows/.../Chrome/InPrivateWindow.xaml.cs:21 + Broker/BrowserPolicyBroker.cs:37 + Chrome/SettingsWindow.xaml.cs:151 | KillSwitch 是每个 broker 的实例属性：设置窗触发的是主窗 broker 的开关，而每个无痕窗口 `new BrowserPolicyBroker()` 自带独立 KillSwitch，永不触发——紧急终止后无痕窗口导航/下载/批准链完全不受冻结，与“全部导航冻结”声明相悖 → KillSwitch 改进程级共享单例（静态状态或单实例注入各 broker 构造器），InPrivate 复用同一实例；补跨窗口联动测试 |
| CS-292 | P1 | 功能缺陷 | windows/.../WebView/HostWebView.cs:75-80 + Chrome/InPrivateWindow.xaml.cs:64-110 | HostWebView 对 NewWindowRequested 一律 `e.Handled=true` 后转发事件，但 InPrivateWindow 全文零订阅（主窗 MainWindow.xaml.cs:416-424 有）——无痕窗口内 target=_blank/window.open 链接点击无任何反应 → InPrivate CreateRuntime 中订阅 `runtime.NewWindowRequested += url => _tabs.NewTab(url)`，加逻辑级测试 |
| CS-293 | P2 | 正确性 | windows/.../Core/Tabs/TabManager.cs:116-121 | 撤销栈容量淘汰方向反了：`while (_closed.Count > 20) _closed.Pop()` 从栈顶弹出的是刚压入的最新关闭项——关闭第 21 个标签时该标签立即不可恢复；TabManagerTests.cs:352 注释宣称“淘汰最旧”但断言恰锁定现行为 → Push 前若已满则先淘汰栈底（改 LinkedList/双端结构或反转维护），并改测试断言“最新关闭项必须在栈内、最旧项被淘汰” |
| CS-294 | P2 | 功能缺陷/一致性 | windows/.../WebView/HostWebView.cs:159-163 + Chrome/MainWindow.xaml.cs:428-438 | InPrivateWindow 未订阅 DownloadConfirmationRequested——无痕窗口下载危险扩展时走“无订阅者 fail-closed”分支被静默取消，用户看不到任何提示 → InPrivate 订阅并提供同款确认 MessageBox（至少 SecurityLog+可见反馈说明拒绝原因） |
| CS-295 | P2 | 功能缺陷 | windows/.../WebView/HostWebView.cs:303-311 + Chrome/InPrivateWindow.xaml.cs | 确认门（AEGIS_REQUIRE_NAVIGATION_CONFIRMATION=1）下 InPrivate 无 ApprovalPanelController、零订阅 NavigationConfirmationRequested——RequireConfirmation 导航被静默取消且无任何 UI 可批准/拒绝 → InPrivate 复用 ApprovalPanelController（XAML 补 overlay 或经主窗共享面板） |
| CS-296 | P2 | 双源/正确性 | windows/.../Core/Security/UrlRedactor.cs:16 vs Broker/BrowserPolicyBroker.cs:346-359 | CS-070 的“脱敏单源”只收敛了一半：Broker 仍持私有 RedactUrl（带代理对安全截断），共享 UrlRedactor.Redact 的回退分支 `url[..256]+"…"` 硬切可产生孤立代理；UrlRedactor 全仓零测试 → UrlRedactor 吸收代理对回退逻辑，Broker 删除私有实现改调 UrlRedactor；补孤立代理/256 边界用例 |
| CS-297 | P2 | 文化 | windows/.../Chrome/MainWindow.xaml.cs:324 | 下载记录时间 `DateTime.Now.ToString("yyyy-MM-dd HH:mm:ss")` 未指定 InvariantCulture——自定义格式串中 ":" 是文化时间分隔符占位（CS-034/149/175 同类已修，此处漏网）→ 加 CultureInfo.InvariantCulture，与读取侧口径锁定 |
| CS-298 | P2 | 边界 | windows/.../Chrome/MainWindow.xaml.cs:779-784 + Core/Settings/SettingsService.cs:197-198 | RestoreWindowState 对 Left/Top 只校验上界无下界；NormalizeWindow 允许持久化到 -100000——负值可把窗口恢复到虚拟屏幕外不可见 → 校验区间改 [VirtualScreenLeft, Left+Width]（Top 同理），越界回退居中 |
| CS-299 | P2 | 性能/IO | windows/.../Chrome/MainWindow.xaml.cs:527-531 + Core/History/HistoryStore.cs | 每次导航完成在 UI 线程同步写历史：`_history.Add(...)` 每次新建 SQLite 连接+INSERT+周期修剪——与 CS-031/159“IO 移出 UI 线程”口径相悖 → Task.Run 后台写入（带代际防错序）或内存队列+后台 flusher |
| CS-300 | P2 | 指纹防护自曝 | windows/.../WebView/FingerprintShield.cs:266,274-278 | `reducePrecision = Math.round(v/TP)*TP + (Math.random()-0.5)*TP/2` 同样套在 Date.now 上——返回非整数（`Number.isInteger(Date.now())===false` 一行即识破）；随机抖动破坏 performance.now 单调性 → Date.now 分支改 `Math.round(reducePrecision(v))` 保持整数毫秒；performance.now 钳单调非递减 |
| CS-301 | P2 | 正确性 | windows/.../Core/History/HistoryStore.cs:100,119-121 vs 202,215 | Recent/Search 仅 `ORDER BY visited_at DESC` 无 id 决胜列，分页查询均有 `, id DESC`——同一秒多条记录时列表与分页顺序不一致可能重复跳行 → 两处补 `, id DESC`+同秒多条顺序锁定用例 |
| CS-302 | P2 | 正确性 | windows/.../Core/Settings/SettingsService.cs:125-139 vs Core/Settings/AppSettings.cs:76-98 | 坏 settings.json 双口径：AppSettings.Load 失败先备份 .bak 再回退默认；SettingsService.ReadSnapshot 失败直接回退默认不备份 → ReadSnapshot 复用备份逻辑（BackupCorruptFile 提 internal 共享）+用例 |
| CS-303 | P2 | 正确性/截断 | windows/.../Core/Downloads/DownloadPolicy.cs:91-101 | SanitizeFileName 超长截断硬切不代理对安全——emoji 文件名截断产生孤立代理；CS-101/155/163/212 已修同类四处此处漏 → 截断处加 `char.IsHighSurrogate` 回退一位；补用例 |
| CS-304 | P2 | 正确性 | windows/.../Chrome/SessionSaveScheduler.cs:83-100 | BeginRestore 注释宣称“可重入安全（内层先退出不清除外层抑制）”，实现是布尔置位——嵌套恢复时内层 Dispose 直接 `_restoring=false`，外层仍在恢复期却提前放行 MarkDirty/Flush → 改 int 计数器（Enter/Leave 配对）+嵌套抑制用例 |
| CS-305 | P2 | 审计缺口 | windows/.../Chrome/BookmarkManagerWindow.xaml.cs:223-235 vs 170-186 | 键盘 Delete 删除书签路径无 SecurityLog 留痕（鼠标路径有——CS-290 只补了一半）→ 提取 DeleteBookmark(row) 单源（含日志+异常反馈+Reload），两路共用 |
| CS-306 | P2 | 死代码/崩溃面 | windows/.../Chrome/HistoryWindow.xaml:128-132 | DayHeaderTemplate 是 DateHeaderTemplate 的陈旧副本：绑定 `{Binding Name}`（DateHeader 无 Name 属性）且引用全仓未定义的 `{StaticResource DateLabelConverter}`——模板一旦实例化即 XamlParseException → 删除死模板 |
| CS-307 | P2 | 安全/输入校验 | windows/.../Broker/OriginPolicy.cs:90-95 + Core/UrlSafety.cs:95-107 | 前导零八进制 IPv4（"0177.0.0.1"）：OriginPolicy 四段全数字即放行、TryParseAlternateIpv4 只识别 2/3 段与整数/0x 形态——OS 解析栈按八进制解释为 127.0.0.1 → 两处对“4 段且任一段前导零”按 IPv4 变体解析后走 IP 判定，补向量用例 |
| CS-308 | P2 | 性能/取证 | windows/.../WebView/HostWebView.cs:230-234 + Core/Security/SecurityLog.cs:58-61 | 跟踪防护每个被拦截子请求同步 SecurityLog.Write（每条 File.AppendAllText）——跟踪器密集页 IO 放大且 1MB 取证日志被冲掉 → 拦截类事件按 host+原因聚合计数周期落一行 |
| CS-309 | P2 | 隐私一致性 | windows/.../Core/Favicons/FaviconService.cs:30,60-65,75-77 | 负缓存 Miss 未按持久化语义分面——无痕标签抓取失败把 host 写入进程级共享 Miss，普通窗口随后首访直接命中负缓存不抓取 → Miss 键复用 flightKey 的 persistToDisk 前缀方案 |
| CS-310 | P2 | 可观测性 | windows/.../WebView/HostWebView.cs:236-239 | OnWebResourceRequested 兜底 catch 完全静默——策略管线异常零痕迹 → catch 写 SecurityLog（含 ResourceContext 与脱敏 URL），维持不 rethrow |
| CS-311 | P3 | 双源 | windows/.../Chrome/TabRuntime.cs:165-178,214-227 + Chrome/Ntp/NtpBridgeFactory.cs:182-195 | 同一段“容错导航”逻辑现存三副本（TabRuntime 实例/静态、NtpBridgeFactory.SafeNavigate）→ 静态版改调实例版，SafeNavigate 改调 TabRuntime.Navigate |
| CS-312 | P3 | 死代码 | windows/.../Contracts/Generated/*.cs（6 文件） | 生成契约类生产与测试零引用 → 接入真实 JSON 反序列化面或从编译移除 |
| CS-313 | P3 | 死代码 | windows/.../Core/UrlSafety.cs:33-44 | IsPublicHttpUrl 生产零调用 → 删除或注明保留原因 |
| CS-314 | P3 | 死代码 | windows/.../Chrome/DateField.xaml.cs:41-45 | FieldText 属性零使用 → 删除 |
| CS-315 | P3 | 性能微 | windows/.../Core/UrlSafety.cs:129,134 | IsPublicIp 对同一地址两次 GetAddressBytes → 删除 bytes 复用 raw |
| CS-316 | P3 | 性能微 | windows/.../Broker/OriginPolicy.cs:79,90 | IsValidHost 对同一 host Split('.') 两次 → 一次 Split 复用 |
| CS-317 | P3 | 安全一致性 | windows/.../WebView/HostWebView.cs:74 vs 127-137 | HTTPS-only 升级只在顶层执行，_onFrameNavigationStarting 直接 TryAuthorize——iframe 的 http 子文档在 HTTPS-only 模式保持明文 → frame 处理器同判 HttpsOnly（cancel 明文 frame 导航并留审计） |
| CS-318 | P3 | 主题 | windows/.../Chrome/MainWindow.xaml:337-350 | ErrorPagePanel/FeedbackBar 及文字色硬编码深色——浅色主题割裂 → 提为资源键，ApplyTheme 一并写入浅色值 |
| CS-319 | P3 | 一致性/校验 | windows/.../Chrome/MainWindow.xaml.cs:946-950 + Core/History/HistoryStore.cs:53-88 | 手写路径绕过导入器长度上限：Star_Click 直 Add（标题不截断），HistoryStore.Add 对 url/title 无上限——BookmarkImporter 有 2048/256 上限 → 库层统一钳制（代理对安全截断） |
| CS-320 | P3 | 一致性 | windows/.../Chrome/MainWindow.xaml.cs:314-332 vs Core/Downloads/DownloadRecordStore.cs:8-10 | 下载记录在启动时即写入：completed_at 实为开始时刻、取消/中断同样留档——与“保存已完成/失败下载”注释相悖 → 移到完成态再写或补写，或字段改名 started_at 并完成时回填 |
| CS-321 | P3 | UI | windows/.../Chrome/MainWindow.xaml:186-201 | 标签图标位 Ellipse 蓝点常显，favicon 同格叠加覆盖——PNG 透明区透出蓝点 → Ellipse 移入 Icon==null 的 DataTrigger 分支 |
| CS-322 | P3 | 可观测/健壮性 | windows/.../Chrome/SuggestionController.cs:74-85 | Run 的 `_ = Task.Run(...)` 无 try/catch——坏库/锁时未观察任务异常，弹层无声不出现 → 体内 try/catch → SecurityLog 并关闭弹层 |
| CS-323 | P3 | 性能 | windows/.../Broker/BrowserPolicyBroker.cs:44,373-388 | 每次导航决策都 ProbeFromEnvironment：原生模式下每次 NativeLibrary.TryLoad+GetExport+Free 一轮 → ctor 探测一次缓存结果（失败按短 TTL 重试） |
| CS-324 | P3 | 一致性/取证 | windows/.../Core/Security/SecurityLog.cs:60 | 安全日志时间戳用 DateTime.Now 且未指定 culture——与 UTC round-trip 口径不一致 → 改 UtcNow + InvariantCulture |
| CS-325 | P3 | 双源 | windows/.../Chrome/MainWindow.xaml.cs:296-298 | 标签创建日志内联手写脱敏——与 UrlRedactor.Redact 同形且回退分支丢 256 截断 → 改调 UrlRedactor.Redact |
| CS-326 | P3 | 双源 | windows/.../Core/Settings/AppSettings.cs:101-117 + SettingsService.cs:91-113 | 原子写（temp+Replace/Move+finally Delete）两份同形实现 → 提取 internal static AtomicWriteAllText 单源 |
| CS-327 | P3 | 一致性 | windows/.../Chrome/InPrivateWindow.xaml.cs:171-177 vs MainWindow.xaml.cs:474-477 | 无痕窗口标签切换只翻 Visibility/IsHitTestVisible，主窗口还设 IsEnabled——CS-177 只对齐了一项 → 补 `pair.Value.Control.IsEnabled = on;` |
| CS-328 | P3 | 测试缺口 | windows/tests/.../FaviconServiceTests.cs | 负缓存命中短路（含 CS-309 语境隔离）、InFlight 去重、TrimCaches 上限零覆盖 → 提 internal 可测缝补 3-5 例 |
| CS-329 | P3 | 测试缺口 | windows/tests/.../DownloadItemTests.cs | Refresh 状态机分支（UserCanceled→Canceled、ObjectDisposedException→Ended、未知状态→Interrupted）零锁定 → 注入假 DownloadOperation 直测各分支 |
| CS-330 | P3 | 测试缺口 | windows/tests/（无 TabRuntimeCoordinator 覆盖） | NavigateVirtualHostWithRetry 重试耗尽→NtpNavigationFailed、ValidateNavigationTarget 探针异常拒绝零测试 → 提纯校验/重试计数为 internal 直测 |
| CS-331 | P3 | JS 性能 | windows/.../WebView/FingerprintShield.cs:225-234 | stripTrackingParams 每次 fetch/XHR 重建 ~40 键 lowerSet——请求热路径重复分配 → IIFE 顶层一次性构建冻结集合 |
| CS-332 | P3 | 一致性 | windows/.../Broker/BrowserPolicyBroker.cs:75 vs 90-107 | AllowDownload 在锁内检查 `_disposed`，RegisterSession 不检查——Dispose 后仍可注册新会话（清空后复活）→ RegisterSession 头部补 `_disposed` 检查（同锁内） |
| CS-333 | P3 | 内存驻留 | windows/.../Chrome/MainWindow.xaml.cs:48,396-403 + DownloadsWindow.xaml.cs:63-76 | `_downloads` 集合只增不减——每个 DownloadItem 持有原生对象，长会话无上限常驻 → 超阈值自动移除最早非进行中条目 |

## 2. Android（AD-211..251，41 项）

| ID | 优先级 | 类型 | 位置 | 问题 → 方案 |
|---|---|---|---|---|
| AD-211 | P1 | 安全/日志泄敏 | android/webview-adapter/src/main/kotlin/com/aegis/webviewadapter/AegisWebViewClient.kt:240 | denied() 只对 url 参数走 LogRedact，但 reason.detail 本身内嵌完整明文 URL（AndroidBroker.kt:163 deny("url_policy", "拒绝 URL: $rawUrl") 直接拼原文；Rust deny detail 同路）→ AD-004 脱敏被整链绕过，query 中 token/搜索词仍入 logcat → detail 组装处即用脱敏值，或日志面对 reason.detail 一并 LogRedact.redact，并补「detail 不含原文」断言测试 |
| AD-212 | P1 | 指纹防护缺陷 | android/app/src/main/java/com/aegis/browser/WebViewHardening.kt:186-196 | toDataURL 噪声用 `ctx.putImageData` 破坏性写回活画布：①二次读同一画布结果不同，噪声注入自身可检测（RS-025 修了 Rust 侧，Android 独立实现未修）；②页面后续渲染被永久污染；③getImageData/putImageData 全画布拷贝在 JS 主线程，大画布卡顿 → 在离屏 canvas 复制副本上加噪后仅用于返回值，不动原 ctx |
| AD-213 | P1 | 安全/URL 混淆 | android/broker/src/main/kotlin/com/aegis/broker/OriginPolicy.kt:55-60 | IPv4 备用编码判定漏两类：`0177.0.0.1`（4 段全数字即放行，inet_aton 按八进制=127.0.0.1）、`0x7f.1`（`startsWith("0x")` 但含 `.` 判 false）——PY-071/072 防线被绕过；Chromium 解析归一后 `location.hostname` 可命中 bridge_guard 白名单 `127.0.0.1` → 数字段含前导零且长度>1 拒绝、`0x` 逐段（而非仅整串）拒绝；OriginPolicyTest 补向量 |
| AD-214 | P1 | 生命周期/泄漏 | android/app/src/main/java/com/aegis/browser/SecureWebViewFactory.kt:144-149 | tearDown 在 destroy() 前未从父容器 detach——关闭当前激活标签（TabManager.closeTab→tearDown，WebView 仍挂在 FrameLayout）与 MainActivity.onDestroy 全量销毁路径全部命中「attached destroy」→ 序列首部加 `(webView.parent as? ViewGroup)?.removeView(webView)` |
| AD-215 | P2 | 状态丢失 | android/app/.../BrowserViewModel.kt:107 | _pageError 是全局单槽：仅 clearPageError 与当前标签 onPageUrlObserved 清除；switchTo/closeTab 均不清 → 标签 A 出错后切到健康标签 B，错误遮罩仍盖在 B 内容上 → PageError 绑定 webView 引用，切换/关闭时按当前标签重算或清除 |
| AD-216 | P2 | 状态语义混用 | android/webview-adapter/.../AegisWebViewClient.kt:183 + BrowserViewModel.kt:274-276 | 「待确认」与「被拒」共用 false 返回：RequireConfirmation 分支返回 false，ViewModel 据此弹「该地址无法通过安全策略验证」→ 确认对话框与错误提示同时弹出且误导 → SecureNavigator 返回三态（Pending/Allowed/Denied）或 ViewModel 在 pendingConfirmation 非空时抑制错误；补测试 |
| AD-217 | P2 | 安全/下载 | android/app/.../DownloadPolicy.kt:53-64 | URL 路径段不参与百分号解码（AD-002 只给 query 值补了 decode）：`/dl/malware%2Eexe` 路径段归一后无字面 `.`，危险扩展漏判；resolveDownloadFileName 的 urlPathSegment 同样不解码 → path 段复用 decodeQueryValue 后再取尾段，补 `%2E` 向量测试 |
| AD-218 | P2 | 安全/检测失效 | android/app/.../WebViewVersionCheck.kt:21,37-43 | 仅探测 com.google.android.webview：AOSP com.android.webview、Chrome 代打 provider、厂商包上 getPackageInfo 必抛 NameNotFoundException → null 静默返回，过旧 WebView 提示完全失效 → 改 WebViewCompat.getCurrentWebViewPackage(context)，取 versionCodeLong |
| AD-219 | P2 | 构建/R8 缺口 | android/app/proguard-rules.pro:14-15 | 只 keep 了 NativePolicyCoreBridge$NativePolicyCoreAbi；NativePolicyCoreGate$NativePolicyCoreAbi（probe 的 JNA 接口）未 keep——AD-003 恢复 R8 后方法名被混淆 → LinkageError → 门禁 block → 全部导航 fail-closed 拒绝 → 补 keep 规则，或把两个 Abi 接口合并单源 |
| AD-220 | P2 | 隐私/跨模块 | android/app/.../WebViewDownloadHandler.kt:39,49 | 下载拦截两处 Log.w 明文记录完整 URL（含 query）；LogRedact 是 webview-adapter 的 internal，app 模块无法复用 → 脱敏工具上移到可共享位置，下载日志统一接入 |
| AD-221 | P2 | 测试缺口 | android/webview-adapter/.../AegisWebViewClient.kt:223-227 | renewSessionBeforeDecision 的「待审批确认期间不续期」门控（防覆盖式重注册孤儿化 pending nonce 的关键时序）无任何测试 → mock broker 断言 pending 非空时 renewSession 未被调用、消费后恢复调用 |
| AD-222 | P3 | 无障碍 | android/app/.../MainActivity.kt:372-377 | ChromeIconButton 的 semantics 仅在 enabled=true 分支挂 contentDescription——AD-064 引入禁用态后，禁用的后退/前进按钮对 TalkBack 完全静默 → 语义无条件外置 |
| AD-223 | P3 | 一致性 | android/app/.../VerticalTabBar.kt:65-79 | AD-086 只给横向 TabBar 补了 animateScrollToItem；VerticalTabBar 的 LazyColumn 无对应滚动 → 同口径 LaunchedEffect(activeIndex) 滚动 |
| AD-224 | P3 | 状态残留 | android/app/.../BrowserViewModel.kt:235-249 | closeTab 不清地址栏草稿（switchTo 明确清 addressDraftActive，关闭标签导致 activeIndex 变更却不清）→ 关闭路径与切换路径同口径清草稿 |
| AD-225 | P3 | 状态陈旧 | android/app/.../BrowserViewModel.kt:449-471 | onPageUrlObserved 更新 TabManager.updateUrl 后不调 refresh()：_tabs StateFlow、canGoBack/canGoForward 均不刷新——无标题变化的页面前进/后退按钮状态滞后 → 回调尾部补 refresh()（与 onTitleObserved 同口径） |
| AD-226 | P3 | 性能 | android/app/.../MainActivity.kt:146-155 | 阅读模式对话框用单个 Text 渲染至 200K 字符+verticalScroll：一次性测量整段文本，低端机卡顿/ANR → 分段 LazyColumn 渲染或收紧上限 |
| AD-227 | P3 | 健壮性 | android/app/.../ReaderMode.kt:92-94 | text 有 MAX_TEXT 截断，title 无任何上限——超长标题直接进 AlertDialog 标题 → title 同走截断（对齐 256） |
| AD-228 | P3 | 文案单源 | android/app/.../ReaderController.kt:34,51 | 两条提示硬编码中文——AD-045/046 迁移时漏网 → 迁 strings.xml |
| AD-229 | P3 | 主线程 IO | android/app/.../SecureNavigator.kt:42 | 每次导航都同步 SearchEngines.currentEngine 读 SharedPreferences（首次磁盘 IO 在主线程）→ 进程内缓存 engine key（onSharedPreferenceChanged 失效） |
| AD-230 | P3 | 下载/兼容 | android/app/.../WebViewDownloadHandler.kt:92-96 | Content-Disposition 只认 `filename=` 字面：RFC 5987 `filename*=UTF-8''…`（非 ASCII 中文名标准形态）、大小写变体不解析 → 优先解析 filename*（百分号解码），再回退 filename |
| AD-231 | P3 | 口径不一致 | android/app/.../TranslateEntry.kt:28 | startsWith("http://") 大小写敏感：HTTP:// 页面翻译被拒，而决策层 scheme 均大小写不敏感 → 统一 ignoreCase 判定 |
| AD-232 | P3 | 日志噪声 | android/app/.../BrowserEngine.kt:82-87 | onProgressChanged 每次进度变化 Log.i（每页 5-10 条永久 info）→ DEBUG 包裹或仅完成/异常留痕 |
| AD-233 | P3 | 日志噪声 | android/webview-adapter/.../AegisWebViewClient.kt:264 | https 升级 Log.i 对每条 http 资源（含全部子框架）各打一条 → 降 DEBUG 或采样 |
| AD-234 | P3 | 文档漂移 | android/app/.../WebViewVersionCheck.kt:14-17 | 类注释宣称「版本低于安全阈值时拒绝外部浏览」，实现只有提示——安全预期与行为矛盾 → 修正注释或落地拒绝开关 |
| AD-235 | P3 | 死代码/日志 | android/app/.../AegisHomeBridge.kt:70-73 | logError 中 message ?: "" 是对非空 String 的冗余判空；且页面可控 message 未做换行净化直接 Log.e → 删冗余判空+复用 sanitizeTitleForLog 同口径净化 |
| AD-236 | P3 | 资源治理 | android/broker/.../NativePolicyCoreBridge.kt:123-125 | NativePolicyCoreBridge 实现 AutoCloseable 但 close() 全工程零调用——Rust broker 指针进程期内永不释放 → 提供销毁 API 或注释固化进程级生命周期 |
| AD-237 | P3 | 可观测性 | android/broker/.../NativePolicyCoreBridge.kt:118-121 | consumeNavigation 把 Decision 折叠成 isAllow：原生核心返回 Deny 时原因被静默丢弃 → deny 分支 Log.w 留痕 code/detail |
| AD-238 | P3 | UX/占位符 | android/app/.../BrowserViewModel.kt:40,207 | HOME_DISPLAY_URL="aegis://home" 是不可导航占位：首页未编辑直接点「打开」→ 弹「无法通过安全策略验证」恐吓性错误 → 地址等于占位时映射回 HOME_URL 或 no-op |
| AD-239 | P3 | 重复弹窗 | android/app/.../MainActivity.kt:89-93 | 版本检查无进程级去重：未声明 configChanges 的变更触发重建后再次 checkAndPrompt → 检查结果上移存续层 |
| AD-240 | P3 | 生命周期 | android/app/.../MainActivity.kt:399-405 | onNewIntent 未调 setIntent(intent)：后续 getIntent() 仍指旧 Intent → onNewIntent 内 setIntent |
| AD-241 | P3 | 构建 | android/app/build.gradle.kts:84-88 | signing.properties 缺任一键时 file(getProperty("storeFile"))（null）在配置期抛无指引异常 → 逐键校验并给出「缺 xxx 键」明确报错 |
| AD-242 | P3 | 构建单源 | android/build.gradle.kts:2-8 | 插件版本为字面量未入 libs.versions.toml——AD-154 只收敛了 app 依赖 → 插件版本入 catalog |
| AD-243 | P3 | CI | .github/workflows/android-quality.yml:47-53 | Gradle 缓存 key 的 hashFiles 未含 gradle/libs.versions.toml——版本目录变更不失效缓存 → key 追加 toml 哈希 |
| AD-244 | P3 | 死产物 | android/contracts/.../generated/ | 6 个生成契约中仅 ActionContract 被引用；其余 5 个零消费点 → 收窄 codegen 生成范围或补真实消费 |
| AD-245 | P3 | 字体/死配置 | android/app/.../AegisTheme.kt:20-25 | Inter 与 Source Han Sans SC 同以 FontWeight.Normal 声明进同一 FontFamily：按权重匹配首个命中，中文字形实际走系统默认字体 → 用 res/font XML fallback 链或拆分 family |
| AD-246 | P3 | 性能 | android/webview-adapter/.../AegisWebViewClient.kt:96-101 | 非主框架导航同样走完整 requestNavigationConfirmation+自动批准+consumeNavigation（native 模式下每次 JNI→Rust 持锁）→ 子框架走轻量判定 |
| AD-247 | P3 | 测试缺口 | android/app/.../WebViewHardening.kt:151-312 | fingerprintShieldScript 9 阶段无任何 JVM 断言——「脚本被改而注入照常」是零回归盲区 → internal 暴露+各阶段关键标记断言 |
| AD-248 | P3 | 测试缺口 | android/app/.../SearchEngines.kt:75-90 | uriEncode 声称与 android.net.Uri.encode 语义一致，等价性仅 2 条冒烟 → instrumented 侧补全对照矩阵 |
| AD-249 | P3 | 测试缺口 | android/broker/.../AndroidBroker.kt:337-346 | canonicalOrigin 的 IPv6 host、非默认端口拼接、默认端口折叠无直接单测 → 补用例 |
| AD-250 | P3 | 测试缺口 | android/app/.../AegisHomeBridge.kt:90-109 | getEngine 的 JSON 结构与 start.html 消费契约零断言 → internal 化+JSON 结构断言 |
| AD-251 | P3 | 死代码/功能缺失 | android/app/.../BrowserViewModel.kt:91 + MainActivity.kt:222-239 | _tabsPosition 全工程零写入点（恒 "top"），left 分支 UI 不可达；且该分支没有 AddressBarRow——一旦接线用户将失去地址栏 → 补布局切换入口并补齐地址栏，或按 AD-082/083 同口径删除死分支 |

## 3. Rust 策略核心（RS-206..237，32 项）

| ID | 优先级 | 类型 | 位置 | 问题 → 方案 |
|---|---|---|---|---|
| RS-206 | P1 | 防护绕过 | core/rust-policy-core/src/shield.rs:90,117,144 | canvas 三通道（toDataURL/toBlob/convertToBlob）噪声前置 `const ctx = this.getContext('2d'); if (ctx)` 门禁：①画布已持 WebGL 上下文时 getContext('2d') 返回 null → 直接走无噪声回退，WebGL 画布读取完全绕过 canvas 噪声（WebGL 画布恰是主流指纹向量）；②画布尚无上下文时该调用会把画布永久锁定为 2d——页面随后 getContext('webgl') 返回 null，渲染被破坏。且 ctx 变量除真值判定外从未使用 → 删除该门禁（drawImage(this) 对任意上下文类型的源画布均可用，离屏副本自取 2d 上下文即可），补 WebGL 画布噪声回归 |
| RS-207 | P2 | 跨站关联 | core/rust-policy-core/src/shield.rs:98,125,150 | canvas 噪声种子取 `__AEGIS_SESSION_SEED.slice(0,8)`——会话级常量，同一用户在同会话内访问 A/B 两站，噪声图案完全相同，站点比对 canvas 哈希即可跨站关联；PerSiteSeed 仅覆盖 AudioBuffer 通道，canvas 这个主指纹面未按域隔离 → canvas 噪声改由 per-site 种子驱动 |
| RS-208 | P2 | 伪装可检测 | core/rust-policy-core/src/timer_prec.rs:118-122 | 默认 jitter=true 时 `Date.now = function(){ return reducePrecision(origDateNow()); }` 返回带小数——`Number.isInteger(Date.now())` 一行即识破防护；Android 孪生 AD-108 已修，Rust 侧未同步 → Date.now 通道 Math.round 取整（jitter 仅保留给 performance.now）+回归断言 |
| RS-209 | P2 | 口径漂移 | core/rust-policy-core/src/space_routing.rs:225-227 | 注入 JS 的 route() 域匹配 `(h === r.pattern) \|\| h.endsWith('.' + r.pattern)` 无空 pattern 防御：pattern="" 的 Domain 规则对无 host URL（getHostname 得 ''）空串等值命中——Rust 侧 RS-119 已拒空 pattern，JS 孪生未同步 → JS 侧补 `if (!r.pattern) continue;`+双端口径回归 |
| RS-210 | P2 | 状态破坏 | core/rust-policy-core/src/font_norm.rs:141-151 | measureText 包装直接 `this.font = ...` 改写画布上下文字体且不恢复：页面后续所有绘制都被换成安全字体串，且页面回读 ctx.font 即检测到防护 → 临时对象测量（prevFont 保存/finally 恢复），不改写原上下文状态 |
| RS-211 | P2 | FFI 健壮性 | core/rust-policy-core/src/c_abi/mod.rs:33-56 | `read_utf8(...) -> Result<&'static str, &'static str>` 把宿主 C 缓冲的切片声明为 'static——签名层面 unsound：任何调用方把返回引用存入全局/缓存即悬垂 → 改为 `fn read_utf8<'a>(value: *const c_char) -> Result<&'a str, &'static str>` |
| RS-212 | P2 | 测试缺口 | core/rust-policy-core/tests/vectors.rs:70-76 | 注释声称「清单级向量见 c_abi 集成测试对 update-manifest-valid.json 的完整消费」——全 crate 无任何测试消费 update-manifest-valid/invalid.json，招牌能力（Ed25519 阈值验证）从未对跨语言契约向量跑过 → 新增向量消费者或如实修正注释 |
| RS-213 | P2 | fail-open 开关 | core/rust-policy-core/src/executor.rs:93-127 | execute_pipeline 的 `policy_check: bool` 是逐调用策略旁路：已挂载 ActionPolicy 的调用方传 false 即静默跳过阶段 4（测试明确锁定「条件命中的恶源也执行」）——安全裁决核内不应存在 per-call 关闭开关 → 移除该参数（挂载即强制）；测试旁路改走「不挂策略的 Executor」构造 |
| RS-214 | P3 | API 名不副实 | core/rust-policy-core/src/ffi/mod.rs:202-208 | build_fingerprint_pipeline(session_seed) 名为 pipeline 实则只生成单阶段脚本，且带 domain 的真正管线 fingerprint_pipeline 未做 #[uniffi::export]——宿主经 FFI 永远拿不到 per-site 隔离管线 → 导出 domain+mode 版管线或更名并文档声明孪生对账口径 |
| RS-215 | P3 | 平台孪生漂移 | core/rust-policy-core/src/shield.rs:99-101,126-128,151-153 | canvas 噪声 i += 4 只扰动 R 通道——Android 孪生 AD-175 已改多通道混淆，Rust 侧未同步（跨端噪声形态不一致本身即指纹差异面）→ 对齐多通道扰动 |
| RS-216 | P3 | 伪装可检测 | core/rust-policy-core/src/timer_prec.rs:109-113 | `Object.defineProperty(performance,'now',{value, writable:false, configurable:false})`——原生描述符为 true，getOwnPropertyDescriptor 一查即破 → 属性描述符对齐原生（writable:true, configurable:true） |
| RS-217 | P3 | 覆盖缺口 | core/rust-policy-core/src/timer_prec.rs:127-159 | RS-074 只圆整 measure() 直接返回的 entry 与 mark 的显式 startTime——getEntries/getEntriesByName/getEntriesByType 返回的条目仍是宿主内部时钟原值 → 覆盖 getEntries* 家族或文档登记已知缺口 |
| RS-218 | P3 | 文档口径过强 | core/rust-policy-core/src/tostring_guard.rs:88-98 | 注释宣称 Symbol 键「不出现在任何枚举通道」——Object.getOwnPropertySymbols(window) 无需猜测即可枚举，再按 Symbol.for 取用注册接口 → 修正注释；描述串去品牌化 |
| RS-219 | P3 | 探测面残留 | core/rust-policy-core/src/space_routing.rs:238、command_bar.rs:290 | RS-027/RS-146 已收敛 toStringGuard/protection_mode，但 __AEGIS_SPACE_ROUTING/__AEGIS_COMMAND_BAR 两个具名 window 属性仍是免费探测点 → 同款收敛（Symbol.for） |
| RS-220 | P3 | 时间源散布 | core/rust-policy-core/src/ffi/broker.rs:107,228-231,560-563 | RS-155 把 broker.rs 的 SystemTime::now 收敛到 now_unix_secs 单源，ffi/broker.rs 仍有 3 处内联 → 复用 broker::now_unix_secs（pub(crate) 化） |
| RS-221 | P3 | 热路径分配 | core/rust-policy-core/src/broker.rs:355,390-391 | validate_action_at Allow 路径 Decision::Allow(action.clone()) 整结构 12 个 String 克隆（每导航一次）；consume_nonce contains_key 后再索引同键双哈希查找 → Allow 改返回 Result<(),DenyReason>；双查找改 if let Some(record) |
| RS-222 | P3 | 热路径分配 | core/rust-policy-core/src/capability.rs:164 | validate 成功路径 CapabilityResult::Allowed(cap.clone()) 克隆整个 Capability——三层管线仅消费判别即丢弃 → Allowed 改无载荷 |
| RS-223 | P3 | 输入无界 | core/rust-policy-core/src/ffi/broker.rs:354-364 | FFI create_session 对 session_id/tab_id 仅空串检查——1024 会话 × 64KB 双键 ≈128MB 键驻留面（core 层 MAX_TAB_ID_LEN=256 未对齐）→ 键长度上限 256 字节，超长拒绝 |
| RS-224 | P3 | 跨语言漂移 | core/rust-policy-core/src/update_manifest.rs:230-269 | base64_decode 接受非规范长度："Zg"（无 padding）与 "Zg="（len 3）均放行——Python b64decode 拒绝两者；签名编码严格性两端不一致 → 对齐规范长度（len%4==0 且 padding 仅 == / = 收尾） |
| RS-225 | P3 | 重复逻辑 | core/rust-policy-core/src/ext_proxy.rs:108 | 端点转义内联 replace 链——未复用 util::js_escape_single_quoted，漏 \n/\r 转义：端点含换行即产出语法错误脚本 → 改调单源 |
| RS-226 | P3 | 拼接缺陷 | core/rust-policy-core/src/ext_proxy.rs:136-140 | proxyUrl 固定拼 PROXY_ENDPOINT + '?url='——端点自带 query 时产出双问号畸形地址 → contains('?') ? '&' : '?' 分支拼接 |
| RS-227 | P3 | 文档失实 | core/rust-policy-core/src/origin.rs:14-16,129-131 | RS-190 字段文档声明「host 字段不含端口」——实现 host: canonical_authority 在非默认端口时包含端口（测试已证明）→ 修正文档或拆分 host/port |
| RS-228 | P3 | 校验缺口 | core/rust-policy-core/src/origin.rs:93-100 | 非 dot-decimal 拒绝只看「4 段全数字」——999.1.1.1/256.0.0.1 等八位组越界形态放行 → 4 段全数字时补逐段 ≤255 校验（对齐 WHATWG），同步跨端向量 |
| RS-229 | P3 | 类型宽容 | core/rust-policy-core/src/executor.rs:160-164 | parse() 对 `"origin": 123`（非字符串）静默落默认 "cli"（unwrap_or 设计用于字段缺失，类型损坏被同路径吞掉）→ origin 非字符串走类型化错误 |
| RS-230 | P3 | 口径不一 | core/rust-policy-core/src/session_state.rs:90-94 | RS-110 把 isIncognito 收紧为缺即拒，但 timestamp/lastActiveTime 仍是 unwrap_or(0) 静默默认——损坏会话的 timestamp=0 会让宿主把该标签排为最旧 → timestamp/lastActiveTime 缺失或类型损坏同样拒恢复 |
| RS-231 | P3 | 冗余扫描 | core/rust-policy-core/src/command_bar.rs:131-134 | matches() 先 keywords.iter().any（=title_lc/subtitle_lc 两个克隆串）再直接 contains——keywords 通道与后两行完全重复 → 删 keywords 遍历（顺带省两 String/条目） |
| RS-232 | P3 | 模式脆弱 | core/rust-policy-core/src/query_strip.rs:204-208、ext_proxy.rs:162-167 | 两个 XHR 拦截都靠 `arguments[1] = ...` 赋值生效——仅非严格模式合法 → 改显式参数转发 origOpen.call(this, method, stripParams(url), ...rest) |
| RS-233 | P3 | 重复组装 | core/rust-policy-core/src/lib.rs:73-109、protection_mode.rs:157-215 | 九阶段管线两套手写组装（JsPipeline trait 对象 vs parts Vec+enable_* 分支），阶段清单/顺序各自维护 → fingerprint_pipeline 委托 fingerprint_pipeline_with_mode(Maximum, domain) |
| RS-234 | P3 | 死数据面 | core/rust-policy-core/src/oracle.rs:82-87,90-160 | snapshot() 记入有界账本，但 verify() 只接收外部传入的快照、从不消费已记录快照——回放验证语义名存实亡 → 提供 verify_recorded(action_id) 或文档明确账本仅为审计留存 |
| RS-235 | P3 | 死依赖 | core/rust-policy-core/Cargo.toml:44-45 | [dev-dependencies] hex = "0.4" 全 crate 零使用 → 删除 |
| RS-236 | P3 | 注释失实 | core/rust-policy-core/src/c_abi/mod.rs:246-251 | LIVE_BROKER 替换时直接覆盖旧退休地址且 Box 永不 drop——多轮生命周期循环下退休分配线性累积，RS-140「泄漏有界」仅对单轮成立 → 修正注释口径 |
| RS-237 | P3 | 守卫不一致 | core/rust-policy-core/src/letterbox.rs:126-129 | screen 四属性覆盖仅判 descriptor 存在（if (osW)）即调用 osW.get.call(this)——数据属性形态时页面首读 screen.width 即抛 TypeError；window 组已是双守卫 → screen 组补 .get 判定，同步修正断言 |

## 4. Python/CI/契约/发布链（PY-173..215，43 项）

| ID | 优先级 | 类型 | 位置 | 问题 → 方案 |
|---|---|---|---|---|
| PY-173 | P1 | 门禁失效 | .github/workflows/release.yml:199-207 | 去重后重生成清单探测的是改名前的文件名：dedup 把 dist/android/SHA256SUMS.json 改名为 android-SHA256SUMS.json 后，`[ -f "dist/android/SHA256SUMS.json" ]` 永假 → android 的摘要清单完全不重生成，发布出的 android-SHA256SUMS.json 仍引用旧名 build-metadata.json——消费者校验必失败 → 重生成循环改为探测改名后命名 |
| PY-174 | P1 | 发布链死锁/审批绕过 | .github/workflows/release-windows.yml:154-169 | 残留的平台级直发步骤：workflow_call 路径下调用方只授予 contents: read，`gh release create` 必 403 → build job 失败整链死亡；workflow_dispatch 选 v* tag 时 job 级 contents: write 生效，可绕过编排器 verify-gate 与 release environment 审批直接发布 → 删除该步骤，发布统一收口 release.yml publish |
| PY-175 | P1 | 死门禁 | release/verify_release.py:7-8,28-35,48-50 | 文档声称"release.yml verify job 使用"，全仓零调用——build-metadata 必填字段断言与 bundle 级 SBOM 齐全断言在发布链完全不生效 → verify-gate 对三平台各调一次 `python release/verify_release.py --bundle dist/<platform>`，或删除脚本并同步文档 |
| PY-176 | P1 | 供应链验证弱化 | .github/workflows/release.yml:113-130 | verify-gate 内联 `gh attestation verify` 只带 --owner+--predicate-type，未固定 --signer-workflow——仓库内任何 workflow 产生的 attestation 都能满足校验；verify_provenance.py:25-29 支持该参数却零调用 → 三处改调 verify_provenance.py 或补 --signer-workflow |
| PY-177 | P1 | 门禁可绕过 | .github/workflows/release.yml:36；release-windows.yml:22；release-android.yml:25；release-core.yml:25 | pin-check 正则 `uses: [^#]+@[0-9a-f]{1,39}[^0-9a-f#]` 要求 SHA 后必须跟非 hex 字符——行尾短 SHA（如 `uses: a/b@1a2b3c4`）不匹配（实测验证），@develop/@latest/@release 等也漏检 → 改负向断言匹配"非 40 位完整 SHA"的引用 |
| PY-178 | P1 | 供应链 hash 缺口 | contracts.yml:30；agent-redteam.yml:25；supply-chain.yml:26 | PY-010 只修了 ci.yml——contracts.yml 的 jsonschema/rfc3339/pyyaml、agent-redteam 的 pyyaml、supply-chain 的 pip-audit==2.7.0 均为仅版本 pin 的明文安装，且仓库根没有覆盖活动 Python 工具链的 requirements 锁文件 → 建根级 requirements-ci.txt（pip-compile --generate-hashes），三处改 --require-hashes -r |
| PY-179 | P2 | 证据失配 | .github/workflows/release.yml:196 + 209-213 | 去重改名的资产其 attestation subject 名仍是改名前的名字（attest 发生在各平台 build job 内、改名之前）——发布后消费者对改名资产执行 attestation verify 找不到对应 attestation，SLSA 证据链断裂 → 去重改名后对新名重新 attest，或改为上传前以平台前缀命名产物 |
| PY-180 | P2 | SBOM 不可得 | .github/workflows/release-windows.yml:206-210；release.yml:212-213 | 各平台 SBOM 仅作为 workflow artifact（90 天过期）留存，files: dist/** 不包含 SBOM——Release 页面无任何 SBOM 资产 → 把 sbom-*.cdx.json 复制进各平台 dist 后再上传 |
| PY-181 | P2 | 脚本注入 | release-windows.yml:54-55；release-android.yml:75-76 | `${{ github.ref_name }}` 直接内插进 pwsh/bash 脚本——tag 名是外部可控输入，可注入任意命令 → 改用 env 中转后脚本内引用 |
| PY-182 | P2 | 定时门禁 fail-open | .github/workflows/compat.yml:54 | `python -m app.webview2_probe … \|\| python -c …run_selftests()`——探测失败（恰是 WebView2 回归场景）时静默回退到不含探测的纯 selftest 路径，整条定时门禁可对真实回归保持绿色 → 探测失败应直接 fail |
| PY-183 | P2 | 审计面缺口 | .github/workflows/supply-chain.yml:27 | pip-audit 只扫 legacy/windows-pywebview/requirements-lock.txt——requirements-dev.txt 与 contracts/agent-redteam 的工具链依赖全部不在依赖审计面 → 增加扫描面 |
| PY-184 | P2 | 版本比较缺陷 | release/update_verifier.py:61-65 | 预发布数字段前导零未拒绝："2.2.0-01" 与 "2.2.0-1" 比较相等（SemVer 前导零非法且不相等）——防回滚比较存在别名 → 数字段先 fullmatch 校验，违规抛 UpdateRejected；补单测 |
| PY-185 | P2 | 脚本健壮性 | release/build_metadata.py:22 | `key, value = line.split("=", 1)`——version.properties 出现无 "=" 的行直接 ValueError（sync_versions 已修同型；两处 load_properties 已成双源）→ 复用 scripts/sync_versions.load_properties |
| PY-186 | P2 | XML 转义缺失 | scripts/sync_versions.py:37-38 | re.subn 把属性值原样拼进 XML：DISPLAY_NAME 含 &/< 会生成非法 csproj，含 \ 会被当正则反向引用 → xml.sax.saxutils.escape + 函数形式替换 |
| PY-187 | P2 | 门禁可剥离 | scripts/verify_vectors.py:58,67,72 | 校验逻辑用裸 assert 实现——`python -O` 运行时断言全部被剥离，脚本对任意向量静默返回 0（fail-open）→ assert 改显式 failures.append |
| PY-188 | P2 | 契约强度损失 | contracts/codegen/generate_csharp.py:32-41；generate_kotlin.py:33-42 | 类型映射完全忽略 schema 的 enum/const（6 份 schema 含 enum）——C#/Kotlin 模型全部降级为裸 string → enum 生成枚举或常量类+单测 |
| PY-189 | P2 | 死工具 | release/tools/verify_manifest/verify_manifest.py:47-60；verify_artifact_set/verify_artifact_set.py:94-107 | 两个"阶段 E"工具仅被 runbook 文档引用，CI 零接线：更新清单签名阈值/防回滚验证、dist↔manifest 双向闭合验证在发布链从未执行 → verify-gate 增加调用或明确标注部署侧手动步骤 |
| PY-190 | P2 | 测试缺口 | tests/python/ | scripts/verify_vectors.py、verify_release_schema.py 零单测——锚点守卫、值域等行为无回归锁 → 补 tmp_path+monkeypatch 用例（含 -O 场景） |
| PY-191 | P3 | 内存不对称 | release/verify_checksum_json.py:54 | candidate.read_bytes() 整文件进内存——写入侧已分块流式，校验侧对大安装包同样整读 → 对齐 1MiB 分块摘要 |
| PY-192 | P3 | 产物集合不确定 | .github/workflows/release-core.yml:76-78 | 三个 `cp … 2>/dev/null \|\| true` 全吞错误，.so 意外缺失时仍会静默发布不完整集合 → 按平台断言期望产物，cp 失败即 exit 1 |
| PY-193 | P3 | 步骤重复 | .github/workflows/native-policy-artifacts.yml:30-35 | build-windows job 中 Swatinem/rust-cache 同一步骤连写两遍——重复 restore/save → 删除一处 |
| PY-194 | P3 | 命名漂移 | .github/workflows/native-policy-artifacts.yml:94 | 步骤名"Build four Android ABI policy libraries"，实际单架构 arm64-v8a → 改名 |
| PY-195 | P3 | 报文失真 | contracts/codegen/analyze_action_catalog.py:40-41 | "首次出现行 {seen_names[name]}" 实际存的是列表下标 i，不是 YAML 行号——定位信息误导 → 记录 start_mark.line 或更正文案 |
| PY-196 | P3 | 崩溃吞结果 | contracts/codegen/verify_contract_compatibility.py:68-70 | check_generated_models 里 json.loads 无守卫——坏 JSON 时已收集的失败信息被未捕获异常吞掉 → 复用 check_schemas 的 try/except |
| PY-197 | P3 | fail-open | contracts/codegen/generate_csharp.py:61；generate_kotlin.py:50 | required 引用不存在的属性时被静默丢弃：必填约束无声丢失 → 先算 unknown 集合，非空即抛 ValueError |
| PY-198 | P3 | 参数校验缺口 | scripts/sync_versions.py:74；verify_versions.py:67 | int(values["VERSION_CODE"]) 无守卫——非数字时原始 ValueError 栈 → 载入后即校验 isdigit，失败汇总报错 |
| PY-199 | P3 | 证据弱化 | release/build_metadata.py:47-49 | 本地运行时 source_revision 等写入哨兵值 "local-unverified"——一旦 verify_release 接线，该值 truthy 会被当有效溯源证据通过 → 校验侧显式拒绝哨兵值 |
| PY-200 | P3 | 输出丢失 | scripts/run-security-e2e/run.py:32 | 只打印 stdout 最后一行——完整测试输出被截断 → 完整透传 |
| PY-201 | P3 | 检查错位 | scripts/bootstrap-dev-environment/run.py:16-21,31 | _check("python") 用 shutil.which("python") 判存在、却运行 sys.executable——两者可能是不同解释器；注释声称 3.12 实际不校验版本 → 统一对 sys.executable 做 which+版本断言 |
| PY-202 | P3 | 内联脚本无守卫 | .github/workflows/agent-redteam.yml:32-38 | heredoc 内联 Python：open 无 close、结构变化时 KeyError 原始栈；断言与 analyze_action_catalog.py 双源 → 移入 contracts/codegen，workflow 改调脚本 |
| PY-203 | P3 | 死参数 | scripts/build_review_package.py:178,297 | apply_edit 参数函数体内零引用——--check 传入 False 并不改变行为 → 删除该参数 |
| PY-204 | P3 | 死条目 | scripts/build_review_package.py:44-47 | FILE_COPY 中 docs/DESIGN.md 与 KNOWLEDGE_BASE.md 已被 TREE_COPY 的 ("docs","docs") 覆盖——死条目 → 删除并注释 |
| PY-205 | P3 | 遍历不剪枝 | scripts/build_review_package.py:153 | src.rglob("*") 全遍历后再逐文件过滤——android/build、target 等目录数千中间产物全走一遍 IO → os.walk(topdown=True) 在 dirs 层剪枝 |
| PY-206 | P3 | CI 触发过宽 | contracts.yml:3-5；android-quality.yml:7-9；core-rust.yml:2-4 | 三 workflow push: {} 全分支全路径触发——docs 改动也全量跑 Gradle/cargo/dotnet 门禁 → 补 paths 过滤 |
| PY-207 | P3 | 生成失真 | scripts/gen_jsapi_schema.py:100-108 | 参数提取只处理 item.args.args——kwonlyargs 完全不进 schema，required 统计失真 → 合并处理并用 kw_defaults 判必填 |
| PY-208 | P3 | 导入脆弱 | release/verify_release.py:16 | from verify_checksum_json import 平铺导入——仅脚本方式从 release/ 运行才生效 → sys.path 锚定 |
| PY-209 | P3 | 无守卫解析 | scripts/build_review_package.py:304 | check_reviewed 中 json.loads 无 try——manifest 损坏时原始栈替代干净报告 → 包 try/except 计入 problems |
| PY-210 | P3 | URL 解码缺失 | release/tools/verify_artifact_set/verify_artifact_set.py:48-49 | url.split("/")[-1] 不做百分号解码——Release browser_url 对含空格/中文的资产名是 percent-encoded，与本地文件名不匹配 → unquote 后再匹配 |
| PY-211 | P3 | 命名误导 | scripts/dedup_release_assets.py:47 | 同平台内不同子目录同名文件也被加平台前缀改名（android/arm64/windows-README.md）——名字撒谎且与脚本文档不符 → 前缀改父目录链或更新文档 |
| PY-212 | P3 | 双源清理逻辑 | release/verify_checksum_json.py:30-34 vs write_checksum_json.py:12-14 | "排除清单自身"的文件集合推导在写/读两侧各自实现——规则演化时两处必漂移 → 抽共享 iter_release_files |
| PY-213 | P3 | 提示语义错 | scripts/verify_xaml_resources.py:47 | TryFindResource 命中也标成 "FindResource"——排障提示失真 → 记录匹配前缀原文作为 kind |
| PY-214 | P3 | 阈值解析脆弱 | release/tools/verify_manifest/verify_manifest.py:36-44 | 手写正则解析 YAML 抽 threshold——.*? 可跨块误绑；零单测 → 改 yaml.safe_load 结构化读取+三用例 |
| PY-215 | P2 | 死代码回退 | contracts/codegen/verify_bridge_guard.py:45-52,82-84 | REQUIRED_SINKS_FALLBACK 内置清单与"PY-043 锚点单源"声明并存——第二事实源失效后无人更新 → 删除 FALLBACK，锚点缺失直接 return 1 |

## 5. Web 资产与文档（WB-101..132，32 项）

| ID | 优先级 | 类型 | 位置 | 问题 → 方案 |
|---|---|---|---|---|
| WB-101 | P1 | 文档误导 | CLAUDE.md:57-59 | 架构红线 #3/#4/#5 仍把归档栈当正典关口：#3 要求一切导航经 app/security.py 的 safe_url()、#4 指向 app/api_bridge.py 的 _JS_EXPOSED、#5 指向 app/nav_queue.py——三者全在只读冻结的 legacy/windows-pywebview → 红线改指 UrlSafety.cs/BrowserPolicyBroker/WebView2 原生事件模型，归档栈条目并入"归档纪律" |
| WB-102 | P2 | 变更日志 | CHANGELOG.md:3 | 变更记录终点为 beta.49，其后另有约 35 个独立提交批次（R1+…RS8/C2…C19b/SP-A1，含指纹隔离、存储 UTC、FFI 泄漏等用户可见修复）零 CHANGELOG 条目 → 以 docs/audit 批次日志为源补记，或确立规则并在文件头注明 |
| WB-103 | P2 | 门禁盲区 | shared/shell/manifest.txt:10 | 单源资产清单仅登记 1 张壁纸，实际 4 张（NtpAssets.cs/start.main.js/AegisHomeBridge.kt 均为 4）——magenta/lime/violet 丢失/损坏将静默过门禁，成品 NTP 三张壁纸 404 → 清单补齐+差集对账测试 |
| WB-104 | P2 | 交付声明失真 | shared/release.json:17-19 | android.distribution 声明 play-aab，但 release-android.yml 仅 assembleRelease 出直装 APK——全链无 bundleRelease/AAB 产物 → 补 AAB 构建或删声明收敛为 direct-apk |
| WB-105 | P2 | CSP 失效 | shared/shell/start.html:14-15 | meta CSP 内 frame-ancestors 'none' 属规范明文在 meta 中被忽略的指令——防嵌套保护实际不存在，属"安全声明失真" → 移除误导指令，由宿主响应头注入（或文档注明由 WebView 容器承担） |
| WB-106 | P2 | 双端协议漂移 | android/.../AegisHomeBridge.kt:165 | openGeogebra() 返回 wv != null——openTrustedAsset 的加载结果被丢弃，资源缺失时仍返回 true；start.js 据此跳过 onFail，"资源未随包→按钮置灰"降级在 Android 永不触发（C# 侧正确反映资源可用性） → openTrustedAsset 改返回 Boolean 并透传 |
| WB-107 | P2 | 健壮性 | shared/shell/start.main.js:268,283 | 书签 it.url 为 null/非字符串时 new URL(it.url) 抛错→catch 回赋 host=null→host.charAt(0) 抛 TypeError，异常逃逸——整格后续书签全部不渲染 → 逐条容错：String(it.url \|\| '')，单条畸形跳过不中断循环 |
| WB-108 | P3 | 无障碍 | shared/shell/start.main.js:114-117 | document 点击关闭引擎菜单时不复位 enginePill 的 aria-expanded（selectEngine 同样遗漏）——读屏持续播报"已展开" → 两处关闭路径统一置 false |
| WB-109 | P3 | 无障碍 | shared/shell/start.css:301 | .search input:focus-visible { outline: none; } 使主搜索输入框成为全页唯一零焦点指示的可交互控件 → 删该规则或改胶囊容器 focus-within 描边 |
| WB-110 | P3 | 功能回归 | shared/shell/start.snake.js:75,151,208 | updScore(pop) 三处调用全部传 false——加分时 .pop 缩放动画永不触发，snakePop 变死样式（"分数变化才刷 DOM"优化把视觉反馈一并带走） → step 吃食分支改 updScore(true) |
| WB-111 | P3 | 无障碍 | shared/shell/start.css（全文件） | 0 处 prefers-reduced-motion——贪吃蛇屏震、死亡红闪、粒子对前庭敏感用户无关闭途径 → 加 @media (prefers-reduced-motion: reduce) 关闭 shake/flash/pop/transition |
| WB-112 | P3 | 无障碍 | shared/shell/start.html:81-105 | 贪吃蛇全屏浮层无 role="dialog"/aria-modal/焦点管理与 Tab 陷阱——与导入向导双标 → 对齐模式：打开聚焦关闭钮、Tab 陷阱、关闭归还 |
| WB-113 | P3 | 无障碍 | shared/shell/start.html:64 | imBody 无 aria-live/role="status"——向导"扫描中→导入中→完成/失败"全靠视觉 → 加 role="status" aria-live="polite" |
| WB-114 | P3 | 死代码 | shared/shell/start.js:12,44-141 | 保留已归档 pywebview 栈的完整 'win' 分支共 13 个方法映射，且 kind() 优先级最高——正典发布不含该桥，纯死代码面 → 删除 win 分支，Host 收敛 cs/android 双端 |
| WB-115 | P3 | 打包漂移 | android/app/build.gradle.kts:131-133 | Android 以 assets.srcDir("../shared/shell") 整目录入包且无排除——snake.test.js（约 465 行测试代码）与 manifest.txt 进入正式 APK；Windows csproj 显式排除 snake.test.js 但 manifest.txt 同样落入 → 双端统一排除规则 |
| WB-116 | P3 | 文档漂移 | CLAUDE.md:40-41；CONTRIBUTING.md:64-66 | Android 质量命令仅覆盖 :app，而 CI 实际跑四模块+lintDebug → 文档命令与 CI 对齐 |
| WB-117 | P3 | 命令失效 | CLAUDE.md:35；CONTRIBUTING.md:61 | `node --test tests/ui-regression/*.test.mjs` 通配写法在 Windows 不展开——ci.yml 注释自证并为此显式列 5 个文件，文档照抄必失败 → 文档改为显式文件清单 |
| WB-118 | P3 | 文档漂移 | CLAUDE.md:63-70,91 | 提交自查清单仍全是归档栈口径（ruff/bandit/mypy/selftest）——C#/Rust/Kotlin/Node 零项 → 清单改列双栈门禁 |
| WB-119 | P3 | 双源矛盾 | README.md:40-44 | 归档栈仍保留完整"运行+门禁"指引，与同文件"只读归档、功能 PR 一律拒绝"自相矛盾；CONTRIBUTING.md 又称"仅在触及归档目录时运行"——三份文档三种口径 → README 归档段收敛为一句"冻结基线见 ADR-009" |
| WB-120 | P3 | 文档过期 | docs/architecture-overview.md:61-63,98 | 单源 UI 树仍漏 start.js 与 start.main.js 两个外置文件，"四文件"计数过期（现 6 文件+manifest.txt） → 补全并改"六文件" |
| WB-121 | P3 | 威胁模型过期 | docs/threat-model/trust-boundaries.md:11 | 本地 chrome UI 域仍描述为"固定 bundled origin（file://）"——正典 C# 栈 NTP 已是 https://ntp.aegis.local 虚拟主机 → 按端分列两形态 |
| WB-122 | P3 | 文档过期 | docs/runbooks/device-validation.md:20 | 真机验证项 7 写"ApprovalManager nonce 一次性"——ApprovalManager 已删除 → 改述为 Broker/Rust 核心确认流 |
| WB-123 | P3 | 文档漂移 | docs/runbooks/release-checklist.md:15,34 | 把"Windows 构建+测试"挂在 ci.yml（实际在 contracts.yml/release-windows.yml）；称 release.yml "5 job"（实际 6 个） → 逐条改挂正确 workflow |
| WB-124 | P3 | 流程文档过期 | tests/KNOWN_DEFECTS.md:3 | 登记流程规定"在 start_page.test.mjs 增加断言"——断言面已拆为 5 个 mjs+snake.test.js → 改为按缺陷归属选择文件 |
| WB-125 | P3 | 测试缺口 | shared/shell/start.html:107-111 | 四个脚本的加载顺序是硬契约，任何重排即 ReferenceError 白屏——无任何顺序断言 → start_page.test.mjs 增加按序提取 script src 断言 |
| WB-126 | P3 | 测试缺口 | shared/shell/start.html:61 + start.css:225 | 导入弹层初始隐藏依赖 hidden 属性与高特异度规则的配对——零回归测试 → 补双断言 |
| WB-127 | P3 | 测试归置 | tests/ui-regression/host_bridge.test.mjs:1 | 与 start_host.test.mjs 同测 start.js 适配层，文件名不可区分、chrome 桩两套重复 → 并入或改名 import_contract.test.mjs，桩抽 helper |
| WB-128 | P3 | 空测试 | tests/ui-regression/host_bridge.test.mjs:66-69 | "宿主无回包时 importScan 仍可用"仅断言 typeof === 'function'——零行为断言 → 补真实行为断言 |
| WB-129 | P3 | 测试缺口 | shared/shell/start.main.js:225-241 | restoreBox 渲染与按钮接线零测试 → 补 n=0/1/5 三态渲染与点击调用 restoreSession 断言 |
| WB-130 | P3 | 安全文档缺口 | SECURITY.md:33-37 | "依赖与发布安全"仅覆盖 Python 与 Cargo——Android Gradle（无依赖锁定）与 C# NuGet/WebView2 evergreen 供应链零口径，而这两端才是唯一发布制品 → 补 Android/NuGet 依赖政策行 |
| WB-131 | P3 | 打磨 | shared/shell/start.html（head） | 无任何 icon 声明且 ntp 虚拟主机根无 favicon.ico——每开新标签产生一次 404 子资源请求 → 加 data: URI link icon，FaviconService 对虚拟主机短路 |
| WB-132 | P3 | 打磨 | shared/shell/start.main.js:181 | 壁纸圆点 tooltip 直接暴露原始文件名（"aurora-magenta.jpg"）——面向用户的控件显示内部资产名 → 壁纸表加中文名字段供 title/aria-label 使用 |

## 6. 补充盲区（SP-139..176，38 项）

| ID | 优先级 | 类型 | 位置 | 问题 → 方案 |
|---|---|---|---|---|
| SP-139 | P1 | 隐私泄露 | dist/aegis-windows/Aegis.Windows.App.exe.WebView2/（含 History、Login Data、Web Data、Cache/ 等，整树 160MB） | 发布暂存目录内嵌真实 WebView2 用户配置——dist 是 verify_artifact_set/Compress-Archive 的枚举根，任何本地打包或上传动作都会把用户数据带入制品链 → 删除该 WebView2 目录；调试运行改用独立 UserDataDirectory |
| SP-140 | P1 | 授权绕过 | agent/tests/redteam_e2e_test.py:58 | `session_id: str = "session-default"` 默认值使省略 session_id 的 action 自带合法会话——deny_session 分支仅显式空串可触发（fail-open 默认）→ 默认改 None 且 None 即 DENY_SESSION，补"省略字段"用例 |
| SP-141 | P1 | 授权绕过 | agent/tests/redteam_e2e_test.py:56,114-117 | tool_description_hash 默认 None 且判定用真值检查 `if action.tool_description_hash:`——攻击者省略哈希字段（或传空串）即完全跳过工具描述哈希绑定 → 注册过 approved_descriptions 时哈希必填（缺失/空即 DENY_DESCRIPTION_HASH），补省略字段用例 |
| SP-142 | P1 | 最小权限失效 | agent/tests/redteam_e2e_test.py:69-72,93,102 | intent 与 scope 是两个独立集合分别做成员判定——get_current_origin 搭配另一 action 的 tabs:read 即放行，intent→scope 绑定关系（action-catalog 逐条登记）未被执行 → 从 catalog 构建 intent→scope 映射并校验配对一致，补跨配对拒绝用例 |
| SP-143 | P1 | 供应链 | .github/workflows/release.yml:113-121（同型内联块另见 release-windows/android/core） | 四处 attestation 验证均 gh attestation verify --owner 未固定 --signer-workflow——专门工具 verify_provenance.py 固定了 signer 却全仓零调用 → 接入 verify_provenance.py 或四处内联块补参数 |
| SP-144 | P2 | 门禁退化 | release/tools/verify_artifact_set/verify_artifact_set.py:38,57-61；verify_provenance/verify_provenance.py:22-33 | 空集恒真：manifest artifacts 为空数组且 dist 为空 → failures=[] → 打印"全部通过"——"逐工件闭合 fail-closed"退化为恒真门禁 → expected 为空或 dist 枚举为空即判定失败，补空集用例 |
| SP-145 | P2 | 归档边界 | .github/workflows/release-windows.yml:71；windows/src/Aegis.Windows.App/Aegis.Windows.App.csproj:52-56 | C# 单轨正典构建把 GeoGebra 资源暂存写入归档栈目录 legacy/windows-pywebview/geogebra，csproj 再从归档目录 Content Include——活跃构建向"只读归档"写入并依赖其路径 → dest 改 dist/geogebra-cache/ 并同步 csproj 路径 |
| SP-146 | P2 | 链路缺口 | shared/release.json:23-27；release/manifests/signing-policy.yaml:14 | release.json 声明 updateManifest: ed25519、策略声明 threshold: 2，但全仓无任何步骤产出签名更新清单——验证链只有验证器没有生产者 → 发布 publish 阶段增清单生成+双 key 签名步骤，或 release.json 注明"规划中"消除假声明 |
| SP-147 | P2 | 策略漂移 | release/manifests/signing-policy.yaml:10-13 | 策略声明 signing_tool: cosign + keyless_oidc_issuer + certificate_identity，而实现全走 gh attestation——策略文件与实现工具/身份字段零一致性检查 → 统一口径或加一致性校验 |
| SP-148 | P2 | 策略执行缺口 | agent/tests/redteam_e2e_test.py:74,110-113 | DEFAULT_BUDGET = CATALOG["actions"][0].get("budget", ...) 只取第一条 action 的预算当全局默认——evaluate 不按 action 查各自 budget，catalog 逐条预算字段实际零执行 → evaluate 按 action.intent 查 per-action budget 判定，删 fallback |
| SP-149 | P2 | 预算可伪造 | agent/tests/redteam_e2e_test.py:110-113 | budget_used/max_bytes 均由被评估方自报——broker 不维护每会话累计计数，恶意方恒报 1 即永不过限 → broker 侧 per-session 计数器（并发安全）并以计数判定，补"谎报仍被拒"用例 |
| SP-150 | P2 | 契约漂移 | agent/tests/redteam_e2e_test.py:49-62,262-270 | e2e ProposedAction 与冻结 action.schema.json 十字段严重漂移：e2e 用 intent/generation/budget_used/max_bytes，schema 要求 tab_id/origin/method/document_generation（仅 6/11 字段重合）；test_field_set_matches_schema 声称"与 schema 对齐"却从不读 schema 文件 → 元断言直接加载 schema 的 required 集合对比；e2e 模型补字段对齐冻结契约 |
| SP-151 | P2 | 归档边界/死门禁 | .github/workflows/ci.yml:40,77-96,104-112 | ci.yml python-quality 整个 job（bandit/mypy/8 个 selftest）跑在 legacy 归档栈且注释仍称其为"活跃新栈" → 迁移为低频归档守护并修正注释，常跑门禁对准现役栈 |
| SP-152 | P2 | 门禁绕过 | .github/workflows/release.yml:36-40；release-windows.yml:22 | pin-check 正则为黑名单式：uses: action@latest 漏判放行；且 composite action（.github/actions/*/action.yml）内 uses: 不在扫描面 → 改白名单式断言并把 .github/actions/ 纳入扫描 |
| SP-153 | P2 | CI 重复/漂移 | .github/workflows/release.yml:113-152 vs 三平台子流 | provenance/SBOM/校验和验证逻辑在编排器+三平台共 4 处内联重复，漂移已发生（-P 8 vs -P 4）→ 抽 composite action 或统一调脚本 |
| SP-154 | P2 | 归档边界 | scripts/verify_cross_end_lists.py:48,94 | 活跃对账门禁把 legacy/windows-pywebview/app/asset_scheme.py、url_utils.py 作为强制对账端——归档栈文件被删除/移动时现役门禁断链 → 对账端切至现役源，legacy 对照降级为可选 |
| SP-155 | P2 | 脚本健壮性 | release/tools/verify_artifact_set/verify_artifact_set.py:99；generate_sbom/generate_sbom.py:43 | 两脚本 main() 对 manifest JSON json.loads 无异常处理——坏 JSON 直接 traceback → try/except + exit 2 + 文件名上下文 |
| SP-156 | P3 | 无界增长 | agent/tests/redteam_e2e_test.py:81,119-122 | consumed_nonces 集合无上限——长生命周期 broker 内存无界 → 加容量上限+逐出 |
| SP-157 | P3 | 授权宽限 | agent/tests/redteam_e2e_test.py:97 | expires_at 只判"已过期"，无最大 TTL 上限——now+10 年的授权永久有效 → broker 设 max_ttl 并超限拒绝 |
| SP-158 | P3 | 模拟失真 | agent/tests/redteam_e2e_test.py:104 | 代际判定写死 generation != 0——broker 无当前代际状态，合法新代际（=1）也被拒 → broker 持 current_generation（可推进） |
| SP-159 | P3 | 边界语义 | agent/tests/redteam_e2e_test.py:78-80 | policy_version or .../max_actions or ...——显式传 0/""（falsy 合法值）被静默替换为默认 → 改 is None 判定 |
| SP-160 | P3 | 测试重复 | tests/python/release_tools_test.py:120-144；release_chain_test.py:19-46 | _version_tuple 用例双文件重复 → 并入 release_chain_test 删重复类 |
| SP-161 | P3 | 测试基建 | tests/python/ 六文件 | 各自重复 ROOT=+sys.path.insert 样板 → 新增 conftest.py 统一注入，删六处样板 |
| SP-162 | P3 | 测试重复 | tests/ui-regression/host_bridge.test.mjs:13-37；start_host.test.mjs:25-40 | 同一 cs 桥桩两文件各实现一份 → 抽 helpers.mjs 共享 |
| SP-163 | P3 | CI 口径 | .github/workflows/ci.yml:131；start_page.test.mjs:5 | CI 显式枚举 5 个 mjs 文件——新增第六个测试文件会静默不跑 → CI 改目录模式或 glob |
| SP-164 | P3 | 配置三源 | .github/workflows/ci.yml:73；README.md:42；pyproject.toml:15 | ruff ignore 清单三处手工复制 → 测试豁免进 pyproject per-file-ignores，单源化 |
| SP-165 | P3 | 扫描缺口 | validate_release.py:66-67 | AST 语法扫描目录缺 agent/（ruff 门禁面含 agent，两门口径不一）→ 元组补 'agent' |
| SP-166 | P3 | 死资产 | validate_release.py:77-81；windows/packaging/*.template | MSIX/appinstaller 路线模板全仓零引用，validate_release 却仍每次解析校验 → 确认弃用后删模板与校验分支 |
| SP-167 | P3 | 目录残留 | aegis-专家评审包/legacy/windows-pywebview/.mypy_cache/3.14/ | 含整份 mypy 缓存镜像（本地生成器跑过未清）→ 删除该缓存树 |
| SP-168 | P3 | 冗余规则 | .gitignore:41,44 | aegis-source-all.md 被 aegis-source-*.md 覆盖、aegis-source-*.zip 被 aegis-*.zip 覆盖——两条死规则 → 删除 |
| SP-169 | P3 | 描述过时 | .github/actions/prepare-geogebra/action.yml:5 | 描述仍称"release-windows（PyInstaller datas）"——单轨 C# 后该用途已不存在 → 更新描述 |
| SP-170 | P3 | 运行器不一致 | agent/tests/redteam_test.py:68-73 | __main__ 入口无逐用例异常捕获——首个失败即中断（e2e 版有隔离+汇总）→ 对齐收集-汇总模式 |
| SP-171 | P3 | 校验双源 | .github/workflows/agent-redteam.yml:30-38 | 内联 yaml 断言复刻 redteam_test.py 的 catalog 校验（且为弱化版）→ 删内联块或改为单跑 pytest |
| SP-172 | P3 | 协作基建 | .github/（仅 actions/ 与 workflows/） | 无 ISSUE_TEMPLATE、无 PULL_REQUEST_TEMPLATE——安全项目缺漏洞报告引导入口 → 补最小 issue 模板（bug/安全分型，安全类引导私密披露）与 PR 检查单 |
| SP-173 | P3 | 版本硬编码 | README.md:38 | 构建命令硬编码 ".NET 10.0.302" 补丁版本——SDK 升级即过时 → 改 10.0.x 或引 global.json 单源 |
| SP-174 | P3 | 口径不一 | .github/workflows/release-windows.yml:196-204 | SBOM 双生成器并存：发布用 sbom-action 扫源码目录并以单一 SBOM 绑定全部二进制；generate_sbom.py（清单驱动）仅拿测试向量跑 → 统一为制品级 SBOM 或注明分工 |
| SP-175 | P3 | 解析健壮性 | release/tools/verify_manifest/verify_manifest.py:36-40 | 以 MULTILINE+DOTALL 手写正则从 yaml 抽 threshold——可跨块误绑；CI 已锁 pyyaml → 改 yaml.safe_load 结构化读取 |
| SP-176 | P3 | 忽略规则/残留 | .gitignore:85；.mimosa/ | /.zcode/ 带根锚定而 .mimosa/ 无锚——子目录 .zcode 会漏忽略 → 去掉前导 /（或 **/.zcode/） |

---

## 执行批次日志（随执行更新）

| 批次 | 提交 | 范围 | 项数 | 验证 |
|---|---|---|---|---|
| （待执行） | | | | |

> 完成度：0/229。执行口径与 2026-09-23 轮一致：分批执行、每批全量验证后提交、台账随批更新。

# 真机验证 Runbook（运行门禁——device-validation.md）

> 依据：aegis_future_development_and_target_source_tree.md 蓝图阶段 C/D 退出条件
> （运行门禁——真实设备验证）+ 蓝图 docs/runbooks（runtime-update-restart/
> security-release/incident-response——运行门禁补充）+ 全球调研（WebView2 官方
> 安全指南/Android Termination API——阶段 C/D 落地依据）。
> 需真实设备执行（WebView2 Runtime/Android 真机）——本清单供按设备执行——
> 每项记录结果——失败项修复后重验（运行门禁 fail-closed——蓝图）。

## 一、Windows WebView2 真机验证（蓝图阶段 C 退出条件——真实 WebView2 Runtime）

| # | 场景 | 验证点 | 预期（安全默认值） |
|---|---|---|---|
| 1 | 远程页面 bridge 探测 | 远程站点探测本地 bridge/命令（postMessage/命令面探测） | **无 native API**——探测失败（ADR-003） |
| 2 | 跨源 iframe | 页面内嵌跨源 iframe 导航 | FrameNavigationStarting 经 broker——拒绝/审计 |
| 3 | 重定向 | 导航被重定向到拒绝 URL（data:/blob:） | NavigationStarting 真实取消——错误页可见 |
| 4 | javascript:/data:/file: | 地址栏/页面尝试这些协议 | OriginPolicy 拒绝（url-origin-invalid 向量） |
| 5 | 自定义协议 | aegis:/reader: 等内部协议 | 仅受信壳页流程放行（WB-168，2026-10-01 审计改述正典机制：Windows = ntp.aegis.local 受信虚拟主机之外的 scheme 一律经 UrlSafety/OriginPolicy 拒绝——http/https 白名单外全拒；原「INTERNAL_SCHEMES（P0-01）」为归档 Python 栈机制，已随 ADR-009 冻结） |
| 6 | 下载 MIME 混淆 | 下载 content-disposition/类型混淆 | 下载经 broker 判定（MIME/最终 URL/size） |
| 7 | 重复确认 | 高风险动作重复确认 | **启用前置（R9-DOC-07 补）**：确认面板只在 `NavigationConfirmationGate.IsRequired` 为真时出现——即环境变量 `AEGIS_REQUIRE_NAVIGATION_CONFIRMATION=1` 或注册表 `HKCU\Software\Aegis Browser\RequireNavigationConfirmation`；而安装器 `docs/release/AegisSetup-CSharp.iss:73` **刻意不写**该值（只写 RequireNativePolicyCore，:79），所以**唯一发布制品上面板永不出现**：验证人须先设该环境变量再走本步，或改读启动后安全日志首行 `[adjudication]`（要求=true/false、来源、确认门状态）——否则「看不到面板」会被误判成缺陷，或反过来凭「UI 不存在」签一个无证据的通过。判定本体：确认流经 C# Broker（BrowserPolicyBroker）→ Rust 策略核心裁决，确认面板 pending 态唯一持有（NavigationConfirmationGate）——重复/重放请求按代际与 pending 唯一性拒绝（WB-122，2026-09-26 审计——ApprovalManager 已删除） |
| 8 | 标签代际竞态 | 快速切标签后旧导航尝试执行 | AuthorizedAction 代际变化失效 |
| 9 | renderer crash | WebView 渲染进程崩溃 | 错误页可见（WebErrorStatus）——恢复不自动放行 |
| 10 | Runtime 更新重启 | NewBrowserVersionAvailable | **本步暂无执行对象**——正典树未订阅该事件（无 `RuntimeUpdater.cs`，`windows/` 全树零命中），「保存状态/通知/受控重启」为 ADR-001 后果段的设计要求；缺口已登记在 parity 清单，实现前此步记 N/A 而非通过 |
| 11 | 历史导航是否经策略链（R8-CS-SEC-03 **待实测**，不得凭猜登记） | 依次访问 A→B，然后点「后退」「前进」「重新加载」——菜单、快捷键、无痕窗、NTP 桥四个入口各跑一次，从审计日志数 `NavigationStarting` 与 broker 授权尝试的条数 | 官方 `ICoreWebView2` 参考对 `GoBack/GoForward/Reload` 是否触发 `NavigationStarting` **未置可否**（只写「main frame 请求导航到不同 URI 时运行」），两种结果都必须落地成后续动作：①**触发** ⇒ 那 6 个直取 `Control.GoBack()` 的入口无妨（策略链自然覆盖），但须同时确认历史重放不因 nonce 已消费而被拒（否则「后退」在出货态是坏的）；②**不触发** ⇒ 该 6 入口属未裁决的重导航面，须补 broker 侧「同源已授权」判定或改走 `Navigate()` 复用授权链。**本步未执行前，R8-CS-SEC-03 不登记为缺陷** （第八轮 §十一 同口径：无实测即不判定方向） |

## 二、Android 真机验证（蓝图阶段 D 退出条件）

| # | 场景 | 验证点 | 预期（安全默认值） |
|---|---|---|---|
| 1 | bridge absence | 远程页面探测 addJavascriptInterface | 无 bridge（ADR-003——只本地 origin） |
| 2 | renderer crash | onRenderProcessGone（chrome://crash） | 返回 true + 清理 WebView——错误页可重试 |
| 3 | 生命周期 | 旋转/后台/内存回收/进程重建 | BrowserState 状态机——可见 UI 状态 + 可审计原因 |
| 4 | 下载 | 下载触发 | **实测链（R9-DOC-06 更正，此前写「经 broker 判定 MIME/最终 URL/size/目录」与代码不符）**：`WebViewDownloadHandler.kt:113-114` 的 `WebViewDownloadTargetGuard` 判 **scheme + 保留地址**（第八轮 R8-AD-03 / 第九轮 #130 落地的硬拒在这里），随后 `DownloadPolicy` 按**扩展名**两级拦截——全链不经 `AndroidBroker`，也不判 MIME、size、目录（`DownloadPolicy.kt` grep mime/size 零命中）。按旧文执行会把「无 size/目录门禁」记成通过，而真正落地的保留地址硬拒反而没有真机步骤——本步现在就按上述实测项验：内网/元数据地址的下载应被拒并脱敏留痕 |
| 5 | 重定向 | 导航重定向到拒绝 URL | broker 拒绝——错误页 |
| 6 | 网络切换 | Wi-Fi↔移动网络切换 | 可审计原因 + 安全默认值 |
| 7 | 存储恢复 | 进程重建后状态恢复 | 恢复经 broker 策略重验（不自动放行） |

## 三、记录与门禁

- 每项验证记录（通过/失败 + 证据）——**失败项需修复后重验**（运行门禁 fail-closed）
- 全部通过后运行门禁闭合（蓝图七门禁全闭合——正式发布前提）
- 与 runbooks 联动（WB-069，审计 2026-09-23 清单·W5 批）：security-release
  runbook 在 `release/runbooks/security-release.md`（已落地）；蓝图所列
  **incident-response runbook 尚未落地**——验证失败需升级为安全事件时，
  按 SECURITY.md 报告流程 + security-release runbook 处置，不以不存在的
  文档为依赖

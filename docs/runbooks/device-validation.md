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
| 5 | 自定义协议 | aegis:/reader: 等内部协议 | 仅受信 chrome UI（INTERNAL_SCHEMES——P0-01） |
| 6 | 下载 MIME 混淆 | 下载 content-disposition/类型混淆 | 下载经 broker 判定（MIME/最终 URL/size） |
| 7 | 重复确认 | 高风险动作重复确认 | ApprovalManager nonce 一次性——重放拒绝 |
| 8 | 标签代际竞态 | 快速切标签后旧导航尝试执行 | AuthorizedAction 代际变化失效 |
| 9 | renderer crash | WebView 渲染进程崩溃 | 错误页可见（WebErrorStatus）——恢复不自动放行 |
| 10 | Runtime 更新重启 | NewBrowserVersionAvailable | 保存状态/通知/受控重启（runtime-update-restart） |

## 二、Android 真机验证（蓝图阶段 D 退出条件）

| # | 场景 | 验证点 | 预期（安全默认值） |
|---|---|---|---|
| 1 | bridge absence | 远程页面探测 addJavascriptInterface | 无 bridge（ADR-003——只本地 origin） |
| 2 | renderer crash | onRenderProcessGone（chrome://crash） | 返回 true + 清理 WebView——错误页可重试 |
| 3 | 生命周期 | 旋转/后台/内存回收/进程重建 | BrowserState 状态机——可见 UI 状态 + 可审计原因 |
| 4 | 下载 | 下载触发 | 经 broker 判定（MIME/最终 URL/size/目录） |
| 5 | 重定向 | 导航重定向到拒绝 URL | broker 拒绝——错误页 |
| 6 | 网络切换 | Wi-Fi↔移动网络切换 | 可审计原因 + 安全默认值 |
| 7 | 存储恢复 | 进程重建后状态恢复 | 恢复经 broker 策略重验（不自动放行） |

## 三、记录与门禁

- 每项验证记录（通过/失败 + 证据）——**失败项需修复后重验**（运行门禁 fail-closed）
- 全部通过后运行门禁闭合（蓝图七门禁全闭合——正式发布前提）
- 与 runbooks（security-release/incident-response）联动：验证失败按事故响应处理

# 支持功能（supported-features.md）

> 依据：蓝图 docs/product/supported-features + 阶段 A 完成标准（"支持功能说明
> 不再宣称超出现实能力"）——当前产品能力（阶段 C/D 最小安全壳——不宣称未实现
> 功能）。

## 当前支持（阶段 C/D 最小壳落地）

| 平台 | 支持功能 |
|---|---|
| Windows（C#/.NET 10 + WebView2——阶段 C） | 地址栏导航（经 Broker 决策）、后退/前进/刷新/停止、安全错误页、单标签浏览、导航真实取消（NavigationStarting/Frame/NewWindow）、权限默认拒绝（PermissionRequested）、脱敏审计、审批管理（ApprovalManager）、终止开关（KillSwitch） |
| Android（Kotlin/Compose——阶段 D） | 导航经 broker 决策、renderer crash 恢复（onRenderProcessGone 返回 true）、BrowserState 状态机（Active/Background/Suspended/Restoring/Crashed/Closed）、错误页/恢复指示 |

## 明确不做（蓝图"不做清单"——不宣称）

- Chromium fork / CEF 产品化 / 浏览器扩展生态
- 任意远程网页 native bridge / 网页工具栏 DOM 注入
- HTTP MCP server / Agent 自动下载/上传/导出 / 自动执行网页"指令"
- 云端同步密码 / 用户脚本 / 插件系统
- 书签导入/主题/阅读器/AI/同步/复杂工具栏（阶段 C 明确"先不做"——蓝图）

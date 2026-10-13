# 隐私默认（privacy-defaults.md）

> 依据：蓝图 docs/product/privacy-defaults + 蓝图迁移表（event_log/crash_reporter
> 迁入 Diagnostics——脱敏/速率限制——不可把 token/网页内容写入日志）+ 阶段 C/D/E
> 落地（脱敏审计——audit-event schema——不含 token/query secret）。

## 隐私默认（数据最小化——蓝图）

| 项 | 默认 |
|---|---|
| 日志/审计 | 脱敏（audit-event schema——不含 token/网页内容/query secret——Diagnostics 非敏感日志） |
| 存储 | WB-032（审计 2026-09-23 清单·W5 批）如实描述：**明文**落盘于 OS 应用私有目录——C# 端 SQLite/文件（AppPaths 数据目录）、Android 端 SharedPreferences/应用存储，受 OS 沙箱（用户隔离 + 安装包签名绑定）保护；蓝图的 DPAPI/Keystore **静态加密未落地**（登记为后续增强——密码/令牌本就不落盘，见下行） |
| 凭证 | 不记录/不读取给网页或 Agent。**这一行的保证不来自任何凭据保护模块**（R9-DOC-11，第九轮 2026-10-13 实测：`credential_guard`（OS keystore/DPAPI）只存在于 `legacy/windows-pywebview/app/`，正典全树 `CredentialGuard`/`ProtectedData`/`DPAPI`/`KeyStore` 零命中）⇒ 实际机制是「密码/令牌本就不落盘」（下一行）＋ OS 沙箱，与上一行「DPAPI/Keystore 静态加密未落地」同口径；此前把归档栈的模块名当成正典能力写 |
| 恢复状态 | 不持久化密码/令牌/完整敏感页面内容（蓝图阶段 D——SavedStateHandle 安全上下文） |
| 遥测 | 无默认遥测（非敏感健康/崩溃信息——脱敏——用户可审阅） |
| WebView2 内核能力 | R9-B48（第九轮 2026-10-13 定稿）三项**显式**关：`AreDevToolsEnabled`（F12/右键打开开发者工具——SDK 文档默认 true）、`IsGeneralAutofillEnabled`（姓名/地址/表单历史——默认 true）、`IsPasswordAutosaveEnabled`（保存密码提示——默认 false，这里仍显式写住：SDK 文档同时说明「关掉之前已保存的密码仍会被自动填充」，靠默认值等于靠这台机器的历史）。落点 `windows/src/Aegis.Windows.App/WebView/WebView2Hardening.cs`（两个窗口的唯一初始化路径）+ 启动留痕 `[security] 标签 …: DevTools=关 / 表单自动填充与密码保存已关闭`；诊断需要时显式开 `AEGIS_ENABLE_DEVTOOLS=1`（安装器不写它，与确认门/原生核心门同形） |

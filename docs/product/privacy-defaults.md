# 隐私默认（privacy-defaults.md）

> 依据：蓝图 docs/product/privacy-defaults + 蓝图迁移表（event_log/crash_reporter
> 迁入 Diagnostics——脱敏/速率限制——不可把 token/网页内容写入日志）+ 阶段 C/D/E
> 落地（脱敏审计——audit-event schema——不含 token/query secret）。

## 隐私默认（数据最小化——蓝图）

| 项 | 默认 |
|---|---|
| 日志/审计 | 脱敏（audit-event schema——不含 token/网页内容/query secret——Diagnostics 非敏感日志） |
| 存储 | WB-032（审计 2026-09-23 清单·W5 批）如实描述：**明文**落盘于 OS 应用私有目录——C# 端 SQLite/文件（AppPaths 数据目录）、Android 端 SharedPreferences/应用存储，受 OS 沙箱（用户隔离 + 安装包签名绑定）保护；蓝图的 DPAPI/Keystore **静态加密未落地**（登记为后续增强——密码/令牌本就不落盘，见下行） |
| 凭证 | 不记录/不读取给网页或 Agent（credential_guard——OS keystore/DPAPI） |
| 恢复状态 | 不持久化密码/令牌/完整敏感页面内容（蓝图阶段 D——SavedStateHandle 安全上下文） |
| 遥测 | 无默认遥测（非敏感健康/崩溃信息——脱敏——用户可审阅） |

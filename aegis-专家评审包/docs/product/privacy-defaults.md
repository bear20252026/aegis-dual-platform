# 隐私默认（privacy-defaults.md）

> 依据：蓝图 docs/product/privacy-defaults + 蓝图迁移表（event_log/crash_reporter
> 迁入 Diagnostics——脱敏/速率限制——不可把 token/网页内容写入日志）+ 阶段 C/D/E
> 落地（脱敏审计——audit-event schema——不含 token/query secret）。

## 隐私默认（数据最小化——蓝图）

| 项 | 默认 |
|---|---|
| 日志/审计 | 脱敏（audit-event schema——不含 token/网页内容/query secret——Diagnostics 非敏感日志） |
| 存储 | 加密（Storage——DPAPI/Keystore——蓝图迁移）——最小化（只存必要数据） |
| 凭证 | 不记录/不读取给网页或 Agent（credential_guard——OS keystore/DPAPI） |
| 恢复状态 | 不持久化密码/令牌/完整敏感页面内容（蓝图阶段 D——SavedStateHandle 安全上下文） |
| 遥测 | 无默认遥测（非敏感健康/崩溃信息——脱敏——用户可审阅） |

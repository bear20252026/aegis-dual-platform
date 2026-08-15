# Local IPC Session（阶段 G——蓝图 agent/local-ipc/session.md）

> 每连接 session（蓝图：每连接 session/nonce——官方：短会话 token 生命周期 +
> refresh rotation——多方交叉比对）。

## 会话模型

- **每连接 session**：每次本地 IPC 连接独立 session（session_id——非全局）
- **nonce 一次性消费**：每个 ProposedAction 绑定 nonce——broker 一次性消费
  （重放拒绝——approvals-replay 向量）
- **标签代际绑定**：session 绑定 tab_id + document_generation——跨标签/代际
  变化使批准失效（AuthorizedAction 字段——contracts action schema）
- **短生命周期**：session token 短生命周期（官方会话加固）+ 过期拒绝

## 审计

- 会话事件写入脱敏审计（audit-event schema——不含 token/query secret）
- 会话撤销立即生效（kill switch——revocation.md）

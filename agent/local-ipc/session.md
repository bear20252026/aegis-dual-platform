# Local IPC Session（阶段 G——蓝图 agent/local-ipc/session.md）

> 每连接 session（蓝图：每连接 session/nonce——官方：短会话 token 生命周期 +
> refresh rotation——多方交叉比对）。

## 现状（第八轮 B8 实测，2026-10-05）——本文是设计意图，不是交付清单

- **交付面为零实现**：OS ACL/套接字访问控制、连接进程 PID/可执行路径核验、IPC
  传输与每连接会话的建立、撤销触发链——正典树（`agent/`、`windows/`、`android/`、
  `core/`）中**都没有对应代码**。`agent/broker.py:29-33` 明确声明这些 OS 能力
  不在其职责内，并把真实强制点指向三端 Broker；此前它自称「local-ipc/*.md 记有
  现状注记」而注记并不存在——本轮补齐。
- **现役只有裁决面**：`agent/broker.py` 的 `PolicyBroker`（默认拒绝、nonce 一次性
  消费 + 有界重放缓存、工具描述哈希绑定），以及 `agent/tests/` 的红队夹具。
  没有传输层，也就没有「谁在连」的身份概念。
- **`AgentAuthContext` 属归档栈**：唯一实现在
  `legacy/windows-pywebview/app/mcp.py:51`（ADR-009 D4 只读冻结，禁止 import）——
  不是现役等价实现。
- 本文以下各节的「设计要点」保持原样，作为阶段 G 若复开时的验收依据。
- **有实现的部分**：session/nonce/代际绑定的**语义**存在于契约与三端 Broker——
  `contracts/schemas/action.schema.json` 的 `session_id`/`tab_id`/
  `document_generation`/`nonce`/`expires_at` 字段，以及 C# `BrowserPolicyBroker`
  的会话上下文与重放拒绝。缺的是把它们送进「每连接 session」的那条 IPC 通路。

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

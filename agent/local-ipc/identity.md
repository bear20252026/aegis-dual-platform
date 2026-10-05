# Local IPC Identity（阶段 G——蓝图 agent/local-ipc/identity.md）

> 本地受控 IPC 身份（蓝图：OS ACL/进程身份——官方 CSA：会话加固（短 token/
> 绑定/rotation）——多方交叉比对）。

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
- **本节特有的过期口径**：下文「SP-064 注记」把 `E2EBroker` 称作现役等价实现，
  该类已在第六轮连类删除（全树零命中）——正解是：现役 `agent/broker.py` 的
  `PolicyBroker` 承担**动作裁决**，但**不**承担身份核验（OS 侧无人做）。

## 身份验证（蓝图 + 官方）

- **OS ACL**：本地 IPC socket 仅允许 Aegis 进程（broker）连接（OS 权限——
  Windows ACL——进程身份）
- **进程身份**：验证连接进程身份（PID/可执行路径——防其他进程冒充）
- **短期 token**：每连接短期 token（短生命周期——官方会话加固）——绑定
  进程/会话属性（源身份绑定——CSA 官方）

## 设计要点

- 传输层验证 token 后构造 `AgentAuthContext`（principal/scopes/expires_at/
  nonce——mcp.py P0-02 时代已实现）——网页内容不得直接构造。
  > SP-064（审计 2026-09-23 清单·SP1 批）曾注记「现役等价实现为 agent/ 的
  > E2EBroker」——**该指针已失效**：`E2EBroker` 在第六轮连类删除，全树零命中。
  > 现况（第八轮 B8 更正）：`agent/broker.py` 的 `PolicyBroker` 只做动作裁决，
  > 「验证连接进程身份后构造 `AgentAuthContext`」这条链**在正典树中无人实现**，
  > `AgentAuthContext` 仅存于归档 `legacy/windows-pywebview/app/mcp.py:51`。
- 令牌不落地日志（脱敏——audit-event schema）
- 命名空间隔离（CSA 官方——多服务器独立凭证——防"上帝令牌"——每 IPC
  连接独立会话）

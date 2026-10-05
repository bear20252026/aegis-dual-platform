# Local IPC Revocation（阶段 G——蓝图 agent/local-ipc/revocation.md）

> 撤销机制（蓝图：原生 kill switch 立即撤销已发出但尚未执行的授权——
> 阶段 G 完成标准——官方：JIT 重新授权/会话撤销）。

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
- **KillSwitch 的端别现状**：Windows 有实现但覆盖面有限——主窗口导航/下载/审批链
  判定真实存在，**NTP 宿主桥**（`importBookmarks`/`importHistory`/`restoreSession`）
  与前进/后退/重载等 6 个导航入口不查该开关；**Android 全树零 KillSwitch 代码**。
  因此本文「任何副作用服务执行前检查」一句在两端正典代码里都不成立。

## Kill Switch（原生——不依赖 Agent 配合）

- **原生 UI 触发**（Chrome 终止开关——Windows KillSwitch/Android 对应）——
  立即撤销已发出但尚未执行的授权
- 任何副作用服务执行前检查（Broker 唯一副作用点——ADR-002——EnsureNotEngaged）
- 紧急场景：Agent 网络副作用永久关闭（ADR-004——broker 完成前）

## 会话撤销

- 撤销后：已授权但未执行的 ProposedAction 全部失效（AuthorizedAction
  expires/revoked）
- 重新授权需用户显式确认（JIT——CSA 官方）
- 撤销事件审计（脱敏）

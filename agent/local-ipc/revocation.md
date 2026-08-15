# Local IPC Revocation（阶段 G——蓝图 agent/local-ipc/revocation.md）

> 撤销机制（蓝图：原生 kill switch 立即撤销已发出但尚未执行的授权——
> 阶段 G 完成标准——官方：JIT 重新授权/会话撤销）。

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

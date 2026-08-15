# Local IPC Identity（阶段 G——蓝图 agent/local-ipc/identity.md）

> 本地受控 IPC 身份（蓝图：OS ACL/进程身份——官方 CSA：会话加固（短 token/
> 绑定/rotation）——多方交叉比对）。

## 身份验证（蓝图 + 官方）

- **OS ACL**：本地 IPC socket 仅允许 Aegis 进程（broker）连接（OS 权限——
  Windows ACL——进程身份）
- **进程身份**：验证连接进程身份（PID/可执行路径——防其他进程冒充）
- **短期 token**：每连接短期 token（短生命周期——官方会话加固）——绑定
  进程/会话属性（源身份绑定——CSA 官方）

## 设计要点

- 传输层验证 token 后构造 `AgentAuthContext`（principal/scopes/expires_at/
  nonce——mcp.py P0-02 已实现）——网页内容不得直接构造
- 令牌不落地日志（脱敏——audit-event schema）
- 命名空间隔离（CSA 官方——多服务器独立凭证——防"上帝令牌"——每 IPC
  连接独立会话）

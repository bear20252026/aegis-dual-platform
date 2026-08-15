# Action Planner Contract（阶段 G——蓝图 agent/action-planner-contract.md）

> Agent 永远是 planner，不是 security decision maker（ADR-004——蓝图）。
> 模型输出只能是结构化 ProposedAction——不得直接导航/下载/导出/调用原生 API。

## ProposedAction（结构化意图——经 broker 授权）

```json
{
  "intent": "navigate",
  "target_origin": "https://a.gov.cn",
  "method": "GET",
  "canonical_parameters": "/page",
  "scope": "navigation:read",
  "budget": { "max_bytes": 8192, "max_actions": 5 },
  "session_id": "<local-ipc session>",
  "nonce": "<一次性 nonce>"
}
```

## 约束（调研交叉——工具级 scope/每调用验证）

- **工具级 scope 最小权限**（CSA 官方——读文件工具不带删除权限）——每个
  ProposedAction 绑定 scope——broker 每调用验证（JIT 高危显式重新授权）
- **工具描述哈希绑定**（CSA 官方——批准绑定描述哈希——调用前验证一致——
  描述变更需重新批准——防"地毯拉离"）——工具描述/参数视为不受信输入
- **资源预算**（max_bytes/max_actions——超长输入/超预算请求拒绝）
- **重放/竞态**（nonce 一次性 + 会话绑定 + 标签代际——scope 重放/跨标签拒绝）

## 禁止

- 模型/网页输出不直接产生副作用（提示注入/工具结果投毒不能转化为未批准副作用）
- 不自动下载/上传/导出/策略修改/支付/凭证操作（蓝图不做清单）
- HTTP MCP server（本地 IPC 先行——HTTP 另立 ADR）

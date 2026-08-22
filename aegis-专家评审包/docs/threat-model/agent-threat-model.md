# Agent 威胁模型（agent-threat-model.md）

> 依据：蓝图 docs/threat-model/agent-threat-model + 阶段 G（agent/ 目标结构——
> 红队 fixtures + action-catalog 逐项复开）+ 全球调研（CSA Agentic MCP 最佳实践
> v1——工具级 scope/每调用验证/工具哈希绑定 + 中文掘金 MCP RCE 拆解——工具投毒/
> STDIO 注入）。

## 威胁面（Agent 相关）

| 威胁 | 缓解（已落地——阶段 G + P0-02） |
|---|---|
| 提示注入（网页/PDF/邮件/工具结果——间接注入） | Agent 是 planner 非 decision maker——ProposedAction 经 broker——红队 fixtures 断言拒绝（agent/redteam） |
| 工具投毒（工具描述注入恶意指令——CVE-2025-6514 场景） | 工具描述哈希绑定（描述变更需重新批准——CSA）——redteam_e2e 测试 deny_description_hash |
| scope 重放/跨标签/并发竞态 | nonce 一次性（approvals-replay 向量）+ 标签代际 + 资源预算（broker 侧强制——P0-02） |
| 超长输入/超预算请求 | MAX_TEXT_BYTES/资源预算（P0-02——超预算拒绝——redteam fixtures） |
| HTTP MCP 未认证 | 本地 IPC 先行（OS ACL/进程身份/session/nonce/撤销——ADR-004）——HTTP 另立 ADR（OAuth 2.1/PKCE） |

## 完成标准（蓝图阶段 G）

- 提示注入/工具投毒/scope 重放/跨标签/超长输入/并发竞态 → 红队断言全部拒绝（无未批准副作用）
- kill switch 立即撤销已发出未执行授权（revocation）

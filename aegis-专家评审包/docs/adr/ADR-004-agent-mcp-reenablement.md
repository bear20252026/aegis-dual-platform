# ADR-004：Agent/MCP 默认无网络副作用（逐项复开）

- **状态：** Accepted（2026-08-16——按开发蓝图阶段 A——不可回退）
- **背景：** 当前 MCP 处理器（mcp.py）仅有工具白名单与部分 schema 校验——身份/scope/过期/nonce/重放/速率/预算缺失；Agent 域白名单/sitemap 高风险动作只写日志。专家审查 P0-02/P0-03 已修复（未认证拒绝/scope 校验/导航层白名单拒绝）。蓝图：Agent 永远是 planner 非 decision maker；MCP 只进入 broker。
- **决策：** 在 broker 完成并通过发布门禁前，**永久关闭 Agent/MCP 的网络副作用**（不自动下载/导出/发布/策略修改/自动提交/支付/凭证操作）；Agent 只生成结构化 ProposedAction；MCP 先本地受控 IPC（OS ACL/进程身份/每连接 session/nonce/撤销——mcp.py 已重建信任边界：AgentAuthContext/scope/资源预算），HTTP MCP 另立 ADR（OAuth 2.1/PKCE）。
- **后果：** 模型提示注入/网页污染/工具结果投毒不能转化为未批准副作用；恢复按"一项只读工具、一项确认式工具"逐步开放（阶段 G）。

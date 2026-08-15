# Agent（阶段 G——蓝图 agent/）

> 依据：aegis_future_development_and_target_source_tree.md 蓝图 agent/ 目录
> （测试优先、权限后置——重构完成前不包含对外网络 MCP server）+ 全球调研
> （CSA Agentic MCP 安全最佳实践 v1——OAuth 2.1/PKCE/工具级 scope/每调用验证/
> 令牌交换/工具哈希绑定 + 中文掘金 MCP RCE 拆解——工具投毒/STDIO 注入/
> 最小可行安全基线——多方交叉比对）

## 原则（ADR-004——Agent/MCP 默认无网络副作用）

- **Agent 永远是 planner，不是 security decision maker**（蓝图）——模型输出
  只能是结构化 `ProposedAction`——必须经 schema/origin/scope/预算/会话/标签
  代际/用户确认
- 网页、PDF、邮件、工具返回值、模型上下文都可能包含 prompt injection——
  **没有更改 system policy/scope/批准/信任 origin 的权限**
- MCP 先本地受控 IPC（OS ACL/进程身份/每连接 session/nonce/撤销）——HTTP MCP
  另立 ADR（OAuth 2.1/PKCE）——任何 transport 不能绕过 broker

## 逐项复开（蓝图——每增加 action 修改 contracts/policy/action-catalog.yaml）

- 第一批只恢复**只读低风险工具**（当前标签标题/非敏感当前 Origin——蓝图）
- 每增加 action：风险等级/scope/预算/确认规则/审计事件/负面红队样例/e2e 测试
- 文件写入/导出/策略修改/自动提交/支付/凭证操作**默认不自动化**

## 目录

- `action-planner-contract.md`：ProposedAction 契约（planner 输出——经 broker）
- `local-ipc/`：本地 IPC 身份/会话/撤销设计（identity.md/session.md/revocation.md）
- `prompts/`：仅开发测试（不作为安全边界——蓝图）
- `redteam/`：红队 fixtures（提示注入/工具投毒/重放竞态/资源预算——蓝图）
- `tests/`：红队测试（断言拒绝——无未批准副作用——蓝图完成标准）

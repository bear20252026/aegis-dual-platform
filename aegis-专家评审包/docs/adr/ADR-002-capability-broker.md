# ADR-002：Capability Broker 是唯一本地副作用点

- **状态：** Accepted（2026-08-16——按开发蓝图阶段 A——不可回退）
- **背景：** 当前远程网页、受信 UI、Agent 与可选 pytauri 命令面在多条路径到达相同 Python Api/NavQueue——能力不按调用者身份分配，而是"是否恰好走到某个 if"。专家审查与蓝图：三个信任域（远程网页/本地 chrome UI/Capability broker）——Broker 是唯一允许产生本地副作用的边界。
- **决策：** 所有导航、下载、导出、策略修改、更新申请与 Agent 工具执行必须经 Capability Broker；没有 AuthorizedAction（绑定 session/tab/document_generation/origin/method/canonical_parameters/scope/expires_at/nonce/policy_version）不能进入副作用服务；默认拒绝（fail-closed）。WebView adapter 只做事件转换，Chrome UI 只提交意图。
- **后果：** 消除"通用 bridge 把网页输入升级为本地能力"的结构性缺陷；安全决策收敛到单一可审计执行点；子模块间通过类型化 action 流转（不允许直接调用 UI/任意 service）。

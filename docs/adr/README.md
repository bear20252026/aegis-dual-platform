# docs/adr/ —— 架构决策记录索引（SP-076，审计 2026-09-23 清单·SP1 批）

> ADR-001..009 按序登记；每份头部含状态/关联/取代注记。现行终局口径为
> **ADR-009（C# 单轨正典栈）**——与其冲突的早期表述以各文件头部注记为准。

| ADR | 主题 | 状态 |
|---|---|---|
| [ADR-001](ADR-001-windows-host-webview2.md) | Windows 宿主 = WebView2 | Accepted |
| [ADR-002](ADR-002-capability-broker.md) | Capability broker（唯一副作用点） | Accepted |
| [ADR-003](ADR-003-no-remote-native-bridge.md) | 远程网页域无 native bridge | Accepted |
| [ADR-004](ADR-004-agent-mcp-reenablement.md) | Agent/MCP 复开（broker 前置+永久关网络副作用） | Accepted（SP-072 归档注记） |
| [ADR-005](ADR-005-rust-policy-core-pilot.md) | Rust 仅纯策略核心试点 | Accepted（amended by ADR-006/008——SP-073） |
| [ADR-006](ADR-006-native-policy-core-binding-rollout.md) | 策略核心 C ABI/UniFFI 绑定发布 | Accepted（外链核验 2026-09-27——SP-077） |
| [ADR-007](ADR-007-canonical-stack-and-single-source-guards.md) | 正典栈与单源守卫 | Accepted（D1 被 ADR-009 取代——WB-059 注记） |
| [ADR-008](ADR-008-rust-policy-core-as-single-adjudicator.md) | Rust 策略核心为唯一裁决源 | Accepted（SP-046/074 引用与冻结栈注记） |
| [ADR-009](ADR-009-full-migration-to-csharp.md) | **全功能迁移 C# 单轨（终局口径）** | Accepted，M1-M4 落地（SP-047/048 回写） |

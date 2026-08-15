# ADR-005：Rust 仅为纯策略核心试点（非全量重写）

- **状态：** Accepted（2026-08-16——按开发蓝图阶段 A——不可回退）
- **背景：** 部分观点倾向"用 Rust 全量重写更安全"。专家评估：换语言不能自动实现正确的来源校验/授权/确认/更新/发布策略；错误能力模型用 Rust 重写仍是不安全能力模型。蓝图：Rust 只承载稳定后的纯策略核心（无 UI/无网络/无文件）。
- **决策：** 第一阶段不引入 Rust UI/Tauri 壳/网络 daemon/全量重写；contracts 稳定后（蓝图阶段 F）试点小型无 I/O 纯核心（推荐：update manifest canonicalization + Ed25519 阈值验证；次选：URL/Origin canonicalization）——固定 toolchain、最小 crate 依赖、确定性测试向量、C ABI/UniFFI 接入；收益可量化（fuzz/差分测试/审计/可复现）才迁移 capability token/下载策略。
- **后果：** 缩小可信计算基并强化协议边界，而非把全部文件换成 .rs；Rust 版本可单独审计、无网络和 UI 依赖、所有外部调用有明确错误值；若维护成本超出能力，保留 C#/Kotlin 实现（安全契约不变）。

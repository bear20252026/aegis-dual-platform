# ADR-006：原生策略核心绑定采用 Kotlin UniFFI 与 Windows C ABI 的渐进发布

- **状态：** Accepted（2026-08-27）
- **背景：** `aegis-policy-core` 已通过 UniFFI proc-macro 暴露可测试的 Rust 策略边界，并已在本地从受锁定的 `0.32.0` 工具链生成 Kotlin 绑定。UniFFI 官方完整支持 Kotlin、Swift 和 Python；C# 仅有第三方生成器，不能作为 Windows 安全边界的无条件依赖。[1] [2]

## 决策

Android 使用由同一 `Cargo.lock` 中的 UniFFI 工具生成的 Kotlin 绑定，并将每个 Android ABI 对应的 `libaegis_policy_core.so` 连同生成源码作为可审计制品。生成代码经 JNA 加载动态库；因此 Android 制品必须显式携带与绑定同版本、同 ABI 的原生库，并在构建中校验文件名、ABI 和哈希。[3]

Windows 不接入未审计的第三方 UniFFI C# 生成器。Windows 后续仅通过一个最小、版本化、panic-guarded 的 C ABI 与受管理的 P/Invoke 包装层访问 Rust；在该 ABI、DLL 打包和加载测试全部落地前，Windows 继续使用现有受测试的 C# Broker。

运行时迁移采用显式特性开关。开关默认关闭；关闭时使用现有平台 Broker。若开关被启用但原生库缺失、ABI 版本不匹配、完整性检查失败或加载失败，导航必须被拒绝并记录不含敏感 URL 参数的诊断码，**不得**静默回退到另一套策略实现。该规则使启用状态保持失败闭合，并让禁用状态成为可控回退路径。

## 制品与验收契约

| 平台 | 受支持调用边界 | 必需制品 | 启用前最低门禁 |
|---|---|---|---|
| Android | UniFFI 0.32 生成 Kotlin + JNA | 生成的 Kotlin 源码、`jniLibs/<abi>/libaegis_policy_core.so`、SHA-256 清单 | 绑定再生成无漂移、四 ABI 构建、库名与哈希校验、加载失败拒绝测试 |
| Windows | 版本化 C ABI + P/Invoke | `aegis_policy_core.dll`、C ABI 版本常量、SHA-256 清单 | Windows x64 编译、ABI 探测、缺库/错版本拒绝测试、发布包内容校验 |

## 后果

该决策避免在两个平台同时切换运行时，从而将可回退范围限制在显式的构建开关。它也修正了“UniFFI 自动生成 C#”这一不准确前提。实际消除平台 Broker 重复实现只能在原生制品的可重现构建、签名/哈希验证和加载失败门禁完成后进行；本 ADR 不授权删除现有 C#/Kotlin 实现。

## 参考

[1] [UniFFI 0.32 用户指南：受支持语言](https://mozilla.github.io/uniffi-rs/)

[2] [UniFFI README：官方与第三方语言绑定范围](https://github.com/mozilla/uniffi-rs/blob/main/README.md)

[3] [UniFFI 用户指南：Kotlin Gradle 集成与 JNA 依赖](https://mozilla.github.io/uniffi-rs/latest/kotlin/gradle.html)

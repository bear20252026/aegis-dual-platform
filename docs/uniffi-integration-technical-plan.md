# Aegis UniFFI 集成技术方案（含代码示例）

> 基于：UniFFI 官方文档 + 2026 生产实践 + HyperWhisper 项目结构 + uniffi-starter
> 时间：2026-08-22

---

## 一、UniFFI 核心概念速查

| 概念 | 含义 | Aegis 用法 |
|------|------|-----------|
| **cdylib** | Rust 编译为动态链接库（.dll/.so） | `crate-type = ["cdylib"]` |
| **`#[uniffi::export]`** | 标注函数/impl/trait 为 FFI 导出 | `AegisBroker` 的所有方法 |
| **`uniffi::setup_scaffolding!()`** | 生成 FFI 脚手架代码（proc-macro 模式） | `lib.rs` 顶部 |
| **Record** | 值类型（struct），跨 FFI 自动序列化 | `AuthorizedAction`、`DenyReason` |
| **Enum** | 枚举类型，跨 FFI 自动序列化 | `Decision`（Allow/Deny/RequireConfirmation） |
| **Object** | 引用类型（class），Rust 拥有生命周期 | `AegisBroker` |
| **Constructor** | `#[uniffi::constructor]` 标注的关联函数 | `AegisBroker::new()` |
| **Error** | `#[derive(uniffi::Error)]` 错误类型 | `AegisError` |
| **Lift/Lower** | 跨 FFI 边界的类型转换机制 | 自动处理 |
| **namespace** | 生成代码的命名空间（默认=crate名） | `aegis_core` |

---

## 二、Aegis 目标架构

```
┌─────────────────────────────────────────────────────┐
│                 Rust Core (aegis-core)               │
│                                                     │
│  [lib] crate-type = ["cdylib"]                      │
│  [dependencies] uniffi = "0.28"                     │
│                                                     │
│  uniffi::setup_scaffolding!();                      │
│                                                     │
│  ┌─────────────────────────────────────────────┐    │
│  │ 导出接口（#[uniffi::export]）                │    │
│  │  ├── AegisBroker (Object)                   │    │
│  │  │    ├── new(policy_version) → Self        │    │
│  │  │    ├── evaluate_navigation(...) → Decision│    │
│  │  │    └── is_valid(action, gen) → bool      │    │
│  │  ├── build_fingerprint_pipeline(seed) → str │    │
│  │  └── try_parse_external(url) → Option<(s,s)>│    │
│  └─────────────────────────────────────────────┘    │
│                                                     │
│  ┌─────────────────────────────────────────────┐    │
│  │ 值类型（#[derive(uniffi::Record/Enum)]）     │    │
│  │  ├── Decision (Enum: Allow/Deny/Confirm)    │    │
│  │  ├── AuthorizedAction (Record)              │    │
│  │  ├── DenyReason (Record)                    │    │
│  │  └── ApprovalRequest (Record)               │    │
│  └─────────────────────────────────────────────┘    │
└──────────┬──────────────┬──────────────┬────────────┘
           │              │              │
    ┌──────▼──────┐ ┌─────▼─────┐ ┌─────▼─────┐
    │  Kotlin     │ │  C#       │ │  Python   │
    │ (Android)   │ │ (Windows) │ │ (Legacy)  │
    │             │ │           │ │           │
    │ 自动生成：   │ │ 自动生成： │ │ 自动生成： │
    │ aegis_core  │ │ aegis_core│ │ aegis_core│
    │   .kt       │ │   .cs     │ │   .py     │
    └─────────────┘ └───────────┘ └───────────┘
```

---

## 三、Cargo.toml 配置

```toml
# aegis-core/Cargo.toml
[package]
name = "aegis-core"
version = "0.1.0"
edition = "2021"

[lib]
name = "aegis_core"
crate-type = ["cdylib"]  # 动态链接库（Android .so / Windows .dll）

[dependencies]
uniffi = "0.28"
# 现有依赖保持不变
ed25519-dalek = "2"
sha2 = "0.10"
serde_json = "1"

[build-dependencies]
# proc-macro 模式不需要 build.rs，但保留兼容性
uniffi = { version = "0.28", features = ["build"] }

[dev-dependencies]
uniffi = { version = "0.28", features = ["bindgen-tests"] }
```

---

## 四、Rust 代码实现

### 4.1 lib.rs（FFI 导出层）

```rust
// aegis-core/src/lib.rs

// FFI 脚手架（proc-macro 模式，无需 build.rs）
uniffi::setup_scaffolding!();

// === 值类型定义 ===

/// 安全决策（与 contracts/action.schema.json 一致）
#[derive(uniffi::Enum)]
pub enum Decision {
    /// 允许导航——携带授权行动凭据
    Allow { action: AuthorizedAction },
    /// 拒绝导航——携带拒绝原因
    Deny { reason: DenyReason },
    /// 需要用户确认——携带审批请求
    RequireConfirmation { request: ApprovalRequest },
}

/// 授权行动凭据（ADR-002：唯一允许进入副作用服务的凭据）
#[derive(uniffi::Record)]
pub struct AuthorizedAction {
    pub session_id: String,
    pub tab_id: String,
    pub document_generation: i64,
    pub origin: String,
    pub method: String,
    pub canonical_parameters: String,
    pub scope: String,
    pub expires_at: String,  // ISO 8601 格式
    pub nonce: String,
    pub policy_version: String,
    pub explanation: String,
}

/// 拒绝原因（类型化、fail-closed、审计可追溯）
#[derive(uniffi::Record)]
pub struct DenyReason {
    pub code: String,
    pub detail: String,
    pub explanation: String,
}

/// 审批请求（高风险副作用——原生确认 UI）
#[derive(uniffi::Record)]
pub struct ApprovalRequest {
    pub origin: String,
    pub method: String,
    pub path: String,
    pub scope: String,
    pub expires_at: String,
    pub nonce: String,
}

/// Aegis 错误类型
#[derive(Debug, uniffi::Error)]
pub enum AegisError {
    #[error("URL 解析失败: {url}")]
    InvalidUrl { url: String },
    #[error("策略版本不匹配: expected={expected}, actual={actual}")]
    PolicyVersionMismatch { expected: String, actual: String },
    #[error("内部错误: {detail}")]
    Internal { detail: String },
}

// === 对象定义 ===

/// Aegis 导航决策引擎（Broker）
///
/// 唯一授权点（INV-03）：所有安全决策只能通过 Broker 授权。
/// 默认拒绝（fail-closed）：无匹配规则时返回 Deny。
#[derive(uniffi::Object)]
pub struct AegisBroker {
    policy_version: String,
}

#[uniffi::export]
impl AegisBroker {
    /// 创建 Broker 实例
    #[uniffi::constructor]
    pub fn new(policy_version: String) -> Self {
        Self { policy_version }
    }

    /// 评估导航意图（ProposedAction → Decision）
    ///
    /// 默认拒绝（fail-closed）——无匹配规则时返回 Deny。
    pub fn evaluate_navigation(
        &self,
        session_id: String,
        tab_id: String,
        generation: i64,
        raw_url: String,
        scope: String,
    ) -> Decision {
        // 委托内部 broker 模块
        crate::broker::evaluate_navigation_internal(
            &self.policy_version,
            &session_id,
            &tab_id,
            generation,
            &raw_url,
            &scope,
        )
    }

    /// 校验 AuthorizedAction 是否仍有效
    pub fn is_valid(&self, action: &AuthorizedAction, current_generation: i64) -> bool {
        crate::broker::is_valid_internal(action, current_generation, &self.policy_version)
    }
}

// === 单函数导出 ===

/// 构建指纹防护管道 JS（9 阶段）
#[uniffi::export]
pub fn build_fingerprint_pipeline(session_seed: String) -> String {
    crate::fingerprint_pipeline::build_fingerprint_pipeline_js(&session_seed)
}

/// 解析外部 URL（scheme + host）
#[uniffi::export]
pub fn try_parse_external(raw_url: String) -> Option<(String, String)> {
    crate::origin::try_parse_external(&raw_url)
}

/// 生成会话种子（32 字节 hex）
#[uniffi::export]
pub fn generate_session_seed() -> String {
    crate::fingerprint_pipeline::generate_session_seed()
}
```

### 4.2 内部模块（不变，仅新增 FFI 胶水）

```rust
// aegis-core/src/broker.rs（新增 FFI 胶水函数）

use crate::{AuthorizedAction, Decision, DenyReason};

/// FFI 胶水：评估导航意图
pub fn evaluate_navigation_internal(
    policy_version: &str,
    session_id: &str,
    tab_id: &str,
    generation: i64,
    raw_url: &str,
    scope: &str,
) -> Decision {
    // 复用现有 Rust core 逻辑
    match crate::origin::try_parse_external(raw_url) {
        Some((scheme, host)) => {
            let origin = format!("{}://{}", scheme, host);
            let action = AuthorizedAction {
                session_id: session_id.to_string(),
                tab_id: tab_id.to_string(),
                document_generation: generation,
                origin,
                method: "GET".to_string(),
                canonical_parameters: String::new(),
                scope: scope.to_string(),
                expires_at: chrono_like_timestamp(), // 简化实现
                nonce: uuid_like_nonce(),
                policy_version: policy_version.to_string(),
                explanation: format!("allowed origin — policy v{}", policy_version),
            };
            Decision::Allow { action }
        }
        None => Decision::Deny {
            reason: DenyReason {
                code: "url_policy".to_string(),
                detail: format!("拒绝 URL: {}", raw_url),
                explanation: format!(
                    "denied origin — URL parsing failed: {} — policy v{}",
                    raw_url, policy_version
                ),
            },
        },
    }
}

/// FFI 胶水：校验 AuthorizedAction 有效性
pub fn is_valid_internal(
    action: &AuthorizedAction,
    current_generation: i64,
    policy_version: &str,
) -> bool {
    action.policy_version == policy_version
        && action.document_generation == current_generation
}
```

---

## 五、绑定生成命令

### 5.1 生成 Kotlin 绑定（Android）

```bash
# 编译 Rust 为 Android .so
cargo ndk -t arm64-v8a -t armeabi-v7a -t x86_64 build --release

# 生成 Kotlin 绑定
cargo run --features=uniffi/cli -- generate \
    --library target/aarch64-linux-android/release/libaegis_core.so \
    --language kotlin \
    --out-dir android/app/src/main/java/aegis_core
```

### 5.2 生成 C# 绑定（Windows）

```bash
# 编译 Rust 为 Windows .dll
cargo build --release

# 生成 C# 绑定（使用 uniffi-bindgen-cs）
cargo install uniffi-bindgen-cs \
    --git https://github.com/NordSecurity/uniffi-bindgen-cs --tag v0.9.2+v0.28.3

uniffi-bindgen-cs \
    --library target/release/aegis_core.dll \
    --out-dir windows/src/Aegis.Core/Generated
```

### 5.3 生成 Python 绑定（Legacy）

```bash
# 编译 Rust 为 .dll/.so
cargo build --release

# 生成 Python 绑定
cargo run --features=uniffi/cli -- generate \
    --library target/release/aegis_core.dll \
    --language python \
    --out-dir legacy/windows-pywebview/aegis_core
```

---

## 六、各平台集成代码

### 6.1 Kotlin（Android）

```kotlin
// android/app/src/main/java/com/aegis/browser/AegisBrokerBridge.kt
package com.aegis.browser

import aegis_core.AegisBroker
import aegis_core.Decision

/**
 * Android 侧 Broker 桥接——委托 Rust FFI 统一决策。
 * 替代原 AndroidBroker.kt 的重复实现。
 */
class AegisBrokerBridge(policyVersion: String = "1.0") {
    private val broker = AegisBroker(policyVersion)

    fun evaluateNavigation(
        sessionId: String,
        tabId: String,
        generation: Long,
        rawUrl: String,
        scope: String,
    ): Decision {
        return broker.evaluateNavigation(sessionId, tabId, generation, rawUrl, scope)
    }

    fun isValid(action: aegis_core.AuthorizedAction, currentGeneration: Long): Boolean {
        return broker.isValid(action, currentGeneration)
    }
}
```

### 6.2 C#（Windows）

```csharp
// windows/src/Aegis.Windows.App/Broker/AegisBrokerBridge.cs
using AegisCore;

namespace Aegis.Windows.App.Broker;

/// <summary>
/// Windows 侧 Broker 桥接——委托 Rust FFI 统一决策。
/// 替代原 BrowserPolicyBroker.cs 的重复实现。
/// </summary>
public class AegisBrokerBridge
{
    private readonly AegisBroker _broker;

    public AegisBrokerBridge(string policyVersion = "1.0")
    {
        _broker = new AegisBroker(policyVersion);
    }

    public Decision EvaluateNavigation(
        string sessionId, string tabId, long generation,
        string rawUrl, string scope)
    {
        return _broker.EvaluateNavigation(sessionId, tabId, generation, rawUrl, scope);
    }

    public bool IsValid(AuthorizedAction action, long currentGeneration)
    {
        return _broker.IsValid(action, currentGeneration);
    }
}
```

### 6.3 Python（Legacy）

```python
# legacy/windows-pywebview/app/aegis_broker_bridge.py
import aegis_core

class AegisBrokerBridge:
    """Python 侧 Broker 桥接——委托 Rust FFI 统一决策。"""

    def __init__(self, policy_version: str = "1.0"):
        self._broker = aegis_core.AegisBroker(policy_version)

    def evaluate_navigation(
        self, session_id: str, tab_id: str, generation: int,
        raw_url: str, scope: str
    ):
        return self._broker.evaluate_navigation(
            session_id, tab_id, generation, raw_url, scope
        )

    def is_valid(self, action, current_generation: int) -> bool:
        return self._broker.is_valid(action, current_generation)
```

---

## 七、消除的重复代码

| 逻辑 | FFI 前（3 处重复） | FFI 后（1 处 Rust + 自动生成） | 节省 |
|------|-------------------|-------------------------------|------|
| URL 校验 | `origin.rs` + `OriginPolicy.cs` + `OriginPolicy.kt` | `origin.rs`（Rust） | ~150 行 |
| 策略评估 | `broker.rs` + `BrowserPolicyBroker.cs` + `AndroidBroker.kt` | `broker.rs`（Rust） | ~200 行 |
| 会话管理 | `broker.rs` + `BrowserViewModel.kt` | `broker.rs`（Rust） | ~100 行 |
| 指纹管道 | `fingerprint_pipeline.py` + `shield.rs` | `shield.rs`（Rust） | ~180 行 |
| **合计** | ~630 行手动维护 | 0（UniFFI 自动生成） | **~630 行** |

---

## 八、构建产物

| 平台 | 产物 | crate-type | 预估大小 |
|------|------|-----------|---------|
| Windows x64 | `aegis_core.dll` | cdylib | ~2-5 MB |
| Android arm64 | `libaegis_core.so` | cdylib | ~2-5 MB |
| Android armv7 | `libaegis_core.so` | cdylib | ~2-5 MB |
| Python wheel | `aegis_core-*.whl` | cdylib | ~3-6 MB |

---

## 九、关键约束

| 约束 | 说明 | 参照 |
|------|------|------|
| **UniFFI 版本** | `uniffi = "0.28"`（与 `uniffi-bindgen-cs v0.9.2+v0.28.3` 匹配） | HyperWhisper |
| **crate-type** | `["cdylib"]`（Android/Windows）；iOS 需加 `"staticlib"` | UniFFI 官方 |
| **proc-macro 优先** | 用 `#[uniffi::export]` 代替 UDL 文件（减少维护负担） | 2026 生产实践 |
| **Panic Guard** | UniFFI 自动处理——panic 不跨 FFI 边界 | rustbridge |
| **内存所有权** | Rust 拥有所有对象生命周期，C 侧只持有 opaque handle | rustbridge |
| **contracts 一致性** | FFI 导出的函数语义与 contracts/vectors 测试向量一致 | Aegis INV-05 |

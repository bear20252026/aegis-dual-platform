# Aegis FFI 架构设计：Rust cdylib 跨平台统一

> 参照：rustbridge / HyperWhisper / UniFFI / PyO3 / cbindgen
> 设计时间：2026-08-22

---

## 一、行业规范与设计语言

### 1.1 核心术语

| 术语 | 定义 | 来源 |
|------|------|------|
| **cdylib** | Rust 编译产物，生成动态链接库（.dll/.so/.dylib），供 C ABI 调用 | Rust 官方 |
| **C ABI** | C 语言应用程序二进制接口——所有语言的 FFI 最低公分母 | 行业标准 |
| **FFI** | Foreign Function Interface——跨语言函数调用接口 | 行业标准 |
| **Opaque Handle** | 不透明指针——Rust 类型在 C 侧表现为 `void*`，生命周期由 Rust 管理 | rustbridge |
| **JSON Transport** | 复杂数据通过 JSON 字符串跨 FFI 边界，避免手动序列化 | rustbridge |
| **Panic Guard** | `catch_unwind` 包装——Rust panic 不会跨 FFI 边界传播 | rustbridge |
| **UniFFI** | Mozilla 的 Rust→Kotlin/Swift/Python 绑定生成器 | Mozilla/HyperWhisper |
| **PyO3** | Rust→Python 绑定库（成熟，★12k+） | PyO3 |
| **cbindgen** | Rust→C 头文件生成器（用于 C# P/Invoke） | Mozilla |

### 1.2 行业架构模式

#### 模式 A：C ABI 直连（rustbridge 模式）

```
┌─────────────────────────────────────────┐
│  Host Language (C#/Kotlin/Python)       │
│  ┌─────────────────────────────────┐    │
│  │ Language Bindings (手写/生成)    │    │
│  │ - C#: P/Invoke + Marshal        │    │
│  │ - Kotlin: JNI / JNA             │    │
│  │ - Python: ctypes / cffi         │    │
│  └──────────┬──────────────────────┘    │
│             │ C ABI (extern "C")        │
├─────────────┼───────────────────────────┤
│             ▼                           │
│  ┌─────────────────────────────────┐    │
│  │ FFI Boundary (C Exports)        │    │
│  │ - aegis_broker_create()         │    │
│  │ - aegis_broker_evaluate()       │    │
│  │ - aegis_broker_destroy()        │    │
│  │ - Panic Guard (catch_unwind)    │    │
│  └──────────┬──────────────────────┘    │
│             │                           │
├─────────────┼───────────────────────────┤
│             ▼                           │
│  ┌─────────────────────────────────┐    │
│  │ Rust Core (policy-core)         │    │
│  │ - broker / decision / executor  │    │
│  │ - origin / policy / matcher     │    │
│  │ - shield / letterbox / ...      │    │
│  └─────────────────────────────────┘    │
└─────────────────────────────────────────┘
```

#### 模式 B：UniFFI 自动生成（HyperWhisper 模式）

```
┌─────────────────────────────────────────┐
│  Rust Core (#[uniffi::export])          │
│  ┌─────────────────────────────────┐    │
│  │ hw-core                         │    │
│  │  ├── broker                     │    │
│  │  ├── decision                   │    │
│  │  └── origin                     │    │
│  └──────────┬──────────────────────┘    │
│             │ UniFFI IDL                │
├─────────────┼───────────────────────────┤
│             ▼                           │
│  ┌─────────────────────────────────┐    │
│  │ uniffi-bindgen                  │    │
│  │ 自动生成：                       │    │
│  │  ├── aegis_core.swift (macOS)   │    │
│  │  ├── aegis_core.cs (Windows)    │    │
│  │  ├── aegis_core.kt (Android)    │    │
│  │  └── aegis_core.py (Python)     │    │
│  └─────────────────────────────────┘    │
└─────────────────────────────────────────┘
```

#### 模式 C：PyO3 直连（Python 专用）

```
┌─────────────────────────────────────────┐
│  Python (import aegis_core)             │
│  ┌─────────────────────────────────┐    │
│  │ PyO3 自动生成 Python 模块       │    │
│  │ - #[pyclass] → Python class     │    │
│  │ - #[pymethods] → Python methods │    │
│  └──────────┬──────────────────────┘    │
│             │ PyO3 FFI                  │
├─────────────┼───────────────────────────┤
│             ▼                           │
│  ┌─────────────────────────────────┐    │
│  │ Rust Core                       │    │
│  └─────────────────────────────────┘    │
└─────────────────────────────────────────┘
```

---

## 二、Aegis 适用方案分析

### 2.1 现状：三语言重复实现

| 安全逻辑 | Rust (policy-core) | C# (windows/src) | Kotlin (android) | Python (legacy) |
|----------|-------------------|------------------|------------------|-----------------|
| URL 校验 | `origin.rs` | `OriginPolicy.cs` | `OriginPolicy.kt` | `security.py:safe_url` |
| 策略评估 | `policy.rs` + `broker.rs` | `BrowserPolicyBroker.cs` | `AndroidBroker.kt` | — |
| 会话管理 | `broker.rs` + `session_state.rs` | — | `BrowserViewModel.kt` | `api_bridge.py` |
| **重复行数** | ~800 行 | ~200 行 | ~300 行 | ~150 行 |

**总重复**：~650 行跨平台重写（非 Rust 侧）

### 2.2 方案对比

| 方案 | 优势 | 劣势 | 适用性 |
|------|------|------|--------|
| **UniFFI** | 自动生成 Kotlin/Swift/Python 绑定；Mozilla 维护 | C# 支持依赖社区（uniffi-bindgen-cs）；版本锁定 | ★★★ 首选 |
| **PyO3** | Python 绑定最成熟（★12k） | 仅 Python；C#/Kotlin 需其他方案 | ★★☆ Python 专用 |
| **cbindgen + P/Invoke** | C# 原生支持；成熟 | Kotlin 需 JNI；Python 需 ctypes | ★★☆ C# 优先 |
| **rustbridge** | 全语言支持；JSON 传输 | 较新（★少）；引入运行时依赖 | ★★☆ 参考 |
| **C ABI 直连** | 零依赖；最大控制 | 手动管理内存/生命周期；样板代码多 | ★☆☆ 备选 |

### 2.3 推荐方案：UniFFI（主） + PyO3（Python 备选）

**理由**：
1. UniFFI 由 Mozilla 维护，HyperWhisper 已验证 C#/Kotlin/Swift 全平台
2. `#[uniffi::export]` 宏自动处理 FFI 边界的内存管理/类型转换
3. 绑定代码自动生成——Rust 改一处，三语言绑定同步更新
4. Python 可用 UniFFI 的 Python 绑定或 PyO3（更成熟）

---

## 三、Aegis FFI 架构设计

### 3.1 目标架构

```
┌─────────────────────────────────────────────────────┐
│                    Rust Core (cdylib)                │
│  ┌─────────────────────────────────────────────┐    │
│  │ aegis-core (#[uniffi::export])              │    │
│  │  ├── broker: evaluate_navigation()          │    │
│  │  ├── decision: Allow/Deny/RequireConfirm    │    │
│  │  ├── origin: try_parse_external()           │    │
│  │  ├── policy: evaluate()                     │    │
│  │  ├── shield: inject_script()                │    │
│  │  └── util: hex_digit/extract_host/...       │    │
│  └─────────────────────────────────────────────┘    │
│                                                     │
│  Cargo.toml:                                        │
│    [lib]                                            │
│    crate-type = ["cdylib"]                          │
│                                                     │
│    [dependencies]                                   │
│    uniffi = "0.28"                                  │
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

### 3.2 FFI 接口设计

```rust
// aegis-core/src/lib.rs

#[derive(uniffi::Enum)]
pub enum Decision {
    Allow { action: AuthorizedAction },
    Deny { reason: DenyReason },
    RequireConfirmation { request: ApprovalRequest },
}

#[derive(uniffi::Record)]
pub struct AuthorizedAction {
    pub session_id: String,
    pub tab_id: String,
    pub origin: String,
    pub method: String,
    pub scope: String,
    pub policy_version: String,
    pub explanation: String,
}

#[derive(uniffi::Record)]
pub struct DenyReason {
    pub code: String,
    pub detail: String,
    pub explanation: String,
}

#[derive(uniffi::Object)]
pub struct AegisBroker {
    policy_version: String,
}

#[uniffi::export]
impl AegisBroker {
    #[uniffi::constructor]
    pub fn new(policy_version: String) -> Self {
        Self { policy_version }
    }

    pub fn evaluate_navigation(
        &self,
        session_id: String,
        tab_id: String,
        raw_url: String,
        scope: String,
    ) -> Decision {
        // 委托 Rust core 的 broker 逻辑
        crate::broker::evaluate_navigation(
            &self.policy_version,
            &session_id,
            &tab_id,
            &raw_url,
            &scope,
        )
    }

    pub fn is_valid(&self, action: &AuthorizedAction, current_generation: i64) -> bool {
        crate::broker::is_valid(action, current_generation, &self.policy_version)
    }
}

// 指纹防护管道（单函数导出）
#[uniffi::export]
pub fn build_fingerprint_pipeline(session_seed: String) -> String {
    crate::fingerprint_pipeline::build_fingerprint_pipeline_js(&session_seed)
}

// URL 校验（单函数导出）
#[uniffi::export]
pub fn try_parse_external(raw_url: String) -> Option<(String, String)> {
    crate::origin::try_parse_external(&raw_url)
}

uniffi::setup_scaffolding!();
```

### 3.3 各平台集成方式

#### Kotlin（Android）

```kotlin
// 自动生成：aegis_core.kt
// 使用：
import aegis_core.AegisBroker

val broker = AegisBroker("1.0")
val decision = broker.evaluateNavigation(
    sessionId = "s1",
    tabId = "t1",
    rawUrl = "https://example.com",
    scope = "navigate"
)
when (decision) {
    is Decision.Allow -> { /* 允许导航 */ }
    is Decision.Deny -> { /* 拒绝，显示 reason.explanation */ }
    is Decision.RequireConfirmation -> { /* 弹窗确认 */ }
}
```

#### C#（Windows）

```csharp
// 自动生成：aegis_core.cs
// 使用：
using AegisCore;

var broker = new AegisBroker("1.0");
var decision = broker.EvaluateNavigation(
    sessionId: "s1",
    tabId: "t1",
    rawUrl: "https://example.com",
    scope: "navigate"
);
switch (decision)
{
    case Decision.Allow a: /* 允许 */ break;
    case Decision.Deny d: /* 拒绝 */ break;
    case Decision.RequireConfirmation r: /* 确认 */ break;
}
```

#### Python（Legacy Windows）

```python
# 自动生成：aegis_core.py
# 使用：
import aegis_core

broker = aegis_core.AegisBroker("1.0")
decision = broker.evaluate_navigation(
    session_id="s1",
    tab_id="t1",
    raw_url="https://example.com",
    scope="navigate"
)
if decision.is_allow():
    # 允许导航
    pass
elif decision.is_deny():
    # 拒绝
    print(decision.reason.explanation)
```

### 3.4 构建产物

| 平台 | 产物 | crate-type | 大小预估 |
|------|------|-----------|---------|
| Windows | `aegis_core.dll` | cdylib | ~2-5 MB |
| Android | `libaegis_core.so` | cdylib | ~2-5 MB |
| macOS | `libaegis_core.dylib` | cdylib | ~2-5 MB |
| Python wheel | `aegis_core-*.whl` | cdylib | ~3-6 MB |

### 3.5 消除的重复代码

| 逻辑 | 当前重复 | FFI 后 | 节省 |
|------|---------|--------|------|
| URL 校验 | 3 处（Rust/C#/Kotlin） | 1 处（Rust） | ~150 行 |
| 策略评估 | 3 处（Rust/C#/Kotlin） | 1 处（Rust） | ~200 行 |
| 会话管理 | 2 处（Rust/Kotlin） | 1 处（Rust） | ~100 行 |
| 指纹管道 | 2 处（Rust/Python） | 1 处（Rust） | ~180 行 |
| **合计** | ~650 行 | 0（自动生成） | **~630 行** |

---

## 四、实施路径

### Phase 1：UniFFI 集成（1 周）

| 步骤 | 内容 | 产出 |
|------|------|------|
| 1.1 | Cargo.toml 添加 `uniffi = "0.28"` + `crate-type = ["cdylib"]` | 依赖配置 |
| 1.2 | `#[uniffi::export]` 标注 `AegisBroker` + 核心函数 | FFI 接口 |
| 1.3 | `uniffi::setup_scaffolding!()` | scaffolding |
| 1.4 | 本地 `cargo build --release` 生成 .dll/.so | 构建产物 |

### Phase 2：绑定生成（3 天）

| 步骤 | 内容 | 产出 |
|------|------|------|
| 2.1 | `uniffi-bindgen generate --language kotlin` | `aegis_core.kt` |
| 2.2 | `uniffi-bindgen-cs --library aegis_core.dll` | `aegis_core.cs` |
| 2.3 | `uniffi-bindgen generate --language python` | `aegis_core.py` |
| 2.4 | CI 集成绑定生成 + 一致性验证 | workflow |

### Phase 3：平台集成（1 周）

| 步骤 | 内容 | 产出 |
|------|------|------|
| 3.1 | Android: 替换 `AndroidBroker.kt` → `aegis_core.AegisBroker` | Kotlin 集成 |
| 3.2 | Windows: 替换 `BrowserPolicyBroker.cs` → `aegis_core.AegisBroker` | C# 集成 |
| 3.3 | Python: 替换 `security.py:safe_url` → `aegis_core.try_parse_external` | Python 集成 |
| 3.4 | 删除已替换的重复代码 | 代码清理 |

### Phase 4：验证（3 天）

| 步骤 | 内容 | 产出 |
|------|------|------|
| 4.1 | contracts/vectors 跨语言一致性验证 | 测试通过 |
| 4.2 | CI 全绿（6 个 workflow） | 门禁通过 |
| 4.3 | 编译安装 + 真机验证 | 功能验证 |

---

## 五、关键约束

| 约束 | 说明 | 参照 |
|------|------|------|
| **UniFFI 版本锁定** | uniffi = "0.28"（与 uniffi-bindgen-cs v0.9.2 匹配） | HyperWhisper |
| **Panic Guard** | 所有 FFI 函数内部 catch_unwind，panic 不跨边界 | rustbridge |
| **内存所有权** | Rust 拥有所有对象生命周期，C 侧只持有 opaque handle | rustbridge |
| **JSON 传输** | 复杂类型（Decision/AuthorizedAction）通过 UniFFI Record 自动序列化 | UniFFI |
| **contracts 一致性** | FFI 导出的函数语义与 contracts/vectors 测试向量一致 | Aegis INV-05 |
| **零运行时依赖** | cdylib 不引入 Tokio/async（同步 FFI，简单可靠） | Aegis 架构 |

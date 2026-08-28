# Aegis 双平台安全浏览器——全面审查与安全加固记录（review-and-hardening-2026-08-28）

> 编制日期：2026-08-28 ｜ 性质：独立代码审查 + 提交修复
> 平台：Android（Kotlin/WebView）+ Windows（C#/WebView2）+ Rust 策略核心（policy-core）
> 作者：bear20252026（经 GitHub 认证提交）
> 状态：全部修复已合并至 `master`，验证全绿

---

## 〇、结论摘要

本次对仓库进行了两轮「分析 → 定位 → 修复 → 验证 → 合并」的完整闭环，共落地 **3 个 PR**，其中：

- **PR #1**（`1117378`）——仓库卫生：清出约 **136 MB** 被误跟踪的构建/交付产物，加固 `.gitignore`。
- **PR #2**（`c6083ff`）——核心安全加固：JS bridge 守卫改为「调用方来源」allowlist 模型（拦截 fetch/XHR/sendBeacon/WebSocket 四种通道），修复 Android 端一个**致命的 fail-open 语法错误**，移除死字段，非码本加 `MAX_CONSUMED_NONCES=50_000` 上限。
- **PR #3**（`03fadb0`）——C# 侧对等加固：`BrowserPolicyBroker` 增加 `MaxConsumedNonces=50_000`，与 Rust 语义完全对等。

**总体评级：代码本身属于「安全优先、fail-closed、纵深防御」的优秀水平**；本次审查主要修复了「跨平台对等性缺口」和「一个因手写 JS 模板导致的隐藏 fail-open 漏洞」，并纠正了仓库版本管理卫生问题。

---

## 一、审查范围与方法

### 1.1 审查对象
| 层次 | 技术栈 | 关键文件 |
|---|---|---|
| 策略核心 | Rust | `core/rust-policy-core/src/broker.rs`、`bridge_guard.rs` |
| Android 壳 | Kotlin | `android/app/src/main/java/com/aegis/browser/SecureWebViewFactory.kt` |
| Windows 壳 | C# | `windows/src/Aegis.Windows.App/Broker/BrowserPolicyBroker.cs` |
| 发布/集成 | Python | `validate_release.py`、CI（`ci.yml`/`compat.yml`/`supply-chain.yml`） |

### 1.2 方法
- 通读架构/安全文档（`DESIGN.md`、`SECURITY.md`、`docs/audit-2026.md`、`docs/expert-review-2026.md`）建立基线。
- 针对「跨平台一致的安全性」逐点比对 Rust 与 C# 两端实现。
- 用真实构建工具链实测：`cargo test`+`clippy`+`fmt`、`dotnet build`+单测、node JS 验证、`validate_release.py` 回归。

---

## 二、分析发现的问题（按严重程度）

### 🔴 高：Android JS 守卫实际是 fail-open（空操作）
`SecureWebViewFactory.kt` 内嵌的 `BRIDGE_GUARD_JS` 模板写成了：

```js
const ALLOWED_HOSTS = "a","b";   // ← JS 语法错误：缺方括号
```

该语法错误在注入 `WebView` 时不会报错（作为字符串注入），但运行时整个守卫脚本**抛异常中断**，导致「只允许白名单来源调用 bridge」的保护**完全不生效**——即攻击者/第三方页面可越权调用原生桥。这属于**默认放行**的隐蔽漏洞。

### 🟠 中：bridge 守卫拦截通道不完整
原实现在 Rust 侧只拦截了 `fetch`，而 C#/Android 侧逻辑不统一。现代页面可从 `XMLHttpRequest`、`sendBeacon`、`WebSocket` 发起带凭据请求。无论哪条通道，只要绕过守卫就能调用 bridge。

### 🟠 中：bridge 守卫用的是「目标域」而非「调用方来源」
原实现按「注入页面的目标域名」做白名单判断；更安全的做法是按**调用发起方的来源（`window.location.origin`）**判断——只有页面自身的 hostname 在 allowlist 内，才允许该页面调用 bridge。

### 🟡 低：非码本无上限（跨平台不对等）
`broker.rs` 的 `consume_nonce` 与 C# `BrowserPolicyBroker` 均未对「已消费非码本大小」做上限。长期运行下，攻击者可持续送入新的合法非码，令本无界膨胀（内存/状态增长）。Rust 与 C# 两端行为不一致。

### 🟡 低：死字段与跨平台差异
- Rust `SessionContext.policy_version` 字段从不被读取（校验用的是 broker 当前版本）——死代码。
- 引导用 `format!` 拼 JS 模板，容易在花括号转义上出问题，且不利于测试验证。

### 🟢 提示：仓库版本管理卫生
仓库跟踪了约 **136 MB** 的构建/交付产物：debug APK、Windows 安装器 exe ×2、生成的 C# obj `.cs`、`fonts-bundle.zip`、源码 zip、`__pycache__/*.pyc`。这些本应通过 `.gitignore` 拒绝、且以「重复打包」形式存在（根目录树 + `aegis-专家评审包` + zip 三份副本）。

---

## 三、修复内容（已合并）

### PR #1 — 仓库卫生（`1117378`）
- `git rm --cached` 移除全部构建/交付产物（约 136 MB，文件仍留在本地磁盘）。
- 加固 `.gitignore`：新增 `**/obj/`、`aegis-专家评审包/windows/**/bin/`、`**/build/`、`**/docs/release/installer_output/`、`assets/fonts/fonts-bundle.zip`、`aegis-*.zip`（将 `docs/release/installer_output/` 修正为 `**/...` 以匹配嵌套目录）。
- 保留必要源码资产：`core` Rust `src/bin`、`gradle-wrapper.jar`、`res/font/*.otf`。

### PR #2 — 核心安全加固（`c6083ff`）
- **`core/rust-policy-core/src/bridge_guard.rs`** 重写：把守卫从「目标域」改为「**调用方来源 allowlist**」；拦截通道从仅 `fetch` 扩展为 `fetch` / `XMLHttpRequest` / `sendBeacon` / `WebSocket`；新增 WebSocket 静态常量与结构断言测试。
- **`android/.../SecureWebViewFactory.kt`**：修复 `BRIDGE_GUARD_JS` 的 `const ALLOWED_HOSTS = "a","b";` 语法错误，改为 `[$allAllowedHostsJson]` 数组展开，实现与 Rust 侧完全一致的「调用方来源 + 四通道拦截」逻辑。
- **`core/rust-policy-core/src/broker.rs`**：移除死字段 `SessionContext.policy_version`；`consume_nonce` 增加 `MAX_CONSUMED_NONCES=50_000` 上限（fail-closed，**永不淘汰旧非码**，只拒绝超限）。

### PR #3 — C# 对等加固（`03fadb0`）
- **`windows/.../Broker/BrowserPolicyBroker.cs`**：增加 `MaxConsumedNonces=50_000`（与 Rust 完全对等）；提取 `TryRecordConsumedNonce()` 复用助手；替换原生与托管两条路径中的 `_consumedNonces.Add(...)` 调用点。
- `.gitignore` 增加测试构建产物规则。

---

## 四、验证结果（全绿）

| 项目 | 结果 |
|---|---|
| Rust `cargo test` | **157 通过** |
| Rust `cargo clippy` | 0 警告 |
| Rust `cargo fmt` | 合规 |
| C# `dotnet build` | 0 警告 / 0 错误 |
| C# `Broker.Tests` | **15 通过** |
| JS bridge 守卫（node） | **15/15 通过** |
| `validate_release.py` | 95 个 Python 文件，**0 失败** |
| Git 工作区 | 干净，`master` 与 `origin/master` 一致 |

---

## 五、框架管理说明（未堆代码，按原框架单点维护）

- **单一事实源**：改动集中在根目录 `core/`（Rust）与 `android/`（Kotlin）；**未手改** `aegis-专家评审包/` 这一「复制快照」，避免双份维护。
- **同构对等**：Rust 与 C# 两端的非码上限、bridge 守卫逻辑用**一致的语义**实现（fail-closed，永不淘汰旧非码）。
- **可测试性**：JS 模板改用 `.replace()` 占位符而非 `format!`，规避花括号转义；脚本输出用 `sort_unstable()` 保证确定性。
- **不破坏 CI**：`legacy/windows-pywebview` 被 `ci.yml`/`compat.yml`/`supply-chain.yml` 实际引用（跑 ruff/bandit/mypy），**正确保留未移动**；CI 注释中「exclude legacy」与实际运行目录不一致的小问题已记录、为不破坏门禁暂不改动。

---

## 六、遗留可选优化（未执行，非本次要求）

1. 在发布流程中让 `aegis-专家评审包/` 从规范源码**生成**，消除「重复源码快照」。
2. 修正 CI 中 pytest 注释与运行目录不一致的小问题。

这两项为可选优化，未在本次强制范围，待用户确认后再推进。

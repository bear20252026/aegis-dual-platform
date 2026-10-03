# Aegis 双端安全浏览器

Aegis 是一款**双平台隐私安全浏览器**——以"边界驱动架构"替代传统"补丁式加固"：
所有高危副作用（导航/下载/命令）必经**唯一能力代理（Capability Broker）**裁决，
裁决逻辑收敛在**无 I/O 的 Rust 策略核心**（单一裁决源），跨端行为由**冻结契约
（contracts）**驱动并以跨语言向量逐条锁定。

| 端 | 技术栈 | 状态 |
|---|---|---|
| Windows | C#/.NET 10 + WPF + 原生 WebView2 | **唯一正典栈与唯一发布制品**（Inno Setup 安装包 + SBOM + SLSA attestation；ADR-009） |
| Android | Kotlin + Jetpack Compose + System WebView | 直装 APK（`com.aegis.browser`） |
| 策略核心 | Rust（FFI/C ABI + UniFFI） | 无 I/O 纯函数裁决——canonicalization / Ed25519 阈值验证 / 指纹防护管线 |

> 许可证：MIT（[LICENSE](LICENSE)）｜ 漏洞报告：[SECURITY.md](SECURITY.md)

## 核心安全能力

- **导航裁决链**：每次导航经 Broker 决策（fail-closed）。**注意分端差异**——
  Rust 核心的 FFI 入口 `evaluate_navigation` 内不含策略/能力/黑名单层（代码自述
  H-7：`policy.evaluate / capability.validate 未接入 FFI 通路`），且 Windows 发布物
  运行时从不置位原生门禁环境变量、Android 发布 APK 把确认开关关闭后由客户端
  **自行兑换**一次性 nonce，故"高危目标触发用户确认流"目前两端均未生效
  （详见 [第六轮台账](docs/audit/full-audit-2026-10-03-round6.md) 第二节）
- **指纹防护**：Canvas/WebGL/AudioBuffer/字体/计时器/屏幕多维欺骗，噪声按
  **per-site 种子**隔离（跨站不可关联），注入脚本经三端守卫单源（bridge_guard）对账
- **HTTPS-only 升级** + **DNT** + **追踪参数剥离**
- **威胁黑名单**（订阅制刷新 + 导航门禁）——**仅 Windows 端实现**；Android 全树
  无任何黑名单代码，其导航拒绝条件只有"URL 是否良构"（第六轮 R6 登记，见下方
  「分端裁决现状」）
- **KillSwitch**：进程级紧急终止——触发后全部导航/下载/审批链即刻冻结
- **无痕窗口**：独立 WebView 环境 + 临时目录，favicon/缓存/历史按持久化语义分面隔离
- **下载防护**：危险扩展多级判定（含 URL 编码/路径段混淆形态）+ 二次确认
- **Agent/MCP 复开面**：action-catalog 单源 + 红队 fixtures——提示注入/重放/预算
  超限逐项测试（deny by default）

> **Windows 终局（ADR-009，M1-M4 全部落地）**：全功能迁移完成（parity 清单 100%
> 代码项勾验：[feature-parity-checklist](docs/product/feature-parity-checklist.md)）；
> `legacy/windows-pywebview/` 为**只读冻结归档**——仅 P0 安全缺陷经安全通道评估，
> 功能 PR 一律拒绝。

## 架构

```
contracts/  唯一安全协议事实来源（schemas/vectors/codegen——六类对象冻结；
            bridge_guard.template.js 为三端守卫 JS 单一事实源——ADR-007）
core/       Rust 纯策略核心（canonicalization + Ed25519 阈值验证——无 I/O）
windows/    C#/.NET 10 + 原生 WebView2（App/Chrome/WebView/Broker——能力代理）
android/    Kotlin/Compose（app/broker/webview-adapter/contracts——分层单源）
agent/      Agent/MCP 逐项复开（action-catalog——红队 fixtures——测试优先）
release/    发布链独立验证产品（逐工件闭合——fail-closed）
docs/       ADR/threat-model/runbooks/product/audit（蓝图目标树+全仓审计台账）
.github/    CI 分层门禁（15 个 workflow——WB-214 曾对齐为 13，其后新增
            gradle-dependency-graph / gradle-dependency-insight 两个而计数静默漂移
            （第六轮 R6 记为"闭环即回归"实证）：
            ci / contracts / core-rust / android-quality / supply-chain /
            agent-redteam / native-policy-artifacts / compat /
            legacy-python-guard / release 编排 + release-{windows,android,core}
            三平台链——无「windows」这一独立 workflow）
```

**三个信任域**（ADR-002/003）：远程网页域（无 native bridge）/本地 chrome UI 域
（虚拟主机白名单 origin）/Capability broker 域（唯一副作用点——Default Deny）。

## 构建

<!-- WB-197（2026-10-02 审计）：与 CLAUDE.md「关键命令」逐字对齐——Windows 补
     cd windows 前缀与 -r win-x64/-p:RestoreLockedMode=true，Android 四模块
     ktlint/detekt 补 :contracts: 枚举 -->
- **Windows**（正典栈，ADR-009）：`cd windows` 后 `dotnet build
  src/Aegis.Windows.App/Aegis.Windows.App.csproj -r win-x64 -p:RestoreLockedMode=true`
  （.NET 10.0.x——0 警告）；`dotnet test tests/Aegis.Windows.Core.Tests -r win-x64
  -p:RestoreLockedMode=true` / `dotnet test tests/Aegis.Windows.Broker.Tests -r
  win-x64 -p:RestoreLockedMode=true`
- **Rust 核心**（core/rust-policy-core）：`cargo test && cargo clippy --all-features
  --all-targets -- -D warnings && cargo fmt --check`（全绿 + 0 警告；SP-183 与 CI 统一口径）
- **Android**（与 CI 一致）：`cd android` 后四模块
  `./gradlew.bat :app:ktlintCheck :broker:ktlintCheck :webview-adapter:ktlintCheck :contracts:ktlintCheck`
  + `./gradlew.bat :app:detekt :broker:detekt :webview-adapter:detekt :contracts:detekt`
  + `./gradlew.bat :app:lintDebug` + `./gradlew.bat :broker:testDebugUnitTest
  :app:testDebugUnitTest :webview-adapter:testDebugUnitTest`（contracts 模块
  无独立测试源码——ktlint/detekt 四模块覆盖）
- **契约门禁**（仓库根）：`python validate_release.py` +
  `python contracts/codegen/verify_bridge_guard.py`（守卫 JS 单源——ADR-007）+
  `python scripts/verify_versions.py`
- **Web 资产回归**：`node --test "tests/ui-regression/*.test.mjs"` +
  `node shared/shell/snake.test.js`
- **Agent 红队**：`python -m pytest agent/tests -q`
- 完整命令与提交自查清单见 [CLAUDE.md](CLAUDE.md)

## 质量与审计状态

<!-- WB-198（2026-10-02 审计）：轮次数更正为四轮 → 本行由第六轮审计再次更正 -->
- **六轮全仓审计；前五轮"全量闭环"口径经第六轮复查为部分不实**：
  - 2026-09-07 轮（200 项，[台账](docs/audit/full-audit-2026-09-07-200-items.md)）
  - 2026-09-23 轮（1115 项，[台账](docs/audit/full-audit-2026-09-23-1000-items.md)）
    **1115/1115 全量闭环**——并经 V1 核验批对 RS/PY 两区 377 项逐项代码级复核，
    19 项虚闭环补落地、2 项如实登记（RS-149 uniffi 上游阻塞暂缓 / PY-021 接受风险）
  - 2026-09-26 轮全仓复扫（229 项新发现，
    [报告](docs/audit/full-audit-2026-09-26-229-items.md)）**229/229 全部闭环**
  - 2026-10-01 轮（241 项，
    [台账](docs/audit/full-audit-2026-10-01-241-items.md)——WB-198 链接补齐：
    本轮六区新鲜扫描，P1×4 / P2×23 / P3×214）。**该轮自身尾记为「251 项中 248 项
    闭环」**（AD-296/AD-289/AD-279 三项部分闭环，CHANGELOG 记 245），并非全量
  - 2026-10-02 轮（217 项，
    [台账](docs/audit/full-audit-2026-10-02-217-items.md)）
  - 2026-10-03 轮（第六轮，复查前五轮「闭环」声明 + 架构主轴证伪，
    [台账](docs/audit/full-audit-2026-10-03-round6.md)）：19 项闭环并附可复现验证，
    其中 4 项为前五轮的**虚闭环/修复即回归**（P43 / SP-209 / AD-309 / WB-214）
- 测试规模：cargo 450+ / dotnet 650+ / gradle JVM 280+ / pytest 230+ / node 80+ 用例，
  五门禁（validate_release / verify_versions / bridge_guard / contract_compatibility /
  cross_end_lists）常绿
  （SP-198，2026-10-01 审计补口径：pytest 230+ 为**合计口径**——`tests/python`
  发布链验证器 195+ 用例 + `agent/tests` 红队 30 用例；CHANGELOG 各版本条目中的
  "pytest 30" 为当批 agent 红队单列口径，两者不矛盾）
- 当前版本：见 [shared/version.properties](shared/version.properties) **单源**
  （WB-178，2026-10-02 审计：本文不再硬编码具体版本号——逐版漂移即失实；
  发布记录见 [CHANGELOG.md](CHANGELOG.md)，记账规则见文件头）

## 蓝图状态（蓝图文档已并入 docs/architecture-overview.md）

- 阶段 A（ADR 决策）→ G（Agent 复开）**全部完成** ✅；发布门禁 13 workflow 分层 ✅
  （SP-199，2026-10-01 审计如实口径：**常跑（push/PR 触发）7 个**——ci / contracts /
  core-rust / android-quality / supply-chain / agent-redteam / native-policy-artifacts；
  低频定时 2 个——compat（周一）/ legacy-python-guard（周六）；tag/编排触发 4 个——
  release 编排器 + release-{windows,android,core} 三平台链）
- 剩余（需真实设备/用户操作）：真机验证（[device-validation.md](docs/runbooks/device-validation.md)）｜
  正式发布（[release-checklist.md](docs/runbooks/release-checklist.md)——受保护环境 + 门禁全绿后 tag）

## 安全

见 [SECURITY.md](SECURITY.md)（三信任域边界/漏洞报告/危险 API 审查清单/依赖发布
安全——CI 工具链 hash 锁定、pip-audit/cargo-audit 门禁）。

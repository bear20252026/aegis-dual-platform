# Aegis 双端安全浏览器

Aegis 是一款**双平台隐私安全浏览器**——以"边界驱动架构"替代传统"补丁式加固"：
所有高危副作用（导航/下载/命令）必经**唯一能力代理（Capability Broker）**裁决，
裁决逻辑收敛在**无 I/O 的 Rust 策略核心**（**导航**裁决单源——能力评估层
`policy.evaluate` / `capability.validate` 尚未接入 FFI 通路（核心自述 H-7），
故「单一裁决源」不覆盖能力评估面），跨端行为由**冻结契约（contracts）**驱动并以
跨语言向量锁定（向量覆盖并不均齐：C# 侧只链 2 份、Kotlin 侧只消费
`url-origin-*`——第八轮 §5.2 实测）。

| 端 | 技术栈 | 状态 |
|---|---|---|
| Windows | C#/.NET 10 + WPF + 原生 WebView2 | **唯一正典栈与唯一发布制品**（Inno Setup 安装包 + SBOM + SLSA attestation；ADR-009） |
| Android | Kotlin + Jetpack Compose + System WebView | 直装 APK（`com.aegis.browser`） |
| 策略核心 | Rust（FFI/C ABI + UniFFI） | 无 I/O 纯函数裁决——canonicalization / Ed25519 阈值验证 / 指纹防护管线 |

> 许可证：MIT（[LICENSE](LICENSE)）｜ 漏洞报告：[SECURITY.md](SECURITY.md)

## 核心安全能力

- **导航裁决链**：每次导航经 Broker 决策（fail-closed）。**注意分端差异**——
  Rust 核心的 FFI 入口 `evaluate_navigation` 内不含策略/能力/黑名单层（代码自述
  H-7：`policy.evaluate / capability.validate 未接入 FFI 通路`）；Windows 发布物的
  原生门禁此前依赖永不置位的环境变量，第六轮已改由安装器写入的按用户注册表标记
  （`HKCU\Software\Aegis Browser\RequireNativePolicyCore`）驱动，故安装包内导航
  确实经 Rust 核心裁决（启动留痕见安全日志 `[adjudication]` 行）；Android 发布 APK
  由发布链置位 `-PrequireNavigationConfirmation=true`（该置位自第八轮 B3 起被静态锚
  钉住，删参数即红），故「高危目标触发用户确认流」在 **Android 生效**；Windows 出货
  构建**未启用**导航确认门，核心判「需显式确认」的目标自第八轮 B4 起改为用户可见
  拒绝并取消导航（不再是无反馈的静默 false）——**两端行为不同：Android 问一次，
  Windows 直接拒**。本机/内网 http 目标因此分端表现不一致，属待用户裁决的产品行为
  （第八轮台账 §七 1）
  （详见 [第六轮台账](docs/audit/full-audit-2026-10-03-round6.md) 第二节、
  [第八轮台账](docs/audit/full-audit-2026-10-04-round8.md) §三与§五）
- **指纹防护**：Canvas/WebGL/AudioBuffer/字体/计时器/屏幕多维欺骗，噪声按
  **per-site 种子**隔离（跨站不可关联）；文档创建前注入脚本的对账是**两端**而非三端——
  `bridge_guard.template.js` 单源覆盖 Rust（`include_str!`）与 Android（手抄 + 逐行比对），
  Windows C# 的注入面（`WebView2Hardening.cs:70`）**不在该单源对账范围内**（第八轮实测）
- **HTTPS-only 升级** + **DNT** + **追踪参数剥离**
- **威胁黑名单**（导航门禁）——**仅 Windows 端实现**；刷新实为**启动一次性**
  （`ThreatFeedCoordinator` 只在 `Start()` 内调一次，全仓无周期计时器——「订阅制刷新」
  的旧口径已撤）；Android 全树
  无任何黑名单代码，其导航拒绝条件只有"URL 是否良构"（第六轮 R6 登记，见下方
  「分端裁决现状」）
- **KillSwitch**（**仅 Windows**；Android 全树零实现，README 旧版未标端别）——触发后
  主窗口的导航/下载/审批链冻结；**已知缺口**：NTP 宿主桥（`importBookmarks` /
  `importHistory` / `restoreSession`）与前进/后退/重载等 6 个导航入口不查该开关
- **无痕窗口**（**仅 Windows**）：独立 WebView 环境 + 临时目录，favicon/缓存/历史按
  持久化语义分面隔离；Android 侧无对应实现（`android/README.md` 的 `clearPrivateData`
  条目已就地更正为「未落地」）
- **下载防护**：危险扩展多级判定（含 URL 编码/路径段混淆形态）+ 二次确认
- **Agent/MCP 复开面**：action-catalog 单源 + 红队 fixtures——提示注入/重放/预算
  超限逐项测试（deny by default）

> **Windows 终局（ADR-009，M1-M4 全部落地）**：全功能迁移完成（parity 清单代码项
> 勾验——第八轮 B8 复核后为 **除 1 项外全部勾验**：`NewBrowserVersionAvailable`
> Runtime 更新事件未实现，见 [feature-parity-checklist](docs/product/feature-parity-checklist.md)）；
> `legacy/windows-pywebview/` 为**只读冻结归档**——仅 P0 安全缺陷经安全通道评估，
> 功能 PR 一律拒绝。

## 架构

```
contracts/  唯一安全协议事实来源（schemas/vectors/codegen——六类对象冻结；
            bridge_guard.template.js 为守卫 JS 单源（Rust+Android 两端对账，C# 未纳入——ADR-007）
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

<!-- WB-198（2026-10-02 审计）：轮次数更正为四轮 → 本行由第六轮审计再次更正
     → 第八轮（2026-10-04）审计补记：第七/第八两轮台账此前未列入本清单，
     故此处「六轮」已失实（R8-DOC-15，同 WB-214「计数静默漂移」族） -->
- **八轮全仓审计；前五轮"全量闭环"口径经第六轮复查为部分不实**：
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
  - 2026-10-04 轮（第七轮，8 分区并行 + 逐条回读，
    [台账](docs/audit/full-audit-2026-10-04-round7.md)）：P1×8 全部落地（PR #77–#85），
    其中 4 项为前五轮的虚闭环/修复即回归
  - 2026-10-04 轮（第八轮，9 分区并行 + 第七轮闭环核验，
    [台账](docs/audit/full-audit-2026-10-04-round8.md)）：登记 P1×7（主代理逐条回读确证）
    + P2×11（已回读部分）；第七轮的 B8「本机与内网可打开」经复核为**部分闭环**——
    三端只 Windows 改了托管侧拒绝面，出货 Windows 因确认门未启用而**静默取消**、
    Android 因 http 强升 https 而**不可达**；另含依赖与工具链升级面全清单
    （OSV 实测在用版本无一命中 CVE）
- 测试规模：cargo 450+ / dotnet 650+ / gradle JVM 280+ / pytest 230+ / node 80+ 用例，
  五门禁（validate_release / verify_versions / bridge_guard / contract_compatibility /
  cross_end_lists）常绿——「常绿」限定为**本轮 CI 实测绿且各门禁确有失败能力**：
  B1 之前 pwsh 吞退出码曾使红灯长期呈绿，故「绿」本身不是结论，能红才是
  （文档计数与实树对账另有 `scripts/check_doc_claims.py`，workflow 脚本壳口径另有
  `scripts/check_workflow_shells.py`）
  （SP-198，2026-10-01 审计补口径：pytest 230+ 为**合计口径**——`tests/python`
  发布链验证器 195+ 用例 + `agent/tests` 红队 30 用例；CHANGELOG 各版本条目中的
  "pytest 30" 为当批 agent 红队单列口径，两者不矛盾）
- 当前版本：见 [shared/version.properties](shared/version.properties) **单源**
  （WB-178，2026-10-02 审计：本文不再硬编码具体版本号——逐版漂移即失实；
  发布记录见 [CHANGELOG.md](CHANGELOG.md)，记账规则见文件头）

## 蓝图状态（蓝图文档已并入 docs/architecture-overview.md）

- 阶段 A（ADR 决策）→ F **全部完成** ✅；**阶段 G（Agent 本地受控 IPC）只有设计文档
  与裁决/红队夹具，交付面（OS ACL / 进程身份核验 / IPC 传输 / 撤销）零实现**——
  `agent/broker.py` 自述不承担这些 OS 能力，`agent/local-ipc/*.md` 已就地标注现状；
  发布门禁 15 workflow 分层 ✅
  （SP-199，2026-10-01 审计如实口径：**常跑（push/PR 触发）7 个**——ci / contracts /
  core-rust / android-quality / supply-chain / agent-redteam / native-policy-artifacts；
  低频定时 2 个——compat（周一）/ legacy-python-guard（周六）；依赖面 2 个——
  gradle-dependency-graph（Dependency Graph 上传：周一 + push:android/** + dispatch）/
  gradle-dependency-insight（仅 dispatch）；tag/编排触发 4 个——release 编排器 +
  release-{windows,android,core} 三平台链。7+2+2+4=15，与
  `scripts/check_doc_claims.py` 的实树现算同源——WB-214 起这类「文档数 = 实树数」的
  陈述已三次漂移，现由门禁逐处对账）
- 剩余（需真实设备/用户操作）：真机验证（[device-validation.md](docs/runbooks/device-validation.md)）｜
  正式发布（[release-checklist.md](docs/runbooks/release-checklist.md)——受保护环境 + 门禁全绿后 tag）

## 安全

见 [SECURITY.md](SECURITY.md)（三信任域边界/漏洞报告/危险 API 审查清单/依赖发布
安全——CI 工具链 hash 锁定、pip-audit/cargo-audit 门禁）。

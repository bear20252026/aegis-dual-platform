# Aegis 架构与可维护性审计报告（2026-08-31）

> 与《代码审计 2026-08-31》（安全向）互补，本报告聚焦：架构分层、耦合、可读性、可扩展性。
> 方法：3 个专项并行审计 + 全部关键论断 grep/实测验证。
> 评分：**架构 6.5/10 · 耦合度 4/10（越低越好） · 可读性/一致性 7/10 → 综合 6.8/10**

---

## 一、值得肯定的结构性优点（经验证）

1. **三语言分层依赖方向零反向**（grep 验证）：Android `app → broker + webview-adapter` 单向、broker 零反向 import；Rust `broker → ffi → c_abi` 单向委托；Python `main_webview → app/` 单向（app/ 对 main_webview 仅注释级提及，无 import）。
2. **start.html 单源消费彻底**：两端均指向仓库级目录，无平行副本（ADR-007 落实到位）。
3. **Rust 零全局状态**：`static mut`/`lazy_static` 0 命中，状态全部结构体传递——三端标杆。
4. **Python 全局纪律好**：全仓 `global` 仅 4 处且为幂等标志。
5. **发布编排器模式**：release.yml → release-{windows,android,core}.yml 结构清晰。
6. **命名规范贯彻度近乎零违规**：三端命名、中文注释、TODO=0、裸 except=0。

---

## 二、按优先级排列的问题清单

### P0 — 结构性风险（尽快处理）

**A1【高】Android 存在 4 个不参与构建的死模块**
- 位置：`android/chrome-ui/`、`android/contracts/`（生成物部分）、`android/storage/`、`android/diagnostics/`
- 验证：`settings.gradle.kts:18-20` 仅 include `:app/:broker/:webview-adapter`；4 目录源码已入 git（BrowserScreen.kt/StorageService.kt/Diagnostics.kt 等），零引用。
- 影响：约 500 行死代码持续误导读者与审计；contracts 生成物死代码尤其危险（见 A2）。
- 修复：删除 chrome-ui/storage/diagnostics 三目录；contracts 处置见 A2。

**A2【高】契约机制在 Android 端断裂——生成物死代码 + 手写平行模型**
- 位置：`contracts/codegen/generate_kotlin.py` → `android/contracts/generated/`（6 文件，无模块消费）；实际用的是手写 `android/broker/AuthorizedAction.kt`（camelCase，与生成物 snake_case 字段平行双轨）；C# 端则真消费生成物。
- 影响：schema 变更时 Android「契约一致性」只靠注释维持——契约机制一端落实一端落空。
- 修复（二选一，推荐 ①）：① `:contracts` 纳入 settings.gradle.kts，AuthorizedAction 改继承/对齐生成物；② 删除 generate_kotlin.py + generated/，文档声明 Android 端契约手写同步 + CI diff 校验。

**A3【高】Android 双套 URL 校验语义漂移（展示层弱、决策层强）**
- 位置：`BrowserEngine.kt:27-39 normalizeExternal`（无 userinfo/控制字符/非法端口/长度校验）vs `OriginPolicy.kt:8-26`（全查）；消费点 `SecureWebViewFactory.kt:488` 走的是弱实现；Rust `origin.rs` 与 Python `security.py:40` 均为强校验——四处中 Android 展示层最弱。
- 影响：同一 URL 展示层与 Broker 决策层可得出不同判定（钓鱼地址栏风险）；契约漂移实锤。
- 修复：删除 `normalizeExternal` 独立实现，改薄封装 `OriginPolicy.tryParseExternal`；scheme 白名单字面量（BrowserEngine.kt:20）同步收敛到 OriginPolicy 常量；用 contracts `url-origin-*` 向量补 Kotlin 端口用例。

### P1 — 维护负担（一个月内）

**A4【高】`aegis-专家评审包/` 是已漂移的源码快照**
- 验证：131MB 快照入库，`diff` 证实 10+ 文件与主源码不一致（broker.rs/session_store.py/shell_toolbar.py 等），且缺 core/src/bin、缺 wallpapers。
- 影响：不可信的过期副本；每次同步 = 全量 diff 成本。
- 修复：从主树删除，改为 CI tag 触发 `build_review_package.py` 产 artifact（脚本已存在）。

**A5【中高】`main_webview.py`（767 行/27 函数）职责越界**
- 问题：启动编排 + WebView2 硬化 + **agent sitemap 匹配策略**（37-113 行纯策略逻辑寄生在壳里）+ 烟雾测试四合一。
- 修复：agent 策略段下沉 `app/agent_sitemap.py`；`_on_request`（116 行，DNT/威胁/拦截多职责）按处理器表拆分。

**A6【中】`SecureWebViewFactory` 单例静态持有 broker**
- 位置：`SecureWebViewFactory.kt:24`（object + `private val broker = AndroidBroker()`），同模式 object 共 6 个。
- 影响：测试隔离性差（AndroidBrokerTest 只能绕过单例直接 new）、多 Activity 无法隔离。
- 修复：broker 移至 `Application` 持有 + 构造注入；object 降级为纯函数容器。**注意与 H-4 修复的 release() 生命周期衔接**。

**A7【中】跨端数据清单无单源无校验（扩散系数实测）**
- 壁纸清单 4 处（asset_scheme.py:31 + start.html:543 + AegisHomeBridge.kt:39 + jpg 本体）——**扩散系数 4**；
- 搜索引擎 2 处（url_utils.py:32 + AegisHomeBridge.kt:30）——无一致性校验；
- FFI 方法 4 处绑定（c_abi/*.rs、bindings/*.py、NativePolicyCoreBridge.kt/.cs）。
- 修复：壁纸/引擎清单加 verify 脚本比对（最低成本）或纳入 contracts codegen；FFI 绑定纳入 codegen（generate_kotlin.py 先例）。

### P2 — 可读性债（随迭代偿还）

**A8【中】start.html 922 行：贪吃蛇（286 行）+ 导入向导（242 行）占 JS 87%**
- 修复：拆 `start.snake.js`、`start.import.js`、CSS 外置；两端 assets.srcDir 配置已天然支持多文件。注意三端消费路径回归（Windows START_URL/PyInstaller datas/gradle assets.srcDir）。

**A9【中】「session」一词三义**：Python 标签恢复快照 / Rust persona 授权上下文 / start.html restoreSession（指前者）。建术语表或 Rust 侧改名 broker_context。

**A10【中】JS 桥 API 双轨命名**：Python snake_case（set_search_engine）vs Android camelCase（setEngine），靠 start.html Host 适配层手工对齐，漏改无静态守卫。桥方法清单纳入 codegen。

**A11【中】审计溯源号体系只覆盖 Python**（约 40 处），Rust 2 处、Kotlin 0 处，且无编号定义文档（语义要反查 CHANGELOG）。补 `docs/audit-index.md`。

**A12【中】超长函数 Top 热点**：fingerprintShieldScript（168 行 JS 内嵌 Kotlin 字符串——移 assets 外置）、_on_request（116）、handleOnBackPressed（134）、validate_action（97）、consume_navigation（91）、handle_request（91）、config.load（87）。

**A13【中低】Rust 结构性重复**：13 个模块同构 `inject_script`（抽 `trait ScriptInjector` 聚合）；ffi 层 14 处 DenyReason 字面构造（抽构造器族）；adblock/util 与 origin 两套 host 提取语义分裂（统一走 try_parse_external）。

**A14【低】文档漂移**：README 称 8 门禁实际 12 workflow；android/app/README 与 DownloadPolicy 等描述需随实态回写；ADR-007 无 start.html 字样、桥契约无文档（建议 docs/bridge-contract.md）。

**A15【低】Windows 双栈无收敛计划**：Python 栈现役、C# 栈是第三套策略接入层（与 Android broker 高度同构），CI 同时伺候两栈。写 ADR 明确退役里程碑，避免永久双维护。

---

## 三、重构实施路线图

**阶段 1（1-2 天，零风险减法）**
1. 删 3 个死模块目录（A1）
2. 删评审包目录 + CI 产 artifact（A4）
3. README 门禁数回写（A14 部分）

**阶段 2（3-5 天，行为保持重构）**
4. A2：:contracts 进构建 or 删生成物（一次性决策）
5. A3：normalizeExternal → OriginPolicy 薄封装（每步跑 ktlint/detekt + contracts 向量测试）
6. A5：main_webview.py agent 策略下沉 + _on_request 处理器表化（selftest 全程护航）

**阶段 3（1-2 周，结构升级）**
7. A6：broker 依赖注入化
8. A7：清单单源 + verify 脚本
9. A12/A13：长函数拆分、ScriptInjector trait、DenyReason 构造器族

**阶段 4（随版本迭代）**
10. A8：start.html 拆分（需三端消费回归）
11. A9-A11：术语表、桥契约文档、审计号全端覆盖
12. A15：双栈退役 ADR

**总评**：架构骨架（分层方向、单源消费、发布编排、Rust 纯函数化）质量高于多数同类项目；主要债集中在「机制建了没接线」（contracts 死代码、清单无校验）与「快照入库必腐化」两类系统性疏忽，均为可控的机械性重构，无伤筋动骨项。

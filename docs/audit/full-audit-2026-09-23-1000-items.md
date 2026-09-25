# Aegis 全仓审计与 1000 项改进总清单（2026-09-23）

**范围**：aegis-dual-platform 全仓六区——Windows C# 正典栈（windows/）、Android（android/）、Rust 策略核心（core/rust-policy-core）、Python/CI/契约/发布链（scripts、validate_release、.github/workflows、contracts、release）、共享 Web 资产与文档（shared/shell、docs、根文档）、补充盲区（agent/、release/tools、tests/、dist、.gitignore、历史报告归置）。
**方式**：6 路并行审计代理逐文件核对（每项带 file:line 证据）→ 去重分级 → 分批执行 → 每批全量验证后提交。
**基线**：接续 docs/audit/full-audit-2026-09-07-200-items.md（该轮 200 项不再重复；本轮发现其中 3 项修复不完整：P76 hex 半面残留、P28 default_workspace 未转义、P34 JS 侧仍区分大小写——已并入 RS-036/RS-037/RS-010）。
**总量**：**1115 项**（CS 290 / AD 210 / RS 205 / PY 172 / WB 100 / SP 138，编号经脚本核对无缺口）+ 先导修复 1 项（matcher glob_subsumes，v2.2.0-beta.44 已提交）。

> 编号体系：CS=C# 正典栈，AD=Android，RS=Rust 策略核心，PY=Python/CI/契约/发布链，WB=Web 资产+文档，SP=补充盲区。
> 优先级：P1=必须（缺陷/安全/门禁失效），P2=应该（正确性/一致性/重要测试），P3=可以（打磨/补测/归置）。
> 每行格式：`ID | 优先级 | 类型 | 位置 | 问题 → 方案`。

---

## 第〇部分：P1 缺陷与安全修复汇总（89 项，跨六区）

### 0.1 Windows C#（CS-001..006）

| ID | 优先级 | 类型 | 位置 | 问题 → 方案 |
|---|---|---|---|---|
| CS-001 | P1 | 资源泄漏 | windows/.../Core/Tabs/TabManager.cs:23 | _tabClosed 事件从未 Invoke——每关一标签泄漏一个 WebView2 实例 → CloseTab 移除后触发事件+回归测试 |
| CS-002 | P1 | 崩溃 | windows/.../Core/UrlSafety.cs:80 | host=="0x" 时 Convert 抛 FormatException → 补 Length>2 守卫+用例 |
| CS-003 | P1 | 无痕落盘 | windows/.../Core/Favicons/FaviconService.cs:63 | InFlight 去重不区分无痕——无痕 favicon 可写盘 → 键加入 persistToDisk 维度 |
| CS-004 | P1 | 功能失效 | windows/.../Chrome/TabRuntime.cs:123 | 内存缓存命中时调用方丢返回值——二次访问站点图标不显示 → 命中同步回设 Tab.Icon |
| CS-005 | P1 | 竞态泄漏 | windows/.../Chrome/InPrivateWindow.xaml.cs:57 | _environmentLease ??= await 非原子——双开标签泄漏环境与临时目录 → SemaphoreSlim 串行化 |
| CS-006 | P1 | 指纹伪装失效 | windows/.../WebView/FingerprintShield.cs:108,120 | MAX_VIEWPORT_DIMS 返回 Float32Array（应 Int32Array）——类型检测即识破 → 两处改 Int32Array+断言 |

### 0.2 Android（AD-001..031）

| ID | 优先级 | 类型 | 位置 | 问题 → 方案 |
|---|---|---|---|---|
| AD-001 | P1 | 安全 | android/app/src/main/AndroidManifest.xml:16 | launchMode 未设——外链热启动叠加整个浏览器实例 → singleTask+回归 |
| AD-002 | P1 | 安全 | android/.../DownloadPolicy.kt:48 | 危险扩展判定漏查询参数（?file=x.exe 绕过）→ 补 query 参数值尾段判定 |
| AD-003 | P1 | 安全 | android/app/build.gradle.kts:107 | release isMinifyEnabled=false——R8 全关 → 恢复混淆+keep 规则回归后启用 |
| AD-004 | P1 | 隐私 | android/.../webviewadapter/AegisWebViewClient.kt:220 | 日志明文记完整 URL 含 query（6 处）→ 抽 RedactUrl 统一接入 |
| AD-005 | P1 | 密码学 | android/.../WebViewHardening.kt:166 | per-site 种子仍是自制 acc*31 混合（P25 未对齐 Android）→ Kotlin 侧 SHA-256 派生 |
| AD-006 | P1 | 生命周期 | android/.../MainActivity.kt:359 | onPause 不挂起 JS 定时器/媒体 → onPause pauseTimers+onResume 恢复 |
| AD-007 | P1 | 测试缺口 | webview-adapter/src/test（空） | 导航授权状态机 381 行零测试 → 新建 AegisWebViewClientTest |
| AD-008 | P1 | 测试缺口 | AegisWebViewClient.kt:88 | navigate() 合法 https 放行无测试 | 
| AD-009 | P1 | 测试缺口 | AegisWebViewClient.kt:198 | 顶层拒绝上抛链路无测试 |
| AD-010 | P1 | 测试缺口 | AegisWebViewClient.kt:70 | 主框架 http 阻断+升级分支无测试 |
| AD-011 | P1 | 测试缺口 | AegisWebViewClient.kt:63 | iframe http 不劫持顶层（P1-2 修复）无回归 |
| AD-012 | P1 | 测试缺口 | AegisWebViewClient.kt:239 | onRenderProcessGone 返回 true 无测试 |
| AD-013 | P1 | 测试缺口 | AegisWebViewClient.kt:359 | close() 销毁 Broker 会话无测试 |
| AD-014 | P1 | 测试缺口 | AegisWebViewClient.kt:225 | 大写 scheme 升级（T3 修复）无客户端级测试 |
| AD-015 | P1 | 测试缺口 | AegisWebViewClient.kt:97 | approvePendingNavigation 空边界无测试 |
| AD-016 | P1 | 测试缺口 | broker/.../AndroidBroker.kt:46 | registerSession 四类非法输入拒绝无测试 |
| AD-017 | P1 | 测试缺口 | AndroidBroker.kt:311 | nonce FIFO 逐出有界性无测试 |
| AD-018 | P1 | 测试缺口 | AndroidBroker.kt:297 | consumeNavigation 参数不匹配拒绝无测试 |
| AD-019 | P1 | 测试缺口 | AndroidBroker.kt:266 | policyVersion 不匹配拒绝无测试 |
| AD-020 | P1 | 测试缺口 | AndroidBroker.kt:30 | SESSION_TTL 滑动续期防退化不可测（时钟不可注入）→ 注入 Clock |
| AD-021 | P1 | 测试缺口 | app/.../BrowserEngine.kt:38 | normalizeExternal 零测试 |
| AD-022 | P1 | 测试缺口 | app/.../SecureWebViewFactory.kt:123 | navigatorFor 未注册返回 null 无测试 |
| AD-023 | P1 | 测试缺口 | app/.../WebViewHardening.kt:23 | newSessionSeed 熵源零测试 |
| AD-024 | P1 | 测试缺口 | app/.../DownloadPolicy.kt:60 | 大写/尾点净化（P2-5 修复）无回归 |
| AD-025 | P1 | 测试缺口 | app/.../DownloadPolicy.kt:6 | 23 个危险扩展全集无矩阵断言 |
| AD-026 | P1 | 测试缺口 | app/.../WebViewDownloadHandler.kt:105 | sanitizeFileName 零测试且 private → internal+测 |
| AD-027 | P1 | 测试缺口 | WebViewDownloadHandler.kt:77 | resolveDownloadFileName 三级优先零测试 |
| AD-028 | P1 | 测试缺口 | app/.../ReaderMode.kt:78 | parse 两段 JSON 解析零测试 |
| AD-029 | P1 | 测试缺口 | app/.../TranslateEntry.kt:26 | buildUrl 非 http 拒绝零测试 |
| AD-030 | P1 | 测试缺口 | app/.../WebViewVersionCheck.kt:46 | isOutdated 阈值边界零测试 |
| AD-031 | P1 | 测试缺口 | app/.../SearchEngines.kt:67 | normalizeInput DOMAIN 全链零测试 |

### 0.3 Rust 策略核心（RS-001..010）

| ID | 优先级 | 类型 | 位置 | 问题 → 方案 |
|---|---|---|---|---|
| RS-001 | P1 | 崩溃 | core/rust-policy-core/src/letterbox.rs:125-128 | window.innerWidth 覆盖未捕获原 getter——getter 自递归栈溢出 → 先取 descriptor 再 defineProperty |
| RS-002 | P1 | 隔离失效 | core/rust-policy-core/src/lib.rs:82 | fingerprint_pipeline 把 session_hex 当 domain 传 per_site——per-site 隔离自上线空转 → 增加 domain 参数透传 |
| RS-003 | P1 | 隔离失效 | core/rust-policy-core/src/protection_mode.rs:156 | 同 RS-002 参数错传 → 统一修正 |
| RS-004 | P1 | panic | core/rust-policy-core/src/action_policy.rs:153 | context_contains_token 多字节 UTF-8 续扫 panic → 按字符边界推进+回归 |
| RS-005 | P1 | UB | core/rust-policy-core/src/c_abi/mod.rs:33 | read_utf8 声明 64KB 可读窗口——小缓冲构造越界 slice UB → 分块扫描 NUL |
| RS-006 | P1 | 占位桩 | core/rust-policy-core/src/executor.rs:110-121 | parse() 恒返回 "default"——真实命令永远路由失败 → serde_json 实现或收回 pub API |
| RS-007 | P1 | 死防护 | core/rust-policy-core/src/tostring_guard.rs:52,74 | proxyMap 无任何模块注册——toString 欺骗防护为零 → 覆盖点同步注册 |
| RS-008 | P1 | DoS | core/rust-policy-core/src/matcher.rs:30-37 | 16K 上限时 DP 缓冲 (16385)²≈256MiB 单次分配 → 乘积上限 |
| RS-009 | P1 | DoS | core/rust-policy-core/src/session_state.rs:55 | from_json 先全量解析后限长——无界分配 → 解析前总长上限 |
| RS-010 | P1 | 绕过 | core/rust-policy-core/src/query_strip.rs:153-156 | 注入 JS 的参数剥离区分大小写（P34 半面）→ JS 侧小写化比较后 delete |

### 0.4 Python/CI/契约/发布链（PY-001..025）

| ID | 优先级 | 类型 | 位置 | 问题 → 方案 |
|---|---|---|---|---|
| PY-001 | P1 | 契约漂移 | contracts/schemas/version.schema.json:8 | version pattern 拒绝预发布号——当前 2.2.0-beta.44 无法通过（P100 回归）→ pattern 补预发布段 |
| PY-002 | P1 | 契约漂移 | contracts/schemas/update-manifest.schema.json:10 | 同上枚举 pattern 拒绝 beta → 单源同一 SemVer pattern |
| PY-003 | P1 | 契约漂移 | contracts/schemas/update-manifest.schema.json:19-20 | platform/format 枚举缺 inno-setup-exe/exe/zip → 补枚举并与 release.json 对账 |
| PY-004 | P1 | 防回滚绕过 | release/update_verifier.py:50 | _version_tuple 丢弃预发布段——回滚到预发布清单可绕过 → 按 SemVer precedence 比较 |
| PY-005 | P1 | 生成器缺陷 | scripts/gen_jsapi_schema.py:66 | 只遍历 Api 自身 body——28/30 暴露方法来自 mixin 缺失 → 解析基类链 |
| PY-006 | P1 | CI 编排 | .github/workflows/release-windows.yml:5-11 | tag 直推+workflow_call 双触发——重复构建/发布竞态 → 移除子工作流 push.tags |
| PY-007 | P1 | CI 编排 | .github/workflows/release-android.yml:9-15 | 同 PY-006 双触发面 → 同修 |
| PY-008 | P1 | CI 编排 | .github/workflows/release-core.yml:9-15 | 同 PY-006 双触发面 → 同修 |
| PY-009 | P1 | 死门禁 | release/verify_release.py:43-46 | 要求 .sigstore 但链路不产出且工具零调用 → 改判 gh attestation 或删断言 |
| PY-010 | P1 | 供应链 | .github/workflows/ci.yml:51 | pip install 无 hash 锁定（validate_release 专门门禁锁文件）→ --require-hashes |
| PY-011 | P1 | 门禁缺口 | .github/workflows/ci.yml:77-85 | mypy 手工清单 17/33——15 个 app 模块静默免检 → glob 全量 |
| PY-012 | P1 | CI fail-open | .github/workflows/release.yml:34 | pin-check grep 已删文件，返回码被吞当通过 → 目标改现存目录+缺失即 exit 1 |
| PY-013 | P1 | 契约门禁 | .github/workflows/contracts.yml:26-75 | 7 份 schema 纯装饰——向量不经 JSON Schema 校验 → jsonschema 步骤 |
| PY-014 | P1 | 生成链断裂 | scripts/gen_jsapi_schema.py:104 | 生成器零 CI 接线——schema 漂移无门禁 → 重生成+diff 门禁 |
| PY-015 | P1 | 死门禁 | contracts/codegen/analyze_action_catalog.py:64 | 静态分析器零调用 → 接入 contracts.yml |
| PY-016 | P1 | 生成器缺陷 | contracts/codegen/generate_csharp.py:59 | 陈旧清理 glob 与生成名不匹配——清理 no-op → 修 glob |
| PY-017 | P1 | 生成器缺陷 | contracts/codegen/generate_kotlin.py:58 | 同 PY-016 → 修 glob |
| PY-018 | P1 | 锁定构建 | .github/workflows/release-windows.yml:59 | cargo build 不带 --locked（test 带）→ 补 --locked |
| PY-019 | P1 | 供应链 | .github/workflows/core-rust.yml:41 | cargo-audit 未锁版本（3 处）→ --version pin |
| PY-020 | P1 | 供应链 | .github/workflows/agent-redteam.yml:21 | pyyaml 未锁版本+重复安装 → pin+单次 |
| PY-021 | P1 | 供应链 | .github/workflows/release-windows.yml:90 | innosetup 未锁版本 → --version pin |
| PY-022 | P1 | 向量腐化 | contracts/vectors/update-manifest-valid.json:4 | 合法向量 expires_at 已过期 → 远期日期 |
| PY-023 | P1 | 向量腐化 | contracts/vectors/approvals-replay-and-expiry.json:4 | 同上 → 远期日期 |
| PY-024 | P1 | 校验器缺陷 | release/tools/verify_artifact_set/verify_artifact_set.py:46 | expected 以 basename 为键跨平台互相覆盖+不递归 → platform+basename+rglob |
| PY-025 | P1 | CI 重复 | .github/workflows/release.yml:133-185 | verify-gate 内联 50 行复刻校验脚本（规则必漂移）→ 直接调用脚本 |

### 0.5 Web 资产与文档（WB-001..009）

| ID | 优先级 | 类型 | 位置 | 问题 → 方案 |
|---|---|---|---|---|
| WB-001 | P1 | 功能失效 | shared/shell/start.js:126 | importBookmarks 三端分支均 return undefined——cs 端导入统计恒 0、宫格不刷新（P89/90 回归）→ 返回 thenable |
| WB-002 | P1 | 功能失效 | shared/shell/start.js:131 | importHistory 同样丢弃返回值 → 回调/thenable 双通道 |
| WB-003 | P1 | 变更日志 | CHANGELOG.md:3 | 缺 beta.32–beta.44 共 13 版条目 → 补齐+门禁 |
| WB-004 | P1 | 文档矛盾 | CLAUDE.md:46 | 架构红线#1 仍指 main_webview.py（归档栈）→ 改指 C# 工程 |
| WB-005 | P1 | 文档缺口 | CLAUDE.md:17 | 关键命令全为归档栈——缺 dotnet/cargo/契约命令 → 增补正典命令段 |
| WB-006 | P1 | 文档缺口 | CONTRIBUTING.md:44 | 质量门槛缺 C#/Rust → 补全双栈 |
| WB-007 | P1 | 文档过时 | docs/product/supported-features.md:9 | 仍称 legacy 为"真实载体" → 重写现役段 |
| WB-008 | P1 | 文档过时 | docs/product/supported-features.md:22 | 称 C#"无书签/历史/多标签"（parity 已全勾）→ 更新已交付清单 |
| WB-009 | P1 | 文档过时 | docs/architecture-overview.md:3 | 架构全景仅 Python 27 文件视图 → 重写双端正典架构 |

### 0.6 补充盲区（SP-001..008）

| ID | 优先级 | 类型 | 位置 | 问题 → 方案 |
|---|---|---|---|---|
| SP-001 | P1 | 契约冲突 | agent/action-planner-contract.md:9-19 | ProposedAction 示例与冻结 action.schema.json 字段集完全冲突 → 改为严格符合 schema |
| SP-002 | P1 | 缺陷库损坏 | tests/KNOWN_DEFECTS.md:34-37 | BUG-011/012/013 孤立表外渲染破碎 → 并入主表补表头 |
| SP-003 | P1 | 编号冲突 | docs/KNOWLEDGE_BASE.md:470,482 | KB 内嵌 ADR-008/009 与 docs/adr/ 同号不同题 → 改 KB-DR 编号互引 |
| SP-004 | P1 | 权威入口失效 | docs/architecture-overview.md:12 | agent/README 声称蓝图并入本文件但内容过时 → 重写或加横幅 |
| SP-005 | P1 | 交付声明失真 | shared/release.json:9-11 | 声明 arm64 但全链无 arm64 构建 → 删声明或补构建 |
| SP-006 | P1 | 策略零消费 | release/manifests/signing-policy.yaml:8-21 | threshold:2 由脚本硬编码复写——策略可漂移 → 脚本读 yaml 单源 |
| SP-007 | P1 | 缺陷库矛盾 | tests/KNOWN_DEFECTS.md:34 | BUG-011 修复列写已删除的 AddressBarSnake.kt → 改 start.snake.js |
| SP-008 | P1 | 测试缺口 | agent/tests/redteam_e2e_test.py:36-54 | E2EBroker deny_scope 分支零触达 → 增 scope 用例 |

---

## 第一部分：Windows C#（CS-001..296，296 项）

统计：P1×6 / P2×77 / P3×207；测试缺口 118 / 健壮性 78 / 代码质量 50 / 性能 27 / API 一致性 10 / XAML 无障碍 13。

### 1.1 P2（CS-007..083）

| ID | 位置 | 问题 → 方案 |
|---|---|---|
| CS-007 | Broker/BrowserPolicyBroker.cs:191 | RequestNavigationConfirmation 缺 KillSwitch 前置检查 → 头部补检查+审计 |
| CS-008 | Broker.Tests | 缺 AllowDownload_KillSwitch 用例 → 断言 false+审计含 kill_switch_engaged |
| CS-009 | Broker.Tests | 缺 EvaluateNavigation_KillSwitch_Denies 用例 |
| CS-010 | Broker.Tests | 缺 RegisterSession_重复 sessionId false 用例 |
| CS-011 | Broker.Tests | 缺 RegisterSession 超 1024 上限 false 用例 |
| CS-012 | Broker.Tests | 缺 RegisterSession null/空白 false 用例 |
| CS-013 | Broker.Tests | 缺 UpdateDocumentGeneration 拒跳跃/回退/错标签用例 |
| CS-014 | Broker.Tests | 缺过期授权 IsValid false 用例 |
| CS-015 | Broker.Tests | 缺 TryConsumeNavigation 同 nonce 重放拒绝用例 |
| CS-016 | Broker.Tests | 缺注入 blockedHosts 的 IsHostBlocked 用例 |
| CS-017 | Broker.Tests | 缺 UpdateBlockedHosts(null) 回退放行用例 |
| CS-018 | Core/History/HistoryStore.cs:180 | title 参数未 LikeEscape——同搜索 %/_ 在标题当通配 → 统一 LikePattern |
| CS-019 | HistorySettingsTests | 缺 Search 多词语义用例 |
| CS-020 | HistorySettingsTests | 缺 Search 大小写不敏感用例 |
| CS-021 | HistoryStoreUpgradeTests | 缺 ByDate 未知日期空用例 |
| CS-022 | HistoryStoreUpgradeTests | 缺 Dates limit 边界用例 |
| CS-023 | HistoryStoreUpgradeTests | 缺 Delete 不存在 id false 用例 |
| CS-024 | HistorySettingsTests | 缺 Clear 后 Count==0 组合断言 |
| CS-025 | HistorySettingsTests | 缺 Add 磁盘失败返回 false 不抛用例 |
| CS-026 | HistoryStorePageNumberTests | 缺仅标题命中 Count 用例 |
| CS-027 | HistoryStorePagingTests | 缺单端区间组合用例 |
| CS-028 | HistoryStore.cs:82 | limit 负值=无上限（SQLite 语义）→ 统一 Math.Max(1,limit) |
| CS-029 | Bookmarks/BookmarkStore.cs:147 | 每次 Open 跑 DDL（All 每 150ms 调用）→ EnsureSchema-once |
| CS-030 | Tabs/TabSessionStore.cs:116 | 每次 Open 跑 DDL+迁移 → EnsureSchema-once |
| CS-031 | Chrome/Ntp/NtpBridgeFactory.cs:112 | 导入在 UI 线程同步跑 → Task.Run+回投 |
| CS-032 | BookmarkManagerWindow.xaml.cs:32 | 过滤无防抖全表加载 → DispatcherTimer 200ms |
| CS-033 | HistoryWindow.xaml.cs:249 | Delete/Clear 无 try/catch → 捕获+EmptyHint 反馈 |
| CS-034 | HistoryWindow.xaml.cs:82 | 日期 ToString 未指定 InvariantCulture → 统一 |
| CS-035 | DateField.xaml.cs:740 | 年份 1/9999 边界越界抛异常 → 钳制+禁用按钮 |
| CS-036 | Tabs/ZoomStore.cs:33 | Get 只校验下界——超上界脏值原样返回 → 补上界钳制 |
| CS-037 | UtilityClassesTests | 缺 ZoomStore 高越界用例（驱动 CS-036） |
| CS-038 | MainWindow.xaml.cs:127 | SafeNavigate 逻辑存在 4 份漂移面 → 收敛 TabRuntime.Navigate 单源 |
| CS-039 | UtilityClassesTests | TrackerList.IsSameSite 零覆盖 → 5 断言 |
| CS-040 | WindowSmokeTests | HistoryWindow.DateLabel 四分支零测试 → 提 internal 直测 |
| CS-041 | WindowSmokeTests | HistoryWindow.ParseLocalTime 分支零测试 |
| CS-042 | AuditRegressionTests | OriginPolicy MaxUrlLength=8192 边界零测试 |
| CS-043 | AuditRegressionTests | OriginPolicy host 长度/标签边界零测试 |
| CS-044 | AuditRegressionTests | userinfo 拒绝分支零测试 |
| CS-045 | AuditRegressionTests | 控制字符/0x7F 拒绝零测试 |
| CS-046 | BookmarkTests | BookmarkStore.Rename 零测试 |
| CS-047 | BookmarkTests | Rename 空白标题 false 分支零测试 |
| CS-048 | BookmarkTests | RemoveById 不存在 false 零测试 |
| CS-049 | BookmarkTests | ClearAll 零测试 |
| CS-050 | BookmarkTests | Import 重复 URL 计 total 不计 imported 零直测 |
| CS-051 | ThreatFeedCoordinatorTests | 缺刷新成功应用新快照用例 |
| CS-052 | ThreatFeedCoordinatorTests | 缺刷新失败保旧快照用例 |
| CS-053 | NtpBridgeTests | 缺 marker/id 非数字不抛用例 |
| CS-054 | NtpBridgeTests | 缺 jsError 写日志用例 |
| CS-055 | NtpBridgeTests | 缺 importHistory limit 钳 1..2000 用例 |
| CS-056 | NtpBridgeTests | 缺 goBack false 透传用例 |
| CS-057 | ThreatFeedTests | ParseFeedLine localhost/IPv6/端口条目零用例 |
| CS-058 | ThreatFeedTests | ValidateFeedUrl 首尾空白裁剪零用例 |
| CS-059 | WindowSmokeTests | 缺 SettingsWindow STA 冒烟 |
| CS-060 | WindowSmokeTests | 缺 BookmarkManagerWindow STA 冒烟 |
| CS-061 | WindowSmokeTests | 缺 SourceViewerWindow STA 冒烟 |
| CS-062 | ApprovalPanelControllerTests | 缺 Resolved 隐藏面板用例 |
| CS-063 | MainWindow.xaml:359 | BookmarkBarItems ItemTemplate+处理器死代码 → 删除 |
| CS-064 | MainWindow.xaml.cs:1001 | 每次查看源码 new HttpClient → 静态共享 |
| CS-065 | WebView/HostWebView.cs:129 | NavigationStarting UI 线程同步 DNS 解析 → 缓存快路径 |
| CS-066 | FingerprintShieldTests | NewSessionSeed 未锁 hex 字符集 → 正则断言 |
| CS-067 | MainWindow.xaml.cs:727 | RestoreWindowState 无下界/上限钳制 → 统一口径 |
| CS-068 | Security/ThreatFeed.cs:40 | IsBlocked 每次生成后缀串（热路径）→ 预展开 HashSet |
| CS-069 | HostWebView.cs:243 | IsTrustedChromeOrigin 死代码 → 删除 |
| CS-070 | HostWebView.cs:251 | RedactUrl 与 Broker 逐行重复 → 提取 UrlRedactor 单源 |
| CS-071 | TabRuntimeCoordinator.cs:54 | Close/Sleep 方法体相同 → 提取 Teardown |
| CS-072 | DecouplingTests | 缺 NativePolicyCoreGate 空路径用例 |
| CS-073 | Broker.Tests | 缺 NativePolicyCoreBridge.TryCreate(null) false 用例 |
| CS-074 | ThreatFeedTests | 缺仅点号 host 不误拦用例 |
| CS-075 | SettingsServiceTests | 缺写盘失败不抛且内存快照已更新用例 |
| CS-076 | UrlSafetyTests | 缺 .local/.internal/.localhost 后缀分支用例 |
| CS-077 | SettingsWindow.xaml:9 | 全窗 0 个 AutomationProperties → 逐控件补 |
| CS-078 | HistoryWindow.xaml:121 | 全窗 0 个 AutomationProperties → 逐控件补 |
| CS-079 | BookmarkManagerWindow.xaml:117 | 全窗 0 个 AutomationProperties → 逐控件补 |
| CS-080 | DownloadsWindow.xaml:58 | 全窗 0 个 AutomationProperties → 逐控件补 |
| CS-081 | InPrivateWindow.xaml:38 | 全窗 0 个 AutomationProperties → 逐控件补 |
| CS-082 | MainWindow.xaml:155 | 标签条 ✕/SleepMark 无 Name → 补 |
| CS-083 | MainWindow.xaml:382 | 查找条 ▲/▼/✕ 无 Name → 补 |

### 1.2 P3（CS-084..296）

| ID | 位置 | 问题 → 方案 |
|---|---|---|
| CS-084 | HistoryStore.cs:20 | 修剪逻辑零测试 → 提 internal+小阈值测试 |
| CS-085 | HistoryStore.cs:330 | 每次 Open 建目录 → 静态 HashSet 记录 |
| CS-086 | HistoryStore.cs:337 | Pooling=false 无注释权衡 → 注释或开池 |
| CS-087 | HistoryStore.cs:147 | clauses 构建四处重复 → 提取 BuildFilter |
| CS-088 | HistoryStore.cs:301 | Read() 单调用者 → 内联 |
| CS-089 | HistoryStore.cs:49 | visited_date 未指定 InvariantCulture → 统一 |
| CS-090 | HistoryStore.cs:48 | visited_at 存本地时间 DST 错位 → 改 UTC |
| CS-091 | HistoryStore.cs:356 | 双检锁对象是 ConcurrentDictionary → 换独立锁 |
| CS-092 | HistoryStore.cs:74 | LikeEscape 三连 Replace → 单遍循环 |
| CS-093 | HistoryRecorderTests | 缺 NTP host 大小写/geo 主机用例 |
| CS-094 | HistoryImporter.cs:68 | 清理仅捕 IOException → 改捕 Exception |
| CS-095 | HistoryImporterTests | 缺空候选 (0,0) 用例 |
| CS-096 | HistoryImporter.cs:105 | limit 钳制内联不可测 → 提取 ClampLimit |
| CS-097 | BookmarkTests | 缺空白候选跳过不计 total 用例 |
| CS-098 | BookmarkTests | 缺空白标题 false 用例 |
| CS-099 | BookmarkStore.cs:144 | busy_timeout 仅此库 → 四库统一 |
| CS-100 | BookmarkImporter.cs:508 | Parse 无容错 → 捕获返回空 |
| CS-101 | BookmarkImporter.cs:527 | TrimTitle 可劈代理对 → 代理对安全截断 |
| CS-102 | BookmarkTests | 缺深度>64 截断用例 |
| CS-103 | BookmarkTests | 缺无 roots 键返回空用例 |
| CS-104 | BookmarkTests | 缺 URL 超 2048 拒收用例 |
| CS-105 | BookmarkTests | 缺 name 缺省回退 host 用例 |
| CS-106 | DownloadPolicy.cs:41 | 同 URL 解析两次 → 一次传递 |
| CS-107 | DownloadPolicyTests | 缺空 url+空文件名 false 用例 |
| CS-108 | DownloadPolicyTests | 缺多级扩展 x.tar.exe 用例 |
| CS-109 | DownloadPolicyTests | 缺 URL 编码形态 f=x%2Fy.exe 用例 |
| CS-110 | DownloadItem.cs:73 | FormatBytes 默认文化 → InvariantCulture |
| CS-111 | DownloadItem.cs:102 | Refresh 异常面不全 → 兜底 catch |
| CS-112 | DownloadItem.cs:15 | 中文串状态机 → 提枚举 |
| CS-113 | DownloadItem.cs:69 | FormatBytes 不可测 → 提 internal |
| CS-114 | DownloadRecordStore.cs:72 | Open 失败连接不 Dispose → try-catch-dispose |
| CS-115 | DownloadRecordStore.cs:74 | CREATE TABLE 每次 Add → EnsureSchema-once |
| CS-116 | DownloadRecordStore.cs:51 | 负 limit=无上限 → Math.Max |
| CS-117 | DownloadRecordStoreTests | 缺默认 limit=200 用例 |
| CS-118 | DownloadRecordStore.cs:35 | 每次插入跑修剪 → 仅超限修剪 |
| CS-119 | FaviconService.cs:74 | 全命中长会话缓存无界 → Mem 写后 Trim |
| CS-120 | FaviconService.cs:196 | CachePath 不可测 → 提 internal |
| CS-121 | FaviconService.cs:26 | 进程级缓存不区分无痕 → 独立实例 |
| CS-122 | SettingsService.cs:168 | 白名单内联字面量 → static readonly |
| CS-123 | SettingsService.cs:172 | 宽高阈值两套并存 → 单源常量 |
| CS-124 | SettingsServiceTests | 缺缩放超上界钳制用例 |
| CS-125 | SettingsServiceTests | 缺构造器坏文件路径用例 |
| CS-126 | SettingsServiceTests | 缺 Apply 触发一次 Changed 用例 |
| CS-127 | MainWindowDependencies.cs:22 | settings.json 读两次 → 合并读取 |
| CS-128 | SettingsServiceTests | 缺 NaN 往返用例 |
| CS-129 | ZoomStore.cs:44 | Changed 锁内外不一致 → 统一锁外 |
| CS-130 | ZoomStore.cs:20 | Load(null) 抛 → null 守卫 |
| CS-131 | ThreatFeed.cs:173 | LoadCached 回放不经过滤 → 套 ParseFeedLine |
| CS-132 | ThreatFeed.cs:169 | 超限时 5MB 分配只为表达超限 → 哨兵 |
| CS-133 | ThreatFeedTests | 两文件重复覆盖 → 合并 |
| CS-134 | ThreatFeedCoordinator.cs:65 | 刷新后重读磁盘 → 直接用返回值 |
| CS-135 | SecurityLog.cs:24 | 每次写两次系统调用 → 计数器 |
| CS-136 | TrackerList.cs:425 | IsTracker 每请求切片分配 → 预展开 |
| CS-137 | TrackerList.cs:437 | IsSameSite 分配 → EndsWith 语法 |
| CS-138 | UrlNormalizerTests | 缺未知引擎回退用例 |
| CS-139 | UrlNormalizerTests | 缺尾点输入判搜索词用例 |
| CS-140 | UrlNormalizer.cs:69 | 裸 IPv6 判搜索词 → 识别补 http |
| CS-141 | UrlNormalizerTests | 缺 ABOUT:BLANK 大小写用例 |
| CS-142 | UrlNormalizerTests | 缺 host:port 带路径用例 |
| CS-143 | SuggestionController.cs:109 | ToLower 两串分配 → Contains+OrdinalIgnoreCase |
| CS-144 | SuggestionController.cs:108 | 循环无早退 → break |
| CS-145 | SuggestionController.cs:107 | seenUrls 用 Ordinal → OrdinalIgnoreCase |
| CS-146 | SuggestionController.cs:140 | WrapIndex 不可测 → 提取 |
| CS-147 | FindBarController.cs:62 | 空 catch 全吞 → SecurityLog |
| CS-148 | ApprovalPanelControllerTests | 缺同标签二次 Request 用例 |
| CS-149 | ApprovalPanelController.cs:70 | 格式化未指定 InvariantCulture → 统一 |
| CS-150 | MainWindow.xaml.cs:727 | 四个恢复阈值魔法数 → 命名常量 |
| CS-151 | MainWindow.xaml.cs:1210 | CycleTab ToList 复制 → for 循环 |
| CS-152 | MainWindow.xaml.cs:960 | 每次新建两把刷子 → 缓存 |
| CS-153 | MainWindow.xaml.cs:155 | 书签栏无上限重建 → 截断+溢出 |
| CS-154 | MainWindow.xaml.cs:1027 | 失败分支未守卫 IsLoaded → 补守卫 |
| CS-155 | MainWindow.xaml.cs:144 | TruncateTitle 零直测 → 提 internal |
| CS-156 | MainWindow.xaml.cs:1236 | 双 FlushSession → 保留单点 |
| CS-157 | MainWindow.xaml.cs:1216 | ToDigit 不可测 → 提取 |
| CS-158 | MainWindow.xaml.cs:1205 | NextIndex 不可测 → 提取 |
| CS-159 | HistoryWindow.xaml.cs:97 | LoadPage UI 线程同步查 → Task.Run |
| CS-160 | HistoryWindow.xaml.cs:131 | FindResource 无守卫 → TryFindResource |
| CS-161 | HistoryWindow.xaml.cs:190 | TryHost 零测试 → 直测 |
| CS-162 | BookmarkManagerWindow.xaml.cs:39 | ToLower Contains → OrdinalIgnoreCase |
| CS-163 | BookmarkManagerWindow.xaml.cs:94 | 标题截断可劈代理对 → 安全截断 |
| CS-164 | BookmarkManagerWindow.xaml.cs:96 | Rename/Remove/ClearAll 无捕获 → 捕获反馈 |
| CS-165 | BookmarkManagerWindow.xaml.cs:32 | 过滤谓词不可测 → 提取纯函数 |
| CS-166 | BookmarkManagerWindow.xaml.cs:44 | "共 N"语义误导 → 匹配 N/共 M |
| CS-167 | SettingsWindow.xaml.cs:85 | 每次新建刷子 → 缓存 |
| CS-168 | SettingsWindow.xaml.cs:42 | KillSwitch 文案两处重复 → 单源 |
| CS-169 | SettingsWindow.xaml.cs:96 | SleepIndex 不可测 → 提取 |
| CS-170 | DownloadsWindow.xaml.cs:41 | 每 500ms ToList → for 循环 |
| CS-171 | DownloadsWindow.xaml.cs:25 | 隐藏时轮询继续 → 暂停恢复 |
| CS-172 | DownloadsWindow.xaml.cs:69 | 危险条目直接执行 → 二次确认 |
| CS-173 | DownloadsWindow.xaml.cs:105 | Process.Start 拼接串 → ArgumentList |
| CS-174 | DownloadsWindow.xaml.cs:21 | 列表只增不减 → 清空按钮 |
| CS-175 | DateField.xaml.cs:674 | yyyy-MM-dd 未指定 Invariant → 统一 |
| CS-176 | DateField.xaml.cs:686 | 周一 offset 不可测 → 提取 |
| CS-177 | InPrivateWindow.xaml.cs:158 | 未切 IsHitTestVisible → 对齐 |
| CS-178 | WebViewEnvironment.cs:24 | _shared ??= 非线程安全 → Lazy |
| CS-179 | WebViewEnvironment.cs:87 | InPrivate 不加 DoH 未注释 → 注释或启用 |
| CS-180 | WebViewEnvironment.cs:67 | 重试全败静默 → SecurityLog |
| CS-181 | WebViewEnvironment.cs:69 | 重试魔法数 → 常量 |
| CS-182 | WebView2Hardening.cs:65 | 注入 fire-and-forget → ContinueWith |
| CS-183 | WebView2Hardening.cs:94 | IsTrustedLocalHost 零直测 → 4 例 |
| CS-184 | FingerprintShield.cs:26 | 种子未校验直插 JS → 入口校验 |
| CS-185 | FingerprintShieldTests | 缺非法种子被拒用例 |
| CS-186 | TabSessionStore.cs:75 | SELECT position 不读取 → 移除 |
| CS-187 | TabSessionStoreTests | 缺空列表清空会话用例 |
| CS-188 | TabSessionStoreTests | 缺损坏库最后行生效用例 |
| CS-189 | NtpBridge.cs:72 | 仅捕 JsonException → 扩捕 |
| CS-190 | NtpBridgeTests | 缺字符串数字解析用例 |
| CS-191 | NtpBridgeFactory.cs:87 | SavedSessionCount 全量 Load → COUNT 查询 |
| CS-192 | NtpBridgeFactory.cs:209 | FilterSources 大小写敏感零测试 → 直测 |
| CS-193 | NtpAssets.cs:65 | 每标签 File.Exists → 进程缓存 |
| CS-194 | NtpBridgeTests | IsVirtualHostUrl 零直测 → 3 例 |
| CS-195 | NtpBridgeTests | IsWallpaperAllowed 零直测 → 3 例 |
| CS-196 | App.xaml.cs:86 | ShouldShowPopup 不可测 → 提取 RateLimiter |
| CS-197 | App.xaml.cs:106 | 构造 MainWindow 异常闪退无日志 → 捕获+日志 |
| CS-198 | HostWebView.cs:216 | pageHost 每请求重 Parse → 缓存 |
| CS-199 | HostWebView.cs:366 | checked 溢出于导航事件 → 前置守卫 |
| CS-200 | AuditRegressionTests | 合法 IPv6 放行零用例 |
| CS-201 | AuditRegressionTests | IPv6 zone 拒绝零用例 |
| CS-202 | KillSwitch.cs:221 | EnsureNotEngaged 死代码 → 删除 |
| CS-203 | Contracts.cs:11 | ContractRoot 零引用+版本重复 → 删/单源 |
| CS-204 | StorageService.cs:6 | 空骨架零引用 → 删除 |
| CS-205 | Tab.cs:6 | 注释宣称无 UI 依赖却有 ImageSource → 改注释 |
| CS-206 | NativePolicyCoreBridge.cs:298 | 第二个 Utf8 分配抛则指针泄漏 → 统一进 try |
| CS-207 | NativePolicyCoreBridge.cs:14 | 裸 IntPtr 无 SafeHandle → 封装 |
| CS-208 | NativePolicyCoreBridge.cs:235 | fail-closed 行为零直测 → 开 internal |
| CS-209 | BrowserPolicyBroker.cs:95 | 1024 内联字面量 → const |
| CS-210 | BrowserPolicyBroker.cs:98 | TTL 120 裸数字 → const |
| CS-211 | BrowserPolicyBroker.cs:181 | AddMinutes(2) 魔法数 → const |
| CS-212 | BrowserPolicyBroker.cs:336 | 截断可劈代理对 → 安全截断 |
| CS-213 | Broker.Tests | AuditLog 环形上限零测试 → 5001 次断言 |
| CS-214 | Broker.Tests | TryConsume(null) 零测试 |
| CS-215 | Broker.Tests | 不可解析 URL deny 分支零测试 |
| CS-216 | MainWindow.xaml:246 | EngineCombo 无 Name → 补 |
| CS-217 | MainWindow.xaml:321 | AddressBar 无 Name → 补 |
| CS-218 | MainWindow.xaml:33 | NavButton Focusable=False → 注释或局部放开 |
| CS-219 | MainWindow.xaml:347 | FeedbackText 无 LiveSetting → 补 |
| CS-220 | MainWindow.xaml:133 | TabStrip 无 Name → 补 |
| CS-221 | MainWindow.xaml:17 | AccentSoftBrush 零引用 → 删/接线 |
| CS-222 | SourceViewerWindow.xaml:16 | SourceText 无 Name → 补 |
| CS-223 | InPrivateWindow.xaml.cs | 无快捷键与主窗不对齐 → 补分支 |
| CS-224 | InPrivateWindow.xaml.cs:878 | 每窗同步读 settings → 传入引擎 |
| CS-225 | BookmarkManagerWindow.xaml.cs:64 | 编辑弹层无键盘路径 → 补 KeyDown |
| CS-226 | SettingsWindow.xaml.cs:137 | 无 Enter/Esc → 补 |
| CS-227 | FindBarController.cs:34 | 关闭后焦点不落页面 → 显式还给 WebView |
| CS-228 | MainWindow.xaml.cs:878 | 可收藏虚拟主机页 → 排除 |
| CS-229 | MainWindow.xaml.cs:989 | 虚拟主机 URL 抓源必失败 → 前置提示 |
| CS-230 | App.xaml.cs | 无单实例互斥 → Mutex |
| CS-231 | HistoryImporter.cs:19 | DetectSources 近似复制 → 提取共享 |
| CS-232 | ThreatFeed.cs:149 | Move 抛时 tmp 残留 → finally 清理 |
| CS-233 | MainWindow.xaml.cs:45 | _sourceViewerWindows 驻留 → OnClosed 清理 |
| CS-234 | MainWindow.xaml.cs:86 | ApplyTheme 失败仅 Debug → SecurityLog |
| CS-235 | MainWindow.xaml.cs:191 | EngineOption 双定义 → 提公共 |
| CS-236 | TabRuntime.cs:119 | 0.001 epsilon 魔法数 → const |
| CS-237 | TabRuntime.cs:82 | 匿名订阅不退订 → 命名化 |
| CS-238 | TabRuntimeCoordinator.cs:45 | 重复创建覆盖泄漏 → 先 Close 再建 |
| CS-239 | DecouplingTests | ctor null 分支零测试 |
| CS-240 | TabSleepPolicyTests | 缺空集合用例 |
| CS-241 | ZoomPolicyTests | 缺非法负 current 钳制用例 |
| CS-242 | ThreatFeedTests | LoadCached 空白行裁剪零用例 |
| CS-243 | UtilityClassesTests | TrackerList.Domains 元测试 |
| CS-244 | ThreatFeedTests | 空集合放行零用例 |
| CS-245 | ThreatFeedCoordinatorTests | 缺空白 URL 裁剪路径用例 |
| CS-246 | SecurityLog.cs:15 | 路径绑定静态不可测 → 注入面 |
| CS-247 | Core.Tests | SecurityLog 转义/截断零直测 |
| CS-248 | AppPaths.cs:8 | 静态冻结不可测 → ResetForTest |
| CS-249 | MainWindowDependencies.cs:21 | 直指真实用户目录 → 文档+override |
| CS-250 | TabSessionStoreTests | 缺 IsPinned 往返用例 |
| CS-251 | SessionSaveSchedulerTests | 缺无脏数据仍保存锁定用例 |
| CS-252 | DownloadPolicyTests | 缺截断保扩展名断言 |
| CS-253 | SettingsServiceTests | 缺 SleepMinutes 非法归一用例 |
| CS-254 | UrlNormalizerTests | 缺 null 入参用例 |
| CS-255 | HistoryStorePagingTests | 缺末页 HasMore=false 断言 |
| CS-256 | Core.Tests | 缺 xunit.runner.json → 补齐同配置 |
| CS-257 | MainWindow.xaml.cs:433 | 切换遍历全部 runtime → 单旧值翻转 |
| CS-258 | MainWindow.xaml.cs:615 | 菜单无 InputGestureText → 补 |
| CS-259 | HistoryStore.cs:93 | 非 ASCII 大小写敏感 → 文档化或冗余列 |
| CS-260 | MainWindow.xaml.cs:287 | 两处订阅投递优先级不同 → 统一处理器 |
| CS-261 | MainWindow.xaml.cs:114 | Changed 用 Invoke 阻塞 → 评估 BeginInvoke |
| CS-262 | TabManager.cs:56 | IndexOf O(n) → 直接用 insertAt |
| CS-263 | TabManager.cs:114 | 撤销栈上限 20 魔法数 → const |
| CS-264 | TabManagerTests | 缺 Duplicate 用例 |
| CS-265 | TabManagerTests | 缺 PopClosed 空栈/LIFO 用例 |
| CS-266 | TabManagerTests | 缺撤销栈淘汰最旧用例 |
| CS-267 | TabManagerTests | 缺 SetPinned 未知 id no-op 用例 |
| CS-268 | TabManagerTests | 缺 UpdateTitle 空白忽略用例 |
| CS-269 | TabManagerTests | 缺 SeedSession 清空撤销栈用例 |
| CS-270 | TabManagerTests | 缺事件顺序契约用例 |
| CS-271 | TabManagerTests | 缺 CloseTab/CloseOthers 事件序列用例（配合 CS-001） |
| CS-272 | TabStripDragController.cs:65 | Drop 半侧判定不可测 → 提取 |
| CS-273 | ChromeControllersTests | 拖拽控制器无逻辑级测试 → 补 |
| CS-274 | DownloadsWindow.xaml.cs:59 | 提示与状态未联动 → 绑定 |
| CS-275 | DownloadPolicy.cs:57 | Split('/').Last 分配 → LastIndexOf |
| CS-276 | NtpBridge.cs:141 | 默认 500 三处重复 → const |
| CS-277 | NtpBridge.cs:50 | Dispatch 抛时页面 Promise 永挂 → 包 try 回错误 |
| CS-278 | MainWindow.xaml.cs:163 | 每次全量重建书签栏 → 缓存 Style |
| CS-279 | HistoryWindow.xaml.cs:147 | PageSize 未校验范围 → Clamp |
| CS-280 | SettingsService.cs:174 | 入参差异未注释 → 补注释 |
| CS-281 | InPrivateWindow.xaml.cs:90 | 匿名订阅不退订 → 注释或清理 |
| CS-282 | HistoryStore.cs:93+96 | IsNullOrEmpty 判两次 → 局部变量 |
| CS-283 | MainWindow.xaml.cs:447 | _suppressTabSelection 非 finally → 包裹 |
| CS-284 | InPrivateWindow.xaml.cs:163 | 同上 → 包裹 |
| CS-285 | BrowserPolicyBroker.cs:131 | RemoveWhere O(全部nonce) → 注释或分桶 |
| CS-286 | BookmarkStore.cs:27 | 两库时间口径不一致 → 统一 |
| CS-287 | HistoryWindow.xaml.cs:102 | 每页重建全 items → 批量替换 |
| CS-288 | MainWindow.xaml.cs:397 | fail-closed 无日志 → 补审计 |
| CS-289 | SettingsWindow.xaml:6 | 固定宽无滚动 → ScrollViewer |
| CS-290 | BookmarkManagerWindow.xaml.cs:137 | 删除无确认无日志 → SecurityLog |

---

## 第二部分：Android（AD-001..210，210 项）

统计：P1×31 / P2×38 / P3×141；测试缺口 96 / 代码质量 53 / 安全 28 / 资源无障碍 17 / Compose 14 / 协程生命周期 4。

### 2.1 P2（AD-032..069）

| ID | 位置 | 问题 → 方案 |
|---|---|---|
| AD-032 | WebViewDownloadHandler.kt:53 | 下载文件名无长度上限 → 组合名超 200 截断保扩展名 |
| AD-033 | BrowserViewModel.kt:395 | 页面可控标题原样写日志（换行伪造）→ 剥换行+截断 |
| AD-034 | SecureWebViewFactory.kt:57 | registerSession 失败路径 WebView 泄漏 → 先 tearDown 再抛 |
| AD-035 | AegisWebViewClient.kt:282 | 库模块持 UI 中文文案 → 错误码上抛+文案移 app 层 |
| AD-036 | BrowserViewModel.kt:380 | url 原地改 var 不触发 StateFlow → updateUrl copy 单写点 |
| AD-037 | TabManager.kt:121 | updateUrl 单写点测试 |
| AD-038 | MainActivity.kt:110 | 7 处 collectAsState → collectAsStateWithLifecycle |
| AD-039 | TabBar.kt:63 | itemsIndexed 未传 key → key=tab.id |
| AD-040 | VerticalTabBar.kt:74 | itemsIndexed 未传 key → key=tab.id |
| AD-041 | VerticalTabBar.kt:101 | rememberOrderedGroups 无 remember → 改 remember(tabs) |
| AD-042 | MainActivity.kt:314 | 纯字形按钮无 contentDescription → 补 semantics |
| AD-043 | TabChipCore.kt:73 | 关闭钮无语义 → contentDescription+Role.Button |
| AD-044 | TabBar.kt:75 | 「+」无 contentDescription → 补 |
| AD-045 | MainActivity.kt:137 | 无 strings.xml 约 30 条硬编码 → 建+迁入 |
| AD-046 | BrowserViewModel.kt:216 | 5 条提示硬编码 → 迁 strings.xml |
| AD-047 | AndroidManifest.xml:10 | label 字面量未引用 DISPLAY_NAME → @string/app_name |
| AD-048 | BrowserViewModel.kt:227 | 外链受 500ms 防抖静默吞 → 外链绕过防抖 |
| AD-049 | MainActivity.kt:207 | getTabManager()!! 两处 → requireNotNull |
| AD-050 | AegisWebViewClient.kt:168 | 自动批准分支不可测 → 注入 decision 源 |
| AD-051 | AndroidBroker.kt:334 | about:blank 特判无 broker 级测试 |
| AD-052 | AndroidBroker.kt:123 | destroySession 清 nonce 无测试 |
| AD-053 | AegisWebViewClient.kt:250 | onPageStarted 推进代际无客户端级测试 |
| AD-054 | AegisWebViewClient.kt:310 | onReceivedHttpError 过滤逻辑无测试 |
| AD-055 | BrowserEngine.kt:45 | 12 项硬化标志零回归 → Robolectric 逐项断言 |
| AD-056 | TabManager.kt:37 | addTab 即时挂起无测试 |
| AD-057 | SearchEngines.kt:61 | searchUrl 依赖 android Uri 不可 JVM 测 → 抽纯函数 |
| AD-058 | MainActivity.kt:77 | 版本检查主线程同步 → 协程包裹 |
| AD-059 | BrowserViewModel.kt:318 | 裸 Handler → viewModelScope.launch |
| AD-060 | TabManager.kt:103 | replaceWebView 保留 suspended 失真 → 重置 |
| AD-061 | BrowserViewModel.kt:323 | 手写销毁绕过 tearDown 单源 → 改调 tearDown |
| AD-062 | BrowserViewModel.kt:189 | closeTab 双调用 destroySession → 删显式 close |
| AD-063 | BrowserViewModel.kt:50 | 地址栏显示 file:// 原始 URL → 占位文案 |
| AD-064 | MainActivity.kt:268 | 前进后退按钮无感知禁用 → canGoBack Flow |
| AD-065 | AegisApplication.kt:12 | 无 UncaughtExceptionHandler → 注册留痕 |
| AD-066 | .github/workflows/android-quality.yml:48 | 未跑 :app:lintDebug → 加 step+baseline |
| AD-067 | app/src/androidTest | 无 instrumented 测试 → 冒烟集 |
| AD-068 | app/build.gradle.kts:152 | compose BOM 字面量未入 catalog → platform(libs.compose.bom) |
| AD-069 | WebViewHardening.kt:96 | BRIDGE_GUARD_JS 零 JVM 校验 → internal 暴露+断言 |

### 2.2 P3（AD-070..210）

| ID | 位置 | 问题 → 方案 |
|---|---|---|
| AD-070 | BrowserEngine.kt:6 | 4 个未使用 import → 删除 |
| AD-071 | BrowserViewModel.kt:246 | 字段声明散落 → 上移集中 |
| AD-072 | MainActivity.kt:349 | onDestroy suspendAll 冗余 → 去掉 |
| AD-073 | contracts/Contracts.kt:11 | Contracts 对象零引用 → 删/消除双源 |
| AD-074 | app/detekt-baseline.xml:9 | 基线含已删符号 → 重生成 |
| AD-075 | broker/detekt-baseline.xml:1 | 基线吞 39 条存量 → 分批清零 |
| AD-076 | WebViewHardening.kt:58 | 注释与实现不符 → 修正 |
| AD-077 | SearchEngines.kt:133 | replace(" ","%20") 重复执行 → 归一去重 |
| AD-078 | MainActivity.kt:264 | dp 魔法数散落 → Dimens 常量 |
| AD-079 | TabManager.kt:48 | LRU 用墙钟 → elapsedRealtime |
| AD-080 | NativePolicyCoreGate.kt:33 | probe 热路径重复加载 → 缓存 |
| AD-081 | BrowserViewModel.kt:250 | lateinit 无守卫 → 补齐 |
| AD-082 | Tab.kt:24 | pinned 字段无写入点（假 parity）→ 实现/删 |
| AD-083 | Tab.kt:25 | group 字段无写入点 → 实现/删 |
| AD-084 | Tab.kt:20 | data class 五个 var → val+copy |
| AD-085 | TabManager.kt:40 | 默认标题双处硬编码 → 常量单源 |
| AD-086 | TabBar.kt:53 | LazyRow 不随激活项滚动 → animateScrollToItem |
| AD-087 | VerticalTabBar.kt:65 | 每分组全量遍历 → groupBy 一次 |
| AD-088 | MainActivity.kt:382 | AndroidView 无 onRelease → removeAllViews |
| AD-089 | MainActivity.kt:385 | WebView 换挂依赖偶然重组 → 显式 activeIndex 键 |
| AD-090 | MainActivity.kt:131 | 对话框高度魔法数 → 常量 |
| AD-091 | MainActivity.kt:290 | 「打开」无 Role 且目标过小 → semantics+最小尺寸 |
| AD-092 | TabChipCore.kt:77 | 关闭钮 28dp 触摸目标 → 扩展点击区域 |
| AD-093 | AegisTheme.kt:31 | Typography 覆写不全 → 补齐 |
| AD-094 | res/values/styles.xml:5 | 颜色字面量未入 colors.xml → 迁入 |
| AD-095 | styles.xml:3 | Light 基底与深色 chrome 相悖 → 换 parent |
| AD-096 | AndroidManifest.xml:5 | 无 localeConfig → 建+挂接 |
| AD-097 | proguard-rules.pro:21 | webkit 全量 keep → 收窄 |
| AD-098 | proguard-rules.pro:5 | MainActivity 全成员 keep → 收窄 |
| AD-099 | broker/build.gradle.kts:94 | JNA 5.12 落后 → 升级回归 |
| AD-100 | app/build.gradle.kts:60 | versionCode 手写 → 读 version.properties |
| AD-101 | MainActivity.kt:468 | 468 行超红线 → 抽组件 |
| AD-102 | AegisWebViewClient.kt:381 | 381 行超红线 → 抽 ErrorTexts |
| AD-103 | BrowserViewModel.kt:442 | 442 行+TooManyFunctions → 抽装配对象 |
| AD-104 | WebViewHardening.kt:123 | sendBeacon 守卫缺失 → 显式存在性 |
| AD-105 | WebViewHardening.kt:129 | WebSocket 包装断原型链 → setPrototypeOf |
| AD-106 | WebViewHardening.kt:153 | 包装未注册反检测 → 各点注册 proxyMap |
| AD-107 | WebViewHardening.kt:161 | getETLD1 取最后两段——公共后缀共享种子 → 迷你 PSL |
| AD-108 | WebViewHardening.kt:286 | Date.now 返回非整数 → 取整仅 perf 加抖动 |
| AD-109 | ReaderMode.kt:89 | take 按字符劈代理对 → 边界回退 |
| AD-110 | MainActivity.kt:172 | Instant.toString 用户不可读 → 格式化 |
| AD-111 | BrowserViewModel.kt:215 | 空输入恐吓性文案 → 静默 no-op |
| AD-112 | AegisHomeBridge.kt:57 | isTrustedShellPage 不可测 → 抽纯函数 |
| AD-113 | AegisHomeBridge.kt:112 | setWallpaper 拒绝路径无测试 |
| AD-114 | AegisHomeBridge.kt:76 | setEngine 非法 key 无测试 |
| AD-115 | WebViewVersionCheck.kt:37 | 异常返回 null 无测试 |
| AD-116 | TabManager.kt:58 | 同索引切换 no-op 无测试 |
| AD-117 | TabManager.kt:81 | closeTab 先 pause 次序无测试 |
| AD-118 | TabManager.kt:130 | list() 浅拷贝语义无固化测试 |
| AD-119 | SearchEngines.kt:116 | 大写 scheme 分类无测试 |
| AD-120 | OriginPolicy.kt:32 | 大写解析无测试 |
| AD-121 | AndroidBroker.kt:128 | 直调 javascript: Deny 无测试 |
| AD-122 | AndroidBroker.kt:337 | about:blank 全链消费无测试 |
| AD-123 | AegisWebViewClient.kt:121 | rejectPending 空边界无测试 |
| AD-124 | BrowserEngine.kt:20 | HOME_URL 单源契约无守护 → 测试 |
| AD-125 | ReaderMode.kt:34 | MIN_TEXT 门槛无测试 |
| AD-126 | ReaderController.kt:31 | toggle 状态机无测试 |
| AD-127 | ReaderController.kt:47 | translate 失败分支无测试 |
| AD-128 | SecureWebViewFactory.kt:130 | release 未注册 no-throw 无测试 |
| AD-129 | SecureWebViewFactory.kt:139 | tearDown 次序无测试 |
| AD-130 | DownloadPolicy.kt:43 | URL 路径段判定无独立测试 |
| AD-131 | WebViewDownloadHandler.kt:115 | inferExtension 无测试 |
| AD-132 | Tab.kt:18 | equals 含 WebView 引用语义无守护测试 |
| AD-133 | WebViewDownloadHandler.kt:34 | 4 条 Toast 硬编码 → strings.xml |
| AD-134 | AegisHomeBridge.kt:144 | Toast 硬编码 → strings.xml |
| AD-135 | WebViewVersionCheck.kt:56 | 提示文案硬编码 → strings.xml |
| AD-136 | AegisWebViewClient.kt:328 | 错误映射硬编码 → 拆层后迁移 |
| AD-137 | WebViewDownloadHandler.kt:56 | runCatching 包成功 Toast → 分离捕获 |
| AD-138 | WebViewDownloadHandler.kt:119 | mime 子类型当扩展名 → 白名单映射 |
| AD-139 | AegisApplication.kt:13 | broker 主线程即时初始化 → lazy |
| AD-140 | MainActivity.kt:96 | 返回 null 时静默不 finish → 降级 finish |
| AD-141 | BrowserViewModel.kt:280 | 中缀 return 风格不一 → 分行 |
| AD-142 | AndroidBroker.kt:175 | nonce 内联表达式 → 抽函数 |
| AD-143 | AndroidBroker.kt:172 | Duration.parse 字符串拼 → Duration.seconds |
| AD-144 | NativePolicyCoreBridge.kt:98 | 手工 JSONObject 链 → 抽映射函数 |
| AD-145 | NativePolicyCoreGate.kt:21 | 双工厂无差别 → 合并 |
| AD-146 | SearchEngines.kt:36 | ENGINE_NAMES 双处维护 → 单源 |
| AD-147 | AegisHomeBridge.kt:39 | WALLPAPERS 人工同步 → 打包校验 |
| AD-148 | AegisHomeBridge.kt:39 | TRUSTED_ASSET_PATHS 双处硬编码 → 引用常量 |
| AD-149 | BrowserViewModel.kt:96 | 三处守卫样板 → 抽 withTabManager |
| AD-150 | MainActivity.kt:431 | 三元内嵌中文串 → 状态映射 |
| AD-151 | MainActivity.kt:120 | 三对话框无优先级 → 状态机 |
| AD-152 | MainActivity.kt:197 | 魔法字符串 "top"/"left" → 枚举 |
| AD-153 | MainActivity.kt:284 | 色彩未走 theme → 汇入语义色 |
| AD-154 | app/build.gradle.kts:158 | 依赖未入 catalog → 全量入库 |
| AD-155 | settings.gradle.kts:1 | 无依赖锁定 → enableDependencyLocking |
| AD-156 | app/build.gradle.kts:97 | 无 lint 配置块 → 显式 |
| AD-157 | BrowserViewModel.kt:238 | 防抖窗口行为无测试 → 时钟注入 |
| AD-158 | BrowserViewModel.kt:287 | 跨标签批准拒绝无测试 |
| AD-159 | BrowserViewModel.kt:176 | 切换撤销待审批无测试 |
| AD-160 | BrowserViewModel.kt:154 | refresh 草稿保护无测试 |
| AD-161 | TabManager.kt:133 | suspendAll 语义无固化测试 |
| AD-162 | NativePolicyCoreBridge.kt:245 | 缺省 explanation 容错无测试 |
| AD-163 | NativePolicyCoreBridge.kt:293 | unknown decision 抛→null 链路无测试 |
| AD-164 | NativePolicyCoreGate.kt:46 | gate 三态结构断言缺失 |
| AD-165 | BrowserEngine.kt:100 | 256 截断无测试 |
| AD-166 | SearchEngines.kt:44 | scheme 字符集边界无测试 |
| AD-167 | SearchEngines.kt:121 | isPortSegment 边界无测试 |
| AD-168 | OriginPolicy.kt:25 | 空白字符全集无逐项测试 |
| AD-169 | OriginPolicy.kt:38 | 端口 65535/65536 边界无测试 |
| AD-170 | TranslateEntry.kt:18 | 参数契约无测试 |
| AD-171 | BrowserEngine.kt:90 | 死回调噪声 → 移除/DEBUG 条件 |
| AD-172 | BrowserViewModel.kt:395 | 调试日志永久 info → DEBUG 包裹 |
| AD-173 | MainActivity.kt:448 | Surface+Text 当按钮 → Material3 Button |
| AD-174 | VerticalTabBar.kt:94 | 两套新建控件不统一 → 抽组件 |
| AD-175 | WebViewHardening.kt:183 | canvas 噪声仅 R 通道 → 多通道混淆 |
| AD-176 | WebViewHardening.kt:217 | 尺寸冻结常量 → getter 化或注释 |
| AD-177 | AegisWebViewClient.kt:136 | 待审批新导航拒旧 nonce 无测试 |
| AD-178 | AegisWebViewClient.kt:205 | 每子框架导航续期 → 仅主框架 |
| AD-179 | AndroidBroker.kt:313 | 逐出循环单移除 → 批量移除 |
| AD-180 | AndroidBroker.kt:340 | 默认端口映射脆弱 → 查表 |
| AD-181 | SecureWebViewFactory.kt:59 | sessionId 派生命名冗余 → 注释/透传 |
| AD-182 | network_security_config.xml:1 | 无守护 → 注释+断言 |
| AD-183 | MainActivity.kt:66 | onCreate 170 行 → 拆文件 |
| AD-184 | app/src/test | 仅 2 文件八类零覆盖 → 逐文件补齐 |
| AD-185 | app/build.gradle.kts:166 | 仅 junit → 引断言库+共享桩 |
| AD-186 | broker/build.gradle.kts:96 | adapter/contracts 无 test 接线 → 补 |
| AD-187 | UiColors.kt:13 | 颜色双源 → colors.xml 同源 |
| AD-188 | TabChipCore.kt:61 | emoji 前缀拼标题 → 固定槽位 |
| AD-189 | BrowserViewModel.kt:439 | orFalse 扩展散布 → 统一口径 |
| AD-190 | MainActivity.kt:74 | 状态栏图标硬编码 → 单源派生 |
| AD-191 | AegisHomeBridge.kt:90 | 每次重建 JSON → 静态缓存 |
| AD-192 | AegisHomeBridge.kt:140 | applicationContext Toast → 注释/回调上抛 |
| AD-193 | WebViewDownloadHandler.kt:49 | 通知无 title/description → 补 |
| AD-194 | WebViewDownloadHandler.kt:55 | Cookie 过滤语义 → 注释固化 |
| AD-195 | BrowserEngine.kt:107 | 单例重复获取 → 静态一次 |
| AD-196 | BrowserViewModel.kt:85 | lazy 时序约束仅注释 → 显式构造 |
| AD-197 | MainActivity.kt:86 | 冷启动外链消费时序 → 注释固化 |
| AD-198 | TabManager.kt:82 | 已关 WebView 再 loadUrl → 去冗余 |
| AD-199 | AndroidBroker.kt:49 | 三处重复判定 → 抽 nativeBridgeOrNull |
| AD-200 | AndroidBroker.kt:285 | 锁内 JNI 跨界 → 锁外调用 |
| AD-201 | AegisWebViewClient.kt:256 | 代际失败与本地分叉 → 回滚自增 |
| AD-202 | AegisWebViewClient.kt:44 | 404 与断网同文案 → 细分状态 |
| AD-203 | BrowserViewModel.kt:362 | deny code 映射不集中 → 映射表 |
| AD-204 | MainActivity.kt:143 | 去更新按钮无失败降级 → 降级/隐藏 |
| AD-205 | WebViewVersionCheck.kt:63 | 双跳转链路无测试 → 抽纯函数 |
| AD-206 | ReaderMode.kt:45 | 候选块无上限 → 设限提前退出 |
| AD-207 | SearchEngines.kt:128 | looksLikeUrl 无跨端向量 → 共享向量 JSON |
| AD-208 | app/build.gradle.kts:127 | 配置分区不明 → 重排 |
| AD-209 | BrowserViewModel.kt:59 | var 未声明单线程意图 → 注释/Atomic |
| AD-210 | ActionContract.kt:8 | 生成物 String vs Instant 双形态 → 转换扩展单源 |

<!-- APPEND-AD -->
---

## 第三部分：Rust 策略核心（RS-001..205，205 项）

统计：P1×10 / P2×40 / P3×155；测试缺口 88 / 健壮性 35 / 安全 26 / 代码质量 34 / 性能 20 / FFI 2。

### 3.1 P2（RS-011..050）

| ID | 位置 | 问题 → 方案 |
|---|---|---|
| RS-011 | src/origin.rs:37-49 | 多冒号 authority 取最后段——非法 origin 被接受 → host 段拒内嵌冒号 |
| RS-012 | src/origin.rs:53-56 | host 仅校验非空——与 C# 口径不一致 → 字符白名单+尾点剥离 |
| RS-013 | src/util.rs:43-48 | extract_hostname query 中 @ 被当 userinfo → 终止符补 ?/# |
| RS-014 | src/util.rs:65-68 | 裸 IPv6 按首个 : 截断 → 整体返回或 None |
| RS-015 | src/matcher.rs:41-59 | 递归深度 32K 帧风险+covers 无记忆化 → 迭代 DP+memo |
| RS-016 | src/matcher.rs:106 | glob_subsumes 无输入上限 → 复用 MAX_GLOB_INPUT |
| RS-017 | src/security_policy.rs:79 | "..":replace 单趟折叠不闭合 → fixpoint 循环 |
| RS-018 | src/font_norm.rs:129-135 | measureText 对 this.font 做 font-family 前缀替换——永不含该前缀空操作 → 解析简写尾部 family 段 |
| RS-019 | src/font_norm.rs:102 | check() 提取 family 含尺寸前缀永不命中 → 剥除前缀 |
| RS-020 | src/timer_prec.rs:80-89 | microseconds=0 除零 → 校验或饱和 |
| RS-021 | src/letterbox.rs:96-108 | 步长 0 除零 → with_config 校验 |
| RS-022 | src/query_strip.rs:140 | 自定义参数含单引号直拼 JS → 转义 |
| RS-023 | src/font_norm.rs:85 | 自定义字体名含 ' 直拼 → 转义 |
| RS-024 | src/webgl_spoof.rs:98-99 | vendor/renderer 含 ' 直拼 → 转义 |
| RS-025 | src/shield.rs:83-89 | putImageData 破坏性写回——双读可检测 → 离屏复制 |
| RS-026 | shield.rs:96 vs webgl_spoof.rs:105 | 两模块都覆盖 VENDOR/RENDERER 口径矛盾 → 单一负责 |
| RS-027 | src/tostring_guard.rs:74-80 | __AEGIS_* 4 个全局常量页面可探测 → Symbol 键收敛 |
| RS-028 | src/per_site_seed.rs:88-92 | 站点种子注入后无人消费死值 → 闭包内驱动 |
| RS-029 | src/policy.rs:129-141 | Allow 映射空凭据——下游必 expired → 拒绝或注入真实参数 |
| RS-030 | src/action_policy.rs:24 | priority 字段从未参与评估 → 排序或删 |
| RS-031 | src/executor.rs:110-121 | raw_input 无长度上限 → 64KB 对齐 |
| RS-032 | src/oracle.rs:88-107 | verify 只遍历 before——after 新增不可检测 → 追加 Mismatch |
| RS-033 | src/broker.rs:118 | create_session 覆盖已有会话无告警 → 拒绝或显式 replace |
| RS-034 | src/broker.rs:307-340 | 空与超长 nonce 无界驻留 → 拒空+128B 上限 |
| RS-035 | src/ffi/broker.rs:215-227 | pending 无过期清理——满后自拒绝服务 → retain 清过期 |
| RS-036 | src/ffi/mod.rs:183-195 | hex_seed_to_bytes 长串截断/非法位置零 → 整体拒绝 |
| RS-037 | src/space_routing.rs:188 | default_workspace 未转义直拼 → serde 转义 |
| RS-038 | src/space_routing.rs:198-212 | 注入 JS 不检查 enabled → 补字段+短路 |
| RS-039 | src/command_bar.rs:116-124 | matches 每查询 3 次 to_lowercase → 预计算缓存 |
| RS-040 | src/js_inject.rs:17-28 | JsInjectable 抽象与实现脱节 → 模块实现 trait |
| RS-041 | src/policy.rs:57-74 | 远程降级路径零覆盖 → 3 用例 |
| RS-042 | src/broker.rs:166-191 | evaluate 无正向用例（现有断言与名相反）→ 补 Allow 链路+更名 |
| RS-043 | src/broker.rs:123-127 | destroy_session 清 nonce 零测试 |
| RS-044 | src/session_state.rs:97-114 | 恶意标题往返零测试 |
| RS-045 | src/action_policy.rs:130-158 | context_contains_token 零直接单测 → 5+ 用例 |
| RS-046 | src/protection_mode.rs:138-196 | pipeline_with_mode 输出内容零测试 → 每模式一测 |
| RS-047 | src/space_routing.rs:161-222 | P28 修复无回归 → 恶意 name 注入回归 |
| RS-048 | src/command_bar.rs:204-267 | P27 修复无回归 → 恶意标题注入回归 |
| RS-049 | src/c_abi/mod.rs:34-38 | 64KB 无 NUL/非 UTF-8 路径零测试 |
| RS-050 | fuzz/fuzz_targets | 仅 fuzz_origin → 新增 5 个 target |

### 3.2 P3（RS-051..205）

| ID | 位置 | 问题 → 方案 |
|---|---|---|
| RS-051 | src/lib.rs:69-91 | pipeline 无测试：阶段标记+确定性 → 2 测 |
| RS-052 | src/lib.rs:97-102 | ABI 版本门禁说明性测试 |
| RS-053 | src/lib.rs:79-90 | format! 9 参拼接 → Vec join |
| RS-054 | src/util.rs:99-128 | userinfo/协议相对/大写 scheme 未测 → 4 用例 |
| RS-055 | src/util.rs:114-128 | extract_host IPv6/纯端口未测 → 4 用例 |
| RS-056 | src/util.rs:73 | extract_host 每次分配 → Cow |
| RS-057 | src/origin.rs:114-188 | 编码 host/全数字/8192 边界未测 → 4 用例 |
| RS-058 | src/origin.rs:37-52 | 端口 u16 边界未测 → 3 用例 |
| RS-059 | src/origin.rs:66 | unwrap_or_default 冗余 → ? 或 if let |
| RS-060 | src/origin.rs:57-77 | 三次 format!+clone → 单次复用 |
| RS-061 | src/matcher.rs | subsumes flat/Any1 交错/unicode 未测 → 5 用例 |
| RS-062 | src/matcher.rs:271-276 | 恰 16384/16385 边界未测 |
| RS-063 | src/matcher.rs:34-35 | 每次 Vec<char> 双分配 → ASCII 快路径 |
| RS-064 | src/matcher.rs:106-110 | subsumes 每次 tokenize → 缓存/Cow |
| RS-065 | src/adblock.rs:157-208 | 端口/大写/裸 host 未测 → 6 用例 |
| RS-066 | src/adblock.rs:119-127 | TLD 条目全网拦截语义未文档化 → 锁定+文档 |
| RS-067 | src/adblock.rs:90 | new 缺 /// → 补 |
| RS-068 | src/adblock.rs:25-30 | 无 Debug → derive |
| RS-069 | src/adblock.rs:105-128 | should_block 分配 → 预归一 API |
| RS-070 | src/query_strip.rs:192-257 | fragment '?'/空 query/无 '=' 未测 → 5 用例 |
| RS-071 | src/query_strip.rs:71-87 | TRACKING_PARAMS 每次 34 String → 静态切片 |
| RS-072 | src/font_norm.rs:149-176 | 自定义字体/通用族完整未测 → 2 用例 |
| RS-073 | src/timer_prec.rs:130-170 | microseconds 边界/jitter 未测 → 2 用例 |
| RS-074 | src/timer_prec.rs:104-118 | mark/measure/timeStamp/rAF 未覆盖 → 注入 |
| RS-075 | src/webgl_spoof.rs:141-174 | 自定义值/Int32Array 回归未测 → 2 用例 |
| RS-076 | src/webgl_spoof.rs:118 | MAX_VIEWPORT_DIMS 每次新数组 → 缓存单实例 |
| RS-077 | src/webgl_spoof.rs:76-131 | getSupportedExtensions 等未伪装 → 补覆盖 |
| RS-078 | src/letterbox.rs:142-185 | roundTo 钳制/step=0 未测 → 2 用例 |
| RS-079 | src/letterbox.rs:111-129 | colorDepth/DPR 未圆整 → 扩展覆盖 |
| RS-080 | src/tostring_guard.rs:93-112 | toLocaleString/可枚举泄漏未测 → 2 用例 |
| RS-081 | src/shield.rs:125-158 | 确定性/Debug 不泄种子未测 → 3 用例 |
| RS-082 | src/shield.rs:78-113 | toBlob/OffscreenCanvas/Audio 未覆盖 → 补或修文档 |
| RS-083 | src/per_site_seed.rs:98-156 | 字符集/空域名未测 → 2 用例 |
| RS-084 | src/per_site_seed.rs:69-74 | 16 次 format! → write! |
| RS-085 | src/ext_proxy.rs:168-210 | P29 转义无回归 → 用例 |
| RS-086 | src/ext_proxy.rs:75-82 | endpoint 不校验 scheme → 校验 |
| RS-087 | src/ext_proxy.rs:114-115 | 仅拦一个域名 → 扩充 |
| RS-088 | src/js_inject.rs:102-167 | 空管线/多语句/跳过顺序未测 → 3 用例 |
| RS-089 | src/decision.rs:1-50 | 全模块零测试 → 3 用例 |
| RS-090 | src/decision.rs:7-12 | 缺 is_allow/deny_code → 补 helper |
| RS-091 | src/policy.rs:52,103 | 缺 /// → 补 |
| RS-092 | src/policy.rs:36-43 | trait 方法无文档 → 补 |
| RS-093 | src/policy.rs:226-247 | Ask 规则映射未测 |
| RS-094 | src/action_policy.rs:161-205 | 默认值/首胜/限制性未测 → 3 用例 |
| RS-095 | src/action_policy.rs:98-101 | find().unwrap() → max_by_key |
| RS-096 | src/action_policy.rs:81-90 | 每次收集 Vec → 单趟 |
| RS-097 | src/executor.rs:135-175 | 全链路/覆盖注册/空白拒未测 → 3 用例 |
| RS-098 | src/executor.rs:100-103 | policy_check 空操作 → 接入或删参 |
| RS-099 | src/executor.rs:131 | validate_schema 无谓 clone → 借用 |
| RS-100 | src/oracle.rs:140-204 | Warning/上界/排序未测 → 4 用例 |
| RS-101 | src/oracle.rs:44-52 | Warning 变体从未构造 → 实现或删 |
| RS-102 | src/oracle.rs:76-81 | Vec::remove(0) O(n) → VecDeque |
| RS-103 | src/capability.rs:152-241 | parse 全量/排序/边界未测 → 5 用例 |
| RS-104 | src/capability.rs:70-81 | 尾斜杠白名单静默失效 → 归一化 |
| RS-105 | src/capability.rs:57 | uses_count pub 可篡改 → 私有化 |
| RS-106 | src/capability.rs:105-107 | register 静默覆盖 → 返回或文档 |
| RS-107 | src/broker.rs:354-549 | 过期/计数/逐出未测 → 4 用例 |
| RS-108 | src/broker.rs:105-110 | 长 ttl 永不逐出 → 文档或 LRU |
| RS-109 | src/session_state.rs:139-218 | 超长/奇数 hex/缺字段未测 → 4 用例 |
| RS-110 | src/session_state.rs:79-84 | 无痕标记损坏降级普通 → 必填缺失 None |
| RS-111 | src/session_state.rs:118-120 | hex_encode 每字节 format! → 查表 |
| RS-112 | src/security_policy.rs:158-190 | 保留名/截断边界/解码未测 → 4 用例 |
| RS-113 | src/security_policy.rs:58-119 | 未剥 RTL 双向控制符 → retain 过滤 |
| RS-114 | src/security_policy.rs:101-112 | 截断在保留名检查后 → 截断后重查 |
| RS-115 | src/security_policy.rs:30-47 | scheme 大小写变体未测 → 2 用例 |
| RS-116 | src/https_only.rs:17-18 | upgrade_counts 无界 → 上限 |
| RS-117 | src/https_only.rs:58-83 | userinfo/尾点未测 → 2 用例 |
| RS-118 | src/https_only.rs:66,77 | 两次 find+全串小写 → 一次+前缀 |
| RS-119 | src/space_routing.rs:231-301 | 大小写不归一/空 pattern 未测 → 4 用例 |
| RS-120 | src/space_routing.rs:80-93 | pattern 未小写归一 → 构造时归一 |
| RS-121 | src/space_routing.rs:88 | ends_with(format!) 分配 → strip_suffix |
| RS-122 | src/command_bar.rs:276-344 | 空集/0 上限/unicode 折叠未测 → 4 用例 |
| RS-123 | src/command_bar.rs:240-243 | JS search 与 Rust 口径不一 → 补或文档 |
| RS-124 | src/update_manifest.rs:211-242 | verify_threshold 白盒分支未测 → 4 用例 |
| RS-125 | src/update_manifest.rs:93-102 | version_tuple 预发布/溢出未测 → 4 用例 |
| RS-126 | src/update_manifest.rs:21-33 | canonical 克隆整个 map → 遍历跳过 |
| RS-127 | src/update_manifest.rs:62 | 浮点 to_string 字节级漂移 → 拒绝或定点 |
| RS-128 | src/update_manifest.rs:169-209 | base64 空串/URL-safe/空白未测 → 3 用例 |
| RS-129 | src/bridge_guard.rs:37-45 | scheme/host 大小写误杀 → ignore_case |
| RS-130 | src/bridge_guard.rs:70-131 | 带端口/组合语义未测 → 2 用例 |
| RS-131 | src/bridge_guard.rs:28 | new 缺 /// → 补 |
| RS-132 | src/ffi/mod.rs:200-465 | FFI 层回归未测 → 3 用例 |
| RS-133 | src/ffi/mod.rs:172-178 | 文档与实现不符 → 修正 |
| RS-134 | src/ffi/mod.rs:183-195 | hex 回归未测 → 3 用例 |
| RS-135 | src/ffi/broker.rs:569-649 | 容量/清理/覆盖未测 → 4 用例 |
| RS-136 | src/ffi/broker.rs:518-531 | 检查与插入原子性 → 注释/测试 |
| RS-137 | src/ffi/broker.rs:553-561 | nonce 32 次 format! → 查表 |
| RS-138 | src/c_abi/mod.rs:221-776 | 畸形 JSON/null 指针/retired 未测 → 5 用例 |
| RS-139 | src/c_abi/mod.rs:50 | FALLBACK .expect() 残留 → 预构造 static |
| RS-140 | src/c_abi/mod.rs:174-188 | broker_new 无限泄漏 → 单例互斥 |
| RS-141 | src/c_abi/navigation.rs:81-154 | 细分错误码被折叠 → 透传 |
| RS-142 | src/c_abi/navigation.rs:105 | 文档错位描述 → 修正 |
| RS-143 | src/c_abi/navigation.rs:1-215 | null 组合/极大值未测 → 3 用例 |
| RS-144 | src/broker.rs:47-54 | 公有字段无逐字段文档 → 补 |
| RS-145 | src/protection_mode.rs:198-268 | 数字别名/空串/Display 未测 → 2 用例 |
| RS-146 | src/protection_mode.rs:107-125 | 全局常量可探测 → 并入 RS-027 |
| RS-147 | tests/vectors.rs:35-65 | action/glob 跨语言向量缺失 → 新增 |
| RS-148 | tests/vectors.rs:67-74 | version_tuple invalid 形态未测 → 扩充 |
| RS-149 | Cargo.toml:4 | edition 2021 → 升级 2024 |
| RS-150 | Cargo.toml:21-29 | 无 [lints] 门禁 → 补 |
| RS-151 | Cargo.toml | 无 release profile 优化 → 补 lto/strip |
| RS-152 | Cargo.toml | 未声明 MSRV → rust-version |
| RS-153 | Cargo.toml:24 | getrandom 0.2 → 评估 0.3 |
| RS-154 | src/policy.rs:194-224 | 短路顺序未测 → 计数 mock |
| RS-155 | src/broker.rs:223-241 | 时钟不可注入 → 抽时间源 |
| RS-156 | src/broker.rs:233 | expires_at==now 边界未锁定 |
| RS-157 | src/broker.rs:16-21 | H-7 注记三处重复 → 统一 |
| RS-158 | src/ffi/broker.rs:337-357 | ttl 无上限 → 设上限或文档 |
| RS-159 | src/ffi/broker.rs:46-53 | session_id 无直接测试 |
| RS-160 | src/ffi/broker.rs:115-130 | evaluate 多次 clone → 借用 |
| RS-161 | src/https_only.rs:39-48 | 往返未直接测试 → 2 用例 |
| RS-162 | src/https_only.rs:45-48 | 放行域名未归一尾点 → 归一化 |
| RS-163 | src/letterbox.rs:113-120 | descriptor 缺失跳过未测 → 脚本断言 |
| RS-164 | src/query_strip.rs:128-132 | pop 隐式约定 → 提取 strip_query |
| RS-165 | src/command_bar.rs:168-174 | filter+take 不短路 → 短路迭代 |
| RS-166 | src/executor.rs:29-47 | 三枚举零测试 → 基础用例 |
| RS-167 | src/policy.rs:18-26 | PolicyVerdict 微补文档 |
| RS-168 | src/matcher.rs:233-240 | flat=true 锁步用例缺失 |
| RS-169 | src/matcher.rs:31 | 16K 按字节语义未文档 → 注释 |
| RS-170 | src/capability.rs:29-47 | pub 方法无 /// → 补 |
| RS-171 | src/broker.rs:35-40 | 50K 常量不可测试注入 → cfg(test) |
| RS-172 | src/session_state.rs:16-17 | 前向兼容策略未单测锁定 → 0/2 两例 |
| RS-173 | src/ffi/mod.rs:151-170 | FFI 入口无前置长度检查 → 64KB |
| RS-174 | src/c_abi/mod.rs:442-480 | destroy 后 consume 清理路径未测 |
| RS-175 | src/c_abi/mod.rs:44-53 | write_response 双份缓冲 → to_vec |
| RS-176 | src/c_abi/mod.rs:55-65 | deny 固定串重复 → 常量化 |
| RS-177 | src/origin.rs:33-36 | '[' 拒绝未锁定 → 1 用例 |
| RS-178 | src/util.rs:16-23 | 非 ASCII 字节用例缺失 |
| RS-179 | src/adblock.rs:100-102 | load 不归一化 → 入库归一 |
| RS-180 | src/adblock.rs:100-102 | 空串/重复条目未测 |
| RS-181 | src/js_inject.rs:42-47 | 宏类型约束未文档化 → 文档 |
| RS-182 | src/policy.rs:77-88 | fail-safe explanation 未断言 |
| RS-183 | src/broker.rs:130-147 | u64::MAX 溢出分支未测 |
| RS-184 | src/ffi/broker.rs:399-413 | 字段比较清单重复两次 → 抽函数 |
| RS-185 | src/ffi/broker.rs:269-282 | approve URL 解析失败未测 |
| RS-186 | src/session_state.rs:117 | hex 工具未统一 → util |
| RS-187 | src/security_policy.rs:137-153 | 非法 UTF-8 回退未测 → "%FF" 用例 |
| RS-188 | src/security_policy.rs:71 | retain 保留 \n\r\t → 剥离或文档 |
| RS-189 | src/protection_mode.rs:44-59 | name/description 全模式未断言 |
| RS-190 | src/origin.rs:8-14 | 字段无逐项 /// → 补 |
| RS-191 | src/decision.rs:18-30 | AuthorizedAction 字段无文档 → 补 |
| RS-192 | src/matcher.rs:254-262 | "***"/"**?" 组合用例缺失 |
| RS-193 | src/command_bar.rs:55-63 | 构造器无上限 → 截断 |
| RS-194 | src/command_bar.rs:177-198 | 8 条目关键字未全测 |
| RS-195 | src/https_only.rs:13-20 | 无 Debug → derive |
| RS-196 | src/space_routing.rs:96-99 | extract_hostname 空 URL 未测 |
| RS-197 | src/update_manifest.rs:107-163 | 5 层 continue 嵌套 → 抽辅助 |
| RS-198 | src/update_manifest.rs:116 | 重复 keyid 语义未测 |
| RS-199 | src/ffi/broker.rs:99-102 | 熵不足路径不可注入 → 参数化 |
| RS-200 | src/c_abi/mod.rs:16-21 | pub 性误导 → 文档或 pub(crate) |
| RS-201 | src/policy.rs:102-116 | action_policy 访问器无测试 |
| RS-202 | src/https_only.rs:59 | 非 http 也整串小写 → 前缀比较 |
| RS-203 | src/broker.rs:57-59 | is_expired 需真实 sleep → Clock trait |
| RS-204 | src/lib.rs:64-68 | pipeline doctest 缺失 → 补 |
| RS-205 | fuzz/Cargo.toml:14 | libfuzzer 未锁 minor → 对齐 |

<!-- APPEND-RS -->
---

## 第四部分：Python/CI/契约/发布链（PY-001..172，172 项）

统计：P1×25 / P2×123 / P3×24；测试缺口 46 / 向量与 schema 34 / CI 34 / 脚本健壮性 25 / 发布链打包 14 / 供应链 5 / 工程化 14。

### 4.1 P2——脚本健壮性（PY-026..043）

| ID | 位置 | 问题 → 方案 |
|---|---|---|
| PY-026 | scripts/sync_versions.py:17 | 无 "=" 行直接 ValueError → 判守卫+行号 |
| PY-027 | scripts/verify_versions.py:37-45 | 8 处下标 KeyError 原始栈 → required/missing 模式 |
| PY-028 | scripts/verify_versions.py:31-32 | 缺文件原始栈 → is_file 检查 |
| PY-029 | scripts/dedup_release_assets.py:22-24 | 手工 argv 无 -h → argparse |
| PY-030 | scripts/codegen-contracts/run.py:26 | subprocess 无 timeout+stderr 丢弃 → 补 |
| PY-031 | scripts/run-security-e2e/run.py:25-26 | 无 timeout+stderr 丢 → 补 |
| PY-032 | scripts/build_review_package.py:110-117 | git 无 timeout → timeout=30 |
| PY-033 | contracts/codegen/verify_bridge_guard.py:67,78 | RUST/KOTLIN 无 is_file 预检 → 补 |
| PY-034 | scripts/verify_cross_end_lists.py:34-81 | 5 个 read_text 无守卫 → _read 帮助函数 |
| PY-035 | verify_cross_end_lists.py:66 | 只 glob *.jpg → 多后缀或反向断言 |
| PY-036 | scripts/verify_xaml_resources.py:19 | 只匹配 FindResource 字面 → 正则扩 TryFindResource/索引器 |
| PY-037 | validate_release.py:18-25 | AST 检查仅 legacy 子树 → 扩 scripts/contracts/release |
| PY-038 | validate_release.py:63-65 | 资产清单与 CI 平行维护 → 抽共享清单文件 |
| PY-039 | release/write_checksum_json.py:18 | 整文件进内存 → 1MiB 分块 |
| PY-040 | scripts/gen_jsapi_schema.py:77-78 | defaults 遍历空操作——必填性失真 → 回填 required |
| PY-041 | gen_jsapi_schema.py:27 | 指向归档栈 api_bridge → 标注或建 C# 桥 schema |
| PY-042 | contracts/codegen/verify_contract_compatibility.py:56-59 | 只查文件存在不比内容 → 重生成 diff |
| PY-043 | verify_bridge_guard.py:33-40 | REQUIRED_SINKS 手工副本 → Rust 导出单源 |

### 4.2 P2——CI（PY-044..068）

| ID | 位置 | 问题 → 方案 |
|---|---|---|
| PY-044 | .github/workflows/ci.yml:12 | 无 concurrency → 加 group+cancel |
| PY-045 | contracts.yml:3 | 无 concurrency → 同修 |
| PY-046 | android-quality.yml:7 | 无 concurrency → 同修 |
| PY-047 | core-rust.yml:2 | 无 concurrency → 同修 |
| PY-048 | supply-chain.yml:2 | 无 concurrency → 同修 |
| PY-049 | agent-redteam.yml:2 | 无 concurrency → 同修 |
| PY-050 | compat.yml:13 | 无 concurrency → 加 group |
| PY-051 | native-policy-artifacts.yml:4 | 无 concurrency → 同修 |
| PY-052 | contracts.yml:97 | rust-conformance 无 rust-cache → 加 |
| PY-053 | core-rust.yml:19 | 无 rust 缓存 → 加 |
| PY-054 | release-core.yml:68 | build 无 rust 缓存 → 加 |
| PY-055 | release-windows.yml:43 | Windows DLL 无 rust 缓存 → 加 |
| PY-056 | release-android.yml:47 | ndk 无 rust 缓存 → 加 |
| PY-057 | native-policy-artifacts.yml:21,70 | 两 job 无 rust 缓存 → 加 |
| PY-058 | contracts.yml:108 | 无 NuGet 缓存 → cache: true |
| PY-059 | release-windows.yml:40 | 无 NuGet 缓存 → 加 |
| PY-060 | ci.yml:41 | setup-python 无 pip 缓存 → 加 |
| PY-061 | contracts.yml:17 | 无 pip 缓存（3 处）→ 加 |
| PY-062 | contracts.yml:133 | android job 无 Gradle 缓存 → 复制配置 |
| PY-063 | ci.yml:43 | Python 版本矩阵漂移 3.12/3.14 → 统一 |
| PY-064 | contracts.yml:26 | 50 行内联 heredoc → 抽 scripts/verify_vectors.py |
| PY-065 | android-quality.yml:51 | 依赖 runner 预装 Python → setup-python |
| PY-066 | android-quality.yml:64 | detekt 报告只传 app → 四模块聚合 |
| PY-067 | compat.yml:40 | stderr 全吞 → tee 保留 |
| PY-068 | compat.yml:50 | 声称归档基线实际不回仓 → 实现或改注释 |

### 4.3 P2——契约向量（PY-069..102）

| ID | 位置 | 问题 → 方案 |
|---|---|---|
| PY-069 | vectors/url-origin-invalid.json | 缺 IPv6 环回向量 → 增 |
| PY-070 | 同上 | 缺 IPv4-mapped IPv6 向量 → 增 |
| PY-071 | 同上 | 缺整数编码 IP 向量 → 增 |
| PY-072 | 同上 | 缺十六进制/简写 IP 向量 → 增两条 |
| PY-073 | 同上 | 缺尾点主机向量 → 增 |
| PY-074 | 同上 | 缺非 DNS 字符向量 → 增 |
| PY-075 | 同上 | 缺端口 :0/:65536 向量 → 增两条 |
| PY-076 | 同上 | 缺无密码 userinfo 变体 → 增 |
| PY-077 | 同上 | 缺 Tab/CR 控制字符变体 → 增两条 |
| PY-078 | 同上 | 超长 URL 动态样本未兑现 → 生成用例 |
| PY-079 | vectors/url-origin-valid.json | 缺大写归一化向量 → 增 |
| PY-080 | 同上 | 缺显式端口归一化向量 → 增两条 |
| PY-081 | 同上 | 缺 punycode/IP 字面量向量 → 增两条 |
| PY-082 | vectors/update-manifest-invalid.json | 缺非法 base64 签名向量 → 增 |
| PY-083 | 同上 | 缺未信任 key_id 向量 → 增 |
| PY-084 | 同上 | 缺无时区过期时间向量 → 增 |
| PY-085 | 同上 | 缺制品级非法向量 → 增四条 |
| PY-086 | 同上 | 缺顶层 const 破坏向量 → 增两条 |
| PY-087 | vectors/update-manifest-valid.json | 缺预发布+beta channel 向量 → 增 |
| PY-088 | 同上 | 缺 threshold=1 单钥向量 → 增两条 |
| PY-089 | vectors/approvals-replay-and-expiry.json | 缺换 scope 重放向量 → 增 |
| PY-090 | 同上 | 缺 expires_at==now/缺 nonce 向量 → 增两条 |
| PY-091 | vectors/native-navigation-decision.json | 缺消费点 KillSwitch 向量 → 增 |
| PY-092 | 同上 | 缺 generation 失配向量 → 增 |
| PY-093 | 同上 | 缺 native-required 黑名单 deny 向量 → 增 |
| PY-094 | schemas/action.schema.json | 无向量文件 → 新建两向 |
| PY-095 | schemas/capability.schema.json | 无向量文件 → 新建 |
| PY-096 | schemas/audit-event.schema.json | 无向量文件 → 新建 |
| PY-097 | schemas/approval.schema.json:9 | method 词表与 action 不一致 → 收敛 |
| PY-098 | schemas/capability.schema.json | 实现超出契约（预算字段）→ 补字段或注释 |
| PY-099 | codegen/generate_csharp.py:19-30 | number 降级 object/optional 必填 → 按 required 区分+守卫 |
| PY-100 | codegen/generate_kotlin.py:19-30 | 同 PY-099 对偶修 |
| PY-101 | shared/release.json:9-11 | 声明 arm64 无构建 → 删或补 |
| PY-102 | shared/release.json | 仅对账 2 字段——其余 14 字段无 schema 校验 → jsonschema 校验 |

### 4.4 P2——脚本单测缺口（PY-103..148）

| ID | 位置 | 问题（每个测试一项） |
|---|---|---|
| PY-103 | sync_versions.py:11 | load_properties 单测（注释/空行/值含=） |
| PY-104 | sync_versions.py:22 | replace_assignment 单测（count/缩进/引号） |
| PY-105 | sync_versions.py:32 | replace_xml_value 单测（缺失抛错/首匹配） |
| PY-106 | verify_versions.py:16 | expected_xml_value 单测 |
| PY-107 | verify_versions.py:21 | expected_assignment 单测 |
| PY-108 | dedup_release_assets.py:33-54 | 去重主逻辑三用例 |
| PY-109 | gen_jsapi_schema.py:34 | _doc_first_line 单测 |
| PY-110 | gen_jsapi_schema.py:41 | build_schema 单测 |
| PY-111 | gen_jsapi_schema.py:66 | mixin 提取回归测试 |
| PY-112 | build_review_package.py:135 | _match_excluded 表驱动 8 用例 |
| PY-113 | build_review_package.py:145 | collect_sources 单测 |
| PY-114 | build_review_package.py:107 | git_commit_and_head 降级单测 |
| PY-115 | build_review_package.py:238 | stamp_readme 两用例 |
| PY-116 | build_review_package.py:292 | check_reviewed 三类报告单测 |
| PY-117 | verify_xaml_resources.py:23 | collect_keys 单测 |
| PY-118 | verify_xaml_resources.py:39-44 | 缺失键定位单测（行号） |
| PY-119 | verify_cross_end_lists.py:33 | wallpapers_from_asset_scheme 单测 |
| PY-120 | verify_cross_end_lists.py:42 | wallpapers_from_start_html 单测 |
| PY-121 | verify_cross_end_lists.py:53 | wallpapers_from_kotlin 单测 |
| PY-122 | verify_cross_end_lists.py:69,78 | 引擎表解析单测 |
| PY-123 | validate_release.py:40-44 | 锁文件门禁单测（先抽函数） |
| PY-124 | validate_release.py:48-65 | C# 关键文件断言单测 |
| PY-125 | generate_csharp.py:19 | cs_type 表驱动 5 用例 |
| PY-126 | generate_csharp.py:33 | generate 快照断言 |
| PY-127 | generate_csharp.py:50 | contract_name 用例 |
| PY-128 | generate_csharp.py:59 | 陈旧清理回归（锁 PY-016） |
| PY-129 | generate_kotlin.py:19 | kt_type 表驱动 |
| PY-130 | generate_kotlin.py:44 | 尾逗号锁定 |
| PY-131 | verify_contract_compatibility.py:21 | contract_name 三副本一致性测试 |
| PY-132 | verify_bridge_guard.py:50 | norm 单测 |
| PY-133 | verify_bridge_guard.py:112 | _first_diff 单测 |
| PY-134 | verify_bridge_guard.py:27 | Kotlin 占位符归一化端到端 |
| PY-135 | analyze_action_catalog.py:39 | 重复名检测单测 |
| PY-136 | analyze_action_catalog.py:46 | scope 冲突检测单测 |
| PY-137 | analyze_action_catalog.py:55,59 | audit/fixtures 缺失检测单测 |
| PY-138 | analyze_action_catalog.py:17 | 坏 yaml 解析路径单测 |
| PY-139 | release/write_checksum_json.py:9 | build_manifest 三用例 |
| PY-140 | release/verify_checksum_json.py:14 | verify_manifest 用例 |
| PY-141 | verify_checksum_json.py:49-56 | 篡改/越界/重复三拒绝单测 |
| PY-142 | release/update_verifier.py:30 | canonical_unsigned 字节精确断言 |
| PY-143 | update_verifier.py:43 | _version_tuple 四用例（含预发布序） |
| PY-144 | update_verifier.py:53 | verify_manifest 四用例 |
| PY-145 | update_verifier.py:65 | 回滚拒绝单测 |
| PY-146 | release/native_artifact_manifest.py:53 | 三类 ValueError 单测 |
| PY-147 | native_artifact_manifest.py:100-103 | --verify 拒绝单测 |
| PY-148 | release/build_metadata.py:33-37 | 缺属性 SystemExit 单测 |

### 4.5 P3——工程化/打包链/口径（PY-149..172）

| ID | 位置 | 问题 → 方案 |
|---|---|---|
| PY-149 | pyproject.toml:1 | 无 pytest 配置 → testpaths |
| PY-150 | pyproject.toml:6 | line-length=120 与 ignore E501 并存 → 收口 |
| PY-151 | pyproject.toml:5 | 无 target-version → py312 |
| PY-152 | pyproject.toml:9 | 排除不存在目录 → 删 |
| PY-153 | ci.yml:59,64 | ruff ignore 三处平行维护 → per-file-ignores |
| PY-154 | pyproject.toml:15 | I001 永久忽略 → scripts/contracts 重启 |
| PY-155 | ci.yml:74-85 | mypy 无配置文件 → 承载清单 |
| PY-156 | ci.yml:72 | bandit skip 仅在命令行 → 配置文件 |
| PY-157 | .github/ | 无 dependabot → 三生态周频 |
| PY-158 | requirements-dev.txt:6 | dev 锁含构建工具 → 拆 requirements-ci |
| PY-159 | requirements-dev.txt:1 | dev 无 hash 锁 → generate-hashes |
| PY-160 | windows/packaging/build-windows.ps1:15 | 引用退役 PyInstaller 管线 → 删/归档 |
| PY-161 | validate_release.py:30 | 门禁解析死 MSIX 模板 → 随上移除 |
| PY-162 | docs/release/AegisSetup.iss:1 | Python 时代死脚本 → 删/归档 |
| PY-163 | AegisSetup-CSharp.iss:17-36 | 三个安装器资产闲置 → 补引用 |
| PY-164 | AegisSetup-CSharp.iss:34 | 无 SetupLogging → 补开关 |
| PY-165 | AegisSetup-CSharp.iss:45 | 无 WebView2 检测 → [Code] Check |
| PY-166 | generate_sbom.py:31-36 | SBOM 缺字段+测试向量当输入 → 真实依赖或注明 |
| PY-167 | release-threat-model.md:13-14 | 声称在用门禁实际未接线 → 接线或改文档 |
| PY-168 | scripts/e2e-android-search.sh:6 | set 缺 -e → set -euo |
| PY-169 | e2e-android-search.sh:45,57 | 截屏落 /tmp 陷阱 → mktemp |
| PY-170 | e2e-android-search.sh:5 | REQUIRES_DEVICE 注释未实现 → 实现或删 |
| PY-171 | supply-chain.yml:26-30 | cargo audit 三处重复 → 收敛单处 |
| PY-172 | native-policy-artifacts.yml:4-9 | 仅 PR 触发 → 补 push paths |

<!-- APPEND-PY -->
---

## 第五部分：Web 资产与文档（WB-001..100，100 项）

统计：P1×9 / P2×27 / P3×64；Web 资产质量 22 / JS 测试 40 / 无障碍 11 / 文档 21 / 一致性门禁 6。

### 5.1 P2（WB-010..030）

| ID | 位置 | 问题 → 方案 |
|---|---|---|
| WB-010 | windows/.../UrlNormalizer.cs:23 | C# 引擎表 5 引擎与三端 4 引擎漂移无门禁 → 纳入对账脚本 |
| WB-011 | verify_cross_end_lists.py:14 | 壁纸对账漏 C# NtpAssets 第 5 份清单 → 增列 |
| WB-012 | .github/workflows/ci.yml:103 | snake.test.js 不在任何 CI → 追加 step |
| WB-013 | shared/shell/start.main.js:309 | 6 处空 catch 全吞 → Host.jsError 留痕 |
| WB-014 | shared/shell/start.js:118 | android 白名单缺 bookmarks——死分支 → 补或删并注明 |
| WB-015 | start.import.js:101 | 导入统计管道无回归测试 → mock Host 测试 |
| WB-016 | start.snake.js:391 | turn() 反向拒绝无测试 |
| WB-017 | start.snake.js:77 | freeCell() 无测试 |
| WB-018 | start.snake.js:181 | step() 撞墙/撞自身无测试 |
| WB-019 | start.snake.js:186 | 吃食 +10/奖励 +50 无测试 |
| WB-020 | start.import.js:185 | 15s 超时兜底无回归 |
| WB-021 | start.js:36 | Host.kind() 三端判定无测试 |
| WB-022 | start.js:37 | Host.has() 白名单语义无测试 |
| WB-023 | start.js:63 | Android 引擎解析回退无测试 |
| WB-024 | start.js:23 | csCall 响应关联无测试 |
| WB-025 | start.main.js:150 | 未知壁纸整体 no-op 无测试 |
| WB-026 | start.main.js:157 | 单引号 %27 编码无测试 |
| WB-027 | start.html:59 | 导入向导无焦点管理 → 聚焦+陷阱+归还 |
| WB-028 | start.html:30 | engineMenu 无 role=menu → 补+aria-controls |
| WB-029 | start.css:1 | 全文件 0 处 focus 样式 → :focus-visible |
| WB-030 | CHANGELOG.md:41 | "未发布"节错位重复 → 并入或删除 |

### 5.2 P3（WB-031..100）

| ID | 位置 | 问题 → 方案 |
|---|---|---|
| WB-031 | docs/runbooks/release-checklist.md:16 | 已修复项仍标待定位 → 更新 |
| WB-032 | docs/product/privacy-defaults.md:12 | 宣称加密实际明文 → 如实描述 |
| WB-033 | CONTRIBUTING.md:71 | 引用不存在章节 → 改指 ADR 索引 |
| WB-034 | CLAUDE.md:63 | 文件地图缺正典栈路径 → 补 |
| WB-035 | windows/README.md:11 | 硬编码测试计数过期 → 移除计数 |
| WB-036 | supported-features.md:44 | 已知缺口三项均已实现 → 重核 |
| WB-037 | start.js:18 | csCall 无超时上限 → TTL 清理 |
| WB-038 | NtpBridge.cs:143 | jsError 仅取 args[0] 丢堆栈 → 拼接再入日志 |
| WB-039 | NtpBridge.cs:167 | ArgInt 两分支失败语义不一致 → 统一 null |
| WB-040 | HostWebView.cs:243 | IsTrustedChromeOrigin 零调用 → 删/接线（同 CS-069） |
| WB-041 | start.snake.js:1 | 缺 'use strict'（两文件）→ 补 |
| WB-042 | start.snake.js:2 | 4 空格缩进残留 → 重排 |
| WB-043 | start.css:11 | 无效 transition → 删或交叉淡入 |
| WB-044 | start.main.js:52 | 引擎菜单无方向键导航 → 补 |
| WB-045 | start.main.js:107 | Escape 不关闭菜单 → 补 |
| WB-046 | start.html:87 | 音效开关无 aria-pressed → 同步 |
| WB-047 | start.css:104 | 白字对比度可能低于 AA → 提高并实测 |
| WB-048 | start.main.js:247 | ☆ 文案为 Windows 专属 → 按平台差异化 |
| WB-049 | start.html:75 | Ctrl+L 提示与实际不符 → 改文案 |
| WB-050 | start.html:36 | autofocus 弹软键盘 → pointer:fine 条件 |
| WB-051 | start.html:71 | 壁纸圆点 div 手写语义 → 原生 button |
| WB-052 | start.html:14 | CSP 无 report-uri → 加观测面 |
| WB-053 | shared/jsapi-schema.json:5 | C# NtpBridge 协议无 schema → 生成 |
| WB-054 | validate_release.py:63 | 不校验 csproj 排除 snake.test.js → 增断言 |
| WB-055 | start.import.js:119 | 未选来源静默关闭 → 提示 |
| WB-056 | start.import.js:217 | running 态 Escape 关闭 → 忽略或确认 |
| WB-057 | start.main.js:138 | 魔法延时散落三文件 → 常量集中 |
| WB-058 | docs/KNOWLEDGE_BASE.md:83 | 基线 v0.3.0 严重脱节 → 更新 |
| WB-059 | ADR-007:2 | 状态未标注 D1 被取代 → 头部注记 |
| WB-060 | ADR-009:55 | 目标树与落地差异未注记 → 补 |
| WB-061 | repo-health.md:5 | 2026-08-14 报告绝对路径+已修项仍列 top → 标注历史 |
| WB-062 | agent/README.md:29 | 引用不存在 prompts/ → 删/补 |
| WB-063 | fixtures README.md:1 | 目录仅 README 无数据 → 补或注明内联 |
| WB-064 | KNOWN_DEFECTS.md:34 | 缺 BUG-009 登记行 → 补（同 SP-039） |
| WB-065 | windows-run-guide.md:6 | 缺 dotnet test 与原生核联调 → 补 |
| WB-066 | windows-run-guide.md:16 | cwd 口径不一致 → 统一 |
| WB-067 | release-checklist.md:30 | v1.0.0 示例脱节 → 占位符 |
| WB-068 | release-checklist.md:42 | 引用不存在 runbook → 落地或改指 |
| WB-069 | device-validation.md:23 | 引用不存在 runbook → 同上 |
| WB-070 | SECURITY.md:29 | 危险 API 行缺 Process.Start/FFI → 补 |
| WB-071 | CONTRIBUTING.md:18 | 命名规范缺 C# → 补 |
| WB-072 | CONTRIBUTING.md:20 | 依赖政策缺双栈 → 补 |
| WB-073 | supported-features.md:15 | 引擎清单与 C# 实际不符 → 更新（同 WB-010） |
| WB-074 | start.snake.js:395 | turn 队列上限 3 无测试 |
| WB-075 | start.snake.js:197 | bonus +50/ttl 过期无测试 |
| WB-076 | start.snake.js:195 | 提速曲线下限 70 无测试 |
| WB-077 | start.snake.js:98 | best 即时更新无测试 |
| WB-078 | start.snake.js:101 | localStorage 往返无测试 |
| WB-079 | start.snake.js:110 | setState 四态文案无测试 |
| WB-080 | start.snake.js:142 | die() 粒子无测试 |
| WB-081 | start.snake.js:257 | DIG 位图覆盖无测试 |
| WB-082 | start.main.js:82 | renderEngineMenu 选中态无测试 |
| WB-083 | start.main.js:56 | 空引擎表隐藏分支无测试 |
| WB-084 | start.main.js:128 | go() 空输入短路无测试 |
| WB-085 | start.main.js:129 | _searchBusy 防抖无测试 |
| WB-086 | start.main.js:261 | host 提取失败回退无测试 |
| WB-087 | start.main.js:257 | 前 8 书签截断无测试 |
| WB-088 | start.main.js:313 | 有界重试无测试 |
| WB-089 | start.main.js:221 | parseInt 归一无测试 |
| WB-090 | start.import.js:146 | renderDone 三态文案无测试 |
| WB-091 | start.import.js:53 | renderPick 无来源分支无测试 |
| WB-092 | start.import.js:126 | limitSel 默认 500 无测试 |
| WB-093 | start.js:27 | 回调异常不影响其他 pending 无测试 |
| WB-094 | start.html:15 | CSP 全局放行 file: → 注释+评估差异化 |
| WB-095 | start.js:64 | Android 回退表第三份名单 → 跨端断言 |
| WB-096 | start.main.js:333 | submit+click 双路径防重放无锁定测试 |
| WB-097 | compat-baselines/README.md:3 | 承诺基线文件实际不存在 → 修正说明 |
| WB-098 | start.main.js:28 | 默认壁纸三处硬编码 → 一致性断言 |
| WB-099 | CHANGELOG.md:104 | beta.1-15 无记录无说明 → 注明起点 |
| WB-100 | start.html:84 | 得分 chip 无 aria-live → 补 |

<!-- APPEND-WB -->
---

## 第六部分：补充盲区（SP-001..138，138 项）

统计：P1×8 / P2×57 / P3×73；测试缺口 33 / 文档修正 63 / 代码修复 16 / 配置 12 / 归置 12 / 卫生 9。

### 6.1 P2（SP-009..065）

| ID | 位置 | 问题 → 方案 |
|---|---|---|
| SP-009 | agent/tests/redteam_e2e_test.py:28 | ALLOWED_INTENTS 与目录双源 → yaml 动态构建 |
| SP-010 | 同上:45 | 允许 scope 硬编码 → 目录推导 |
| SP-011 | 同上:49-52 | 工具哈希未批准分支无测试 → 用例 |
| SP-012 | 同上:33,41-53 | consumed_nonces 无锁+无并发测试 → Lock+8 线程用例 |
| SP-013 | 同上:24-54 | 无 revoke() 语义测试 → 增加 |
| SP-014 | 同上:30-31 | policy_version 存而不用 → 比对分支+测试 |
| SP-015 | 同上:14-21 | 缺 session_id——跨会话重放未覆盖 → 字段+测试 |
| SP-016 | 同上 | 缺 max_bytes 预算 → 字段+超限测试 |
| SP-017 | 同上:36-54 | 无 expires_at 过期判定 → 分支+测试 |
| SP-018 | agent/tests/redteam_test.py:30-32 | 断言仅查一次子串 → 解析全部 JSON 块 |
| SP-019 | prompt-injection-fixtures/README.md:29-38 | STDIO 参数注入向量无 e2e → canonical_parameters 校验+用例 |
| SP-020 | tool-result-poisoning-fixtures/README.md:6-17 | 结果投毒向量无 e2e → 新增测试 |
| SP-021 | redteam_test.py:35-41 | 目录 schema 完整性未校验 → 断言 |
| SP-022 | contracts/policy/action-catalog.yaml:10-24 | 两条 action 均无 budget 字段 → 补+断言 |
| SP-023 | redteam_test.py:40-41 | fixtures 引用存在性未校验 → 断言 |
| SP-024 | release/tools/verify_manifest/verify_manifest.py:26-27 | 坏 JSON traceback → try/except+exit 2 |
| SP-025 | 同上 | main() 三退出码路径无测试 → 单测 |
| SP-026 | verify_provenance.py:22 | 目录不存在 traceback → is_dir 检查 |
| SP-027 | 同上:31 | subprocess 无 timeout → 120s+捕获 |
| SP-028 | 同上:32-33 | 失败信息不含 stderr → 附摘要 |
| SP-029 | 同上:22-24 | 仅迭代顶层——子目录跳过 → recursive |
| SP-030 | 同上 | 无测试 → mock subprocess 单测 |
| SP-031 | release/test-vectors/release-verify.json | 8 向量无执行消费者 → 元一致性门禁 |
| SP-032 | release/runbooks/security-release.md:15-29 | 缺 cosign verify-blob 步骤 → 增 |
| SP-033 | 同上:29 | SBOM 校验无承载 → 补命令或注明 |
| SP-034 | scripts/bootstrap-dev-environment/run.py:21 | _check 忽略 returncode → 检查 |
| SP-035 | 同上:28-32 | 不校验版本下限 → 解析主版本 |
| SP-036 | 同上 | 缺 Node.js 检查 → 增 |
| SP-037 | 同上:15-23 | _check 无单测 → 三分支覆盖 |
| SP-038 | scripts/migrate-profile-data/run.py:14-22 | 骨架恒返回 0 虚假成功 → 专用退出码 |
| SP-039 | tests/KNOWN_DEFECTS.md:7-16 | BUG-009 被引用未登记 → 补行 |
| SP-040 | 同上:62 | BUG-014 被断言未登记 → 补行 |
| SP-041 | 同上:24 | 单元层口径过时 → 更新 C# 主 |
| SP-042 | start_page.test.mjs:93-94 | BUG-005 断言读 legacy spec → 补 csproj 断言 |
| SP-043 | start_page.test.mjs | BUG-013 无静态回归 → 补 Manifest 断言 |
| SP-044 | tests/ | 缺陷库与测试引用互检缺失 → lint 测试 |
| SP-045 | ADR-007:3 | 状态无取代注记 → 补 |
| SP-046 | ADR-008:5 | 交叉引用指错对象 → 改指 |
| SP-047 | ADR-009:26-27 | D1 改名决策结局未回写 → 补记录 |
| SP-048 | ADR-009:98-103 | M4 清单完成情况未记录 → 逐项标注 |
| SP-049 | docs/DESIGN.md:1-4 | Apple 设计规范误放 docs 根 → 移/删+同步引用 |
| SP-050 | build_review_package.py:54 | DESIGN.md 列为事实来源 → 修正 |
| SP-051 | security-testing-guide.md:91 | 列死脚本 → 改现役 |
| SP-052 | 同上:67 | 源码表列不存在文件 → 删/改 |
| SP-053 | compat-baselines/README.md:3-5 | 承诺归档不存在 → 修正说明 |
| SP-054 | KNOWLEDGE_BASE.md:83 | 基线版本写死 → 引用单源 |
| SP-055 | AegisSetup-CSharp.iss:2-3 | 头注称并存与单轨矛盾 → 更新 |
| SP-056 | docs/release/AegisSetup.iss:6 | 死脚本硬编码版本 → 删/归档（同 PY-162） |
| SP-057 | dist/ | 三代陈旧安装包混杂 → 清理 |
| SP-058 | dist/build-metadata.json:6 | 双份元数据互矛盾 → 删旧副本 |
| SP-059 | docs/ | 12+ 份带日期报告散落根目录 → 统一移 docs/audit/ |
| SP-060 | docs/ | 历史报告无时代横幅 → 逐份加横幅 |
| SP-061 | security-testing-guide.md:3,83 | 版本/制品表全不符 → 更新或标历史 |
| SP-062 | agent/README.md:3 | 蓝图并入指向过时文档 → 改指 |
| SP-063 | KNOWLEDGE_BASE.md:97 | R8 状态与 25.5 节矛盾 → 改 ✅ |
| SP-064 | agent/local-ipc/identity.md:16-17 | 引用归档 mcp.py 为现役 → 标注 |
| SP-065 | resource-budget-fixtures/README.md:12 | 常量归属 legacy 未标注 → 补标注 |

### 6.2 P3（SP-066..138）

| ID | 位置 | 问题 → 方案 |
|---|---|---|
| SP-066 | redteam_e2e_test.py | deny 不消费 nonce 无测试 |
| SP-067 | 同上:14-21 | 字段集与 schema 漂移 → 对齐或校验 |
| SP-068 | 同上 | 返回裸字符串与 Decision 不对齐 → 结构化 |
| SP-069 | agent/tests | pytest 收集无配置 → testpaths/conftest |
| SP-070 | agent/redteam/ | fixtures 无机器可读 .json → 抽向量文件 |
| SP-071 | agent/README.md:29 | 列不存在的 prompts/ → 删（同 WB-062） |
| SP-072 | ADR-004:5 | 引用归档 mcp.py 无标注 → 补注记 |
| SP-073 | ADR-005:3 | 无 amended-by 注记 → 补 |
| SP-074 | ADR-008:18 | 防御表列冻结栈未标注 → 补标注 |
| SP-075 | ADR-009:3 | "落地但验收未完"自相矛盾 → 拆分表述 |
| SP-076 | docs/adr/ | 无 ADR 索引 → 新增索引页 |
| SP-077 | ADR-006:27-31 | 外链无核验日期 → 注明 |
| SP-078 | verify_manifest.py:29 | threshold 双写 → 一致性断言（过渡） |
| SP-079 | security-release.md:19 | min_version 无示例 → 补 |
| SP-080 | 同上:35 | 灰度无承载定义 → 注明手动 |
| SP-081 | bootstrap-dev-environment:26-39 | 失败无安装指引 → 附入口 |
| SP-082 | 同上 | 缺 ISCC 探测 → 可选检查 |
| SP-083 | 同上:31 | python 恒成功形同自检 → 查 PATH |
| SP-084 | migrate-profile-data:14-22 | 无 CLI 参数骨架 → argparse 预留 |
| SP-085 | 同上:16-21 | 4 步骤无回归保护 → 断言 |
| SP-086 | KNOWN_DEFECTS.md:34-37 | 行列语义错位 → 重排（SP-002 细化） |
| SP-087 | 同上:7-16 | BUG-010 缺号无说明 → 补登/注记 |
| SP-088 | 同上:25 | 跳过退出码语义未注明 → 注明 |
| SP-089 | dist/*.ps1 | 4 份调试脚本无版本管理 → 移 scripts/ 或删 |
| SP-090 | dist/edge-screen.png | 1.3MB 调试截图 → 删 |
| SP-091 | dist/SHA256SUMS*.json | 三代并存 → 随 SP-057 清理 |
| SP-092 | dist/*sbom*.json | 空 SBOM 被 latest 流程复制 → 重生成或删 |
| SP-093 | .gitignore:3-7,79 | 指向不存在 assets/ 的死规则 → 删 |
| SP-094 | .gitignore:49-50 | 死目录规则 → 删 |
| SP-095 | .gitignore:53-54,70-71 | 冗余规则 → 删 |
| SP-096 | .gitignore:72 | 三重冗余 → 删 |
| SP-097 | .gitignore:27-32 | 缺现代缓存条目 → 补齐 |
| SP-098 | pyproject.toml:9 | 死排除项 → 删（同 PY-152） |
| SP-099 | aegis-专家评审包/ | 空目录残留 → 删除 |
| SP-100 | 同上 | 无 README 说明 → 随上处置 |
| SP-101 | KNOWLEDGE_BASE.md:92 | R2 状态过时 → 改 ✅ |
| SP-102 | shared/jsapi-schema.json | 无栈归属标注 → 加头注 |
| SP-103 | KNOWLEDGE_BASE.md:94 | R5 状态过时 → 改 ✅ 链接 |
| SP-104 | 同上:146 | 历史内容无时代标注 → 节首标注 |
| SP-105 | 同上:492 | 硬编码字节数 → 改口径 |
| SP-106 | docs/sbom-aegis-2026.json | SBOM 首组件为退役栈 → 归档/删 |
| SP-107 | docs/release/b4-enable-notes.md:9-12 | 描述已失效结构 → 加历史说明 |
| SP-108 | 同上:5 | 字节数证存在 → 改提交号 |
| SP-109 | agent-sitemap.example.json:3 | legacy 语义无指引 → 补注 |
| SP-110 | docs/threat-feed-mirror-plan.md:5 | 依据归档文件为现状 → 标注 |
| SP-111 | docs/obfuscation-isolation-design.md:2-5 | 混淆链失去对象 → 标注被取代 |
| SP-112 | privacy-defaults-audit.md:4 | 对照对象已归档 → 加横幅 |
| SP-113 | audit-report.md:5 | 现在时描述归档栈 → 加横幅 |
| SP-114 | audit-2026.md:2 | 无时代标注 → 加横幅 |
| SP-115 | code-structure-review-2026.md:4 | 路径已不存在 → 加横幅 |
| SP-116 | code-quality-assessment.md:3 | 基于 legacy 证据 → 加横幅 |
| SP-117 | expert-audit-report.md:3 | 无时代标注 → 加横幅 |
| SP-118 | optimization-plan.md:2 | 基于 legacy 前提 → 加横幅 |
| SP-119 | toolchain/tech-evolution-plan.md:2 | 结论已被 ADR 否决 → 加横幅 |
| SP-120 | tauri-migration-report*.md:2 | 调研已终结 → 归档标注 |
| SP-121 | pytauri-*.md:2 | 路线已失效 → 归档标注 |
| SP-122 | rust-desktop-landscape-2026.md:2 | 结论过时 → 归档标注 |
| SP-123 | source-study 等 3 份 | 本机路径+过时前提 → 归档标注 |
| SP-124 | open-source-browser-audit*.md:2 | 三批审计散落 → 移 docs/audit/ |
| SP-125 | architecture-audit-2026-08-22/31.md:2 | 位置违反先例 → 移 docs/audit/ |
| SP-126 | audit-search 等 5 份 | 同上 → 移 docs/audit/ |
| SP-127 | docs/ | 移动后缺索引 → 新增 README |
| SP-128 | quality-reports/valknut 双份 | 同源报告并存 → 删一或标注 |
| SP-129 | expert-audit-report.md:5-7 | 外部评分工具无获取说明 → 补来源 |
| SP-130 | architecture-audit-2026-08-31.md:1-5 | 评分基于双栈期无指引 → 加后续指引 |
| SP-131 | dist/latest-release/ | 两版并存 latest 失真 → 清理 |
| SP-132 | dist/native-policy/windows | 仅 x64 与声明缺口对应 → 随 SP-005 同步 |
| SP-133 | .gitignore:24-25 | 崩溃目录规则未核实 → 核实修正 |
| SP-134 | prompt-injection-fixtures/README.md:13 | 无向量用途声明 → 补一句 |
| SP-135 | start_page.test.mjs:25-30 | syntaxOk 未含 chrome.webview → 补 |
| SP-136 | security-release.md:9-13 | 签名无 keyless 说明 → 补 |
| SP-137 | tests/ | 无 README 说明分层 → 增一页 |
| SP-138 | security-testing-guide.md:184-185 | 本机绝对路径 → 改相对 |

---

## 第七部分：执行批次日志（随执行更新）

| 批次 | 提交 | 范围 | 项数 | 验证 |
|---|---|---|---|---|
| 先导 | 82a04b2 (beta.44) | RS：matcher glob_subsumes 可靠性修复+边界测试 8 项 | 1 | cargo test 197+clippy 0 |
| R1 | 3d28097 (beta.45) | RS-001..010 Rust P1 缺陷修复+回归测试 | 10 | cargo test 209+clippy 0+fmt |
| C1 | 8af2d26 (beta.46) | CS-001..006 C# P1 缺陷修复 + RS-001/RS-010 孪生缺陷 + 回归 6 测 | 8 | dotnet 318+29 全绿 |
| W1 | b4e26d0 (beta.47) | WB-001/002 导入统计管道 Promise 修复 + 行为级桥测试 4 项 | 2+4测 | node 15/15 |
| P1 | 0e102af (beta.48) | PY-001..025 关键子集 13 项（schema 预发布段/防回滚 precedence/差集清理/锁版/双触发/pip hash/mypy 全量/工件集消歧）+ pytest 基建 13 测 + 过期向量 | 13 | pytest 13/13+validate+YAML 全解 |
| A1 | 9859c18 (beta.49) | AD-001/002/004/006 + JVM 测试 14 项 | 4+14测 | gradle 单测+ktlint+detekt 全绿 |
| W2 | 本次提交 | WB-003 CHANGELOG 补 beta.32–49、WB-004/005/034 CLAUDE.md 正典口径（红线/命令/文件地图） | 4 | 文档核对 |
| W3+SP1 | 本次提交 | WB-006..009 文档口径四项（CONTRIBUTING 双栈门槛/supported-features 重写 ×2/架构全景重写）+ SP-001..008 八项（契约示例对齐/KNOWN_DEFECTS 表格并入×2/KB-DR 编号互引/release.json arm64 声明删除/threshold yaml 单源 fail-closed/deny_scope 测试） | 12 | 红队 e2e 5/5+validate_release 52 文件+threshold 正负例 |
| A2+PY2 | 本次提交 | AD-007..023/026..031 测试缺口 24 项（AegisWebViewClientTest 9 项含 scheme 纯字符串化/AndroidBrokerPolicyTtlTest 5 项含 Clock 注入/app 模块 6 测试类+SearchEngines 全链补强；AD-024/025 已由 A1 覆盖）+ 附带缺陷修复（WebViewDownloadHandler 双重扩展名 report.pdf→pdf.pdf）+ PY-005/009/013/014/015/020/025 七项（生成器 mixin 链解析/verify_release 死签名断言改判 gh attestation/向量 jsonschema 校验脚本+接线/生成器 CI drift 门禁/action-catalog 分析器接线/pyyaml 锁版单次/release.yml 内联 50 行改调脚本） | 31 | JVM 测试 broker+app+webview-adapter 全绿（74+）/pytest 13/13/ruff/validate_release 52/YAML 12 份 |
| A3（P2 核心） | 本次提交 | AD-032..034/036..037/048..063/065/066/068/069 P2 核心逻辑+测试 25 项：下载名 200 截断保扩展（032）/标题日志净化（033）/registerSession 失败先 tearDown（034）/updateUrl copy 单写点+测试（036/037）/外链绕过防抖（048）/requireNotNull（049）/自动批准注入 decision 源（050）/about:blank+destroySession broker 测试（051/052）/onPageStarted 代际+onReceivedHttpError 客户端测试（053/054）/BrowserEngine 硬化 Robolectric 逐项断言（055）/addTab 即时挂起测试（056）/searchUrl 纯字符串化 uriEncode+测试（057）/版本检查协程化（058）/裸 Handler→viewModelScope（059）/replaceWebView suspended 重置（060）/销毁收敛 tearDown+删双 destroySession（061/062）/file:// 地址栏占位（063）/UncaughtExceptionHandler 留痕（065）/CI :app:lintDebug 门禁+webview-adapter 单测（066）/Compose BOM 入 catalog（068）/BRIDGE_GUARD_JS internal+防御标记断言（069）；附带真缺陷修复：DownloadPolicy URLDecoder Charset 重载 API 33+ 在 minSdk 26 崩溃（lint NewApi） | 25+1附带 | gradle 三模块 ktlint+detekt+单测全绿+lintDebug 0 error |
| A4（P2 UI） | 本次提交 | AD-035（库层错误码上抛：onPageError 改 (code,detail,isSsl,url) 结构、契约常量 public 单源、ssl/mainFrame/HTTP 文案映射收敛 app 层）+ AD-038（8 处 collectAsStateWithLifecycle）+ AD-039/040（itemsIndexed key=tab.id）+ AD-041（rememberOrderedGroups remember(tabs)）+ AD-042/043/044（ChromeIconButton contentDescription+enabled 灰显、TabChip 关闭钮 semantics+Role.Button、两处新建标签语义）+ AD-045/046/047（strings.xml 单源 ~44 条：MainActivity/ViewModel 全部提示、Manifest label→@string/app_name 对齐 DISPLAY_NAME）+ AD-064（canGoBack/canGoForward StateFlow+按钮禁用+navigateHistory 刷新）+ AD-067（androidTest 冒烟 4 测+runner 依赖+testInstrumentationRunner） | 13 | 三模块 ktlint+detekt+单测全绿+assembleDebugAndroidTest+lintDebug 0 error |
| W4（WB P2） | 本次提交 | WB-010..030 Web 资产 P2 21 项：跨端对账增列 C# 正典栈（壁纸第 5 份 NtpAssets/引擎表 UrlNormalizer+CS_ENGINE_EXTENSIONS 扩展白名单 fail-closed）（010/011）/snake.test.js 入 CI 门禁（012）/start.main.js 7 处空 catch→bridgeError→Host.jsError 留痕（013）/Android 书签纵深防御分支注明保留（014）/导入统计管道回归 2 测（015）/snake 行为测试 turn 反向拒绝+队列上限+freeCell+step+计分（016..019，经 __test 只读钩子）/15s 扫描超时兜底+迟到回包忽略+Promise 拒绝兜底（020）/Host.kind 三端判定+共存优先级+has 白名单语义（021/022）/Android 引擎解析回退（023）/csCall id 关联+回调异常隔离+无桥降级（024）/未知壁纸整体 no-op 含持久化恢复路径（025）/背景 url 单引号 %27 编码（026）/导入向导焦点管理：初始聚焦+关闭归还+Tab 陷阱（027）/engineMenu role=menu+aria-controls+menuitemradio（028）/:focus-visible 键盘焦点样式（029）/CHANGELOG 未发布节标题补正（030）；新增 start_host/start_import/start_main 三测试文件 22 测入 CI | 21 | node 五文件 33/33+snake 19/19+跨端对账（壁纸 ×4 端/引擎 3 端+扩展 6）+validate_release 52+verify_versions+bridge_guard |
| 暂缓 | — | AD-003（R8 minify）、AD-005（per-site SHA-256）——需真机回归，按 device-validation runbook 单独批次；AD-067 冒烟集执行（CI 无模拟器，真机批次跑） | 2 | 待设备 |
| R1+（RS P2 代码） | 59834b2 | RS-011..040 Rust P2 代码修复 30 项：origin host 段拒内嵌冒号（011）/尾点剥离+字符白名单+点段拒绝（012）/extract_hostname authority 终止符扩 /?#（013）/裸 IPv6 拒绝（014）/glob_match+covers 迭代 DP 替代递归（栈深）（015）/glob_subsumes 16K 上限（016）/`..` 折叠 fixpoint（017）/measureText CSS 简写解析（018）/check() 剥尺寸样式前缀（019）/microseconds.max(1)（020）/letterbox 步长钳 max(1)（021）/query_strip 参数转义（022）/字体名转义（023）/webgl vendor+renderer 转义+Symbol 注册（024）/canvas 噪声离屏副本（025）/shield 删 WebGL 块（单一负责方）（026）/注册接口 Symbol.for 键（027）/AudioBuffer LCG per-site 微扰（028）/空凭据 Allow→RequireConfirmation（029）/同效果 priority 降序 fold（030）/oracle after 键 absent Mismatch（032）/create_session 续期语义注释（033）/MAX_NONCE_LENGTH 128（034）/pending 账本惰性过期清理（035）/hex seed 严格解析（036）/default_workspace serde 转义（037）/JS 规则 enabled 字段（038）/command_bar 小写缓存（039）/impl_js_injectable! 宏+blanket &T（040） | 30 | cargo test 224+5+4+clippy 0+fmt；五门禁全绿 |
| R1++（RS P2 测试/fuzz） | 3d036f4 | RS-041..050 测试与 fuzz 10 项：policy 远程降级 3 用例+本地优先锁定（041）/broker evaluate 全链 Allow 正用例+更名断言相反用例（042）/destroy_session 清 nonce 账本（043）/session_state 恶意标题往返+字段注入（044）/context_contains_token 直接单测 8 项（045）/pipeline_with_mode 三模式阶段标记+站点种子确定性（046）/space_routing P28 恶意 name/workspace 注入回归（047）/command_bar P27 恶意 title/value 注入回归+scheme 门禁（048）/read_utf8 64KB 边界+非 UTF-8+null（049）/fuzz 新增 5 target（origin_canonical/glob/session_state/security_policy/util_hostname） | 10 | cargo test 253+5+4+clippy 0+fmt+fuzz --bins 编译过 |
| C2+C3（CS P2 存储+Broker 测试） | b1a063a | CS-007..030 24 项：RequestNavigationConfirmation 补 KillSwitch 前置检查（007——确认请求入口唯一缺口）+Broker.Tests 11 用例（008..017：AllowDownload/EvaluateNav/RequestConfirm KillSwitch、重复/超限/空白 RegisterSession、代际跳跃/回退/错标签、过期 IsValid、nonce 重放、StubBlockedHosts 注入、UpdateBlockedHosts(null) 回退）+HistoryStore title LIKE 转义 4 处（018）+分页/升级/搜索语义测试 9 项（019..027）+ClampLimit 负 LIMIT=无上限钳制（028）+BookmarkStore/TabSessionStore EnsureSchema-once volatile（029/030） | 24 | Core.Tests 327+Broker.Tests 42 全绿；五门禁全绿 |
| C4（CS P2 Chrome 主链） | 443b4f2 | CS-031..041 11 项：NtpBridge import 三操作 Task.Run+marshalToCaller UI 线程 I/O 外移（031）/BookmarkManagerWindow 搜索 200ms DispatcherTimer 防抖+OnClosed 停表（032）/HistoryWindow 删除/清空容错+EmptyHint 反馈+SecurityLog（033）+日期解析/展示 InvariantCulture（034）/DateField 年份钳 1..9999+末月导航按钮禁用态（035）/ZoomStore Get Math.Clamp（036）/TabRuntime.Navigate 单源收敛 MainWindow/InPrivate 双 SafeNavigate 副本（038）/InternalsVisibleTo+UtilityClasses IsSameSite Theory（039）+DateLabel/ParseLocalTime 直测（040/041） | 11 | Core.Tests 338 全绿；五门禁全绿 |
| C5（CS P2 回归测试） | 3960035 | CS-042..058 回归测试 17 项（051/052 核验既有覆盖已足）：MaxUrlLength 8192/host 253/254/label 63/64/userinfo 3 形态/控制字符边界 Theory（042..045）/Bookmark Rename/RemoveById/ClearAll/Import 计数（046..050）/NtpBridge 畸形 marker/id ValueKind 前置检查不抛+jsError 落日志+importHistory 钳 1..2000+goBack false 透传（053..056；053 附带修真实 FormatException 缺陷）/ThreatFeed ParseFeedLine 边界+ValidateFeedUrl Trim（057/058） | 17 | Core.Tests 370+Broker.Tests 42 全绿；五门禁全绿 |
| C6（CS P2 窗口冒烟+收敛） | f415d0b | CS-059..071 13 项（062/065/066 核验既有实现已覆盖）：Settings/BookmarkManager/SourceViewer 三窗口 STA 冒烟+ApplyTheme（059..061；附带修 SettingsWindow 10 位十六进制颜色 #FFB3FFFFFF→#B3FFFFFF XamlParseException 真实缺陷）/BookmarkBarItems ItemTemplate+死处理器删除（063）/静态 SourceFetchClient PooledConnectionLifetime 5min（064）/RestoreWindowState 上限钳虚拟屏幕（067）/BlockedHosts span 备用查找零分配后缀匹配（068——首版清单侧祖先域预展开会过度封锁，被既有单测拦截后改查询侧 span 方案）/IsTrustedChromeOrigin 死代码删除（069）/UrlRedactor 单源新建（070）/Teardown 收敛 Close/Sleep（071）；附带 HistoryStore LikeEscape null 守卫×3 | 13 | Core.Tests 373+Broker.Tests 42 全绿；五门禁全绿 |
| C7（CS P2 无障碍+边界） | 8ed099d | CS-072..083 12 项：NativePolicyCoreGate 空路径 Block/未启用 Disabled 分支（072）/TryCreate(null/空白) fail-closed 且 out null（073）/仅点号 host 不误拦+点号清单条目构造期丢弃（074）/SettingsService 写盘失败不抛且内存快照更新+Changed 仍通知（075）/.local/.internal/.localhost 后缀分支锁定（076）/Settings/History/BookmarkManager/Downloads/InPrivate 五窗口逐控件 AutomationProperties.Name（077..081）/标签条 ✕+SleepMark Name（082）/查找条 ▲▼✕ Name（083） | 12 | Core.Tests 389+Broker.Tests 45 全绿；五门禁全绿 |
| PY1（PY P2 脚本健壮性） | 03e7a27 | PY-026..043 18 项：sync_versions 缺 "=" 行 RuntimeError 带路径行号（026）/verify_versions inputs is_file 预检+required/missing 汇总 fail-closed（027/028）/dedup_release_assets argparse 化（029）/codegen+security-e2e runner 超时 120/180s+stderr 透传（030/031）/build_review_package timeout=30+异常收窄（032）/verify_bridge_guard RUST/KOTLIN is_file 预检（033）+REQUIRED_SINKS 模板锚点行机器可读（043，Kotlin 内嵌副本同步）/verify_cross_end_lists _read fail-closed×7+壁纸多后缀（034/035）/verify_xaml_resources FindResource 索引器正则（036）/validate_release AST 扫描扩 scripts/contracts/release 79 文件（037）+shared/shell/manifest.txt 资产清单（038）/write_checksum_json 1MiB 分块哈希（039）/gen_jsapi_schema defaults 对齐+循环变量遮蔽方法名真实缺陷修复（040）+APP_DIR legacy 标注（041）/verify_contract_compatibility 重生成内容 diff（042） | 18 | 本地七脚本全绿；五门禁全绿 |
| PY2（PY P2 workflow 优化） | be445f3 | PY-044..068 25 项：8 workflow concurrency group+cancel-in-progress（044..051）/rust-cache@v2 SHA-pin 批量接入 7 处（052..058）/NuGet+pip+gradle actions/cache@v4（059..061）/verify_vectors.py 从 CI 内联抽出（064）/ci Python 3.14→3.12 统一（062/063）/android-quality 显式 setup-python+detekt 四模块聚合 artifact（065/066）/compat stderr tee 留痕+归档注释改实（067/068） | 25 | YAML 结构+verify_vectors 本地绿；android-quality 重复键缺陷延至 PY3 修复 |
| PY3（PY P2 向量扩充+三端对齐） | 80d3e58+2ca6051 | PY-069..093 25 项：url-origin-invalid 9→23——IPv6 环回/IPv4-mapped×2/整数 IP/0x 十六进制/127.1 简写/连续点段/下划线+引号/端口 0+65536/空 userinfo/Tab+CR（069..077）/url-origin-valid 3→8——大写归一/显式默认端口×2/punycode/点分 IP（079..081）/超长 URL 物化契约——vectors.rs 消费端锚点物化+verify_vectors 锚点守卫（078）/update-manifest-invalid 5→14——非法 base64/未信任 key_id/无时区过期/bad sha256/未知 platform/零 size/不安全 url/顶层 const×2（082..086）/update-manifest-valid 1→4——预发布+beta/threshold=1 单钥/多钥（087/088）/approvals 3→6——换 scope 重放/到点/缺 nonce（089/090）/navigation-decision 4→6——协议扩展 destroy_session/advance_generation/expected_reconsume_code，fail-closed 拒绝码 action_not_issued（091/092）/黑名单能力归属 C# BrowserPolicyBroker.IsHostBlocked 登记，native 无注入口（093）；三端 OriginPolicy IPv4 备用编码对齐（Rust origin.rs 全数字段≠4 段拒+0x 守卫/C# authority @ 扫描+段守卫/Kotlin isAlternateIpv4Encoding 提取+常量化） | 25 | cargo test 253+5+4+Core.Tests 389+Broker.Tests 45+broker 33 全绿；五门禁全绿（附带修 cargo fmt 门禁+android-quality.yml if-no-files-found 重复键真实缺陷） |
| PY4（PY P2 schema/向量/codegen） | e8b1f95 | PY-094..102 9 项：action/capability/audit-event 双向向量 24 条 schema 级严格校验（094..096，valid 必过/invalid 必拒）/approval method 词表与 action 收敛（097）/capability 预算语义澄清归属 Broker 运行时+actions/resources minItems=1+词表 enum（098）/release.json 全字段 schema 门禁化（102——architecture enum 仅 x64 固化 PY-101 口径；附带修 jsonschema date-time 依赖 rfc3339-validator 可选包缺装时区校验静默跳过真实缺陷）/codegen 双生成器 number→decimal/Double 显式映射+required 区分可空默认+未知类型 fail-closed+SKIP_SCHEMAS 单源（099/100；101 已由 92f4c36 修复）；android :contracts detekt 排除 generated/**（基线按参数签名记录，生成物字段变化即失配——根因修复） | 9 | 本地九脚本+C# 389+45+Kotlin contracts/broker 全绿；五门禁全绿 |
| PY5-1（PY P2 脚本单测①） | 3ecc297 | PY-103..116 14 项：load_properties 注释/空行/值含=/缺=带行号（103）/replace_assignment 引号两态+缩进+首匹配+失败不落盘（104）/replace_xml_value（105）/expected_xml_value+expected_assignment（106/107）/dedup 子进程级四用例（108）/gen_jsapi _doc_first_line+build_schema 白名单与 required 语义+mixin 跨文件溯源+派生遮蔽（109..111）/build_review _match_excluded 表驱动 8+collect_sources 确定性+git 降级+stamp_readme 两态+check_reviewed 三类报告（112..116）；**附带修真实缺口：tests/python/release_chain_test.py（PY-149）从未入 CI——死测试基建，接 ci.yml pytest 步骤+requirements-dev 锁版 pytest==8.4.2** | 14 | pytest 45/45；五门禁全绿 |
| PY5-2（PY P2 脚本单测②） | 64da53b | PY-117..124 8 项：verify_xaml collect_keys+缺失键文件:行号+索引器类别+全定义通过（117/118）/壁纸提取器三端（asset_scheme 多后缀/start.main.js/AegisHomeBridge setOf）+锚点缺失 fail-closed（119..121）/引擎表三端解析+CS_ENGINE_EXTENSIONS 白名单语义（122）/validate_release check_lock_file 三态（123）+check_required_cs_files 三态（124）；**附带修真实缺陷：validate_release 模块级 raise SystemExit 使 pytest import 即退（INTERNALERROR）→主流程包 main()+__main__ 守卫；verify_xaml_resources 报告路径 relative_to 崩溃→try/except 降级** | 8 | pytest 61/61；validate_release 真仓 81 文件 0 失败；五门禁全绿 |
| PY5-3（PY P2 脚本单测③） | 5cadcd8 | PY-125..138 14 项：cs_type/kt_type 表驱动 6 类型+未知 fail-closed（125/129）/generate_csharp 快照断言（126）/contract_name 映射+三副本一致性漂移守卫（127/131）/陈旧清理回归 GhostContract 差集删除（128）/Kotlin 尾逗恒定+可选可空（130）/bridge_guard norm+«first_diff 行号定位+EOF（132/133）/Kotlin 占位符归一化端到端三态（合成三端环境 main 全绿/未登记插值拦截/漂移行定位）（134）/action-catalog 重复名/scope risk 冲突/audit+fixtures 缺失/坏 YAML 不抛+干净通过（135..138）；**附带修 verify_bridge_guard relative_to 崩溃→降级** | 14 | pytest 95/95；五门禁全绿 |
| PY5-4（PY P2 脚本单测④——P5 收官） | 21c0925 | PY-139..148 10 项：write_checksum build_manifest 排序+自排除+递归+空目录（139）/verify_checksum 合规计数（140）+篡改/越界/重复/漏列四拒绝（141）/canonical_unsigned 字节精确断言（142）/_version_tuple 预发布序+构建元数据忽略+非法拒绝（143）/verify_manifest Ed25519 双钥阈值通过/单钥不满足/过期/签名后篡改/重复 key_id 只计一次（144）/回滚拒绝（145）/native_manifest 缺失+空文件+符号链接三类 ValueError+往返稳定（146）/--verify 投毒场景拒绝（147）/build_metadata 缺属性 SystemExit+GITHUB_SHA 降级（148） | 10 | pytest 121 passed+1 skipped（Windows 非特权符号链接跳过）；五门禁全绿 |

> 完成度：385 项落地（跨 27 批——先导/R1/C1/W1/P1/A1/W2/W3+SP1/A2/A3/A4/W4/R1+/R1++/C2+C3/C4/C5/C6/C7/PY1/PY2/PY3/PY4/PY5-1/PY5-2/PY5-3/PY5-4；beta.44–49 各批随版本递增，其后批次独立提交），并随批补强回归/行为测试；1115 项完整清单作为后续批次的工作池（余量 ~730 项：CS-084..296 / RS-051..205 / WB-031..100 / AD-070..210 / SP-009..138；另有 AD-003/005 与 AD-067 冒烟执行共 3 项暂缓待真机）。


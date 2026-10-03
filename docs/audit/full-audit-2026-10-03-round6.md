# 全仓审计第六轮（2026-10-03）——发现、闭环与缓修台账

方法：按语言/模块分六区并行扫描（Rust 核心 / Android / Windows / 契约+Web 资产 /
CI-供应链 / Python+文档核验），覆盖 649 个跟踪文件、约 70K LOC 四语言实现。
所有 P1/P2 由主代理逐条回读代码复核（含 1 条子代理误报被推翻，见文末）。
本轮定位为**复查前五轮「全量闭环」声明是否属实**——结论：分项大多属实，
总口径不属实，且存在三条使架构主轴落空的断链。

## 一、本轮已闭环（全部有验证手段，非"改完即算"）

| 编号 | 级别 | 缺陷 | 修复位置 | 验证方式与结果 |
|---|---|---|---|---|
| R6-01 | P1 | 尾点 host 三端判决相反：Rust `origin.rs` 剥离归一并**放行** `https://example.org./`、`https://localhost./`，C# / Kotlin 一律**拒绝**；`url-origin-*.json` 零尾点向量，三端向量测试同时全绿。Rust 侧注释却自称"与 C# 口径一致"（不实）。按 AD-252 记录的攻击面，Chromium 会剥尾点使 `location.hostname == localhost` 命中 bridge_guard 环回白名单 | `core/.../origin.rs`、`contracts/vectors/url-origin-invalid.json`（+2 deny 向量）、`origin.rs` 单测改断言并补 7 形态拒绝 | `cargo test` 541+10+4 全绿；`url_origin_vectors_match_contracts` 通过；C# `dotnet test --filter UrlOriginVector` 38 例通过，日志实证 `https://localhost./` 作为 deny 用例在 Rust 与 C# **两端都真实执行** |
| R6-02 | P1 | 威胁黑名单在无痕窗口永久为空：`InPrivateWindow` 自建 broker（默认 `NoBlockedHosts`），而订阅源刷新只 apply 到主窗 broker。同文件 CS-291 已为 KillSwitch 修过同一缺陷类却漏了黑名单 | `SharedBlockedHosts`（新，进程级持有者）+ `MainWindowDependencies.cs` 与 `InPrivateWindow.xaml.cs` 两处注入 | 构建 0 警告；Core.Tests 708 通过。子代理曾建好持有者类却**未接线任何调用点**（等于空转），本轮补齐注入并验证 |
| R6-03 | P1 | 子框架 Allow 劫持顶层框架（前五轮标✅的 AD-309 引入的回归）：iframe 内导航执行 `view.loadUrl()`，而该方法恒作用主框架 → 整标签被替换、真 iframe 永不加载，且绕过主框架授权链（UI 红描通道） | `AegisWebViewClient.handleSubFrameNavigation`：Allow 改返回 `false` 放行原始请求，并删除 `view` 形参；HTTPS 升级依赖 `network_security_config` 三层明文禁令（已核实存在且有守护测试） | 单测改为断言"子框架路径不得对 WebView 产生任何调用"（旧假 WebView 无框架语义正是此前不可见的原因） |
| R6-04 | P2 | 桥守卫门禁**自证其检查清单**：`REQUIRED_SINKS` 存活于被认证模板自身的注释行里，钩住模板与两端副本同删 hook 实现 + 删锚点 token 时门禁恒绿 | 清单迁出至 `contracts/policy/bridge-sinks.yaml`（门禁自有），双向断言 body 实现 / 锚点 token / 两端副本命中 | 故障注入实证：镜像仓库同删 sendBeacon 实现与锚点 token → **exit 1**（三条违规）；未改动镜像 → exit 0。此前该攻击返回 exit 0 |
| R6-05 | P1 | 红队 fixtures 从不驱动 broker：门禁为正则抓 `README.md` 里的 `"expected":"deny"` 字符串，且目录里**根本没有可解析载荷**；标注 deny 的实际放行样例无法被发现 | `agent/redteam/*/fixtures.json`（新，4 类共 12 case / 20+ 步）+ `redteam_test.py` 行为化测试：逐步喂出厂 `PolicyBroker`，断言**精确**拒绝码（禁止笼统 "deny"）；每 case 含 allow 对照步防"broker 整体失效即全绿" | `pytest agent/tests` 40 通过。故障注入：加一个"标注 deny 实际 allow"的样例 → **exit 1** 并指名"声明 deny 却实际放行"；还原后复绿 |
| R6-06 | P2 | legacy 订阅源降级（200 轮台账 P43 记为已闭环但代码从未落地）：`validate_feed_url` 只校验初始 URL，两处 `urlopen` 均不复查 `resp.geturl()`，urllib 允许 https→http 跨 scheme 跳转 → MITM 可篡改黑名单（注入或删除条目） | `threat_feed.py` 新增 `_require_same_https_scheme`，两处读取前强制；保留离线 file:// 开关语义 | 单元实证：https→http 拒、https→file 拒、https→https 与 file→file 放行；同仓 `api_bridge.py` / C# `ThreatFeed.cs` 早已这样做 |
| R6-07 | P2 | `credential_guard.redact_url` 用 `urlunsplit(netloc)` 重组 → **保留 userinfo 凭据**；且解析失败 `return raw` 回吐原文。同类已在 C#（CS-337）/ Kotlin（AD-264）闭环，独漏 Python | 改由 `hostname`+`port` 重组，异常路径 fail-closed 返回固定占位符 | 直跑验证：`https://SECRETtoken@example.com/p?api_key=abc` → `https://example.com/p?api_key=[REDACTED]`；`https://user:pw@example.com/a` → 凭据剥除；端口与常规 URL 不误伤 |
| R6-08 | P2 | MCP 工具 scope 门禁 fail-open：`if need and not auth.allows(need)` —— 新工具忘记登记 `_TOOL_SCOPE` 时 scope 校验被整段跳过 | 未登记 scope 一律 `-32004` 拒绝（default-deny） | 实证：仅入 `_TOOLS` 不入 `_TOOL_SCOPE` 的工具 → `-32004`；正常工具越过该门进入后续校验 |
| R6-09 | P2 | `native_hardening.py` per-origin WebMessage 翻转包在 `except Exception: pass` 里 → 静默即 fail-open（该模块 docstring 自陈 pywebview 6.2.1 的 js_api 传输正是 WebMessageReceived，且承诺"安全状态变化一律留痕"） | 异常路径尽力关闭两条通道 + `log_event` 显式留痕 | `py_compile` 通过；`pytest` 全绿 |
| R6-10 | P1 | 指纹噪声站点种子被发布给页面：`defineProperty(window,'__AEGIS_SITE_SEED',…)` 且噪声是该种子的纯函数 → 页面可按名读取并**确定性还原真实 canvas**；Rust 参考模块 `per_site_seed.rs` 明令禁止此形态 | `WebViewHardening.kt` 改闭包内 `const`，与参考实现对齐；新增回归测试断言 const 形态、无 window 导出、无 defineProperty、消费点取闭包值 | 静态断言 + `androidTest` 在真机侧检查 `typeof window.__AEGIS_SITE_SEED` |
| R6-11 | P2 | 紧急终止只在 broker 入口判定：`Engage` 不停内核、不取消在途下载，页面继续流式拉取子资源 | `KillSwitch.RegisterProcessReaction` + `HostWebView` 接线（`Stop()` + 追踪下载 `Cancel()`，解绑时注销） | 子代理建好 API 却**零调用者**（又一处空转），本轮接线进 `WireEvents/UnwireEvents`；构建 0 警告 |
| R6-12 | P2 | 下载元数据读取失败被吞成空串 → 危险扩展判定输入变空 → 静默落盘可执行文件；`SetPerOrigin` 对 `file:`/`data:`/`about:` 一律**启用** WebMessage；翻转处理器在导航被取消后仍执行；`AllowExternalDrop` 全仓未设（拖拽可外泄本地文件）；`TabRuntime.Navigate` 对未接线控件写 `Source` 触发默认环境隐式初始化（零策略处理器） | `HostWebView`（fail-closed 元数据 + 取消短路 + 拖放关闭）、`WebView2Hardening.SetPerOrigin` 默认拒绝、`TabRuntime` 就绪/接线双闸 | `dotnet build` 0 警告；Core 708 / Broker 49 通过 |
| R6-13 | P2 | 四个原生 ABI 用例在环境变量缺失时 `return`，xunit 记为**通过**——P/Invoke 面从未被触碰也报全绿（DLL 缺席时"已跳过 0、失败 0、通过 49"）。xunit 2.9.3 无 `Assert.Skip`，本仓不为此加包 | 新增自洽锚点用例：一旦声明原生模式即必须真跑完整跨界往返 + 双 broker 共存，否则失败 | 正向：指向真实 DLL → 50 通过（实证 P/Invoke 可用，且 `NativePolicyCoreBridgeHub` 确实化解了 Rust RS-140 进程内单 broker 约束）；故障注入：DLL 缺失 → **exit 1** 并给出 `native_policy_core_unavailable` |
| R6-14 | P1 | 安全门禁可被直推绕过：`contracts.yml` / `android-quality.yml` 的 `push` 带 `paths:` 过滤（ADR-007 D3 明令禁止），只改 `WebViewHardening.kt` 或 `bridge_guard.rs`——即守卫门禁唯一对账的两个文件——零作业运行 | 删除两处 `push.paths`，恢复全量常跑 | YAML 校验通过；代价与正确替代方案（required checks）已在注释中如实说明 |
| R6-15 | P2 | `validate_release.py` 的 hash-lock 门禁守的是**退役归档栈**的锁（`legacy/.../requirements-lock.txt`），CI 实际以 `--require-hashes` 安装的根级 `requirements-ci.txt` 无任何仓库级断言 | 新增 `check_active_lock_file`（锁 + 编译源存在性/ hash）并接入主流程 | `python validate_release.py` exit 0；空目录树负例 → 报缺失（证明非恒真） |
| R6-16 | P2 | zip-slip / 入口存在性防护用 `assert`（SP-209 的"闭环"本身可被 `python -O` 剥除，PY-187 同型） | `prepare-geogebra/action.yml` 与 `scripts/migrate-profile-data/run.py` 改显式 `raise SystemExit` | `action.yml` YAML 通过；`python -O` 实跑 `run.py` 行为不变（exit 3 语义保留）；全仓 `-O` 面复查 |
| R6-17 | P2 | `workflow_dispatch` 输入未加引号直入 `run:`（`packages=a"$(id)"b` 可在 runner 执行命令，需仓库写权限，非外部可达） | `gradle-dependency-insight.yml` 经 `env:` 中转，输入永不进入脚本源码 | 全量扫描 workflows/actions 确认该行为唯一残留 in-run 表达式 |
| R6-18 | P1 | 签名身份从不校验：`apksigner verify` / `signtool verify /pa` 只证明"有签名且成链"，不证明"是谁签的"。keystore secret 被替换时 CI 会用攻击者钥匙签名并**全程绿灯发布**（恶意更新链）。预期值若也放 secret，则与 keystore 同爆炸半径 | 新增受版本控制、经评审的 `docs/release/signing-identity.txt`（含实测指纹）+ `release-android.yml` 对账步骤，身份文件缺失/未登记/不匹配一律 fail-closed | 本地实跑该步骤逻辑：真机制品指纹 → exit 0；攻击者指纹 → **exit 1**；空登记 → **exit 1** |
| R6-19 | P3 | bandit 全局豁免 B603/B607（`-ll` 阈值下实测零新增发现，故危害在增量而非存量） | `bandit.yaml` skips 收窄为 `["B101","B404"]` | `bandit -c bandit.yaml -r scripts release contracts agent -ll -q` **exit 0**，零发现 |

### 一之二、延续轮（2026-10-04）新增闭环——架构主轴的两条断链

| 编号 | 级别 | 缺陷 | 修复 | 验证 |
|---|---|---|---|---|
| R6-20 | P0 | **FFI 通路无任何内容判定**：`evaluate_navigation` 只做 URL 归一 + 会话/代际/nonce 校验，从不调 `PolicyEngine::evaluate`/`CapabilityRegistry::validate`，也无 host 黑名单——任意良构 https（含钓鱼/恶意 host）一律 Allow 并发放可消费 nonce。因 `PolicyEngine::default()` 是 deny-all 故从未接线（代码 H-7 自述），结果是"单一裁决源"退化为"单一 nonce 记账员" | 新增 C ABI 入口 `aegis_policy_core_broker_update_host_denylist_json`（入参 JSON host 数组，返回 `{decision,accepted,input}`；未注入时黑名单为空=行为不变，不 deny-all），`evaluate_navigation` 在归一后先查黑名单命中即 `deny/threat_blocklist`。锁中毒按"被拒"处理。已登记入 `c_abi_export_surface_is_frozen` 冻结符号表 | 新增 3 条跨端向量（`blocklisted_host_denied` / 大小写形态 / `bad.example:8443` 带端口形态）；`cargo test` 551 通过。带端口那条是开发期实测到的**我自己的**绕过：`CanonicalExternalUrl.host` 依 RS-227 保留非默认端口，直接比对会使 `bad.example` 匹配不上 `bad.example:8443`——已改为剥端口后比对并加向量钉住 |
| R6-21 | P1 | **确认流被核心侧无条件触发**：`request_navigation_confirmation` 把每一个 Allow 都转成 RequireConfirmation，等价于"每次导航都弹确认"，因而 2026-08-30 被关闭、整套确认域（pendingConfirmation / 防孤儿 nonce / 受信 Compose 批准入口）沦为死代码 | 高危判据落进核心：`SecurityPolicy::is_local_or_private_host`（127/8、0/8、10/8、172.16/12、192.168/16、169.254/16 含云元数据、`localhost`），仅高危目标登记待审批；普通公网导航直接 Allow。CI 释放构建恢复 `-PrequireNavigationConfirmation=true` | 5 条高危向量（127.0.0.1、127.0.0.1:6379、localhost、192.168.1.1、169.254.169.254 → require_confirmation）+ 公网对照 → allow；`assert!(evaluated.get("action").is_none())` 钉住"高危不得同时发放可消费授权"。副带收益：子框架轻量路径只调 `evaluate_navigation`，收到 require_confirmation 即 fail-closed 阻断——远程页嵌 iframe 打 127.0.0.1/私网的 SSRF 面在核心层被拦，不依赖端侧实现 |

判定口径的两处诚实限定（写在代码注释里，此处同步）：

1. **不按 `.local`/`.internal` 后缀名判高危**——宿主自有资产虚拟主机
   （Windows `ntp.aegis.local` / `geo.aegis.local`）正是该形态，按名匹配会把
   chrome UI 自己拖进高危集。DNS rebinding（域名 A 记录指向 127.0.0.1）超出
   无 I/O 纯函数能力，仍属宿主侧判定面，核心不假装全覆盖。
2. **退化信任锚未被证明可利用**：`update_manifest` 对可信密钥只做
   `VerifyingKey::from_bytes` + 长度校验，未筛除单位元/小顺序点。按 [k]A=O
   构造的 forged 签名（R=基点编码、s=1）在 ed25519-dalek 3.x 下被
   `verify_strict` **拒绝**——实测不可利用，因此本轮**不声称修了一个漏洞**，
   而是留 `identity_anchor_does_not_verify_forged_signature` 作 tripwire：
   dalek 换版或改用非 strict 验证时即红。keyid 与密钥字节无绑定一事同样以
   `keyid_is_not_bound_to_key_bytes_current_state` 记录现状供后续格式改造对齐。
3. **降级保护此前只存在于离线验证器**：`verify_threshold` 完全不看版本，全仓
   唯一降级判定在 `release/update_verifier.py`（设备侧运行时不校验更新）。新增
   `accept_update_version`（严格高于已接受版本、≥ min_version 下限、不可解析
   即拒），并把 `update-manifest-invalid.json` 的 rollback 用例从"断言向量自身
   两字段 cur<min"的同义反复改为真实调用该函数——同时补一条反向对照断言，
   防止实现退化为恒拒（那同样是假闭环）。

## 二、分端裁决现状（本轮确立的准确口径）

README 原述"裁决逻辑收敛在无 I/O 的 Rust 策略核心（单一裁决源）"对**两条发布
路径都不成立**，且两端缺的恰是对方有的一半：

| | Windows 发布物（唯一正典制品） | Android 发布 APK |
|---|---|---|
| Rust 核心是否参与裁决 | **否**——`AEGIS_REQUIRE_NATIVE_POLICY_CORE` 仅在 CI 构建机 shell 赋值，不随安装包交付，运行时恒 `Disabled()` | 是（`-PrequireNativePolicyCore=true`） |
| 威胁黑名单 | 有（R6-02 修复后无痕窗口亦生效） | **完全没有**（全树 grep 零命中） |
| 高危导航用户确认 | 关（同上，环境变量不持久） | 关——构建未开确认开关，客户端**自行兑换**一次性 nonce |
| 净效果 | 托管 C# broker 决定：良构 URL + 黑名单 | Rust 核心决定：仅"URL 是否良构"，即任意 https URL 均 Allow |

根因是三条彼此独立的断链：Rust FFI 入口 `evaluate_navigation` 内**不含任何策略/
能力/黑名单层**（代码自述 H-7：`policy.evaluate / capability.validate 未接入 FFI
通路`，因 `PolicyEngine::default()` 是 deny-all，接线属产品级变更）；Windows 运行
时门禁从不置位；Android 确认开关关闭后 `RequireConfirmation` 被自动批准。

## 三、显式缓修（需产品决策或真实设备验证，本轮**登记不改**）

| 项 | 为何不改 | 需要谁决策 |
|---|---|---|
| 启用 Windows 原生核心 | 前置条件本轮已就绪并实测（共享 broker 桥可共存）。翻开关会改变出货行为，需按 `docs/runbooks/device-validation.md` 真机回归无痕/多标签 | 用户已选"真正启用"，待排期验证 |
| 仅高危目标要求确认 | 当前 Rust 把**每一个** Allow 都转成 RequireConfirmation，故 2026-08-30 关闭确认；要在不牺牲可用性下恢复确认，必须先给 `evaluate_navigation` 注入策略层并定义"高危集合"——ADR 级变更 | 用户 + ADR |
| FLAG_SECURE | 会使 `screencap` 全黑，直接打断真机坐标校准调试流程 | 用户已选"不做" |
| 退出清理 cookies/DOM storage | 会把用户从已登录站点登出 | 用户已选"不做" |
| IDN 非 ASCII 域名支持 | 现状拒绝（fail-closed），是常态可用性缺陷而非安全缺陷 | 用户已选"不做" |
| Android 下载纳入 Broker + 禁明文 | 涉及跨进程（系统下载提供程序不受 `network_security_config` 约束）行为改造 | 用户已选"不做" |
| Rust `update_manifest` 加固 | 小顺序/单位元公钥拒绝、`key_id` 绑定密钥字节、单调版本校验。该路径**生产零调用者**（仅测试消费），风险为潜伏 | 待策略更新通道真正上线时 |
| 种子按顶层 eTLD+1 派生 | Android 注入脚本从 JS 侧拿不到主框架 origin，需宿主下发 | 与确认流改造同批 |
| required status checks | "必需检查永不出现"会永久卡死 merge box；须在门禁改动合入并观测到一次真实 PR 全量运行后再挂 | 本轮未开，ruleset 已开两项无上下文依赖的保护 |

## 四、前五轮台账复核（抽样 25 项）

约 20 项 PY-* 闭环属实且实现正确（241 轮确实扎实）。本轮确认的**虚闭环/回归**：

- **P43（200 轮）虚闭环**——订阅源最终 URL scheme 强制：台账记已修，Python 侧从未
  落地（C# 侧有）。本轮 R6-06 真修。
- **SP-209（241 轮）半虚闭环**——zip-slip 防护存在但包在 `assert` 里，`-O` 下失效。
  本轮 R6-16 真修。
- **AD-309（217 轮）修复即回归**——把良性放行改成顶层劫持。本轮 R6-03 撤销。
- **WB-214（217 轮）已回归**——README"13 workflow"对齐当时实树，之后新增两个
  `gradle-dependency-*` 使计数漂移至 15，无人发现（与历史上"测试文件因命名不匹配
  跑出 0% 覆盖"同一失效模式：闭环声明随代码漂移而静默）。
- **README「四轮全仓审计，全量闭环」过度声明**——241 轮自身尾注为"251 项中 248 项
  闭环"（CHANGELOG 又记 245），且树内已存在第五轮 217 项台账未被计入。
- **跨端类失效模式（最高频）**——同一不变量在 C# / Kotlin 闭环、在 Python 或 Rust
  未回落；以及"三端单源"由文本比对而非行为比对保证。

## 五、被推翻的子代理结论（记录以防以讹传讹）

Android 区曾报一条 P1：「子框架 Deny 返回 `false` 导致被拒 URL 仍加载，且自测
`assertTrue(denied)` 不可能为绿」。**误判**——`handleSubFrameNavigation` 的 `when`
分支是块表达式 `{ denied(...); true }`，其值为字面 `true`，`denied()` 的返回值被
调用方丢弃；该测试与实现一致。同一分支的 Allow 路径才是真缺陷（R6-03）。

## 六、验证命令汇总（本轮实际执行）

```
cargo test --offline                      → 541 / 10 / 4 全绿
cargo clippy --all-features --all-targets -- -D warnings → 0 警告
cargo fmt --check                         → 已格式化后通过
dotnet build ... -r win-x64               → 0 警告 0 错误
dotnet test Core.Tests                    → 708 通过 0 跳过
dotnet test Broker.Tests                  → 49 通过（原生模式 50 通过）
dotnet test --filter UrlOriginVector      → 38 通过（含尾点 deny 实证）
python -m pytest -q                       → 354 通过 1 跳过（基线 347+1）
python -m ruff check <活跃树>             → All checks passed
python -m bandit -c bandit.yaml -ll -q    → exit 0
python validate_release.py                → failures=0
bridge_guard / 红队 fixtures / 签名 pin   → 三处故障注入均按预期转红
```

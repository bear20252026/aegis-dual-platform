# 第七轮全量审计（2026-10-04）·8 分区并行 + 逐条回读复核 + 既往闭环声明核验

审计对象：`aegis-dual-platform` @ master `8d6dcf2`（PR #74/#75/#76 已并入）。
方法：分区并行派发只读子代理（文件所有权互斥）→ 主代理对每条 P1/P2 回读代码复核
→ 对既往台账标 ✅ 的条目做三态闭环核验。子代理结论未经回读者一律不登记。

## 一、真实源码规模基线（决定分区粒度）

按 `git ls-files` 收口，排除生成物（`Contracts/Generated/`、`contracts/generated/`）、
二进制与资产（28 个）、非源码扩展名（60 个）：

| 语言 | 文件 | 行数 |
| --- | --- | --- |
| Python | 104 | 20,953 |
| C# | 123 | 20,511 |
| Rust | 76 | 19,893 |
| Kotlin | 85 | 14,838 |
| Markdown | 103 | 12,926 |
| JS | 14 | 4,396 |
| YAML/JSON/HTML/XAML/CSS/TOML | 92 | 12,361 |
| **合计（真实源码）** | **597** | **106,495** |

统计口径修正一条：`core/rust-policy-core/src/bin/aegis_uniffi_bindgen.rs` 被自动排除
规则（目录名 `bin/`）误伤，实际是受管源码，已交 RS 分区审计——本轮 Rust 分区
覆盖含该文件。仓库受管文件总数 698。

## 二、分区与 COVERAGE 汇总（置信边界）

| 分区 | 前缀 | 负责目录 | 全文读 | 主要未读面（置信边界） |
| --- | --- | --- | --- | --- |
| Rust 核心 | R7-RS | `core/rust-policy-core/**` | 裁决主路径 + c_abi + ffi + fuzz 9 target 全量 | `src/` 指纹扰动/JS 生成族（shield/query_strip/font_norm/timer_prec/webgl_spoof/ext_proxy/space_routing/command_bar/matcher/policy/capability，约 4.3K 行）未独立判读，沿用既往 RS 批判定 |
| Android | R7-AD | `android/**` | 安全链路 33 个 Kotlin 文件全量 + 4 gradle + manifest | 16 个纯逻辑单测文件与 `detekt.yml` 未读；本机无 Gradle，一切「测试通过」类结论均未声称 |
| Windows 安全层 | R7-CS1 | `Broker/` `Chrome/` `WebView/` | 60 文件全量 | `Core/**` 仅定点读（ThreatFeed/SecurityLog/UrlSafety/DownloadPolicy），故 `IsPublicHost` 全量覆盖度取信于既有注记 |
| Windows 契约与测试 | R7-CS2 | `Core/` `Contracts/` `windows/tests/` | 测试 22 文件全量 + Core 关键 4 文件 + csproj/props | 其余 26 个测试文件按定向 grep + 片段核；`dotnet test` 因锁文件 RID 约束（NU1004）**未取得可比运行基线**，该区结论全部为静态逐行核验，不声称「测试通过」 |
| 归档 Python 栈 | R7-PY | `legacy/windows-pywebview/**` | 安全相关 20 文件 + 8 selftest 全量并实跑 | 约 3000 行展示/存储层无 CI 与出货执行路径，经 grep 交叉确认不含历史 P1 面后未逐行 |
| 工具链/发布/代理 | R7-TOOL | `scripts/` `release/` `agent/` 根脚本 | 30 个脚本全量 + 故障注入实证 | `requirements-ci.txt` 机生锁未逐行（按 `.in` 顶层 pin 对账） |
| 共享壳/契约/UI 回归 | R7-SH | `shared/` `contracts/` `tests/` | 13 文件全量 + 变异注入实测 | `contracts/schemas/*.json` 8 份正文未逐行（由校验器行为覆盖） |
| CI/供应链 | R7-CI | `.github/**` 根配置 | 15 个 workflow + 4 个 action 全量、action pin 逐个 `ls-remote` 回查 | `docs/**`（归主代理）、`release/tools` 判定归 TOOL |

**未覆盖面如实声明：本轮不是「全仓 100%」**。Rust 指纹族与 Android 展示层为抽样；
Windows 契约/测试区**没有任何运行态证据**（`dotnet test` 因 `-r win-x64` 锁约束未跑通，
陈旧产物 177 例与台账 708 例不可比，故该区全部为静态判定）——本条已在 B3 落地时闭合，
见第十节。

## 三、本轮 P1（8 条，全部经主代理回读或实跑证实）

| ID | 位置 | 现象 → 修复方向 | 证据 |
| --- | --- | --- | --- |
| R7-SH-01 | `contracts/codegen/verify_contract_compatibility.py:31-54,133-141` | 第六轮为闭合 AD-244「schema 与自身生成镜像自证」新建 `REAL_MODEL_CONTRACTS`（3 条真实手写模型映射）与 `DESIGN_NOTATION_MIRRORS`，注释宣称「此集外的镜像若无真实消费方则 `check_mirror_consumption` 计入 failures」——**该函数不存在，两个常量全仓零引用**，`main()` 仍是 schema↔自身镜像的自证。手写 `Decision.cs`/`AuditEvent.cs`/`capability.rs` 与冻结 schema 的字段/可空性漂移无任何门禁 | `git grep check_mirror_consumption` 仅命中注释行；`REAL_MODEL_CONTRACTS` 仅命中定义行；`main()` 主体三行原文 |
| R7-TOOL-02 | `agent/broker.py:149,152,360,367-368` + `agent/redteam/tool-result-poisoning-fixtures/fixtures.json:28-31` | 契约把 `expires_at`/`policy_version` 列为 required、`origin` 有 `^https?://` pattern、`method` 有 enum，而 `evaluate()` 只在 `expires_at is not None` 时才查过期与 `max_ttl`，且不校验 origin/method → **省略 expires_at 即得到永久有效授权**，`file:///C:/secrets`、`javascript:alert(1)`、`method=ARBITRARY` 全部 allow；夹具还把「不带 expires_at 放行」钉成 allow 对照，即门禁反向保护该缺陷 | 实跑（不落盘、只读导入 `agent/broker.py`）：`allow` / `deny_max_ttl`(2099) / `allow`(file://) / `allow`(ARBITRARY)；`contracts/schemas/action.schema.json` required 与 pattern/enum 原文 |
| R7-AD-01 | `android/app/src/main/java/com/aegis/browser/WebViewVersionCheck.kt:31,62` | `MIN_SAFE_VERSION_CODE = 132_000_000` 与 Chromium versionCode 编码差一个数量级（官方 `(BUILD*1000+PATCH)*100+后缀`，m132→BUILD 6834→约 `6.83×10⁸`），比较对象是 `PackageInfoCompat.getLongVersionCode` → 阈值反推 BUILD≈1320（约 m40 时代），**任何能跑 minSdk 26 的设备恒判「版本安全」**，MainActivity:73-74 声明的 CVE-2026-12438/11295 提示在全部出货设备上静默为零 | 阈值行与 `isOutdated` 直读；同仓 `WebViewVersionCheckProviderTest.kt:57` 用 `141_000_7390L` 表示 `141.0.7390.0`（10 位），与阈值 9 位记法只可能对一套 |
| R7-CS1-01 | `windows/.../WebView/HostWebView.cs:350-404`（对照 `Broker/BrowserPolicyBroker.cs:504-514`） | 本轮建立的隐私网络边界（`IsNonPublicNavigationTarget` = `!IsLocalAssetDocument && !IsPublicHost`）只作用于导航；`OnWebResourceRequested` 只做 DNT 注入、黑名单 403、跟踪分级——远程页面改发 `<img src="http://169.254.169.254/…">`、`fetch("http://192.168.1.1/…")`、XHR 时该处理器一律放行 → 声明的「远程页 SSRF/CSRF 原语已拦」仅在导航层成立 | 处理器全量回读：三条判定齐备、私网判定缺席；谓词本就存在且本类 `:242` 已在用（改动约 3 行） |
| R7-CS1-05 ≡ R7-CS2-01 | `windows/.../WebView/FingerprintShield.cs:115` + `core/rust-policy-core/src/shield.rs:82-84,123`（对照 `android/.../WebViewHardening.kt:328-338`） | R6-25 的顶层站框定**只落了 Android**：Windows 与 Rust 参考实现都仍按**本帧** host 派生（`getETLD1(location.hostname)` / `aegisEtldPlus1(location.hostname \|\| '')`），而 `per_site_seed.rs:17-19` 引 Brave 原文正是「Third party frames and script share the seed value of the **top level** eTLD+1 domain」→ 第三方跟踪帧在所有宿主站点拿到同一噪声，加噪画布哈希本身即跨站持久标识符（该机制要消除的东西）。两处测试还**正向断言缺陷字串**（`FingerprintShieldTests.cs:117`、`shield.rs:379-380` `assert!(script.contains("location.hostname"))`）＝把未修形态钉成契约（与 25a88bf 推翻的「锚点钉住缺陷」同型）；`shield.rs:82-84` 的「与 Android 孪生同口径」注记现已失实 | 三处行号直读；C# 全文件 `ancestorOrigins`/`window.top` grep 零命中；Android 侧该通道存在 |
| R7-CS2-02 | `windows/.../Broker/BrowserPolicyBroker.cs:219-220,247-248,346-350,512-522` + `Broker/TrustedChromeUiOrigins.cs:38` | 本轮新增的隐私网络边界（`private_network` 拒绝码，覆盖托管+原生两条求值路径与消费点）在 `windows/tests/**` **零断言**——`git grep private_network/IsNonPublicNavigationTarget/DenyNonPublicTarget -- windows/tests` 命中 0。它不像导航主链那样有 `native-navigation-*.json` 向量兜底：`private_network` 是**纯托管层拒绝码**，核心向量里没有它。任何人把该检查挪到 `HasCurrentSession` 之后、或在桥缺失分支提前 return，708 例仍全绿（与 R6-26「接入面零调用者藏了五轮」同一失效模式）。修：按向量口径补 127.0.0.1/`localhost`/192.168.1.1/169.254.169.254/`::1`/`0177.0.0.1` 精确拒绝码 + 公网对照 + `ntp/geo.aegis.local` 豁免仍放行 + 非默认端口 `.local` 不豁免 | 上列 grep 零命中（仅 `windows/src` 有 10 处）；测试区由 CS2 代理全文核 22 文件后同样报告零覆盖 |
| R7-CS1-15 | P1 | 问题/安全（原生跨界 use-after-free，**本轮已复现**） | `windows/src/Aegis.Windows.App/Broker/NativePolicyCoreBridge.cs:35`、`:164-251` （八个入口）→ 全部改走 `TryAcquireLease/ReleaseLease` 并入口检 `_disposed` | 现象：`AEGIS_REQUIRE_NATIVE_POLICY_CORE=1` 下跑 `Core.Tests`，测试主机进程崩溃 `0xC0000005`，栈顶是 `NativePolicyCoreBridge.CreateSession → InvokeTwoStrings → 跨界 trampoline`；崩溃前通过的用例数不稳定（667 / 403 两次），是终结器与调用竞态的典型签名。即 R7-CS1-04 记的「八个入口裸 DangerousGetHandle、不检 _disposed」不是潜在问题而是已可复现的原生越权访问。 | 影响/可利用场景：任何 GC 压力时点都可能让已释放的原生 broker 句柄被再次传给 DLL——正典 Windows 制品内的崩溃（含浏览器进程整体退出），且**没有任何门禁跑过这条路径**：required 的 `windows-contract-build` 跑 Core.Tests 时不设 `AEGIS_*` 环境变量（托管路径），唯一置位的 `native-policy-artifacts` job 只跑 Broker.Tests。 | 与既往关系：**R7-CS1-04 的实证升级**（同一缺陷从「注释失实 + 潜在」升为「已复现崩溃」）；并给 R7-CI-01「原生作业不在必需检查里」补了一条具体代价 |
| R7-TOOL-01 | `.github/workflows/release-windows.yml:91-99,108-131`、`native-policy-artifacts.yml:85-101` | `shell: pwsh` 步骤把**测试命令放在步骤中间**：`cargo test` 后接 `cargo build`+`Copy-Item`；两个 `dotnet test` 后接 `dotnet publish`。pwsh 包装只设 `$ErrorActionPreference='Stop'`，而原生命令非零不产生 PowerShell 错误 → 步骤退出码取末条原生命令 ⇒ **测试红、构建绿 ⇒ 步骤绿 ⇒ 唯一正典制品照常打包签名** | 本地 Windows PowerShell 5.1 实测：`$ErrorActionPreference='Stop'; cmd /c exit 3; Write-Host 'STILL-RUNNING'` → 打印 STILL-RUNNING 继续执行；PS 7.3 的 `$PSNativeCommandUseErrorActionPreference` 当时仍标注 experimental（默认 `$false`），Actions 包装脚本不设置它；同文件 `:149/:173/:175` 自己就用 `if ($LASTEXITCODE -ne 0) { throw }`——作者口径即不依赖自动失败。**残余不确定：需在 runner 上做一次故障注入定论；修复（逐条显式断言 `$LASTEXITCODE`）在两种语义下都正确** |

## 四、本轮 P2（31 条，已复核）

合并关系先列：`R7-SH-02 ≡ R7-CI-02`（同一条 paths 过滤问题，两个代理各自发现，
主代理合并为 R7-CI-02）；`R7-SH-05 ≡ R7-RS-06 ≡ R7-CS2-03`（向量单端消费，合并为
R7-SH-05，C# 侧覆盖率 2/15 由 CS2 代理量化）；`R7-SH-06 ≡ R7-CS1-08`（同一
`localhost:8080` 输入两组件结论相反，两个代理独立命中，主代理合并为 R7-SH-06）；
`R7-CS1-05 ≡ R7-CS2-01`（见 P1 节）。

| ID | 位置 | 现象 → 修复方向 |
| --- | --- | --- |
| R7-RS-01 | `core/.../ffi/broker.rs:324-329` | 核心黑名单 `denied.contains(host)` 精确匹配、无祖先域链；同仓 `adblock.rs:153-175`、C# `ThreatFeed.cs:47-63`、Python `threat_feed.py` 都是「精确 + 逐后缀」→ 订阅源以裸域登记的条目在核心侧只封字面那一条，`www.`/`api.`/任意子域放行。修：复用查询侧后缀链（不得反向展开条目，`ThreatFeed.cs:44-46` 已记载过度封锁教训）+ 补向量 |
| R7-RS-02 | `src/c_abi/mod.rs:31` + `navigation.rs:258` + `ffi/broker.rs:347` | `hosts_json` 受 `FFI_INPUT_MAX_BYTES=64KiB` 上限，而注入是**整批替换、无追加/分块**；托管侧订阅源允许 5 MiB（`ThreatFeed.cs:79`）→ 真实规模下核心名单必然注入失败（`ffi_input_too_long` → C# 记 `NotPublished`），出货 Windows 的核心侧 `threat_blocklist` 分支不执行。修：clear+append 两阶段或分块 + 补一条 >64KiB 负例 |
| R7-RS-03 | `core/rust-policy-core/bindings/aegis_policy_core.py` + `.github/workflows/contracts.yml:104-108` | 入库 Python UniFFI 绑定缺 `update_host_denylist`（最后一次重生成早于该入口）；`src/bin/aegis_uniffi_bindgen.rs` 自述「CI 必须生成绑定并检查漂移」，而 stale 门禁的 diff 目标只有 C#/Kotlin 契约生成目录，**不含 `bindings/`** → 声称的门禁不覆盖该文件 |
| R7-RS-04 | `src/c_abi/tests/export_surface.rs:13-34` | 导出面冻结集扫描 `../mod.rs`+`../navigation.rs`（12 项），全 crate 实际 `#[unsafe(no_mangle)]` 有 13 个：`lib.rs:53 aegis_policy_core_abi_version`（Android `NativePolicyCoreGate.kt:118` 真实绑定的符号）既不在清单也不在扫描集 → RS-310 的「导出面=契约不得静默变更」覆盖 12/13 |
| R7-RS-05 | `src/security_policy.rs:218-245` | `is_local_or_private_host` 窄于 C# 孪生 `UrlSafety.cs:183-200`：缺 100.64/10 CGNAT（含阿里云元数据 `100.100.100.200`）、192.0.2/24、198.18/15、224/4、IPv6 ULA/组播 → 核心把该段判「公网」，R6-21 的「SSRF 面在核心层被拦」对其不成立。修：补齐段集 + 向量 |
| R7-RS-07 | `src/ffi/broker.rs:280,361-399` | 高危导航每次都 `register_pending_approval`，过期回收仅在满 1024 时触发；子帧路径与未启用确认的宿主从不 approve/reject → 页面对 `127.0.0.1` 起量 iframe 可长期压满待审批账本，此后真实确认请求被 `approval_ledger` 自拒。修：登记前先回收 |
| R7-RS-08 | `fuzz/fuzz_targets/`（9 个） | 9 个 target 全部只喂 crate 内纯函数；`read_utf8` 的 64KiB 有界扫描、`parse_action` JSON 字段面、denylist 解析、归一后 host→私网判定这条真实链路零 fuzz 输入 |
| R7-RS-09 | `src/update_manifest.rs:220-232` | 注释称 ed25519-dalek **2.x** API，`Cargo.toml:33` 钉 `"3"`（同文件 `:245` 又自称 3.x）——按 2.x 语义改写验证链会引入静默行为变化 |
| R7-CS1-02 | `windows/.../WebView/HostWebView.cs:277-346` + `Broker/BrowserPolicyBroker.cs:111-133` | `AllowDownload` 只校验 KillSwitch/会话/标签，**下载 URL 从不查黑名单、也不判私网**（`DownloadPolicy.cs` 内无 host 逻辑）→ 远程页一个下载链接可把 `http://169.254.169.254/latest/user-data` 落盘。**这不是被否决的「Android 下载走 broker」**：Windows 下载已在 broker 上，本条只指出该门不看 URL |
| R7-CS1-03 | `windows/.../Broker/NativePolicyCoreGate.cs:47-73` | 门禁探测只要求 1 个导出（abi_version==3）即判 `Enabled()`，桥的建立要求 11 个导出全部解析（任一 `EntryPointNotFoundException` → `TryCreate` 静默 false）→「门禁过 + 桥不可用」自洽可达：每导航落 `bridge_unavailable` 全站拒，而启动 `[adjudication]` 日志已按门禁写下「导航由 Rust 核心裁决」，把排障方向指反。修：门禁按同一导出清单探测 + 桥 null 时写 `[adjudication] bridge_unavailable` |
| R7-CS1-04 | `windows/.../Broker/NativePolicyCoreBridge.cs:30-35` | 注释宣称「全部原生调用改走 `TryAcquireLease/ReleaseLease`，并在入口检 `_disposed`」，实测唯一消费者是 `UpdateHostDenylist`；8 个导航/审批入口仍直取 `DangerousGetHandle()` 且不检 `_disposed`，`IsUsable`（`:71`）全仓零引用＝伪装成守卫的死代码。当前不致 use-after-free 靠两条本文件零记载的对端前提（Rust `broker_free` 只置 retired 永不释放 + `Mutex` 内部可变），且 R6-26 已使「只有 UI 线程进入」假设失效（`ThreatFeedCoordinator.cs:53` 的 `Task.Run`） |
| R7-CS1-06 | `windows/.../WebView/HostWebView.cs:86-155` + `Chrome/TabRuntime.cs:92-110` | `_wired` 在 `:92` 置位，早于 141-148 的订阅、`:150` `WebView2Hardening.Apply`、`:154` KillSwitch 反应；`AllowExternalDrop=false` 在 `TabRuntime.cs:103` 更后 → 中途抛异常即产出「策略层看似在线、加固面全缺」的标签，而 fail-closed 守卫（R6-12）正因 `_wired` 已真而放行 |
| R7-CS1-07 | `windows/.../WebView/HostWebView.cs:359-366` | tracker 拦截已用聚合器收口 CS-308，**同一处理器里的黑名单分支每次命中逐条 `SecurityLog.Write`**（`lock + File.AppendAllText`，UI 线程同步盘 IO，1MB 轮转只留一份 `.1`）→ 含被拉黑子资源的页面即触发逐请求写盘并挤出取证行 |
| R7-CS1-11 | `windows/.../Broker/IBroker.cs:50-55` vs `Chrome/Ntp/` | `IBroker.KillSwitch` 设立理由写明「子资源/**桥**/下载必须与授权链同一个开关」；实测桥侧零判定（`Chrome/Ntp/` 下 `KillSwitch` 命中 0）→ 拉闸后已渲染的 NTP 顶层文档仍可驱动 `importBookmarks`/`importHistory`/`restoreSession`/`setEngine` 写本地数据 |
| R7-CS1-12 | `windows/.../Broker/BrowserPolicyBroker.cs:55-83` | `blockedHosts`/`killSwitch` 参数缺省分别落到 `NoBlockedHosts.Instance` 与 `new KillSwitch()`——即 R6-02 与 CS-291 两条已修缺陷的原始形态；今天靠两个生产调用点显式注入维持，无痕窗每次开窗都走字段初始器，新增第三个入口漏一个命名参数即静默复发（本仓同型已复发 ≥3 次）。修：缺省改共享单例 + 非共享时留痕 |
| R7-CS1-14 | `windows/.../Chrome/InPrivateWindow.xaml.cs:81-103` vs `MainWindow.xaml.cs:109` | 无痕窗构造 `TabRuntimeCoordinator` 却不订阅 `NtpNavigationFailed`，也无主窗「映射传播期抑制错误页渲染」分支 → 首页虚拟主机重试耗尽时用户看到 Chromium 原始错误文档。同文件同类不对称已修过 7 次（CS-349/358/378/384/393/402/411） |
| R7-AD-02 | `android/.../WebViewHardening.kt:182-199` | Android 手抄的 ToStringGuard 比另两端弱三档：未自注册 `Function.prototype.toString` 自身（Rust `tostring_guard.rs:89-93` 原文即「否则检测 toString 是否被覆盖本身即可识破防护」）、无 RS-252 的 typeof 校验/`proxyMap.has(original)` 拒链式/注入窗口后 `setTimeout` 锁死（`:106-124`）→ 一行 `Function.prototype.toString.toString()` 即暴露包装源码；且 `allowedOriginRules=setOf("*")` 下**任意远端页面可调用注册接口把自己的 hook 洗成 `[native code]`**（反检测逃逸原语） |
| R7-AD-03 | `android/app/src/androidTest/.../SmokeInstrumentedTest.kt:118` | 替换锚点 `getETLD1(location.hostname)` 在生产脚本中已不存在（R6-25 改成 `getETLD1(aegisTopLevelHostname())`，grep 命中 0），而 `WebViewHardeningScriptTest.kt:101-104` 还反向断言该串不得出现 → replace 恒为 no-op，`hardwareConcurrency` 已知答案断言不可能通过；`android-quality.yml` 只 `assembleDebugAndroidTest` 不执行 → 完全静默。AD-005/AD-067 声称的「JS 内嵌 SHA-256 与 Kotlin/Rust 逐字节验证」因此不再存在 |
| R7-AD-04 | `android/.../MainActivity.kt:77-85` vs `:98` | 版本检查协程在 `viewModel.init()`（`BrowserViewModel.kt:226` 才写 `appContext`）之前就已 `launch(Dispatchers.Default)`；后台先被调度则 `HostActivityBindings.kt:46` 的 `if (context == null) return` 整段缺席，而 `onCreate` 只此一次调用 → 与 R7-AD-01 叠加，过旧 WebView 提示双重失效。修：把协程移到 init 之后，或让调用方直接传 context |
| R7-AD-05 | `android/.../AegisHomeBridge.kt:179` + `SearchEngines.kt:188-202` + `broker/.../OriginPolicy.kt:104-110` | AD-303 的外跳 scheme 前置分型只落地址栏。首页搜索框：①`mailto:`/`sms:` 判 FORBIDDEN_SCHEME → `?: return` 零反馈静默；②`tel:100`/`geo:1` 被 `isPortSegment`（纯数字即端口段）判 DOMAIN → 归一为 `https://tel:100`，`isAcceptedHostShape` 不要求含点 → 放行到 WebView，表现为全屏「找不到服务器」错误面板。同一输入两入口两种行为 |
| R7-SH-03 | `tests/ui-regression/start_page.test.mjs:133-134` + `.github/actions/prepare-geogebra/action.yml:57-63` | `zip-slip` 断言是 **token 邻接**（`/zip-slip[\s\S]{0,220}sys\.exit\(1\)/`）而非行为：`bad = []`（containment 整条失效）后 `if bad:` 块与其中的 token、`sys.exit(1)` 原样保留 → 变异注入实测两条断言仍全绿 |
| R7-SH-04 | `tests/ui-regression/start_page.test.mjs:135-137` + `bandit.yaml:26` | 禁裸 `assert` 的正则是 `/^\s*assert\s+\S/m`，`assert(x)`（无空格）实测不匹配却仍是 `-O` 下被剥离的裸断言；且禁令只覆盖 `action.yml` 一个文件，同批 R6-16 修的 `scripts/migrate-profile-data/run.py` 无对应禁令，bandit 全局 `skips: ["B101","B404"]` ⇒ 活跃 Python 面无第二张网 |
| R7-SH-05 ≡ R7-RS-06 | `contracts/vectors/*.json`（15 个） | 主代理建消费矩阵：**只有 `url-origin-{valid,invalid}` 三端齐**。`native-navigation-*`/`approvals-replay-and-expiry`/`glob-match`/`update-manifest-*`/`action-*`/`capability-*`/`audit-event-*` 的 C#/Kotlin 消费点为 0（`Aegis.Windows.Core.Tests.csproj:24-28` 只链两个 JSON；Kotlin 仅 `OriginPolicyTest.kt`）；`validate_vector_schemas.py:15-18` 却自称这些「由 Rust/Android 一致性测试消费」 |
| R7-SH-07 | `contracts/codegen/validate_vector_schemas.py:80-85` vs `:129-132` | `invalid_vectors = (_load(...) if invalid_path.exists() else [])`：`update-manifest-invalid.json` 被删/改名时 deny_schema 双向断言整段消失且 **exit 0**；同文件对 action/capability/audit-event 六个向量却是「缺失文件计入 failures」——同文件内两套口径。另：invalid 向量的豁免完全以条目自述 `expected == "deny_schema"` 为准，无取值白名单 |
| R7-TOOL-03 | `release/update_verifier.py:126-146` | **R6-24 的孪生未回落**：Python 验证器 `valid_key_ids` 按 **key_id** 去重，同一把公钥以两个 key_id 登记即凑满 threshold=2；这是当前**实际执行**的那一份（`agent/broker.py` 引用），Rust 侧修好了而未接线的 `verify_threshold` 只是参考实现。修：按公钥字节去重 + 补「同钥双 keyid 拒 / 两真钥过」向量 |
| R7-TOOL-04 | `scripts/verify_vectors.py:86-88`、`verify_xaml_resources.py:26-31`、`check_file_sizes.py:114-118` | 空面即恒绿（代理在临时 git 仓实证 exit 0）：contracts 整树移除 → 「✅ 向量有效」；SRC 目录不存在 → 「0 个 x:Key」；无受管源 → 「扫描 0 个文件」。另 `verify_vectors.py` 的超长 URL 锚点按**文件名**匹配，同内容改名即静默失效 |
| R7-TOOL-05 | `scripts/check_file_sizes.py:120-125` | ratchet 记录的是**最后一次人工快照**而非历史最小值：文件缩到红线下而基线条目不删不收紧，其后涨回原额度仍绿（临时仓实证 350→1 行→涨回 350 行 exit 0）。本轮 PR #76 重建基线后现网 88 条与实测逐项相等（headroom=0），非既有违规，是机制洞。修：`lines < baseline[rel]` 即判「基线未同步收窄」，强制同 PR 重跑 `--write-baseline` |
| R7-TOOL-06 | `agent/tests/redteam_test.py:53-59,161-201`、`redteam_e2e_test.py`、`scripts/run-security-e2e/run.py:27` | R6-05 行为门全部用裸 `assert` 表达且保留不经 pytest 的 `__main__` 运行器：镜像注入「声明 deny 实 allow」后 `pytest`→1 failed、直跑→exit 1、**`python -O`/`PYTHONOPTIMIZE=1`→打印 ALL OK exit 0**（`python -O -m pytest` 仍红，故 CI 路径暂被兜住）。修：运行器首行 `if sys.flags.optimize: raise SystemExit(...)`，与 `agent/broker.py:35-37` 自订口径一致 |

| R7-CS2-04 | `windows/tests/Aegis.Windows.Broker.Tests/BrowserPolicyBrokerTests.cs:117-119,140-141,182-184,224-226,267-270` + `NativePolicyCoreDenylistTests.cs:115-116,164-165,182-184` | 8 条跨界/ABI 用例仍是「环境变量或 `NativePolicyCoreGate.IsRequired` 不满足 → `return` 记通过」形态；R6-13 的反假绿锚点只在**已声明原生模式**时生效，而「原生 job 确实声明了模式」这件事在仓库里无任何断言——唯一置位处是 `native-policy-artifacts.yml:85-88` 的 shell 赋值，与该 YAML 和 C# 常量之间零对账。修：照 `InstalledBuildMarkerTests.cs:179-198`（读 .iss 与 C# 常量逐字对账）的同法，加一条读 workflow YAML 断言两个 env 变量名字面值的用例 |
| R7-CS2-10 | `windows/.../WebView/FingerprintShield.cs:89-103` vs `core/rust-policy-core/src/shield.rs:103-111` | 两端各自手维护一份公共后缀表，集合**不同**：Rust 表含 `github.io`/`gitlab.io`/`pages.dev`/`vercel.app`/`netlify.app`/`appspot.com`/`blogspot.com`/`herokuapp.com`/`azurewebsites.net`/`cloudfront.net`，C# 表这些条目一个都没有（grep 零命中）。后果不是「噪声不同」而已：`user.github.io` 在 Rust 侧 eTLD+1 = `user.github.io`，在 C# 侧 = `github.io` → **同一用户下所有 GitHub Pages 站点共享一种子**，正是 CS-381 要防的跨站关联面；且无任何差集对账门禁 |

| R7-SH-06 ≡ R7-CS1-08 | `android/app/src/test/resources/search-normalize-vectors.json:2` + `SearchNormalizeVectorsTest.kt:18-22` vs `windows/.../Chrome/UrlNormalizer.cs:112-118,190-205` | 向量文件与其 Kotlin 注释都自称「Windows 测试面可直接引用同一 JSON（跨端单源）」，实测该文件在 `contracts/vectors/` 之外、**C#/Rust 零引用**（`git grep search-normalize-vectors` 只命中那个 Kotlin 测试），因此逃过向量消费门禁；同输入两端相反：向量把 `localhost:8000`/`192.168.1.1:8080` 钉成 **https**，C# 经 `IsExplicitLocalHostName`/`SchemeForLocal` 出 **http**（`UrlNormalizerTests.cs:62,174` 锁定）；`::1`/`[::1]:8080` 只有 C# 有分支；C# 剥控制字符与 `\`/`'`，Kotlin 不剥。修：迁入 `contracts/vectors/` 并由 csproj 链接逐条消费，对本机/私网 scheme 作显式单端裁决（核心已有 `is_local_or_private_host` 可作口径锚） |

## 五、P3 抽样（登记，不逐条复述）

R7-RS-09 · R7-CS1-08/09/10/13 · R7-CS2-05/06/07/08/09 · R7-AD-06/07/08/09/10/11/12 ·
R7-SH-08/09/10/11/12/13 · R7-CI-05/06/09/10/11/12/13/14/15 · R7-PY-09/10/11/12 ·
R7-TOOL-07/08/09/10。

其中两条由子代理定 P2、主代理降 P3，理由记入第七节：R7-CS2-05（三层测试「互斥」的
表述只有一半成立——`MainWindowLogicTests.cs:59` 实际与 broker 同侧拒绝，真实残余是
`WebViewPipelineTests.cs:106` 的升级豁免与 `UrlNormalizer` 本机分支成为**不可达死路径**
＋注释失实），R7-CS2-06（`expected == "allow"` 折叠对未来第四态才有风险，当前向量
只有 allow/deny 两值）。

值得单列的（都是「注释/文档与行为相反」，修复成本一行级）：
R7-CS1-09（`CoreDenylistPublisher` 注释承诺「每一次订阅源刷新」，实测 `Refresh`
只在 `Start()` 调一次，无周期计时器）、R7-AD-12（`TabManager.closeTab` 两条内联注释
与分支错配一格）、R7-TOOL-07（`agent/local-ipc/identity.md:19` 仍指向第六轮已连类
删除的 `E2EBroker`）、R7-CI-14（`README.md:124` 写「13 workflow」而 `:55` 已按 WB-214
改为 15，同文件自相矛盾；`:125-128` 的「常跑 7 个」口径与 R7-CI-02 的过滤面不完全一致）。

## 六、既往声明核验结论（本轮第二产出）

抽验既往标 ✅/已闭环条目 **34 项**（两代理重叠项已合并；RS/CS1/CS2/AD/SH/TOOL/CI 七个分区各自抽验）。
结论：**真闭环 15 / 部分闭环 17 / 虚闭环 2**（下表按行呈现，同族条目合并为一行，
故行数少于项数）。台账自称的闭环率只在按此修正后才可引用。

| 条目 | 判定 | 依据 |
| --- | --- | --- |
| R6-02 无痕窗黑名单 | **真闭环** | 两窗均注入 `SharedBlockedHosts.Shared`（`MainWindowDependencies.cs:40-42`、`InPrivateWindow.xaml.cs:28-30`）；全仓 `new BrowserPolicyBroker` 仅 2 处 |
| R6-03/AD-309 子帧 Allow 不 loadUrl | **真闭环** | `AegisWebViewClient.kt:188-192` + 测试 `verifyNoInteractions(view)`，未见回退 |
| R6-10 站点种子不外泄 | **真闭环** | `WebViewHardening.kt:338` 闭包内 const + 反向导出锚点 |
| R6-12 `TabRuntime.Navigate` fail-closed | **真闭环** | 全仓唯一写 `Control.Source` 在 `:253`，前置双闸 `:245`；6 个调用点全部经它；5 个 .xaml 无声明式 Source |
| R6-13 桥 Hub 单活约束 + 反假绿锚点 | **真闭环（Hub 结构）/ 部分闭环（反假绿）** | Hub：引用计数 + 归零才释放、失败不入缓存可重建（`NativePolicyCoreBridgeHub.cs:31-78`）。反假绿锚点本身是硬断言（`BrowserPolicyBrokerTests.cs:137-163`），但它只在**已声明原生模式**时生效，而声明来源只有 workflow 里一行 shell 赋值、与 C# 常量零对账 → R7-CS2-04 |
| **CS-418 contracts 向量 C# 全量消费** | **部分闭环** | 「全量」实为 2/15（`Aegis.Windows.Core.Tests.csproj:24-29`）；`expected` 折叠为布尔 → R7-CS2-06；`native-navigation-*` 的 C# 拒绝码与向量不同名（向量 `session_not_found` ↔ C# `session_context`，`nonce_replay`/`action_not_issued`/`action_binding_mismatch` 在 C# 全树零命中——`TryConsumeNavigation` 只返回裸 `bool`，失败既无码也不留痕） |
| **CS-379 / CS-380 / CS-381 指纹噪声三项** | **部分闭环** | 逐像素 PRNG、三出口、PSL 表存在性均有文本断言（`FingerprintShieldTests.cs:127-169`），但 CS-381 的目标语义（跨站不可关联）在 iframe 场景仍不成立 → R7-CS1-05；且 C# 与 Rust 的 `PUBLIC_SUFFIXES` 是两份手维护清单、集合不同且无差集对账 → R7-CS2-10 |
| R6-22 InstalledBuildMarker 两判定源 | **真闭环**（另有第三处不一致） | 门禁与确认门共用同一标记键单源；但门禁判据（1 导出）≠ 桥判据（11 导出）→ R7-CS1-03 |
| R6-26 托管快照发布进核心 | **真闭环（结构）** | 单点收敛 + 桥新建补推 + 两窗共用一个桥；「全进程唯一收敛点」仅由调用点约定维持 → R7-CS1-12 |
| AD-213 / AD-252 | **真闭环** | `OriginPolicy.kt:104-105,129-151` + 向量全量消费 |
| BUG-005 画板两次失效 | **真闭环** | 成因①`sys.exit(1)` 显式化 + `grep -Fx` 入口断言；成因②白名单 `file://` 直载不经 broker |
| CS-337 UrlRedactor userinfo 剥除 | **真闭环** | `Core/Security/UrlRedactor.cs:23` 走 `Scheme+Authority+AbsolutePath`；`UrlRedactorTests.cs:27-47` 四条**精确等值**断言（非 Contains/非 NotEmpty），IPv6 方括号另有一例 |
| CS-412 XAML 绑定静态锚 | **真闭环**（有 P3 口子） | `XamlBindingStaticAnchorTests.cs:40-65`，未映射宿主出现新绑定即红（`:50`）、目录缺失显式 throw（`:126`）；撞名与嵌套绑定两个口子见 R7-CS2-09 |
| CS-414 壁纸双向差集对账 | **真闭环** | `NtpBridgeTests.cs:271-276` 正反两向 `Assert.Empty` + 布局定位失败显式 throw |
| CS-398 / CS-397 死事件与死方法注记 | **真闭环** | `SettingsService.cs:83` 删除说明 + 反射锚 `Assert.Null(GetEvent("Changed"))`；`HistoryStore.cs:244-248` 如实标注生产零调用 |
| CS-312 `Contracts/Generated` 移出编译 | **真闭环** | `Aegis.Windows.App.csproj:44-52` `<Compile Remove>`；漂移仍由 `verify_contract_compatibility.py:85-123` 的 schema↔模型 diff 兜住（故「C# 无 ContractAlignmentTest」不构成缺口） |
| **R6-14 门禁 paths 过滤** | **部分闭环** | 只删了台账点名的 2 个文件；ADR-007 D3 清单里的 6 个门禁 workflow 中仍有 4 个带 `push.paths`（agent-redteam/ci/core-rust/supply-chain）→ R7-CI-02 |
| **R6-18 签名身份 pin** | **部分闭环** | Android 侧 tag fail-closed + 身份对账齐备（未回退，实测四分支）；Windows 正典安装包两者皆无，缺证书即 `Write-Warning; exit 0`，且 `signing-identity.txt` 的 `AUTHENTICODE_SHA256` 无任何 CI 消费者 → R7-CI-03 |
| **R6-20 FFI 通路落内容判定** | **部分闭环** | 只落 host 黑名单一条出口；`PolicyEngine`/`CapabilityRegistry` 在 FFI 通路仍零调用（H-7 注记原文未撤，`src/broker.rs:17-22`），且该唯一出口有两个规模性洞（父域语义 R7-RS-01、64KiB 注入上限 R7-RS-02） |
| **R6-21 高危判定落核心、不依赖端侧** | **部分闭环** | 子帧阻断属实；但高危集窄于 C#（R7-RS-05）、Android 出货构建自行兑换顶层 `RequireConfirmation`、Windows 在托管层先硬拒私网使核心高危分支对 Windows 不可达 |
| **R6-24 按公钥字节计票** | **部分闭环** | Rust 修复本身真落且有测试；但被修的 `verify_threshold` 生产零调用者，实际执行的 Python 验证器仍按 key_id 计票 → R7-TOOL-03 |
| **R6-25 顶层站种子框定** | **部分闭环** | 只落 Android；Windows 未回落（R7-CS1-05），且 Android 唯一的跨语言已知答案验证因锚点失效而不再执行（R7-AD-03） |
| **R6-07 URL 脱敏单源** | **部分闭环** | 修的是 `credential_guard.redact_url`（零调用者），仍带 userinfo 泄漏形态的 `mcp.py:80-89` `_redact_url` 没修 → R7-PY-01 |
| **R6-09 静默 fail-open** | **部分闭环** | 异常路径已留痕，但加固翻转整段仍被 `if dnt_enabled:` 包住，另有两处无留痕静默出口 → R7-PY-02 |
| **RS-310 C ABI 导出面冻结** | **部分闭环** | 13 个真实导出冻结 12 个 → R7-RS-04 |
| **AD-211 deny detail 泄敏 / AD-303 tel: 分型 / AD-297·314 ToStringGuard / BUG-006 通配守护 / CS-388 升级豁免** | **部分闭环** | 各见 R7-AD-02/05、R7-CS1-08 与下表「推翻」条 |
| **契约门禁「真实模型对账」（第六轮注释宣称）** | **虚闭环** | 表与注释落了，函数与接线没落 → R7-SH-01 |
| **「全部原生调用改走租约守卫」（NativePolicyCoreBridge 注释宣称）** | **虚闭环** | 8 个入口未改、`IsUsable` 零引用 → R7-CS1-04 |

## 六之二、本轮核对为「非问题」的形态（写下来防下一轮重复报）

- **C# 确实读同一份向量**，不是自带副本：csproj `Link="contracts\vectors\…"` + `..\..\..\`
  上溯仓库根；文件缺失/为空时 `File.ReadAllText` 在 MemberData 枚举期抛出 ⇒ 用例红而非静默跳过。
  三处仓库布局定位助手全部显式 `throw`。
- `windows/tests/**` 全树无 `Skip=`/`Assert.Skip`/`[Trait]`/`ClassData`/`DataRow`；
  `Assert.NotEmpty` 仅 2 处且均伴随实质内容断言（`NtpBridgeTests.cs:274` 前置双向差集、
  `UtilityClassesTests.cs:165` 后随 `Assert.All`）。
- 两套件 `xunit.runner.json` 均 `parallelizeTestCollections: false` ⇒ 构造期清空环境变量的
  用例与原生锚点用例之间无并串扰。
- `AuditRegressionTests.cs:134-137` 的 InlineData 含真实控制字符（`cat -v` 证实未丢失），非空断言。
- `Contracts/Generated` 六个 record 是生成数据模型而非桩实现，不作缺陷。
- 归档栈 R6 四处修复（threat_feed 两处 scheme、credential_guard、mcp `-32004`、
  native_hardening fail-closed）**逐条回读确认未回退**；R6 之后仅 `1ffd2cb` 一次提交触及该目录。
- PR #76 的测试外迁**未丢断言强度**（RS 代理独立方法学核验：五个模块的 `fn` 名集合差 0、
  断言宏计数逐模块相等 74/68/82/148/164，行多重集差异全部可解释为换行合并与 `use` 改写）。

## 七、推翻与降级（子代理误读记录，供校准）

| 主张 | 裁决 | 理由 |
| --- | --- | --- |
| R7-SH-02「ci.yml paths 过滤致守卫漏跑」定 **P1** | **降级 P2** | 4 个门禁 workflow 的 `pull_request` 面全部无过滤（`core-rust.yml:18`、`supply-chain.yml:29` 为 `pull_request: {}`）→ 走 PR 时 9 个必需上下文照跑。真实盲区只有「管理员直推 master」，而 `enforce_admins=false` 本身已使直推不经任何检查（R7-CI-04），过滤没有新增独立洞。另 ADR-007 D3 正文与 4 处现存过滤互斥，属**口径失实**（并入 R7-CI-02 修复项） |
| R7-CI-01「原生作业未列 required 是 P1 缺陷」 | **降级 P2** | 这是上一轮**有记录的自觉取舍**：`native-policy-artifacts.yml` 带 `pull_request.paths`，若直接列 required，不触 `windows/android/core` 的 PR 会永久卡 `Expected`（当时的排除理由已写入 PR 说明）。本条的价值在于给出两条可执行收口路径（删过滤后再列 required，或把原生模式锚点用例复制进已 required 的 `windows-contract-build`），不是新发现的疏漏 |
| R7-CI-03「Windows 未签名发布定 P1」 | **降级 P2** | 缺证书即 `exit 0` 是第六轮写在 `release-windows.yml:152-155` 注释里的**自觉决策**（与 Android keystore 区分）。真实缺陷是 `signing-policy.yaml:5,42-44` 仍宣称「所有制品必须签名/fail_closed/all」——**声明与实现相反**。改成 tag 即拒属发布流程行为变更，需用户裁决，不顺手改 |
| R7-AD-06「document-start 注入失败无状态上抛」定 P2 | **降级 P3** | 现象属实（只 `Log.w/e`，且 document-start 接线本身零测试），但 Android 端本仓尚无出货 APK，也无既有测试声明其「必须上抛」；按「重要补测 + 可观测性」归 P3 |
| R7-CS1-01/02 由代理自评 P2 | **升级 P1 / P2** | 见第三节：正典出货物上，导航层已声明的边界在子资源层与下载层不成立——按「控制可绕」而非「提升」计 |
| R7-CS2-05「三层测试互斥，用户必然踩分裂体验」定 P2 | **降级 P3** | 回读后发现三方并不全互斥：`MainWindowLogicTests.cs:59` 锁的是 `CanOpenNewWindowLink("http://192.168.1.1/admin") == false`（**与 broker 同侧拒绝**）。真实残余是 `WebViewPipelineTests.cs:106` 的 HTTPS 升级豁免与 `UrlNormalizer` 本机分支成为**不可达死路径** + `UrlSafety.cs:226-230` 注释仍称"用户明确要求能力"——按死路径/注释失实定 P3，产品裁决需求另列第八节 |
| R7-CS2-06「`expected` 折叠使 C# 一条腿自证失效」定 P2 | **降级 P3** | `UrlOriginVectorTests.cs:58-60` 的折叠确为事实，但当前 url-origin 向量只有 `allow`/`deny` 两值，拼错的 `denyy` 折叠后仍要求 deny（判定结果不变）；真实风险面是**未来第四态**（`require_confirmation`）出现时才会静默。补测类，定 P3 |
| R7-CS2-02「新增安全控制零测试」由代理定 P1 → **维持 P1** | 保留 | 与一般「补测」不同：`private_network` 是**纯托管层拒绝码**，核心向量里没有它，全仓零判定锚；且同一条边界已被 R7-CS1-01/02 证明在子资源与下载两层缺失。回归即静默移除 SSRF/CSRF 门禁，符合「门禁失效」口径 |
| 「`dist/native-policy` 的预编译 DLL 已入库，早于新符号」 | **推翻（本轮由子代理提出，主代理证实）** | `git ls-files` 命中 **0**，`.gitignore:39` 全局忽略 `dist/`；全仓不跟踪任何可执行/库类二进制
（`git ls-files` 下 dll/so/exe/a/lib/pdb **0 个**），受管二进制只有 10 个图片/字体资产与
`android/gradle/wrapper/gradle-wrapper.jar`（后者已钉 `distributionSha256Sum` +
`validateDistributionUrl=true`）。CI 两条链均从 `core/` 现场构建。**故第六轮台账与本轮任务清单里「已入库 DLL 走降级路径」的表述在仓库层面不成立**——真实情形是「本机工作副本里有旧产物，本地跑走降级」。已按此修正条目 |
| 「BUG-006 通配规则回归有守护」 | **部分闭环（推翻其证据）** | `start_page.test.mjs:143` 的断言作用在 `allScripts = HOSTJS+MAINJS+SNAKE+IMPORT`（`shared/shell/*.js`，见 `:18-23`）上，而 `setOf("https://*", "http://*")` 是 **Kotlin 源**里的写法——正则扫的是永远不会出现该 token 的语料 ⇒ 断言恒真。Android 侧亦无 `allowedOriginRules` 断言。代码本身正确（`WebViewHardening.kt:39-44` 用 `setOf("*")`） |

## 八、本轮未覆盖 / 需下一轮或需用户裁决

1. **Windows 契约/测试区无运行态证据**：（本轮 B3 已闭合，见第十节「B3 落地」末段——
   不加 `-r win-x64` 即可跑通，Broker 128/128、Core 708/708。以下保留派发时的原始记录：）
   `dotnet test -p:RestoreLockedMode=true`（未加 `-r win-x64`）
   报 NU1004——`packages.lock.json` 的 RID 是 win-x64（`Directory.Build.props` SP-220 自述该约束），
   `--no-build` 命中的是 2026-09-07 陈旧产物（177 例，与台账 708 例不可比）。该区所有结论均为
   静态判定，**未声称任何测试通过**；`packages.lock.json` 未被改写（`git status` 干净）。
   下一轮要拿该区运行基线，需在 CI 里跑或本地按 `-r win-x64` 跑后立刻 `git restore` 锁文件。
2. `docs/**` 其余 88 个 Markdown 的陈述与代码一致性未逐篇核（本轮只核了
   README/SECURITY/ADR-007/signing-policy/identity 五处，见 R7-CI-08/14、R7-PY-07、R7-TOOL-07）。
3. 真机与安装态验证仍缺（`[adjudication]` 日志行、无痕窗经桥、下载/子帧、SmartScreen、第二账户）。
4. **需用户裁决的 4 项行为变更**（不是缺陷，不动）：Windows tag 发布缺 Authenticode 证书是否
   fail-closed；服务端 `strict=true` / `enforce_admins=true` / 至少 1 名评审是否开启（单人仓库
   下 `required_pull_request_reviews` 等于自锁）；Android 顶层导航是否停止客户端自行兑换；
   此前已否决的 FLAG_SECURE / 退出清 Cookie / IDN / Android 下载走 broker 维持否决。
5. `contracts/schemas/*.json` 8 份 schema 正文语义未逐条审。

## 九、建议修复批次（文件所有权互斥，供下一轮派发用）

批次划分的依据是「同文件不得并行」与「每批都有可失败的门禁可验证」：

| 批 | 内容 | 触及文件 | 验证方式 |
| --- | --- | --- | --- |
| B1 发布链退出码 | R7-TOOL-01：三条 pwsh 步骤逐命令显式断 `$LASTEXITCODE`，或整步改 `shell: bash` | `release-windows.yml`、`native-policy-artifacts.yml` | 故障注入：把某步第一条命令改成必然失败者，观察步骤是否转红（当前不红即为实证） |
| B2 门禁可失败化 | R7-SH-01（`check_real_models`/`check_mirror_consumption` 落地或删表并改注释）、R7-SH-03/04（行为级 zip-slip 回归 + `assert\b` 正则 + 扩面）、R7-SH-07 / R7-TOOL-04 / R7-TOOL-05（空面 exit 2、锚点去文件名、ratchet 收窄强制）、R7-TOOL-06（`-O` 守卫） | `contracts/codegen/*`、`scripts/*`、`tests/ui-regression/start_page.test.mjs`、`agent/tests/*` | 每项都要先注入失效证据再声称修好；禁止「加了断言但写不出失败用例」 |
| B3 隐私网络边界补全 | R7-CS1-01/02（子资源 + 下载两层复用同一谓词）、R7-CS2-02（补 `private_network` 行为用例含豁免与端口形态） | `windows/.../WebView/HostWebView.cs`、`Broker/BrowserPolicyBroker.cs`、`windows/tests/**` | `dotnet test`（须先解决第八节 1 的运行基线问题） |
| B4 种子框定三端对齐 | R7-CS1-05 ≡ R7-CS2-01（C# 与 Rust `shield.rs` 改顶层 eTLD+1；两处反向锚点改性质断言）、R7-CS2-10（PSL 清单单源化 + 差集对账）、R7-AD-03（androidTest 锚点复原并补「锚点必须命中生产脚本」断言） | `FingerprintShield.cs`、`shield.rs`、`FingerprintShieldTests.cs`、`WebViewHardening.kt`、`SmokeInstrumentedTest.kt` | cargo test（Rust 侧）+ node/pytest 静态锚；C#/Kotlin 侧只能静态断言，须如实声明 |
| B5 核心语义与孪生对齐 | R7-RS-01（父域后缀链）、R7-RS-05（补 CGNAT/TEST-NET/基准/组播段）、R7-RS-02（denylist 分块/追加 + >64KiB 负例）、R7-TOOL-03（Python 按公钥字节计票） | `ffi/broker.rs`、`security_policy.rs`、`c_abi/navigation.rs`、`contracts/vectors/*`、`release/update_verifier.py` | 向量三端 + `cargo test` + `pytest`；改语义必须先补向量再改码 |
| B6 单端项与端侧收口 | R7-AD-01/02/04/05（版本阈值、ToStringGuard 三项加固、启动次序、首页 scheme 分型）、R7-CS1-03/04/06/07/11/12/14、R7-SH-06（本机 scheme 三处对齐——**先取用户裁决**） | `android/**`、`windows/**`（与 B3/B4 同文件者须串行） | Android 只能静态；Windows 侧同 B3 |
| B7 口径与文档真相 | R7-CI-02/03/04/08/14、R7-PY-07/10、R7-TOOL-07/08、R7-RS-09、R7-CS1-09、R7-AD-12 | `.github/**`（仅注释与触发面）、`README.md`、`CLAUDE.md`、`SECURITY.md`、`signing-policy.yaml`、`legacy/**` 文档 | `check_markdown_links.py` + 新增「workflow 计数/清单对账」门禁 |

**批次内不得并行的理由**：B3 与 B4、B6 都改 `HostWebView.cs`/`BrowserPolicyBroker.cs`；
B4 与 B6 都改 `WebViewHardening.kt`。同文件并行必冲突，按表内串行次序派发。

**需用户裁决后才动的三项**（不列入上述批次）：Windows tag 发布缺 Authenticode 是否
fail-closed；服务端 `strict`/`enforce_admins`/评审要求；本机与局域网浏览是否继续支持
（决定 B3/B6 的谓词方向与三处死路径的处置）。


## 十、落地状态（同轮续）

| 批 | 状态 | 备注 |
| --- | --- | --- |
| **B1** | **已落地** | `release-windows.yml`（cargo test / 两条 dotnet test / verify_versions）与 `native-policy-artifacts.yml`（cargo build / dotnet test）逐条显式断 `$LASTEXITCODE`；新增 `scripts/check_workflow_shells.py` 作常跑门禁（挂进 `contracts.yml` 既有 required job，不新增 context 名，避免 merge box 卡 `Expected`），带 `--self-test` 故障注入自证。**本地实证**：PS 5.1 下「原生命令中段失败 + 后续命令成功」实测步骤 exit=0（输出只剩 `publish ok`），加断言后 exit=1。runner 侧 pwsh 7 语义的最终定论仍待一次 CI 故障注入——修复在两种语义下都正确。 |
| **B2** | **已落地** | 六项全部收口：R7-SH-01（`check_real_models` / `check_mirror_consumption` 真正接进 `main()`，capability 误接映射按实测删除并留注释，17 条新用例逐个钉失败分支）；R7-SH-03（zip-slip 改**行为级**回归——真跑恶意 zip，另加一条对照用例证明「把判定掏空后旧 token 锚仍全绿」）；R7-SH-04（`` 正则覆盖 `assert(x)`；活跃树非测试 Python 全面禁令，实测当下 0 命中 ⇒ 是防腐而非补票）；R7-SH-07（invalid 向量缺失改无条件 fail-closed + `expected` 取值白名单 + 反向对照）；R7-TOOL-04（三门禁加空扫描面非零退出 + 锚点去文件名化）；R7-TOOL-05（基线未同步收窄即判失败——新规则当场抓出 3 处 stale，实降 507→503 / 692→691 / 477→450）；R7-TOOL-06（**删除两份红队套件的手工运行器**：`-O` 全绿的根因是「手工收集裸 assert」这个形态本身，唯一入口改 pytest，`run-security-e2e` 相应改为驱动 pytest 并拒绝 `-O`）。 |
| B3 | **已落地** | 见本节「B3 落地」。 |
| B5 | **已落地** | 见本节「B5 落地」。 |
| R7-TOOL-02 | **已落地** | 见本节「R7-TOOL-02 落地」——第九节批次表漏排的 P1，B3/B5 之后仍红，故未等排期直接补做。 |
| B4 | **已落地** | 见本节「B4 落地」。 |
| R7-CS1-15 / 04 | **已落地** | 根因是**镜像被卸载后仍可能调用其内函数指针**（崩溃转储模块列表零命中 aegis_policy_core.dll），不只是缺租约：镜像常驻 + 八个入口全走 `InvokeLeased` + `IsUsable` 接成入口判据 + 原生作业补跑 Core.Tests。原生模式 711/711 三轮全绿（修复前中止点 667/403/389/502 不稳定）。见「R7-CS1-15 / R7-CS1-04 落地」。 |
| B8 本机/内网可浏览 | **已落地** | 见「B8 落地」——用户裁决「本机与内网要能打开」，私网拒绝改为仅拦保留/元数据/组播/广播/文档段。 |
| R7-AD-01 | **已落地** | 见「R7-AD-01 落地」——第八个 P1 就此收口；阈值取版本名口径，不可解析 fail-closed 到提示侧。 |
| B6/B7 | 未动 | 见第九节。B6 的三项与 B7 的部分需先取得用户裁决（第八节 4）；B6 与 B3/B4 同改 `HostWebView.cs`/`WebViewHardening.kt`，须串行。 |

### B4 落地（种子框定三端对齐 + 后缀清单单源 + androidTest 锚点）

R7-CS1-05≡R7-CS2-01：C# 与 Rust 的站点键都改成**顶层框定**——新增与 Android
逐字同口径的 `aegisHostFromOrigin` + `aegisTopLevelHostname`（`location.ancestorOrigins[0]`
→ host，取不到才保守退回本帧 hostname，绝不因顶层链失败而放弃噪声）。两端原先
正向断言缺陷字串（`FingerprintShieldTests.cs:117` 断言
`getETLD1(location.hostname)`、`shield.rs` 断言 `contains("location.hostname")`），
现改为性质断言：必须经 `aegisTopLevelHostname()`、必须出现 `var anc = location.ancestorOrigins;`、
**缺陷调用形态出现即红**。

R7-CS2-10：新增 `contracts/policy/public-suffix-list.txt`（79 条 = 三份手抄表
54/51/31 的并集，实测数字）为唯一权威。Rust 端 **`include_str!` 现算生成**（零手抄，
编译期读取——核心运行期无 I/O 的约束不破）；C#/Kotlin 各持一份内嵌副本（不额外发布
数据文件、不改打包），由新门禁 `contracts/codegen/verify_seed_framing_parity.py`
逐项对账并挂进必需的 contracts job。门禁另有 `--self-test` 四类植入漂移（Kotlin 少一条 /
C# 多一条 / Rust 回退手抄 / C# 退回本帧口径）全部检出，`tests/python/seed_framing_parity_test.py`
12 例含「解析塌陷判 exit 2」「注释顶不掉要件（要件取代码形态）」「门禁挂在常跑 job 里」。

R7-AD-03：`SmokeInstrumentedTest.kt` 的锚点从已被淘汰的 `getETLD1(location.hostname)`
改指生产实际形态，并新增「**锚点必须命中生产脚本**」断言——此前 replace 恒为 no-op，
known-answer 不可能通过，而 android-quality 只 assemble 不执行 ⇒ 全程静默。

**落地过程中被实证抓到的两个自身缺陷**（都留下常驻锚点，不是口头修正）：
① `format!` 里写 `{psl}` 时花括号被当插值吞掉，产出 `var AEGIS_PUBLIC_SUFFIXES = 'co.uk': 1, …`
——三端产物 dump 后 `node --check` 当场报 SyntaxError；两端各加常驻锚（花括号/圆括号配平 +
「表体必须是对象字面量」），Rust 侧生成函数改为自带花括号。
② 门禁自证用 `write_text(encoding=…)` 未带 `newline=""`，把 CRLF 工作副本改写成 LF——
即「门禁自己污染源文件」；现按 `newline=""` 读写并**逐字节校验还原**，还原失败即判失败。

验证：cargo 561+10+4、fmt/clippy 干净；Core.Tests **711/711**、Broker.Tests 128/128；
`pytest tests/python` 383 passed；`run-security-e2e` ✅；active-tree ruff/bandit ✅；
`check_file_sizes` ✅（shield.rs 524→322，测试外迁 `shield/tests.rs` 300 行；
FingerprintShield.cs 399 持平，种子素材拆入 71 行的 `FingerprintShield.Seed.cs`；
WebViewHardening.kt 636 持平——表体 reflow 净零）；三端 JS 产物 node --check 全通过。

未验证：新框定在真实 WebView2/WebView 第三方帧上的行为（需安装态/真机——本批只有
结构与纯函数量级的证据）；`ancestorOrigins[0]` 即最顶层祖先这一前提沿用 Android 侧
既有口径，未另行在设备上复核。androidTest 仍不被 CI 执行（只 assemble），如实保留。

**PR #82 首跑 CI 红（本地全绿）——已闭合并把成因做成常驻门禁**：`contract-source-of-truth`
报 `TypeError: Path.read_text() got an unexpected keyword argument 'newline'`。
根因是解释器版本面漂移：本地跑 3.14，workflow 钉 `python-version: 3.12`，而
`Path.read_text` 的 `newline` 关键字是 3.13 才加的——同族缺陷（只在高版本成立的写法）
此前无任何扫描。处置：两处改用 `open(path, newline="")`；新增
`scripts/active_tree_gates.py compat`（与 ruff/bandit 同一目标面，扫 63 个文件，
空扫描面判 exit 2，注释列不违规、3.12 已成立的 `write_text(newline=)`/`open(newline=)`
不误报），挂进必需的 contracts job；`tests/python/py312_compat_test.py` 11 例钉
「每条规则自带命中的违规样例」「规则数==样例数」「CI 钉版不得分叉（现为 3.12 单一值）」
「植入违规必被检出」。这类「本地绿、CI 红」的代价本应由门禁承担，而不是由一次 PR 失败承担。



### B3 落地（隐私网络边界补到子资源与下载两层）

**（本节的边界口径已于同日按用户裁决改版，见「B8 落地」——`PrivateNetworkBoundary`
已改名 `ReservedAddressBoundary`，本机与内网改为放行；下文保留建立时的原始描述。）**

谓词从 `BrowserPolicyBroker.IsNonPublicNavigationTarget` 提纯为单源
`Broker/PrivateNetworkBoundary.cs`（`Denies(Uri)` / `DeniesRaw(string)` / `DenyCode` / `Reason`
四个成员一处定义），四类出口全部接上：原生前置（`BrowserPolicyBroker.cs:230`）、托管导航
（`:258`）、消费点复判（`:358`）、下载（`:124` `AllowDownload` 此前从不看 URL）、子资源
（`HostWebView.cs:364` 与黑名单同一 403 分支，命中来源写进日志以便归因）。

R7-CS2-02 的零断言空洞由 `PrivateNetworkBoundaryTests` 33 例补上（谓词矩阵 14 形态：
127.0.0.1/localhost/192.168.1.1/169.254.169.254/10/8/`[::1]`/`0177.0.0.1`/100.64/10 +
公网与宿主虚拟主机对照 + 「非默认端口与明文的 `.local` 不豁免」；三类出口的拒绝码与审计
留痕；伪造授权在消费点被复判拒绝）。**可失败性实证**：把 `AllowDownload` 的边界判定与
`OnWebResourceRequested` 的谓词调用各替换成一条恒假表达式后重跑 → 6 例转红
（4 条下载 + 1 条不可判定 + 静态锚），随后逐项还原；静态锚断言 broker 内 ≥4 处调用、
且子资源处理器体内必须出现该调用，专门防「只定义不接线」（R6-26 失效形态）。

**运行基线缺口就此闭合（更正第八节 1）**：`dotnet test --configuration Release`（不加
`-r win-x64`、不加 `RestoreLockedMode`）在本树可直接跑通——Broker.Tests 128/128、
Core.Tests 708/708 首次取得运行态证据；代价是构建会剥掉 `packages.lock.json` 的
`net10.0-windows7.0/win-x64` 节，必须随即 `git checkout` 还原（本轮两次踩到并还原）。
行数红线同 PR 收窄 556→549 / 604→584，为此把 `HostWebView` 的拦截落盘接线（CS-308/CS-363）
拆出 `HostWebView.TrackerBlocks.cs`（partial，逻辑零改动）。子资源层的 403 与下载层的
落盘抑制仍只能静态判定（需真实 CoreWebView2 COM 环境），如实登记。

### R7-CS1-15 / R7-CS1-04 落地（原生跨界：租约纪律 + 镜像常驻 + 原生模式门禁入口）

**根因不是"没加租约"这一条**。崩溃转储（`dotnet test --blame` 采集，502 例通过时中止）
的模块列表里 `aegis_policy_core.dll` **已不在场**——AV 来自「调用已卸载镜像中的函数指针」：
委托（`_createSession` 等）指向镜像地址，其生命周期与某个桥实例并不一对一（桥可被
Dispose/终结，委托却被另一个仍在用的桥持有；门禁探测另有 TryLoad/Free 配平）。
原 `NativeLibraryHandle.ReleaseHandle` 只处理了 CS-376 的「Free 抛异常」，
未处理「Free 成功本身才是缺陷」。

三层处置：

1. **镜像常驻**：`ReleaseHandle` 不再 `NativeLibrary.Free`（进程退出由 OS 回收映射）；
   SafeHandle 形态保留（IsClosed/IsInvalid 语义不变）。
2. **租约纪律**：八个原生入口全部经 `InvokeLeased<T>`——先 `TryAcquireLease()`
   （`DangerousAddRef`）再在租约内读 `Broker`，取不到租约即 fail-closed
   （bool→false，Decision→`native_policy_core_disposed`）；裸指针获取点全文件**只有一处**
   （`return operation(Broker);`），入口自行取指针不再可能。
3. **死守卫接上**：`IsUsable` 此前全仓零引用（注释把它写成守卫），现作为
   `TryAcquireLease` 的入口判据——R7-CS1-04 由「注释失实 + 潜在」实质收口。
4. **门禁入口补上**：`native-policy-artifacts.yml`（唯一置 `AEGIS_REQUIRE_NATIVE_POLICY_CORE=1`
   的作业）原样只跑 Broker.Tests——Core.Tests 从未走过跨界路径，这正是崩溃藏了五轮的原因。
   现加 Core.Tests 原生模式一步，并按 B1 口径显式断 `$LASTEXITCODE`。

**证据**：修复后原生模式 Core.Tests **711/711 连跑三轮全绿**（修复前实测中止点不稳定：
667 / 403 / 389 / 502，是终结器与调用竞态的典型签名）；Broker.Tests 托管 140/140、
原生 140/140；托管 Core.Tests 711/711。
**因果实证（故障注入）**：把 `NativeLibrary.Free` 单行加回 → 原生 Core.Tests 第 45 例即
中止；再改回常驻 → 同一条命令 711/711。故"镜像常驻"一项的因果成立，不是顺带改。
**常驻锚**（`NativePolicyCoreBridgeLeaseTests` 12 例，源码静态锚——运行期无法稳定复现
GC 时序，把它当唯一防线就是假保证）：八个入口逐个必须含 `InvokeLeased(`；
`_brokerHandle.DangerousGetHandle()` 代码行计数必须为 1 且位于 `InvokeLeased` 内、
`Broker,` 计数必须为 0；`IsUsable` 必须有消费者；`NativeLibraryHandle` 的 ReleaseHandle
不得再出现 `NativeLibrary.Free`；workflow 必须在置位原生开关后跑 Core.Tests
且其后有 publish 步（防退出码被吞的老形态）。行数：`NativePolicyCoreBridge.cs` 480→433
（互操作面拆入 `NativePolicyCoreBridge.NativeInterop.cs` 94 行）。

**残余**：镜像常驻意味着本进程的 DLL 不卸载——若将来要求可卸载（例如热替换策略核心），
必须先把「委托 → 镜像」引用做成显式计数，而不是回到 FreeLibrary。



### R7-TOOL-02 落地（第九节批次表漏排的唯一 P1）

第九节的批次表把 R7-TOOL-02 漏了——B1 收 TOOL-01、B2 收 SH/TOOL 四项、B5 收 RS/TOOL-03，
`agent/broker.py` 的契约必填面不在任何一批里，因此在 B3/B5 落地后它仍是红的。本条按
「可执行项不等排期」直接补做：

- 新增 `agent/action_contract.py`：required 集、method enum、origin pattern、minLength
  **全部从冻结 `action.schema.json` 现算**（手抄第二份字段表就是新的漂移面）；schema
  读不到或结构不合预期即 `ActionContractError`，broker 拒绝构造。`ACTION_SCHEMA_PATH`
  此前是**导出却零引用**的死常量（与 B2 抓到的两张死契约表同型），现由本模块真正读取。
- `evaluate()` 增 `deny_schema`（与 `contracts/vectors` 既有词汇一致）；刻意放在
  `deny_session/scope/canonical/generation` 之后——具体码优先，既有口径一字不改，只补
  从未覆盖的形状面。`proposed_action_from_dict` 的必填面改取
  「dataclass 无默认字段 ∪ schema required」，于是省略 `expires_at` 的载荷在构造层就拒。
- `well_formed_action` 工厂补上 `expires_at`/`policy_version`：此前"well-formed 底座"
  自身就不合契约，红队夹具把「不带 expires_at」钉成 **allow 对照**——门禁反向保护缺陷
  的原始形态，现改钉 `deny_schema`，并新增 origin（`file:///C:/secrets`、
  `javascript:alert(1)`）、method（`ARBITRARY`）、空 nonce/空 tab_id 的伪造型。
- `redteam_test.py` 的 `DENY_EXPECTS` 由手抄 15 码改为从 `Decision` 现算——否则新增拒绝码
  会静默不被夹具承认（本次就是撞上这一点才发现的）。
- `scripts/run-security-e2e/run.py` 由逐文件驱动两份红队套件改为驱动整个 `agent/tests`
  目录：逐文件列举会让新增套件静默地不被安全 e2e 跑到。
- 新锚 `agent/tests/action_contract_test.py`（38 例）：判定面逐字等于 schema、
  **改写 schema 副本可移动门禁**（反证非硬编码）、逐个 required 字段省略/置空绝不放行、
  bool 冒充 integer、五种坏 schema 结构 fail-closed、以及「broker 真的调用了门禁」的
  静态锚。**可失败性实证**：把门禁改成 `... and False` 并把构造层必填面退回旧形态 →
  78 例中 58 例转红，随后逐项还原。
- 顺带闭合四处文档失真：三个 fixture README 自称「本目录仅含设计说明、独立 fixture
  待外置」（实际 `fixtures.json` 四个都在且由 broker 真判）、`action-planner-contract.md`
  的示例 `expires_at` 是 2027 年（超 `max_ttl` 必被拒——已注明"仅示意形态"）。
  `agent/broker.py` 红线 446→445。

### R7-AD-01 落地（Android WebView 版本阈值：编码量级错一个数量级 → 恒判"版本安全"）

旧实现 `MIN_SAFE_VERSION_CODE = 132_000_000` 直接与 `getLongVersionCode` 比较。真实
ASW 的 longVersionCode 是**十位量级**——本仓自己的 `WebViewVersionCheckProviderTest`
就用 `141_000_7390L` 表示 `141.0.7390.0`——于是 1.32×10⁸ 反推回去只约等于 m40 时代，
任何能跑 minSdk 26 的设备恒判安全，`MainActivity` 声明的 CVE-2026-12438/11295 提示在
全部出货设备上静默为零。

处置：判定改取**版本名的数字段**（`MIN_SAFE_MAJOR = 132` / `MIN_SAFE_BUILD = 0`），
不再依赖各发行版并不一致的后缀编码；`parseVersion` 支持厂商后缀
（`141.0.7390.163-bugfix`）与两段形态（`132.0`→build 0），**不可解析一律 fail-closed 到
"提示更新"侧**（绝不因为读不懂版本名就宣布安全）。`parseVersion` 单 return、无常量魔数
（detekt `ReturnCount`/`MagicNumber` 当场抓到过）；`isOutdated(WebViewVersion)` 取代
`isOutdated(Long)`。

验证：`:app:testDebugUnitTest`（WebViewVersionCheckTest 10 例 + ProviderTest 6 例）全绿、
`:app:ktlintCheck` 与 `:app:detekt` 全绿。**因果实证**：把 `isOutdated` 退回
`version.code < 132_000_000L` → `atOrAboveSafeMajorIsNotOutdated` 与
`decisionNeverReadsVersionCode` 两例转红；还原后重新全绿。新用例里
`decisionNeverReadsVersionCode` 专门钉住旧失效方向：给"十位 longVersionCode + 过旧版本名"
的组合（`118.0.1997.106` / `1_180_199_710L`）必须仍判过旧。

残余（不假称已核）：阈值取 m132 沿用仓库既有声明——CVE-2026-12438/11295 的**确切**
修复版本需按 Google 安全公告核对，本轮无法离线核实，故只修"编码量级"这一确定缺陷、
不新增我无法验证的公告号；真机上 provider 版本读取与提示对话框呈现仍未验证（无设备）；
R7-AD-04（检查协程早于 `appContext` 初始化的启动竞态）另计，未随本条动。



### B8 落地（2026-10-04 用户裁决：本机与内网必须能打开）

裁决内容：**GitHub 仓库不开评审要求**（单人推送，开了等于自锁——只做不需要审批的那部分）；
**本机地址与内网一律允许打开**。因此 B3 建立的「本机/内网/链路本地默认拒绝」需要收口成
「只拦根本不是任何设备的地址形态」，而不是继续全量私网拒绝。

- `PrivateNetworkBoundary` → **`ReservedAddressBoundary`**（改名以免类名与口径相反），
  拒绝码 `private_network` → `reserved_address`；四类出口（原生前置导航、托管导航、
  消费点复判、下载、子资源 403）仍共用同一谓词单源。
- **放行**：127/8 与 `::1`、`localhost`、10/8、172.16/12、192.168/16、100.64/10
  （CGNAT/Tailscale）、`fc00::/7`（ULA）、`*.local`/`*.internal` 主机名（mDNS 的 NAS/
  打印机）、宿主自有 `ntp/geo.aegis.local`。宿主虚拟主机豁免分支随之删除——主机名形态
  本来就不再被拒，留着会误导。
- **仍拒**：169.254.0.0/16（链路本地，含云元数据 `169.254.169.254`）、`0.0.0.0/8` 与 `::`
  未指定、224/4 组播、255.255.255.255 广播、240/4 保留、`fe80::/10`、`ff00::/8`、
  TEST-NET-1/2/3 与 198.18/15 基准段、IPv4-mapped 形态、取不到 host 的不可判定输入。
- **编码变体按更严一侧判**（实测平台差异）：`.NET` 把 `http://2852168190/` 的 host 归一成
  `170.0.161.254`，而 Chromium 按 inet_aton 解析成 `169.254.169.254`（元数据端点）——
  只看归一后的 host 就是留一条绕过路，故对**原始 authority** 是纯数字或 `0x` 形态的一律拒；
  `UrlSafety` 的两个归一化器由 private 改 internal 复用（零行变动，不破红线）。
- 测试面同步改版：`ReservedAddressBoundaryTests` 55 例（托管与原生模式下各跑一遍均全绿）——矩阵 34 形态（含八进制
  `0251.0376.0251.0376`、十进制整数、简写 `169.254.1`、IPv6 zone/组播/mapped），
  并单列 `LocalAndLanTargets_AreOpenableByRuling` 钉住裁决本身（防后来者把「SSRF 加固」
  理解成「恢复私网拒绝」而静默改回），静态锚另加「源码里不得再出现 private_network /
  PrivateNetworkBoundary」，杜绝两条面分叉。

**已知代价（不假称已封）**：阿里云元数据端点 `100.100.100.200` 落在按裁决放行的 CGNAT 段内；
本机/内网服务本身仍会以用户身份被远程页面访问（导航/子资源/下载三层都放行），只剩黑名单与
用户确认这一层拦——高危目标（含 `127.0.0.1:*`）仍走 Rust 核心的确认域，需用户点一次确认。

验证：Broker.Tests **162/162**、Core.Tests **711/711**（托管）；`check_file_sizes` ✅
（新文件 137 行；`HostWebView.cs` 584、`BrowserPolicyBroker.cs` 549 均持平或收窄）；
`check_markdown_links` ✅。Android 与 Rust 侧本批零改动（Rust 核心的
`is_local_or_private_host` 只驱动「高危需确认」，不做拒绝，故与本裁决不冲突）。

### B1 落地当天即抓到一个被吞掉的真实失败
`Build Windows x64 policy DLL` job 补上 `$LASTEXITCODE` 断言后立刻变红：`BrowserPolicyBrokerTests.NativePolicyCoreBridgeRequiresApprovalBeforeConfirmationNavigationCanConsume` 断言 `RequireConfirmation` 而核心回 `Allow`（1 失败 / 86 通过）。根因是 R6-21 把确认域收窄为「仅高危目标」后，该用例仍拿 `https://example.com/…` 期望确认——**它自第六轮起一直是红的**，被「测试红 + 后续 `dotnet publish` 绿 ⇒ 步骤绿」与「该 job 不在必需检查里」两层叠加吞掉。

处置：用例按既定口径改用 `http://127.0.0.1:8080/…` 触发确认域，并新增**公网 host 不得触发确认**的对照断言（此前 C# 侧对 R6-21 的收窄零锚点，正是 R7-CS2-02 指出的空洞）；本地以现建 DLL 实跑 87/87 通过，并用假路径做反证（该用例转红）以证明它真走了跨界路径。

### B5 落地（PR 见提交历史）

R7-RS-01 父域后缀链（展开只在查询侧，向量含两条近似 host 对照与一条「条目祖先域不得预展开」）、R7-RS-05 补齐 CGNAT/TEST-NET/基准/组播四段（14 条向量，每段左右两侧都有公网对照，防过度收紧；IPv6 如实记为归一层之外而非假称已补）、R7-RS-02 注入改 `clear` 两阶段 + C# 按 60KiB 切批（就地加参不改符号名与 ABI v3，故以应答 `clear` 回显为唯一探针，缺回显即中止并记前缀规模）、R7-TOOL-03 把「按公钥字节计票」回落到**真正执行的那份** Python 验签器、R7-RS-04 导出面 13/13、R7-RS-09 注释版本改述。
**过程收获**：B1 的退出码断言让原生模式的真实红灯第一次可见，顺带复现出 R7-CS1-15（`0xC0000005`，见 §三）。新增 `NativeDenylistChunkingTests` 8 条纯函数用例补上「C# 分块无入库测试」的空洞；`release_tools_test.py` 的 13 处 reflow 用 token 级 difflib 逐处核对为纯换行（语义零变化）。

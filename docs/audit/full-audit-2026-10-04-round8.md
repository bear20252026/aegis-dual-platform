# 第八轮全量审计（2026-10-04）·9 分区并行 + 逐条回读复核 + 第七轮闭环声明核验

审计对象：`aegis-dual-platform` @ master `880df86`（PR #77–#85 已并入，工作树干净）。
方法：分区并行派发只读子代理（文件所有权互斥，输出契约强制 `文件:行号 + 严重级 +
影响场景 + COVERAGE`）→ 主代理对每条 P1 与「将进入修复批次的 P2」逐条回读代码复核
→ 第七轮台账自称的「已落地」逐条三态核验。**未经主代理回读的条目一律不进登记表**，
只列入第十一节「待复核队列」。本轮主诉求按用户提法调整为「有什么**升级**的地方」，
因此除缺陷外单列第八节升级面清单（依赖/工具链/一致性/门禁）。

## 一、真实源码规模基线（决定分区粒度）

按 `git ls-files`（受管 720 文件）收口，排除：`legacy/` 只读归档栈 80 文件、
生成物 12 文件（`Contracts/Generated`、`contracts/generated`）、二进制与资产 31 个、
`docs/` 90 个 Markdown、锁文件与 `dist/`。

| 语言 | 文件 | 行数 |
| --- | --- | --- |
| C# | 130 | 21,517 |
| Rust | 79 | 20,348 |
| Kotlin | 85 | 14,925 |
| Python | 63 | 13,931 |
| HTML | 3 | 2,373 |
| JS | 6 | 2,284 |
| Node 回归（.mjs） | 8 | 2,112 |
| XAML | 10 | 1,710 |
| CSS | 1 | 393 |
| Gradle KTS | 6 | 617 |
| PowerShell | 1 | 54 |
| **合计（活跃源码）** | **392** | **80,264** |

配置/契约面（受管、非「源码」但受门禁管辖）：JSON 39/3,988、YML 22/3,703、
YAML 4/195、TOML 4/306。

## 二、分区与 COVERAGE 汇总（置信边界）

| 分区 | 前缀 | 负责面 | 全文读 | 主要未读面（置信边界） |
| --- | --- | --- | --- | --- |
| 依赖与工具链 | R8-DEPS | csproj/props/lock、Cargo、gradle catalog、requirements-ci、action pin | 23 个清单/配置文件全量 + 上游注册表逐个查证 | `requirements-ci.txt` 锁体 hash 字面值、cargo-audit 之外的 composite 细节 |
| Windows 安全层 | R8-CS-SEC | `Broker/` `Chrome/` `WebView/` | 48 文件全量 | 无（该区结论均为静态，运行态项已标「需 CI/真机」） |
| Windows 数据层与测试 | R8-CS-CORE | `Core/` `Contracts/` `windows/tests/` | 测试面为主，Core 关键类全量 | `Core/` 其余展示/存储类的逐行判读为抽样 |
| Rust 策略核心 | R8-RS | `core/rust-policy-core/**` | **补上第七轮自认未读的 4.3K 行指纹/JS 生成族**（36 文件全量） | 部分测试子模块（用 grep 抽样断言强度，未逐行） |
| Android | R8-AD | `android/**` | 4 模块主源集 + **补读 26 个 JVM 测试全文与 detekt.yml** | contracts 生成物、res 正文 |
| 活跃 Python | R8-PY | `scripts/` `release/` `contracts/codegen/` `agent/` | 30+ 脚本全量 + **补读 requirements-ci.txt 逐条结构** | legacy 归档栈（按分区纪律不入面） |
| 共享壳与契约 | R8-SH | `shared/` `contracts/schemas|vectors` `tests/ui-regression/` | **补读 7 份 schema 正文全量** | `contracts/vectors/` 其余 12 份逐条入参、`snake.test.js` |
| CI 与供应链 | R8-CI | `.github/**` 根配置 | 15 workflow + 4 action 全量 + required checks 只读取证 | workflow 历史 run 的日志正文 |
| 文档与架构主轴 | R8-DOC | README/CLAUDE/SECURITY/ADR/product/runbooks | 24 份现行文档全量 | `docs/` 20 份带时代横幅的历史调研稿 |

**未覆盖面如实声明：本轮不是「全仓 100%」**。两处抽样口径：R8-CS-CORE 的 `Core/`
展示层、R8-RS 的部分测试子模块；R8-DOC 未逐篇核 `docs/` 全部 76 份 Markdown。
运行态证据一律不声称——本轮**未运行任何**构建/测试/lint/门禁脚本（项目验证纪律
「本地只编辑、云端跑门禁」），唯一的本地执行是纯静态盘点与只读 HTTP 查证。

## 三、本轮 P1（7 条，主代理逐条回读确证）

| ID | 位置 | 现象 → 修复方向 | 主代理确证方式 |
| --- | --- | --- | --- |
| **R8-CS-SEC-01**（≡R8-DOC-02） | `windows/.../WebView/HostWebView.cs:498-508`、`WebView/NavigationConfirmationGate.cs:14-22`、`Broker/InstalledBuildMarker.cs:35-51`、`Broker/BrowserPolicyBroker.cs:214-238`、`contracts/vectors/native-navigation-decision.json:101-131` | 出货 Windows 制品里，核心返回的 `require_confirmation` 被**静默丢弃**：确认门 `IsRequired` 出厂为 false（安装器刻意不写 `RequireNavigationConfirmation`），于是 `decision is not Allow → return false`，既不发 `NavigationDenied` 也不弹面板。向量把 `https://127.0.0.1:8080`、`https://localhost/panel`、`http://192.168.1.1/set_config` 钉为 `require_confirmation`，而原生模式（安装器写 `RequireNativePolicyCore=1`）走的正是桥返回的那一份决策 ⇒ **用户按「本机与内网必须能打开」的裁决（第七轮 B8）在唯一发布制品上不成立，且零提示** | 逐行回读四处：确认门面只认环境变量与注册表两个来源；`EvaluateNavigation` 在 `_nativePolicyCoreRequired` 分支直接 `return nativeDecision`（不经托管侧 B8 放行路径）；向量原文 14 条 `require_confirmation`；`InstalledBuildMarker` 注释里「Windows 两点已硬拒本机＝死路径」的前提已被 B8 自己拆除 |
| **R8-AD-01** | `android/webview-adapter/src/main/kotlin/.../AegisWebViewClient.kt:446-461`、`app/.../SearchEngines.kt:150`、`app/src/test/resources/search-normalize-vectors.json:20-21`、`app/src/main/res/xml/network_security_config.xml:16` | 同一裁决在 Android 端也**未落地**：任何 `http` 无条件升 `https`（无本机/私网豁免），无 scheme 输入一律补 `https://`（向量把 `localhost:8000`、`192.168.1.1:8080` 钉成 https），叠加 `cleartextTrafficPermitted="false"` 且无 `domain-config` 例外 ⇒ 路由器/NAS/dev-server 的 http 地址得到 SSL 失败或 ERR_CONNECTION_REFUSED 全屏错误。`classifyWithScheme` 的 T1 分支注释自称「开发/内网最高频输入形态」，却把它升级到不可达的 scheme | 回读升级函数全文 + `normalizeInput`/DOMAIN 分支 + 向量原文 + NSC 全文（确认无 domain-config）；第七轮 B8 落地段自述「Android 与 Rust 侧本批零改动」 |
| **R8-RS-01** | `core/rust-policy-core/src/shield.rs:209-220, 245-251, 272-278`（测试 `src/shield/tests.rs:154-181`） | canvas 噪声「逐像素混合」（RS-249）在数学上**恒退化**：三枚常数 `0x9E3779B1/0x85EBCA6B/0x27D4EB2F` 全为奇数 ⇒ `Math.imul` 乘积最低位＝操作数最低位，而 `i += 4` 使字节偏移恒为偶 ⇒ `(seed ^ imul(i,K)) & 1 ≡ seed & 1`，对每个像素、每个通道都相同 ⇒ 全图同一 ±1 偏移，**有效熵 1 bit**，试 2 个候选即确定性还原真画布，canvas 哈希仍是可归一的稳定标识符（该机制要消除的东西正被它自己发放） | 主代理独立复算奇偶性并核 `i += 4` 步进；核旧测试为 token 断言（`assert_eq!(script.matches("Math.imul(i, 0x9E3779B1)").count(), 3)`）——字符串层面永远发现不了；对照 Android `WebViewHardening.kt:371-377`（用像素序号 ⇒ 2 相位、三通道恒等，窄但不退化）与 Windows `FingerprintShield.cs:155-162`（mulberry32 有逐像素性但 `& 0xff` 回绕、无像素上限） |
| **R8-AD-02** | `android/app/proguard-rules.pro:38` ↔ `android/broker/src/main/kotlin/com/aegis/broker/NativePolicyCoreGate.kt:105,117` | AD-219 的 keep 规则写成 `com.aegis.broker.NativePolicyCoreGate$NativePolicyCoreAbi`（嵌套形态），但该接口是**顶层 private interface**（object 在 `:105` 已闭合，`:117` 缩进为 0），真实二进制名 `com.aegis.broker.NativePolicyCoreAbi` ⇒ 规则命中 0 个类 ⇒ R8 改名 ⇒ JNA 按方法名查符号失败 ⇒ `LinkageError` 折叠为 `Unavailable` ⇒ 门禁 block ⇒ 每次远程导航拒 `native_policy_core_unavailable`；首页是 `file://` 不经 broker，形态是「进程存活 + 首页正常 + 所有网站打不开」，**恰与 beta.51/52 的启动存活型冒烟口径互补** | 回读源文件行号与缩进；核 `broker/detekt-baseline.xml:8,20` 对 Bridge 记作带点号嵌套、对 Gate 记作裸名（同仓反向印证）；核 `v2.2.0-beta.52` tag 内 `release-android.yml:175-177` 确实带 `-PrequireNativePolicyCore=true` 且 `app/build.gradle.kts:187 isMinifyEnabled=true`。**运行态未取证**：是否已在现网 APK 上真的全导航拒绝，需 `mapping.txt` 或 minified release 真机远程导航；本批按「静态确证的不匹配 + 常驻门禁」处置 |
| **R8-CI-01** | `.github/workflows/release.yml:9,200,207`；服务端 `GET /environments/release` | `release` 环境实测 `protection_rules: []`、`can_admins_bypass: true`、`deployment_branch_policy: null`——发布链上**没有任何人工检查点**，而 release.yml 头注与 :200 步骤名、`docs/runbooks/release-checklist.md` 都写「受保护环境审批」。持有 write 的凭据推一个 `v*` tag 即：三平台构建 → verify-gate → 直接把 19 个制品发到公开 Release（Android 用库内合法 keystore 真签，身份 pin 必然通过）。tag ruleset 的 creation 规则对 admin `bypass_mode=always`，不构成阻挡 | 主代理亲自执行只读 `gh api repos/.../environments/release` 取证（与 CI 分区结论一致）；未做任何写操作 |
| **R8-CI-02** | `.github/workflows/legacy-python-guard.yml:72-82,129-137` | job 在 `windows-latest` 且步骤**未写 `shell:`** ⇒ 默认 pwsh；三条 pip 与八条 `selftest_*.py` 均无 `$LASTEXITCODE` 断言 ⇒ hash 锁安装失败被后续 dev 锁安装覆盖（环境已坏仍绿，下方 ruff/bandit/mypy 跑在错工具链上），前七条自检任一失败被第八条的成功盖掉。根因是 B1 门禁 `check_workflow_shells.py` 只扫显式 `shell: pwsh`（见 R8-CI-03），故这类形态对门禁完全不可见 | 回读两段步骤原文与 job 头；并以新扫描器对**修复前**的该文件实扫 → 报 9 处违规（可失败实证） |
| **R8-DOC-01** | `README.md:24-26`；`.github/workflows/release-android.yml:213-216` | README 称「Android 发布 APK 把确认开关关闭后由客户端自行兑换一次性 nonce，故高危确认流**两端均未生效**」——HEAD 上 `assembleRelease` 已带 `-PrequireNavigationConfirmation=true`（第六轮 607d7a1 恢复启用），确认面板是活代码 ⇒ 该句现为失实。定级保留 P1 但**修正子代理口径**：对已发布的 `v2.2.0-beta.52` tag 该句仍成立（查证：该 tag 内 assembleRelease 只有 `requireNativePolicyCore=true`，无 confirmation 标志），属**文档滞后于第六轮改动**，而非「从来就是错的」 | 主代理 `git show v2.2.0-beta.52:.github/workflows/release-android.yml` 与 HEAD 版逐条对比；回读 `android/broker/build.gradle.kts:54-61` 的 buildConfig 接线与 `check(!requireNavigationConfirmation || requireNativePolicyCore)` 约束 |

**合并关系**：`R8-DOC-02 ≡ R8-CS-SEC-01`（同一事实的文档面与代码面）；
`R8-PY-01 ≡ R8-CI-03`（同一门禁脚本的扫描面问题，两个分区各自发现）；
`R8-RS-01 / R8-CS-SEC-04 / R8-AD-04` 属同一「canvas 噪声三端不同口径」根因的三面。

## 四、本轮 P2 中已回读确证的条目（进入修复批次的部分）

| ID | 位置 | 现象 → 处置 | 裁决 |
| --- | --- | --- | --- |
| R8-CI-03 | `scripts/check_workflow_shells.py:83,87-92,44-49` | 四类结构性盲区：`job["shell"]` 不是合法键（真实为 `defaults.run.shell`）、windows 隐式 pwsh 不进面、`& "tool.exe"` 形态不匹配、composite action 不在面内；命令表缺 ruff/bandit/mypy/pip-audit/nm/readelf/unzip/tar；且「扫描 workflow 文件数」而非 pwsh 步骤数，0 个步骤也 exit 0 ⇒ 已随 B1 全修（含空面 fail-closed + 7 种形态故障注入） | 保留 P2 |
| R8-SH-10 | `.github/workflows/ci.yml:17-25` | SP-235 给 `ci.yml` **新加** `push.paths`，而该 job 的断言语料有 9 处在该清单之外（含它亲自守护的 `.github/actions/prepare-geogebra/action.yml`）；ADR-007 D3 明列 `ci` 为须零过滤的门禁型 ⇒ 属 R7-SH-02/R7-CI-02 的**回潮实例** | 保留 P2 |
| R8-PY-02 | `contracts/codegen/validate_vector_schemas.py:118-121`；`scripts/verify_vectors.py:39` | 「空面即绿」的第二形态：invalid 侧缺 `manifest` 键 `continue` 静默跳过（同文件 valid 侧 `:104-106` 却记 failure，两套口径）；`MIN_FILES` 数**文件**不数**条目**，把任一 vectors 数组清空 ⇒ 循环 0 次、exit 0 | 保留 P2 |
| R8-PY-08 | `scripts/check_markdown_links.py:79-85,122-135` | `resolve_target` 不做仓库根包含性判定（`](/../../Windows/win.ini)` 解析到仓外、本机存在即判可达）；`main()` 无 `checked == 0` 判定（扫描 0 个 .md 也打 ✅） | 保留 P2 |
| R8-RS-02 | `core/rust-policy-core/src/shield.rs:160-181` | `aegisCanvasSeed()` 的会话种子混入循环以 `etld1.length` 为界 ⇒ hostname 取不到（`about:srcdoc` 派生 worker、opaque origin）时循环零次执行，种子退化为**与会话无关的常量**（跨用户跨站同噪声，反成「Aegis 用户」共享标识符）；另 worker 内 `WorkerLocation` 无 `ancestorOrigins` ⇒ 第三方帧的 worker 退回本帧 host（R7-CS1-05 的缺陷形态从 worker 出口复活） | 保留 P2；常量退化已随 B2 修，worker 顶层域下发属核心接口缺口（R8-RS-15） |
| R8-AD-09 | `android/broker/src/test/.../AndroidBrokerTest.kt:159-170` | 子代理判「`if (BuildConfig.REQUIRE_NATIVE_POLICY_CORE) {assertFalse} else {assertTrue}` 两分支都记通过 ⇒ 常规门禁里不可能失败」。**主代理回读后降级**：那是**变体自适应**断言——默认变体断「放行托管 Broker」、置位变体断「block + 拒绝码」，任一侧被破坏都会红。真剩下的缺口只有两条，且都属接线/语义边界：①「置位变体确实被跑过」只由两个 workflow 的 `--tests` 字符串撑着，删参数即整套原生门禁语义在发布链里静默消失而 JVM 用例全绿；②置位变体跑在 JVM 宿主（x86_64 Linux）加载 arm64 `.so`，验的是「核心不可得即关闭」而非「核心缺失/ABI 失配」 | **降级 P2→P3**：接线缺口由 B3 的 `NativeGateWiringAnchorTest` 静态钉住；运行态覆盖缺口并入 R8-AD-06。附带教训见第六节第 2 条 |
| R8-CS-SEC-04 | `windows/.../WebView/FingerprintShield.cs:155-162` | 三端唯一使用 `& 0xff` 回绕（0→254、255→1：视觉伪影 + 一行检出判据）、且无 Android AD-270 那条像素上限守卫（8K×8K ⇒ 6.7×10⁷ 次闭包分配 + 268MB ImageData 复制，页面可低成本冻结渲染进程） | 保留 P2，已随 B2 与双端同公式 |
| R8-CS-SEC-08 | `HostWebView.cs:493,506-512,527-533`；`BrowserPolicyBroker.cs:343-346,364-366` | 6 条 `return false` 静默出口（consume 失败、代际推进失败、ProbeGate 失败、桥为 null）既不发 `NavigationDenied` 也不写审计码——这些恰是授权链内部不一致（nonce 重放/代际漂移/会话销毁）的唯一信号，全部表现为「导航无反应」；另 `:366` 有 `return false;            lock (…)` 行合并排版 | 保留 P2（待回读补全其余出口清单后实施） |
| R8-CS-CORE-1 | `windows/tests/**` ↔ `BrowserPolicyBroker.cs:135,241,286,303,317` | 5 个生产拒绝码在测试全树零字串锚点（`session_context`/`download_session_context`/`native_confirmation_core_required`/`confirmation_rejected`/`native_policy_core_disposed`），现有用例只断 `is Type<Decision.Deny>` ⇒ 改码不红 | 保留 P2 |
| R8-RS-13 | `core/.../src/ffi/mod.rs:219-228`、`src/util.rs:160-172` | FFI 尺寸防线覆盖 URL/scope/domain 却**漏 `session_seed`**：`hex_seed_to_bytes` 先 `hex_decode`（对任意长度 `with_capacity(len/2)` + 全量扫描）再判长度 ⇒ 宿主传 1 GiB 十六进制串即拿到一次 512 MiB 分配；uniffi 面 `update_host_denylist(Vec<String>)` 无条目数/单条长度上限 | 保留 P2（C ABI 面有 64KiB `read_utf8` 兜住，uniffi 面兜不住） |

## 五、既往声明核验结论（本轮第二产出）

### 5.1 第七轮 8 个 P1 的三态复核（抽样回读，非全量）

| 条目 | 判定 | 证据 |
| --- | --- | --- |
| R7-TOOL-01（pwsh 退出码） | **部分闭环** | 点名的 5 处断言在位（`release-windows.yml:93-135,165,189-191`、`native-policy-artifacts.yml:78,96,102`），新门禁确挂 required job（实测 contexts 含 `contract-source-of-truth`）；但扫描器四类盲区（R8-CI-03）使 `legacy-python-guard.yml` 两处同型残留存活五轮 ⇒ 「修了点名处，同型面仍在」 |
| R7-TOOL-02（Agent 契约判定面） | **真闭环 + 新旁路** | `action_contract.py:113-158` 确从 schema 现算、夹具由 allow 改钉 `deny_schema`、手工运行器已删；但判定面**只遍历 `required`**——把 `"origin"` 从 required 摘掉（pattern 保留）即整段消失且全部门禁仍绿（R8-PY-03，未回读队列） |
| R7-TOOL-05（ratchet 收窄强制） | **真闭环** | `check_file_sizes.py:126-133`；主代理独立复算基线 88 条与当前工作树逐条相等，无 stale（只读行数统计） |
| R7-SH-01（镜像消费门禁） | **部分闭环，且修复自身复现同一形态** | `check_real_models`/`check_mirror_consumption` 确接进 `main()`；但 `DESIGN_NOTATION_MIRRORSS` 6 条目恰等于全部 6 个镜像名 ⇒ `_has_real_consumer()` 现行仓库零次被调用，「无消费方即红」判定面为空集（R8-SH-08） |
| R7-CS1-04/15（原生跨界租约 + 镜像常驻） | **真闭环（静态层面）** | `NativePolicyCoreBridge.cs:42-96` 租约 + 八入口 `InvokeLeased` + `Denylist.cs:55-79` 第 9 入口 `finally` 归还；`NativeInterop.cs:28-45` `ReleaseHandle` 不再 `NativeLibrary.Free`。台账的运行态结论（711/711 三轮全绿）本轮未复核也不推翻 |
| R7-CS1-05 ≡ R7-CS2-01（种子顶层框定） | **真闭环** | `FingerprintShield.cs:93-115`、`shield.rs:145-171`、`WebViewHardening.kt:328-338` 三端同口径；PSL 单源 + 双向差集对账；C# 侧反向锚 `Assert.DoesNotContain("getETLD1(location.hostname)")`。但**噪声算法**三端仍各异（R8-RS-01/CS-SEC-04）——即「框定对齐了，扰动强度没对齐」 |
| R7-RS-01/05（父域后缀链 / 段集补齐） | **真闭环** | `ffi/broker/denylist.rs:51-67` 展开只在查询侧 + `policy_host_of` 同源；`security_policy.rs:249-268` 四段齐 + 14 条左右对照向量 + IPv6 如实记为归一层之外 |
| R7-CS2-02（拒绝码行为断言） | **部分闭环** | `ReservedAddressBoundaryTests` 55 例 + 静态锚 headroom=0（删任一即红）；但该类全部断言走 `ManagedBroker()`，**原生前置分支 `BrowserPolicyBroker.cs:230` 零行为断言**（R8-CS-CORE-2）；另 5 个其余拒绝码仍零锚（R8-CS-CORE-1） |
| R7-AD-01（WebView 版本阈值） | **真闭环** | 阈值取版本名口径、不可解析 fail-closed 到提示侧，可达链逐段核过（`MainActivity.kt:80` → `BrowserViewModel:189-191` → `HostActivityBindings:42-49`），且锚在 CI 真跑的 JVM 测试里 |
| R7-AD-02/04/05/12、B6/B7 全部 | **未闭环（与第七轮自述一致，非虚报）** | `WebViewHardening.kt:185-188` 三项加固全缺 + `:44 allowedOriginRules=setOf("*")`——本轮实测**已从「潜在」升级为「现网即泄」**：`window.fetch` 被三次包裹，默认形态下 `fetch.toString()` 取到的就是含 `[Aegis] CWS request intercepted` 字样的注入脚本文本，不需攻击者先调注册接口（R8-AD-02 分区记录，待主代理逐行回读） |
| B8（本机/内网可打开） | **部分闭环，且落地方式与文档相反** | 三端只 Windows 改了托管侧拒绝面；核心仍把这些 host 判高危 ⇒ 出货 Windows 静默取消（R8-CS-SEC-01）、Android 升 https 不可达（R8-AD-01）。台账 B8 段写的「需用户点一次确认」与两端实际行为都不符 |

### 5.2 文档/门禁声明对账（抽核结论）

| 声明 | 判定 | 关键证据 |
| --- | --- | --- |
| 「裁决收敛在无 I/O 的 Rust 核心（单一裁决源）」 | **部分属实** | 核心确被咨询（安装器写标记→`InstalledBuildMarker`→`NativePolicyCoreGate`→桥，缺失 fail-closed 三段齐全，且 `aegis_policy_core.dll` 确随包交付），但 FFI 通路只含「URL 形状 + 黑名单 + 高危判定 + nonce」；`PolicyEngine::default()`/`CapabilityRegistry::new()` 被构造却从不参与 evaluate（H-7 自述未撤，`broker.rs:17-22`、`ffi/broker.rs:147-150`） |
| 「注入脚本经三端守卫单源（bridge_guard）对账」 | **口径失实（实为两端）** | `verify_bridge_guard.py` 自陈 C# 不在范围，而 C# 确有文档创建前注入（`WebView2Hardening.cs:70`）——即 Windows 的注入面**无任何单源对账**；Kotlin 是手抄 + 逐行对账而非生成 |
| 「威胁黑名单订阅制刷新」 | **部分属实** | 刷新实为启动一次性：`ThreatFeedCoordinator` 只在 `Start()` 内调一次 Refresh，全仓无周期计时器；`CoreDenylistPublisher.cs:16-21` 注释自称「每一次订阅源刷新」（R7-CS1-09 未修） |
| 「跨端行为由冻结契约驱动并以跨语言向量逐条锁定」 | **部分属实** | 15 份向量中 C# 只链 2 份、Kotlin 只消费 `url-origin-*`；拒绝码词表不存在于任何冻结面（向量 `session_not_found` ↔ C# `session_context`；`reserved_address` 无向量） |
| 「KillSwitch：触发后全部导航/下载/审批链即刻冻结」 | **部分属实** | Windows 侧判定真实存在，但 NTP 宿主桥零判定（拉闸后首页仍可驱动 `importBookmarks/importHistory/restoreSession`）；后退/前进/重载 6 个导航入口不查开关；**Android 全树零 KillSwitch 代码**，README 未标端别 |
| 「无痕窗口」 | **部分属实（未标仅 Windows）** | Windows 成立（每窗独立临时目录 + `persistToDisk=false`）；Android 无实现，而 `android/README.md:9` 把 `clearPrivateData` 列为**发布前强制控制**——全树零命中 |
| 「五门禁常绿」 | **本轮成立，限定缺失** | 五个脚本确挂在常跑且 required 的 `contract-source-of-truth`；但「常绿」未区分「历史 run 绿」与「门禁有失败能力」，且 B1 之前 pwsh 吞退出码曾使红灯长期呈绿（文档未加此限定） |
| 「dotnet 650+ / cargo 450+ …」 | **可信（静态可核）** | 主代理按数据源枚举复算：Core.Tests 309 `[Fact]` + 364 `[InlineData]` + 8 + 30 = 711，Broker.Tests 86 + 36 + 32 + 8 = 162，与台账逐项相等；两套件零 `Skip=`、无空数据源形态（xunit 2 下空 Theory 判红） |
| 「M1-M4 全部落地、parity 清单 100% 代码项勾验」 | **部分属实** | 真机验收四行仍为 ☐（与「代码项」限定一致）；但 parity 有真实漏项：WebView2 `NewBrowserVersionAvailable` 在 `windows/` 零命中，归档栈有实现，且 ADR-001 与 device-validation 都列为要求 |
| 「legacy 只读冻结」 | **纪律口径分裂** | 无功能提交（守住了），但归档后有 5 次提交含 `1ffd2cb` 改 4 个安全模块（对应第六轮记为 P2 的 R6-06/07/08/09），与 `CLAUDE.md`「功能与安全修复一律不在该栈进行」及 ADR-009 D4「只修 P0/P1」两套口径都未对齐 |
| 「阶段 A→G 全部完成」「13 workflow」 | **失实** | 实树 15 个 workflow，README :55 已改 15 而 :124 仍写 13（另 5 处文档同错）；阶段 G 的本地 IPC 交付面（OS ACL/进程身份/传输/撤销）无任何实现，`agent/broker.py:31-33` 自述无实现 |
| 「master 受保护，禁止直接推送」 | **服务端事实相反** | 实测 `enforce_admins=false`、`required_pull_request_reviews` 不存在、ruleset 只挡 deletion/non_fast_forward 且 admin `bypass_mode=always` ⇒ 快进直推与绕过 9 个 required check 完全可行 |

## 六、推翻与降级（子代理误读记录，供校准后续派发）

1. **R8-AD-04 对 Android canvas 的定性被降级**：子代理称 Android「与 Rust 同退化」。
   主代理回读 `WebViewHardening.kt:371-377` 确认它乘的是**像素序号**（`px`，步进 1），
   故噪声位 = `seed&1 XOR px&1`——有逐像素性（2 个相位、三通道恒等），属「扰动宽度
   不足」的 P2，不属「恒退化」的 P1。Rust 用的才是 `i`（字节偏移，恒偶）。
2. **B3 首轮改名撞出的耦合（CI 实证）**：`release-android.yml:192` 与
   `native-policy-artifacts.yml:236` 用 `--tests` **逐字**指名
   `AndroidBrokerTest.defaultNativePolicyCoreGateClosesWhenBuildRequiresNativeCore`。
   主代理首轮把它改名并断言默认变体，Gradle 当场报 `No tests found for given includes`
   把发布链打红。据此恢复原名、锚点独立成新文件，并加「两处过滤器与用例名必须对齐」的
   常驻断言。**凡重命名被 workflow `--tests` 指名的用例，必须同批改过滤器。**
3. **R8-DOC-01 的时间指代被修正**
   是错的」。主代理 `git show v2.2.0-beta.52:.github/workflows/release-android.yml`
   查证：该 tag 的 `assembleRelease` 只有 `requireNativePolicyCore=true`，第二个标志是
   第六轮之后才加的 ⇒ 对**已发布制品**该句仍成立，定性质改为「文档滞后」。
4. **R8-DEPS-11 的否定式结论被采纳并保留**
   （AGP 9.4.1 / Gradle 9.8.0 / Compose 插件 2.4.20 / BOM 2026.09.00）经上游逐个查证
   **均为最新稳定线**，本分区唯一可动的是 androidx.webkit 与 lifecycle 两格。这条
   「没有升级面」的结论按原样登记，避免下一轮重复报「AGP 落后」。
4. **未采信为缺陷的观察**（写下来防下一轮重复报）：SQL 全参数化无拼接；
   `allowFileAccess=false` 不影响 `file:///android_asset` 首页；Android 并发面干净
   （无 GlobalScope/runBlocking，launch 三点均显式 Dispatchers）；StateFlow 原地改
   陷阱现存零例；xunit 空数据源不可达；红线「每个 WebView 经 SecureWebViewFactory」
   实测成立；`Contracts/Generated` 六 record 不作桩实现缺陷（沿用第七轮 §六之二）。

## 七、需用户裁决（本轮新增 1 项 + 第七轮遗留 3 项）

1. **【新增·最高优先】出货 Windows 在本机/内网导航上的期望行为**（R8-CS-SEC-01 的
   修复方向）：(a) 安装器同时写 `RequireNavigationConfirmation=1`——用户点一次确认即
   打开，同时保留对「远程页面把用户导航进内网后台」的拦截；(b) 改核心语义让
   `127.0.0.1`/RFC1918/`100.64/10` 不再算高危——无点击但远程页可自由利用用户身份访问
   内网服务；(c) 仅把静默取消改为可见拒绝（本轮 B4 走这一步，不替你改判方向）。
2. **Android 是否落地「本机/内网可打开」**（R8-AD-01）：需要 `http` 不升 https +
   `network_security_config.xml` 加 `domain-config` 明文例外，属明文策略放宽，
   且要同步改 `NetworkSecurityConfigGuardTest` 断言矩阵。
3. **`release` 环境是否加保护**（R8-CI-01）：wait timer（不自锁、公开仓库免费）或
   required reviewer（单人仓库有卡死风险）；本轮**未动任何服务端设置**。
4. 第七轮遗留：Windows tag 缺 Authenticode 是否 fail-closed（`release-windows.yml:179-182`
   现为 `Write-Warning; exit 0`，而 `signing-policy.yaml` 声明 `fail_closed: true`）；
   `enforce_admins` / 强制评审是否开启（单人仓库下等于自锁）。
   此前已否决项维持否决：FLAG_SECURE、退出清 Cookie、IDN、Android 下载走 broker。

## 八、升级面清单（本轮主诉求）

**OSV 查证结论：本仓在用版本无一命中已公告 CVE**（含 WebView2 / Microsoft.Data.Sqlite /
SQLitePCLRaw / xunit / Test.Sdk / jna / org.json / junit / mockito / robolectric / AGP /
androidx.webkit / cryptography 50.0.0-50.0.1 / ed25519-dalek / getrandom / sha2 / uniffi /
cryptography 系 legacy 锁）。故本轮无 CVE 驱动项，以下为「落后/未兑现/被阻塞」三类。

**A. 可直接升、无需重锁**：androidx.webkit `1.15.0 → 1.17.1`（1.16 的 Isolated Worlds /
`addJavaScriptOnEvent` 正是宿主注入脚本与页面 JS 同 world 的解法；1.17 新增
`setDownloadFaviconsEnabled`；本仓仅用 3 个 API，1.16/1.17 的破坏性删项零命中）、
lifecycle-runtime-compose `2.10.0 → 2.11.0`（实测 Compose BOM 不管辖它）、
xunit.runner.visualstudio `3.1.4 → 3.1.5`、`anchore/sbom-action v0.24.2 → v0.24.3`（×3）、
ruff `0.16.9 → 0.16.10`。**否定式结论**：AGP/Gradle/Compose 插件/BOM、detekt、ktlint、
jna、org.json、junit、mockito、robolectric、androidx-test、SQLitePCLRaw core/provider/lib、
xunit 本体、bandit/pytest/pyyaml/jsonschema/pip-audit/cryptography **均已是上游最新稳定线**。

**B. 需重锁或需配套改动**：Microsoft.Data.Sqlite `10.0.0 → 10.0.12` 与 WebView2 SDK
`1.0.2903.40 → 1.0.4258.31`（落后约 22 个月）须按「改 csproj → `dotnet restore -r win-x64
-p:RestoreLockedMode=false` → 回读锁确认 `net10.0-windows7.0/win-x64` RID 块仍在 → 再跑
六条 LockedMode 门禁」的顺序重锁（已知陷阱：裸 restore 会把锁改写成无 RID 形态，六个
门禁随即全报 NU1004）；`SQLitePCLRaw.bundle_e_sqlite3` 在锁内仍解析为 **2.1.11**——csproj
只钉了 core/provider/lib 三件，即 NU1903（GHSA-2m69-gcr7-jv3q）的修复只做了 3/4；
mypy `2.3.1 → 2.4.0` 须 pip-compile 整树重算 hash；Test.Sdk `17.14.1 → 18.10.1` 跨 major。
**依赖自动化侧**：`.github/dependabot.yml` 已配且真在跑（五生态、weekly、分组），但
实测 `dependabot/alerts?state=open` 仍有 **9 条**（含 `bcprov-jdk18on` 一条 critical、
一条 high，`first_patched_version: null`），而 `docs/security/android-build-classpath-triage.md:49`
写的是「附证据 dismissing」——`state=dismissed` 计数为 **0**（R8-CI-06）。

**C. 可复现性与「承诺未接线」类升级**（性价比最高的一批）：
- 「固定 toolchain」是 Cargo.toml:32 与 ADR-005:7 双双声明的 Rust 供应链口径，实测
  **无 rust-toolchain.toml、无 deny.toml、9 处 `toolchain: stable/nightly` 浮动**；
  stable 已从 1.87 基线漂到 1.99.0 ⇒ 同一 commit 隔月重跑的 `aegis_policy_core.dll`
  字节可变，自建哈希基线与 release 台账对账会周期性失配。
- `runs-on` 全用 `*-latest`：实测 `windows-latest` 现映射 **windows-2025-vs2026**
  （VS2026 工具集），与 `windows-2025` 是两张镜像；`ubuntu-latest` = 24.04 而 26.04 已 GA。
  本仓已两次被镜像漂移打疼并留字为证（Inno Setup 预装版本、pwsh 把 `2>/dev/null` 解释成
  写 `D:\dev\null`）。发布链建议显式 `windows-2025`。
- 无 `.gitattributes`：行尾完全交给客户端 `core.autocrlf`（实测本机 667 个受管文件
  `i/lf w/crlf`），而 `android/.editorconfig` 声明 `end_of_line=crlf` 与其管辖对象现状
  （blob 全 LF）相反——第七轮 B4 已为此付过一次代价（门禁自己把 CRLF 工作副本写成 LF
  即「污染源文件」）。
- `dotnet restore` 在 `supply-chain.yml:90` 是无 `-r win-x64` 的裸 restore（跑在 ubuntu，
  判定无害成立，但依赖升级 PR 若照抄该命令行即锁退化——应写进 SOP）。
- .NET 侧有 `TreatWarningsAsErrors` 却零 `AnalysisLevel/EnableNETAnalyzers/Deterministic/
  PathMap` 配置 ⇒「0 警告」的实际含义是「0 个编译器警告」，SDK 自带的 CA2xxx/CA5xxx
  （含 P/Invoke 边界、加密用法、路径规范化）默认面窄得多；这是**白捡的一层静态检查**。
- Rust edition 2024 的暂缓**仍然成立且无 ETA**：crates.io `uniffi.max_version = 0.32.2`，
  mozilla/uniffi-rs 无 GitHub Releases ⇒ Cargo.toml:7 写的「uniffi 0.33+ 官方支持」
  目前不可验证，宜把重启条件改为「绑定具体版本 + 一条 CI 侧 edition-2024 试建冒烟」。
- WebView2 增强安全模式（ESM）：`CoreWebView2Profile.EnhancedSecurityModeState` 的
  moniker 至今只到 `-prerelease`，升 stable 也拿不到 ⇒ `WebView2Hardening.cs:34` 的
  「升级 SDK 后 ESM 自动生效」为假。
- 一致性升级（结构级）：**核心缺 JS 生成导出接口**（13 个 C ABI 符号里没有任何脚本生成
  入口，三端各自手抄同一份 JS）——这是 R7-CS1-05/R7-CS2-10/R7-AD-02/03 与本轮
  R8-RS-01/02/04/05 的共同根因；拒绝码词表未冻结；`reserved_address` 只在 C# 存在，
  同一年份 `169.254.169.254` 在 Windows 硬拒、在 Android 是「弹面板后用户批准即放行」。

## 九、本轮建议批次划分（文件所有权互斥）

| 批 | 内容 | 触及文件 | 可验证方式 | 状态 |
| --- | --- | --- | --- | --- |
| **B1** | R8-CI-02/03：pwsh 门禁扫描面四类盲区 + 空面 fail-closed + 7 种形态故障注入；legacy-guard 两步骤改 bash | `scripts/check_workflow_shells.py`、`tests/python/workflow_shells_test.py`、`.github/workflows/legacy-python-guard.yml` | 新扫描器对修复前文件报 9 处、对当前仓库 27 个 pwsh 步骤报 0 处；CI `contract-source-of-truth` | **已落地 PR #86（全绿）** |
| **B2** | R8-RS-01/02 + R8-CS-SEC-04：三端 canvas 噪声统一 fmix32、边界不外溢、像素上限、空站点键不再退化为常量；三端各补性质断言 | `core/.../shield.rs(+tests)`、`windows/.../FingerprintShield.cs(+Tests)`、`android/.../WebViewHardening.kt(+ScriptTest)` | cargo test/clippy、`:app:testDebugUnitTest`、Core.Tests | **已推 PR #87（cargo fmt 红灯已修，重跑中）** |
| **B3** | R8-AD-02/09：JNA keep 规则名改正 + 常驻 `ProguardKeepCoverageTest`（按声明位置推导二进制名逐个断言被 keep）+ 恒绿用例改可失败断言 + 发布链置位静态锚 | `android/app/proguard-rules.pro`、`android/broker/src/test/**` | `:broker:ktlintCheck/detekt/testDebugUnitTest`（CI 实跑） | **已推 PR #88（首轮 ktlint 解析事故已修，重跑中）** |
| B4 | R8-CS-SEC-01/08 + R8-CS-CORE-1/2：把「核心要求确认」与 6 条静默出口收敛为**用户可见拒绝 + 审计留码**；补 5 个拒绝码的行为断言与原生前置分支断言。⚠ 只改可见性，不改放行/阻断方向（方向属第七节 1） | `HostWebView.cs`、`BrowserPolicyBroker.cs`、`windows/tests/**` | `dotnet test` 两套件（CI） | 未动 |
| B5 | R8-CI-03 残余 + R8-PY-02/08/11 + R8-SH-10：`validate_vector_schemas` invalid 侧缺 manifest 改记 failure、按条目下界、`check_markdown_links` 包含性 + 空面 exit 2、`ci.yml` paths 补齐输入闭包、requirements 锁结构门禁（逐条 `==`+hash、`.in↔.txt` 对账） | `contracts/codegen/validate_vector_schemas.py`、`scripts/{verify_vectors,check_markdown_links}.py`、`validate_release.py`、`.github/workflows/ci.yml`、`tests/python/**` | 每项须先注入失效证据再声称修好 | 未动 |
| B6 | 无破坏升级：androidx.webkit 1.17.1、lifecycle 2.11.0、xunit.runner.visualstudio 3.1.5、sbom-action v0.24.3、ruff 0.16.10、`.gitattributes` + `android/.editorconfig` 行尾口径、发布链 `windows-2025` | `android/gradle/libs.versions.toml`、`windows/tests/*.csproj`、4 个 workflow、仓库根新文件 | CI 全量（gradle/NuGet 侧无需重锁即可验） | 未动 |
| B7 | 需重锁升级：WebView2 SDK + Microsoft.Data.Sqlite + `bundle_e_sqlite3` 补钉（按第八节 B 的五步 SOP）、`AnalysisLevel=Recommended` + `Deterministic`、mypy 2.4.0 整链重锁、rust-toolchain pin + `cargo deny`（或按实改注释）、Dependabot 9 条告警的显式 dismiss/处置 | `windows/*.csproj`、`windows/**/packages.lock.json`、`Directory.Build.props`、`requirements-ci.*`、`.github/workflows/*` | CI；锁文件改写后须回读确认 RID 块仍在 | 未动 |
| B8 | 文档真相（第七轮 B7 未完 + 本轮 R8-DOC 全部）：13→15 workflow 七处、单一裁决源限定语、三端守卫→两端、KillSwitch/无痕端别、parity 补 `NewBrowserVersionAvailable`、legacy 冻结口径合一、`identity.md` E2EBroker 死指针、README 确认流域口径、ADR-003/006 取代注记、4 份历史稿时代横幅 | `README.md`、`CLAUDE.md`、`SECURITY.md`、`CONTRIBUTING.md`、`docs/**`、`agent/local-ipc/**` | `check_markdown_links` + 新增 workflow 计数对账锚 | 未动 |
| B9 | 一致性升级（结构级，须先补向量再改码）：拒绝码词表入 `contracts/schemas` + `contracts/vectors/deny-codes.json` 三端生成常量；`reserved_address` 与元数据段进核心；Rust `is_local_or_private_host` 改名 `is_high_risk_host` 并补 TEST-NET-2/3；三端脚本与核心生成物逐字节对账门禁 | `contracts/**`、`core/.../security_policy.rs`、`windows/**`、`android/**`、`contracts/codegen/**` | 向量三端 + cargo + dotnet + gradle | 未动 |

**串行约束**：B4 与 B6/B7 同改 `windows/**` csproj/`HostWebView.cs`；B8 与 B9 同改
`contracts/**` 与 README；B3 与 B6 同改 `android/`。按表内序号串行派发，同文件不并行。

## 十、本轮登记口径修正三条

1. `contracts/schemas/*.json` 实为 **7 份** JSON + 1 份 `bridge_guard.template.js`——
   第七轮 §八.5 与 `scripts/verify_vectors.py:39` 所称「8 份 schema」不成立。
2. 守卫 JS 单源路径是 `contracts/schemas/bridge_guard.template.js`，不在 `codegen/`。
3. `shared/shell/` 现状与第七轮记载不同：start.html 实测 141 行、零内联脚本、
   CSP 全外置，脚本为 5 份（start.js 185 / start.main.js 475 / start.snake.js 570 /
   start.import.js 338 + start.css 393），WALLPAPERS 在 `start.main.js:15-20`；
   且「.NET 正典栈不消费 start.html」已不成立——三端全消费（C# 拷入输出 `ntp/`
   经 `https://ntp.aegis.local/start.html` 加载，`NtpBridge.cs` 实现 14 个 op）。

## 十一、待复核队列（子代理已给 `文件:行号`，主代理本轮未逐条回读 ⇒ **不作为登记结论**）

按 skill 口径，未回读的条目不得登记为发现，也不得直接进入修复批次。以下为各分区
返回后尚未复核的条目计数与最值得优先复核的三条（复核后再决定是否入正表）：

| 分区 | 未复核 P2（上界） | 未复核 P3（上界） | 最值得先复核 |
| --- | --- | --- | --- |
| R8-CS-SEC | 11（02/03/05/06/07/09/10/11/12/13/14） | — | R8-CS-SEC-02（导航与子资源策略链**没有异常边界**：`e.Cancel = !TryAuthorizeNavigation(...)` 求值期抛异常即 `e.Cancel` 保持 false ⇒ 放行，与红线 fail-closed 相反） |
| R8-CS-CORE | 6（02/03/04/05/06/07 及 P3 10 条） | 10 | R8-CS-CORE-4（`HistoryStore` 8 个公共查询方法零生产调用方，却占了该区最大一块用例预算——「711 例」里相当比例钉在生产不可达路径上） |
| R8-RS | 8（03/04/05/09/10/14/16/21） | 9 | R8-RS-15（核心缺 JS 生成导出接口＝三端手抄的共同根因；若属实则第八节的一致性升级 B9 是正解） |
| R8-AD | 4（03/04/05/06/07） | 11 | R8-AD-02 分区记录的 `allowedOriginRules=setOf("*")` + fetch 三重包裹 ⇒「`fetch.toString()` 默认即返回注入脚本文本」——若回读成立应从 P2 升 P1 |
| R8-PY | 5（03/04/05） | 11 | R8-PY-03（判定面由被证明物自己决定：把 `origin` 从 schema `required` 摘掉即整段消失而全部门禁仍绿） |
| R8-SH | 6（01/02/03/08/13/14/15/16） | 6 | R8-SH-15（两条「回归锁」语料语言错了：`setTag` 是 Android API、`setOf` 是 Kotlin 字面量，而 `allScripts` 是 shell JS ⇒ 两条恒真，BUG-001/006 实际零保护） |
| R8-CI | 5（04/05/06/07/17） | 12 | R8-CI-06（triage 文档写「附证据 dismissing」而实测 `state=dismissed` 为 0，含一条 critical） |
| R8-DEPS | 8（01/03/04/05/06/07/08） | 14 | R8-DEPS-3（NU1903 修复只做 3/4：`bundle_e_sqlite3` 仍解析为被点名的 2.1.11） |
| R8-DOC | 12（03–14） | 8 | R8-DOC-09（「唯一裁决者」的四文档同述 + supported-features 无限定语） |

**已在复核中确证并升入第四节的条目**（共 11 条）：R8-CI-03、R8-SH-10、R8-PY-02、
R8-PY-08、R8-RS-02、R8-RS-13、R8-AD-09、R8-CS-SEC-04、R8-CS-SEC-08、R8-CS-CORE-1、
R8-CS-CORE-2。计数列取子代理自报口径，可能包含上述已确证者，故为**上界**而非精确值。
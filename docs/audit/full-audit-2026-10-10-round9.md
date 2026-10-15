# 全仓第九轮补充审计（2026-10-10）

## 一、方法与规模

**触发原因**：第八轮 §十一 队列里若干条目在增量追加时只落了 ID 与计数、没有
`文件:行号 → 现象` 文本；当轮子代理原文只存在于会话里，会话压缩后即失（第八轮
§十 第 6 条已把这定为失账根因）。本轮**重派六个只读分区**重新 derive：
AD（Android）、CI（workflow 与门禁脚本）、SH（shared 壳层与契约数据面）、
DOC（文档 vs 实树）、CS（Windows 正典）、RS（Rust 核心）。

**输出契约**沿用第八轮：`ID | 严重级 | 类型 | 文件:行号 | 现象 → 方案 | 影响 |
与既往关系`，末行强制 `COVERAGE: 全文读 / 略读 / 未读`。六个分区全部返回并给出了
诚实的未读清单，因此**本轮所有结论的置信边界以各自 COVERAGE 为准**，不写「全仓 100%」。

**登记纪律（本轮起强制）**：未回读的条目必须把 `文件:行号 → 现象` 原样写进第五节
队列，不得只留计数。规模基线沿用第八轮实测（≈474 个受管源文件；本轮 +4：
#130 的两个 Kotlin 文件与 #131 的门禁+测试），未重算。

## 二、主代理回读裁决（已复核，可作登记结论）

| ID | 级别 | 裁决 | 依据（本批实测，不引用子代理） |
| --- | --- | --- | --- |
| R9-AD-1 | **P1**（子代理声称，主代理独立确证后落地） | 保留并落地 | 读装配链而非引用结论：`WebViewHardening.kt:45-52` 把 fingerprint-shield 与 bridge-guard 作**两条** `addDocumentStartJavaScript` 注入，而 R8-RS-09 的撤销 IIFE 原先排在第一条 blob 末尾（`WebViewHardeningStagesShield.kt:198-201`）⇒ 无论 runner 先跑哪一条，桥守卫四处 `__aegisReg` 都空转（先 shield 则 `open=false`，先 bridge 则 Symbol 未定义）。另有**同族第二因**：三处 guard 的 register 都写成「`original` 已在表里 ⇒ 拒绝登记」，被拒的正是链式包装的最外层 ⇒ 它根本不在表内，`outer.toString()` 直接返回我方源码。`core/rust-policy-core/tests/tostring_window.rs` 此前把「撤销在 shield 段末尾」钉成断言，即门禁钉住缺陷形态（同文件已改）。第八轮 §六.8 的推翻就地更正 |
| R9-CI-3 | **P1**（子代理报 P2，升） | 保留并落地 | 本地 `bash -ec` 实测「`false && echo hi; echo done` ⇒ exit 0」：Actions 的 bash 包装是 `-eo pipefail`，`set -e` 对 `&&` 列表中非末位命令的失败豁免 ⇒ `release-android.yml:219` 的 `zipalign -c -P 16 4 … && echo OK` 永不失败，而该步末条是必过的 `grep -Fx`；上方注释却写「不对齐即失败」。后果：非 16K 对齐 APK 全绿出厂，Android 15+ 16KB 页设备装不上 |
| R9-CI-2 | P2 | 保留并落地 | py-yaml 解析各步 `run:` 正文：`dependency-relock.yml` 有 6 处 in-run `${{ }}`（branch/ecosystem/run_id），`gradle-dependency-insight.yml` 为 0 处——而后者头注声称「全量扫描后本行是唯一残留 in-run 表达式」。`${{ }}` 在 shell 解析之前完成文本替换 ⇒ `branch=x"; git push origin HEAD:master; #` 能打断同文件里的 `deps/*` 守卫；本 job 是全仓唯一持 `contents: write` 的手工触发面 |
| R9-CI-4 | P2 | 保留并落地 | 全仓 grep：`verify_xaml_resources.py` 唯一调用点在 `release-windows.yml:219`，而该 workflow 只由 tag 的 `workflow_call`/`workflow_dispatch` 触发 ⇒ XAML `FindResource`↔`x:Key` 对账（V3 启动崩溃类）在 PR/push 面零执行；其 4 条 pytest 用例全部 `monkeypatch.setattr(vxr,"SRC",tmp_path)`，常跑面只证明机制不证明现树 |
| R9-CI-5 | P3 | 保留并落地 | `run_compat()` 面是 `*.py` + `.github/workflows/*.yml`；同仓 `check_workflow_shells.py` 早已把 `.github/actions/*/action.yml` 纳入 pwsh 面 ⇒ 两个「workflow 结构类」门禁面不一致，`prepare-geogebra` 的两个内嵌 python heredoc 在 compat 面外（R8-CI-21 的第三次落点） |
| R9-CI-7 | P3 | 保留并落地 | `release.yml:196`、`release-core.yml:195`、`release-android.yml:392` 三步名为 `Fail-closed gate`、正文只有 `echo "✅ …"`——结构上不可能失败，日志里的「门禁」字样会被后续人当判定证据（SP-231 删零信息量步骤同口径） |
| R9-CI-6 | P3 | 部分确证 | `.github/dependabot.yml:2` 写「13 workflow 全 SHA pin」而实树 16 ⇒ 计数失实属实，本批改声明；「把 `.github/**/*.yml` 纳入 `check_doc_claims` 面」的建议本批**未做**（先改声明，面扩展单独定） |
| R9-CI-9 | **P1**（子代理报 P2，主代理实测后升） | 保留并落地 | 「`dotnet test` 零发现也退 0」不是引用而是**本地实测**：`dotnet test … --filter "FullyQualifiedName~NoSuchTestAnywhere9"`（Broker.Tests，runner 仍 3.1.5）⇒ 打印「没有测试匹配…筛选器」，**EXIT=0**，且写出的 TRX 是 `<Counters total="0" executed="0" passed="0" failed="0" …/>`。八处调用（compat.yml:116,122、contracts.yml、native-policy-artifacts.yml、release-windows.yml）此前只看退出码 ⇒ 一旦测试宿主跨 major 后发现器与框架不同代，最坏结果是**零发现全绿**，而必需检查名里带「Test」的两个 job 都会绿。升级前提就在本轮批次里（Test.Sdk 17.14→18.10 已并 #136，xunit.runner.visualstudio 3.1.5→4.0.1 排队中）⇒ 门禁必须先于 bump 落地 |
| R9-CI-10 | P2 | 保留并落地 | PR #137 的 CI 实证：`windows-contract-build` 里 `dotnet test` 782/782 通过、发现数下界也达成，`scripts/assert_test_counts.py` 却在打印 ✅ 那一行抛 `UnicodeEncodeError: charmap codec can't encode` ⇒ 脚本 exit 1 ⇒ **门禁把成功报成失败**。同形态 2026-10-08 已死过一次（Dependency-Retlock 首跑 run 37793334416，heredoc 里的中文 print），当时只在**那一个 job** 修（job 级 `PYTHONIOENCODING`）⇒ 判定面从未扩展：py-yaml 扫 16 个 workflow，7 个「windows runner + 调 python」job 里 4 个既无 `PYTHONUTF8`/`PYTHONIOENCODING`、脚本侧也没有 reconfigure。方向不是掩盖问题：假红与假绿同等致命，而它正是「把 emoji 删掉就绿了」这种削弱断言的诱因 |
| R9-CS-6 | P3 | 保留并登记（本批未修） | 登记时与本表 §五 Q24 的 `R9-CS-4` **撞号**——被常驻门禁 `gate_hollowness_test.py::test_ledger_csv_ids_are_unique` 在 CI 打红（本会话第二次撞同类：取号必须按 CSV 解析求 max，不能靠 grep 抽文本再排序）。内容：落地项 5 时自读新证：`Core/UrlSafety.cs:20-30` 的 `CanOpenHttpUrl` 把「协议不合」（`file:`/`javascript:`）与「保留地址」并成一个 false，`NewTabGate` 只能给一种拒绝码与一条文案 ⇒ 用户点 `javascript:` 链接时被告诉「链路本地/云元数据/保留地址」。这不是本批引入的（主窗原文案同形，只是此前没有拒绝码），修它要把协议判定从 `CanOpenHttpUrl` 里拆出来——该文件在零余量基线上（301/301），拆面另批处理，**不得**顺手在 `NewTabGate` 里复刻一份协议白名单（那就是第二个判据源） |
| R9-CS-5 | P3 | 保留并登记（方向保守，未修） | `App.xaml.cs:11-32` 的 `PopupRateLimiter` 槽位数组以 **0** 起步，而判定是 `now - _ticks[i] >= windowMs` ⇒ 开机后第一个 30 秒内 `now` 本身 < 30000，三槽全判「未过期」⇒ **这段时间里所有崩溃弹窗被静默拒**（只记日志）。它管的是异常提示，方向保守所以从未被当成缺陷暴露；风险是**形状被抄走**：同形状用在「拒绝用户可达的功能」上就是打开即失效。新建的 `Core/NewTabGate.cs` 刻意用「从未占用」哨兵避开这个坑，并有冷启动用例 `ColdStart_AllowsFullQuotaInsideOneWindow` 钉住；旧那台零测试引用，另批收口 |
| R9-CS-5 **收编** | P3 | 保留并落地（R9-B18，上一条登记行的后半） | 登记时写的是「方向保守所以未修」——回读把范围说得更准一点：调用方传的是 `Environment.TickCount64`（自**开机**起毫秒）而窗口是 30_000，所以静默区间是「开机后前 30 秒」，不是「应用启动后前 30 秒」；这段时间里 `UnihandledException` 的可见信号（MessageBox）全部被吞，只留日志——排查者看到的正是「应用无声退出/无提示」。修法不是调窗口，而是把槽位哨兵改成「从未占用」`long.MinValue`，与 `Core/NewTabGate.cs` 的 `SlotWindow` **同一个形状**（那边有 `ColdStart_AllowsFullQuotaInsideOneWindow` 钉住，减法还会溢出 ⇒ 必须先判哨兵）。新常驻 `PopupRateLimiterTests` 5 条（冷启动满配额、`now=0` 那一拍、到期只放一槽、长期滚动、开机数日的常态路径没被改坏）。反向锚实测：把哨兵判定撤掉（回到 `nowTicks - _ticks[i] >= windowMs`）⇒ 5 条全部判红；还原后 Core **801/801**（796 + 本批 5）。此前该类全仓零测试引用——这也是它能活到第九轮的原因，CS-196 提纯成类的时候没配冷启动用例 |
| R9-SH-8 | P3 | 保留并落地（R9-B19） | 回读确证症状与两条可达路径：init 的 `Host.getEngine(function (data) { if (!data) return; …})` 对 null 回包**静默退出**，胶囊停在 `start.html:38` 硬编码的「百度」上零痕迹——而 null 是真分支：桥未挂接时 `csCall` 直接 `cb(null)`，宿主永不回包时 WB-037 的 TTL 清扫也 `cb(null)` 兜底。对照 WB-138 早已为书签做 null/[] 分流，这条只是漏了。修法刻意**不猜默认引擎**（真实默认可能是 bing，猜错会把搜索发去错引擎）：`renderEngine(unknown)` 在 unknown 或 `ENGINES` 为空时写「未知」，init 的 null 分支改成 `bridgeError('getEngine:init', 'null') + renderEngine(true)`；顺带把「有 data 但引擎表为空」这一支也接上同一判据 （旧行为同样是「什么都不写」＝继续谎报当前引擎）。**零增行落地**：`start.main.js` 停在 475 行零余量基线上，为此把 WB-013/WB-180 两段注释各重排一行（文字不改）并回收 `// 搜索引擎状态` 独立注释行。装载器同批下沉单源（`loadMain`/`makeHost`/`MAINJS` 移入 `tests/ui-regression/helpers.mjs`，并加 source/elementOverrides 扩展点）——否则第二个用例文件要再抄一份 DOM 桩（两处解析漂移＝第二个假绿源，WB-206 同一课）；`start_main.test.mjs` 578→519 行、基线同批收窄。新用例 4 条含一条**内存态反向锚**：把 null 分支改回 `if (!data) return;` 后，「未知」不再出现、留痕归零——症状原样重现，证明前两条判据真的在判它 |
| R9-SH-9 | P3 | 保留并落地（R9-B20） | 回读确证：`scripts/verify_cross_end_lists.py` 的引擎对账只比 **key 集合**，两份元数据各抄多处而零判据——展示名 4 处（legacy `SEARCH_ENGINES` 元组第 0 位 / Kotlin `ENGINE_NAMES` / C# `EngineNames` / 壳层 `engineFallback` 的 `name`），默认引擎 5 处（legacy `DEFAULT_ENGINE`、Kotlin `DEFAULT_ENGINE`、C# `DefaultEngine`、壳层 `engineFallback` 的 `engine`、`start.html` 胶囊初始文字）。改一个中文名或换一次默认值只落一处不会红；而默认值漏改的后果是**两窗行为分叉**（首页胶囊显示旧引擎、Android 搜索走旧引擎）。落地＝新增 `scripts/engine_metadata.py`（154 行，判据面拆出来是因为门禁本体已在 300 行红线上，同 `mirror_consumers.py` 的处理），四端 key→名逐字比对 + 默认值同源 + 「默认值必须 ∈ 核心集」+「start.html 初始文字＝默认引擎的展示名」（这一条把 R9-SH-8 留下的硬编码占位也接进判据：写错就红，而不是靠人记）。范围如实收窄：只比核心引擎集，C# 的六个扩展引擎名不进面——壳层回退表刻意只覆盖核心四引擎，逼它抄满十个只会让它猜没登记过的名字（扩展 key 集仍由 `CS_ENGINE_EXTENSIONS` 双向判）。SP-154 边界照抄：legacy 归档端文件缺失 ⇒ 告警 + 降级为现役三端，文件在但表解析不出 ⇒ fail；`core` 为空 ⇒ 单条告警（对面门禁此时已因 key 集为空而 fail，不叠三条噪声把一次失败伪装成多个缺陷）。新常驻测试 17 条（含现树 0 违规、现树扫描面非空、槽表路径存在、四类漂移各判得出、legacy 两态、空 core 降级、四端逐端可解析）|
| R9-DOC-01..09 | P2×7 + P3×2 | 保留并落地（R9-B21） | 九条「文档说的 ≠ 实树的」逐条回读到具体行后改真：① README 挂着「仍待裁决」的两项其实早已落地（`LocalTargetHosts` + `network_security_config.xml` 的有界 `cleartextTrafficPermitted` + `HostWebView.WebResourceGuards.cs` 的 `SubresourceDenialFailClosed`），改写成事实并把**真未决**（IPv6 导航面）单列；② ADR-007 写「C# 无注入 JS」而 `WebView2Hardening.cs:77` 就在调 `AddScriptToExecuteOnDocumentCreatedAsync(FingerprintShield.BuildScript(…))`；③ ADR-007 写「门禁型 workflow 已全部移除 `paths:`」，py-yaml 实测只有 `android-quality`/`contracts` 两处真无过滤（`ci`=8、`core-rust`=3、`agent-redteam`=5、`supply-chain`=11）；④ architecture-overview 的「16 workflow」分解算出来是 15（漏 `dependency-relock`），而 `check_doc_claims.py` 只比裸数字所以它一直全绿；⑤ parity-checklist 的 ESM「升级自动生效」被第八轮 B6 实测反证（两版 stable loader 对 `EnhancedSecurityModeState` 均 0 命中）；⑥ device-validation Android 第 4 步写「经 broker 判 MIME/最终 URL/size/目录」，实测链是 `WebViewDownloadHandler.kt:113-114` 的 `WebViewDownloadTargetGuard`（scheme/保留地址）+ `DownloadPolicy` 扩展名，不经 broker 也不判 MIME/size；⑦ 同文件 Windows 第 7 步补上「发布制品默认不出现确认面板」的启用前置（安装器刻意不写那个注册表值）；⑧ run-guide「真机验证 10 项」实为 11 项，漏的正是 R8-CS-SEC-03 的唯一实测出口；⑨ README/SECURITY 引的 `:70` 是空行、实调在 `:77`。**一条被推翻的动作**：③ 一度想直接删掉四处 `paths:` 去「兑现」ADR——那属 CI 触发面变更（每次 PR 时长上升、且必需检查与触发条件必须同批核对），故本批只把陈述改真，余下收口另登 Q48 |
| R9-DOC-10..15 | P3×6（R9-B41 落地时的复核＝**六条全部属实**，但其中三条的修法不是「把数字改对」） | 保留并落地 | 六条「文档抄了实树自己会说的话」：①README/CLAUDE/security-testing-guide 的「五门禁」——`contracts.yml` 的 `contract-source-of-truth` 现读 **30 步**（27 步调 python、18 步是 `check_*`/`verify_*`；登记时那句「约 17 步」本身也是估错的），三处一起改成「判定面单源＝那个 job 有哪些步骤」，**不再抄新的步骤数**；②`privacy-defaults.md` 凭证行把 `credential_guard`（OS keystore/DPAPI）当正典能力写，而该模块只在 `legacy/windows-pywebview/app/`，正典全树 `CredentialGuard`/`ProtectedData`/`DPAPI`/`KeyStore` 现读 **0 命中**（同文件 :12 已诚实写「静态加密未落地」＝两行互相打脸），改成「保证只来自密码/令牌本就不落盘＋OS 沙箱」；③`android/README.md` 的「发布前强制控制」把未落地项与已落地项混排——按实树拆两栏（已落地：`DownloadPolicy`、权限**无条件 deny**（`BrowserEngine.kt:97`，不是授权 UI）、`AegisApplication` 的崩溃钩子、签名发布链；未落地：`androidx.room` 与 `bookmark` 各 **0 命中**、Keystore 0 命中、同步协议、无痕 A-03）；④`CONTRIBUTING.md`「master 受保护、禁止直接推送」——**本批重新现读服务端**而不是引用第八轮的数：ruleset `R6-master-no-rewrite` 只有 `{deletion, non_fast_forward}` 且 Administrator/Maintain `bypass_mode=always`（本账号 `current_user_can_bypass=always`），经典保护 9 个必需检查、`strict=false`、**无 `required_pull_request_reviews`**、`enforce_admins.enabled=false`，直推历史 `d898677`/`3243397` 仍在 ⇒ 改成「服务端只强制不许删分支/不许改写历史，经 PR 全绿是流程纪律」，**不动任何仓库设置**（加对管理员生效的 PR 要求留在 §四 待裁决）；⑤parity-checklist `:73`「本清单 100%」与同文件 `:24` 的 ☐ 直接矛盾（复测 `NewBrowserVersionAvailable` 仍 0 订阅、`RuntimeUpdater.cs` 仍不存在）；⑥README 测试计数与现读双向失真（cargo 605／dotnet 508+474／JVM 450＝app 320+broker 84+adapter 46／`tests/python` collect 630＋`agent/tests` 81／UI 回归 126），而这些数**没有任何门禁判过** ⇒ 撤掉聚合数、只保留机器判定的下界（`assert_test_counts.py` Core ≥700/Broker ≥160、`verify_vectors.py` ≥21 份/≥222 条）。共同判据：这一类缺陷永远不会自己变红——代码错了用例会红，文档抄错了没有任何东西会红，所以唯一的修法是**不抄** |
| R9-SH-16 | **P2**（R9-B44 回扫**本会话自己刚写的用例**时发现＝R9-SH-15 同族，只是这次在端侧） | 保留并落地 | R9-B39 把「注释不算消费」装进了门禁，而**端侧那批源码文本锚用例没跟着改**——今天刚写的 `ConsumedNonceLedgerTest`/`WebViewDownloadCompletionGuardTest` 就是 `source.readText().contains("...")`：同一把尺子只磨了门禁那一头。两个方向都会坏：把 `trackConsumedNonce(nonceLedgerKey(` 从代码删掉、只在注记里留一句，接线锚仍然全绿（假绿）；反过来任何一句注记提到被禁形态，「不得回潮」的反向锚就判红，而为变绿最容易被做的是删注记（丢掉的是防回归的上下文）。落地＝`:broker`/`:app` 测试源集各一份 `withoutComments()`（与 `verify_vector_consumers.py:strip_comments` 同口径），加 `SourceTextAnchorSupportTest`（两副本除 package 行外逐字相同：同一组语料、代码行必须存活、四种注释必须剔净、每条语料的「原文确实含 token」恒真防呆、「剔完不是把整段清空」正面控制——跨模块共享要动 Gradle testFixtures，属构建面，改成用同料自证让「各漂各的」不可能悄悄发生），并把本批三处锚接上。**没有机械扫全仓**：清点反而翻出更大的问题——这条纪律在仓里**散了 14 份、三种覆盖等级**（具名 9 + 内联无具名 ≥5 + 本批新写 2），我第一版按 helper 名数出的「22 个未剔」是错的，「连清点都做不准」就是现状；而正则不认识字符串边界，判内嵌 JS 文本的锚照套会把判据删变形 ⇒ 逐份出处、两条「只因作者顺手写了内联过滤才不判红」的反向锚与可复核的收敛判据登记为 §五 Q59 R9-SH-17 |
| R9-SH-17 | **P2**（R9-B44 登记、R9-B45 落地） | 保留并落地 | 收敛前不是 14 份而是 **15 个文件各自实现**（现读：`git grep -c -F` 三条命令分别给 C# 9 / Kotlin 3 / Python 3，见 §3.45 第 2 点——我第一版按 helper 名数成 22、第二版按两种写法数成 14，都漏了 `filterNot`/`map{}.filterNot` 那两类形状）。收成每语言一份：Python `scripts/text_anchors.py`、C# `windows/tests/Aegis.Windows.TestSupport/SourceTextAnchors.cs`（两个测试工程 `<Compile Link>` 共享同一份文件，不新建工程＝不动构建面）、Kotlin `withoutComments()`（`:app`/`:broker` 两份跨模块副本保留，逐字同形由新门禁判）；内联过滤 0 处；`//` 切到行尾那支过剔修掉；JS 文本面（`injected_js_text.py`）**不并入并写明原因**——那里的语料本身就是注释。新常驻门禁 `scripts/verify_text_anchor_helpers.py`（11 条注入用例）判「实现点集合＝登记集合」双向不变量 + 副本同形 + csproj 链接，接进 `contracts.yml` 既有 job
（不新增必需 context）。**收敛本身又撞出三条口径缺陷**，见 R9-SH-18 | 
| R9-SH-18 | **P2**（R9-B45 收敛过程中被**自家套件判红**才发现＝既有剔注释实现的口径缺陷，不是新端缺功能） | 保留并落地 | 三条都有实测症状：①**`#` 整行无差别剔**会把 Rust `#[unsafe(no_mangle)]` 当注释删掉——`core_unwired_modules_test::test_export_inside_an_unwired_module_is_red` 由红变绿（过剔喂绿）；修法＝`strip_comments(text, path)` 按扩展名启用（`_HASH_COMMENT_SUFFIXES`），C#/Kotlin 那份不剔 `#`。②**块注释排在整行注释之前**：`WebViewHardening.kt:41` 的说明里写着 `"https://*"`，第二个 `/` 紧跟 `*` 构成假块起点，先匹配块就吃到下一个 `*/` 把 `:46` 的真语句删掉——端侧正面控制 `DocumentStartInjectionRegressionTest.kt:72` 当场判红；三份统一成 `//` → `#`（按语言）→ 块 → ` * `，各加一条顺序语料（星号续行必须在块匹配之后，否则删掉的是块的收尾）。③**docstring 不是注释**：我在单源文件的模块 docstring 里逐字写了那份原生决策向量的文件名，消费面门禁立刻报出「登记=[RS] → 实测=[PY,RS]」——说明文字冒充了消费者。④影响面可复核：新旧顺序在同一扫描面双跑，21 份向量的端集**0 处变化**（`collect_consumers` 求差），所以不需要重登记 |
| R9-DOC-17 | P3（R9-B45 顺手现读发现，同批改真） | 保留并落地 | `docs/runbooks/device-validation.md:19` 说 Windows 下载入口是 `WebView/HostWebView.cs:268`（`DownloadStarting`），而 R9-B37 把下载生命周期外迁成 partial 之后 `:268` 已在 `Dispose()` 里（现读：订阅 `HostWebView.cs:158`、判定本体 `HostWebView.Downloads.cs:41`）⇒ 改成指向**文件+符号**而不是行号，并按第八轮那条口径记档：行号是引用不是事实，重构会把它变成第二条失实声明 |
| R9-SH-5 | P2（R9-B46 回读时**把登记的处方本身纠正**） | 保留并落地（定稿，非「接进裁决链」也非「删列」） | 登记写「`confirmation/risk/audit` 三列在 `agent/broker.py` 零消费 ⇒ 要么被消费要么删列」。逐列现读消费者：`risk` → `contracts/codegen/analyze_action_catalog.py:81`（同 scope 风险冲突）、`audit` → 同文件 `:91`（必填）、`read_only` → `contracts/codegen/verify_agent_catalog.py:43` + `agent/tests/redteam_test.py:87`（首批只读门禁)——**三列里两列一直在被判定**，只有 `confirmation` 全仓零消费者；两个处方因此都不成立（删的是已被判的列，接的是「默认放行→默认需确认」那条 §四 明写不默认执行的方向）。定稿三件、运行时零行为变化：①catalog 头部写死「判定面 4 项 / 治理元数据 5 项」并逐项标谁判它；②analyzer 规则 ⑤ 把 `confirmation` 变成**必填的意图声明**（缺失/不在词表/与只读性矛盾都判红，出厂两条天然满足）；③`tests/python/codegen_and_catalog_test.py::TestCatalogGovernanceColumns` 反向钉住「运行时不读治理列」（用 R9-B45 的单源剔注释后断言四个治理列名在 `agent/broker.py` 零出现，并配判定面四列必须出现的正面控制）⇒ 将来真要接进裁决链会先撞红，逼出带契约向量的另批。夹具 `_action()` 同批补两行，否则「干净夹具」在新规则下判红会让每条专项用例失去诊断力 |
| R9-CI-13 | P3（R9-B46 落地；R9-B21 当时只把 ADR 陈述改真，本批收口实树） | 保留并落地 | 四处 `push.paths`（`ci`=8、`core-rust`=3、`agent-redteam`=5、`supply-chain`=11）删除，理由不是「清单少列一项」而是**清单不可维护**：`ci.yml` 的清单 R8-SH-10 已从 4 项补到 8 项，仍覆盖不住该 job 真实读取的语料闭包。分类与「谁许过滤」从 ADR 的散文变成 `contracts/ci/workflow-categories.yaml`（gates 6 / builds 5 / probes 5）+ `scripts/verify_ci_trigger_surface.py` 的双向对账：未归类/登记不存在/门禁型带过滤/门禁型无 PR 触发/探测型进 PR 面五种都判红；`native-policy-artifacts` 是唯一 `pull_request` 也带过滤的，按 builds 类保留（它产物而非判定质量）。**先跑红灯实录**：删过滤前脚本准确报出四处，删完转绿。代价如实写进 ADR：三个原 `push` 无 branches 限定的 workflow 现在任意分支 push 全量跑 cargo/红队/审计 |
| R9-CI-14 | **P2**（R9-B47 落地，处方与登记不同——理由写在 §3.47 第 2 点） | 保留并落地（换成内容对账） | 「Gradle 依赖图提交面静默坏掉时全仓没有一张牌会变红」这条洞，登记的处方是按墙钟比对最近提交时间；本批改成**内容对账**：依赖图必须包含当前 `android/*/gradle.lockfile` 的每一个 `group:name` 坐标。实测：现读 SBOM 695 个 package（Maven 形态 332），本地四把锁 284 条坐标**全部在册**（差集 0）；注入「少一条坐标」判红并点名该条，注入「图只剩 5 条」走面塌缩分支而不是「零个缺失」；取数失败/形状不对/锁面为空一律 exit 2（取不到图不等于图是新的）。落图是最终一致的 ⇒ `--attempts` 只延迟红、不掩红（`attempts=1` 时同一份迟到数据必须红，用例钉住） |
| R9-CS-3 | P2（R9-B48 定稿并落地；登记原文的事实部分先被回读改准） | 保留并落地（带显式逃生门，不改判定语义） | 三项出货默认改为显式赋值：`AreDevToolsEnabled`、`IsGeneralAutofillEnabled`、`IsPasswordAutosaveEnabled` 全关。**登记的半句事实是错的**——本机 SDK 文档现读（1.0.2903.40 `lib_manual/netcoreapp3.0/Microsoft.Web.WebView2.Core.xml`）：前两条 default true，`IsPasswordAutosaveEnabled` default **false**；而同一份文档写着「关掉之前已保存的密码仍会被自动填充」⇒ 靠默认等于靠这台机器的历史，所以它虽然默认已关，仍然显式写住。落地的理由不是审美：这个产品没有凭证管理界面也没有删除路径，表单历史与密码提示会写进应用自己的 WebView2 Profile 目录，用户在设置里既看不到也删不掉。调试面保留为 `AEGIS_ENABLE_DEVTOOLS=1`（与确认门/原生核心门同形的 env 门，安装器不写）；状态全部留痕。落点唯一（`WebView2Hardening.Apply`，`HostWebView.cs:164` 调用，两窗口共用）。用例 10 条：`DevToolsAllowed` 六种输入钉「只有字面 1 开」、源码锚要求赋值恰好一次、反向锚 `AreDevToolsEnabled = true` 判红（这条能红的前提是先剔注释——「SDK 默认 true」那句话就写在紧邻注释里）、Profile 不可得必须留痕。文档同批跟上且不再抄计数：`privacy-defaults.md` 新增一行、`device-validation.md` Windows 表加第 12 步、`windows-run-guide.md:76` 的「11 项」改成现读命令 |
| R9-SH-19 | P3（R9-B47 落地时新增） | 保留（写成判据设计规则，不改代码） | 任何「X 没跑」的判据若本身依赖一条不被监视的流水线，只是把洞往上挪一层。本轮已有三例同形：Q48 的 paths 过滤 → 登记表双向对账；Q28 的 README 未接线面 → 按 `lib.rs` 现算；Q56 的提交面 → 产物内容对账。后续「检测检测器」一律按这个形状做 |
| R9-DOC-18 | P3（R9-B48 落地时新增） | 保留并落地（改成现读口径） | `docs/runbooks/windows-run-guide.md:76` 抄了「**11 项**」并枚举名称，而它前一次修正是从「10 项」改到「11 项」，本批给 Windows 表加第 12 步后它又过期一次。改成「计数不在此抄 + `grep -c '^| [0-9]'` 现读 + 按名称核对」。同类形状本轮已第三次出现（五门禁数、测试规模数、真机验证项数）：**凡把单源的值再抄一遍进散文，就要在改代码的同一批把它换成指针** |
| R9-DEPS-2 | **P2**（R9-B49 现读发现＝三处文档共同的失实陈述） | 保留并落地（改真 + 补覆盖面 + 常驻判据） | 分诊文档 §三、`android/build.gradle.kts` 头注与本轮 §二 R9-DEPS-1 段都写「logback 3×low **不在本仓任何解析树内**」。四把 STRICT 锁现读：`ch.qos.logback:logback-core:1.3.16=ktlint`（及 `logback-classic`）在四个模块各一条（`android/app/gradle.lockfile:106-107`、`broker:5-6`、`contracts:5-6`、`webview-adapter:15-16`），父节点 `com.pinterest.ktlint:ktlint-cli:1.8.0` ⇒ 它在**工具类路径面**，不是不在树内。这句话能活三轮的原因很具体：`gradle-dependency-insight.yml` 只扫三条面，**从没扫过 `androidLintTool` 与 `ktlint`**——正是这 9 条告警的实际落点；诊断工具的覆盖面决定结论的可信度，而它自己没人判。处置：三处文字改真（不加地板的结论仍成立，理由换成「在 ktlint 工具面、抬它会改 linter 自身运行时、只在构建期存在」）；该 workflow 补「工具类路径闭包」步骤（从锁现读 configuration 归属并直接调新门禁） |
| R9-CI-15 | P2（R9-B49 新增：dismiss 是可过期的决定，此前无判据） | 保留并落地 | 9 条 Maven 告警在用户授权后正式 dismiss（`tnt` + 逐条锁文件行号证据）。但 dismiss 依赖的事实是「这 5 个坐标只在工具/测试类路径」，一次普通 `implementation` 变更就能推翻，而推翻后 GitHub 不会再有任何提示（告警已被自己关掉）。新常驻门禁 `scripts/verify_gradle_alert_scope_boundary.py`：从四把锁现读坐标→configuration 全集，越界进 `release|debug Runtime|Compile Classpath` 或 `debugAndroidTest*Classpath`（装进设备那份算暴露面）判红并点名撤销 dismiss；坐标从锁里整体消失也判红（载体没了不能继续挂着 dismiss）；锁面为空 exit 2。20 条用例含 12 项配置分类表驱动 + 两条正面控制（登记表坐标必须仍在锁里、分诊文档必须逐条含包名）。接进 `contracts.yml` 既有 job |
| R9-RS-8 | P2 | 提升/门禁缺失（已补门禁并落地） | 定稿项 9 步 1：三端各自抄写的那段共享 JS **没有任何门禁判它是否还同形**——`verify_seed_framing_parity.py` 只查要件 token 在不在（有人改算法它照样绿），`tests/canvas_read_channels.rs` 对两端只查 5 段片段（R9-RS-7 记的余量）。落地新门禁 `contracts/codegen/verify_injected_js_parity.py` + 解释层 `injected_js_text.py`，口径是**逐 token** 而非逐字节（逐字节要有一端出生成物＝定稿项 9 步 2，仍在待定稿面）；钉表 7 个共有函数为下界，少一个判「共有面塌缩」不放行 |
| R9-RS-9 | P2 | 问题/三端语义分歧（本批登记不修） | `core/.../shield/canvas.rs:99,106` ↔ `windows/.../FingerprintShield.Canvas.cs:108` ↔ `android/.../WebViewHardeningCanvas.kt:80,112`：两条像素直读包装里「把 proxy/orig 交给 ToStringGuard」的写法三端各不相同——Rust 走 `try { if (window[Symbol.for(REG_SYM)]) …(proxy, orig); }` 配空 catch、C# 调 `registerProxy(...)`、Kotlin 用 `if (__aegisReg) __aegisReg(...)` 且其 **catch 体是 `return orig.apply(...)`**（与 Rust 的空 catch 行为不同）。同批实测还发现两处纯命名漂移已改掉（Kotlin `noiseBit`→`up`、`MAX_NOISE_PIXELS`→`AEGIS_MAX_NOISE_PIXELS`，值本就一致）。注册窗口这条牵动 R8-RS-09 / R9-AD-1 的三端装配，须带测试另批统一；新门禁先把它**显式挂起**并核对「登记项必须仍然不同形」，修齐当天门禁判红一次要求收编 |
| R9-RS-9 **收编** | P2 | 保留并落地（R9-B15，上一条登记行的后半） | 两条像素直读包装的注册尾现在三端同形：C# 此前**裸调** `registerProxy(...)`、Kotlin 此前**裸调** `if (__aegisReg) ...`，两端都补成与 Rust 同款 `try { if (REG) REG(proxy, orig); } catch (e) {}`——这不是排版：注册器一旦抛异常，裸调会让整个包裹安装中断，等于把「不加噪的原文直读」重新放出来（catch 体本身三端行为早已同形：空 catch + 落到统一 `return orig.apply(...)`，只有 Kotlin rect-read 把 return 写在 catch 体内，现改成同形写法）。剩余唯一分歧是**注册器取用路径**（Windows＝ToStringGuard 闭包内的本地 `registerProxy`，Rust/Android＝`window[Symbol.for('proxy.register.v1')]`），由 `injected_js_text._REGISTER_ACCESSOR` 按别名表归一，因此 `DIVERGENT_REGISTERED` 从 2 条收成 **0 条**、比较面从 5 个函数扩到 7 个。别名表**只认登记的键名**（`proxy.register.v1` 与 Rust 的 `{reg_sym}` 占位），故意不写成通配 `window[Symbol.for(…)]`——否则 close 键 `proxy.register.close.v1` 能冒充注册器通过；这条边界有常驻用例与 `--self-test` 用例各钉一次。没有把 Windows 也改成 window 键入口：那会把注册句柄从闭包暴露到页面可达的 window 空间，是**放宽出货安全面**，已列第四节待裁决 |
| R9-CS-1 | P2 | 保留并落地 | 逐行回读确证：主窗 core-ready 段在 R8-CS-SEC-07 已包 `TabRuntimeLifetime.RunCoreReadyFailClosed`，无痕窗 `InPrivateWindow.xaml.cs:137-166` 仍是裸 lambda，且该回调经 Dispatcher 派发（**抛出没有观察方**）—— `runtime.OnCoreReady` 内的 broker `RegisterSession`（会话池 1024 满即抛）一旦抛出，就留下「已挂载可见、却没接上策略处理器」的标签，且会话在池里泄漏。修法与主窗同形，但**保住两条既有早退语义**（`!e.IsSuccess` 只留痕、`_closed\|\| !_runtimes.ContainsKey` 直接返回），接线体外迁成 `InPrivateWindow.CoreReady.cs`（宿主文件在零余量基线上），宿主侧只剩一行订阅；420\→394 行、基线同批改。**这道缺口两轮全绿存在的直接原因是测试只有主窗锚**——新对偶锚 `InPrivateCoreReadyWiringTests`（5 条，含三条内存态反向锚：删包装 / 接线体长回宿主 / 拆除换成只收协调器，都必须判红） |
| R9-SH-12 | P3 | 保留并落地（#144 落地时新证） | `start.main.js:83` 的 `Enter`/空格 选中分支全仓零用例驱动——#144 只补上了方向键那侧的反向判据，所以把整条 Enter 分支删掉仍 117/117 绿。补正向锚（对 `items[1]` 分别触发两种按键，断 `state.engineCalls.slice(-1)` 为 `['bing']`），并把「删掉 Enter 分支」真的做一遍：改 `start.main.js` 后该用例立刻判红并打出 `Enter 必须选中当前项（R9-SH-12 正向判据）`，还原后全绿。该文件在 579 行零余量基线上，故同批重排文件头与 WB-083 注释（原文不改），581\→578 行、基线同批改 |
| R9-SH-2 | P2 | 保留并落地（锁自身失效） | 逐行回读 Q12 并复现：`start_a11y.test.mjs:25-30` 的 `mediaBlock()` 把「媒体块」切成「本 at-rule 到下一个 `@media`」——coarse 块实际 244-259 行，旧切片却一路带到 :364（19189 字符），块外的 `.veil-btn {`（:324）与 `.engine-item:focus-visible`（:353）都算块内命中，且不剔注释（:245-247 的注记原文就写着 `.engine-item`）。**内存态实证**：从 :248 的保底选择器列表摘掉 `.engine-item, .veil-btn`（即回退 R8-SH-13 半个修复），这把新锁与旧的 WB-142 双双仍绿。→ 改成「去注释 + 花括号配对切闭合块 + 边界自证」，并把判据抽成 `touchProblems(css)` 做反向锚（摘保底、把宽度改回 28px 都必须判红） |
| R9-SH-3 | P2 | 保留并落地（零判定） | Q13 确证：`start_main.test.mjs:313` 注释写「触发按键不得选中引擎（仅 Enter/Space）」，实体是一行 `assert.ok(true)`，而同一 `makeHost()` 已把 `setEngine` 记进 `state.engineCalls` 却没用。→ 换成 `assert.deepEqual(state.engineCalls, [], …)`（该文件是 579 行零余量基线，故净零行：改一行注释 + 一行断言、解构多取一个 `state`）。**故障注入自证**：给 `start.main.js` 的 ArrowDown/ArrowUp 分支加一句 `selectEngine(idx)` ⇒ 该用例立刻判红并打出正确消息；还原后 114/114 绿。Enter/Space 的正向面全仓仍零覆盖，另登 R9-SH-12（队列新增 Q47） |
| R9-SH-4 | P3 | 保留并落地（切片无界） | Q14 确证：`start_page.test.mjs:403-405` 用 `SNAKE.substring(SNAKE.indexOf("document.addEventListener('keydown'"))`——`indexOf` 失配返回 -1 时 `substring(-1)` 按 0 处理 ⇒ 退化全文扫描；命中后又一路读到文末。而 `if (!isOpen) return;` 在 `start.snake.js` 出现两次（键盘 :453、触摸 :472）⇒ 实测删掉键盘那一处仍绿。→ 外迁成新文件 `snake_guard_slice.test.mjs`（原文件 490 行零余量，加边界断言必增行）：有界切片 + 剔注释 + 两条反向锚，其中一条**把旧口径的漏判本身钉成文字**（同一删改下旧写法必须仍“通过”） |
| R9-AD-4 | P2 | 保留并按**第四节处方**落地（不收紧段集） | 逐行回读 Q4 的三处位置：`OriginPolicy.kt:104-110` 的 `!host.contains("[")` 是 AD-299 刻意与 Rust `origin/tests/host_grammar.rs:183-184`（`try_parse_external("https://[::1]:8080/x") == None`）及 contracts 的 url-origin-invalid 向量对齐的**导航入口**判定；而 `LocalTargetHosts.hostOf:83-88` 反过来**剥掉**方括号（P74 那笔账的产物）⇒ `::1`/ULA 在升级豁免层与下载层确是放行形态。两侧都对，缺的只是把关系写下来：对象 KDoc 补该分层事实，新跨层锚用例把「导航拒 / 剥出 `::1` / 下载不拒」三侧各钉一次。用户可见后果如实记：地址栏输 `http://[::1]:9000/` 在 Android 打不开，Windows 能。打通它需解冻核心 host grammar 并增补向量 ⇒ 留在第四节待定稿，**本批零判定改动** |
| R9-SH-7 | P2 | 保留并落地（判据曾不可达） | 回读确证三件事：①`DESIGN_NOTATION_MIRRORS`（6 名）恰等于两个生成目录的全集（各 6 份）⇒ 旧 `check_mirror_consumption` 每条都在 `continue` 处跳过，「镜像有没有人消费」这条判据在现树里**从没执行过**；②旧 `_has_real_consumer` 从仓库根 `rglob("*")`，连 `core/rust-policy-core/target`、`obj/`、`bin/`、`node_modules/` 一起爬——本机实测 20,467 个条目、641 个候选源文件、单次调用 ≈5.6s 且每个未豁免镜像各调一次（全表 ≈34s），这个代价本身就让它进不了 PR 面；③扫描口径三处失实：跨语言同名算消费（`agent/action_contract.py` 的 `class ActionContract` 会让 C# 镜像「有消费方」）、测试引用算消费、构建产物里的副本算消费。落地＝扫描面收窄到各端同语言源码根（`windows/src`、`android`）并排除 generated/tests/obj/bin/build/target/node_modules/dist（拆成 `mirror_consumers.py`，门禁本体 280 行、整条 ≈0.5s）；**并加第二条反向不变量**：登记了却已被端侧真实消费同样判红——豁免的前提是「零消费方的设计标注」，前提没了就必须从表里删掉，否则字段漂移与兼容性检查被一句过期声明悄悄跳过。现树实测 6 个镜像在两端 main 源码同语言引用全为 0 ⇒ 豁免仍成立，但从此**要自证**。接线面已核：`contracts.yml:134` 在 `contract-source-of-truth`（ubuntu-latest、`pull_request` 触发）常跑，新常驻 pytest 锚含「跨语言同名不算 / 构建目录不算 / 被消费的豁免项判红」三条故障注入 |
| R9-RS-2 | P2 | 保留并落地（生成物无人核验） | 逐条回读确证：全仓 `import aegis_policy_core` **零命中**（Python 侧无消费者；命中的 `aegis_policy_core` 都是原生库名），而这份 1,910 行入库件的漂移**没有任何门禁在看**——`core-rust.yml:63` 的 `test -s` 判的是同一步里刚生成的 **Kotlin** 文件非空（那是 APK 真正消费的绑定，随构建产出、不入库），`contracts.yml:147`「Fail if generated bindings are stale」只 `git diff` 两个**契约**生成目录；三个 workflow 里 uniffi-bindgen 出现 3 次、`--language` 全是 kotlin ⇒ 这份 Python 镜像只能手跑生成，也就只能手漂。实测漂移内容：`607d7a1`（2026-10-04）加的 `#[uniffi::export] FfiBroker::update_host_denylist`（`src/ffi/broker.rs:323-333`）在入库件里零出现。落地＝用钉住的 1.99.0 + uniffi 0.32.2 本地重 derive 并入库（1,910→2,005 行；diff 恰为该方法的整套 FFI plumbing + 第六轮语义收窄后的 docstring，零第三方漂移）；新常驻门禁 `scripts/verify_uniffi_binding_surface.py` 做**导出名双向对账**（少导出判「绑定缺方法」、删了没重生成判「绑定多方法」；对象键须按 uniffi 的小写拼接归一 `FfiBroker`↔`ffibroker`——首轮实测就是没归一，9 个方法各报两遍）；两处接线：`contracts.yml` PR 面跑 src↔入库件，`core-rust.yml` 同一次构建里补 `--language python` 权威生成后跑生成↔入库件。红线面同步：入库生成物行数不受人控，`bindings/` 入 `GENERATED_PREFIXES`（基线少一条），漂移改由本门禁兜。**没有**采纳「删掉这份无人消费的入库件」——台账给的两条路里删除是产品/架构裁决（该件自 2026-08-22 的原生 UniFFI 集成即在库），本轮只把「静默落后」变成「落后即红」 |
| R9-RS-6 | P3 | 保留并落地（**修法与队列处方不同**，理由见实测） | 回读确证：`security_policy.rs:233` 的 `is_high_risk_host` 对未剥端口的入参判**非高危**（`169.254.169.254:8080` 的末段 `254:8080` parse 失败即 false），而「入参须已剥端口」这条硬不变量只活在两处文档里（`ffi/broker.rs:114-121` 的 `policy_host_of` KDoc、用例 `predicate_requires_pre_lowered_host_and_no_port`），后者还把绕过**钉成期望值**。队列原处方是「让签名体现不变量」（newtype 或收窄可见性），照做要动 3 处调用点，而 `security_policy.rs` 恰在 300 行零余量红线上。实测过程先试了另一条直觉修法——「段内含 `:` 即 fail-closed 判高危」——`cargo test` 立刻打出 `192.168.1.1:8080 不应被判为高危主机`：那条既有期望正是第七轮 B8 裁决的钉，说明**惩罚漏剥端口的调用方**会把私网带端口形态判错。最终改法更强也更小：函数内部先取 `:` 前段再判，把不变量从「调用方纪律」换成「函数自证」——漏剥与不漏剥得到同一个答案，绕过形态消失且不需要新类型。B8 面逐字保住（新增 `192.168.1.1:8080` 仍判非高危的断言），IPv6 边界段原样保留（依 PY-069/070 在归一层即被拒，本函数取不到那种入参）。同形绕过在两端孪生里**不存在**：C# `UrlSafety.IsPublicIp` 收 `IPAddress`、Kotlin `ReservedAddressBoundary.denies(url)` 经 `LocalTargetHosts.hostOf` 自己剥端口 ⇒ 只有核心这一侧要修 |
| R9-RS-7 | P3 | 保留并落地（测试余量接上） | 回读确证：`canvas_read_channels.rs:101-114` 的三端对账只查 5 段片段（噪声函数头 / px 绝对序号 / 未包裹捕获 / 两个 wrapper 名），**不查** 8 位 RGBA 守卫与两条 `aegisNoiseRectangle` 调用行——而同文件对 Rust 生成脚本查的是 8 段。两次内存态注入各自实证旧口径零红：把 Android 端 `pixels.length === width * height * 4` 退成 `=== width * height`、把 C# 端 `aegisNoiseRectangle(pixels,` 改掉名字；新口径分别打出 `Android 端缺直读段判据：pixels.length === width * height * 4` 与 `C# 端缺直读段判据：aegisNoiseRectangle(pixels,`。两条调用行按**前缀**钉而不是整行：种子访问器名三端本就不同（Rust/C# 用 `aegisCanvasSeed()`、Kotlin 用 `noiseSeed()`），那是 R9-RS-8 逐 token 门禁里显式登记的分歧面（DIVERGENT_REGISTERED），整行钉会把一条已登记的口径差异误判成缺失 |
| R9-AD-2 | P2 | **一半推翻、一半保留并落地** | 队列给的两个判据里，「`Uri.encode` 缺省保留 `:/?&=` ⇒ 带多参页被截成错目标」**不成立**：本仓自己的实测记录 `docs/audit/audit-search-2026-08-31.md` D-2 写着「Android 用 `Uri.encode`（`/` 编码）」——1 参形态连 `/` 都编，`&`/`=` 更不可能保留；若它保留 `/`，AD-057 就不需要另写等价于 `Uri.encode(text, "/")` 的 `uriEncode` 了。参数值因此不会被外层 query 截断，症状描述是误读（登记时未回读这条记录）。**保留的那一半是真的**：`SENSITIVE_QUERY_PARAMS` 只有精确名 {code,state,token}，真实世界最常见的凭据形态 `access_token`/`refresh_token`/`id_token`/`csrf_token`/`api_key`/`sessionid` 都不等于 `token`/`key`，此前整串编码外发翻译服务 ⇒ 凭据泄漏面（AD-313 自己承认「OAuth Code/State 实际经 query 流转」，名单却只收了裸名）。落地＝`isSensitiveParam`：名字小写并去掉 `-`/`_` 后①命中精确名单（补 key/auth/sid/sig/nonce）或②命中词干表（token/secret/password/passwd/credential/apikey/session/authorization/signature/csrf/xsrf）即剥离；**刻意不把 `key`/`id`/`code` 放进词干**——`keywords`/`keyboard`/`category` 被误剥会让翻译页取错内容，这条界有专门用例钉住。同时**没有**换编码器：`TranslateEntryPrivacyTest` 已用 Robolectric 拿真实 `android.net.Uri.encode`，队列建议的「改用 `SearchEngines.uriEncode`」会把 `/` 从 `%2F` 变成明文（线上形态变更）却换不到任何可测性收益 |
| R9-SH-10 | P3 | 保留并落地（注记失实） | 回读确证：`contracts/vectors/capability-invalid.json` 第 2 条 note 写「schema minItems **未设**——本向量按用户语义拒绝」，而 `capability.schema.json` 的 `actions` 实测已含 `minItems: 1`（PY-097 同口径）⇒ 拒绝理由就是 minItems，注记是失实陈述（读者会以为空数组形态只靠约定保护）。落地＝note 改成当前实况并保留来历（PY-095 记下时 minItems 确实未设），`validate_vector_schemas.py` 复跑 ✅。零判定改动，纯注记改真 |
| R9-RS-3 | P3 | 保留并落地（依赖注记失实） | 回读确证两处：`Cargo.toml` 注记写「getrandom 0.3 为当前主线」而下面钉的是 `getrandom = "0.4"`；又写「ed25519-dalek 经 rand_core 0.6 仍消费 getrandom 0.2」，`cargo tree --offline -i` 实测锁里既无 getrandom 0.2 也无 rand_core 0.6——实况是直接依赖解析到 **0.4.3**（本 crate + tempfile 消费），另有 0.3.4 由 rand_core **0.9.5** 带入（ed25519-dalek 3.0 / curve25519-dalek 5.0 一侧），rand_core 为 0.9.5 + 0.10.1。下一批依赖决策若按注记推断会取错对象。落地＝把实测来源与解析结果写进注记（依赖本身零改动、`cargo metadata --locked` 复跑 ✅）|

| AX-01 | P1（外部第三轮审计 2026-10-11 声称，主代理回读后**降级为「一半保留并落地、一半早已成立」**） | 保留并落地（投递面） | 回读结论要分两段：①「策略链异常时保持原始请求路径」在第八轮 ⑤ 已闭（`HostWebView.WebResourceGuards.cs` 的 `SubresourceDenialFailClosed` 异常回 403 + `subresource_policy_error`），审计报告据此点名的仍是**拒绝之后**那一步：旧代码 `try { e.Response = CreateWebResourceResponse(...) } catch { 只写日志 }`——拒绝已经判出来，合成响应自己抛（COM 对象退休/Environment 释放）却把这条请求退回默认路径 ⇒ **留痕不是拦截**。落地＝两段各自收口：交付返回 false 与交付抛出是同一事实（拒绝没落地）⇒ 都升级到 `CoreWebView2.Stop()`（内核随当前导航一并停掉待发子资源），留重码 `subresource_denial_undeliverable`；不做「换一组参数再试一次」（失败原因是环境失效，换参数不改结局，只会把一次失败刷成两条互不相干的日志）。**关键实现细节**：`escalateStop()` 不能和 `tryDeliver()` 放同一个 try——照直觉写 `try{ if(deliver) return; escalate(); } catch{ log }` 时 tryDeliver 抛出会**跳过升级**，正是审计点名的形态，故拆两段并各自吞（`DeliverDenialNeverThrowsBackToTheEventShim` 用三个同时抛的注入面钉「永不抛出」，含留痕面）。不可达面按 R8-CS-SEC-11 同法补结构锚：handler 本体切片（有界、剔注释）必须含 `DeliverDenial(`/`TryStopWebView` 且**不含** `catch` 与 `e.Response =`，`TryStopWebView` 切片必须真有 `webView.Stop()`。WebView2 真实故障注入（本机无 Runtime）仍属第四节阶段 C，本批只有 JVM/CLR 侧判定面 |
| AX-04 | P1（外部审计声称，主代理回读确证后**保留并落地**） | 保留并落地 | 回读确证：`KillSwitch` 此前只被 broker 的导航/下载/批准入口读取，而 `NtpBridge.Dispatch` 的 `restoreSession`/`importBookmarks`/`importHistory`/`goBack`/`openGeo`/`navigate` 经桥直达数据层与宿主，分发层零检查——README 早期就登记过这个覆盖面缺口，外部审计再次点名为准。落地＝判定单点放在 `Dispatch` 而不是按钮：`SideEffectingOps`（6 项）+ 拒绝码 `lockdown_engaged` + SecurityLog 留痕；**位置选择有实义**——`TryHandle` 对导入三操作走 `Task.Run`（CS-031），判在 `Dispatch` 才使「先排队、后排紧急停止」在执行时被重新验证，判在 `TryHandle` 就退化成入队时快照。判定边界如实登记而非一刀切：只读面（`getEngine`/`getWallpaper`/`bookmarks`/`hasSaved`/`importScan`/`jsError`）冻结期间必须可用（否则设置窗与异常上报一起废、用户看不到状态），`setEngine`/`setWallpaper` 是本机偏好、无网络与数据副作用，同样放行——各有用例钉住，防止下一轮把「统一门禁」误读成「桥里全部拒绝」。反向锚两条：同一批操作在未触发时必须照样落到宿主（证明拒绝来自开关而非「根本没接线」）、同一实例翻转闭包必须立刻生效（证明不是构造时快照）。NTP 桥本身有 `IsTrustedSource` 前置 ⇒ 这不构成远程页面可达路径，审计报告「不能直接认定远程网页能调用这些操作」的限定成立 |
| AX-03 | P1（外部审计声称）→ **主代理裁 P2** | 保留并落地**可直改半边**（详见 §3.22） | 回读：`AegisHomeBridge.isTrustedShellPage()` 判的是顶层文档 URL，`@JavascriptInterface` 不提供调用者 frame 的 Origin——报告说的机制差异属实；但可达链要求「顶层已是壳页 + 壳页内有攻击者可控 frame」，实测 `shared/shell` 四段脚本 + HTML **零 iframe**（`<iframe`/`createElement('iframe')` 均 0 命中，GeoGebra 走 `openGeo` 顶层导航），远程页面自己作为顶层时该判据本就拒 ⇒ 属提前封闭的信任边界，按 P2 排。本批落 CSP 显式 `frame-src 'none'`（把「今天恰好没帧」换成「加帧必须改这行」）+ 5 例常驻锚（两条反向注入实测）；报告另一条处方「拒空/异常 URL」**本已成立**（`isTrustedShellUrl` 对 null/"" 返回 false、`runCatching` 异常按拒，`AegisHomeBridgePrefsTest.kt:149-159` 已钉），按原样登记不重做。迁 WebMessage 传输与「整个 `file:///android_asset/` 前缀受信」两面入 §五 Q50 与 §四 |
| AX-05 / AX-06 | **P1**（外部审计声称，回读确证后保留并落地） | 保留并落地 | 回读确认报告的机制描述属实且比描述更糟：`NativePolicyCoreGate.cs:23-29` 的判定源是「环境变量（只在 CI 那步 shell 里赋值，不随包交付）+ HKCU 标记（普通用户可清除）」，`InstalledBuildMarker.cs:21-25` 甚至自己写着「不能恒真，否则毁掉开发工作流」——于是「不得静默回退到另一套策略实现」这条承诺的实际承载物是一个可删的注册表值；Android 侧 `requireNativePolicyCore` 由构建参数决定，而发布链唯一的锚 （`NativeGateWiringAnchorTest.kt:52-66`）判的是 **workflow YAML 里含不含那行字**，不是编译结果。落地＝要求由**编译进产物**：csproj 的 `GenerateNativePolicyCoreBuildMarker` 目标按 `RequireNativePolicyCore` 生成 `NativePolicyCoreBuildMarker.RequiredByThisBuild`（两条分支都生成，开发构建=false），`Gate.IsRequired` 改三源合一且**构建常量排第一**（纯函数 `ResolveRequirement` 可单测，环境变量仍只认精确 "1"）；发布链改验终物——release-windows 在已发布 dll 的 UTF-16 元数据里找姿态串 `aegis.build.require-native-policy-core=1` 并断言 =0 不出现、并第一次真正打开发布 ZIP 断言 DLL 在里面；release-android 改读 AGP 生成的 BuildConfig（含「找不到生成物即失败」，否则 find 空结果会让后面的 grep 恒真）。**两条实测细节写进注释**：①未被引用的 `const string` 不进元数据（加引用前 grep 命中 0）⇒ App.xaml.cs 那处日志引用是验证手段成立的前提，由测试钉住；②字面量在元数据里是 UTF-16，按 ASCII 找永远 0 命中＝另一种假绿。本机实测两版产物姿态串正确区分。三处文档同步改真（README:23-28、ADR-006:41-45、windows-run-guide:57-68），不留「文档说的≠实树的」。15 例新测试 + Core 832/Broker 204 全绿 |
| AX-02 / AEG-001 | **P1**（外部审计声称，回读后**属实但处方必须改写**）→ 已落地 | 保留并落地（惰性接入） | 缺口是真的：`ffi/broker.rs` 的 `evaluate_navigation` 只调 `validate_action`（第三层），`ContextBroker::evaluate`（broker.rs:247）才串三层，前两个层在 FFI 通路零调用（`broker.rs` 的 H-7 注记自述）。但**照处方直连会拒掉每一次导航**，两条实测事实：①生产构造是 `PolicyEngine::default()`＝空规则，`ActionPolicy::evaluate_opt` 在无规则匹配时返回 None（`action_policy.rs:110` 的 `let rule = best?;`，默认效果只作用于非 opt 的 `evaluate`）⇒ `PolicyEngine::evaluate` 落 `PolicySource::FailSafe` 的恒 Deny；②`CapabilityRegistry::validate` 对未注册 capability 恒拒绝（`capability.rs:156`）而生产注册表恒空。落地口径＝「该层**没有意见**时不改裁决；一旦配置即生效且其 Deny 不可被后面的 Allow 出口改回允许」（单调加严），接入点在会话验证**之前**。9 例新测试的三条关键：未配置时 FFI 拒绝码必须仍是 `session_not_found`（把 FailSafe 当拒绝直连的话这条第一个红）；同一入参配上 deny 规则后必须变 `policy_denied`（一条同时证明「配置生效」与「排在会话验证之前」）；空注册表必须是「未配置」而非「什么都拒」。`RequireConfirmation` 复用既有 `register_pending_approval`，不开第二份授权账；锁毒化仍 fail-closed。今天没有宿主入口注册规则/能力（`register()` 生产零调用）⇒ 出货行为零变更是**设计结果**，价值是把「裁决链不完整」变成「链已闭合、缺的是配置面」。五处文档撤 H-7 陈述（README×2、CLAUDE.md 模块表、ADR-006、ADR-008×2、ADR 索引）；ABI 面零变更（新增都在非导出 impl 块）；577 lib 测试全绿、clippy `-D warnings` 干净；三个零余量文件靠改写更短注记 + `impl Default` 换 derive 守住基线 |
| AEG-006 | P1（外部审计声称，回读后**属实但范围改写**）→ 落地为门禁 + 扩面队列 | 保留并落地（判据化） | 报告说「C# 只连部分向量、Kotlin 主要消费 `url-origin-*`」——按 `git ls-files` 的受管源码面逐份实测（543 个文件，命中口径＝词干作为独立词或完整文件名，排除 markdown 与 `META_LEVEL`（按名遍历整个向量目录的工具面，含门禁自己与它的用例））：**15 份向量里只有 2 份真的两端都跑**（`url-origin-valid/invalid`，CS+AD+RS），11 份有端侧执行者，4 份（`capability-*`/`audit-event-*`）**没有任何端侧执行者**、只被 `validate_vector_schemas.py` 判形状/expected。其余单端事实逐条钉进 `scripts/verify_vector_consumers.py` 的 `CONSUMER_MANIFEST`。两点范围改写：①那四份不是「没人判」——它们的 expected 本就是 `valid`/`deny_schema`，schema 就是判据，不能按「契约件白做」处理；②**Agent 端对契约向量的消费为零**（`AG` 在实测分布里一次都没出现），与 R9-SH-5「`action-catalog.yaml` 的 confirmation/risk/audit 三列 broker 不读」是同一件事的两面。落地＝新常驻门禁（登记表双向不变量 + 跨端支点下界 + 端侧执行者下界 + 扫描面塌缩 exit 2）接进 `contracts.yml` 的 PR 面；注入式自证 8 条从 `--self-test` flag **搬进 pytest**（要人主动敲 flag 的自证＝跑不动的判据，R9-SH-7 同课）；扩面工作另登 §五 Q53 |
| AEG-008 / R9-CS-15 | P3（我登记的原级）→ 用户对 §四 第 9 项说「全部完成」后**落地** | 保留并落地 | 回读确证「仅启动时取一次」属实且**不是**声明与行为不符（旧文案确实明示要重启），所以这是一次行为增强：`ThreatFeedCoordinator` 首刷后进入周期重取（默认 6 小时，节拍/上限/过期倍数三份数字单源在类常量上，界面按 `DefaultRefreshInterval × StaleAfterFactor` 算过期而不是抄一份 18 小时），失败按 2 的幂退避并封顶 24 小时（**只拉长不缩短**——「失败就更快重试」在订阅源 429 时就是自伤），每轮**重读**设置所以改源不需重启，未配置/改成非法值 ⇒ 那一轮零网络活动（原判据不变）。UI 半边把「上次成功更新 / 是否过期」贴上提示位，时间取**缓存文件写入时刻**（`FetchAndStore` 只在抓取+校验+落盘全成功后原子替换，所以它就是「最后一次成功」的权威形态；加字段要同步 SettingsService 快照与两个 XAML 锚，代价远大于收益），保存路径改走 `Active?.RefreshNow()`，旧「要重启才生效」文案连同 XAML 说明句一起撤下并由静态锚反向钉住不得回潮。两条**新出口带来的竞态**是这次改动的实质风险，都已处理并有故障注入锚：①周期循环与「保存即刷」并发 ⇒ 后**完成**的抓取决定最终名单（可能是先发出那个请求的旧结果），加 `_refreshGate` 串行化（改成「已在跑就跳过」会让手动刷新静默失效，不做）；②既有五个用例靠 `await BackgroundTask` 收口防 Dispose 抢缓存文件（CS-350 那笔账），周期化后该任务永不完成 ⇒ 它们必须显式传 `refreshInterval: TimeSpan.Zero`，本类只测启动那一次、周期行为归新用例。坑一条：`TimeSpan.Parse("24:00:00")` 是 **24 天**不是 24 小时（实测断言差值 `24.00:00:00` vs `1.00:00:00`），期望值改成小时数——字符串形态的时间期望值在这里会静默判错一个量级。`MainWindow.xaml.cs`（435 行零余量基线）零改动，调度全在协调器里。本地 Core 859/859、Broker 204/204 全绿（CI 为准）。**残余待裁决**：清空订阅源只停止重取，不解除已生效名单也不删缓存（放松防护的方向）⇒ 新登 §五 Q54 |
| AEG-011 / R8-DEPS-8 | **P2**（外部审计声称 P1，回读后裁 P2：这是加固面缺失而非可利用缺陷）→ 落地 | 保留并落地 | 审计要的两件事里只做了一件半：`dependencyLocking` 已启用，dependency **verification**（整树校验和/签名）没做 ⇒ 新登 §五 Q55（**Q55 已由 R9-B50 / §3.50 落地**，2026-10-14）。回读把第八轮 R8-DEPS-8 的判据更正为「`lockAllConfigurations()` 覆盖的是项目全部**可解析配置**（含 AGP 变体、测试、lint、ktlint/detekt 工具面），不是只覆盖直接依赖」；AD-155 当年的否决理由「双源维护成本」在 STRICT 下翻转成门禁本身——catalog 改了而锁没重算，解析直接失败而不是静默漂移。**故障注入实证两次**：①删掉 `android/app/gradle.lockfile` ⇒ `Locking strict mode: Configuration ':app:debugCompileClasspath' is locked but does not have lock state`（EXIT=1）；②给模块加一条新依赖 `org.apache.commons:commons-text:1.15.0` ⇒ `Resolved '…commons-text:1.15.0' which is not part of the dependency lock state`（EXIT=1）——这条在**改成 root 单源之后又重跑了一次**（注入点 `:contracts:compileDebugKotlin`），证明单源形态下 enforcement 仍然生效，不是「写在模块脚本里才管用」。顺带抓到一个**判据陷阱**：`:app:dependencies` 报表任务把解析失败吞成 `FAILED` 文本并 EXIT=0——所以「锁是否可消费」绝不能用报表任务证明，必须用真正吃 classpath 的任务；这条决定了 dependency-relock 的 gradle 面怎么写。落地＝锁块**单源**写在 root `android/build.gradle.kts` 的 `subprojects` 作用域（模块脚本零副本；本来按「逐模块各写一份」做，是 `:app` 脚本停在 **316 行零余量基线**放不下第 5 行逼出了这个更好的形状——单源顺带把「新增第五个模块忘记加锁」从静默 fail-open 变成自动覆盖）+ 四把入库 `gradle.lockfile`（app 314 行/四把共 277 个唯一坐标）+ 新常驻 `tests/python/gradle_locking_test.py`（9 例：模块清单从 settings 现取、锁块同形、锁文件形态与精确版本、CI 解析的配置必须在锁里、ktlint/detekt 工具面也进锁、SECURITY.md 与 settings 决策记录对得上）+ `relock_sop_test.py` 的 gradle 半边（**重锁任务清单 ⊇ CI 各 workflow 的解析面**，删一条即判红）+ `dependency-relock.yml` 新增 `gradle-relock` job（ubuntu + 与 android-quality 同款 JDK/SDK 口径，只写 deps/* 分支）。本机限制如实登记：`:app:assembleRelease` 在本机 Windows 跑不动（AAPT2 windows daemon 缺 UCRT），release 面的锁覆盖是用 `:app:dependencies --configuration releaseRuntimeClasspath` + broker/adapter 的 release 配置条目实证到位，真正的 release 构建要等 CI 的 ubuntu runner。 |
| R9-CS-10 | **P2**（R9-B33 落地时发现，同批修掉） | 保留并落地 | 「有界读取」在 `HttpClient` 默认 `HttpCompletionOption.ResponseContentRead` 下**根本不成立**：`GetAsync` 返回前响应体已被整包缓冲，`ReadBounded` 只是「缓冲完再量一遍」。实测撞出来的形态不是「超限判定」而是异常：`SourceFetcherTests.cs:185 ChunkedOversizeStopsJustPastTheCap` 第一版跑出 `Cannot write more bytes to the buffer than the configured maximum buffer size: 2147483647`。受影响的两条既有路径 `Core/Security/ThreatFeed.cs:148`、`Core/Favicons/FaviconService.cs:187` 在 R9-CS-2 里是被当作**正例**引用的（它们确实有 Content-Length 预筛与上限常量，缺的正是「对方不声明长度时不缓冲」这一刀）⇒ 修法＝三条带外抓取路径统一 `ResponseHeadersRead`，并由 `windows/tests/Aegis.Windows.Core.Tests/OutOfBandFetchDisciplineTests.cs` 按「含 `GetAsync(` 的文件」现取扫描面钉住——第四条抓取路径出现时自动在判据内，而不是靠有人记得往白名单里加一行 |
| R9-SH-14 | P3（R9-B33 回读 R9-B10 落地件时发现＝**部分闭环的残余**） | 保留并落地 | R9-SH-2/-4 当时把「旧锁恒真」写成证据（「把 R8-SH-13 的修复摘掉，这把新锁与旧的 WB-142 双双仍绿」），却只**新写了强锁**、没删被当场证伪的那三段：`tests/ui-regression/start_page.test.mjs:403-405`（`SNAKE.substring(indexOf(...))` 一路读到文末）、WB-141（`fcBlock` 从 `indexOf` 读到文末）、WB-142（「本 at-rule 到下一个 @media」）⇒ 台账那句「双双仍绿」在落地之后仍然成立。本批删掉三段（该文件 490→474 行），WB-142 的三个控件与 WB-141 的三个系统色并进按花括号配对切块的 `start_a11y.test.mjs`，各配反向锚。写反向锚时又撞出一条：`ButtonFace` 在 forced-colors 块内出现两次（`shared/shell/start.css:389,395`），只替换第一处的注入是**假锚**——改成全量替换后它才真的判红 |
| R9-SH-15 | **P2**（R9-B39 复查**本仓自己的登记表**时发现＝门禁自身判据失实，不是某端缺功能） | 保留并落地 | AEG-006 那张消费面表把「命中」定义为文件名出现在受管源码里，而**注释也算命中**——于是注记可以冒充执行者。实测坐实一份：`native-navigation-decision.json` 登记为 `{CS,RS}`，但 CS 那一面的唯一来源是 `windows/tests/Aegis.Windows.Broker.Tests/BrowserPolicyBrokerNativeGateTests.cs:260` 的一句解释性注释（期望值是手写的，零代码读那份向量），登记表把它改回 `{RS}`，§五 Q53 里那句「已有 C# 消费者……可作为接法模板」同时作废。**这不是个别笔误而是口径缺陷**：覆盖面声明的全部根据就是「这端跑过」，让注记充当证据＝门禁被自己喂绿。修法＝命中前剔注释（C 系块注释 / 行注释 / 块注释续行星号 / `#` 四种形态），并跑「剔前剔后各一遍」求 delta 证明**只有这一份**端集受影响（21 份里 1 变 20 不变；若不是 1 份就说明整张表是注记堆的，要整体重登记）。用例 `test_comment_only_citation_is_not_a_consumer` 带一条**正面控制**（同名写进代码行必须算命中），否则「注释被删干净」会让五条断言全部恒真——R9-SH-7 同课。三档扩面缺口一条没动，本批只把「消费」这个词判干净 |

## 三、本批落地（R9-B1：CI / 门禁面）

1. `release-android.yml`：zipalign 改 `if ! …; then ::error + exit 1; fi`，删尾部纯 echo 门禁步。
2. `dependency-relock.yml`：6 处 in-run `${{ }}` 全部改经 step `env:` 中转
   （`RELOCK_BRANCH` / `RELOCK_ECOSYSTEM` / `RELOCK_RUN_ID`），并在**写回步骤内**加二次
   `deps/*` 守卫（不依赖第一步存在）。
3. `contracts.yml`：`verify_xaml_resources.py` 接入 `contract-source-of-truth`（常跑且已是
   必需项，不新增必需 context ⇒ 不会把 merge box 卡在 waiting，R8-CI-01 口径）。
4. `active_tree_gates.py`：`run_compat()` 面追加 `.github/actions/*/action.yml`，打印
   「N py + M workflow + K composite action」，actions 目录存在却扫不到 ⇒ exit 2。
5. 新常驻门禁 `tests/python/workflow_exit_code_test.py`（9 条）：bash 侧 `X && echo` 断言
   形态判红、名为 gate 却只有 echo 判红、`if ! …` 形态不误红、relock 的 run 块内零
   `${{` + 写回步骤二次守卫在场、XAML 门禁必须在 PR 面、zipalign 必须是真断言。
6. `tests/python/py312_compat_test.py` 补两条：composite action 在面内 + 植入 3.13 API 必判出。
7. `.github/dependabot.yml:2` 的「13 workflow」按实树改 16。

本地门禁全绿：`pytest tests/python` 494 passed / 1 skipped、`ruff`、`bandit`、
`py312-compat（76 py + 16 workflow + 4 composite）`、`check_workflow_shells`、
`check_file_sizes`、`check_markdown_tables`、`check_markdown_links`、`check_doc_claims`。

### 3.0 依赖面前批（2026-10-10，用户定稿「按推荐全执行」项 1 / 2）

四条 Dependabot PR 全部并完（串行并，每次并完等 GitHub 重算 mergeable 再推下一条）：
#126 dtolnay/rust-toolchain、#127 gradle/actions、#133 actions 小版本组、#125 cryptography。

并前逐条做了 **tag↔SHA 核对**（SP-178 口径），不是一路点绿就并：

| PR | 核对结果 |
| --- | --- |
| #126 / #127 / #133 的 upload-artifact 与 setup-node | SHA 与 tag 完全对应 ✓（`gradle/actions@748248d` 需先 peel 注解 tag 才对得上） |
| #133 的 download-artifact | SHA `9000827c` 是 **v8.0.2** 的准备提交，而 Dependabot 保留了我们原来的注释文本 ⇒ 4 处 `# v8.0.1` 变失实。SHA 对、标签错 ⇒ 先并（发布链拿包动作前进一个 patch，行为风险为零），本批把标签改回 `v8.0.2` |
| #125（pip，cryptography 50.0.1→50.0.2） | 审过 diff：包版本变化只有 cryptography 一处，另有 **`colorama==0.4.6` 被重算锁时摘除**。不当噪声放过——`pip install --require-hashes` 在 windows-2025 上跑绿（bandit/pytest/rich 的当前闭包确实不再要求它），故判「锁重算的正常结果」而非丢依赖 |

**项 1（九条 Maven 告警）判定为无可升版并结案**：`bcprov/bcutil/bcpkix 1.86`、`jose4j 0.9.7`、
`jdom2 2.0.6.1`、`commons-lang3 3.21.0`、`httpclient 4.5.14` 逐包查
`repo1.maven.org/.../maven-metadata.xml`，**当前钉版即最新已发布版**；Dependabot 也没为它们
开 PR，与此一致。所以 critical（BC name-constraints 绕过）与 high（BC ASN.1 强制解析）
在构建机上仍开放，等上游发版后复检；产品 APK 不受影响（`debugRuntimeClasspath` 闭包零命中）。
`android/build.gradle.kts` 的头注就地补这一段（含「1.85/0.9.6/3.18.0 是 2026-10-03 首次设地板时
的取值、不作现行陈述」的日期更正，顺带把 R9-AD-8 的注记失实闭合）。
   **但同段那句「logback 3×low 维持『不在解析树』原判」是错的，R9-B49 现读推翻**：四把入库锁里
   `ch.qos.logback:logback-core:1.3.16=ktlint`（以及 `logback-classic`）各有一条，
   父节点是 `com.pinterest.ktlint:ktlint-cli:1.8.0` 的传递依赖——它在**工具面**，不在出货面。
   原判之所以活下来：`gradle-dependency-insight.yml` 只扫三条面，从没扫过 `androidLintTool` 与
   `ktlint`（这 9 条告警的实际落点）。本节上方「当前钉版即最新已发布版」对 buildscript 地板成立、
   对这两条 detached 配置不成立（那里仍是 1.80.2 / 3.16.0 / 4.5.6 / 1.3.16）。
   更正、补面与常驻判据见 §3.49。

### 3.2 R9-B3（2026-10-10，定稿项 4 的第一子批）：`Microsoft.NET.Test.Sdk` 17.14.1 → 18.10.1

两个测试工程同步抬版，锁由 `Dependency-Retlock`（dispatch-only，run 38019892345）在 CI 里重算后写回，
人审 diff 结论：**图变化全部可解释**——Test.Sdk 自身的 transitive 集合
（`Microsoft.CodeCoverage` / `Microsoft.TestPlatform.TestHost` / `…ObjectModel`）整体随
17.14.1→18.10.1，而 **`Newtonsoft.Json 13.0.3` 从测试锁里消失**（新 TestPlatform 不再依赖它）。
测试面自查 `grep Newtonsoft windows/tests --include=*.cs` **零命中** ⇒ 没有「靠传递依赖直接用
Newtonsoft」的隐式绑定，去掉是安全的。`verify_lock_rids`（3 把锁、RID 图与中性图都在、
原生件仍钉）与 `check_package_floors`（5 条下界）本地复跑绿；出货 App 项目的锁**未变动**
（diff 只落在两个测试锁上）。

追加核对：NuGet flatcontainer 实测 `xunit.runner.visualstudio` 最新已是 **4.0.1**（不是台账里记
的 4.0.0）——下一子批按 4.0.1 走，不照抄旧记录。

**4.0.1 已落地（#138，merged 0b95c6f）**：锁由 Dependency-Retlock（run 38030614503）重算，写回 diff 人审后**只有** `xunit.runner.visualstudio` 的 `requested/resolved/contentHash` 三字段变化（中性图与 win-x64 RID 图各一处，共 6 行 × 2 个测试锁），零传递依赖增删——比 #125 摘 colorama、#136 摘 Newtonsoft.Json 两例更干净，这次没有需要解释的漂移。CI 侧由刚落的 R9-CI-9 门禁实证**换代没有把发现数打没**：`✅ [Core] 发现测试数 782（下界 700）`、`✅ [Broker] 189（下界 160）`，与 3.1.5 下的本地实测逐字相同。顺序本身就是判据：门禁先于 bump 落地，才有这条对照。

### 3.3 R9-B4（同轮续，定稿项 4 的第二子批前置）：R9-CI-9 发现数下界门禁

**顺序是判定的一部分**：xunit.runner.visualstudio 3.1.5→4.0.1 这一子批的风险恰好是「宿主换代 ⇒
静默零发现」，所以门禁必须**先于** bump 并入，否则 bump 的 PR 自己就是第一个可能假绿的运行。

1. 新常驻门禁 `scripts/assert_test_counts.py`（115 行）：读 `--results-dir` 下全部 `*.trx`，按
   `Counters` 汇总；无目录 / 无 .trx / 不可解析 / 无 `total` 属性 / 计数非整数 ⇒ **exit 2**
   （没有判定输入就不作通过，与 `check_workflow_shells` 空扫描面同口径）；
   `failed+error>0` 或 `total < --minimum` ⇒ **exit 1**。属性名按 TRX 实测为**小写**
   （`total/executed/passed/failed/error/notExecuted`），查表前归一大小写——第一版按 `Total` 查，
   对真实 TRX 恒得 0，是这条门禁自己差点变成恒红的实证。
2. **八处** `dotnet test` 全量接线（不是原先记的四处）：`compat.yml` 两步、`contracts.yml` 两步、
   `native-policy-artifacts.yml` 一步两测（原生模式，`*-native` 标签）、`release-windows.yml`
   一步两测（发布链，`*-release` 标签）。每条命令补
   `--results-directory TestResults/<套件><变体> --logger "trx;LogFileName=…trx"`，
   断言用独立目录，防两个套件计数互相污染。下界 **Core 700 / Broker 160**：
   本轮本地实测 Core `total=782`（第七轮记 771，Test.Sdk 18.10 后自然增长）、Broker 189。
   `--results-directory` 写成相对 cwd 的显式目录是实测决定的：不给它时 TRX 落点随 SDK 版本
   在项目目录与工作目录之间漂，门禁定位不到结果文件就等于没有门禁。
3. `compat.yml:windows-canonical-stack` 与 `contracts.yml:windows-contract-build` 补
   `actions/setup-python` + `python-version: 3.12`——这两个 job 此前不跑 Python，若沿用镜像预装
   解释器，版本不由本仓钉，与 PY-063 的统一 3.12 口径不符。
4. 新常驻测试 `tests/python/dotnet_test_count_gate_test.py`（21 条）：掏空会红（零发现判红、
   缩水判红、失败判红、四类形态不合的 TRX 判 exit 2、一份坏不作部分通过）、不误红（健康 782 判绿、
   多份汇总判绿、大小写归一判绿、相对目录按 ROOT 解析判绿），加接线锚——扫描面必须见到
   4 个 workflow / **8 条** dotnet test，每条都带 `--results-directory` 与 trx logger，
   `--minimum` 条数与 dotnet test 条数一一对应，且下界数字与登记表一致（谁被顺手调松即红）。
5. `CLAUDE.md` 门禁清单与 `docs/runbooks/windows-run-guide.md` 就地补本门禁的本地复现口径；
   `.gitignore` 补 `**/TestResults/`（本轮实跑产生的 1.1 MB TRX 一度是未跟踪残留）。

**第一版 PR #137 自己红了一次，红的是门禁的输出面（→ R9-CI-10）**：

6. `scripts/assert_test_counts.py` 入口 `sys.stdout/stderr.reconfigure(encoding="utf-8",
   errors="replace")`（与 `verify_xaml_resources.py` 同口径）。这层不是为 CI 加的——**本地
   Windows 控制台同样不是 UTF-8**，CI 有 job 级 env 兜住时本地仍会死在同一行。
7. 四个「windows runner + 调 python」的 job 补 `env: PYTHONUTF8: "1"`：
   `compat.yml:windows-canonical-stack`、`contracts.yml:windows-contract-build`、
   `native-policy-artifacts.yml:build-windows`、`release-windows.yml:build`。其余三个
   （`compat.yml:webview2-regression`、`legacy-python-guard.yml:python-archive-guard` 已用
   `PYTHONUTF8`，`dependency-relock.yml:relock` 用 `PYTHONIOENCODING`）本就合规，本轮把
   「只在出事那个 job 修」扩成判定面。
8. 新常驻测试 `tests/python/windows_python_encoding_test.py`（2 条）：实树必须 0 违规且
   **扫描面 ≥7 个 job**（掉了就是解析失灵不是变安全），另有正反双向锚——缺 env 判得出、
   job 级/step 级两种声明都不误判、非 windows 与不跑 python 的 job 不在判定面。
   两层修复各有测试：脚本级 reconfigure 由
   `tests/python/dotnet_test_count_gate_test.py` 的两条 cp1252 用例钉（把 ✅ 打到
   cp1252 流上仍返回 0，且 exit 2 那条分支的说明也必须打得出来）。

本地验证：`dotnet test`（Core，runner 3.1.5）782/782 全绿并落 TRX ⇒ `assert_test_counts.py`
判 782 通过、把下界提到 900 即判红（两个方向都在**真实制品**上证过，不只是合成 XML）；
`check_workflow_shells`、`active_tree_gates ruff|bandit|compat`、`check_file_sizes`、
`check_markdown_tables`、`check_doc_claims` 本地全绿，`pytest tests/python` 515 passed / 1 skipped。

**但 CI 第一次跑就红了**（这正是「本地不可全证」的那一类）：`windows-contract-build` 与
`Build Windows x64 policy DLL` 两个 job 死在 `print("✅ …")` 的 `UnicodeEncodeError`——
本地是 UTF-8 控制台、CI 是 cp1252，所以「本地全绿」对这条判据**没有覆盖力**。修法与常驻测试见
上面第 6–8 条（R9-CI-10），改完 `pytest tests/python` 519 passed / 1 skipped
（= 第九轮起点 494 + 本批 23 + 编码锚 2）、`pytest agent/tests` 81 passed。

**残余**：门禁证的是「发现数没归零/没大幅缩水」，不是「这 782 条断言各自有效」——后者属
R9-DOC-15 的计数口径线，另批处理。（本批 +23 例后实测 Core 791、Broker 189，下界 700/160 未动。）

### 3.4 R9-B5（2026-10-10，定稿项 5）：NewTab 洪水上限 + 新窗口判定收单源

第八轮 §十二 两行都记着「**未做**：`NewTab` 洪水上限（默认阻断类，待用户定稿）」；本仓 16 项
升级清单第 5 项定稿为「同一来源标签 10 秒内 ≤3 次 + 拒绝码」，本批落地（裁决原文
「按推荐全执行」）。

1. **实测缺口**（不是引用）：`HostWebView.cs:131-136` 对 `NewWindowRequested` 一律
   `Handled=true` 后把 URL 转给宿主，两个宿主（`MainWindow.Tabs.cs:82-90`、
   `InPrivateWindow.xaml.cs:188-197`）都直接 `_tabs.NewTab(url)`；而
   `Core/Tabs/TabManager.cs:58-67` 的 `NewTab` **无条件插入**——`MaxTabs`/`TabLimit`/`maxTabs`
   在 `windows/src` 全树零命中（`MAX_TABS=20` 只在 `legacy/…/session_store.py`，且只截断
   恢复会话列表）。⇒ 一句循环 `window.open(...)` 就能无上限开标签，每开一个多一套 WebView2
   运行时 + 一个 broker session，即 CS-382 同族的「页面耗尽宿主资源」。
2. **新增 `Core/NewTabGate.cs`**（单源闸门，188 行）：地址边界在前、限流在后（保留地址不该
   打开，也不该消耗配额）；键是**来源标签**而不是窗口/应用（一个页面的洪水不能把别的标签
   饿死）；拒绝文案带拒绝码，限流码 `new_tab_rate_limited` 单源，地址边界的码引用
   `ReservedAddressBoundary.DenyCode` 而不再造一份；计数字典满阈值即回收整窗过期条目
   （拒绝面本身不能成为第二个无界结构），规模跟随**当前**标签数——由 `TrackedTabs` 测试缝
   断言，去掉 prune 调用即红。
3. **两窗合并成一处判定**：删掉 `InPrivateWindow.CanOpenNewWindowLink`（它只是
   `UrlSafety.CanOpenHttpUrl` 的一行委托，存在的唯一理由是「让测试证明两窗同口径」）。
   现在两窗调同一个方法，同口径由构造保证；`MainWindowLogicTests` 那条向量用例改钉该单源，
   向量逐条不变（含 B8 裁决要求的 `192.168.1.1`/`127.0.0.1`/`localhost` 放行）。
4. **行数纪律**：三个基线文件（`MainWindow.xaml.cs`、`MainWindow.Tabs.cs` 356、
   `InPrivateWindow.xaml.cs` 422）都「只许减不许增」，故同批压缩被取代的旧注记
   （CS-355/CS-386 四行并两行）并删 `CanOpenNewWindowLink`，基线随 PR 收窄。
5. **新增 9 例** `NewTabGateTests.cs`：冷启动豁免（防把 `PopupRateLimiter` 的 0 起步缺陷
   抄进来，见 R9-CS-5）、窗口内第 4 次拒且文案带码、窗口整滑过后恢复（`WindowMs-1` 仍拒 /
   `WindowMs` 放行）、按标签隔离、保留地址不烧配额、两个码互不串、字典规模有界、`Forget` 生效。
6. 本地验证：`dotnet build`（App，Release win-x64）**0 警告 0 错误**；`dotnet test Core.Tests`
   **791/791 全绿**（782 + 本批 9 例）；新文件 188 行 ≤300 红线内，`InPrivateWindow.xaml.cs` 因删 `CanOpenNewWindowLink` 净减 422→420、基线同批收窄。

**Android 侧不需要同款上限（实测，不是推断）**：`BrowserEngine.kt:65` 显式
`setSupportMultipleWindows(false)`，全仓 `onCreateWindow` **零命中**（WebChromeClient 只覆
permission/fileChooser/progress/title），平台默认 `onCreateWindow` 返回 false ⇒ 页面根本
到不了建标签路径；且该设置被 `BrowserEngineHardeningTest.kt:43` 的
`assertFalse(s.supportMultipleWindows())` 钉着。所以这不是「Android 漏了上限」而是「Android
没有这个面」——若哪天开多窗口支持，必须先接同一个闸门（已记入第六节防下轮重复上报）。

### 3.5 R9-B6（2026-10-10）：R9-AD-4 的分层事实写进 KDoc 与测试（判定零改动）

1. `LocalTargetHosts` 对象 KDoc 补一条「方括号 IPv6 字面量在导航层就到不了本函数」，并写清
   后果：**地址栏输 `http://[::1]:9000/` 在 Android 打不开，Windows 能**；要消掉这条差异得解冻
   核心 host grammar 并增补 `url-origin-*` 向量（三端解析器语义变更），不在本批顺手做。
2. 新跨层锚用例 `LocalTargetHostsTest.bracketedIpv6IsRejectedForNavigation_ButExemptOnceHostIsStripped`：
   同一条 URL 三侧结果各钉一次（`OriginPolicy.tryParseExternal` 拒 / `hostOf` 剥出 `::1` /
   `ReservedAddressBoundary.denies` 不拒）。作用域是**双向**的——既防下轮把「段集放行」误读成
   「IPv6 本机可打开」（Q4 报的正是这种误读），也防有人为了「对齐 Windows」把段集收紧。
3. `ReservedAddressBoundaryTest.loopbackPrivateAndCgnatStayOpenableByRuling` 的原注释本就写明
   「下载层」，本批只补一句分层指针。
4. **验证边界如实说**：ktlint/detekt 的独立 CLI jar 本会话已不在本地（`.audit-tmp/` 只剩脚本），
   Gradle 也跑不起来（`~/.gradle` 无 AGP 产物）⇒ 这三处改动（两段注释 + 一条用例）的格式判据
   只有 CI 的 `ktlint + detekt 质量门禁`。已把红灯概率压到最低：新增行全部 ≤110 字符（detekt
   MaxLineLength 120）、测试命名沿用仓内既有下划线形态（`DownloadPolicyTest.kt:19` 等已在 CI 绿过）、
   用例只用该模块已有的断言 import。但**不能声称本地已证**。


### 3.1 R9-B2（同轮续）：R9-AD-1 的三端修法

1. **Android 合成单条 blob**：`fingerprintShieldScript = StagesSeed + StagesShield +
   BRIDGE_GUARD_JS + REGISTER_CLOSE_JS`，`install()` 只注册一条脚本。撤销行从
   `WebViewHardeningStagesShield.kt` 移到装配点并**永远是最后一句**——顺序由构造保证，
   不再有「两条脚本谁先」这个不可控变量；顺带消掉「第一条成功、第二条失败」的部分注入态。
2. **三处 register 改传递解析**（Rust `tostring_guard.rs`、Kotlin `StagesSeed.kt`、
   C# `FingerprintShield.cs`）：`while (proxyMap.has(target) && hops < 8) target =
   proxyMap.get(target)`，登记 `proxy → 最底层原生`。RS-252 拒绝 `proxy→proxy` 的动机是对的
  （那会把内层包装源码经 `origToString.call(内层)` 吐出去），但结论应是**解析**而不是拒绝登记；
   `hops < 8` 防环。
3. **测试同步**：`tostring_guard/tests.rs`（含一条「旧拒绝式必须消失」的反向锚）、
   `tests/tostring_window.rs`（Android 面改为断言「撤销不在 shield 段末尾」+「撤销排在桥守卫
   四处注册之后」，读装配文件）、`WebViewHardeningScriptTest.kt`。
4. 本地验证：`cargo test`（lib 568 + tostring_window 5 + vectors/canvas 10 全绿）、
   独立 ktlint CLI 对整个 Android 面 0 违规、独立 detekt CLI 按模块基线 0 问题、
   `dotnet build -r win-x64` 0 警告 0 错误且未改写三把 `packages.lock.json`、
   `verify_bridge_guard.py` 与 `verify_seed_framing_parity.py` 通过、`pytest tests/python` 494。

**残余（不假称已闭）**：真实设备上「页面能否读到包装源码」只能靠真机/WebView 冒烟确证，
本轮全部是静态与单元层证据；`REGISTER_CLOSE_JS` 仍依赖 document-start 早于任何页面脚本，
这条前提第八轮已由「撤销排在宏任务之外」的写法闭合。
### 3.6 R9-B7（2026-10-10，定稿项 12）：公共后缀表补齐 + 收录口径 + 「只增不减」入门禁

Q16（R9-SH-6）报的是**表本身**不完备，而不是副本漂移——原对账门禁只比三端副本与表，
永不判表。本批做三件事，第三件是把「以后别再退化」搬进门禁：

1. **补齐 13 条**（79 → 92）：Q16 点名的 `com.jp`（表里 co/ne/or/go/ac.jp 全有，独缺
   `com.jp`）、`web.app`、`firebaseapp.com`、`workers.dev`、`wordpress.com`、
   `squarespace.com`、`bitbucket.io`；按同一判据另补 `myshopify.com`、`tumblr.com`、
   `storage.googleapis.com` 与动态 DNS 三条 `ddns.net`/`no-ip.com`/`duckdns.org`。
   Rust 侧经 `include_str!` 自动同步，C#/Kotlin 两份内嵌副本同批改。
2. **收录口径写进清单头注**（三条判据 + 两条不收录）：ccTLD 的 NIC 分层段；
   **托管域**——判据是「子域归谁」而不是「服务有多出名」；**动态 DNS**。不收录公共 CDN
   的边缘名与单标签 LAN 名（后者由 `LocalTargetHosts` / `IsPublicHost` 判，往这里加
   它们就是造第二个名字判据）。同时写明代价：加条目会把该后缀下已有站点的种子**重排
   一次**（隔离变细），这是修正归属的一次性账。
3. **新增 `PINNED_SUFFIXES` 门禁**（22 条）：完备性要外部知识、判不了，但「已按判据收
   进来的托管域被后来者顺手摘掉」判得了 ⇒ 头注那句「只增不减」现在可执行。
   门禁自带第五条故障注入（从权威清单删掉 `web.app` 必须判红），pytest 侧三条锚：
   现树钉全、pin ⊆ 表且三份副本都含、摘一条即红。

**未做（保持待定稿）**：Q16 的另一半——「未命中回退两段」改成「回退整主机名」会改变
同站多子域共享种子的产品语义（`a.example.com` 与 `b.example.com` 从同键变异键），
属第九轮 §四 已列的用户决定，本批不顺手改。


### 3.7 R9-B8（2026-10-10，定稿项 13(b)）：可直跑的交付链补 concurrency，禁止取消在跑的运行

`release-core/android/windows` 三条链都是 `workflow_call` + `workflow_dispatch` 双入口
⇒ 编排器一次、手动 dispatch 一次就是**两个并发 run 在同一个版本号上**做 build → sbom →
attestations → 发布资产。PY-007/008 当年消掉的是「tag 直推 + 编排器」双触发，dispatch
这条侧门一直没关。

1. 三个 workflow 补顶层 `concurrency`（`group: <workflow 名>-${{ github.ref }}`，
   `cancel-in-progress: false`）——发布中途取消留下的是半截制品 + 已签 attestation，
   比排队糟；判据是「必须排队」不是「允许抢占」。
2. **边界写进注记**：GitHub 的 concurrency 组是 per-workflow 的，跨 workflow 不互斥 ⇒
   这条只保证「同一条交付链不自我重叠」，父级排队仍由 `release.yml` 的组负责。
   不这么写，下一轮很容易把它当成整条发布链的串行锁。
3. 新常驻测试 `tests/python/release_concurrency_test.py`（3 条）：实树在判定面 ≥3 份
   `workflow_call` 交付链且 0 违规；正反锚（缺 concurrency 判得出、
   `cancel-in-progress: true` 判得出、字符串简写形态不误判、只可被调用与不可被调用的
   都不在判定面）；外加四条 group 名逐字钉。
4. 踩到并当场改掉一处自伤：模板用 `str.format()` 渲染含 `${{ github.ref }}` 的注释块，
   `{{`/`}}` 被 format 当转义吃掉 ⇒ 写出来的表达式变成 `${ github.ref }`（Actions 会当
   普通字符串，group 名就此失去 ref 维度）。由 py-yaml **复读实际值**发现，不是靠肉眼看 diff。
5. **同批未做**：13(a)（把八处 dotnet 命令抽 composite——**已在 R9-B16 落地，见 §3.15**）
   与 13(c)（出货 builder 钉 `ubuntu-24.04`，属用户待定稿面）。

### 3.8 R9-B9（2026-10-10，定稿项 9 步 1）：三端注入 JS 逐 token 同形对账入门禁

1. 新门禁 `contracts/codegen/verify_injected_js_parity.py`（判据层，241 行）+
   `contracts/codegen/injected_js_text.py`（解释层，135 行）。拆两层不只是因为新文件
   ≤300 红线：解释层要讲的「宿主引号与 JS 串不是一回事」和判据要讲的「豁免表必须仍然
   失真」是两件事，混写的第一版 363 行且读起来像一份工具手册。
2. **口径逐 token 而非逐字节**：注释、缩进、标点旁空白不参与；字符串内容与标识符参与。
   逐字节今天做不到——Rust 的 `format!` 把 `{` 写成 `{{`，C# 的原语串缩进 12 空格，
   Kotlin 缩进 6 空格；真要逐字节得有一端出**生成物**，那是定稿项 9 步 2（待定稿）。
3. 两条刻意的「不判」都写了理由：声明关键字 `var/let/const` 归一（三端确有分歧且无行为差，
   判它的净效果是诱导下次把门禁调松）；种子访问器 `aegisCanvasSeed()` / `noiseSeed()`
   归一（各端自己的宿主接线，不属于共享逻辑）。
4. `DIVERGENT_REGISTERED` 是**带真实性核对的**挂起表：`violations()` 要求表里每一条确实
   仍然不同形，修齐却不收编就判红。`--self-test` 第四条注入用例专门证这条判得出——
   豁免悄悄长大是所有白名单式门禁的通用失效形态（本仓 B3 keep 规则与覆盖门禁同族）。
5. 本批实际消掉的漂移：Kotlin 的 `aegisNudge` 参数名 `noiseBit`→`up`、上限常量
   `MAX_NOISE_PIXELS`→`AEGIS_MAX_NOISE_PIXELS`（三端值本就都是 `4096 * 4096`，只是名字
   不同）；其余 5 个共有函数从此进入可判状态（现树 ✅ 通过），剩下 2 个登记为 R9-RS-9。
6. 解释层踩到的两个坑都写进注释防回归：整份宿主文件按 JS 串语义扫会把 Kotlin 三引号当
   串起点（`aegisHostFromOrigin` 因此被读丢，配对只在函数体内部走）；以及注释里写下
   `Path.read_text(newline=)` 会被 py312-compat 判红——第十节第 17 条「静态文本锚被自己的
   注释打红」在本轮的第二次实证。
7. 接线与自证：挂进 `contracts.yml` 的 `contract-source-of-truth`（常跑且已是必需项，
   不新增必需 context ⇒ 不会把 merge box 卡在 waiting）；`--self-test` 四条（改分支 /
   改顶层框定 / 核心函数改名 / 豁免表失真）全部检出且逐字节还原工作树；pytest 侧 13 条锚
   （含「这条门禁必须真被 workflow 接上」）。
8. 本地验证：`cargo test --locked --all-features` 568 + 3 + 3 + 5 + 10 + 4 全绿（Rust 侧
   读 Kotlin/C# 文本的同形用例未受影响）、`pytest tests/python` 538 passed / 1 skipped、
   `ruff` / `py312-compat` / `check_file_sizes`（486 源文件）绿。**Android ktlint/detekt
   本地不可跑**（独立 CLI jar 不在本地、Gradle 无 AGP 产物），已核对改动行均 ≤118 字符且
   命名沿用仓内既有形态，格式判据交 CI。



### 3.9 R9-B10（2026-10-10，PR #144）：三把恒真的前端回归锁改真（R9-SH-2 / -3 / -4）

同一族失效：**源码里字句俱在、判定其实没发生**。三条都逐行回读 + 故障注入确证后才动，
并把「静态文本断言」的自检三件套写进代码注释：① 切片有没有边界（`substring(indexOf(...))` 在 -1 时按 0 处理 = 全文扫描）；② 注释剔了没有（修复注记里
常常原文写着被禁的旧写法与被保的选择器名）；③ 把修复回退半个必须判红。
详见 §二 三行裁决与 §5.2 三条结案标注。

### 3.10 R9-B11（2026-10-10）：无痕窗 core-ready 失败闭合（R9-CS-1）+ 引擎键正向锚（R9-SH-12）

**共同主题：一半的覆盖面不算覆盖。** 主窗那段包了失败闭合、无痕窗没包，而测试只有主窗锚
⇒ 缺陷全绿活过两轮；方向键「不选中」有判据、Enter「必须选中」没有 ⇒ 删掉整条 Enter 分支全绿。

1. `InPrivateWindow.CoreReady.cs`（新）：入口保两条早退（`!e.IsSuccess` 只留痕；窗口已关或
   标签已不在直接返回），接线体 `WireCoreReady` 整体交给 `RunCoreReadyFailClosed`，拆除走
   `TabManager.CloseTab` 完整路径（只收协调器会留「runtime 已销毁、标签还在条上」的死条目）。
   宿主文件 420→394 行。
2. `InPrivateCoreReadyWiringTests.cs`（新，5 条）：形状对偶锚 + 三条内存态反向锚（删包装 /
   接线体长回宿主 / 拆除换成只收协调器）。行为面仍由 `CoreReadyFailClosedTests` 对纯函数核直测
   ——两窗共用同一个核，「同款」由单源保证而不是两处各抄一份再靠测试比对。
3. `start_main.test.mjs`：正向锚（`Enter` 与空格各驱动一次选中），并把「停用 Enter 分支」真的
   做一遍：改 `start.main.js` ⇒ 该用例判红并打出带 R9-SH-12 的消息；还原 ⇒ 117/117。
4. 两个零余量基线文件同批收窄：`InPrivateWindow.xaml.cs` 420→394、`start_main.test.mjs`
   579→578（`file_size_baseline.json` 的 diff 只有这两项）。
5. 本地验证：`dotnet build` 0 警告 0 错误；Core **796/796**（791 + 本批 5 条）、Broker **189/189**；
   `node --test` **117/117**；`py312-compat` / `check_doc_claims` / `check_workflow_shells` /
   `check_file_sizes` 绿。Android 侧本批未触及。

### 3.11 R9-B12（2026-10-10，队列批次 B 第一子批）：镜像消费面判据从「不可达」改成「每次 PR 都跑」

**共同主题：跑不动的判据等于没有判据。** R7-SH-01 把这条判据补进门禁时，扫描面写成了
「仓库根全量 `rglob`」——于是它同时输在两点：贵（单次 ≈5.6s、全表 ≈34s，进不了 PR 面）
和宽（跨语言同名、测试引用、`target/`/`obj/` 副本都算消费）。更糟的是豁免表恰好等于镜像
全集，每条都在 `continue` 处跳过，所以现树里那条判据**一次都没执行过**，而文档写着「镜像
消费面已登记」。

1. `contracts/codegen/mirror_consumers.py`（新，62 行）：只管**怎么扫**——各端同语言源码根
   （`windows/src`、`android`）+ 排除 generated/tests/test/obj/bin/build/target/node_modules/
   dist/.git，单遍遍历、命中集齐即提前退出。三条边界各挡一种蒙混，文件头逐条写明。
2. `verify_contract_compatibility.py`：删掉旧的 `_has_real_consumer`（全仓混扫）与内联扫描器，
   改为委托；`check_mirror_consumption` 由三条判据扩成**四条**，新增 ②「登记了却已被真实消费
   ⇒ 判红，必须删登记」。313→280 行（新文件按 ≤300 红线拆分，不抬基线）。
3. 现树实测：6 个镜像在两端的同语言 main 源码引用数全为 0 ⇒ 豁免**仍然成立**，但从此是
   要自证的声明；整条门禁 ≈0.5s（旧口径光扫描就 ≈5.6s/次），已在 `contracts.yml:134`
   的 `contract-source-of-truth`（ubuntu-latest、pull_request）常跑面上。
4. 新常驻锚 3 条（`tests/python/contract_models_test.py`，20 条全绿）：被消费的豁免项必须判红、
   跨语言同名不得算消费、`build/`/`obj/`/`generated/` 里的引用不得算消费。加上既有「未登记且
   无消费方判红」「死条目判红」「目录缺失不放行」三条，豁免表两头都收紧。
5. 本地验证：`verify_contract_compatibility.py` ✅、`check_file_sizes` ✅（489 文件 / 基线 87 项，
   diff 无新抬基线）、`active_tree_gates ruff|bandit|compat` ✅、`tests/python` 全量绿。
   本批只动 Python 门禁面，未触及三端运行时代码。

### 3.12 R9-B13（2026-10-10，队列批次 B 第二子批）：UniFFI 入库绑定重 derive + 导出面双向对账入门禁

**共同主题：无人生成的入库件，就会无人核验。** 本轮实测的形态是「镜像存在、门禁存在、
两者不相连」：`core-rust.yml` 有一条生成绑定步骤、`contracts.yml` 有一条「stale bindings
即失败」步骤，看起来这条面被管着——实际上前者只生成 Kotlin（不入库）、后者只 diff 两个契约
目录，那份 1,910 行的 Python 绑定自 2026-10-03 起再没被任何机器生成过，于是 2026-10-04
新增的 `update_host_denylist` 落后至今、零红。

1. `core/rust-policy-core/bindings/aegis_policy_core.py`：用钉住的 1.99.0 toolchain +
   uniffi 0.32.2 本地重 derive 入库（`cargo build --release --locked` →
   `aegis-uniffi-bindgen generate … --language python --no-format`），1,910→2,005 行；
   diff 只有两类内容：该方法的 FFI plumbing（符号声明、checksum、`Vec<String>`/u32 转换器）
   与第六轮语义收窄后的 docstring 文本。
2. `scripts/verify_uniffi_binding_surface.py`（新，201 行）：解析 Rust 侧
   `#[uniffi::export]`（impl 上的属性把该 impl 内全部 `pub fn` 计入 FFI 面，
   `#[uniffi::constructor]` 另计一组）与绑定侧 `fn_method_/fn_constructor_/fn_func_` 符号，
   双向差集即漂移；注释行先剔（`ffi/mod.rs:253` 的注记原文就写着「未做 `#[uniffi::export]`」，
   不剔会把文档反例算进导出面）；任一侧零符号 ⇒ exit 2（空面不作通过判定）。
3. 两处接线：`contracts.yml` 新增常跑步骤（PR 面，src↔入库件）；`core-rust.yml` 的生成步骤
   改名并补 `--language python`，用**同一次构建**的权威产物跑生成↔入库件（该 job 补
   setup-python 3.12——PY-065 同口径，不赌 runner 预装）。
4. `scripts/check_file_sizes.py`：`core/rust-policy-core/bindings/` 入 `GENERATED_PREFIXES`
   并把理由写进注释（加一个导出就涨 95 行，按 ratchet 反倒会拦住「把入库件重 derive 成
   当前真相」这个正确动作；不在红线面 ≠ 无人看管，漂移由本门禁兜）。基线同批重建，
   diff 只有那一条登记项被移除（87→86）。
5. 新常驻测试 13 条（`tests/python/uniffi_binding_surface_test.py`）：现树对账为空、
   导出面形状、注释不算导出、对象名大小写归一不误报、缺方法/多方法/缺构造子/缺自由函数
   四类故障注入、`--generated` 模式的前缀与判定、四种空面 exit 2、exit code 1。
6. 本地验证：`verify_uniffi_binding_surface.py` ✅（含 `--generated` 自证）、
   `pytest tests/python` **554 passed / 1 skipped**、`ruff`/`bandit`/`py312-compat` ✅、
   `check_workflow_shells --self-test`（27 个 pwsh 步骤零违规）✅、`check_file_sizes`
   （491 文件）✅、`check_doc_claims` ✅。三端运行时代码零改动。

### 3.13 R9-B14（2026-10-10，队列批次 B 第三子批）：核心主机判据自证端口 + 三端 canvas 余量接上

**共同主题：把「靠纪律」换成「靠形状」。** 一条只在文档里写的入参前提（须已剥端口）和
一份只查一半片段的跨端对账，都不会在缺陷出现时报警——前者被 `cargo test` 里已有的
期望值反过来钉住了绕过，后者删掉端上的 8 位 RGBA 守卫照样绿。

1. `core/rust-policy-core/src/security_policy.rs`（R9-RS-6）：`is_high_risk_host` 入口
   `let host = host.split(':').next().unwrap_or(host);`——「已剥端口」从调用方纪律变成函数
   自证；`169.254.169.254:8080` 判高危、`192.168.1.1:8080` 仍判非高危（B8 裁决不可回退）。
   doc 块同步重排（端口自处段新增、IPv6 边界段事实不变），文件停在 300 行零余量红线上。
   先试过的「段内含 `:` 即 fail-closed」被既有 B8 用例打回，这条实测过程记进 §二。
2. `security_policy/tests/scheme_and_host_predicates.rs`：用例改名
   `predicate_requires_pre_lowered_host_and_strips_port_itself`，断言从 2 条扩到 6 条
   （元数据地址带/不带端口、域名带端口、私网带端口、localhost 两种大小写）。
3. `core/rust-policy-core/tests/canvas_read_channels.rs`（R9-RS-7 余量）：三端片段表从 5 段
   扩到 8 段——`BYTE_RGBA_GUARD` 整行 + 两条 `aegisNoiseRectangle` 调用**前缀**（前缀而非
   整行的理由见 §二：种子访问器名是 R9-RS-8 已登记的三端分歧面）。
4. 反向锚实测两次并原样还原：Android 端守卫退化 ⇒ `Android 端缺直读段判据：pixels.length
   === width * height * 4`；C# 端调用改名 ⇒ `C# 端缺直读段判据：aegisNoiseRectangle(pixels,`。
5. 本地验证：`cargo fmt --all -- --check` ✅、`cargo clippy --locked --all-features
   --all-targets -- -D warnings` ✅（0 警告）、`cargo test --locked --all-features`
   **568 条 lib + canvas 3 / vectors 10 / tostring_window 5 / timer_parity 3 全绿**；
   C#/Kotlin 侧零改动（孪生不收带端口入参，见 §二 R9-RS-6 行末）。

### 3.14 R9-B15（2026-10-10）：两条像素直读包装的注册尾三端收编（R9-RS-9）

**共同主题：豁免表能收编才算修完。** 上一批立门禁时把 `aegisWrapReadPixels` /
`aegisWrapRectRead` 显式挂起，并要求「修齐当天门禁判红一次要求收编」——本批就是那次收编。

1. `windows/.../FingerprintShield.Canvas.cs`（2 处）、`android/.../WebViewHardeningCanvas.kt`
   （2 处）：注册尾补 try 包裹并与 Rust 逐 token 同形。这不是排版差异——注册器抛异常时
   裸调会中断整个包裹安装，等于把「不加噪的原文直读」重新放出来（⑦ 要消除的正是它）。
2. Kotlin `aegisWrapRectRead` 的 catch 体从「体内 return」改成「空 catch + 落到统一
   return」：两条写法行为相同（都是再读一次原像素并返回），但只有后者能与三端对账。
3. `contracts/codegen/injected_js_text.py`：新增 `_REGISTER_ACCESSOR` 别名表，把三端的
   注册器**取用路径**归一成 `__REG__`；只认 `registerProxy` / `__aegisReg` /
   `window[Symbol.for('proxy.register.v1')]` / Rust 模板占位 `{reg_sym}` 四个登记项，
   **刻意不用通配**（否则 close 键可冒充注册器）。理由与三端机制差异写在注释里。
4. `contracts/codegen/verify_injected_js_parity.py`：`DIVERGENT_REGISTERED` 2 条 → 空，
   比较面 5 → 7 个共有函数；`--self-test` 从 4 条扩到 6 条，新增「C# 注册尾丢掉 try 必须
   判红」「Rust 换成未登记的 Symbol 键必须判红」两条——别名表本身也被反向锚住。
5. 常驻测试 +2 条（`tests/python/injected_js_parity_test.py`，现 15 条）：两条包装确实
   不在豁免表且确实同形；别名表按键名收口。原「豁免表必须仍然失真」那条改用注入名字驱动
   （表现在是空的，判据不能跟着失效）。
6. 三端机制未强求一致：Windows 的注册器是 ToStringGuard **闭包内的本地函数**，比
   Rust/Android 发布到 `window` Symbol 键更严（页面脚本拿不到注册句柄）。统一到 window 键
   ＝放宽出货面 ⇒ 进第四节待裁决，不在本批顺手做。
7. 本地验证：`verify_injected_js_parity.py`（7 个共有函数全比对）+ `--self-test` 6 条 ✅、
   `verify_seed_framing_parity.py --self-test` ✅、`cargo test --locked --all-features`
   568 + 集成 ✅、`dotnet test` Core **796/796**（发现数下界门禁同时跑过）、
   `pytest tests/python` **556 passed / 1 skipped**、ruff/bandit/compat/file sizes ✅。
   Android 侧本批只改注入文本，未跑 Gradle（ktlint/detekt 由 CI 判）。

### 3.15 R9-B16（2026-10-10，定稿项 13(a)）：八处 dotnet test 的命令面抽 composite 单源

**共同主题：复制八份的判定面，改一处就是制造分歧。** compat / contracts /
native-policy-artifacts / release-windows 各抄一整行 `dotnet test … -r win-x64
-p:RestoreLockedMode=true --results-directory … --logger "trx;…"` 再各跟一条
`assert_test_counts.py`。给其中一份补参数（`--no-build`、新 logger 设置）其余七份不会红
——本仓记了整轮的「部分闭环」正是这一类。

1. 新增 `.github/actions/dotnet-test-suite/action.yml`（54 行）：五个必填输入
   （project / results-dir / trx-name / label / minimum），命令面与发现数下界断言、
   两条 `$LASTEXITCODE` 处置各只有一份。输入**全部经 step `env:` 中转**，不写进 run 正文
   （R9-CI-2 口径：`${{ }}` 在 shell 解析之前完成文本替换）。
2. **八个调用点**改为 `uses:`（四个 workflow × 2 步），只声明工程/目录/标签/下界；
   workflow 正文里 `dotnet test` 归零（第 8 条锚判「只做一半」）。
3. native-policy-artifacts 与 release-windows 两条 job 各拆出一个「导出原生判定环境」步骤
   （`Resolve-Path` 一次 → 四个变量写 `GITHUB_ENV`），composite 步骤与后面的 publish 读
   同一份路径。**这一步是本次重构的真正风险**：`AEGIS_REQUIRE_NATIVE_POLICY_CORE=1` 一旦
   漏导出，那两个调用点会退化成「托管模式再跑一遍」，而发现数下界照样达标、看不出来。
   因此新锚第 6 条按**步骤顺序**判「导出必须在调用点之前」，并用删掉导出步的内存态注入
   自证它能判红。
4. 接线锚随抽取迁出成 `tests/python/dotnet_suite_composite_wiring_test.py`（12 条）：
   调用点数量与分布、输入齐全、下界与登记值一致、project 与 label 同套件、results-dir
   在 job 内不复用、原生导出在前、composite 正文含全套参数、`${{ }}` 不进 run 正文、
   workflow 里不留 dotnet test；另有四条内存态反向锚（调松下界 / 缺输入 / 工程与标签
   不匹配 / 删掉原生导出）。原 `dotnet_test_count_gate_test.py` 收窄成「脚本判定面」20 条。
5. **判定面缩水也被抓出来了**：`windows_python_encoding_test.py`（R9-CI-10 的锚）在抽取后
   从 7 个「windows + python」job 塌到 5 个——因为它只解析 workflow 正文里的 `python`，
   调用搬进 composite 就等于把这条 UTF-8 判定的覆盖面自己削掉。已扩成
   「含经本地 composite 转发的调用」，并加一条反向锚（只经 action 调 python 的 windows
   job 必须被计入）。这正是本仓反复记的「扫描面悄悄变小 = 看起来更安全」。
6. `dotnet build`（2 处）与 `dotnet publish`（2 处，参数与产物校验各不同）**没有**抽进来：
   没有可合并的重复面，硬抽只会造出条件分支——边界写在 action 头注里，别让下轮以为
   「所有 dotnet 都单源了」。
7. **CI 现场抓出第二条被旧形状钉住的锚**（这正是抽取该付出的账）：
   `windows/tests/Aegis.Windows.Broker.Tests/NativePolicyCoreBridgeLeaseTests.cs` 的
   `NativeModeCoreTestsAreGatedInCi`（R7-CS1-15 的常驻锚）用字面量
   `AEGIS_REQUIRE_NATIVE_POLICY_CORE = "1"` 判「原生开关在作业里置位」——导出改写成
   `"…=1" >> $env:GITHUB_ENV` 后它判红，三张必需检查一起红。锚的**意图**（开关必须在
   Core.Tests 之前生效、publish 在后、判定不被吞）依然成立，所以把锚改成更严的口径：
   ①开关必须是 **GITHUB_ENV 导出**（composite 步骤只继承 job/step env，同一步里的
   `$env:X=` 传不到下一步——旧写法在新结构下会静默退回托管模式，而这恰是抽取引入的
   新风险）；②第一个测试调用点必须排在导出之后；③publish 在 Core 之后且自断退出码；
   ④发现数下界断言随每次测试（文案单源在 action 正文）。**反向锚实测**：把导出改回
   `$env:X = "1"` ⇒ 该用例判红（`失败: 1`），还原后 Broker **189/189** 全绿——不是把
   锚改到「怎么都过」，而是改到「判定更严且仍然会红」。
8. 本地验证：`pytest tests/python` **562 passed / 1 skipped**、ruff / bandit / py312-compat /
   `check_workflow_shells --self-test`（26 个 pwsh 步骤）/ `check_file_sizes` / 三条文档门禁 ✅、
   `dotnet test` Broker **189/189**（含改造后的常驻锚）+ Core 796/796 已在前批同口径跑过。
   **composite 的 pwsh 正文本机不可证**（本机无 pwsh、无 act）：本次 CI 首跑已证明
   inputs→env→run 的解析与判定文案都正确（失败信息打出 `dotnet test（Broker）失败：exit 1`，
   即 label/trx/目录三项输入都到位），8 个调用点里 6 个由 PR 面现场验证；
   release-windows 的 2 个只由静态锚判（该 workflow 仅 tag/dispatch 触发）。
   若 `${{ inputs.* }}` 在 composite 步骤的 `env:` 层不受支持，Actions 会直接报 context
   错误而不是静默变空——CI 当场可辨。

### 3.16 R9-B17（2026-10-10，队列批次 C 第一子批）：翻译入口凭据词干 + 两处注记失实改真

**共同主题：注记也是一种断言，失实的注记会把下一批引到错对象上。** 本批三条里有一条是
真泄漏面（P2），两条是「文字与实树不符」（P3），还有一条**队列自己的判据被推翻**。

1. R9-AD-2（P2，Android `TranslateEntry`）：一半推翻——「`Uri.encode` 缺省保留 `:/?&=`」
   与本仓 D-2 实测记录（`audit-search-2026-08-31.md`：Android 侧 `/` 是编码的）矛盾，
   截断症状不存在；一半落地——敏感参数名单只有裸名 `{code,state,token}`，
   `access_token`/`refresh_token`/`id_token`/`api_key`/`sessionid` 全部漏过，整串编码
   外发翻译服务。新增 `isSensitiveParam`（小写 + 去 `-`/`_` 后：精确名单补
   key/auth/sid/sig/nonce，另加词干表 token/secret/password/passwd/credential/apikey/
   session/authorization/signature/csrf/xsrf）；**词干刻意不含 `key`/`id`/`code`**，
   并有 `benignLookalikeParamsAreKept` 用例钉住不过界。没换编码器（Robolectric 已能
   拿到真实 `Uri.encode`，改用 `SearchEngines.uriEncode` 只会把 `%2F` 变明文 `/`）。
2. R9-SH-10（P3，`contracts/vectors/capability-invalid.json`）：note 写「schema minItems
   未设」而 `capability.schema.json` 实测已含 `minItems: 1` ⇒ 拒绝理由就是 minItems；
   note 改成当前实况并保留来历。`validate_vector_schemas.py` 复跑 ✅，零判定改动。
3. R9-RS-3（P3，`core/rust-policy-core/Cargo.toml`）：注记写「getrandom 0.3 主线」而钉的是
   `"0.4"`；写「ed25519-dalek 经 rand_core 0.6 消费 getrandom 0.2」而 `cargo tree -i` 实测
   锁里没有 0.2 也没有 0.6（实况：直接依赖解析 0.4.3，0.3.4 由 rand_core 0.9.5 带入，
   rand_core 为 0.9.5 + 0.10.1）。注记改成带实测来源的事实，依赖零改动、
   `cargo metadata --locked` ✅。
4. 新常驻用例 3 条（`TranslateEntryPrivacyTest`）：12 个凭据名各剥一次、6 个良性相似名
   各保留一次、`isSensitiveParam` 直测大小写与分隔符不敏感。
5. **本机不可证（如实记）**：Android 侧 Gradle/AGP 产物不在本机 ⇒ Kotlin 编译与
   ktlint/detekt/Robolectric 只有 CI 一条路；已按仓内 CI-green 写法收敛格式
   （多参列表一行一项、赋值换行、行长 ≤120），风险剩「CI 一次跑绿」这一件，由本 PR 现场判定。
   Python/文档面本地全绿：`pytest tests/python` **562 passed / 1 skipped**、ruff ✅、
   `check_file_sizes`（492 文件 / 基线 86）✅、三条文档门禁 ✅。

### 3.18 R9-B19（2026-10-10，队列批次 C 第二子批）：引擎胶囊的「宿主未回包」状态可见 + 测试装载器下沉单源

**共同主题：静默的失败分支不是分支，是盲区。** `if (!data) return;` 看上去无害，
但 null 有两条真实到达路径（桥未挂接、WB-037 的 TTL 兜底），而它抹掉的不只是渲染，
还有痕迹——用户看到的是 start.html 硬编码的「百度」，于是「设置没生效」这件事
在 UI 上伪装成「生效了」。

1. `shared/shell/start.main.js`：`renderEngine(unknown)` 在 unknown 或 `ENGINES` 为空时
   写「未知」；init 的 null 分支改成 `bridgeError('getEngine:init', 'null') + renderEngine(true)`。
   **不猜默认引擎**（真实默认可能是 bing）；顺带把「有 data 但引擎表为空」这支也接上同一判据。
   该文件停在 475 行零余量基线 ⇒ 落地方式是不增行：WB-013 / WB-180 两段注释各重排一行
   （文字不改）+ 把 `// 搜索引擎状态` 并进变量行的尾注。
2. `tests/ui-regression/helpers.mjs`：`loadMain` / `makeHost` / `MAINJS` 从
   `start_main.test.mjs` 下沉单源，并新增两个扩展点——`elementOverrides`（按 id 预置元素初值，
   用来把胶囊预置成硬编码标签）与 `source`（载入改过的源码文本，做内存态故障注入）。
   理由与本仓 WB-206 同一课：装载器只有一份时，第二个用例文件想驱动同一入口就得再抄一份桩，
   两处解析漂移就是第二个假绿源。
3. `tests/ui-regression/start_engine_unknown.test.mjs`（新，4 条）：null ⇒ 「未知」+ 留痕；
   空表 ⇒ 「未知」（对照组）；正常回包照常渲染且**不得**留痕（防误红）；
   **反向锚**：把 null 分支还原成 `if (!data) return;` 后注入源文本重载 ⇒ 胶囊保持「百度」、
   `state.errors` 归零——症状原样重现，证明前两条真的在判它（不改工作树）。
4. `start_main.test.mjs` 578 → **519 行**，`file_size_baseline.json` 同批收窄（diff 只有这一项）。
5. 本地验证：`node --test "tests/ui-regression/*.test.mjs"` **121 pass / 0 fail**（117 + 新 4）、
   `pytest tests/python` 全绿、`check_file_sizes`（494 文件 / 基线 86）/ `check_doc_claims` /
   `check_markdown_tables` ✅。C#/Kotlin/Rust 三端运行时代码零改动。

### 3.19 R9-B20（2026-10-10，队列批次 C 第三子批）：引擎「展示名 + 默认值」进跨端门禁

**共同主题：key 集合对齐了，元数据还是会各说各话。** 五端引擎表的 key 早已双向对账，
但同一个引擎在两窗显示不同名字、换了默认值只落一处，这类事实在门禁里没有任何判据
——`verify_cross_end_lists.py` 从来没看过 key 之外的任何一列。

1. 新增 `scripts/engine_metadata.py`（154 行）：四端 key→展示名逐字比对、五处默认引擎同源、
   「默认值必须 ∈ 核心集」、`start.html` 的胶囊初始文字必须等于默认引擎的展示名
   （这一条把 R9-SH-8 留下的硬编码占位接进判据——写错就红，不靠人记）。
   判据面拆成独立模块的原因与 `mirror_consumers.py` 相同：门禁本体已在 300 行红线上。
2. 范围如实收窄并写进注释：只比**核心引擎集**，C# 的六个扩展引擎名不进面（壳层回退表刻意
   只覆盖核心四引擎）；扩展 key 集仍由既有 `CS_ENGINE_EXTENSIONS` 白名单双向判。
3. SP-154 边界照抄：legacy 归档端文件**缺失** ⇒ 一条告警 + 降级为现役三端；文件在而表解析
   不出 ⇒ fail；`core` 为空 ⇒ 单条告警（对面门禁此时已因 key 集为空而 fail，不叠三条噪声
   把一次失败伪装成多个缺陷）。
4. 新常驻测试 `tests/python/engine_metadata_test.py` 17 条：现树 0 违规、现树扫描面非空
   （四端各 ≥4 名、四端默认值都取到、html 标签取到）、`_NAME_SLOTS`/`_DEFAULT_SLOTS` 指向的
   路径必须仍在库里（防「锚指向已挪走的文件」）、改一端名字 / 改一端默认值 / 默认值不在核心集 /
   html 标签不符 / 表被删 / 四端全空 / legacy 两态 / 空 core 各判得出，末条按端参数化。
5. `CLAUDE.md` 的门禁行同步注明「引擎 key 集/展示名/默认值/壁纸」与新模块位置。
6. 本地验证：`verify_cross_end_lists.py` ✅（现树四端一致）、`pytest tests/python`
   **579 passed / 1 skipped**、ruff / bandit / py312-compat / `check_file_sizes`（496 文件）/
   三条文档门禁 ✅。三端运行时代码零改动（纯门禁 + 测试）。

## 四、待用户定稿（本轮新增四项，其余沿用第八轮 §七）

- **R9-RS-9 的一半（机制对齐）**：Windows 的 ToStringGuard 注册器是**闭包内的本地函数**，
  Rust/Android 则把同一个注册器发布到 `window[Symbol.for('proxy.register.v1')]` 供各段取用。
  本批已把三端注册尾的**写法**收编同形（try + 真值判定），并把取用路径作为已核等价项在
  同形门禁里显式别名；把 Windows 也改成 window 键入口＝把注册句柄暴露到页面可达的
  window 空间（要靠 R8-RS-09 那套「窗口关闭」标志兜着），属**放宽出货安全面**，不默认执行。

- ~~**R9-CS-3**：Windows 未关 `AreDevToolsEnabled`（WebView2 默认 true）与 autofill/密码自动
  保存默认——关闭改变调试与默认 UX，属产品行为变更。~~ **已定稿并落地（R9-B48 / §3.48）**：
  三项显式关 + `AEGIS_ENABLE_DEVTOOLS=1` 显式逃生门（安装器不写）；登记里「密码自动保存默认开着」
  这半句被本机 SDK 文档现读推翻（default false），但它仍是三条里最不能靠默认的一条——
  同一份文档写着「关掉之前已保存的密码仍会被自动填充」。
- ~~**R9-SH-5**：`action-catalog.yaml` 的 `confirmation/risk/audit` 三列在 `agent/broker.py` 零消费。~~ **已定稿并落地（R9-B46 / §3.46）**：逐列现读消费者后发现登记的处方本身不成立——`risk`/`audit`/`read_only` 一直各有静态消费者（`analyze_action_catalog.py:81,91`、`verify_agent_catalog.py:43`、`agent/tests/redteam_test.py:87`），只有 `confirmation` 全仓零消费者；而「接进裁决链」正是本节下面那句「默认放行改默认需确认，不默认执行」。定稿走第三条路：列身份写进 catalog 头部、`confirmation` 变成必填的意图声明（analyzer 规则 ⑤）、反向用例钉住运行时不读治理列。
- **R9-SH-6 的一半**：`public-suffix-list.txt` 未命中时 fallback 改「整主机名」会改变
  同站多子域共享种子的产品语义。该表的**补条目 + 收录口径 + 只增不减门禁**已落地（§3.6），
  只剩这一半未决。
- **本节写作后已推进（2026-10-10 划账）**：`Microsoft.NET.Test.Sdk` 18.10.1 已并 #136；
  `xunit.runner.visualstudio` 4.0.1 走 #138（锁 diff 实测只有那一个包的三字段，零传递漂移）；
  `NewTab` 洪水上限已定稿并落地（§3.4）；Dependabot #125/#126/#127/#133 已全部并完（§3.0）。
  这四项从待裁决面划掉；13(b) 发布子链 concurrency 已落地（§3.7）；定稿项 9 步 1（三端注入 JS 同形门禁）已落地（§3.8），步 2「三端改用它」仍待定稿。
- **真未决**：WebView2 SDK bump（产品行为变更）、子资源 `shouldInterceptRequest`、
  **入库 UniFFI Python 绑定要不要删**（R9-RS-2 的另一条处方：该件全仓零 Python 消费者，
  本轮已把它重 derive 成当前真相并加双向对账门禁，但「留一份无人消费的跨语言镜像」本身
  是架构取舍——删除属产品/架构裁决，不默认执行）、
  Android `dependencyLocking`、核心 JS 生成导出（R8-RS-15）、
  ~~`action-catalog.yaml` 三列（`confirmation/risk/audit`）到底由 broker 消费还是删列并写明
  「治理元数据非判定面」（R9-SH-5，方向是「默认放行改默认需确认」，不默认执行）~~
  **（R9-B46 已定稿：既不接进裁决链也不删列——见 §3.46）**、
  **IPv6 字面量在导航面**（R9-AD-4 的一半：`[::1]:9000` 这类 authority 被
  `OriginPolicy.kt:104-110` 与 Rust `origin/host_grammar` 一致拒，Windows 反而放行 ⇒
  要打通得解冻核心 host grammar 并增补 `url-origin-*` 向量，是跨三端的解析器语义变更，
  不是「剥个括号」的小改。R9-AD-4 的**口径改真**半边已按第四节处方落地（§3.5：KDoc + 跨层锚用例，判定零改动），剩下的「打通导航面」仍是待定稿项。

- **外部第三轮审计（2026-10-11）里不能照做的条目**——审计报告给的处方有几条会改变
  「默认放行 vs 默认阻断」的语义或出货制品的强制方式，逐条列出而不是静默丢弃：
  1. ~~**AX-02 / AEG-001**~~ **已落地（§3.28，用户 2026-10-11 授权「全部完成」）**：当时卡的是「按字面接线会拒掉全部导航」，解法是**「没有意见时不改裁决 + 单调加严」**而不是恒放或恒拒。剩下的只是配置面（谁注册规则/能力白名单从哪来）。原文：源码注释确实记着这条缺口（既有台账 H-7），但「接通」不是补一行调用——
     Windows/Android 现在各自解释 FFI 返回值，一旦把 capability 的许可面并入裁决，
     端侧对 `Allow` 的放大行为要同时定义（本仓已实测过同类放大：某端桥把上游**每一个**
     Allow 都转成 RequireConfirmation，照审计的「一律拒绝异常」写就会全导航需确认）。
     这是核心裁决语义变更，要带三端契约向量另批设计，不当缺陷顺手改。
  2. ~~**AX-05 / AX-06**~~ **已落地（§3.27；用户 2026-10-11 授权「全部完成」）**：
     当时卡的是「设成不可关会让无 DLL 的开发机起不来」——解法不是恒真，而是**按构建属性
     生成常量**：发布链传 `-p:RequireNativePolicyCore=true` ⇒ 产物里 `true`，开发机不传 ⇒
     `false`，两条分支都生成文件所以「忘传参数」不会静默退化。HKCU 标记与环境变量保留为
     第二/第三来源（旧安装升级、运维手工强制）。发布链同时改成验终物（dll 元数据姿态串 +
     ZIP 内容 + Android 生成的 BuildConfig）。
  3. **AEG-009 / AEG-010（Android 局域网 HTTP 与 HTTPS-only 冲突、无痕与 KillSwitch 缺失）**：
     与用户 2026-10-07 定稿「**本机与内网必须能打开**」直接冲突，那条是不可回退裁决；
     Android 无痕模式需要独立数据生命周期设计（`clearCache()` 不等价），先前已否决过
     「退出清 Cookie」「FLAG_SECURE」两刀，同一族不重开。
  4. ~~**AEG-011（Android Gradle dependencyLocking + verification）**~~ **定稿并落地**
     （用户 2026-10-11 说「全部完成」；见 §二 裁决行与 §3.30）。本项登记时写的
     「本机无 Gradle 环境」在 2026-10-11 实测已失实（`~/.gradle/wrapper/dists` 里有
     9.8.0、JDK 21 与 SDK 都在位 ⇒ 重锁本地真跑过一次并把锁入库）。
     审计要的**两**件事只做了一件：`dependencyLocking`（版本锁定）落地，
     dependency **verification**（整树校验和/签名）没做 ⇒ 新登 §五 Q55（**Q55 已由 R9-B50 / §3.50 落地**，2026-10-14）。
  5. **AEG-014（FFI 裸指针/panic 边界）与 §五 攻击面矩阵的十项动态测试**：属审计自述的
     「阶段 C 红队验证」，需要 WebView2 Runtime 与真机（会弹调试窗、写真实数据根）⇒ 需用户在场。
  6. **AEG-016（本地/内网目标风险分类过宽）**：报告自己标「待源码和动态测试确认」，
     且现树 `is_high_risk_host` 的私网放行是第七轮 B8 裁决的钉（有专门用例保护
     `192.168.1.1:8080` 不被判高危，见 R9-RS-6）。它建议的「按发起者信任分级」与
     第 1 条是同一次改造，不单独收紧。
  7. **AX-03 的两半残余**（§五 Q50）：①把 Android 桥的受信面从「整个
     `file:///android_asset/` 前缀」收窄成壳页精确名单——要先确证内置 GeoGebra 页不消费
     该桥，而那份资源是构建期下载、不入库，本机 grep 只能对当前副本负责；②把桥传输从
     `@JavascriptInterface` 迁到 `androidx.webkit` 的 origin-scoped `addWebMessageListener`
     （唯一能拿到帧 Origin 的路），牵动三端共用的 `shared/shell/start.js` 适配层 ⇒ 跨端
     契约变更。本批只落了「不需要动这两处」的那一半：CSP 显式 `frame-src 'none'`。
  8. **Q51 R9-CS-14：Android 要不要有威胁订阅源**（外部审计 AEG-003 的准确范围）。两端
     出厂默认都是空名单放行，差别在 Android 连「让用户开启」的地方都没有。补齐＝新_fetch
     →校验→缓存→灌核心 denylist_整条链，要先定源从哪来、谁签、断网时是否保留最后一份
     已验证情报（审计建议保留，方向与 Windows 现实现一致）。属功能排期，不默认执行。
  9. ~~**Q52 R9-CS-15：威胁情报要不要周期刷新**~~ **已定稿并落地**（用户 2026-10-11 对
     本项说「全部完成」；见 §二 裁决行与 §3.29）。定稿口径：默认 6 小时节拍 + 失败退避
     封顶 24 小时 + 「上次成功更新 / 是否过期」上设置界面 + 保存即刷一次。
     本项残余的「清空订阅源会不会解除已生效名单」**没有**顺手改（那是放松防护的方向）
     ⇒ 新登 §五 Q54。
  10. **Q54 R9-CS-16（本轮落地时新增）：清空订阅源到底应不应该解除已生效的黑名单**。
     现状是「只停止重取，名单继续拦截到进程结束，重启后仍从缓存文件加载」（缓存文件不删）。
     改成「清空即解除＋删缓存」更符合「把配置项清空＝关掉该功能」的用户心智，但它是
     **放松防护**的方向，且要一并决定「误清一次怎么办」⇒ 需用户给话，不默认执行。
     本轮只把提示文案写成事实。
  11. ~~**Q53 第②档要怎么闭**~~ **已定稿并落地**（用户 2026-10-14 批准推荐方案；形状 ②，见 §3.59）。
     定稿口径：`platform_decidable` 由期望值推导、不许省略、不许塌成一块；平台执行者仍为零，
     登记表仍 `{"RS"}`。下面留的是当时的两条候选形状（①未采纳）。
     Q53 第②档（§3.42 核查后新增，两个形状都要人点头）：给
     `native-navigation-decision.json` 接平台执行者，**不是**加一份 C# / Kotlin 用例就能做的——
     43 条里 13 条期望 `require_confirmation`，而两端在常跑（托管）配置下根本产不出这个分支
     （Windows `BrowserPolicyBroker.cs:286` 直接 Deny `native_confirmation_core_required`；
     Android `AndroidBroker.kt:284` 顺延到 `evaluateNavigation`）。可选形状：
     **①把原生变体用例提升成 PR 必需检查**（要同批核对必需 context 集合，避免 R8-CI-01 的
     `Expected — Waiting for status` 卡死 merge box，代价是每条 android/** 与 Windows PR 都要
     跑一次带 `.so`/原生库的构建）；**②给向量加显式分区字段**（如每条 `platform_decidable`），
     门禁判「两端只执行被标记的子集，确认面由核心独占」——这是冻结契约面的词表变更，与
     Q21 R9-SH-11 是同一次定稿。**默认不执行任何一个**：在那之前 `CONSUMER_MANIFEST` 保持
     `{"RS"}`（R9-B39 刚把它从虚记的 `{CS,RS}` 改回来）。
  12. **那 9 条 Maven 告警要不要再处理一次**（§3.60 现读后新增，两个选项都要仓库所有者点头）：
     R9-B49 的 dismiss 已被 2026-10-14T07:09:5xZ 那次扫描重开（现读 `open=9 / dismissed=0 / fixed=3`），
     机制是「vulnerable 版本仍可解析就重开」——`bcprov-jdk18on:1.80.2` 还在 `androidLintTool` 里，
     而告警范围是 `< 1.85` / `>= 1.74, < 1.84`。可选：
     **①再 dismiss 一轮**（同样的理由与证据，代价是下一次扫描还会重开，变成拉锯；
     且每次点击都是一次对外的安全姿态声明）；
     **②fix-forward**——把 lint 工具面那份顶到 ≥1.85（要动 AGP/lint 工具链版本面，
     属构建变更，牵连 `verify_gradle_alert_scope_boundary.py` 的登记表与分诊文档证据）。
     判据面不受影响：`verify_gradle_alert_scope_boundary.py` 常驻判「坐标落在哪条 configuration」，
     这是 `tolerable_risk` 唯一的事实依据，告警 state 已经不是（也未再被当作）证据。
     本项**默认两个都不做**，只把状态与代价写清。

## 五、待回读队列（**必须带 file:line**——第八轮失账的修法）


### 5.1 AD（Android）

- ~~Q1 R9-AD-1~~ **本批已确证并落地**（升 P1）：见 §二 裁决表与 §3.1。修法：Android 合成单条 blob 且撤销为最后一句 + 三处 register 改传递解析（hops 上限防环）。同族的 **R9-AD-3**（下载 3xx 旁路）仍在队列里，未被本批覆盖。
- ~~Q2 R9-AD-2~~ **回读后一半推翻、一半落地**（§二 裁决行 + §3.16）：
  「`Uri.encode` 缺省保留 `:/?&=` ⇒ 截成错目标」与本仓 D-2 实测记录矛盾
  （`audit-search-2026-08-31.md`：Android 侧连 `/` 都编码；若它保留 `/`，AD-057 就不必
  另写等价于 `Uri.encode(text, "/")` 的 `uriEncode`），症状是误读。
  **真的一半**是名单只有裸名 {code,state,token} ⇒ `access_token`/`api_key`/`sessionid`
  原样外发：已加 `isSensitiveParam`（小写 + 去 `-`/`_`，精确名单补 key/auth/sid/sig/nonce，
  另加凭据词干表），并有用例钉住「不过界」（`keywords`/`keyboard`/`category` 保留）。
  「改用 `SearchEngines.uriEncode`」**没做**：Robolectric 已提供真实 `Uri.encode`，
  换了只把 `%2F` 变明文 `/`（线上形态变更），换不到可测性收益。
- ~~Q3 R9-AD-3~~ **本批已闭**（R9-B43 / §3.43：新增 `WebViewDownloadCompletionGuard.kt` +
  `WebViewDownloadCompletionReceiver.kt` + manifest 里 `exported="false"` 的
  `DOWNLOAD_COMPLETE` receiver；完成后读 `COLUMN_URI` 复判、命中即 `remove()` + 留痕 + Toast，
  判据直接复用 `WebViewDownloadTargetGuard.rejectionOf`（一条新判据都没写，且有用例扫全 app
  源面钉住「`rejectionOf(` 只能有两个出处」）；读不到 URI/scheme ⇒ 不撤销（删不可逆）。
  用例 9 条含 B8 裁决的对偶锚、「状态判在地址判之前」的顺序锚与「scheme 取不出不豁免」的方向锚；`:app` 329 条 0 失败。
  **三条平台事实未验**（广播是否投递到非导出 receiver、`COLUMN_URI` 是否真等于跳转后地址、
  `remove()` 是否真删公共目录文件）⇒ 验收步写进 `docs/runbooks/device-validation.md` Android
  第 8 步，`windows-run-guide.md:92` 的「7 项」同步改 8 项）。原条目 ↓
  Q3 R9-AD-3 | P2 | `WebViewDownloadHandler.kt:139-169` 全树零 `setRedirectsAllowed`：
  闸门只判**入队** URL，DownloadProvider 默认跟随重定向 ⇒ `302 → 169.254.169.254` 仍
  落盘公共目录（PR #130 消除的后果复活路径）。建议完成后用 `COLUMN_URI` 对最终地址复判
  + `remove()` + 留痕；`setRedirectsAllowed(false)` 会打断正当 CDN 重定向（产品代价，不推荐）。
- ~~Q58 R9-CS-18~~ **本批结案（R9-B57 / §3.57，判据进 §六）**：桌面实测三场景（一跳 302、两跳、页面内 `click()` 触发 `download`）同一结论——`DownloadStarting` 时刻的 `CoreWebView2DownloadOperation.Uri` **已经是最后一跳的落点**，`Completed` 时不变 ⇒ 原条目「闸门只判入队地址」的前提不成立；后半句也不成立，落点在放行前会过 `BrowserPolicyBroker.cs:111-127` 的 `ReservedAddressBoundary.DeniesRaw`（169.254/16、云元数据、不可判定地址一律拒；第七轮 R7-CS1-02 落的，Android 侧同形是 R8-AD-03）。两个修法（完成后复判 + 删文件 / 重做下载发起链）连同代价一起作废。测量脚本以 `--redirect` 模式入仓（compat 仍只跑静态面：动态面要有浏览器宿主）。本批过程中我自己误判过一次「Windows 缺这道门」——只读了 `DownloadPolicy` 没读 broker，现读后自纠，未新登条目（§3.57 第 4 条记的是这次误读）。此前的「部分推进（R9-B56 / §3.56）」描述的是静态清单那半，一并归档。原条目 ↓
  Q58 R9-CS-18 | P2 | `windows/src/Aegis.Windows.App/WebView/HostWebView.Downloads.cs:48` ↔
  `:112-118`（R9-B43 落地 Android 侧复判时同批复读的新证）：Windows 的下载闸门同样只判
  `DownloadOperation.Uri`（入队地址），R9-B37 加的 `StateChanged` 只做「终态退订 + 摘表」，
  **不复判落点** ⇒ 与 Q3 同型的 `302 → 169.254.169.254` 缺口在正典 Windows 制品上仍在。
  不能照抄 Android 修法的原因写清：Android 靠的是 DownloadProvider 会把 `COLUMN_URI` 改写成
  跳转目标这一事实，而 WebView2 这边**反射只能给出名字**——本批复测
  `CoreWebView2DownloadOperation` 的属性面是 EstimatedEndTime / TotalBytesToReceive / **Uri** /
  ContentDisposition / MimeType / BytesReceived / **ResultFilePath** / State / InterruptReason /
  CanResume（事件面仍是三个，与 R9-B37 一致），有 `Uri` 这个属性**不等于**它在跟随重定向后
  报的是跳转后的地址。所以修它的第一步是拿一台真机/桌面实测那条属性的语义，再决定是
  「完成后复判 + 删文件」还是「改用 `CoreWebView2` 请求侧自行解析跳转」。登记不顺手修：
  前者要先做一次 SDK 语义实测（没有它就只能猜，而猜错的形态是「以为拦住了」），
  后者要重做下载发起链（与 ADR-009 的制品形态牵连）。
- Q4 R9-AD-4 | P2 | `OriginPolicy.kt:104-110` ↔ `LocalTargetHosts.kt:153-159`：方括号
  IPv6 authority 在导航层一律拒 ⇒ `::1`/ULA 的「放行」永不被判定，而
  `LocalTargetHostsTest.kt:26-28`、`ReservedAddressBoundaryTest.kt:62,68` 用
  `http://[::1]:9000/` 当放行样本，读起来像「IPv6 本机可打开」。建议如实写进 KDoc 与
  测试注释（**不得反向收紧段集**，与 B8 相反）。——**部分闭环（R9-B6 / §3.5）**：口径改真那半边已逐行回读并按该处方落地，判定零改动；**仍开着的那半边**是「打通 IPv6 导航面」（要解冻核心 host grammar 并增补向量）⇒ §四 待定稿。
  **2026-10-15 续做（在途分支 `fix/q4-ipv6-navigation`，未开 PR、不可并）**：三端里两端已落地并自证，
  差 Kotlin 与共享向量——
  ①核心 `origin.rs` 收下 `[<v6>]`（`Ipv6Addr` 解析；host 只保留**字面小写**不重排，因为三端 IPv6
  打印格式互不相同，重排会让 origin 跨端不等）；`security_policy::is_high_risk_host` 新增
  `ipv6_is_high_risk`：先把内嵌 IPv4 折叠回 IPv4 判定（`::ffff:7f00:1` 与 `::ffff:127.0.0.1` 必须
  等价，否则刚放开语法就是绕过口），再判 fe80::/10、ff00::/8、`::`、2001:db8::/32；
  **不判** ULA 与 `::1`（B8）。`cargo test` 590 全过，含改写后的 `bracketed_ipv6_authority_grammar`
  （5 个合法 + 8 个仍须拒：`[1.2.3.4]`、`%eth0`、未闭合、`]x`、`:0`、`:99999`、`[]`、段数超限）
  以及 `nonce_tests` 那条「畸形 URL」样本换成 `https://[::1/bad`——旧样本 `[::1]/bad` 现在合法，
  不换就等于用例在判一个已不存在的形态。
  ②C# `OriginPolicy.IsValidHost` 同口径收下并改用 `IPAddress.TryParse` + 要求 InterNetworkV6 族，
  编译通过（0 警告 0 错误）。**现读纠正一条我先前的担心**：`UrlSafety` 早就按字节判 IPv6
  （:60-68 剥方括号、CS-201 对 `%`/残留括号 fail-closed、`IsPublicIp` :178 折叠 IPv4-mapped），
  所以保留地址面**没有活的绕过**——这条队列项缺的确实只有「导航层不放行」。
  ③还差：Kotlin 两处（`isAcceptedHostShape` 的 `!host.contains("[")`、`isExemptIpv6` 要剥括号 +
  折叠 mapped），共享向量（`url-origin-invalid` 那三条 IPv6 移进 valid 并补非法形态；
  `native-navigation-decision` 加 IPv6 段集向量，同批改 `native_vector_partition_test.py`
  钉住的 43/30/13 计数），三端各跑一遍。**不断开一半的理由**：向量是三端共用的单一事实源，
  只改一端的语法会让另两端的向量消费测试立刻红——这正是它被标成跨端契约变更的原因。
- ~~Q5 R9-AD-5~~ **本批已闭**（R9-B40 / §3.40：新增 `android/broker/src/main/kotlin/com/aegis/broker/NonceLedger.kt`
  把账本键与回收判据收成同一前缀约定（`nonceLedgerKey` 幂等折算 + `belongsToNonceLedger`），
  两条消费点都经键折算，回收点改用它；新常驻 `ConsumedNonceLedgerTest.kt` 5 例含一条
  「裸 nonce 入账 ⇒ 摘不掉」的反向锚。`:broker:testDebugUnitTest` 84 例 0 失败。
  **端到端的原生消费路径在 JVM 里到不了**（要真实 `.so`），与 Windows 侧同一限制，故用纯函数＋接线锚）。
  原条目：Q5 R9-AD-5 | P3 | `AndroidBroker.kt:189` ↔ `:368`：原生变体进账本的是 64 位裸 hex nonce
  （无 `sessionId:` 前缀）⇒ 关标签的 `removeIf startsWith` 一条都摘不掉，而注释称
  「销毁会话并移除其已消费 nonce」；`AndroidBrokerTest.kt:414-417` 只钉托管路径形态。
  孪生形态见 `BrowserPolicyBroker.NativeNonceLedger`（R8-CS-REG-01 同源，后果轻得多）。
- ~~Q6 R9-AD-6~~ **R9-B24 已闭**（§3.24）：`approvePendingDownload` 补 `currentWebView()` 归属判定
  （不符**不清槽**，与导航同口径），`newTab`/`switchTo` 各补 `rejectPendingDownload()`；
  新常驻 `DownloadConfirmationOwnershipTest.kt` 7 例，本地 `:app:testDebugUnitTest` 315 例 0 失败。原条目 ↓
  Q6 R9-AD-6 | **P2**（外部审计 AX-07 同一处，由 P3 提级）| `BrowserViewModelConfirmations.kt:104-108`：下载确认缺「仅当前活动标签
  可消费」的归属校验（导航确认有，AD-158），且 `switchTo` 撤销 pending 导航确认却不撤销
  pending 下载确认 ⇒ 后台标签的危险扩展确认可顶到前台标签被批准。提级理由（本批回读）：
  授权必须绑定具体操作与发起者，同一文件里导航确认已经做对（`BrowserViewModelConfirmations.kt:80`
  的 `pending == null || currentWebView() !== pending.webView` ⇒ 拒），而 `approvePendingDownload`
  （:104-108）取出 pending 即 `proceed()`＝用户批准的对象被换成了另一标签的目标 ⇒ 批次 2。
- ~~Q7 R9-AD-7~~ **本批已闭**（R9-B40 / §3.40 第 5 点：三条 when 分支的行内注释各归各位，
  净零增行、行为零改动——三条分支的语义早就由 `TabManagerTest.kt:359/:380/:434` 钉住，
  本批只让注释不再和它们相反）。
  原条目：Q7 R9-AD-7 | P3 | `TabManager.kt:109-130`：`closeTab` 三条 when 分支的行内注释整体错位
  一条（与类 KDoc AD-254 段的正确对应相反）——按注释读会得出与实现相反的激活位语义。
- ~~Q8 R9-AD-8~~ **本批已闭**（见 §3.0 与 R9-DEPS-1：就地补日期更正注记，不改写历史）。
  原条目：Q8 R9-AD-8 | P3 | `android/build.gradle.kts:13-19` 头注声明「1.85 / 0.9.6 / 3.18.0」，
  `:26-32` 实钉 BC 1.86（且拆三条）、jose4j 0.9.7、commons-lang3 3.21.0 ⇒ 按头注做构建
  类路径分诊会与实树对不上账（`docs/security/android-build-classpath-triage.md` 同账本）。
- ~~Q9 R9-AD-9~~ **本批已闭**（R9-B33 / §3.33：解码器单源化成 `android/app/src/main/java/com/aegis/browser/PercentEncoding.kt:26`（`decodeStrict`），`DownloadPolicy.kt` 与 `WebViewDownloadHandler.kt` 两处调用点都改走它）。
  原条目：Q9 R9-AD-9 | P3 | `DownloadPolicy.kt:96`（`URLDecoder`，`+`→空格）↔
  `WebViewDownloadHandler.kt:210,338-364`（`decodePercentStrict`，`+` 字面）：同一「URL
  路径段」两套解码器，而后者注释正是前者的反驳理由；本仓两处自写纪律「不欢迎第二个解析器」。
  落地时把**查询值**也一并改严格（Windows 侧两处都是 `Uri.UnescapeDataString`，见
  `Core/Downloads/DownloadPolicy.cs:65,130`）——两端对同一个 URL 从此解出同一个名字。
- Q10 R9-AD-10 | P3（**待裁决**：桥传输整体迁移属跨端契约变更，§四） | `AegisHomeBridge.kt:95-121` + `SecureWebViewFactory.kt:127-132`：
  `addJavascriptInterface` 对象对所有帧可见（本类 KDoc 自述）而判据只取 `webView.url`
  （主框架），受信面是整个 `file:///android_asset/` 前缀（首页 + GeoGebra）⇒ 壳页内跨源
  iframe 可驱动 `navigate/setEngine/setWallpaper/goBack`。实测 `shared/shell` 现零 iframe
  ⇒ 今日无落点，属一次性加固窗口（androidx.webkit 1.17 的 origin-scoped 重载）。
  外部审计 AX-03 报**同一处为 P1**（理由「frame 身份未被鉴别」）⇒ 主代理裁决 **P1→P2**：
  可达链要求「顶层已是壳页 + 壳页内有攻击者可控 frame」，而 `shared/shell` 全仓零 iframe
  （本批 grep：`<iframe`/`createElement('iframe')` 在 `shared/` 与 Android assets 均 0 命中），
  远程页面自己加载时 `webView.url` 就是那个远程 URL、判据本就拒 ⇒ 是提前封闭的信任边界，
  不是现有绕过，与报告自己的限定一致（「不应声称已经存在远程代码执行漏洞」）。
  批次 3 先做可直改面：壳页 CSP 把 `frame-src` 从「由 `default-src 'self'` 隐含」写成显式声明、
  来源判据拒空/异常 url、补用例；`addJavascriptInterface` 拿不到调用方 frame origin 这条
  残余属平台能力，迁 WebMessage 传输另行裁决。
- Q50 R9-AD-11 | **P2 → 第一半已闭（§3.26），第二半带理由挂起** | 收窄已落地：桥受信面从整个 `file:///android_asset/` 前缀改成壳页精确名单（名单由 `BrowserEngine.HOME_URL` 派生），依据是 dist/geogebra-cache 当前副本对桥零引用（grep AegisBridge/__aegis/android_asset/JavascriptInterface/navigate( 全 0）。第二半（迁 origin-scoped addWebMessageListener）在 frame-src 'none' + 精确名单之后已无「可区分的输入」，要动的却是三端共用的 start.js 两个通道选择点 ⇒ 不做，理由见 §3.26 第 5 项。以下为登记原文（事实仍有效，前缀语义已被替换）：
  原条目 ↓
  Q50 R9-AD-11 | P2 | `android/app/src/main/java/com/aegis/browser/AegisHomeBridge.kt:55,95-99,109-121`
  （`TRUSTED_SHELL_PREFIX = "file:///android_asset/"` + `isTrustedShellUrl` 前缀匹配）
  ↔ `android/app/src/main/java/com/aegis/browser/SecureWebViewFactory.kt:127-132`
  （`addJavascriptInterface(AegisHomeBridge…, "AegisBridge")` 对该 WebView 的**全部**文档与帧生效）：
  桥的受信面是整个 assets 前缀，而不只是首页——内置离线 GeoGebra 页
  （`file:///android_asset/geogebra/GeoGebra/HTML5/5.0/GeoGebra.html`，
  `AegisHomeBridgePrefsTest.kt:151-154` 现把它钉成**受信**）经 `openGeo` 顶层导航后，
  那枚第三方大 bundle 仍能以 `AegisBridge` 调 `navigate/setEngine/setWallpaper/goBack/logError`。
  两个方向都要判，且都必须带实证再动手：①收窄成「壳页精确名单」前要先确证 GeoGebra 页
  自身不消费该桥（该资源由 `.github/actions/prepare-geogebra` 构建期下载、不入库 ⇒ 本机
  只能对 `dist/geogebra-cache` 的当前副本 grep，结论不是对上游版本的保证）；②`androidx.webkit`
  的 origin-scoped `addWebMessageListener` 能给出帧的 Origin，但那是把整条桥传输从
  `@JavascriptInterface` 迁走（页面侧 `Host` 适配层三端共用，`shared/shell/start.js` 一起改），
  属跨端契约变更 ⇒ 入 §四 待裁决。外部第三轮审计 AX-03 的同源出处见 §二 与 §3.22。

- ~~Q55 R9-AD-12~~ **本批已闭（R9-B50 / §3.50）**：档位落在 `android/gradle.properties` 的
  `org.gradle.dependency.verification=strict`（**属性面**生效，不是命令行参数——注入改一个字符
  即 BUILD FAILED 实测过），文档面 495 组件 / 842 条 sha256 / 零豁免，重锁与版本同批补录。
  原登记的三条待定稿按 §3.50 第 1 条定死（不引 PGP、只由授权的 dispatch 重算、零 trusted artifacts）。
  原条目：Q55 R9-AD-12 | P2 | `android/settings.gradle.kts:9-15`（`dependencyResolutionManagement` 的两个仓库源）↔ `android/gradle/`（**无** `verification-metadata.xml`）：
  项 10 落的是**版本锁定**（`gradle.lockfile` 记 group:name:version，**不含校验和**），  外部审计 AEG-011 处方里的另一半 **dependency verification**（`--write-verification-metadata  sha256` + `verification-metadata.xml` + 构建时 `--dependency-verification=strict`）没有做。  差别是可利用的：锁防住「今天解析到新版本」，防不住「同一个坐标的构件被换成别的字节」  （仓库被投毒 / 镜像与上游不一致 / 本地缓存被改写都落在锁的覆盖面外）。本批不顺手做的原因：  开启后**任何**新增依赖都要重算校验和，且 Gradle 默认对缺失条目 fail-closed ⇒ 与 Dependabot   的自动 bump 流是产品级流程变更（要先定「谁签、校验和从哪来、trusted artifacts 怎么豁免」）  ⇒ §四 待裁决。验收口径：CI 里 `--dependency-verification=strict` 跑通  `:app:assembleRelease`，且注入「改动某个 jar 的字节」必须判红。

- ~~Q60 R9-AD-14~~ **本批已闭（R9-B58 / §3.58）**：写回面不再只有一个前缀——dispatch 新增
  `target_kind`（闭集 deps | dependabot），规则单源 `scripts/relock_branch_guard.sh`，
  六处内联守卫收成同一份脚本调用；`kind=dependabot` 只写 `dependabot/*`、face=dotnet 明确
  没有这一面（拒到 exit 2）。原登记的「两条人工路」因此不再是必经之路。
  **验收交代**：原条目要的那条「真实 Dependabot gradle bump PR 同一 PR 带锁+带校验和」本批没有
  （现树无在途 bump，也无法强制 Dependabot 开一条），实证是 dispatch 双腿 + 反例各一次（§3.58 第 6/10 条）；
  下一次真实 bump PR 属于观察项，不另立开着的队列 ID。原条目 ↓
  Q60 R9-AD-14 | P2（R9-B50 落地时发现；登记即待裁决） |
  `.github/workflows/dependency-relock.yml:232`（`case "$target" in deps/*)` 的写回守卫）↔
  `android/gradle.properties:32`（`org.gradle.dependency.verification=strict`）：
  校验和启用后，一条 Gradle 版本 bump 的 PR 会红在「新坐标没有条目」，而**能补条目的那条命令
  只允许写 `deps/*` 分支**（`gradle-relock` job 的二次守卫，`relock_sop_test.py` 判着）。
  Dependabot 的分支名是 `dependabot/…`，于是它的 PR 在 strict 下没有自动补字节的路径。
  当前两条人工路：①把该分支内容 fast-forward 进一条 `deps/*` 分支再 dispatch；②本地跑
  图面 + 文件面那两条命令并把 diff 附进 PR。改成「重锁作业也可写 `dependabot/*`」就是放松一条
  **已被用例钉住的**安全不变量（有写权限的 job 的写入面）⇒ 属需用户裁决的流程变更，不顺手做。
  验收口径：任一路径落地之后，一条真实的 Dependabot gradle bump PR 必须在**同一个 PR**里同时
  带来四把 `gradle.lockfile` 与 `verification-metadata.xml` 的 diff 且 CI 全绿；
  只要还需要人手动补字节，这条就仍然开着。
  同批未验的半边记在 §3.50 第 7 条：`release-android.yml:223` 的 `:app:assembleRelease`
  在本批只跑到**本机**，CI 侧要等下一次真实 dispatch/标签。

- ~~Q61 R9-AD-15~~ **本批已闭**（R9-B53 / §3.53：队列里那两条形状选的是 ①，且做成了**串行**而非并发——`gradle-relock`（ubuntu，锁+字节）之后新 job `gradle-checksum-windows`（windows-2025，只字节、无 `--write-locks`），文件面命令收成 composite action `.github/actions/gradle-checksum-file-face` 供两条腿各 `uses:` 一次；windows 腿的写回守卫只放 `verification-metadata.xml`、锁文件出现在它面前就红。此前 R9-B51 / §3.51 的「部分闭环」说的是判据那一半，那一半不变；「还有一面靠本机手工生成」这半由本批消掉。原条目 ↓
  Q61 R9-AD-15 | P2（R9-B50 第二轮发现，登记不顺手做） |
  `.github/workflows/dependency-relock.yml:219`（`gradle-relock: runs-on: ubuntu-latest`）↔
  `.github/workflows/contracts.yml:278`（windows runner 上的 `./gradlew.bat`）↔
  `android/gradle/verification-metadata.xml`：
  校验和的**字节面跟平台走**——本机生成的那份里 `aapt2` 只有 `aapt2-9.4.1-15978811-windows.jar`，
  `-linux` 形态零命中；而 PR #189 的红是**两个平台的 runner 同报同 6 个构件**，可见「一份文档
  服务两个 runner」要求「每个平台都生成过一次」。现在唯一的权威生成面是 ubuntu 那个 job ⇒
  windows 侧新依赖的字节只能靠本机 Windows 手工跑（没人审 diff、也没门禁判它做过）。
  这是覆盖面缺口而不是小瑕疵。两种形状都要动执行面 ⇒ 需裁决：①给 `gradle-relock` 加 windows 腿
  （矩阵或第二个 job）——两个 job 若都往同一分支推同一份文件，**必须串行或先合并再推**，
  并发推必然互相覆盖；②在 PR 面加一条便宜的「冷缓存解析」哨兵（例如 android-quality 里
  `./gradlew --refresh-dependencies buildEnvironment` 跑一次），让「文档对干净 runner 不完整」
  在合并前就红，代价是每条 PR 重下一次插件类路径。
  验收口径：任一路落地后，一次真实的依赖 bump 必须让**两个平台**的 gradle 作业在同一份文档下绿；
  只要还有一面靠本机手工生成，这条不闭。

### 5.2 SH（shared 壳层与契约）
- ~~Q11 R9-SH-1~~ **本批已闭**（R9-B35 / §3.35：三张 schema 的 `version.pattern` 合一，并与 `release/update_verifier.py` 逐案等价；release/version 两张 schema 的向量面补齐，`version.schema.json` 从此有消费者）。原条目：Q11 R9-SH-1 | P2 | `contracts/schemas/release.schema.json:12` 与
  `contracts/schemas/version.schema.json:12` 的 SemVer pattern 仍是旧宽松式（接受
  `2.2.0-01`、`2.2.0-beta.`、`2.2.0-..`），PY-279 只收紧了
  `contracts/schemas/update-manifest.schema.json:26`；而 `release/update_verifier.py:44-53`
  对这些抛 UpdateRejected ⇒ 发布声明说合法、客户端验证器判非法。两张 schema 零向量
  （PY-013 的向量面只覆盖 4/7）。
  **登记里有一处需要改准**：PY-279 收紧后的 update-manifest 式**仍放过** `2.2.0-01`
  ——前导零规则不在正则里，而在客户端另一段 `_NUMERIC_ID`（PY-184）。所以本批把三张 schema 一起换成与验证器逐案等价的式子，而不是只把两张旧的改成 PY-279 那份。
- ~~Q12 R9-SH-2~~ **已闭（R9-B10 / §3.9；残余的「旧锁本体没删」另由 R9-B33 / §3.33 收掉）** | P2 | `tests/ui-regression/start_a11y.test.mjs:25-30` ↔
  `tests/ui-regression/start_page.test.mjs:443-453` ↔ `shared/shell/start.css:244-258,324,353`：
  `mediaBlock()` 把「媒体块」切成「本 at-rule 到下一个 `@media`」而非闭合 `}`，切片
  5313/19189 字符，含块外的 `.veil-btn {`（:324）与 `.engine-item:focus-visible`（:353），
  且不剔注释（块内注记 :245-247 原文就写着 `.engine-item`）。**内存态注入实证**：从
  `start.css:248` 的选择器列表摘掉 `.engine-item, .veil-btn`（即回退 R8-SH-13 半个修复），
  新锁与旧锁 WB-142 双双仍绿；整块退回 40px 形态才红。——**本批已回读确证并落地**（§二 R9-SH-2）。
- ~~Q13 R9-SH-3~~ **已闭（R9-B10 / §3.9：`assert.ok(true)` 换成 `state.engineCalls` 反向判据）** | P2 | `tests/ui-regression/start_main.test.mjs:313`：注释写「触发按键不得
  选中引擎（仅 Enter/Space）」，实体是一行 `assert.ok(true)`——零判定，而 `makeHost()`
  已提供 `state.engineCalls` 却未取用。**本批已回读确证并落地**（§二 R9-SH-3）；Enter/Space 正向面零覆盖另记为 R9-SH-12（队列新增 Q47）。
- ~~Q14 R9-SH-4~~ **已闭（R9-B10 / §3.9 外迁 `snake_guard_slice.test.mjs`；恒绿旧断言本体由 R9-B33 / §3.33 删掉）** | P3 | `tests/ui-regression/start_page.test.mjs:403-405`：
  `SNAKE.substring(SNAKE.indexOf("document.addEventListener('keydown'"))` 在 indexOf 返
  `-1` 时退化为全文扫描，而 `if (!isOpen) return;` 在 `shared/shell/start.snake.js`
  出现 2 次（:449 keydown 与触摸处理器）⇒ 实测删除全部 document keydown 注册后仍绿
  （WB-133 的锁）。——**本批已回读确证并落地**（§二 R9-SH-4：外迁成新文件 `tests/ui-regression/snake_guard_slice.test.mjs`，原文件在零余量基线上）。
  **R9-B33 补一刀（§3.33 第 7 条）**：那把恒绿的旧断言当时只是「另有一份强的」，本体仍留在
  `start_page.test.mjs` 里——同批的 WB-141/WB-142 也是同一形态。三段已删（−16 行），其中
  WB-142 的三个控件与 WB-141 的三个系统色并进 `start_a11y.test.mjs` 的按花括号配对切片，
  各带反向锚。**留着的后果就是「新旧双双仍绿」这句话到今天还成立**——删掉才算闭。
- ~~Q15 R9-SH-5~~ **本批已闭**（R9-B46 / §3.46）| P2 | 登记给的处方（「要么被消费、要么删列」）回读后**两条都不成立**：`risk`/`audit`/`read_only` 三列其实各有静态消费者（`analyze_action_catalog.py:81,91`、`verify_agent_catalog.py:43`、`agent/tests/redteam_test.py:87`），只有 `confirmation` 全仓零消费者；而把它接进裁决链是 §四 明写不默认执行的「默认放行→默认需确认」方向。定稿＝列身份写进 catalog 头部 + `confirmation` 变成必填的意图声明（analyzer 规则 ⑤）+反向钉住「运行时不读治理列」。以下为登记原文（事实部分仍有效）：
  Q15 R9-SH-5 | P2 | `contracts/policy/action-catalog.yaml:14-35` 声明
  `risk/read_only/confirmation/audit/redteam_fixtures`，而 `agent/broker.py:178-190,278-283,366`
  裁决只读 `name/scope/budget(+default_deny/policy_version)` ⇒ `confirmation` 一列是装饰；
  `contracts/codegen/analyze_action_catalog.py:93-95` 只断 `redteam_fixtures` 非空。
  出厂两条 action 皆只读 ⇒ 今日零行为变化（如实写明）。
- Q16 R9-SH-6 | P2 | `contracts/policy/public-suffix-list.txt`（79 条，自述「三端唯一权威」）
  缺 `com.jp`（而 co/ne/or/go/ac.jp 都在）、`web.app`、`firebaseapp.com`、`workers.dev`、
  `wordpress.com`、`squarespace.com`、`bitbucket.io`；`core/rust-policy-core/src/shield.rs:139-147`
  未命中即返回后两段 ⇒ 表外托管域整域共享站点键（`a.web.app` 与 `b.web.app` 同键）。
  对账门禁只比三副本与表，**永不判表本身完备**。——**条目半边与「只增不减」门禁已落地**（§3.6，79→92 条 + PINNED_SUFFIXES）；
  「未命中回退整主机名」那半仍在第四节待定稿。
- ~~Q17 R9-SH-7~~ **本批已确证并落地**（§二 裁决行 + §3.11）：判据曾不可达（豁免集＝镜像全集
  ⇒ 每条 `continue`；旧扫描单次 ≈5.6s 且把跨语言同名/测试/构建产物都算消费）。现收窄成
  同语言源码根单遍扫（整条门禁 ≈0.5s）并加「被真实消费的豁免项判红」反向不变量；现树 6 个
  镜像同语言引用实测为 0 ⇒ 豁免仍成立但改为要自证。`VersionContract` 全树零引用这一事实
  仍在（豁免表内的合法条目，不是缺陷）。**第八轮 R8-SH-08 重 derive 成功且那时仍未闭**
  （该轮只留了计数）——本批是真闭。
- ~~Q18 R9-SH-8~~ **本批已确证并落地**（§二 裁决行 + §3.18）：init 的 null 回包不再静默——`bridgeError('getEngine:init', 'null')` 留痕 + `renderEngine(true)` 把胶囊显式改成「未知」，空引擎表同分支一并接上；刻意不猜默认引擎（猜错会把搜索发去错引擎）。装载器下沉 helpers.mjs 单源，`start_engine_unknown.test.mjs` 4 条含内存态反向锚（还原旧写法 ⇒ 症状原样重现）。`start.main.js` 零增行（475 行零余量基线，靠两处注释重排 + 一处注释并行换出空间）。
- ~~Q19 R9-SH-9~~ **本批已确证并落地**（§二 裁决行 + §3.19）：展示名四端逐字比对 + 默认值五处同源（含 `start.html` 初始文字＝默认引擎展示名）已进 `scripts/verify_cross_end_lists.py`，判据面在 `scripts/engine_metadata.py`；只比核心集、C# 六个扩展引擎名不进面，SP-154 的 legacy 降级照抄，新常驻测试 17 条。
- ~~Q20 R9-SH-10~~ **本批已确证并落地**（§二 + §3.16）：note 改成当前实况（拒绝理由就是
  `minItems: 1`）并保留来历（PY-095 记下时确实未设）。`validate_vector_schemas.py` 复跑 ✅，
  向量内容与期望零改动——纯注记改真。
- ~~Q21 R9-SH-11~~ **本批已闭（R9-B59 / §3.59）**：两份原生向量的信封同形成
  `protocol`/`version`/`description`/`vectors` 四键（confirmation 把修订号从字符串尾巴拆成
  `version: 3`），`expected_deny_code` 按 `MULTI_STEP_PREFIXES` 自己的规则改成
  `expected_evaluate_code`（数据 7 处 + Rust 消费者同批），并同批引入 `platform_decidable`
  分区。消费者集合**没有**被假装扩面：仍只有 RS。原条目：Q21 R9-SH-11 | P3 |
  `contracts/vectors/native-navigation-confirmation.json:2,12-15` ↔
  `native-navigation-decision.json:2-3`：同一原生 ABI 的两份向量信封不一致（前者只有
  `protocol`、无 `version/description`；期望字段名 `expected_request` /
  `expected_request_code` vs `expected_evaluate` / `expected_deny_code`），且仅
  `core/rust-policy-core/src/c_abi/tests/vectors_confirmation.rs` 一份消费者（C#/Kotlin 零）
  ⇒ 属 B9 词表入冻结面的余量，需定稿。

- Q53 R9-SH-13 | P2 | `contracts/vectors/`（登记时 15 份，R9-B35 起 **21 份**）↔
  `scripts/verify_vector_consumers.py`
  的 `CONSUMER_MANIFEST`（实测端集）↔ `agent/broker.py`（`AG` 零命中）：
  AEG-006 的**扩面**那一半，本批只把它变成可判定的表，没有替任何端新增执行面。三档缺口按代价排序：
  ①`capability-*` / `audit-event-*` / `release-*` / `version-*` **八份**零端侧执行者
  （它们的 expected 是 schema 级的，
  所以「补消费」要先定**由谁判**——C# 的 capability 校验面与 FFI 的 `capability.validate`
  尚未接线是同一件事，见 §四 第 1 项 AX-02）；
  ②`action-valid/invalid`、`native-navigation-confirmation`、`native-navigation-decision`、
  `approvals-replay-and-expiry`、`glob-match`、`update-manifest-invalid` 只有 Rust 执行
  ⇒ 「Windows/Android 与核心同一裁决」对这些命题**未被验证**
  （**这一档不能靠「补一份 C# 用例」闭**——§3.42 逐行实证：`native-navigation-decision`
  的 43 条里 13 条期望 `require_confirmation`，而两端在常跑（托管）配置下都产不出该分支，
  Windows 在 `BrowserPolicyBroker.cs:286` 直接拒、Android 在 `AndroidBroker.kt:284` 顺延到
  evaluate；要么把原生变体用例提升成必需检查，要么给向量加 `platform_decidable` 分区
  ⇒ 升入 §四 第 11 项待裁决，登记表在此之前保持 `{"RS"}`）
  （此处原写「`native-navigation-decision` 已有 C# 消费者 `BrowserPolicyBrokerNativeGateTests.cs`，
  可作为接法模板」——**已被 R9-B39 推翻**：该文件唯一的命中是 `:260` 的一句解释性注释，
  没有任何代码读这份向量，登记表已改回 `{"RS"}`；Windows 侧至今仍是零执行者）；
  ③**这一档的后半已被 R9-B46 定稿、并被 R9-B66 现读改真**：`action-catalog.yaml` 的
  `confirmation`/`risk`/`audit`/`read_only` 不是「没人读的缺口」，而是**设计上就不给运行时读**的治理元数据
  （列身份写在 catalog 头注第 8-22 行，由 `contracts/codegen/analyze_action_catalog.py` 等静态判据判，
  并有反向锚 `catalog_governance_columns_test.py::test_broker_never_reads_the_governance_columns`
  ＋它的正面控制 `::test_broker_really_reads_the_judgment_columns`）⇒ 照原处方「把三列接进裁决」
  现在会被这条反向锚**判红**，不是可自由执行的改进。
  ③剩下的真缺口只有一条：**Agent 端不消费任何契约向量**（`CONSUMER_MANIFEST` 现读 `AG` 命中 0）——
  要不要把红队夹具与 `action-valid/invalid.json` 绑成同一份输入，属排期决定（⇒ §四）。
  登记本节时这里写的是「三列也不被 broker 读 ⇒ 两端各说各话」——那是 R9-B46 之前的旧状态，
  改真是因为**同一份文档的指针自己也漂过一次**（见 §3.65）。
  不顺手做的原因：每一档都要在端侧新增/改写裁决实现（不是加测试文件就有数），且第①档与
  AX-02 是同一次改造。门禁已把当前事实钉住：**将来任何一端接上消费者，表不改就判红**，
  所以这笔账不会再变成第二段声明。
  **R9-B39（§3.39）做了第 0 档：先把「消费」这个词本身判干净**——命中口径剔注释后实测
  21 份向量只有 1 份端集变化（`native-navigation-decision` 由虚记的 CS+RS 改回 RS），
  其余 20 份逐份复核确认真在代码里命中；同时把本条上面那句失实的「已有 C# 消费者」改掉。
  **R9-B59（§3.59）把第②档的「要怎么闭」定稿成形状 ②**：两份原生向量每条带
  `platform_decidable`，标签由该条期望值推导（decision 13 条 false＝`require_confirmation`；
  确认面 5 条全 false），门禁判「不许省略、不许塌成一块、标签必须可推导」。
  注意这条**没有**把第②档的覆盖面缺口修掉——平台执行者仍然是零，登记表仍是 `{"RS"}`；
  它定的是「将来接的那一端必须只覆盖 true 的 30 条」，因此 §3.42 否证过的那种假覆盖
  （补一份 C# 用例把 13 条断不真的确认分支也断进去）现在会被常驻判据挡住。
  三档缺口**仍在**，且现在才是可信的缺口数。

### 5.3 CS（Windows 正典）

- ~~Q22 R9-CS-1~~ **已闭（R9-B11 / §3.10：无痕窗接线体外迁 + 失败闭合 + 对偶锚）** | P2 | `windows/src/Aegis.Windows.App/Chrome/InPrivateWindow.xaml.cs:135-164`：
  无痕窗 `CoreWebView2InitializationCompleted` 回调体（`BindVirtualHosts`→`runtime.OnCoreReady`
  （内含 `WireEvents`→`RegisterSession`：会话池 1024 满即抛 / `WebView2Hardening.Apply` /
  `AddWebResourceRequestedFilter` COM）→`WireNtpBridge`→首次 `Navigate`）**未包**
  `TabRuntimeLifetime.RunCoreReadyFailClosed`，而主窗同段已包
  （`Chrome/MainWindow.Tabs.CoreReady.cs:40`、`Chrome/TabRuntimeLifetime.cs:57`，
  R8-CS-SEC-07）。该回调在 `CreateRuntime` 的 try/catch **之外的独立 dispatcher 派发**中
  执行 ⇒ 抛出无观察方，冒到 `App.xaml.cs` 全局弹窗（3/30s 后静默）并留下一个已挂载可见
  但未接线的标签；`RegisterSession` 成功后任一步抛出还会让会话在池中泄漏（拆除只在主窗
  `CloseTab` 里）。`CoreReadyFailClosedTests` 仅锚 MainWindow，无 InPrivate 对偶锚。
  非策略 fail-open（`_wired` 末位置位 + `IsWired` 仍挡后续导航）。  **本条所指缺口已逐行回读确证并落地**（§3.10 / §二 R9-CS-1：无痕窗接线体外迁 + 包失败闭合 + 对偶锚 5 条）。
- ~~Q23 R9-CS-2~~ **本批已闭**（R9-B33 / §3.33：新增 `windows/src/Aegis.Windows.App/Core/Security/HttpFetchGuard.cs:29`（有界读取）与 `:48`（逐跳落点判定）、`Chrome/SourceFetcher.cs:32`（手动逐跳抓取编排），三条带外抓取路径（源码查看器 / 订阅源 / favicon）全部收口，并由 `windows/tests/Aegis.Windows.Core.Tests/OutOfBandFetchDisciplineTests.cs` 按扫描面现取钉住）。
  原条目：Q23 R9-CS-2 | P2 | `windows/src/Aegis.Windows.App/Chrome/MainWindow.SourceViewer.cs:29-38,71-75`：
  查看源码（Ctrl+U）的带外抓取 ①不设 `AllowAutoRedirect=false`、落地也不对**最终** URI
  复查 `ReservedAddressBoundary` ⇒ 敌意页 302 跳 `169.254.169.254` 照跟（同仓
  `Core/Favicons/FaviconService.cs:46` 显式关重定向、`Core/Security/ThreatFeed.cs` 复查
  final-uri，唯此出口两者皆无——保留地址边界「四类出口单源」之外的第五类带外 fetch）；
  ②`ReadAsByteArrayAsync` 先整读进内存再比 `SourceMaxBytes` ⇒ 无 Content-Length 预检的
  大响应可 OOM。响应只回显给用户、页面读不到 ⇒ 非逃逸级，但「把内网/元数据内容递给被
  诱导读源码的用户」不该发生。
  **登记时把 Favicon/ThreatFeed 当反例引用，回读发现它们的「有界读取」同样只在响应声明了
  Content-Length 时成立**（`HttpClient` 默认 `ResponseContentRead` 先把整包缓冲进内存）——
  见 §3.33 第 2 条，实测撞出来的那条红灯就是这件事。
- ~~Q24 R9-CS-4~~ **本批已闭**（R9-B37 / §3.37：下载生命周期外迁成 `windows/src/Aegis.Windows.App/WebView/HostWebView.Downloads.cs`，终态即退订并摘除；终止路径只 Cancel 在途项）。原条目：Q24 R9-CS-4 | P3 | `windows/src/Aegis.Windows.App/WebView/HostWebView.cs:332-336`：
  每个放行下载 `_trackedDownloads.Add(operation)`，完成**不移除**（仅 `UnwireEvents` 里
  `Clear`）⇒ 长会话累积已完成 `CoreWebView2DownloadOperation` COM 引用，`StopLiveTraffic`
  还对已结束项 `Cancel()`（抛→吞）。

  **实测补一条登记时没写的**：本 SDK（WebView2 1.0.2903.40）的 `CoreWebView2DownloadOperation` **没有** `Completed` 事件——反射实测只有 BytesReceivedChanged / EstimatedEndTimeChanged / StateChanged（事件参数类型还是 `EventHandler<object>` 而不是强类型 args）。所以终态信号只能取 `StateChanged` + `State` 判定这条路，照 Win32 文档写 `Completed +=` 连编译都过不去。
- Q51 R9-CS-14 | P2 | `windows/src/Aegis.Windows.App/Core/Settings/SettingsService.cs:24`
  （`ThreatFeedUrl { get; init; } = ""`）↔ `Chrome/MainWindow.xaml.cs:138,326-337`
  ↔ `core/rust-policy-core/src/ffi/broker.rs:331`（`update_host_denylist`）↔ Android 全端
  （grep `Denylist|ThreatFeed|blocklist|isHostBlocked` 在 `android/**` **0 命中**）：
  外部第三轮审计 AEG-003「Android 缺少威胁黑名单防护」**范围要改准**——两端默认都是
  **空名单即放行**（Windows 的订阅源是用户在设置页填 https URL 或
  `AEGIS_THREAT_FEED_URL`，缺省空 ⇒ 出厂形态两端行为一致）。真实缺口是**能力面**：
  Android 整条「取源 → 校验 → 缓存 → 灌进核心 denylist」的链不存在，Rust 侧
  `apply_host_denylist` 在 Android 恒不被调用，所以用户即使想在 Android 上开黑名单也无处可开。
  补齐它是一项功能而非一次修补：要网络抓取、缓存原子替换、版本/签名/防回滚、失败降级
  可解释（审计 §AEG-003 的处方方向正确），且要先定「源从哪来、谁签」。⇒ §四 待裁决；
  验收按审计口径：同一威胁测试集在两端输出同一裁决，并能在真机上确认实际拦截。
- ~~Q52 R9-CS-15~~ **本批已定稿并落地**（§二 裁决行 + §3.29）：外部审计 AEG-008「威胁情报
  仅启动时刷新」属实——`StartThreatFeedRefresh()` 在启动链调用**一次**，同文件的
  `_feedbackTimer`/`_sleepTimer` 都有 DispatcherTimer，唯独订阅源没有周期重取。登记时的
  关键判断保留：它**已在设置 UI 明示**旧文案，所以不是「声明与行为不符」而是「行为偏弱」，
  改它＝出货行为变更（用户配了源就从「开窗取一次」变「持续取」）⇒ 走 §四 第 9 项定稿，
  定稿后落地为 6 小时节拍 + 退避封顶 24 小时 + 最后成功时间上 UI + 保存即刷。
- Q54 R9-CS-16 | P3 | `windows/src/Aegis.Windows.App/Chrome/SettingsWindow.xaml.cs:103-129`
  （`ThreatFeedBox_LostFocus` 的清空分支）↔ `windows/src/Aegis.Windows.App/Core/Security/ThreatFeedCoordinator.cs:117-139`
  （`Start()` 无条件 `LoadCached`）：用户在设置页**清空**订阅源只让周期循环不再取源，
  已生效的 `BlockedHosts` 快照继续拦截到进程结束；重启后 `Start()` 仍无条件读缓存文件
  `threat_feed.txt`（清空动作不删它），于是那份名单**无限期**留在拦截面里。出厂默认无缓存
  时两端仍是「空名单放行」，所以这不是默认行为缺陷，而是「把配置项清空＝关掉该功能」这个
  用户心智没有对应实现。没有顺手改的理由：清空即解除拦截＝**放松防护**的方向（与 §二 里
  AX-02「只加严不加宽」同一条纪律），且要一并决定「删不删缓存文件、下次启动是否仍加载」——
  属产品决策 ⇒ §四 待裁决。现网提示文案已按事实写成「已清空订阅源：此后不再自动重取，
  当前名单仍会继续拦截」（不是「退回空表」），并由 `ThreatFeedRefreshScheduleTests.
  Cleared_feed_means_no_further_network_activity_not_a_cleared_list` 钉住「清空不制造空窗」。
- ~~Q62 R9-CS-19~~ **本批已闭**（R9-B54 / §3.54：三处会并发枚举的记录面收成 `ThreadSafeRecorder<T>`（带锁 + 一次性快照，底层 `List` 不外露），行为层用例用 `CountdownEvent` 把读写重叠**协调出来**并断言它非空心，接线层钉住字段类型与「不得再出现 `.Add(`」；注入实测：删掉三处 `lock` ⇒ 同一条用例红在丢写入（3200 变 2563）。同批复读 `ThreatFeedRefreshScheduleTests` 判定**不是同形**（读都在 `await BackgroundTask` 之后）⇒ 不动。原条目 ↓
  `windows/tests/Aegis.Windows.Core.Tests/ThreatFeedCoordinatorTests.cs:28-29`（`Harness.Applied` /
  `Harness.Logs` 是普通 `List<>`）↔ 同文件 `:65-66`、`:80`、`:93`、`:105`、`:127`、`:140`、`:178`
  （`SpinUntil` 每 10ms 从测试线程枚举这两个表）↔ `:185-193`（`SpinUntil` 本体）：
  `ThreatFeedCoordinator.Start()` 把快照应用与刷新放在**后台线程**，而那两个表就是后台线程的
  回调写的（`applyHosts: applied => Applied.Add(applied)`、`message => Logs.Add(message)`）——
  测试线程同时在枚举它。实测红灯（run 38461642255 的 `windows-contract-build`，
  同一 commit 的 PR 面两次全绿）：`System.InvalidOperationException : Collection was modified`
  at `ThreatFeedCoordinatorTests.cs:line 65`，`Failed: 1, Passed: 900`。
  这不是「运气差的门禁」而是**用例自己的数据竞态**：它判的是后台链有没有把快照灌进来，
  而它读的那份记录不是线程安全的。影响：`windows-contract-build` 会偶发红在一条与改动无关的
  PR 上，而这类红灯的实际处置是「重跑一次」——每次都重跑就是门禁失信（R9-CI 那批反复记的形态）。
  修法方向（下一批）：把两个记录表收成带锁的快照面（写侧 `Add` 入锁、读侧一次性 `Snapshot()`
  出来再枚举），并把「`SpinUntil` 只碰快照」写成判据；同批回读 `ThreatFeedRefreshScheduleTests`
  的 `Delays`/`_logs` 与 `CoreDenylistPublisherTests._pushed` 是否同一形态。
  **不在本批顺手改**：B53 的主题是 Gradle 校验和的生成面，C# 测试面的并发修复放进去会让
  两件事都对不上账。

### 5.4 RS（Rust 核心）

- Q25 R9-RS-1 | P2 | **部分闭环（R9-B38 / §3.38）**：挂载形态与描述符这一半已三端合一（原型级挂载 + 保留原生描述符 + 实例兜底），三端同形判据落在 `core/rust-policy-core/tests/timer_parity.rs`；六条高解析通道两端零包裹的**剩余半边**续登为 Q57 R9-CS-17（不顺手做：rAF/getEntries*/Event.timeStamp 的包裹是站点可观察的行为变更，只能由真机冒烟证明）。原条目：Q25 R9-RS-1 | P2 | `windows/src/Aegis.Windows.App/WebView/FingerprintShield.cs:207` +
  `android/app/src/main/java/com/aegis/browser/WebViewHardeningStagesShield.kt:175` ↔
  `core/rust-policy-core/src/timer_prec.rs:127-140`、`core/rust-policy-core/tests/timer_parity.rs:69-94`：
  计时防护**挂载形态与通道集**三端不同口径——两端把包装装在 `performance` **实例**上且
  descriptor 写死 `writable:false, configurable:false`，核心按 RS-216/RS-250 装在
  `Performance.prototype` 并保留原生 descriptor。后果：出货的 Windows/Android 制品里
  一行 `Performance.prototype.now.call(performance)` 即取**无降噪 µs 精度时钟**，一行
  `hasOwnProperty.call(performance,'now')` 即检出防护存在；且 mark/measure/getEntries*/
  rAF/`Event.timeStamp`/`timeOrigin` 六条高解析通道两端零包裹（核心全裹，
  `getEntriesByType` 在两端主源码零命中）。第十二节 B2 余量段「三端一致地如此」在此出口为假。
- ~~Q26 R9-RS-2~~ **本批已确证并落地**（§二 裁决行 + §3.12）：两条处方里选了第二条
  ——入库件已按钉住的 1.99.0 + uniffi 0.32.2 重 derive（1,910→2,005 行，diff 只有
  `update_host_denylist` 的 FFI plumbing 与语义收窄后的 docstring），`test -s` 那条空断言
  之外新增 `scripts/verify_uniffi_binding_surface.py` 双向对账，`contracts.yml`（PR 面
  src↔入库件）与 `core-rust.yml`（同一次构建的权威 python 产物↔入库件）两处接线。
  「删这份无人消费的入库件」这条**没走**：删除是产品/架构裁决（该件自 2026-08-22 原生
  UniFFI 集成即在库），留作定稿项（见第四节）。
- ~~Q27 R9-RS-3~~ **本批已确证并落地**（§二 + §3.16）：`cargo tree --offline -i` 实测补一条
  ——锁里既无 getrandom 0.2 也无 rand_core 0.6；实况是直接依赖解析 0.4.3（本 crate + tempfile），
  0.3.4 由 rand_core 0.9.5 带入（ed25519-dalek 3.0 / curve25519-dalek 5.0 一侧）。注记已改成
  带实测来源的事实，依赖零改动、`cargo metadata --locked` ✅。
- ~~Q28 R9-RS-4~~ **本批已闭（范围按实测扩到 8 个模块）**（R9-B36 / §3.36：README 的「核心裁决面」陈述改真 + 新常驻门禁 `scripts/verify_core_unwired_modules.py`）。原条目：Q28 R9-RS-4 | P3 | `core/rust-policy-core/src/https_only.rs:89-125`、
  `src/update_manifest.rs:170-309`、`BridgeGuard::inject_script`：三个策略面在 13 个冻结
  导出符号里**零入口**、两端零消费，而 `README.md:15,71` 仍把「Ed25519 阈值验证」列为
  核心裁决面；`HttpsOnlyState::upgrade` 判的是运营者手工白名单，**不含** B8 的回环/
  RFC1918/CGNAT/`.local` 段豁免 ⇒ 一旦按「迁移到核心」接线，`http://192.168.1.1` 立刻被
  升 https（R8-AD-01 原形态复现）。②建议模块头标「非 B8 判据载体」；①③补导出即改 ABI ⇒ 待定稿。
  **实测更正两点**：①「三个策略面」不止三个——`pub mod` 而除自身文件/自身测试外零引用、
  且不在任何导出面上的顶层模块共 **8 个**：`adblock`、`bridge_guard`、`executor`、
  `https_only`、`js_inject`、`oracle`、`session_state`、`update_manifest`；②「两端零消费」
  不能用「宿主源码里出现同名标识符」来判——Windows 侧确有 `HttpsOnly` 隐私设置（端侧另一份
  实现），按名字扫会把「未接线」误判成「已消费」。sound 的判据只剩两条：接入层
  （`c_abi/**`、`ffi/**`）剔注释后不得出现模块名，且模块自身不得有导出属性。
  ①③（补导出＝改 ABI）仍挂 §四 待定稿；「未接线即删除」也不是本批的建议。
- ~~Q29 R9-RS-5~~ **本批已闭**（R9-B34 / §3.34：新增 `core/rust-policy-core/src/c_abi/tests/denylist_modes.rs`——5 条 ABI 层用例，四档位端到端 + `mode/staged/served` 字段面 + `denylist_mode_invalid` 拒绝码）。原条目：Q29 R9-RS-5 | P3 | `core/rust-policy-core/src/c_abi/tests/buffer_boundaries.rs:157-203` ↔
  `windows/src/Aegis.Windows.App/Broker/NativePolicyCoreBridge.DenylistPush.cs:102-131`：
  ⑨ 的四档位协议在 Rust 侧只端到端跑了 0/1，应答字段 `mode/staged/served` 在 Rust 全测试树
  **零断言**（只产出，`src/c_abi/navigation.rs:288-297`），`denylist_mode_invalid` 亦无 ABI
  层用例；而 C# 的提交判定正依赖这三字段（`commit.Staged/Accepted` →
  `denylist_commit_refused`），且那 8 例跑在假核心上、真 DLL 用例不在必需检查（R8-CI-18）
  ⇒ 核心改名/丢字段在 PR 面永不红。
  落地时另外把三个探针 helper（`denylist_payload`/`push_denylist`/`evaluate_code`）从 `buffer_boundaries.rs` 上收到 `common.rs`——档位面与规模面判的是同一个 ABI 入口，两份 helper 就是两份真相。
- ~~Q30 R9-RS-6~~ **本批已确证并落地**（§二 裁决行 + §3.13）：修法没走「签名体现不变量」，
  而是让 `is_high_risk_host` 自己取 `:` 前段（函数自证 > 调用方纪律），绕过形态直接消失；
  `169.254.169.254:8080` 判高危、`192.168.1.1:8080` 仍判非高危（B8 裁决保住——先试的
  「段内含 `:` 即判高危」正是被这条既有期望打回的，实测过程记在 §二）。同形绕过在 C#/Kotlin
  孪生里不存在（不收带端口入参），故本批零跨端判定改动。
- ~~Q31 R9-RS-7~~ **本批已确证并落地**（§二 裁决行 + §3.13）：三端片段表 5 段 → 8 段，
  补 `pixels.length === width * height * 4` 与两条 `aegisNoiseRectangle` 调用前缀。
  两次内存态注入（Android 守卫退化、C# 调用改名）旧口径零红、新口径各自判红并已还原。

### 5.2.1 本批落地时新增队列（同口径：必须带 file:line）

- ~~Q47 R9-SH-12~~ **已闭（R9-B11 / §3.10：Enter/Space 正向锚 + 删分支故障注入）** | P3 | `shared/shell/start.main.js:83` ↔ `tests/ui-regression/start_main.test.mjs:307-313`：`Enter`/`空格` 选中引擎这条**正向**判据全仓零覆盖（:83 的 `if (ev.key === 'Enter' || ev.key === ' ')` 无任何用例驱动），而 :87 的方向键分支刚被 R9-SH-3 补上反向判据——只锁一侧意味着「把 Enter 整条删掉」仍全绿。补法：在同一用例里对 `items[1]` 触发 Enter 并断 `state.engineCalls` 增长（`start_main.test.mjs` 在 579 行零余量基线上，需先净减）。
  **本批已落地**（§二 R9-SH-12 / §3.10：正向锚 + 故障注入自证）。
- ~~Q59 R9-SH-17~~ **本批已闭**（R9-B45 / §3.45，2026-10-13）| P2 | 登记时写「散了 14 份」，
  现读纠正为 **15 个文件各自实现**（C# 9 / Kotlin 3 / Python 3，命令见 §3.45 第 2 点）；原条目：「按文本判源码前剔注释」这条纪律在仓里**散了 14 份、三种覆盖等级**
  （R9-B44 清点，出处见 §3.44 第 4 点）：具名 9 份——
  `scripts/verify_vector_consumers.py:126`、`scripts/verify_core_unwired_modules.py:66`、
  `contracts/codegen/injected_js_text.py:98`、`HostWebViewWiringOrderTests.cs:47`、
  `CoreReadyFailClosedTests.cs:199`、`SubresourceDenialDeliveryTests.cs:164`、
  `SubresourceFailClosedTests.cs:209`、`OutOfBandFetchDisciplineTests.cs:37`、
  `DocumentStartInjectionRegressionTest.kt:49`；内联无具名 ≥5 份——
  `WebViewPipelineTests.cs:268`、`NativePolicyCoreBridgeLeaseTests.cs:80`、
  `NativePolicyCoreBuildRequirementTests.cs:72,140`、`InPrivateCoreReadyWiringTests.cs:46`；
  加 R9-B44 新写的 `withoutComments`（`:broker`/`:app`）。
  覆盖等级三样：只切行首 `//`（C# 多数与内联那些）、切 `//`+`/*`+` *`（`codeOnly`/
  `withoutComments`）、切到行尾（`verify_core_unwired_modules.py`——**会把字符串里的
  `https://` 一起吃掉**）。块注释与 ` * ` 续行在 C# 那几份里 today 无护栏；本仓注记传统恰好
  把被禁历史写法原文抄在注记里，所以两条反向锚
  （`WebViewPipelineTests.cs:271`、`SubresourceDenialDeliveryTests.cs:150`）
  **只因作者顺手写了内联过滤才不判红**（对照：`HostWebView.cs:104`、
  `BookmarkManagerWindow.xaml.cs` 的注记原文就写着被禁形态）。
  验收判据（不要写成「全部换成共用件」）：**每种语言只剩 1 个 helper、内联过滤 0 处、
  「切到行尾」那一支的过剔要么修掉要么写明**；清点本身要可复跑（按上面 14 个出处 grep）。
  不能机械替换的原因：正则不认识字符串边界，判「内嵌 JS 文本」的锚
  （`WebViewHardeningScriptTest`、`injected_js_text.py` 输入面）照套会把 JS 自己的 `//` 删掉，
  判据反而变形；C# 侧跨 `Core.Tests`/`Broker.Tests` 两程序集共享还要动工程引用（构建面）。
  共用件与自证语料已由 R9-B44 备好（§3.44 第 3 点）
  **落地实况（R9-B45）**：三份实现收成「Python `scripts/text_anchors.py` + C#
  `SourceTextAnchors.cs`（两个测试工程链接同一份文件）+ Kotlin `withoutComments()`（两份跨模块副本，
  逐字同形由新门禁判）」；`scripts/verify_text_anchor_helpers.py` 把「实现点集合＝登记集合」变成可失败
  检查（多一处就地过滤判红、登记出处消失也判红）；验收判据三条全部达成：每语言一个 helper、
  内联过滤 0 处、过剔那两支要么修掉（`//` 切到行尾、`#` 无差别剔）要么写明（JS 文本面不并进来）。。

- ~~Q63 R9-CI-18~~ **本批已闭**（R9-B64 / §3.64：三条验收判据各自先量再做——①`_code` **并进单源**
  而非登记成第 6 处：现读 78 份 `.rs` 与 2005 行入库绑定，两种口径的导出面**零差异**，而合成语料
  实测旧口径会在「跨行块注释、续行不带星号」里凭空造出一个只存在于注释里的自由函数（假红方向），
  所以量到的不是「等价」而是「单源更严」；②`MARKERS` 加了紧判据（同一次 `compile(` 调用里同一行
  同时出行注释与块注释形态），判据宽度是把 HEAD 那份塞回 280 份内存态面**三条候选对照着量**出来的
  ——否掉的是「含双斜杠**或**非捕获组起点」（14 处／11 份里 13 处与注释无关），而「含任一形态」
  今天与本判据**同样准**（各 1 处），取窄是严格性取舍 ⇒ 两条都记 §六；判不到的三种写法写在
  `scripts/verify_text_anchor_helpers.py:63-70`；③`_brace_body` 下沉成 `rust_code_reader.brace_body`，
  两份失败语义各自写明（`None`＝判定面塌缩 vs 折成空串＝这一段没有语句，兜它的是本门禁零导出那条
  exit 2）。本批另关掉一条 Q63 里没有的绕过路：绑定那半边过去不剔注释，「把一行符号注释掉」等于
  把它留在面上。原条目 ↓
  Q63 R9-CI-18 | P2 | `scripts/verify_uniffi_binding_surface.py:43`（`_COMMENT`）＋ `:50-53`
  （`_code`）↔ `scripts/verify_text_anchor_helpers.py:41-49`（`MARKERS`）＋ `:52-58`（`ALLOWED`）：
  **R9-B45 那条「实现点集合＝登记集合」的判据漏认一种写法**，于是仓里其实有第 6 份自己写的
  注释过滤而门禁数不到它。现读理由：`MARKERS` 认的是 `def strip_comments(`、`CodeOnly(`、
  `startsWith("//"`、`starts_with("//")` 这类**字面量形态**，而 `_code` 把注释形态写进
  `re.compile(r"^\s*(?://|/\*|\*)")` 这个常量里，一条都不匹配 ⇒ 扫描面（`scripts/` 在
  `GATE_ROOTS` 内）走过了这个文件却不算实现点。它不只是登记问题，覆盖等级也确实不同：
  `_code` 只按行首整行剔，跨行块注释不处理，而**以 `/*` 开头的整行**（哪怕同行 `*/` 之后
  还有真代码）会被连代码一起丢掉——这正是 §3.45 记过的「太窄」与「误吃真代码」两种错法同现。
  同批量到一处同形但不等价：`_brace_body`（`:56-69`）与 R9-B63 抽出的
  `scripts/rust_code_reader.py:56-73` 的 `fn_body` 是同一遍大括号配平，只差失败值
  （`""` 由调用方计成漂移、`None` 按判定面塌缩）。
  **不在本批动**的理由：把 `_code` 并进 `text_anchors.strip_comments` 会改变那份门禁的
  判定结果（导出面比对从「行首整行」换成「配平块注释」），要先证明它对入库绑定面是等价或更严；
  而扩 `MARKERS` 认正则常量这条，风险是把门禁自己 docstring 里引用的被禁形态数成命中
  （它现在靠**拼接构造**避开，`:41-42`），得连带设计自豁免口径。
  验收判据（下一轮按此判，不要写成「都换成共用件」）：①`_code` 要么并进单源、要么显式登记进
  `ALLOWED` 并写明它为什么是第 6 种；②`MARKERS` 对「注释形态写进正则常量」这一类要么能认出
  要么在门禁 docstring 里写明判不到；③`_brace_body` 与 `fn_body` 的失败语义各自写明。

### 5.5 DOC（文档 vs 实树）

- ~~Q32 R9-DOC-01~~ **R9-B21 已落地**（§3.20）｜原记录 ↓
  Q32 R9-DOC-01 | P2 | `README.md:35-37` 仍写「**仍待裁决**：Android 侧 http 一律升 https
  且 `cleartextTrafficPermitted=false`，内网 IP 字面量实际仍不可达（§七 2）；子资源策略链
  异常时的失败闭合方向（§七 5）」——两项均已定稿并落地：`LocalTargetHosts.kt` 存在、
  `android/app/src/main/res/xml/network_security_config.xml:34-41` 有有界
  `cleartextTrafficPermitted="true"` 且显式列 `192.168.1.1`、Windows 侧
  `WebView/HostWebView.WebResourceGuards.cs:37,102` 有 `SubresourceDenialFailClosed`。
- ~~Q33 R9-DOC-02~~ **R9-B21 已落地**（§3.20）｜原记录 ↓
  Q33 R9-DOC-02 | P2 | `docs/adr/ADR-007-canonical-stack-and-single-source-guards.md:50`
  写「**C#**：无注入 JS（走 WebView2 Settings 收紧），不在本门禁范围」，实测
  `windows/src/Aegis.Windows.App/WebView/WebView2Hardening.cs:77` 调
  `AddScriptToExecuteOnDocumentCreatedAsync(FingerprintShield.BuildScript(…))`；
  `README.md:43`、`SECURITY.md:34` 均已改称「C# 的文档创建前注入面」。缺的是**该面未纳入
  bridge_guard 对账**，不是「无注入面」。
- ~~Q34 R9-DOC-03~~ **R9-B21 已落地（只改陈述；四处 `paths:` 收口另登 Q48）**（§3.20）｜原记录 ↓
  Q34 R9-DOC-03 | P2 | 同文件 `:57-58` 写「门禁型 workflow（android-quality/contracts/
  core-rust/agent-redteam/supply-chain/ci）移除全部 `paths:` 过滤」，py-yaml 实测
  `push.paths`：`ci`=8、`core-rust`=3、`agent-redteam`=5、`supply-chain`=11，只有
  `android-quality`/`contracts` 真无过滤 ⇒ 未列路径的改动静默不触发即被判「门禁已过」
  （R8-SH-10 只处理了 `ci.yml` 一处）。
- ~~Q35 R9-DOC-04~~ **R9-B21 已落地**（§3.20）｜原记录 ↓
  Q35 R9-DOC-04 | P2 | `docs/architecture-overview.md:91-100` 声明「16 workflow 分层」但
  分解为 6+1+2+2+4=**15**，依赖面只列 `gradle-dependency-graph`/`gradle-dependency-insight`、
  漏 `dependency-relock.yml`（`:151` 又说 16）⇒ `check_doc_claims.py` 只比裸数字
  （正则 `N workflow`），本条全绿而清单少一整面。
- ~~Q36 R9-DOC-05~~ **R9-B21 已落地**（§3.20）｜原记录 ↓
  Q36 R9-DOC-05 | P2 | `docs/product/feature-parity-checklist.md:22` M1 行「ESM（探测启用）…
  ☑（SDK 未暴露 API——反射探测，**升级自动生效**）」已被
  `windows/src/Aegis.Windows.App/WebView/WebView2Hardening.cs:34-42` 就地反证（R8-DEPS-1：
  两版 stable DLL 对 `EnhancedSecurityModeState` 均 0 命中，ESM 只在 `-prerelease`）。
- ~~Q37 R9-DOC-06~~ **R9-B21 已落地**（§3.20）｜原记录 ↓
  Q37 R9-DOC-06 | P2 | `docs/runbooks/device-validation.md:33` Android 第 4 步预期写
  「经 **broker** 判定（MIME/最终 URL/size/目录）」，实测链是
  `WebViewDownloadHandler.kt:113-114` 的 `WebViewDownloadTargetGuard`（scheme/保留地址）
  + `DownloadPolicy` 扩展名判定（grep mime|size 零命中、不经 `AndroidBroker`）⇒ 按现文
  执行会把「无 size/目录门禁」记成通过；而**已落地**的 #130 下载层保留地址硬拒反而没有任何
  真机步骤。
- ~~Q38 R9-DOC-07~~ **R9-B21 已落地**（§3.20）｜原记录 ↓
  Q38 R9-DOC-07 | P2 | 同文件 `:20` Windows 第 7 步未写启用前置：
  `WebView/NavigationConfirmationGate.cs:14-22` 只认 `AEGIS_REQUIRE_NAVIGATION_CONFIRMATION=1`
  或注册表，而 `docs/release/AegisSetup-CSharp.iss:73` 注明该标记**刻意不写**（只写
  `RequireNativePolicyCore`，:79）⇒ 唯一发布制品上面板永不出现，验证人会「看不到面板」
  而误判缺陷，或凭 UI 存在与否签一个无证据的通过（§十一 第 5 类「结论无证据」）。
- ~~Q39-Q46 R9-DOC-08..15~~ **已闭（R9-B21 / §3.20 与 R9-B41 / §3.41）** | P3 | 八条（**R9-B21 已落地 DOC-08/09**：「10 项」改 11 项并点名漏掉的第 11 步；README/SECURITY 的 `:70` → 实调行 `:77`。**余六条 DOC-10..15 已由 R9-B41 落地，见 §3.41**）：`docs/runbooks/windows-run-guide.md:63-66` 写「真机验证
  **10 项**」并枚举 10 个名称，漏第 11 步（R8-CS-SEC-03 的唯一实测出口）；`README.md:43` 与
  `SECURITY.md:34` 引 `WebView2Hardening.cs:70` 而该行是空行（实调在 :77）；
  `README.md:146-147`「五门禁常绿」vs `contract-source-of-truth` 约 17 个步骤，且
  `CLAUDE.md:51-54` 是第三个子集；`docs/product/privacy-defaults.md:13` 引
  `credential_guard`（只存在于 `legacy/windows-pywebview/app/`，正典全树
  CredentialGuard/ProtectedData/DPAPI/KeyStore 零命中，:12 已诚实写「未落地」而 :13 未同步）；
  `android/README.md:7-13` 把「Room 历史/书签、Android Keystore、同步协议」列为**发布前强制
  控制**而实树零命中且 `supported-features.md:30-31,47` 明写「零 bookmark 引用 / 明确不做」；
  `CONTRIBUTING.md:52`「master 受保护、禁止直接推送」与本仓历史直推（`d898677`、`3243397`）
  及第八轮 §5.2 实测 `enforce_admins=false` 相反（**只改文档，不动服务端设置**）；
  `docs/product/feature-parity-checklist.md:73`「本清单 100%」与同文件 `:24` 唯一未勾验项
  自相矛盾（§十三 只改了 CLAUDE/README/supported-features 三处）；`README.md:145,151-153`
  测试计数「cargo 450+ / dotnet 650+ / pytest 230+」与实测
  （`grep '#\[test\]'`=589、Core.Tests `[Fact]+[InlineData]`=718、
  `grep -c 'def test_'` 461+53、UI 回归 138）双向失真。
  **DOC-10..15 这六条由 R9-B41 落地**（§3.41）：统一动作是「改指向单源而不是再抄一遍新值」，
  其中 DOC-13 是**重新现读服务端**（ruleset 的 bypass 角色、必需检查集合、
  `required_pull_request_reviews` 缺席）而不是引用第八轮那次数测——设置会变，引用旧实测
  就是第二条失实声明；本批只改文档表述，**没有动任何仓库设置**。

- ~~Q48 R9-CI-13~~ **本批已闭**（R9-B46 / §3.46）| P3 | 四处 `push.paths` 已删除，分类与「谁许过滤」从 ADR 的陈述变成 `contracts/ci/workflow-categories.yaml` + `scripts/verify_ci_trigger_surface.py` 的双向对账（门禁型带过滤、门禁型无 PR 触发、新增 workflow 未归类、探测型混进 PR 面——四种都判红）。以下为登记原文：
  Q48 R9-CI-13 | P3 | `.github/workflows/ci.yml`（`on.push.paths` 8 项）、`core-rust.yml`（3 项）、
  `agent-redteam.yml`（5 项）、`supply-chain.yml`（11 项）：ADR-007 声称「门禁型 workflow 已全部移除
  `paths:` 过滤」而实测这四处仍在过滤 ⇒ 未列路径的改动在这些面上静默不触发、检查名看起来「已过」
  （R8-SH-10 当年只处理了 `ci.yml`）。收口属 CI 触发面变更：runner 时长上升，且若某处 job 已列进必需
  检查，触发条件与 required 集合必须同批核对（R8-CI-01 的「Expected — Waiting for status」教训）⇒ 需用户
  点头后另批做。**R9-B21 只把 ADR 的陈述改真。**
- ~~Q49 R9-DOC-20~~ **本批已闭**（R9-B33 / §3.33：`docs/runbooks/device-validation.md:19` 按代码改真，
  读的是 `WebView/HostWebView.cs:268`、`Core/Downloads/DownloadPolicy.cs:46`、
  `Broker/BrowserPolicyBroker.cs:111`、`Core/Downloads/DownloadItem.cs:114` 四处实际链）。
  原条目：Q49 R9-DOC-20 | P3 | `docs/runbooks/device-validation.md:19`（Windows 第 6 步「下载 MIME 混淆」预期写
  「下载经 broker 判定（MIME/最终 URL/size）」）：本批只确证了 Android 那一行（Q37→R9-DOC-06），
  **C# 侧未验**——Windows 下载链是否真判 MIME/最终 URL/size 没有实测支撑，故该行仍是一条未核验陈述
  （下一批读 `windows/.../Downloads/` 后改真或续登）。
  结论：**「判 MIME / 判 size」两句都不成立**（`TotalBytesToReceive` 只喂进度条），真实判定面是
  危险扩展名三候选 + kill-switch + 保留地址 + 会话/标签上下文 + 无确认订阅者 fail-closed。

- ~~Q56 R9-CI-14~~ **本批已闭**（R9-B47 / §3.47）| P2 | 落地的是**内容对账**而不是登记建议的墙钟比对（理由写在 §3.47 第 2 点：墙钟判据要另一条常跑流水线读运行历史，而它自己也需要被判定）。新作业 `verify-graph-freshness` + `scripts/verify_gradle_graph_freshness.py`（11 条用例）。以下为登记原文：
  Q56 R9-CI-14 | P2 | `.github/workflows/gradle-dependency-graph.yml:14-25`（触发面只有
  `push.branches: master` + `paths:`、周 schedule 与 workflow_dispatch）↔ `:49`
  （`uses: gradle/actions/dependency-submission`）：这条 workflow 的**内容**在 PR 面上
  一张牌都不跑—— Dependabot 给它开的跨 major bump（#165：4.4.4→6.4.0）在 15 张绿牌里
  没有任何一张执行过那个动作，于是「合并 = 未经运行的跨 major」。而这个动作的产物是
  Android 依赖图，直接决定 Dependabot alerts 对 Gradle 侧是否持续更新：**它静默坏掉时
  全仓不会变红**（Android 漏扫面就此失效而无人知晓）。本批不擅自改触发面（给 PR 加
  paths 会拖慢每条 android/** PR，且必需检查集合要同批核对——R8-CI-01 的
  「Expected — Waiting for status」教训），采取的是「先运行一次证明它，再合」：
  #165 合并后由 push 触发真跑，看结论与依赖图是否更新；失败即回滚。
  仍待决的结构性修法（要用户点头）：给该 workflow 加一条「图形 stale 检测」——
  比如每周比对 `last dependency submission` 的时间戳，超过 N 天未提交即判红，
  否则这类「只在 master/schedule 跑的提交面」永远没有可失败的判据。

- Q57 R9-CS-17 | P2 | **R9-B38 续登（Q25 的剩余半边）**：
  ①`core/rust-policy-core/src/timer_prec.rs:170-244`（RS-279 一组：`mark`/`measure`/
  `getEntries*`/`timeOrigin`/`Event.timeStamp` 的原型级 getter 与 entry 圆整）↔
  `windows/src/Aegis.Windows.App/WebView/FingerprintShield.cs` Stage 8 与
  `android/app/src/main/java/com/aegis/browser/WebViewHardeningStagesShield.kt` Stage 8：
  **六条高解析通道两端零包裹**（`getEntriesByType` 在两端主源码零命中）。挂载形态那半边
  已在 R9-B38 三端合一，这一半没做的原因是：rAF 与 `getEntries*` 的圆整是**站点可观察**的
  行为变更（动画回调节奏、性能面板读数），只能由真机/桌面冒烟证明——那是需要用户给话的
  验证面（见 §四），不在本批顺手改。
  ②**已判不成立**（R9-B55 / §3.55 与 §六）：三端没有任何一处覆写 `Object.defineProperty`
  （core 30 处取用、Android 10 处、Windows 2 处取用 + 10 处用捕获形态），而注入都在
  document-start（`WebView2Hardening.cs:106` / `WebViewHardening.kt:55`）⇒ 页面还没机会
  篡改，「防页面前篡改」保护的是一个不存在的窗口；Windows 那次捕获的真实原因是同一段里
  它覆写了 `getOwnPropertyDescriptor`/`getOwnPropertyNames`（Windows 独有的原型链反检测层）。
  前提已做成能红的判据（`tests/python/injected_js_parity_test.py` +3 条），不是留一段推理。
  所以 Q57 剩下的只有①那一半，仍**需设备/桌面冒烟**。

### 3.20 R9-B21（2026-10-10，队列批次 D 第一子批）：九条文档陈述改真 + 两条新队列

**共同主题：文档说「已做」而实树没做，比文档空白更危险。** 本批九条全是 P2/P3 的
「陈述 vs 实树」失配，逐条回读到具体行后才动文字；两处**故意没做**（见末尾）。

1. 落地（改文字）：`README.md`（「仍待裁决」两项 → 事实 + 真未决项；`WebView2Hardening.cs:70`→`:77`）、
   `SECURITY.md`（同行号）、`docs/adr/ADR-007`（C# 注入面、`paths:` 过滤实况）、
   `docs/architecture-overview.md`（16 的分解补 `dependency-relock`，并写明
   `check_doc_claims.py` 只比裸数字 ⇒ 这类「分解少一面」门禁看不见）、
   `docs/product/feature-parity-checklist.md`（ESM「升级自动生效」→ 恒为拿不到 + SDK bump 待裁决）、
   `docs/runbooks/device-validation.md`（Android 第 4 步按实测链改写；Windows 第 7 步补确认门启用前置）、
   `docs/runbooks/windows-run-guide.md`（10 项 → 11 项，点名第 11 步＝R8-CS-SEC-03 唯一实测出口，
   并互相指认第 7 步的前置）。
2. 新登记两条（同口径带 file:line）：**Q48 R9-CI-13** = 四个 workflow 的 `paths:` 收口
   （ADR 声称已移除，实测 ci=8/core-rust=3/agent-redteam=5/supply-chain=11）——扩 CI 触发面
   是 runner 时长与必需检查集合的决策，不顺手做；**Q49 R9-DOC-20** = device-validation 的
   Windows 第 6 步「下载经 broker 判 MIME/size」**未经验证**，本批只改了确证过的 Android 那一行。
3. 刻意没做的两件事都记在案：把四处 `paths:` 删掉「兑现 ADR」（Q48）、把未核验的 Windows 下载
   行按 Android 的样子改写成另一条断言（Q49）。
4. 本地验证：`check_markdown_tables` / `check_markdown_links` / `check_doc_claims` ✅（纯文档批，
   代码与门禁零改动；`git status` 只含 7 个 .md + 台账 + CSV）。

### 3.21 R9-B22（2026-10-11，外部第三轮审计驱动的 Windows P1 两则）：拒绝投递升级 + NTP 桥紧急停止门禁

用户给出外部审计报告（`新建 文本文档 (7).txt`，基准即当时 master `eccc4c0`）并要
「按审计意见完成修改」。先逐条回读代码再动手，其中两条 Windows P1 可直改，先落地。

1. **AX-01 投递面**（`windows/src/Aegis.Windows.App/WebView/HostWebView.WebResourceGuards.cs`
   227 行）：`OnWebResourceRequested` 改为 `DeliverDenial(denial, TryCreateDenialResponse,
   TryStopWebView, TryWriteSecurityLog)`。判据核在纯函数里，四条行为用例 + 三条结构锚
   （新文件 `SubresourceDenialDeliveryTests.cs`，206 行）。第八轮 ⑤ 的 `subresource_policy_error`
   判据面留在 `SubresourceFailClosedTests`，两文件互不重叠。
2. **AX-04 紧急停止覆盖面**（`Chrome/Ntp/NtpBridge.cs` 273 行 + `NtpBridgeFactory.cs`）：
   `Services` 记录尾增 `Func<bool> IsLockdownEngaged`（工厂接 `Broker.KillSwitch.Shared.IsEngaged`，
   两个装配点 `CreatePrivate`/`BuildServices` 都接），`Dispatch` 头部按 `SideEffectingOps` 拒绝。
   新文件 `NtpBridgeLockdownTests.cs`（165 行）14 个用例面：6 项副作用操作拒 + 6 项未触发时
   照样可达 + 6 项只读面冻结期可用 + 偏好面放行 + 执行时重验 + Task.Run 异步支路把拒绝**回给页面**
   （否则前端只会把导入态复位成「成功但 0 条」）。
3. 本机验证：`dotnet test` Core **832/832**（下界 700）、Broker **189/189**（下界 160），
   `assert_test_counts.py` 两侧 ✅；`check_file_sizes.py` ✅（四个改动/新增文件均在 300 行内、
   基线无变动）；`packages.lock.json` 零漂移。
4. **三处故障注入实测**（新锁必须能判红，注入前已先提交，还原用 `git checkout --` 回到含修复的
   提交而非 master）：① 把 `DeliverDenial` 改回「escalate 与 tryDeliver 同一个 try」的直觉写法 ⇒
   `DeliveryThrowing_StopsTheNavigationToo` 判红（正是审计点名的形态：交付抛出后连升级都跳过）；
   ② 把 handler 改回旧形态 `try { e.Response = CreateWebResourceResponse(...) } catch { 只写日志 }` ⇒
   结构锚 `HandlerRoutesUndeliverableDenialsToAStopNotJustALog` 与既有
   `SubresourceFailClosedTests.MoveDidNotNarrowTheExistingDenialSurface` 一起判红（后者因
   `CreateWebResourceResponse(` 计数从 1 变 2）⇒ 两条锁互相补位；③ 把 `NtpBridge` 的开关读取
   改成构造时快照 ⇒ `SameBridge_ReChecksAtExecutionTime_NotAtConstruction` 判红（21 绿 1 红，
   说明这条锚只判它声称判的那一件事）。还原后 31/31 绿。
5. 刻意**没有**照抄的审计处方，全部回述进第四节而不是静默丢弃：AX-02（把
   `policy.evaluate`/`capability.validate` 接进 FFI 通路——源码注释 `ffi/broker.rs:146-150`
   记的就是这条缺口，但接通它会把「Rust 判 Allow」在端侧放大成什么，是核心裁决语义变更）、
   AX-05/AX-06（原生核心强制启用脱离 HKCU/环境变量与 Android 构建参数——发布门禁与产品策略）、
   AEG-009/AEG-010（与用户 2026-10-07「本机与内网必须能打开」定稿及既往否决冲突）、
   AEG-011（等价待办项 10，本机无 Gradle 无法生成 lock）、AEG-014（FFI fuzzing 属阶段 C）。
   去重两条：AX-07 ≡ §五 Q6（R9-AD-6）、AX-03 ≡ §五 Q10（R9-AD-10），均在原条目下续外部出处。

### 3.22 R9-B23（2026-10-11，外部审计 AX-03 可直改半边）：壳页 CSP 显式 `frame-src 'none'`

1. 语料事实先回读（不改判定）：`shared/shell/` 四段脚本 + HTML 全仓**零** `<iframe>`
   与 `createElement('iframe')`；`start.main.js` 的 GeoGebra 入口走宿主桥 `openGeo`
   （顶层导航），不是嵌帧。⇒ 这一刀今日成本为零。
2. 改动：`shared/shell/start.html` 的 meta CSP 追加 `frame-src 'none'`，与既有的
   `object-src/media-src/connect-src 'none'` 同族。**为什么这是安全判据而非排版**：
   Android 桥的归属判据是 `AegisHomeBridge.isTrustedShellPage()` 读 `webView.url`
   （顶层文档），`@JavascriptInterface` 拿不到调用者所在 frame 的 Origin；今天
   「顶层 URL ＝ 唯一可能的调用者」成立只是因为壳页没有帧。显式关帧把它从
   「default-src 调宽时顺带放大」变成「必须改这行的显式评审点」。
   与 WB-105 的关系写进注释：被移除的是 `frame-ancestors`（meta 中被忽略＝声明失真），
   本批加的是 `frame-src`（取回类指令，meta 下确实生效）——两条并存才不被下一个人当矛盾。
3. 新常驻 `tests/ui-regression/shell_frame_guard.test.mjs`（5 例，126/126 全套绿）：
   正向控制是「解析到的 CSP 里必须同时看得见周围七条既有指令」（防空串恒真）；
   两条反向锚**实测注入**——删 `frame-src 'none'` ⇒ 2 例判红，往 HTML 塞一个
   `<iframe>` ⇒ 成本哨兵判红；另加一条装配锚判 `android/app/build.gradle.kts:218`
   的 `assets.srcDir(rootProject.file("../shared/shell"))` 仍在（「共享壳层」≠「两端都吃到」）。
4. **审计点名的第二半「reject null/empty url」本已成立**，不需要修：
   `AegisHomeBridge.kt:95-99` 的 `isTrustedShellUrl` 对 `null`/`""` 返回 false，且
   `runCatching { wv.url }` 异常也按拒绝处理；`AegisHomeBridgePrefsTest.kt:149-159` 已把
   `null`/`""`/`file://attacker/android_asset/start.html`/`file:///sdcard/evil.html` 各钉一次。
   登记而非重做，避免同一判据出现第二个来源。
5. 残余两面另登新队列 **Q50**（`AegisHomeBridge.kt:55,95-99,109-121` 的整个
   `file:///android_asset/` 前缀受信 ＝ 内置 GeoGebra 页也带着 `AegisBridge`；
   以及 `@JavascriptInterface` 拿不到帧 Origin ⇒ 迁 WebMessage 传输），并在 §四
   「外部第三轮审计里不能照做的条目」第 7 项挂成待裁决——两者都不是补一行判据。
6. **本批自己踩的一次「本地绿、CI 红」记进方法面**（PR #157 首跑）：给台账 CSV 追加行后，
   本地用 `csv.reader(open(path))` 判「列数全等于 7」是通过的，而常驻门禁
   `gate_hollowness_test.py::test_ledger_csv_files_are_straight_rectangles` 判的是
   `read_text().splitlines()` 再喂 reader——同一份文件两种读法对「未加引号的裸逗号」结果不同，
   门禁把 AX-03 的 location 列（`…AegisHomeBridge.kt:95-99,109-121`，含逗号却未被引号包住）
   读成 8 列。根因不是门禁过严：它正是为「按列解析会读到错位数据」而设；我的临场校验比门禁松。
   ⇒ 从今天起改 CSV 只走两条路：要么让 csv.writer 自己决定加引号（不在写出后做文本替换），
   要么本地直接跑那条门禁（`pytest -k ledger`，秒级）。本行的 location 已重写成
   「:95-99 与 109-121」并把引号交回 writer。

- **AEG-013「WebView2 消息桥与 Origin 验证」在当前代码上不成立**（外部第三轮审计标
  「待验证」，本批按它给的四个 API 名逐个回读）：全仓 `AddHostObjectToScript` **零命中**
  ⇒ 不存在 COM 宿主对象注入面；`WebMessageReceived` 只有两处订阅
  （`Chrome/MainWindow.Tabs.CoreReady.cs:80-84`、`Chrome/InPrivateWindow.xaml.cs:215-221`），
  **两处都是**先 `NtpAssets.IsTopLevelNtpDocument(core)`（顶层文档必须是 ntp 虚拟主机）
  再把 `ev.Source` 交给 `NtpBridge.IsTrustedSource`（https + 固定 host + 默认端口）二次校验，
  不符即静默忽略。per-origin 面不止写在注释里：`WebView/WebView2Hardening.cs:90` 的
  `SetPerOrigin` 在每次顶层导航按来源翻转 `IsWebMessageEnabled`（远程页禁用），
  `WebView/HostWebView.cs:142` 记着子框架形态的取舍理由。⇒ 本项「待验证」就地转成已核实。
- **AEG-013 的「只修主窗未修无痕窗」这一类部分闭环在本项上不成立**——无痕窗走同一
  `NtpBridgeFactory.CreatePrivate` + 同一顶层门禁。⇒ 不登记缺陷；若要攻的是「导航中途
  旧页面残留消息」这类时序面，须按 §五 攻击面矩阵做动态测试再判，不靠静态读代码翻案。
### 3.24 R9-B24（2026-10-11，外部审计 AX-07 = §五 Q6）：危险下载确认绑定发起标签

1. 回读确证（不引用报告措辞）：`BrowserViewModelConfirmations.kt:104-108` 的
   `approvePendingDownload` 取出 pending 即 `proceed()`，而同文件上面的
   `approvePendingNavigationConfirmation`（:80）一直有
   `pending == null || currentWebView() !== pending.webView ⇒ 拒 + 提示切回`。
   `PendingDownloadConfirmation`（`BrowserModels.kt:36-45`）**本就带 `webView` 字段**
   （装配时 `registerPendingDownload(webView, url, proceed)` 已传）⇒ 缺的不是信息，是判据。
   另一半在 `BrowserViewModelTabs.kt`：`newTab`/`switchTo` 只撤销导航确认，pending 下载
   跨标签存续（`closeTab` 走归属式撤销，只清被关闭那条）。
2. 落地＝两处同导航口径：`approvePendingDownload` 先对 `currentWebView()`，不符**不清槽**
   （回原标签仍可确认，与导航一致）只给 `confirm_switch_back` 提示；`newTab`/`switchTo`
   各补一条 `confirmations.rejectPendingDownload()`。审计的第三条建议
   （「下载目标状态变化时重新审核」）不在这刀里——它要动 `WebViewDownloadHandler` 的
   Content-Disposition/重定向复核，另属 §五 既有队列，不顺手扩。
3. 新常驻 `android/app/src/test/kotlin/com/aegis/browser/DownloadConfirmationOwnershipTest.kt`
   （197 行，7 例）：5 例行为面（归属相符消费一次 / 不符不 proceed 且不清槽 / 回原标签仍可确认 /
   拒绝仍清零——反向控制防「归属判定把拒绝变成保留」/ 关无关标签不误清），
   2 例装配面文本锚（`newTab`/`switchTo` 切片必须同时看得见导航撤销与下载撤销——前者是
   正向控制，证明切片取对了地方；`approvePendingDownload` 必须落在**同一个** `currentWebView`
   缝上，另起一份「活动标签」定义就是第二个判据源）。
4. 本地实测：`./gradlew :app:testDebugUnitTest` 全套 **315 例 0 失败**（新增 7 例在内）；
   三处故障注入见下条。
   **本批自己写的一句失实声明就地更正**：PR #158 首跑前我在台账与 CSV 里写
   「ktlint/detekt 零新增违规」，而那两条门禁当时**从没在本地跑过**——CI 当场判红两条
   （`BrowserViewModelTabs.kt:162` 行尾注释的三空格对齐＝`Unnecessary long whitespace`；
   测试文件里 `throw IllegalStateException`＝detekt `UseCheckOrError`）。二者本地都能抓
   （`./gradlew :app:ktlintCheck :app:detekt`，32s），修完复跑 `:app/:broker/:webview-adapter`
   三个 `testDebugUnitTest` 全绿。教训与 §3.22 第 6 条同型：**能跑的判定面必须跑完再写结论**，
   「看起来只是格式」不属于可免检的范围。
5. 反向锚实测：① 从 `switchTo` 删掉 `rejectPendingDownload()` ⇒ 装配锚判红；
   ② 把 `approvePendingDownload` 改回旧形态（取出即 proceed）⇒ 跨标签那例判红；
   ③ 把归属判据换成构造时快照……本例**不适用**（判据是每次调用的 lambda 缝，
   不存在快照形态），故不写空锚——只登记「判据必须走 `currentWebView()` 单源」这一条。

### 3.25 R9-B25（2026-10-11，外部审计 AEG-006）：契约向量的逐端消费面入门禁

1. 先把报告那句话变成可判定的量：`git ls-files` 收口受管源码面（541 个 `.cs/.kt/.kts/.rs/
   .py/.js/.mjs/.yml`，排除 `target/ obj/ bin/ build/ dist/ node_modules/` 与向量本体），
   命中口径＝**词干作为独立词**或**完整文件名**。markdown 提及不算——否则「文档里写了一句」
   会冒充「测试跑过」。`SCHEMA_LEVEL`（`validate_vector_schemas.py` + 它的输入守卫用例）
   也不算端侧消费者：它判的是「实例对 Schema 的通过/拒绝＝向量自述的 expected」。
2. 实测结论（15 份）：`url-origin-valid/invalid` 是**仅有的两份 CS∧AD 同跑**；
   `native-navigation-decision` 到 CS+RS（**这条 CS 已被 R9-B39 证伪**：唯一的命中是注释，
   登记表已回到 `{"RS"}`，见 §3.39 / §二 R9-SH-15）；`action-*`/`glob-match`/`approvals-replay-and-expiry`/
   `native-navigation-confirmation`/`update-manifest-invalid` 只 RS；`update-manifest-canonical`
   RS+PY（`tests/python/release_tools_test.py`，真实消费者）；`update-manifest-valid` RS+CI
   （`supply-chain.yml`）；`capability-*` 与 `audit-event-*` 四份**零端侧执行者**。
   `AG` 一次都没出现 ⇒ Agent 端不消费任何契约向量（与 R9-SH-5 互为表里）。
3. 落地＝`scripts/verify_vector_consumers.py`（223 行）+ `tests/python/vector_consumers_test.py`
   （17 例）：`CONSUMER_MANIFEST` 双向不变量（少一面/多一面/新增未登记/过期登记四种都判红）、
   跨端支点下界（判据 3 **不随登记表松动**：把 url-origin 改成单端登记仍判红，否则 AEG-006
   可以靠改表被说反）、端侧执行者下界 10、向量面 15 与扫描面为空都退 2。
   接进 `contracts.yml` 的 `contract-source-of-truth`（PR 触发、ubuntu）。
4. **注入式自证从 `--self-test` flag 搬进 pytest**：脚本一度自带 8 条内存态注入，但那要人
   主动敲 flag——正是 R9-SH-7 记过的「跑不动的判据＝没有判据」；搬进 pytest 后每条 PR 都执行，
   脚本同时从 327 行降到 223 行（回到新文件 ≤300 红线内）。
5. 本批自己也被自己的门禁打回过**两次**，都写进注释而不是删掉了事：
   ①`update-manifest-invalid` 与 `-valid` 的 `PY` 命中其实全部来自元层文件（首版按直觉把它们
   记成 PY 消费者），本地跑第一遍即判红；
   ②CI 首跑（PR #159）红 13 项——原因是**门禁脚本与它的 pytest 用例本身就在源码里写出了
   每一份向量的名字**，本地跑时这两个文件还没 `git add`（`git ls-files` 收口面里没有它们），
   提交后扫描面 541→543，于是 15 份向量全部「被 PY 执行」。⇒ 判据口径补一条硬规则：
   **按名遍历整个向量目录的工具面一律计入 `META_LEVEL` 排除，包括门禁自己**。
   「本地绿、CI 红」这次不是临场校验比门禁松（§3.22 第 6 条那一型），而是**门禁的扫描面
   依赖 git 跟踪状态**——这条依赖现在写在脚本注释里，且用例必须在提交后重跑一遍才算验过。
6. 扩面工作另登 §五 **Q53 R9-SH-13**（不顺手做：给 C#/Kotlin/Agent 各接一份向量执行面＝新增
   端侧裁决实现，与 §四 第 1 项 AX-02 是同一次改造）。

### 3.26 R9-B26（2026-10-11，Q50 第一半）：Android 桥受信面收窄成壳页精确名单

1. 依据是实测而不是猜测（`dist/geogebra-cache` 当前副本，436 文件 / 117MB）：
   grep `AegisBridge`、`__aegis`、`android_asset`、`JavascriptInterface`、`navigate(` **全 0 命中**；
   `aegis` 的 6 处命中都在 `*/deferredjs/*/*.cache.js` 的 base64/WASM 块里（不是标识符）；
   `openGeo` 的 3 处是 GWT 自带的 `OpenGeoProver`。画板页在 `geogebra/` 子树、不加载
   `start.js`（后者在 assets 根），从画板返回走 `MainActivity.kt:295` 原生
   `navigateHistory(BACK)` 而不是桥的 `goBack`；桥的五个方法在原生侧都有等价路径
   （`BrowserViewModel.kt:144,297,329,371`）⇒ **主页之外没有合法桥消费者，画板不受影响**。
2. 改动（`AegisHomeBridge.kt:56-75,112-137`）：`isTrustedShellUrl` 从前缀匹配改成
   「assets 根下的顶层资源名逐字等于登记名」，名单由 `BrowserEngine.HOME_URL` **派生**
   （不在第二处抄字面量——首页改名会让桥自锁，而 `HomeUrlContractTest` 只钉 HOME_URL 那头）；
   query/fragment 先剥（壳页确实可能带 `#片段` 被 `getUrl` 报告回来，不剥就是把自家首页拒了），
   剥完不接受子路径。写成单个 `when` 表达式而非四段提前 return（detekt `ReturnCount` 上限 2，
   本地 `:app:detekt` 首跑就是被这条打回的）。
3. 测试（`AegisHomeBridgePrefsTest.kt:148-175`）：原 `:151-153` 那条 `assertTrue(geogebra…)`
   改成 `assertFalse` 并写清理由（它是把前缀语义**举例枚举**成断言，不是功能需求——
   挂在 AD-112「纯判定函数」标题下，无任何「画板需要桥」的注释）；新增
   `sub/start.html`、`start.html.bak`、`start.htmlx` 三形态必须拒（后缀/子路径混淆），
   `start.html#engine`、`start.html?v=2` 必须受信（防「收窄把合法首页一起砍了」），
   以及 `isTrustedShellUrl(BrowserEngine.HOME_URL)` 把派生关系钉住。
4. 本地验证：`:app:ktlintCheck` + `:app:detekt` + `:app:testDebugUnitTest` 全绿（首跑 detekt
   判红一条，改完复跑通过——不是「跑不动就免检」）。
5. **Q50 的第二半（迁 `androidx.webkit` origin-scoped `addWebMessageListener`）本批不做，
   且理由不是「太难」**：那条路唯一多买到的能力是「拿到调用者所在 frame 的 Origin」。
   而①`frame-src 'none'`（§3.22）已让壳页文档内不可能存在任何 frame；②本批之后
   受信面又是精确名单。两者叠加后，「帧身份」这条判据没有可区分的输入了——迁移要动的
   却是三端共用的 `shared/shell/start.js` 两个通道选择点（`:30-33`、`:50-66`）与
   `start_host.test.mjs:119/134` 那种「Android 必须直调 `AegisBridge.goBack`」的常驻锚。
   ⇒ 记为「在当前形态下无收益的跨端契约变更」，将来若放开 frame 或新增第二个壳页，
   本条重新成立。Q50 就地标注第一半已闭、第二半带理由挂起。

### 3.27 R9-B27（2026-10-11，外部审计 AX-05/AX-06）：把「要求原生核心」编译进产物，发布链改验终物

1. 判定源重排（`Broker/NativePolicyCoreGate.cs`）：`IsRequired` =  构建常量 ⇒ 环境变量
   ⇒ 安装期标记，合一在纯函数 `ResolveRequirement(bool, string?, bool)`（注册表与环境变量
   不可注入，纯判定面才有 8 组合可测）。构建常量排第一操作数是语义本身——若它排在最后，
   「清注册表 + 清环境变量」就又能关掉要求。顺序由
   `NativePolicyCoreBuildRequirementTests.GateIsRequiredActuallyReadsTheBuildConstant`
   按「第一个实参」判，而不是只判「出现过」。
2. 生成机制（`Aegis.Windows.App.csproj`）：`GenerateNativePolicyCoreBuildMarker`
   `BeforeTargets="CoreCompile"` 写 `obj/generated/NativePolicyCoreBuildMarker.g.cs`，
   **true/false 两条分支都生成**（缺 else 分支 ⇒ 开发构建直接编译不起来，那是最坏形态）。
   两个 MSBuild 实测坑写进注释：裸 `;` 被当项分隔符（首版产物里留下
   `RequiredByThisBuild = ;` ⇒ CS1525，须写 `%3B`）；属性展开里没有内联条件表达式
   （`$(_X == '1')` 展开成空串 ⇒ CS1002）。开发机不传属性 ⇒ 恒 false，行为与以前一致。
3. 发布链验终物：`release-windows.yml` 在 publish 后按 **UTF-16** 解码已发布
   `Aegis.Windows.App.dll` 找姿态串（=1 必须在、=0 必须不在），并第一次打开
   `Aegis.Windows.zip` 断言 `aegis_policy_core.dll` 在其中（此前只 `Test-Path` 发布目录）；
   `release-android.yml` 改读 AGP 生成的 `BuildConfig`（`find` 空结果即失败）。
   本机实测两个构建形态的产物确实可区分（`=0` 与 `=1` 各命中一次，UTF-16 解码）。
4. **验证手段自身的依赖被钉住**：`const string` 没有任何引用点时不进元数据
   （实测 grep 命中 0）⇒ `App.xaml.cs` 的 `[adjudication]` 日志引用姿态串是这条 CI
   断言成立的前提，`PostureStringIsReferencedAtRuntime_OtherwiseNoArtifactCanProveIt`
   判的就是这个引用；「未被引用的守卫是死代码」在同仓已有先例
   （`NativePolicyCoreBridgeLeaseTests.IsUsableGuardIsActuallyConsumed`）。
5. 文档同批改真三处：`README.md:23-28`、`docs/adr/ADR-006…:41-45`、
   `docs/runbooks/windows-run-guide.md:57-68`——三处原文都写「由安装期标记驱动」，
   现在标记是第三来源。不留「文档说的 ≠ 实树的」这类账（R9-DOC 一整族就是这么来的）。

>>>>>>> origin/master

### 3.28 R9-B28（2026-10-11，外部审计 AX-02 / AEG-001）：策略层与能力层接入 FFI 通路

1. 审计处方（「把 capability 纳入统一导航授权对象、异常一律拒」）方向对，但**字面照做会
   拒掉全部导航**——生产构造是空规则 + 空注册表：`action_policy.rs:110` 的
   `let rule = best?;` 让「无匹配」返回 None，`PolicyEngine` 于是落 `FailSafe` 恒 Deny；
   `capability.rs:156` 让未注册 capability 恒 `Denied`。这两条是回读证据，不是推测。
2. 采用的口径：**该层没有意见时不改裁决；一旦配置即生效，且它的 Deny 不可被后面的
   Allow 出口改回允许**（单调加严）。接入点在会话验证**之前**——放在之后就成了
   「会话结果覆盖策略裁决」。判定本体 `src/broker/pre_layers.rs`（`ContextBroker` 的子模块，
   能读它的私有字段，因此不必给三层新增公共访问器）；FFI 侧映射
   `src/ffi/broker/policy_layers.rs`，`RequireConfirmation` 走既有
   `register_pending_approval`（第二份授权账不开），锁毒化返回 `broker_lock` 拒绝
   而不是「当作没意见继续放行」。
3. 测试两侧对称（6 + 3 例）：核心侧钉「空配置惰性 / 配置后终局 / Ask 不被吞 /
   能力白名单内外 / Deny 单调」；FFI 侧钉「未配置时拒绝码仍来自会话层」与
   「配 deny 规则后同一入参变 `policy_denied`」——后者一条同时证明接线**顺序**。
4. 行数红线（三个零余量文件）：`broker.rs` 1115、`ffi/broker.rs` 935、`capability.rs` 543
   全部守住——办法是把注记改写得更短（信息不丢，H-7 那段本就要重写）以及把
   `impl Default for CapabilityRegistry` 换成 `#[derive(Default)]`（clippy
   `derivable_impls` 本来就建议这个），新增逻辑全在两个新文件里。
5. **今天没有任何宿主入口去注册规则或能力** ⇒ 这次接线在出货形态上必然零行为变更。
   这不是「接了个永不响的钩子」：它把「策略/能力层不在 FFI 通路上」这条 P1 陈述变成
   假，并且让将来任何配置面接入时**不可能绕过核心**（顺序与不可覆盖性已被测试钉住）。
   真正的配置面（谁注册规则、能力白名单从哪来）仍是 §四 第 1 项的产品决策，本批不替它决定。


### 3.29 R9-B29（2026-10-11，Q52 = 外部审计 AEG-008 定稿后落地）：威胁订阅源周期重取 + 最后成功时间上设置界面

1. 定稿口径（用户 2026-10-11 对 §四 第 9 项说「全部完成」）：**默认 6 小时节拍、失败退避
   封顶 24 小时、「上次成功更新 / 是否过期」上 UI、保存后立刻刷一次**。三份数字单源在
   `ThreatFeedCoordinator` 的类常量（`DefaultRefreshInterval`/`MaxRefreshDelay`/
   `StaleAfterFactor`），界面算过期用 `DefaultRefreshInterval × StaleAfterFactor` 而不是
   抄一份 18 小时——这条由 `Stale_threshold_comes_from_the_same_constant_as_the_cadence`
   判（它同时断言界面源码里出现这两个常量名）。
2. 周期与退避：`Start()` 仍做首刷（既有语义与既有用例都不变），之后 `RunPeriodicRefresh()`
   **先等再取**。`NextDelay(interval, failures)` 是纯函数：无失败⇒节拍本身，此后每次失败
   翻倍，封顶 24 小时，且**只拉长**（`interval <= 0` 时原样返回，关闭周期是显式语义）。
   每轮**重读** `_resolveFeedUrl()` 并重新校验 ⇒ 改源不需重启，而未配置/改成非法值那一轮
   零网络活动（「未配置源 ⇒ 零流量」这条既有判据在周期化之后仍然成立，且单独有用例钉）。
3. 「最后一次成功」不新增字段：`ThreatFeedUpdater.FetchAndStore` 只在抓取+校验+落盘
   全部成功后原子替换缓存文件（tmp+Move），所以**文件写入时刻就是权威值**。加
   `AppSettings` 字段要同步 SettingsService 快照与两个 XAML 锚，代价远大于收益，且会多出
   一份会漂移的进程内副本。文案是纯函数 `ThreatFeedCacheStatus.Describe`（相对时长而不是
   绝对时刻，因此「按 UTC 取的文件时间」不进文案；时钟被回调 ⇒ 负 age 落进「刚刚」档而不是
   显示「-3 分钟前」）。
4. 两条**新出口带来的竞态**才是这次改动的实质风险，都有故障注入锚：
   ① 周期循环与「保存即刷」并发 ⇒ 两个抓取各自 apply 一次，**后完成**的那个决定最终名单，
   而它可能是先发出那个请求的旧结果。加 `SemaphoreSlim(1,1)` 串行化；刻意**不**做成
   「已在跑就跳过」——那会让用户保存后的手动刷新静默失效。锚
   `Concurrent_refreshes_are_serialised` 用进入计数重叠检测（撤闸门即红）。
   ② 设置界面需要一个「当前在跑的协调器」才能刷——`Active` 单点（`KillSwitch.Shared` 同款），
   由 `Start()` 赋值。它是一条真实的接线而不是一句文档：
   `Start_registers_the_active_coordinator_for_the_settings_window` + 源码文本锚
   `SettingsWindow_wires_the_saved_feed_to_an_immediate_refresh` 共同钉住（WPF 窗口起不来，
   所以判定用静态锚，正向锚 + 反向锚成对：旧文案「生效于下次启动」从 `.xaml.cs` 与 `.xaml`
   两个文件里都必须消失）。
5. **既有五个用例必须显式关掉周期**（`ThreatFeedCoordinatorTests` 三处 +
   `CoreDenylistPublisherTests` 一处传 `refreshInterval: TimeSpan.Zero`）：它们靠
   `await BackgroundTask` 收口防 Dispose 与后台写盘抢缓存句柄（CS-350 那笔账），周期化后
   那条任务永不完成 ⇒ 不改就是挂死。这不是「测试挡路」，而是**周期化的真实代价**：
   后台链的生命周期从「一次」变成「与进程同寿」，凡等它收工的地方都要自己表态。
6. 坑一条（已写进用例注释）：`TimeSpan.Parse("24:00:00")` 是 **24 天**而不是 24 小时
   （实测差值 `Expected: 24.00:00:00 / Actual: 1.00:00:00`），首段 ≥24 被 .NET 按天解析。
   期望值因此改成小时数（`TimeSpan.FromHours(expectedHours)`）——字符串形态的时间期望值在
   这里会静默判错一个量级，而 `[Theory]` 的三行恰好只有封顶档踩到。
7. 余量与验证：`MainWindow.xaml.cs`（435 行零余量基线）**零改动**，调度全部留在协调器里；
   三个新文件 254/128/52 行都在 300 红线内，`check_file_sizes.py` 在 `git add` **之后**重跑
   （扫描面按 `git ls-files` 收口，提交前跑等于没算新文件——R9-RS-2 同课）。本地
   Core **859/859**、Broker **204/204**、`-r win-x64 -p:RestoreLockedMode=true` 下 0 警告 0 错误，
   `packages.lock.json` 未被改写。以 CI 为唯一通过依据。
8. 顺带把一个**不实声明**改成事实：清空订阅源那句原文写「黑名单退回空表（导航与子资源
   不因此拦截）」，而现树清空后已生效快照继续拦截、缓存文件也不删、重启后仍加载——
   改成「此后不再自动重取，当前名单仍会继续拦截」。「清空即解除」本身没做（放松防护方向）
   ⇒ 新登 §五 Q54 / §四 第 10 项。
9. **补 R9-B22 欠下的文档账**（改 README 的订阅源那句时发现两处已失实的陈述，都来自
   本会话早先落地的批次，不是外部审计的新报）：`README.md` 与
   `docs/product/supported-features.md` 都把「NTP 宿主桥」与「后退/重载入口」并列写成
   KillSwitch 缺口，而 AX-04 已经在 `NtpBridge.Dispatch` 查闸——按 §二 那行的口径拆开写：
   桥侧 6 项有副作用操作已查闸（拒绝码 `lockdown_engaged`），仍在的是
   `MainWindow.Menus.cs:180`/`182`、`MainWindow.Shortcuts.cs:204`/`241`/`257`、
   `InPrivateWindow.xaml.cs:322`/`332` 不在**入口处**查闸，其引发的导航由
   `EvaluateNavigation` 以 `kill_switch_engaged` 拒绝（所以这条是「不早退、无即时反馈」
   而不是绕过——后半句未经真机确证，如实标注）。`docs/product/feature-parity-checklist.md`
   的订阅刷新行同步补上周期重取事实。**教训：落地一条判定面时，凡是把该缺口写进
   「已知缺口」清单的文档都在失效面里，要同批扫一遍**（`check_doc_claims.py` 只判计数，
   这类陈述性失实它抓不到）。

### 3.30 R9-B30（2026-10-11，项 10 = 外部审计 AEG-011 / 第八轮 R8-DEPS-8）：Android 四模块启用 STRICT 版本锁 + 重锁执行面

1. 先把判据读准（这条同时更正第八轮 R8-DEPS-8 的登记文本）：`dependencyLocking
   .lockAllConfigurations()` 锁的是**全部可解析配置**，不是「只覆盖直接依赖」——实测锁文件里
   有 `debugAndroidTestCompileClasspath`、`debugLintChecksClasspath`、`detektPlugins`、
   `ktlintRuleset` 这些传递与工具面条目。当年 AD-155 据此给的第二条否决理由
   （「双源维护成本：catalog 升级忘重锁就解析失败」）在 STRICT 下**翻转成门禁本身**：
   版本漂移不再是静默发生，而是必红。真正剩下的代价只有「每次升级多跑一次重锁」，
   而这条已被工具化（见第 5 点）。
2. 落地形态：锁块**单源**一份，写在 root `android/build.gradle.kts` 的 `subprojects` 作用域里
   （`lockAllConfigurations()` + 显式 `lockMode = LockMode.STRICT`——STRICT 虽是缺省，靠缺省就是
   「缺省一变即静默放松」）。这个形状不是审美选择：`:app/build.gradle.kts` 停在 316 行的
   **零余量基线**（行数红线：基线文件只许减不许增），逐模块各写一份第 5 行都塞不进去；而单源
   恰好把覆盖面从「写脚本时存在的那四个模块」变成「全部现有与后续子模块」——fail-open 变
   fail-closed。时序也有实义：root 脚本先于子模块脚本求值，所以 `lockAllConfigurations()` 注册在
   AGP 创建变体配置与 ktlint/detekt 创建工具配置**之前**（实测锁里确有这些条目）。
   判据/覆盖面/重锁 SOP 单源写在 `settings.gradle.kts` 的决策记录里（注记不散落防漂移）；
   四把 `gradle.lockfile` 入库（`:app` 314 行，四把共 277 个唯一 `group:name:version`）。
   **不覆盖的面**如实写进 settings 与 SECURITY.md：`buildscript {}` 与 plugins DSL 是
   **脚本类路径**，不在项目配置锁内（那一路由 root 的七条显式 classpath 地板 +
   `buildEnvironment` 回读承接）；锁里也**不含校验和**，整树哈希/签名验证是
   dependency verification 那一刀 ⇒ §五 Q55【已由 R9-B50 / §3.50 落地：`gradle.properties` 的
   strict 档位 + 文档 495 组件 / 842 条 sha256，重锁同批补录】。
3. **门禁是实测的，不是推断的**，两次故障注入都判红：①删掉 `android/app/gradle.lockfile`
   ⇒ `Locking strict mode: Configuration ':app:debugCompileClasspath' is locked but does not
   have lock state`；②给 `:app` 加一条新依赖（`org.apache.commons:commons-text:1.15.0`）
   ⇒ `Resolved '…' which is not part of the dependency lock state`。
   ②在改成 root 单源**之后**又重跑过一次（注入点 `:contracts:compileDebugKotlin`，同样 EXIT=1），
   所以 enforce 不依赖「写在模块脚本里」这个形状。
   注入过程还抓到一个**判据陷阱**（本批最有普适价值的一条）：`:app:dependencies`
   这类**报表任务**把解析失败吞成树里的 `FAILED` 文本并 **EXIT=0**——所以「锁是否可消费」
   绝不能用报表任务证明，必须用真正吃 classpath 的任务（`compileDebugKotlin`/`assembleDebug`）。
   dependency-relock 的 gradle 面因此写的是实任务清单，不是 `dependencies`。
4. 覆盖面由两条常驻门禁判（都在 `contracts.yml` 的 `pytest tests/python` 面里，PR 必跑）：
   ①新文件 `tests/python/gradle_locking_test.py`（9 例）——模块清单从 `settings.gradle.kts`
   的 `include(...)` **现取**（不在测试里抄名单，抄了就判不到新增模块），判「root 有且只有一份
   写在 `subprojects` 里的锁块」「模块脚本没有自己的副本」「每个模块目录里有 Gradle 形态的锁文件」
   「CI 会解析的配置名确实在锁里」「ktlint/detekt 工具面也进锁」，并钉 settings 决策记录与
   SECURITY.md 的口径（旧句「Gradle 依赖无 lock 文件」必须消失）。反向锚是**四条注入**：
   拆掉 `subprojects` 包裹 / 删掉 `lockMode` 行 / 删掉整块 / 复制成两份，任一不被判红即报错；
   ②`relock_sop_test.py` 的 gradle 半边——当时钉的是「重锁任务清单 ⊇ CI 各 workflow
   里会解析依赖的 gradle 任务」。
   【R9-B32 更正：这条锚判错了面。「清单 ⊇ 任务名」看着严格，实际漏掉了**不属于任何任务名**
   的配置（AGP UTP 构建监听器解析的 `:app:androidTestUtil`），而它红在 master 而不是红在 PR。
   判据已改成按模型枚举 `canBeResolved` 集合，见 §3.32。】
5. 重锁执行面：`.github/workflows/dependency-relock.yml` 新增 `gradle-relock` job。
   为什么是独立 job 而不是在 windows job 里加几步：AGP 要「JDK 21 + setup-android 基线包
   （`platforms;android-36`/`build-tools;36.0.0`）+ compileSdk 37 由 AGP 构建期自动装配」
   这套已在 ubuntu 实证过的组合（SP-238：显式 pin android-37 因未进 stable 渠道必失败），
   搬到 windows 重验只会换来「重锁面与门禁面不同形」。守卫照 R9-CI-2 写在**每个**持
   写权限的 job 里（dispatch 输入经 env 中转、run 正文零 `${{ }}`、push 前二次判 `deps/*`），
   **坑一条**：Gradle 9.8 里根本没有 `writeLocks` 任务（实测
   `Cannot locate tasks that match ':app:writeLocks' as task 'writeLocks' not found in project
   ':app'`）——重锁只能是「跑任务 + `--write-locks`」，所以「跑哪些任务」本身就是判据（第 4 点
   的覆盖关系锚判的就是它）。这条写进 settings 的决策记录，防下一轮又去找那个不存在的任务。
   并新增「diff 里必须全是 `gradle.lockfile`」这条——纯重锁运行里冒出别的改动（顺手改了
   版本目录）就不推。`ecosystem` 输入加 `gradle`，同时 windows 的 `relock` job 用
   `if: ecosystem != 'gradle'` 排除自己（它没有 Android SDK，跑了就是「写不回任何东西的成功」）。
6. Dependabot 的 gradle 生态早就在跑（`/android`，weekly）。启用锁定后的分诊口径写进
   `.github/dependabot.yml` 注释当时写的是「**Dependabot 是否会在同一 PR 里重写
   `gradle.lockfile` 本仓未实证**」——这条在下一批就被 #167 证真了（见 §3.31：四把锁
   在同一个 PR 里被重算）。登记时的处理是对的：没证据就不写成断言，只写「锁没动就要
   人工补锁」的可执行 SOP；拿到证据后再把口径改真。
7. `android/settings-gradle.lockfile` 被 `.gitignore` 单条忽略，理由写在注释里：它是
   `--write-locks` 顺手生成的 settings 侧产物，恒为一行空条目（版本目录那条内部配置不解析
   任何坐标）；实测删掉后 `./gradlew help` EXIT=0 且不重建。入库会让第 5 点的守卫每次误判红。
   四把模块锁**绝不**用 `*.lockfile` 通配忽略——那等于把判定面自己忽略掉。
8. 本机边界如实登记：`:app:assembleRelease` 在本机 Windows 跑不动（AAPT2 windows daemon
   报「Please check if you installed the Windows Universal C Runtime」，与锁定无关）。
   release 面的锁覆盖是用 `:app:dependencies --configuration releaseRuntimeClasspath`
   与 broker/webview-adapter 锁里的 `release*Classpath` 条目实证到位，
   真正的 release 构建要等 CI 的 ubuntu runner——这一条不在「本地已验」清单里。
9. 验证：**同一条任务清单去掉 `--write-locks` 重跑两次都 BUILD SUCCESSFUL**——逐模块锁块
   形态下 12m45s，改成 root 单源后 9m36s（236 个可执行任务：23 实执行 / 213 up-to-date），
   覆盖 ktlint×4 / detekt×4 / assembleDebug / assembleDebugAndroidTest / lintDebug /
   testDebugUnitTest×3 / contracts:assembleDebug / broker+adapter compileDebugKotlin；
   `pytest tests/python` 新增 13 例全绿（9 + 4）。
   `:app:assembleRelease` 本机未跑（第 8 点），但 **release 的依赖解析面已单独实证**：
   `./gradlew :app:compileReleaseKotlin` 在锁上跑通（BUILD SUCCESSFUL）——它解析
   `releaseCompileClasspath`，而「锁不满足」只可能发生在解析阶段，不是打包阶段。
   仍未跑的是 R8/aapt2 那半段（与锁定无关）。


### 3.31 R9-B31（2026-10-12，#167 分诊 + 版本锁下 Dependabot 行为的口径改真）

1. **#167 是版本锁上线后第一次真实 bump**（gradle wrapper 9.8.0→9.8.1 +
   compose 插件 2.4.20→2.4.21）。它给出的事实比它的 diff 更值钱：**Dependabot 的 gradle
   生态会在同一个 PR 里重算四把 `gradle.lockfile`** ——该 PR 的文件面就是「四把锁 +
   `libs.versions.toml` 一行 + wrapper properties/jar」。于是 §3.30 第 6 点当时写的
   「未实证」就地改真（`dependabot.yml` 与 `settings.gradle.kts` 的决策记录同步），
   常规 bump 从此**不需要**人工 dispatch 重锁。
2. 锁面变化的方向核对过：坐标与配置**只增不减**（`:app` 309→328 坐标 / 33→38 配置，
   `:contracts` 14→27 配置——它解析到的配置比本仓 CI 任务清单更宽）。这不构成风险：
   `relock_sop_test.py` 的覆盖锚判的是「重锁清单 ⊇ CI 解析面」这个方向，宽一点只会多锁。
   消失的坐标全是 kotlin 2.4.20 一族被 2.4.21 顶替（外加 AGP UTP 的 android-test-engine
   几个新条目），没有「条目被删而无人解释」的形态。
3. 分诊核对（照 Dependabot 既有 SOP 逐字查证，不采信 PR 自述）：`distributionSha256Sum`
   与上游 `https://services.gradle.org/distributions/gradle-9.8.1-bin.zip.sha256`
   **逐字一致**（AD-277 那条完整性校验因此仍然成立）；9.8.1 是修三个高危 advisories 的
   patch（worker↔daemon 未认证反序列化两则 + 仓库禁用遇 SSL 失败可被投毒一则），
   属「越并越安全」那一类；compose 插件是补丁级。
4. CI 红灯归因：唯一红的是 `Automatic Dependency Submission (NuGet)` 的
   `submit-dependency-snapshot`，日志是 `HttpError: Server Error` —— GitHub 依赖提交 API
   的 5xx；`gh run rerun --failed` 后即全绿。**不改它**：给提交步骤加
   `continue-on-error` 等于把这条判据关掉，而「第三方瞬时故障靠重跑收敛」是可以接受的噪声。
5. 本批真正的改进是**消掉一个漂移类**而不是再抄一遍数字：`android-quality.yml:6` 与
   `gradle-wrapper.properties:5` 两处注释此前把工具版本抄在散文里（SP-252 抄 9.7.0→9.8.0，
   #167 又漂到 9.8.1，两轮都要人回头改注释）。现在改成指向单源——
   「版本＝`gradle-wrapper.properties` 的 `distributionUrl`」「校验对象＝同 URL 追加
   `.sha256`」。**凡是把版本号抄进注释的句子，下一次升级都会变成一句假话**；
   要么不写数字，要么写「去哪里读」。
6. 同批登记 **Q56 R9-CI-14**（§五 5.5）：`gradle-dependency-graph.yml` 只在 master push /
   周 schedule 上跑，Dependabot 给它的**跨 major**（#165：`gradle/actions/dependency-submission`
   4.4.4→6.4.0，SHA↔tag 已逐字核对为 v6.4.0 的 commit `3f5f9ad`）在 PR 面一张牌都没执行过
   那个动作 ⇒ 合并等于「未经运行的跨 major」。本批的处置是**先证后合**：合 #165 后立即
   看它自己触发的 push 运行与依赖图是否更新，失败即回滚。结构性修法（加 stale 检测）
   属 CI 面变更，等用户点头。

### 3.32 R9-B32（2026-10-12，自查红灯）：锁的覆盖面从「抄任务清单」改成「按模型枚举」

1. **这是本会话自己引入、且被自己引入的门禁漏掉的缺陷**（登记级别按事实定 P2：
   不影响出货制品，影响 CI 的持续可用面）。现象：`Gradle-Dependency-Graph` 在 master 上
   连红两次（`#164`、`#167` 两次合并各触发一次），报
   `Locking strict mode: Configuration ':app:androidTestUtil' is locked but does not have lock state`
   （另有 1 条同因失败）；而**同期每一条 PR 门禁全绿**。
2. 归因不是「Gradle 有问题」，是我把覆盖判据写成了「重锁任务清单 ⊇ CI 里的 gradlew 任务名」。
   `androidTestUtil` 由 AGP 的 UTP **构建监听器**在依赖图生成时解析——它不出现在任何任务名里，
   所以那份清单可以「抄得完全正确」而仍然漏掉它。这正是本仓反复登记的形态：
   **判据判的不是失效面，就等于没有判据**（R9-SH-7 同课，这次是我自己踩的）。
3. 修法把集合定义拿回来，两侧同时改：
   ①root 新增常驻任务 `verifyDependencyLockCoverage`——枚举本模块所有 `canBeResolved`
     配置，与 `gradle.lockfile` 里出现过的配置名（坐标条目 + `empty=`）对账，缺一个就
     fail-closed 列出全部缺口；接进 `android-quality.yml`（PR 面，一条命令判四个模块，
     不解析产物、秒级）。②重锁面改成 `resolveAllConfigurations --write-locks`
     （解析每个配置的**依赖图**）+ 紧接着跑一次 `verifyDependencyLockCoverage` 自证。
     用图解析而不是 `.files`：锁记的是版本，文件解析会连带要求本模块产物已构建
     （实测库模块的 androidTest 文件解析因此假失败 35 条）。
   解析面 ⊇ 任何任务清单，从此是集合事实而不是纪律。
4. 实测取证（本机 Gradle 9.8.1）：旧锁跑新门禁 ⇒ 判红并逐个点名（`:app` 8 个、
   `:contracts` 15 个缺状态，第一条就是 `androidTestUtil`）；
   `resolveAllConfigurations --write-locks` 补齐后 ⇒ 四模块 45/41/41/41 个可解析配置全部有状态，
   检查通过。锁的变化是**纯增覆盖**：`-15 +15` 行里坐标三元组集合只动了
   `org.jetbrains.kotlin:compose-group-mapping:2.4.20 → 2.4.21`（跟随 #167 的 catalog 值），
   没有任何配置名从锁里消失。
5. 反向锚三条（都在 PR 面跑）：从 app 锁里抹掉 `androidTestUtil` ⇒ `gradle_locking_test.py`
   的监听器配置判据归因到它；从 workflow 里删掉 `--write-locks resolveAllConfigurations` 或
   删掉覆盖自证 ⇒ `relock_sop_test.py` 两条 `pytest.raises` 判红；root 脚本里少注册任一任务 ⇒
   `test_root_script_registers_both_lock_tasks` 判红。旧的那条「清单 ⊇ 任务名」锚随之删除
   （留着它就是在保护一个错误设计）。
6. **红灯实为三次、同一因**：`#164`、`#167` 两次合并各触发一次 push 运行，加上周一那条
   周 schedule 运行（三次都是 `Could not resolve all dependencies for configuration
   ':app:androidTestUtil'`），全部发生在修复之前。修复合入（#169）后 master 的 push 运行
   转绿——正证取的是「红灯消失在被修的那面」，不是把旧运行 rerun 洗白。
7. `#165`（`gradle/actions/dependency-submission` 4.4.4→6.4.0 跨 major）先前那次 dispatch
   验证被本缺陷挡住，结论对它**不作数**；本批改完后重做了两遍才算证过：①在一条临时分支上
   打同一行 pin 后 dispatch，日志走到 `Submitted ...: The snapshot was accepted, but it is
   not for the default branch.`（图生成 + 提交都成功，只是非默认分支不刷新仓库级结果）；
   ②合并 #165 后由 push master 触发的真实运行 success。pin 也逐字对过上游：`3f5f9ad` 就是
   tag `v6.4.0` 指向的 commit（旧 pin `748248d` == `v4.4.4`）。之所以肯为它多跑两遍：
   这个 workflow 只在 master / schedule 上跑，PR 面那 18 张绿牌一张也不会执行它。

### 3.33 R9-B33（2026-10-12，队列 Q23 / Q9 / Q49 + Q12·Q14 的残余）：带外抓取的读取口径单源化

1. **Q23（R9-CS-2，P2）落地形态**：新增 `windows/src/Aegis.Windows.App/Core/Security/HttpFetchGuard.cs`
   （`ReadBoundedAsync:29` 有界读取 + `RedirectProblem:48` 逐跳落点判定）与
   `Chrome/SourceFetcher.cs:32`（手动逐跳抓取，上限 `MaxRedirectHops = 3`，相对 `Location` 按**当前跳**解析）；
   `Chrome/MainWindow.SourceViewer.cs:38` 的抓取客户端从「默认自动跟随重定向」改成
   `AllowAutoRedirect = false`，编排整体交给 SourceFetcher。裁决边界写进类型注释而不是只写在 PR 里：
   **首跳不判保留地址**（2026-10-04「本机与内网必须能打开」是用户裁决），重定向落点判——
   因为那一跳是页面选的，不是用户选的。
2. **实测撞出来的第二层缺陷（另登 R9-CS-10，见 §二）**：`HttpClient` 默认
   `HttpCompletionOption.ResponseContentRead` 会在 `GetAsync` 返回前把响应体整包缓冲 ⇒
   此前 ThreatFeed 与 favicon 那两处「Content-Length 预筛 + 限量缓冲」对**不声明长度**的响应
   根本不成立，CS-232 当年想挡的无界分配仍然在。三条路径统一改 `ResponseHeadersRead`。
   证据形态值得记一句：新用例第一次跑报的不是「超过 5MB」而是
   `Cannot write more bytes to the buffer than the configured maximum buffer size: 2147483647`
   ——是那条用例把这件事暴露出来的，不是推理出来的。
3. **门禁**（`OutOfBandFetchDisciplineTests`，3 条）：扫描面按「`windows/src` 下含 `GetAsync(` 的文件」
   **现取**而不是写死名单，逐个要求 `HttpFetchGuard.ReadBoundedAsync` + `ResponseHeadersRead` +
   不再出现 `ReadAsByteArrayAsync(`；第二条钉住扫描面确实认得出那三个文件（否则「零个输入」会让第一条
   静静变绿）；第三条是内存态注入反向锚（照旧写法造一个抓取点，三处缺失都要被归因）。
   剔 `//` 注释后才判——本批注记里逐字抄着被禁写法（同口径第三次使用）。
4. **Q9（R9-AD-9，P3）**：解码器单源化成新文件 `android/app/src/main/java/com/aegis/browser/PercentEncoding.kt`
   （`decodeStrict`），`DownloadPolicy.kt` 与 `WebViewDownloadHandler.kt` 两处调用点都改走它；
   `WebViewDownloadHandler.kt` 随之 414→346 行（私有实现与三个十六进制常量搬走），零余量基线只减不增。
   **一处行为变更按事实登记**：Android 的**查询值**解码也从 `URLDecoder`（`+`→空格）改成严格 `%XX`，
   理由不是「更严」而是「与 canonical 端同一答案」——Windows 侧路径段与查询值都是
   `Uri.UnescapeDataString`（`Core/Downloads/DownloadPolicy.cs:65,130`，严格、不动 `+`）。
   两端实测差异只在 `x.exe+` 这类字面文件名：旧 Android 先解成 `x.exe ` 再被净化 trim，于是比
   Windows 多拦一层；现在两端同判不拦（`exe+` 不在危险集）。该差异有专门用例钉住
   （`PercentEncodingTest.downloadPolicyKeepsPlusLiteralAcrossPathAndQuery`）。
   新增 `PercentEncodingTest`（5 条：`+` 字面、多字节序列整体按 UTF-8 解、孤立 `%`/半截转义/非法 UTF-8
   都原样返回、DownloadPolicy 两端同判、以及一条「主源里不许再出现第二个百分号解码器」的树扫锚）。
5. **Q49（R9-DOC-20，P3）**：`docs/runbooks/device-validation.md:19` 按代码改真，读的四点是
   `WebView/HostWebView.cs:268`、`Core/Downloads/DownloadPolicy.cs:46`、
   `Broker/BrowserPolicyBroker.cs:111`、`Core/Downloads/DownloadItem.cs:114`。结论：**「判 MIME」「判 size」
   两句都不成立**（`TotalBytesToReceive` 只喂进度条）；真实判定面＝危险扩展名三候选（建议文件名 ∪ URL
   路径末段 ∪ 各查询参数值）+ kill-switch + 保留地址 + 会话/标签上下文 + 无确认订阅者即 fail-closed。
   行内另给验证人三条可执行判据（含「`Content-Type: text/plain` 而文件名 `.exe` 时仍按扩展名拦——
   按 MIME 放行不是通过，那正是本行要防的类型混淆」）。与 R9-DOC-06 对 Android 那一行的更正成对。
6. **Q12 / Q14 的残余（另登 R9-SH-14）**：R9-B10 把两把强锁写出来了，但被它当场证伪的三段旧断言
   **一直留在** `start_page.test.mjs` 里——于是「新旧双双仍绿」这句话从落地那天起持续成立。
   本批删掉三段并把它们的独有覆盖面（`.link-btn`/`.snake-sound`/`.snake-close` 的 44px 保底、
   `CanvasText`/`ButtonFace`/`ButtonText` 三个系统色）并进按花括号配对切块的 `start_a11y.test.mjs:64,99`，
   判据改成「那一条声明本身带 44px」而不只是「名字在切片里」。两条反向锚各自还附一句
   「旧口径在同一份变异上应仍然放行」，把失效形态钉成文字。
7. **验证（本机全跑，不靠 CI 兜）**：`dotnet test Aegis.Windows.Core.Tests -r win-x64 -p:RestoreLockedMode=true`
   ⇒ 873 通过 / 0 失败（新增 SourceFetcherTests 11 条 + OutOfBandFetchDisciplineTests 3 条）；
   `./gradlew :app:ktlintCheck :app:detekt :app:testDebugUnitTest` ⇒ BUILD SUCCESSFUL，
   app 面 320 条单测 0 失败；`node --test tests/ui-regression/*.test.mjs` ⇒ 126 通过 / 0 失败；
   python 门禁全套（file_sizes / markdown_tables / markdown_links / doc_claims / workflow_shells /
   active_tree_gates all / pytest tests/python）复跑绿。ktlint 两轮红都是真形制问题：
   限定名开头的链要么整条断行要么整条不断行（`chain-method-continuation`），多行表达式赋值必须换行起
   （`multiline-expression-wrapping`）——与本仓既往「when 条目尾注/多行体」同一族，见 §二 R9-SH-2 的口径。

### 3.34 R9-B34（2026-10-12，队列 Q29）：⑨ 四档位协议在 C ABI 层的行为面补齐

1. 缺口按事实分两半：档位**状态机**在 `src/ffi/broker/denylist/tests.rs` 里早已跑全
   （staged 不可见 / 弃会话 / 无会话提交 / 旧路径不变 / 未知档位拒收 / 空会话提交清空），
   缺的是**线格式**——`aegis_policy_core_broker_update_host_denylist_json` 的应答里
   `mode/staged/served` 三字段在 Rust 全测试树零断言，ABI 层只端到端跑过 0/1 两档，
   `denylist_mode_invalid` 也没有 ABI 层用例。这条缺口不是学术问题：C# 提交判定
   读的就是那三字段（`NativePolicyCoreBridge.DenylistPush.cs:70-74` 的 `echoesMode` 是
   「字段不在就当作旧核心」的能力探测，`:130` 用 `commit.Staged/Accepted` 决定留
   `denylist_commit_refused`），而 C# 那 8 例跑在假核心上、真 DLL 用例不在必需检查
   （R8-CI-18）⇒ 核心改名/丢字段在 PR 面**一张牌都不会红**。
2. 新增 `src/c_abi/tests/denylist_modes.rs`（262 行，5 条用例，全走真 ABI）：
   ①`session_modes_travel_over_the_abi_and_stay_invisible_until_committed`——REPLACE(2)→BEGIN(3)→
     APPEND(1)→COMMIT 全程，逐档核对 `accepted/input/mode/staged/served/clear` 六个字段，
     并断言暂存条目在提交前**判定读不到**、提交后基线快照被整份换掉；
   ②`commit_without_a_session_reports_no_swap_and_serves_the_previous_snapshot`；
   ③`replace_discards_an_uncommitted_session_instead_of_landing_it_later`（丢弃是真丢弃：之后的提交换不出东西）；
   ④`unknown_modes_are_refused_at_the_abi_with_their_own_code_and_change_nothing`（取 4/256/-1 三种形态，
     拒绝后既有快照与被拒载荷都不留痕迹，且之后的 BEGIN/COMMIT 照常工作）；
   ⑤`form_rejected_entries_are_visible_as_counts_on_the_abi`（`accepted < input` 是宿主唯一能发现
     「死条目」的入口，四条形态非法条目不得进活动快照）。
   `assert_envelope` 是共用的字段面判据（带 `#[track_caller]`，红了直接指到调用它的那一档）。
3. **四条内存态变异各自证过红**（本仓对新锁的固定要求）：应答里删掉 `"mode"` 字段 ⇒ 5 条全红并
   点名「档位 N 的应答缺字段 mode」；`mode_is_known` 放行 4 ⇒ 只有④红；`host_denied` 改成也读
   暂存 ⇒ 只有①红（第 95 行，正是「暂存不得参与判定」那条断言）；COMMIT 的 `accepted` 改回报
   条目数 ⇒ ①②④三条各自红。
4. 顺带修掉一个会污染归因的测试脚手架问题：`broker_new` 是进程级单例（RS-140），用例 panic 时
   没走到 `broker_free` 就会把单例位永久占住 ⇒ **一个真失败伪装成五条 `broker_new` 失败**
   （第 3 条的变异实测就是这个形态）。改为 `LiveBroker` 在 `Drop` 里归还，红的时候只剩真红的那条。
5. 三个探针 helper（`denylist_payload`/`push_denylist`/`evaluate_code`）从 `buffer_boundaries.rs`
   上收到 `common.rs`：档位面与规模面判的是同一个入口，两份 helper 就是两份真相
   （`buffer_boundaries.rs` 203→166 行）。
6. 验证：`cargo fmt --all -- --check` 0、`cargo clippy --locked --all-features --all-targets -- -D warnings` 0、
   `cargo test --locked --all-features` 582 passed / 0 failed（原 577 + 本批 5）。

### 3.35 R9-B35（2026-10-12，队列 Q11）：SemVer 判据从「三份手抄」收成「一份 + 逐案等价」

1. 现象是真的，但**登记时的处方不完整**。Q11 写「PY-279 只收紧了 update-manifest 一份」，
   处方是「把 release/version 两张改成同一份」——照做会留下第三个分歧：PY-279 的式子
   **仍放过** `2.2.0-01`，因为前导零规则不在那条正则里，而在客户端另一段
   `_NUMERIC_ID`（PY-184：`int("01")==1` 会让 `2.2.0-01` 与 `2.2.0-1` 比较相等，防回滚有别名）。
   实测把两条历史式与验证器摆在一起对 31 个形态逐案判：旧宽松式放过
   `2.2.0-01` / `2.2.0-beta.` / `2.2.0-..` / `2.2.0+b..1`，PY-279 式只放过 `2.2.0-01` 一族。
2. 落地：`release.schema.json:12`、`version.schema.json:12`、`update-manifest.schema.json:26`
   三处 `properties.version.pattern` 换成同一条式子（数字标识符无前导零、标识符非空、
   字符集显式 `[0-9A-Za-z-]` 不用 `\d`——避免 Python 与 ECMA 的 Unicode 数字差）。
   实测该式与 `update_verifier._version_tuple` 的接受集在 31 个形态上**零分歧**。
3. 向量面（Q11 的第二半：「两张 schema 零向量」）：新增 6 份文件、39 条
   - `semver-form-valid.json`(16) / `semver-form-invalid.json`(15)：**形态电池**，
     每条都带 note 写明它为什么在该侧（如 `2.2.0-0a.1` 合法：以数字开头但含字母，
     不是数字标识符，无前导零问题；`2.2.0-alpha+001` 合法：构建段允许前导零）；
   - `release-valid.json`(3) / `release-invalid.json`(6)、`version-valid.json`(3) /
     `version-invalid.json`(5)：**实例级双向**，进 `validate_vector_schemas.py` 的
     `SCHEMA_VECTOR_FILES`（valid 必过 / invalid 必拒，无 semantic 豁免）。release 侧
     除版本串外还钉了 `architecture` 枚举与 `required`，失效面不只版本一处。
   `verify_vector_consumers.py` 同步登记（21 份 / 13 份有执行者 / 8 份仅 schema 级）：
   四条实例级向量记 `frozenset()`——**没有平台实现跑它们**，只由 schema 层判定，这是事实陈述；
   `semver-form` 两条记 `{"PY"}`，因为 `tests/python/semver_schema_parity_test.py` 真的逐案执行。
   登记时 gate 当场打回一条：本批的 parity 测试读取 `update-manifest-valid.json` 的首条
   manifest 当宿主模板 ⇒ 它的 PY 消费面是真的，登记表照改而不是把测试塞进 META_LEVEL。
4. 判据 `tests/python/semver_schema_parity_test.py`（6 条）：①三张 schema 同源（纯函数
   `parity_problems`）；②反向锚——内存态只改一张必须**只点名那一张**（归因跑偏也判红）；
   ③31 个形态过「客户端 × 三张 schema」四方对账；④电池判别力锚：把两条历史式喂进同一
   判据，必须各自在 `2.2.0-01` 上与客户端分歧（否则「等价」可能只是「两边都松」的巧合）；
   ⑤现役 `shared/release.json` 的 `2.2.0-beta.52` 三处都过（防「收紧到自伤」）；
   ⑥扫描面对账：`contracts/schemas` 里凡带 `properties.version.pattern` 的 schema 都须在
   登记表内——新增一张忘记登记即红。
5. 实树证红（不只是纯函数）：把 `version.schema.json` 改回旧宽松式 ⇒ ①②③三条同时红，
   还原后 6 条全绿。
6. 验证：`pytest tests/python` 620 passed（本批 +6）/ 1 skipped；`active_tree_gates all`
   （ruff/bandit/py312-compat）绿；`validate_vector_schemas.py` 与 `verify_vectors.py` 绿；
   `check_file_sizes` 绿（新测试 163 行 < 300 红线）。

### 3.36 R9-B36（2026-10-12，队列 Q28）：核心「已实现但未接线」的面与 README 对账

1. 这条 P3 的用户可见面是**文档过度声明**，而且有**两处**：`README.md:15` 的策略核心表行写「无 I/O 纯函数
   裁决——canonicalization / **Ed25519 阈值验证** / 指纹防护管线」，把 `update_manifest` 摆在
   运行时裁决面上。实测：`update_manifest` 只被 `tests/vectors.rs` 消费（与
   `contracts/vectors/update-manifest-*.json` 做差分），`c_abi/**` 与 `ffi/**` 里一次都没出现；
   同文件的目录树 `README.md:86` 又写「canonicalization + Ed25519 阈值验证」。出货路径上的清单验证
   是 Python 发布链 `release/update_verifier.py`。代价不是措辞——
   下一批会按「核心已经判了」去做接线取舍，或直接引用它当安全保证。
2. **范围按实测扩**：登记说三个，实际 8 个（清单见 §五 Q28）。过程中两条弯路值得留着，
   都是「判据看着像但不准」：①先写了个 BFS 推可达集，把注释里提到的 `crate::x` 当边、
   又漏了目录型模块的 `super::` 引用，推出的集合是错的 ⇒ **自制静态可达性不作判据**，
   只保留两条能 sound 化的负向检查；②用「宿主源码出现同名标识符」判消费——Windows 的
   `HttpsOnly` 是端侧另一份实现，会把未接线误判成已消费。
3. 落地：`scripts/verify_core_unwired_modules.py`（166 行）五条不变量——①登记表内每个模块
   必须仍是 `pub mod`；②接入层剔注释后出现模块名即红（**双向**：登记了却已接线也要红，
   必须删登记并同步 README，同 `verify_vector_consumers.py` 的口径）；③模块自身不得有
   `#[no_mangle]`/`uniffi::export`；④README 那句必须逐字含由登记表生成的模块名清单。
   ⑤凡提到「Ed25519 阈值验证」的那一条必须同时给出执行路径（这条一加，`README.md:86`
   当场判红——两处失实陈述就是这么被扫出来的，不是靠人想起来去搜）；
   接入层目录缺失 / `pub mod` 数异常小 ⇒ exit 2（面塌缩不是「变安全」）。
   接进 `contracts.yml` 的 PR 面，紧跟 `check_doc_claims.py`。
4. **接线者的坑写进门禁文档而不是模块头注记**：`HttpsOnlyState::upgrade()` 只判运营者手工
   白名单，不含 B8 的回环/RFC1918/CGNAT/`.local` 豁免 ⇒ 直接接进导航链会把
   `http://192.168.1.1` 升 https（R8-AD-01 原形态，且与「本机与内网必须能打开」的裁决冲突）。
   原打算写进 `https_only.rs`/`update_manifest.rs` 的模块头，实测两文件都在
   `check_file_sizes` 的零余量基线上（396/406 行），加 7 行注记当场判红 ⇒ 文本改放门禁
   docstring（接线动作必然先过这道门禁），取舍在此记下。Rust 面最终**零改动**。
5. 用例 `tests/python/core_unwired_modules_test.py`（8 条）：现树全绿 + 面未塌缩 +
   四条反向锚（接入层注入 `use crate::update_manifest`、把 `pub mod oracle;` 注释掉、
   README 少列一个模块、README 抹掉执行路径）各自判红并归因到点名对象；另有假目录下的「导出即接线」锚与
   「接入层缺失 ⇒ exit 2」。**注入用例打回门禁自己的一个真 bug**：`export_attrs_in()` 用
   `relative_to(ROOT)` 渲染路径，文件不在仓库根下时抛 `ValueError`——门禁应当报告而不是
   抛栈，改为 `rel()` 兜底。同一批还从生成文本里清掉一个零宽字符（U+200B，写在 docstring 的
   `` `.local` `` 里，肉眼不可见但会进库）。
6. 验证：`pytest tests/python` 628 passed（本批 +8）/ 1 skipped；`active_tree_gates all`
   （ruff/bandit/compat）绿；`check_file_sizes` / `check_markdown_tables` / `check_doc_claims`
   / `check_workflow_shells` 绿；`cargo fmt --all -- --check` 0、`cargo test --locked
   --all-features` 582 passed（Rust 零改动）。

### 3.37 R9-B37（2026-10-12，队列 Q24）：在途下载登记表的回收，与「事件面只有一个」的事实

1. 现象（登记在 §五 Q24）：`HostWebView` 放行下载后 `_trackedDownloads.Add(operation)`，
   **完成时从不移除**——只有 `UnwireEvents` 里一次 `Clear()`。长会话里已结束的
   `CoreWebView2DownloadOperation` COM 引用（连同其内部指针）每标签每文件一个地堆着；
   而 `StopLiveTraffic` 对整张表逐个 `Cancel()`，已结束项必抛、被 `catch` 吞掉，
   于是「取消了几只真在途的」这件事在日志里不可见。
2. 落地：下载生命周期整体外迁成 partial 分片 `HostWebView.Downloads.cs`（216 行），
   里面做三件事——①登记时订阅 `StateChanged`，进终态（`Completed`/`Interrupted`）即
   **退订 + 摘表**；②订阅之后立刻补判一次终态（快文件 + 慢接线的窗口，那种形态不再发事件）；
   ③`CancelInFlightDownloads()` 只对非终态项 `Cancel()`，取消完一律摘表。
   `HostWebView.cs` 531→445 行（基线同批收窄），`StopLiveTraffic` 与 `UnwireEvents`
   各留一次调用——旧的那段自持取消循环被删掉，反向锚就是钉这一点。
3. 保守方向选的是「**读不到状态按非终态处理**」而不是旧的「一律 Cancel 再吞异常」：
   真在途的下载不能被 COM 抖动放过；重复 Cancel 一只已结束的项除了被吞掉的异常没有别的效果。
   与 R9-B33 的「上限判定必须在读取之前」是同一类方向选择。
4. SDK 事实（登记时不知道、写代码时撞上）：本 SDK 的
   `CoreWebView2DownloadOperation` **没有 `Completed` 事件**，只有
   `BytesReceivedChanged` / `EstimatedEndTimeChanged` / `StateChanged`，且事件参数类型是
   `EventHandler<object>`（PowerShell 反射实证，成员表里就这些）。⇒ 终态信号必须走
   `StateChanged` + `State` 判定；`sender` 是唯一回指操作对象的途径（args 里没有）。
5. 测试面（`HostWebViewDownloadTrackingTests`，9 条）分两半：
   终态判定提成 `internal static IsTerminalState(CoreWebView2DownloadState)` 纯函数直测
   （含未知枚举值 999 按非终态——CS-329 同口径，`CoreWebView2DownloadOperation` 是
   internal ctor 的 COM 包装件，单测造不出来）；订阅/退订/摘表/「Add 之后必须紧跟终态补判」/
   「主文件不再自持取消循环」这几条判源码文本。**注入证红做过**：删掉
   `operation.StateChanged -= _onDownloadStateChanged;` 一行 ⇒ 恰好 1 条判红且归因到
   那条锚（其余 8 条不受影响），还原后 9 条全绿。
6. 验证：`dotnet test Aegis.Windows.Core.Tests -r win-x64 -p:RestoreLockedMode=true`
   ⇒ 882 passed / 0 failed；`dotnet build` 0 警告 0 错误；`check_file_sizes`
   随收窄入库；`packages.lock.json` 零改动。
7. 未做：`DownloadItem`（面板侧）对同一 operation 的引用另有其生命周期，
   由 `TrimDownloadItems()` 有界管理，本批不动它——Q24 报的是登记表这一份。

### 3.38 R9-B38（2026-10-13，队列 Q25 的第一半）：计时包装的挂载形态三端合一

1. 修的是「**装在哪里**」而不是「算了什么」：三端的圆整/抖动/钳位逻辑第八轮就齐了
   （`timer_parity.rs` 的 `all_three_ends_share_the_same_clamp_form` 一直在判），
   但 Windows（`FingerprintShield.cs` Stage 8）与 Android（`WebViewHardeningStagesShield.kt`
   Stage 8）把包装用 `Object.defineProperty(performance,'now',{value:…, writable:false,
   configurable:false})` **遮蔽在实例上**，而核心按 RS-216/RS-250 装在 `Performance.prototype`
   并原样保留原生描述符。两个后果都在出货制品里成立：
   `Performance.prototype.now.call(performance)` 一行取到无降噪的 µs 时钟（绕过），
   `hasOwnProperty.call(performance,'now')` 或 `getOwnPropertyDescriptor` 一查即知防护存在
   （检出——冻结描述符本身就是探针）。
2. 落地：两端改成与核心同一形状——先取 `Performance.prototype` 的描述符，取不到才退回实例
   （引擎定义位差异，绝不静默不装），写回时 `writable/enumerable/configurable`
   **全部沿用原生描述符**。C# 侧仍用它那份提前捕获的 `origDefineProp`
   （`:66`，防页面前篡改 `Object.defineProperty`）——「用哪一份 defineProperty」三端仍有分歧，
   这条记在下面第 5 点的续登项里，不在本批顺手统一。
3. **又一条「门禁把缺陷形态钉成期望值」**：`WebViewHardeningScriptTest.kt:390` 断言的正是
   `script.contains("Object.defineProperty(performance, 'now'")`——旧形态被测试钉住了，
   改对的第一现场就是这条用例判红。现改为钉「原型描述符查询 + `defineProperty(tgtPN,…)`」，
   并把「为什么原来那条是错的」写在注释里（R9-RS-6 / R8-PY-02 同族，第四次）。
4. 三端同形判据放哪儿：放 `core/rust-policy-core/tests/timer_parity.rs`（该文件的存在理由
   就是「跨端对账需要同时看到三份源码」），新增两条——
   `all_three_ends_mount_performance_now_on_the_prototype_preserving_the_native_descriptor`
   （六个共用片段 + **负向**：任何一端再出现 `writable: false, configurable: false` 这个
   冻结实例形态即判红）与 `mounting_shape_is_not_satisfied_by_mere_identifier_presence`
   （内存态注入：把「原型」整体换成实例，两个原型片段必须同时消失——否则上面那组
   断言等于在判「文件里有 oPN 三个字」）。**不新开 python 门禁**：
   `verify_injected_js_parity.py` 判的是 7 个共有噪声函数的 token 序列，
   与 Stage 8 挂载点不是同一张面，硬塞进去只会让那把门禁开始判它看不懂的东西。
5. 续登 **Q57 R9-CS-17**（P2，剩余半边）：①六条高解析通道（`mark`/`measure`/`getEntries*`/
   `requestAnimationFrame`/`Event.timeStamp`/`timeOrigin`）两端零包裹，核心全覆盖
   （`timer_prec.rs:170-244` 的 RS-279 一组）——rAF 与 `getEntries*` 的包裹是**站点可观察**
   的行为变更，只能由真机冒烟证明，本批按「不顺手做」处理；②「用哪一份 defineProperty」的
   残余分歧（C# `origDefineProp` vs 核心/Kotlin 直接引用）。
6. 验证：`cargo test --locked --all-features` 全绿（timer_parity 5 条，含本批新增 2 条）；
   `dotnet test Aegis.Windows.Core.Tests` ⇒ 882 passed / 0 failed；
   `./gradlew :app:ktlintCheck :app:detekt :app:testDebugUnitTest` ⇒ BUILD SUCCESSFUL，
   app 面 320 条 0 失败；`check_file_sizes` 绿——三份改动文件都在 300 行红线内
   （`FingerprintShield.cs` 236→256、`WebViewHardeningStagesShield.kt` 202→219、
   `timer_parity.rs` 94→168），而 `WebViewHardeningScriptTest.kt` 是 421 行零余量基线 ⇒
   那处改锚**净零增行**（注释放台账与核心注记里，不在基线文件里挤行数，第 3 点的说明因此
   不在这个文件里）。**未跑真机/桌面冒烟**——本批改的正是
   只能在真 WebView2/System WebView 里观测其行为的注入 JS，验证结论要等那一跑。

### 3.39 R9-B39（2026-10-13，队列 Q53 的第 0 档）：消费面门禁不再被注释喂绿

1. 起因是复查**自己写的这张表**：Q53 登记时把 `native-navigation-decision.json` 写成
   「已有 C# 消费者 `BrowserPolicyBrokerNativeGateTests.cs`，可作为接法模板」，并据此在
   `CONSUMER_MANIFEST` 里记了 `{"CS","RS"}`。逐行回读该文件：唯一的命中是 `:260` 的一句注释
   （`// 公网 https + 已注册会话 ⇒ 核心判 allow（native-navigation-decision 向量同口径）`），
   断言里的期望值是手写的，**没有任何代码打开那份向量**。「这端跑过」这句话的来源于是文档式
   自我声明——而覆盖面正是靠这句话立起来的，所以这不是措辞问题，是判据问题。
2. 落地＝命中口径改成**剔注释后再匹配**（`scripts/verify_vector_consumers.py` 新增
   `strip_comments()` 并接进 `scan_surface()`），四种形态各覆盖：C 系块注释、行注释、
   块注释续行的对齐星号、`#` 注释（`.py`/`.yml`）。登记表随之把该份改回 `frozenset({"RS"})`，
   并在原行写明「Windows 侧真接一份执行者是 §五 Q53 的第②档，本批不顺手补」。
3. **实测 delta 只有这一份**：同一次扫描跑「剔注释前 / 后」两遍，21 份向量里 1 份端集变化、
   20 份不变（变化的正是 `native-navigation-decision`：注释命中共 4 个文件——3 份 Rust 注记 +
   1 份 C# 注记——全被剔掉后剩下的唯一真实消费者是 `vectors_decision.rs`，端集由 `CS,RS` 回落到 `RS`）。
   这一步必须做：如果剔注释一次改掉六七份的端集，说明整张表是注记堆出来的，要整体重登记
   而不是改一行。
4. 反向锚 `tests/python/vector_consumers_test.py::test_comment_only_citation_is_not_a_consumer`：
   五条注释语料（把上面四种形态分布在 C#/Kotlin/Rust/python/mjs 五个文件上）逐一断言
   「文件名在原文里 → 剔完不在 → 不算消费者」，再加一条**正面控制**
   （同一文件名写进代码行必须算命中）。没有那条正面控制，前面五断言全部恒真——等于用
   「注释被删光了」证明「注释不算消费」，正是 R9-SH-7 / `gate_hollowness_test` 判的那类假绿。
5. 顺带把那句失实的「可作为接法模板」在两处改成事实——§五 Q53（原位标注由谁推翻，并把
   登记时的 15 份同步成现在的 21 份、①档零端侧执行者由四份增至八份）与 §3.25 第 2 点的
   「`native-navigation-decision` 到 CS+RS」。**这句话在台账里出现在两处**（§3.25 第 2 点与
   §五 Q53；§二 AEG-006 行只写了聚合计数、没点名这份向量的 CS，所以不用改）。历史记录保留
   当时的措辞，但必须当场写明它已被推翻——否则后来人按 §3.25 读一遍就会以为 Windows 真跑过
   它。本批定位是「第 0 档：先把『消费』这个
   词判干净」——三档缺口一条没动，只是缺口数现在可信。
6. 验证：`python scripts/verify_vector_consumers.py` ⇒ **EXIT 0**（21 份 / 563 个受管源文件）；
   `pytest tests/python` ⇒ 629 passed / 1 skipped（本批 +1）；`ruff check` 干净；
   `check_file_sizes` 绿（该门禁 264 行、用例 270 行，均在基线内）。

### 3.40 R9-B40（2026-10-13，队列 Q5 + Q7）：Android 账本回收与 closeTab 注释归位

1. **Q5 R9-AD-5 是「出货配置里才成立」的那一类**：账本有两条写入路径——托管路径的 nonce
   由 `AndroidBroker.newNonce` 生成为 `sessionId:token`，原生路径的 nonce 是 Rust 核心发的
   64 位裸 hex（`NativePolicyCoreBridge` 原样取 `nonce` 字段，无前缀）。回收侧
   `destroySession:189` 按 `startsWith("$sessionId:")` 摘 ⇒ 原生条目**一条也摘不掉**，而
   `:180` 的 KDoc 写着「销毁会话并移除其已消费 nonce」。默认构建（`REQUIRE_NATIVE_POLICY_CORE=false`）
   走托管路径，所以 JVM 用例全绿看不出；置位变体正是发布 APK 的形态（`release-android.yml`
   传 `-PrequireNativePolicyCore=true`，这件事由 `NativeGateWiringAnchorTest.kt`（R8-AD-09）
   钉成常驻断言）。后果不是重放被打开（裸 nonce
   留在册只会更拒），而是账本被死会话条目长期挤占 `MAX_CONSUMED_NONCES=50_000` 的 FIFO 名额，
   且那句 KDoc 是失实声明。
2. 修法与 Windows 侧同源：`BrowserPolicyBroker.NativeNonceLedger.cs` 的
   `NativeNonceLedgerKey(sessionId, nonce)`（R8-CS-REG-01，那条「满额后全站导航永久锁死」的
   自 DoS 换来的教训是**把键推导抽成纯函数**，这样不需要原生库/真桥就能在常跑门禁里断言——
   「文本锚证明不了数学」）。新增 `android/broker/src/main/kotlin/com/aegis/broker/NonceLedger.kt`：
   `nonceLedgerPrefix` / `nonceLedgerKey`（幂等：托管形态已带前缀，不叠第二层）/
   `String.belongsToNonceLedger`，写入与回收共用同一个前缀约定，两侧不可能再各抄一份。
   `AndroidBroker.kt` 两个消费点改 `trackConsumedNonce(nonceLedgerKey(sessionId, …nonce))`，
   回收点改 `removeIf { nonce -> nonce.belongsToNonceLedger(sessionId) }`，
   `trackConsumedNonce(nonce)` → `trackConsumedNonce(ledgerKey)`（参数名字说出它收的是键）。
3. **零余量文件的净零增行**：`AndroidBroker.kt` 基线 447＝实 447，所以本批全部改动是**同行替换**
   （含把 `consumedNonces` 从 `private` 改 `internal` 作为常驻用例的读回缝，理由写在
   `NonceLedger.kt` 的头注里而不是行内注释里）。第四处撞到的是 ktlint 而不是行数：
   两个参数的单行签名被判三处 `function-signature` 违规（要求逐行断参），而按同一正则扫
   四个 main 源集，**改之前的实树里这种形态是零处**——所以这不是我的写法偏好，是门禁口径；
   另 `multiline-expression-wrapping`
   要求 `val x = File(\n…)` 这种多行表达式整体另起一行——两处都按门禁口径改形，不改语义。
4. 用例 5 条 `ConsumedNonceLedgerTest.kt`（新文件 93 行）：
   ①原生形态键经 `destroySession` 真实现被摘掉（写入侧用生产键函数，回收侧是真代码）；
   ②**反向锚**：把裸 nonce（旧形态）直接入账 ⇒ `destroySession` 后仍在册——这条为真才说明
   ①判的确实是键形态，不是恒绿；③托管 nonce 折算幂等（不叠前缀）＋原生裸 hex 折算得
   `sessionId:hex`；④前缀含冒号 ⇒ 销毁 `s1` 不得顺手摘掉 `s12` 的同名条目（跨会话错清是
   另一种失配）；⑤接线锚：`trackConsumedNonce(nonceLedgerKey(` 恰好 2 处、回收点用
   `belongsToNonceLedger`、且旧的字面前缀拆判据不得回潮。
   局限如实写明：原生分支的**端到端**消费在 JVM 里到不了（要真实 `.so`），
   与 Windows 侧 `AEGIS_NATIVE_POLICY_CORE_TEST_PATH` 那条限制同型，所以用「纯函数＋接线锚」
   而不是假称跑过真桥。
5. **Q7 R9-AD-7 是注释错位而不是行为错位**：`TabManager.closeTab:109-130` 三条 when 分支的
   行内注释整体错了一位——「后方后台标签：激活位不变」贴在 `index < activeIndex`（它会移激活位）
   上面，「前方移除：激活标签左移一位」贴在 `else`（关闭激活标签本身）上面，而第一条分支
   `index > activeIndex` 裸着。类 KDoc（AD-254 段，`:95-100`）的三条对应是**对的**，
   所以按注释读会读出与实现和 KDoc 都相反的语义。三条分支的行为早已有用例钉住
   （`TabManagerTest.kt:359` 关后方、`:380` 关前方、`:434` 关激活本身），本批只把注释挪回
   各自分支（+1 −1 行＝净零），行为零改动。
6. 验证：`./gradlew :broker:ktlintCheck :broker:detekt :broker:testDebugUnitTest` ⇒ BUILD SUCCESSFUL
   （broker 面 84 条 0 失败，含本批新增 5 条）；`:app:ktlintCheck :app:detekt :app:testDebugUnitTest`
   同批跑（app 面 320 条）；`check_file_sizes` 绿（`AndroidBroker.kt` 仍 447＝基线，
   `TabManager.kt` 仍 260）。**未跑真机**——原生分支的行为面只能由装机的置位 APK 证明，
   那一跑仍列在待裁决清单里。

### 3.41 R9-B41（2026-10-13，队列 Q39–Q46 的剩余六条 DOC-10..15）：文档不再抄「实树自己会说的话」

共同形状：这六条都不是「写错了个数字」，而是**把某个单源的值又抄了一遍到散文里**——
抄的那一份从此没人判，实树变了它也不会红。R9-DOC-16（wrapper 版本抄进注释）已经是同一课，
所以本批的统一动作是「改指向单源」而不是「再抄一遍新值」。

1. **R9-DOC-10 五门禁**：README 写「五门禁（validate_release / verify_versions / bridge_guard /
   contract_compatibility / cross_end_lists）常绿」，而 `contracts.yml` 的
   `contract-source-of-truth` job 实测 **30 个步骤**（py-yaml 现读；其中 27 步调 python、
   18 步是 `check_*`/`verify_*` 门禁——登记时写的是「约 17 个步骤」，那个数本身也是估错的，
   正说明不该把它抄进文档），CLAUDE.md 列的是第三个子集
   ⇒ 任何新挂门禁（#131 的表形门禁就是当时撞上来的）在文档面上隐形。改法：README/CLAUDE/
   `docs/security-testing-guide.md`（横幅里也写着「五门禁」）三处一起改成
   **「判定面单源＝那个 job 有哪些步骤」**，并明确 CLAUDE 的清单只是本地能跑的子集。
   刻意**不写新的步骤数**——那是同一个会被抄坏的值。
2. **R9-DOC-15 测试计数**：README 的「cargo 450+ / dotnet 650+ / gradle JVM 280+ / pytest 230+ /
   node 80+」与 2026-10-13 现读（`#[test]` 605、`[Fact]` 508＋`[InlineData]` 474、JVM `@Test` 450
   ＝app 320/broker 84/webview-adapter 46、`pytest --collect-only` `tests/python` 630＋
   `agent/tests` 81、UI 回归 126）**双向失真**，且这些数
   一个门禁都没判过（`check_doc_claims.py` 只判 `N workflow` 形态）。改法：README 不再抄总数，
   只保留**机器判定的下界**——`assert_test_counts.py`（dotnet Core ≥700 / Broker ≥160）与
   `verify_vectors.py`（向量 ≥21 份 / 条目 ≥222），其余写「看 CI 日志现算」；
   SP-198 那条「pytest 230+ 是合计口径」的解释随基数一起撤掉，只留「CHANGELOG 里的
   "pytest 30" 是 agent 红队单列口径」这层仍然需要的关系。
3. **R9-DOC-11 credential_guard**：`privacy-defaults.md` 的凭证行把 `credential_guard`
   （OS keystore/DPAPI）当成正典能力写，而该模块只在 `legacy/windows-pywebview/app/` 存在，
   正典全树 `CredentialGuard`/`ProtectedData`/`DPAPI`/`KeyStore` **实测 0 命中**；同文件 :12
   已经诚实写了「DPAPI/Keystore 静态加密未落地」——是同一张表里两行互相打脸。改成
   「这一行的保证只来自密码/令牌本就不落盘 + OS 沙箱，不来自任何凭据保护模块」。
4. **R9-DOC-12 android/README 的强制控制清单**：原来一句话把已落地项与未落地项并列写成
   「发布前强制控制」，而本节自己禁止的正是「用清单代替实现」。按实树拆两栏——
   已落地：`DownloadPolicy`、权限默认拒绝（`BrowserEngine.kt:97` 无条件 `request.deny()`，
   顺手把「权限请求 UI」这个说法改准：它是**拒绝而不是弹窗授权**）、崩溃诊断
   （`AegisApplication` 的 `setDefaultUncaughtExceptionHandler`）、签名发布流程；
   未落地：Room 历史/书签（`androidx.room` 与 `bookmark` 在 android 全树各 0 命中，
   `HistoryAction` 只是 WebView 的 BACK/FORWARD/RELOAD）、Keystore 存储（0 命中）、
   同步协议（`supported-features.md` 的「明确不做」已列云端同步密码）、无痕清理（A-03，
   前一轮就注明了）。
5. **R9-DOC-13 CONTRIBUTING 的「master 受保护、禁止直接推送」**：登记时的依据是第八轮实测
   `enforce_admins=false`；本批**重新现读**服务端（设置会变，不能引用几年前的实测）——
   ruleset `R6-master-no-rewrite` active，rules 只有 `{deletion, non_fast_forward}`，
   `bypass_actors` 是 Administrator＋Maintain 两个角色 `bypass_mode=always`（本账号
   `current_user_can_bypass=always`）；经典保护挂了 **9 个必需状态检查**（
   `contract-source-of-truth`/`rust-conformance`/`windows-contract-build`/
   `android-contract-build`/`UI Regression (start.html)`/`cargo-gate`/`ktlint + detekt 质量门禁`/
   `audit`/`redteam`，`strict=false`），但响应里**没有 `required_pull_request_reviews`**，
   `enforce_admins.enabled=false`，且 `git log --first-parent --no-merges master` 里
   `d898677`、`3243397` 两次直推还在。⇒ 文档改成「服务端真正强制的只有不许删分支/不许改写历史，
   经 PR + Actions 全绿是**流程纪律**」，并把「给 master 加对管理员也生效的 PR 要求」明确留在
   §四 待裁决（**这是仓库设置变更，本批只改文档不动设置**）。
6. **R9-DOC-14 parity 清单的「本清单 100%」**：同文件 `:24` 就是 ☐ 未实现
   （`NewBrowserVersionAvailable`——本批复测仍是 0 订阅、无 `RuntimeUpdater.cs`），
   末行 M4 真机验收也是 ☐。第八轮 §十三 改了 CLAUDE/README/supported-features 三处，
   漏了清单自己这一行。改成「本清单的**终局口径**勾验，未勾的两项＝`:24` 与 M4 真机验收」。
7. 为什么这六条值得单独一批：它们是**唯一一类「永远不会自己变红」的缺陷**——代码错了用例
   会红，文档抄错了没有任何东西会红，所以只能靠「不抄」来消除失效面。本批改的是两类聚合
   计数（测试规模、门禁清单）；README 里其余的数字各有归属：`16 个 workflow` 与它的分层
   分解由 `check_doc_claims.py` 现算对账（本批复测触发面逐 workflow 列出后 7+2+3+4=16 仍成立），
   `13 个冻结导出符号`/`6 项有副作用操作`是机制描述而非进度数字，第 138–153 行那些轮次计数
   带 ISO 日期＝历史陈述（门禁按 `chain_dated` 豁免）。**没有把「所有文档数字」都判成门禁面**
   ——那需要一个会随每批漂移的真值源，代价大于收益。
8. 验证：`check_markdown_tables` / `check_markdown_links` / `check_doc_claims` 三道 EXIT 0；
   `pytest tests/python` 629 passed / 1 skipped（本批零代码改动）；`check_file_sizes` 绿
   （`.md` 不在扫描面）；所有新增断言逐条给出现读命令（`gh api`、`grep -c`、py-yaml 数步骤），
   不复用上轮台账的数字。

### 3.42 R9-B42（2026-10-13，Q53 第②档的可执行性核查）：登记一条「加测试文件闭不掉」的结构性障碍

1. 起因是 R9-B39 之后那条最自然的下一步假设：`native-navigation-decision.json` 既然被记回
   `{"RS"}`，那就「给 Windows 接一份真执行者」——加个 C# 用例读向量逐条断言即可。本批按
   真实调用方语义核这条路能不能走通（结论：**不能**，且照做会得到一个比现状更假的登记）。
2. 向量现读（`contracts/vectors/native-navigation-decision.json`，43 条）：
   `expected_evaluate` ＝ allow 23 / **require_confirmation 13** / deny 7；另有 `deny_hosts` 9 条、
   `expected_replay_code` 7 条、`advance_generation` 1 条、`destroy_session` 1 条。
3. **两端在常跑（托管）配置下都产不出 `require_confirmation`**，逐行实证：
   - Windows：`Broker/BrowserPolicyBroker.cs:204` 的 `EvaluateNavigation` 托管分支只可能
     `Decision.Allow` 或 `Decision.Deny`；确认面在 `:272` 的 `RequestNavigationConfirmation`，
     而它 `:286` 写死 `if (!_nativePolicyCoreRequired || _nativePolicyCoreBridge is null)
     return NativeBridgeDenied(scope, "native_confirmation_core_required")`——托管模式**直接拒**。
     全仓 `new Decision.RequireConfirmation` 只有一处生产者：`NativePolicyCoreBridge.cs:324`
     （解析核心返回的 `"require_confirmation"`）。
   - Android：`AndroidBroker.kt:194` 的 `evaluateNavigation` 托管分支同样只 Allow/Deny；
     `:254` 的 `requestNavigationConfirmation` 在非原生构建走 `:284` 的 `else -> evaluateNavigation(...)`
     （注释写明是为了「默认产物不再每次导航都被拒」），`Decision.RequireConfirmation` 的唯一
     生产者是 `NativePolicyCoreBridge.kt:314`。
4. 所以第②档只有两种诚实形状，代价都**不是测试**：
   ①让平台用例真的跑原生核心——Windows 要 `AEGIS_NATIVE_POLICY_CORE_TEST_PATH`、Android 要
   置位变体 + 真实 `.so`，而这两者都**不是 PR 的必需检查**（`native-policy-artifacts.yml` 是
   master push + paths 过滤，`release-*.yml` 是发布）。接上之后合并门禁里那张面仍零执行，
   而 `CONSUMER_MANIFEST` 会把它读成「CS/AD 已覆盖」⇒ **登记表从「没人跑」升级成「有人跑但
   PR 不看」**，正是 R8-CS-CORE-2 记过的盲区形态；
   ②给向量加一个显式分区字段（如每条 `platform_decidable`），门禁判「两端各自执行且**只**执行
   被标记的子集，13 条 `require_confirmation` 由核心面独占」——这是**冻结契约面的词表变更**，
   与 Q21 R9-SH-11（两份原生向量信封字段本就不一致）是同一次定稿，不能由修 bug 的批次顺手做。
5. 处置：本批**不动代码**，把上面两种形状升入 §四 待用户定稿；§五 Q53 的②档文字同步改准
   （原写「只有 Rust 执行 ⇒ 未被验证」属实，但没写**为什么不能顺手补**，后来人会把这行读成
   「补个 C# 测试就行」——那才是这批要防的错）。
6. 这一条的价值判定：它不是「发现了个问题」，而是**否证了一个看起来最合理的修法**。
   核查成本是一次读两端 `evaluateNavigation` + 两次 `grep RequireConfirmation`，
   而照原假设动手会写出 43 条里 13 条永远断不真的用例，还要连带改登记表。

### 3.43 R9-B43（2026-10-13，队列 Q3）：下载重定向落点的完成后复判

1. 洞的形状（回读确证，与登记时一致）：`WebViewDownloadHandler.kt:107` 的形态闸门判的是
   **入队那个 URL**，而真正把字节写进公共下载目录的是**另一个进程**的系统 DownloadProvider，
   它默认跟随重定向（全树零 `setRedirectsAllowed`）⇒ `https://ok.example/a` 一发 302 指到
   `http://169.254.169.254/...`，闸门从未看到落点。这就是 PR #130（R8-AD-03）消过的后果
   换了个入口复活——导航层被 broker 拒、子资源层被 NSC 挡的形态，下载层照旧放行。
2. 处方按登记口径二选一，这里取**登记推荐的**那条：`setRedirectsAllowed(false)` 会打断
   一切正当 CDN 重定向（产品代价，登记时已标「不推荐」），所以做「完成后复判 + 撤销 + 留痕」。
   复判的输入来自 `COLUMN_URI`——AOSP `AbstractDownloadThread.redirect()` 会把这一列改写成
   跳转目标，因此完成后查它就拿得到了闸门本该看到的地址。**这条依赖没有设备实证**（见第 6 点）。
3. 新增三处，**判据一份都没多写**：
   - `WebViewDownloadCompletionGuard.kt`：`verdict(finalUrl, finalScheme)` 直接调
     `WebViewDownloadTargetGuard.rejectionOf`（同一段表、同一个 `reserved_address` 码、同一条
     「本机与内网必须能打开」上界）；`rowVerdict(status, url, scheme)` 把「只复判
     STATUS_SUCCESSFUL 的行」这条顺序判据也放进纯函数——状态判在地址判之前，否则一条
     没成功的记录也会弹「已拦截指向保留地址的下载」，那是与实际不符的话。
   - `WebViewDownloadCompletionReceiver.kt`：读行 → 判 → `manager.remove(id)` → 留痕 + Toast。
     **撤销失败单独记 error 级日志**（「文件仍在公共目录，需人工删除」）——那种输入下
     Toast 说「已拦截」就是假话，不能只报喜。
   - `AndroidManifest.xml`：`<receiver ... android:exported="false">` + `DOWNLOAD_COMPLETE`。
     为什么 exported 必须 false：这条广播由系统按归属定投，false 收得到；true 等于把
     「任意应用伪造一个 download_id 让本 app 删自己的文件」开放出去——**这条判断写进了
     用例**（`receiverIsDeclaredAndNotExported` 解析 DOM 断言），不是注释里说说。
4. 「读不到就删」被明确否掉：`verdict(null/"")` 返回 null ⇒ 不撤销——判据没有输入时把
   不可逆动作做掉，等于把平台抖动转嫁成用户的文件损失。**但「畸形 URI」不在豁免之列**：
   URI 读到了而 scheme 取不出时照旧按闸门口径拦（入队侧对同样的输入就判「非 http(s) 拦」，
   复判在这里改成放行就是第二套口径，而「落点看不出问题就先留着」等于把拦不住说成已处理）
   ——这条方向差别单独写成用例 `schemelessLandingIsNotExempted`，免得后来人把两个
   「读不到」当成同一件事合并掉。
5. 用例 9 条 `WebViewDownloadCompletionGuardTest.kt`：元数据落点被撤（断言留痕含
   `DENY_CODE`）、**B8 裁决的对偶锚**（`127.0.0.1` / `192.168.1.10` / `localhost` /
   阿里云 `100.100.100.200` 照旧不撤）、复判与入队闸门在 6 条 URL 上**逐字同判**
   （这条就是「不许有第二个判据源」的判据）、无从判断的行保留文件、状态优先、
   `DOWNLOAD_STATUS_SUCCESSFUL == DownloadManager.STATUS_SUCCESSFUL`（那条常量不是手抄魔数，
   有等式锚）、manifest DOM 断言、以及一条**全 app 源面扫描**：`rejectionOf(` 的出处
   只能有两个文件（闸门自身 + 完成复判），第三处出现即红——这正是本次新增判据时
   最容易长出的东西。
6. **诚实边界（本批最该记住的一条）**：JVM 侧能验的是判据与接线形态，验不了的是
   ①广播是否真投递到 `exported=false` 的 manifest receiver，②`COLUMN_URI` 在本机 ROM 上
   是否真等于跳转后的地址，③`remove()` 是否真把公共目录里那个文件删掉。这三条任一不成立，
   防护就是纸面能力——所以验收步写进 `docs/runbooks/device-validation.md` **Android 第 8 步**
   （含怎么造这个 302），并同步把 `windows-run-guide.md:92` 那句「Android 清单（7 项……）」
   改成 8 项与实名（R9-DOC-08 同一口径：文档数量与名称必须对上实树）。
7. **同型缺口另登 Q58（Windows）**：`HostWebView.Downloads.cs:48` 判的也是
   `DownloadOperation.Uri`（入队地址），R9-B37 加的 `StateChanged` 只做引用回收、不复判落点
   ⇒ 同型缺口在正典 Windows 制品上仍在。**不照抄 Android 的原因写清**：Android 靠的是
   DownloadProvider 会改写 `COLUMN_URI`，而本批反射复测 `CoreWebView2DownloadOperation`
   只能给出**名字**——属性面 EstimatedEndTime / TotalBytesToReceive / **Uri** / ContentDisposition /
   MimeType / BytesReceived / **ResultFilePath** / State / InterruptReason / CanResume，
   事件面仍只有三个（与 R9-B37 一致）；有 `Uri` 这个属性不等于它在跟随重定向后报的是
   跳转后的地址。第一步必须是拿真机/桌面实测那条属性的语义，否则改动的错法是「以为拦住了」
   （登记在 §五 Q58，需设备授权）。
8. 验证：`./gradlew :app:ktlintCheck :app:detekt :app:testDebugUnitTest` ⇒ BUILD SUCCESSFUL，
   app 面 **329 条 0 失败**（320 + 本批 9）。四轮 ktlint/detekt 返工的形态都进了用例注释：
   限定名接收者的链必须逐环断行（`android.net.Uri.parse(url).scheme` 那种写法在本仓必须
   拆成 `.parse(url)` / `.scheme` / `?.lowercase()` 三行）、`ReturnCount ≤2`（入口守卫合并成
   一个 `completedDownloadId()`）、`Path.readText()` 在本仓 stdlib 里不存在（要 `.toFile().readText()`）、
   `getElementsByTagName("action")` 在 manifest 上会连 activity 的 action 一起数（要限定到
   receiver 子树）。`check_file_sizes` 绿：`WebViewDownloadHandler.kt` 仍 346＝基线（本批没动它），
   新主文件 61 / 132 行、用例 186 行。

### 3.44 R9-B44（2026-10-13，R9-B39 的同一条课推到端侧用例）：按文本判源码的用例必须先剔注释

1. 触发方式是**回扫自己这几批的落地件**，不是新漏洞：R9-B39 刚把
   `verify_vector_consumers.py` 的命中口径改成「注释不算消费」，理由写得很清楚——注记里
   逐字抄着被禁形态是本仓的传统（`InstalledBuildMarkerTests`、`ReservedAddressBoundaryTests`
   这些文件的断言消息里就原文写着历史写法）。而**端侧那批源码文本锚用例没跟着改**：
   今天刚写的 `ConsumedNonceLedgerTest` 与 `WebViewDownloadCompletionGuardTest` 就是
   `source.readText().contains("...")` ——同一把尺子只磨了门禁那一头。
2. 两个方向的失败都会发生，且方向相反：
   - **假绿**：把 `trackConsumedNonce(nonceLedgerKey(` 从代码里删掉、只在注记里留一句
     「已改为 trackConsumedNonce(nonceLedgerKey(...)）」⇒ 接线锚仍然全绿；
   - **假红**：反过来，任何一句解释性注记提到被禁形态（`nonce.startsWith("$sessionId:")`
     这种），「不得回潮」的反向锚就判红——而为了让它变绿最容易被做的是**删注记**，
     于是丢掉的正是防止回归的那段上下文。
3. 落地：
   - 新增 `withoutComments()`（`:broker` 与 `:app` 测试源集各一份，四种注释形态与
     `verify_vector_consumers.py:strip_comments` 同口径）；跨模块共享要动 Gradle 的
     `testFixtures`（构建面变更），本批不做，改成——
   - 新增 `SourceTextAnchorSupportTest`（两模块各一份，**除 package 行外逐字相同**）：
     同一组语料、同一批期望，含 ①代码行必须存活 ②四种注释形态必须剔净
     ③每条语料的「原文里确实含 token」恒真防呆 ④「剔完不是把整段清空」的正面控制。
     两副本一旦各漂各的，同一份语料就会在两个模块给出不同答案，而期望值是写死的。
   - 把本批新写的三处锚改用 `withoutComments()`（账本写入点、receiver 接线、
     `rejectionOf(` 出处扫描）。
4. **清点把本批真正的发现翻出来了**（我第一版的数字是错的，纠正如下）：「剔注释再匹配」这条纪律
   在本仓不是有没有的问题，而是**散了 14 份、三种覆盖等级**——
   - 具名 9 份：`scripts/verify_vector_consumers.py:126 strip_comments`（四形态）、
     `scripts/verify_core_unwired_modules.py:66 strip_comments`（**只切 `//` 到行尾**，
     因此会连字符串里的 `https://` 一起吃掉＝过剔）、
     `contracts/codegen/injected_js_text.py:98 strip_comments`、
     C# 的 `CodeOnly()` 四份（`HostWebViewWiringOrderTests.cs:47`、
     `CoreReadyFailClosedTests.cs:199`、`SubresourceDenialDeliveryTests.cs:164`、
     `SubresourceFailClosedTests.cs:209`）与 `OutOfBandFetchDisciplineTests.cs:37 StripLineComments`、
     Kotlin `DocumentStartInjectionRegressionTest.kt:49 codeOnly`；
   - 无具名的内联过滤 ≥5 份：`WebViewPipelineTests.cs:268`、
     `NativePolicyCoreBridgeLeaseTests.cs:80`、`NativePolicyCoreBuildRequirementTests.cs:72,140`、
     `InPrivateCoreReadyWiringTests.cs:46`（都是就地一句
     `Where(line => !line.TrimStart().StartsWith("//"))`）；
   - 加上本批新写的 `withoutComments`（`:broker`/`:app` 各一份）。
   **我第一版按 helper 名 grep 得出「22 个未剔」——错**：内联过滤没有名字数不到，
   而按 `//` grep 会把断言里的字符串本身算进来。「连清点都做不准」就是这条纪律的真实状态。
5. 三种覆盖等级并存的实际后果，本批实测两处：`WebViewPipelineTests.cs:271` 的
   `DoesNotContain("e.Cancel = !TryAuthorizeNavigation")` 与
   `SubresourceDenialDeliveryTests.cs:150` 的 `DoesNotContain("SecurityLog")`——被禁形态
   **就原文写在源码注记里**（`HostWebView.cs:104` 的 R8-CS-SEC-02 历史说明、
   `BookmarkManagerWindow.xaml.cs` 里的 SecurityLog 说明），这两条锚今天不判红
   **全靠作者顺手写的那段内联 `//` 过滤**。差一次重构（把过滤挪走、或下一个人写锚时没抄这段），
   套件就会因为一句解释性注记红在不该红的地方。而内联过滤与 `CodeOnly` 都**不处理块注释与
   ` * ` 续行**——那条路径今天没有护栏；反过来 `verify_core_unwired_modules.py` 切到行尾，
   过剔字符串。同一件事在仓里有「太窄」和「太宽」两种错法，正是没有单一出处的症状。
6. **没有做的部分及为什么**：把 14 份一次收成每语言一份。①C# 侧跨 `Core.Tests`/`Broker.Tests`
   两个程序集，共享要动工程引用（构建面变更）；②**过剔是真的风险**：正则不认识字符串边界，
   判「内嵌 JS 文本」的锚（`WebViewHardeningScriptTest`、`injected_js_text.py` 的输入面）里
   JS 自己的 `//` 会被当源码注释删掉，判据反而变形。所以登记成 §五 **Q59**，验收判据写成
   可复核的形态：**每种语言只剩一个 helper、内联过滤 0 处**，并且把「切到行尾」这一支的
   过剔行为要么修掉要么写明；不写「全都换掉」。
7. 验证：`:broker` 与 `:app` 的 ktlintCheck + detekt + testDebugUnitTest 全绿
   （broker 87 条 / app 332 条，0 失败，较上批各 +3 条语料用例）。写锚时又撞两次
   ktlint/detekt 互斥窗口（`multiline-expression-wrapping` 要求多行表达式整体另起行；
   表达式体单行落进 121..140 就被两把尺子互相打不到 ⇒ 块体两句），都按已有形状改形。

### 3.45 R9-B45（2026-10-13，队列 Q59 = R9-SH-17）：把「剔注释」收成每语言一份——收敛本身撞出三条口径缺陷

1. 落地范围与形状（验收判据是 §3.44 第 6 点写下的「每语言只剩一个 helper、内联过滤 0 处、
   『切到行尾』那一支要么修掉要么写明」，没有写成「全都换掉」）：
   - **Python 单源** `scripts/text_anchors.py:strip_comments(text, path)`，
     `verify_vector_consumers.py` 与 `verify_core_unwired_modules.py` 各删掉自己那份改成引用它
     （跨脚本 import 沿用 `scripts/sync_versions.py:11` 的 `sys.path.insert(parent)` 既有形状）。
     后者原来那支「`//` 切到行尾」＝**过剔**（字符串里的 `https://` 会连后半行一起吃掉）就地消失。
   - **C# 单源** `windows/tests/Aegis.Windows.TestSupport/SourceTextAnchors.cs`，
     两个测试工程用 `<Compile Include="..\Aegis.Windows.TestSupport\SourceTextAnchors.cs" Link=…>`
     **链接同一份源文件**——不新建 TestSupport 工程：那要动工程引用、`packages.lock.json`
     与发现数下局面（构建面），而链接源码零这些代价。原 9 处（4 份 `CodeOnly`、
     1 份 `StripLineComments`、4 处内联 `Where(line => !line.TrimStart().StartsWith("//"…))`）
     全部改成引用。
   - **Kotlin** 三份就地过滤（`DocumentStartInjectionRegressionTest.kt:49`、
     `DownloadConfirmationOwnershipTest.kt:164`、`PercentEncodingTest.kt:84`）改接
     `withoutComments()`；`:app`/`:broker` 两份副本保留（Gradle testFixtures 属构建面），
     由 `SourceTextAnchorSupportTest` 的同一组语料自证同形。
   - **常驻门禁** `scripts/verify_text_anchor_helpers.py`（判据面只收「门禁脚本 + 各语言测试目录」，
     不收主源码与 vendor——那里 `//` 字面量是产品逻辑）+ `tests/python/text_anchor_helpers_test.py`
     12 条，全部内存态注入证伪；接进 `contracts.yml` 既有 job（不新增必需 context，R8-CI-01 教训）。
2. **清点第三次纠正**（现读命令，不是改口）：收敛前不是 14 份，是 **15 个文件各自实现**——
   C# 9、Kotlin 3、Python 3（`git grep -c -F 'TrimStart().StartsWith("//", StringComparison.Ordinal)' HEAD -- windows/tests`
   给 8，加 `OutOfBandFetchDisciplineTests.cs:37` 的 `trimmed.StartsWith` 变体＝9；
   `git grep -c -F 'startsWith("//")' HEAD -- android/app/src/test android/broker/src/test` 给 3；
   `git grep -n -F 'def strip_comments' HEAD -- scripts contracts` 给 3）。
   §3.44 漏的正是**按 helper 名数不到**的那两类：`filterNot { it.trimStart().startsWith("//") }` 与
   `.map { it.trim() }.filterNot { … }`。同一批新写的 `withoutComments()` 两份是**有意的跨模块副本**。
3. 撞出来的第一条真缺陷：**`#` 整行只对哈希注释语言成立**。把 Python/YAML 那支 `^\s*#` 无差别
   套到 Rust 上，`#[unsafe(no_mangle)]` 这类**属性行**会被当注释删掉。实测症状：
   `tests/python/core_unwired_modules_test.py::test_export_inside_an_unwired_module_is_red`
   由**红变绿**（注入的 Rust 导出属性被删掉 ⇒ 「接入层长出导出＝接线即红」判据当场失效）。
   修法＝`strip_comments` 收 `path`，`#` 形态只在 `_HASH_COMMENT_SUFFIXES`（.py/.pyi/.yml/.yaml/
   .toml/.sh/.bash/.cfg/.conf）里生效；C# 那份从一开始就不剔 `#`（`#if`/`#region` 是预处理指令）。
   用例 `test_hash_rule_is_scoped_to_hash_comment_languages` 钉住两侧。
4. 撞出来的第二条真缺陷：**顺序也是口径——整行注释必须先剔，再做块注释匹配**。
   `WebViewHardening.kt:41` 的说明里写着 `"https://*"`，其中第二个 `/` 紧跟 `*` 构成一个**假块起点**，
   先做块匹配就一路吃到下一个 `*/`，把中间第 46 行的真语句删掉。实测症状：端侧正面控制
   `DocumentStartInjectionRegressionTest.kt:72`（`val allowedOrigins = setOf(` 必须在语料里）当场判红。
   三份口径统一成 `//` → `#`（按语言）→ 块 → ` * ` 四步，并各加一条**顺序语料**（Kotlin
   `lineCommentHoldingAFakeBlockOpenDoesNotEatFollowingCode`、C# 同名 Fact、Python
   `test_line_comment_holding_a_fake_block_open_does_not_eat_code`）。星号续行必须排在块匹配**之后**：
   先剔它会删掉块的收尾 `*/`，让剩下的块开头去配后面的另一个收尾——同一种错的另一个方向。
5. 撞出来的第三条：**docstring 是字符串不是注释**。我在 `text_anchors.py` 的模块 docstring 里逐字写了
   `native-navigation-decision.json`，`verify_vector_consumers.py` 立刻报
   「消费面漂移 登记=[RS] → 实测=[PY, RS]」——**说明文字自己冒充了消费者**。这不是门禁错，
   是「注记里逐字抄被观察对象」这条本仓传统在 Python 侧没有注释可藏。处理＝prose 改成
   「那份原生决策向量」，并把这条写进单源文件的 docstring 头部（后来者在这里撞一次就够了）。
6. 收敛前后**端集零漂移**的可复核证明：新旧两种顺序在同一扫描面上对比跑一遍，
   21 份向量的实测端集**一份都没变**（`collect_consumers` 双跑求差＝0 份；文本差异只落在
   被吞/不吞的行上）。这条是必要的：否则「收敛口径」与「改动覆盖面」混成一团，
   下一个人无法判断登记表动没动。
7. 顺手改真的文档失实（登记为 **R9-DOC-17**）：`docs/runbooks/device-validation.md:19` 说
   Windows 下载入口是 `WebView/HostWebView.cs:268`，而 R9-B37 把下载生命周期外迁成 partial 之后
   `:268` 已经在 `Dispose()` 里面（现读：订阅在 `HostWebView.cs:158`，判定本体在
   `HostWebView.Downloads.cs:41`）。**行号是引用不是事实**——运行手册里的出处要么指向符号名，
   要么在改完代码的同一批把它改真。
8. 验证（全部现读）：`pytest tests/python` **641 passed / 1 skipped**（本批 +12）；
   `dotnet test` Core **891**（+9 条 helper 语料用例）/ Broker **204**（发现数下界 700/160 由
   `scripts/assert_test_counts.py` 判）；Android ktlint+detekt+testDebugUnitTest 全绿
   （app **333** / broker **88** / webview-adapter 46，较上批 +1/+1）；三道 markdown 门禁 EXIT 0；
   `check_file_sizes` 在 `git add` 之后复跑绿；`git status -- '*packages.lock.json'` 空（没动依赖）。

### 3.46 R9-B46（2026-10-13，队列 Q48=R9-CI-13 与 Q15=R9-SH-5）：CI 触发面收口 + action-catalog 的列身份定稿

两条队列项是同一种病的两面——**「谁判什么」写在散文里就永远不会红**。一条把「门禁型不过滤」
从陈述变成判据，另一条把「这列被谁读」从注释变成判据。

1. **Q15 的回读先把登记本身纠正了**。登记（§四与 §五 Q15）写的处方是
   「`confirmation/risk/audit` 三列在 `agent/broker.py` 零消费 ⇒ 要么被消费、要么删列并写明是治理元数据」。
   逐列现读消费者的结果是：**只有 `confirmation` 真的全仓零消费者**——
   `risk` 由 `contracts/codegen/analyze_action_catalog.py:81` 判「同 scope 不同 risk 冲突」，
   `audit` 由同文件 `:91` 判必填，`read_only` 由 `contracts/codegen/verify_agent_catalog.py:43`
   与 `agent/tests/redteam_test.py:87` 判「首批只读门禁」。
   ⇒ 两个处方都不成立：列**已经在被判定**（判的是它自身的一致性，不是运行时行为），
   而「接进裁决链」会把默认放行推向需要确认——那是 §四 明写不默认执行的方向。
2. 定稿三件（零运行时行为变化）：
   - `contracts/policy/action-catalog.yaml` 头部写死**列的两种身份**：判定面
     （`name`/`scope`/`budget.*` + 顶层 `default_deny`/`policy_version`）与治理元数据
     （`risk`/`audit`/`redteam_fixtures`/`read_only`/`confirmation`），逐项标出「谁判它」。
   - `confirmation` 从装饰变成**必填的意图声明**：analyzer 新增规则 ⑤——缺失、
     不在词表 `{none, required}`、与 `read_only` 矛盾（只读却要求确认 / 写操作却免确认）都判红。
     出厂两条 action 天然满足 ⇒ 现树零变化；下一条 action 忘了想确认问题就判红。
     词表扩值明确写成「属契约面变更，另批定稿」，不在门禁脚本里顺手加。
   - **反向钉住「运行时不读治理列」**：`tests/python/codegen_and_catalog_test.py`
     新增 `TestCatalogGovernanceColumns`（7 条）。其中
     `test_broker_never_reads_the_governance_columns` 读 `agent/broker.py` 源码
     **剔注释后**断言四个治理列名零出现（口径用 R9-B45 那份单源 `text_anchors.strip_comments`），
     并配 `test_broker_really_reads_the_judgment_columns` 作正面控制——
     判定面四列必须真的出现，否则反向锚在判空气。将来谁把 `confirmation` 接进裁决链，
     这条用例先红，逼出的就是「带契约向量的裁决语义变更」而不是改一行读代码。
   - 顺带修夹具：`_action()` 合成条目缺 `read_only/confirmation` ⇒ 加了规则 ⑤ 之后
     「干净夹具」不干净，`test_clean_catalog_passes` 报的红读不出来自哪条规则。
     夹具必须在全规则下干净，专项用例才有诊断力（本批实测撞出来的，不是设想）。
3. **Q48：四处 `push.paths` 收口 + 分类变成机器可读登记表**。
   现读触发面（pyyaml 解析 16 个 workflow）：`ci`=8、`core-rust`=3、`agent-redteam`=5、
   `supply-chain`=11 四处带 `push.paths`，`native-policy-artifacts` 是**唯一一处
   `pull_request` 也带过滤**的（它产生产物而非判定质量 ⇒ 按 builds 类保留），其余门禁型无过滤。
   删过滤的理由不是「清单少列一项」而是**清单这件事不可维护**：`ci.yml` 的清单在 R8-SH-10
   已经从 4 项补到 8 项，仍然覆盖不住该 job 真实读取的语料闭包——补一次就暴露一次
   「下一个漏列的是谁」。ADR-007 D3 自己的判据是「省时收益 << 漏检成本」，本批把它执行完。
4. 新常驻门禁 `scripts/verify_ci_trigger_surface.py`（+ `tests/python/ci_trigger_surface_test.py` 11 条）
   把 ADR 的分类变成与 `.github/workflows/` 的**双向对账**：
   ①每个 workflow 恰好归一类（新增未归类判红、登记了不存在的文件判红）；
   ②gates 的任何触发不得带 `paths`/`paths-ignore`/`branches-ignore`；
   ③gates 必须有 `pull_request` 触发（不在 PR 面上判的门禁等于不存在）；
   ④probes 不得有 `pull_request` 触发（进了必需检查集合跑不完就卡 merge box，R8-CI-01 同族）。
   分类数据在 `contracts/ci/workflow-categories.yaml`（gates 6 / builds 5 / probes 5），
   ADR-007 D3 改成指向它而不是再抄一遍清单。
   先跑一次「红灯实录」证明它能失败：删过滤之前它准确报出四处，删完转绿。
5. 代价与保留的取舍（写下来免得被读成「免费的」）：`core-rust`/`agent-redteam`/`supply-chain`
   原本 `push:` 没有 `branches:` 限定，删过滤后**任意分支的 push** 都会全量跑 cargo/红队/审计；
   `ci.yml` 原有 `branches: [master]` 按原样保留（不是本批新增的收窄）。
   runner 时长上升是 ADR-007 D3 已经认领的代价（「安全性优先，接受」），
   正确的省法在合并流程侧（必需检查）而不是让门禁不跑。
6. 验证：`pytest tests/python` **659 passed / 1 skipped**（本批 +18：治理列 7 条 + 触发面 11 条）；
   `python contracts/codegen/analyze_action_catalog.py` 与 `verify_agent_catalog.py` 均 EXIT 0；
   `python scripts/verify_ci_trigger_surface.py` EXIT 0；`check_doc_claims`（16 个 workflow 的计数
   现算，本批没动 workflow 数量）与表形/链接两道 EXIT 0；4 个改动过的 workflow 全部 pyyaml 可解析。

### 3.47 R9-B47（2026-10-13，队列 Q56 = R9-CI-14）：给 Gradle 依赖图加一条能红的判据（内容对账，不是墙钟）

1. 这条面坏掉的方式很特殊：`gradle-dependency-graph.yml` 只在 master push / 周检 / 手动触发，
   PR 面零执行；它的产物（GitHub 依赖图）是 Dependabot 对 Android 依赖漏扫的**唯一输入**。
   动作静默失败时全仓没有一张牌会变红——Android 漏扫面就此失效而无人知晓。
   #165 那次跨 major bump（4.4.4→6.4.0）是靠「先跑一次证明它」人工确认的，一次性动作不是判据。
2. **登记给的处方被换了**（要写明，不能悄悄改）：Q56 原文建议「每周比对 last dependency submission
   的时间戳，超过 N 天未提交即判红」。不采纳的理由：墙钟判据要另一条常跑流水线去读运行历史，
   而那条流水线本身又需要有人判它没跑——同一个洞换一层皮；而且「按时间算新鲜」在锁没变的周里
   永远绿，在锁刚改的那一周又必须等新作业跑完才有信号。
   改成**内容对账**：GitHub 依赖图必须包含当前 `android/*/gradle.lockfile` 里每一个 `group:name` 坐标。
   锁刚改而图里没有它，只可能是「作业没跑成」或「跑了但没落图」，两种都判红；
   而周检触发本身就是那只钟（图落后于锁，下一次周检必红）。
3. 落地件：
   - `scripts/verify_gradle_graph_freshness.py`：`lock_coordinates()`（四把锁并集）+
     `graph_coordinates()`（SPDX `sbom.packages[].name` 里带 `:` 的 Maven 形态）+
     纯判定 `verdict()`。四条判据里有下界（图内坐标 < 200 ⇒ 面塌缩判红，**不许读成「零个缺失」**）、
     锁面为空 ⇒ 退出 2、取数失败/形状不对 ⇒ 退出 2（取不到图不等于图是新的）。
   - GitHub 落图是最终一致的 ⇒ `--attempts/--delay` 允许在判红之前复判（默认 1，用例走确定路径）。
     把「慢」读成「坏」的判据会教会人忽略红灯，所以重试只延迟红、不掩红：`attempts=1` 时
     同一份迟到数据必须红（用例钉住这一侧）。
   - 作业 `verify-graph-freshness` 接进该 workflow（`needs: submit-dependency-graph`，
     `permissions: contents: read`，`--attempts 4 --delay 20`）。分类登记里它属于 probes，
     本来就不许出现在 PR 面（R9-B46 的 `verify_ci_trigger_surface.py` 会判这条）。
4. 实测（全部现读，不引用推断）：`gh api .../dependency-graph/sbom` 返回 695 个 package、
   其中 Maven 形态 332 个；本地四把锁解析出 284 条 `group:name`，**全部在图里**（差集 0）⇒ 判据 today 绿。
   反向实证：`--sbom` 喂一份「只少最后一条坐标」的图 ⇒ 判红并列出缺的那条；
   喂「图里只有 5 条」⇒ 走面塌缩分支而不是「零个缺失」。
   用例 `tests/python/gradle_graph_freshness_test.py` 11 条（含一条正面控制
   `test_real_lock_surface_is_not_collapsed`：锁解析 ≥200 条且认得出 `androidx.webkit:webkit`，
   否则「全部在册」是空对空的恒真）。

### 3.48 R9-B48（2026-10-13，§四 定稿项 R9-CS-3）：WebView2 三项出货默认改显式赋值（PR #186）

裁决与事实全在 §二 的 R9-CS-3 行与 §四 的定稿段——本小节只补**落点索引**。此前引用 §3.48 的
三处指针是空指针：落地时把正文写进了 §二 的行内而漏开 3.x 小节（「把单源的值再抄一遍就会过期」
这条在台账自己身上第三次出现，同型的前两次是 R9-DOC-18 的计数与五门禁数）。

落点：`windows/src/Aegis.Windows.App/WebView/WebView2Hardening.cs` 的 `Apply(core, tabId)` 里
`AreDevToolsEnabled`（env 门 `AEGIS_ENABLE_DEVTOOLS`，只认字面 `1`）、`IsGeneralAutofillEnabled`、
`IsPasswordAutosaveEnabled` 各一处显式赋值 + 状态留痕；Profile 不可得时必须留痕而不是伪装已生效。
用例 10 条在 `windows/tests/Aegis.Windows.Core.Tests/WebView2HardeningDefaultsTests.cs`
（含「赋值恰好一次」源码锚与 `AreDevToolsEnabled = true` 反向锚，两者都先剔注释再判）。
文档同批：`privacy-defaults.md` 新增一行、`device-validation.md` Windows 表加第 12 步、
`windows-run-guide.md:76` 的计数改成现读命令。

### 3.49 R9-B49（2026-10-13，仓库设置授权后的第一批）：9 条 Gradle 告警正式 dismiss，并把 dismiss 的前提变成常跑判据

1. 用户 2026-10-13 授权「全部剩余项按你的意见完成」后，本批做的是**结掉一件挂了三轮的悬案**：
   `docs/security/android-build-classpath-triage.md` 第三节那 9 条 Maven 告警
   （bcprov×3 / bcpkix / commons-lang3 / httpclient / logback×3）自 2026-10-03 起判为
   「AGP 插件 detached 配置、地板不可达面」，但第八轮 R8-CI-06 实测发现
   **一条都没有 dismiss 过**（9 条全 `state=open`、`dismissed_at` 为 null），
   当时只把「已在 GitHub 上执行」这句失实陈述改真，并注明「属仓库所有者操作，需确认」。
   本批在授权下执行 dismiss。**执行后 API 回读（2026-10-13 16:15Z）**：
   `open=0` / `dismissed=9` / `fixed=3`，9 条均 `dismissed_reason=tolerable_risk` 且
   `dismissed_at` 已写入，逐条 `dismissed_comment` 含该坐标的锁文件行号与 configuration 名。
   两处 API 实况值得记下：①**`dismissed_comment` 上限 280 字符**（首版 566-763 字符被 422 拒），
   所以完整证据只能在文档里、comment 只能是指针——这恰好是「如果当初没写那份分诊文档，
   dismiss 就只能凭记忆」的实证；②合法枚举是 `fix_started / inaccurate / no_bandwidth /
   not_used / tolerable_risk`（从 422 报错里读出来的，不靠猜），
   本批用 `tolerable_risk` 而**不是** `not_used`——这些坐标确实被构建过程用着，只是不在出货面上，
   选 `not_used` 本身就是一次失实陈述。
   **本小节的自查**：§3.49 第 1 点初稿写「本批在授权下执行 dismiss」时动作还没发生——
   正是本节批评的那个形状（把判定写成已执行），故此处补上执行时间与回读证据。
2. **本批真正的产出不是那次点击，而是让那次点击不会过期**。dismiss 依赖的事实是
   「这 5 个坐标只存在于工具/测试类路径」；一次普通的 `implementation` 变更就能推翻它，
   而推翻之后 GitHub 上不会再有任何提示（告警已经被自己关掉了）。
   所以新增常驻门禁 `scripts/verify_gradle_alert_scope_boundary.py`：
   - 从四把 `android/*/gradle.lockfile` 现读每个坐标出现的 configuration 全集；
   - 出货面 = `release|debug` 的 `Runtime|Compile Classpath` + `debugAndroidTest*Classpath`
     （**装进设备跑的那份算暴露面**，不因「不是产品」放过）；
   - 坐标越界进出货面 ⇒ 判红并指明要撤销 dismiss；坐标从四把锁里整体消失 ⇒ 也判红
     （登记载体没了，继续挂着 dismiss 就是下一条失实陈述）；锁面为空 ⇒ exit 2；
   - 接入 `contracts.yml` 既有 job（PR 面必跑；不新增必需 context）。
   用例 20 条（`tests/python/gradle_alert_scope_test.py`），含 12 项 configuration 分类表驱动
   与两条正面控制（登记表每个坐标都必须仍在锁里；文档 §三 表格里必须逐条找得到包名）。
3. **顺手抓到一条三轮都没发现的失实陈述**（这条比 dismiss 更值钱）：分诊文档第三节、
   `android/build.gradle.kts:15-16,26` 与 `docs/audit/full-audit-2026-10-10-round9.md:116` 都写着
   「logback 3×low **不在本仓任何解析树内**」。现读四把锁：
   `ch.qos.logback:logback-core:1.3.16=ktlint` 与 `logback-classic:1.3.16=ktlint`
   在 app/broker/contracts/webview-adapter 四把锁里**各有一条**
   （`android/app/gradle.lockfile:106-107`、`broker:5-6`、`contracts:5-6`、`webview-adapter:15-16`），
   父节点是 `com.pinterest.ktlint:ktlint-cli:1.8.0` 的传递依赖。
   这句话能活三轮的原因很具体：`gradle-dependency-insight.yml` 只扫
   `buildEnvironment` + `debugRuntimeClasspath` + `debugUnitTestRuntimeClasspath` 三条面，
   **从没扫过承载这 9 条告警的两条工具面**（`androidLintTool`、`ktlint`）——
   诊断工具的覆盖面决定了结论的可信度，而它自己没人判。
   处置：三处文字改真（不加地板的结论仍成立，但理由从「不在树内」换成
   「在 ktlint 工具面、抬它会改 linter 自身运行时，且只在构建期存在」）；
   该 workflow 补一条「工具类路径闭包」步骤（从锁文件现读 configuration 归属 + 直接调本门禁），
   以后这两条面每次 dispatch 都在覆盖面里。
4. 事实清单（现读，全部可复核）：`androidLintTool` 的父节点是 AGP 9.4.1 的 lint 工具链
   （`com.android.tools.lint:lint-gradle:32.4.1` 等，`android/app/gradle.lockfile:109-137`）；
   `bcprov-jdk18on` 在测试面已是修复版 **1.85**（`android/app/gradle.lockfile:230`），
   脆弱版 1.80.2 只在 `androidLintTool`（`:229`）；`libs.versions.toml` 与四份
   `build.gradle.kts` 里对这 5 个坐标**没有任何直接声明**，也没有 `constraints{}`/`resolutionStrategy`
   ⇒ 抬版本只能是 AGP/ktlint 升级（`build.gradle.kts:30-42` 的 buildscript 地板管不到
   插件 detached 配置的独立解析域，这一点 SECURITY.md:53-54 已写明）。
5. 判据本身能失败的证据：`violations()` 注入「bcprov 进 releaseRuntimeClasspath」⇒ 红；
   注入「httpclient 从锁里消失」⇒ 红（文案点名「已不存在」）；现树 ⇒ 绿并打印
   5 个坐标各自的 configuration 归属（`logback-core←ktlint`、`commons-lang3←androidLintTool`、
   `httpclient←androidLintTool`、`bcpkix←androidLintTool`、`bcprov←androidLintTool + 三条 UnitTest`）。
6. 验证：`pytest tests/python` 690 passed / 1 skipped（本批 +20）；`check_file_sizes` 绿
   （新脚本/新用例都在 300 行红线内）；表形 / 链接 / `check_doc_claims` 三道 EXIT 0；
   `verify_gradle_alert_scope_boundary.py` 与两个被改 workflow pyyaml 可解析；
   锁文件、`packages.lock.json`、`gradle.lockfile` 均未改动（本批不抬任何版本）。

### 3.50 R9-B50（2026-10-14，队列 Q55 = R9-AD-12）：Gradle 的「字节」那一刀启用——版本与校验和各有重算面

1. Q55 原来挂在 §四 待裁决，是因为它要先定三件事。用户 2026-10-13「全部授权，剩下的按你的意见
   完成」之后按本仓既有口径定死：①**谁签**——不引 PGP（仓内无受信密钥），文档里
   `<verify-signatures>false</verify-signatures>`，所以这一刀说的是「字节与登记的 sha256 一致」，
   不是「构件被谁签名」，SECURITY.md 照这句写；②**校验和从哪来**——只由 `dependency-relock.yml`
   的 gradle 生态在被授权的 dispatch 里按当前解析面重算，只写 `deps/*` 分支，PR 人工审 diff 后合并；
   ③**trusted artifacts 怎么豁免**——**零豁免**：文档里没有 `<ignored-keys>`、`<trusted-artifacts>`、
   `<suppress>`，842 个 artifact 每个都带一条 sha256（这条由用例判，不靠肉眼看）。
2. 落地面四件，缺一件就只是「看起来启用了」：
   - `android/gradle/verification-metadata.xml` 入库：495 组件 / 842 artifact / 842 条 sha256
     （238 `.module` + 258 `.pom` + 346 `.jar`/`.aar`），224 KB / 3526 行；
   - `android/gradle.properties` 加 `org.gradle.dependency.verification=strict`——**生效面是属性**。
     只在命令行加参数的那种做法等于没开：本仓 CI 与本地大量 gradlew 调用不带任何参数，
     它们一条都不校验；命令行参数于是只剩「重锁那一次的放宽」；
   - `dependency-relock.yml` 的 gradle 面从「只写锁」改成「锁与字节同批、两边都强制重取字节」：
     图面那条（`--refresh-dependencies --write-locks --write-verification-metadata sha256
     resolveAllConfigurations`）+ 文件面那条（新任务 `resolveAllConfigurationFiles` +
     `buildEnvironment` + 工具任务清单）+ 原有的覆盖自证。写回守卫的合法面从「只有
     `*/gradle.lockfile`」扩成再加 `*/gradle/verification-metadata.xml`——不扩的话重锁作业会
     **红在自己的守卫上**；
   - 口径单源改真：`android/settings.gradle.kts` 决策记录 ③（原写「本批**不做**」）、
     SECURITY.md 的 Android 条（原写「本仓未做，不对外声称」）。
3. 两面口径为什么不能并成一条（本批最容易读错的地方，也是 PR #189 那一轮红灯的根因）：
   - **图 ≠ 文件**。`resolveAllConfigurations` 走 `incoming.resolutionResult.root`，只下
     `.pom`/`.module`；`--write-verification-metadata` 登记的却是**本次真正落盘的字节**。
     所以新增按文件的集合口径 `resolveAllConfigurationFiles`（解析每个 `canBeResolved` 配置的
     `.files`），构建类任务（`assemble*`/`compile*`）从文件面**删掉**——它们的 classpath 文件
     本来就在这些配置里，两处各写一份就是两份真相；
   - **集合也覆盖不到工具面**。ktlint/detekt/lint/单元测试用的是任务执行时现建的
     **detached 配置**，不在 `project.configurations` 里，只有跑那几个任务才会落盘 ⇒ 那一份
     小清单不能省，它与 CI 的对应关系由 `tests/python/gradle_verification_test.py` 从 workflow
     原文逐 token 判（现值：CI 24 个 token，重算面 + 两类豁免正好盖住）。豁免分两类且都必须
     写理由：`NON_ARTIFACT_FILE_FACE`（不落文件的报表/对账类）与 `SET_COVERED_TASKS`
     （文件来自项目配置，已由集合口径覆盖）。并要求「提取到的 token 数 ≥20」——提取口径自己
     坏掉时这条必须红，否则子集判据就是空对空（本批真的红过一次：正则少写一层 `*`，
     24 个 token 静默只剩 5 个）；
   - **本地全绿不是证据**。这条是本批最贵的：校验和文档只能记录本次落盘的字节，而长命的
     `~/.gradle` 元数据缓存能让一批 parent-pom/BOM 描述文件**永不落盘**。于是本地三条命令全绿、
     入库那份「看起来完整」，CI 的干净 runner 当场红——见第 4 点的第 5 条；
   - **字节面还跟平台走**。本机生成的文档里 `aapt2` 只有 `…-windows.jar`，`-linux` 形态零命中，
     而 CI 的 android-quality/dependency-graph 跑在 ubuntu 上。⇒ 校验和必须在**每个会构建的平台**
     上生成过才算全；本批的处置是把 gradle 重锁面（ubuntu dispatch）当作权威生成面跑一次，
     windows 侧条目由本机那份带入（并集只增不减，Gradle 不剪未用到的条目，实测 466→495 与
     幂等两轮都是这个行为）。**跨平台自动生成面缺一个是新登的口子，见 §五 Q61**。
4. 实测七条，全部现跑（不是设想）：
   - **属性生效**：把 junit 那条 sha256 的末位 `3` 改成 `4`，`./gradlew :broker:testDebugUnitTest`
     不带任何校验参数 ⇒ EXIT=1，`Dependency verification failed for configuration
     ':broker:detachedConfiguration6'` + `One artifact failed verification: junit-4.13.2.jar
     (junit:junit:4.13.2) from repository MavenRepo` + 「This can indicate that a dependency has
     been compromised」，45s。顺带一条事实：报错落在 **detached 配置**上——工具面也在判面内。
   - **缺条目不阻塞重锁**（Q55 原来担心的鸡生蛋）：删掉整个 junit `<component>` 块（等价于
     一次版本升级带来的新坐标没有条目），跑重锁那条命令 ⇒ EXIT=0 且条目被**补录**回来。
     生成模式对缺条目是补录不是判红，这就是「bump 之后靠重锁补字节」这条路能走的原因。
   - **SOP 幂等（按当轮三面写法）**：四把 `gradle.lockfile` 的 md5 逐条不变、
     `verification-metadata.xml` 的 md5 不变（02cbcfaf…）⇒ 入库那份就是重锁面的不动点。
     加上 `--refresh-dependencies` 与新任务之后的那一次不动点，由本批末尾的 dispatch 实证。
   - **改坏的文档不被静默接受**：把 `<configuration>` 里换成放错层级的 `<trust>` ⇒ EXIT=1，
     `Unable to read dependency verification metadata`（并点名 `<trust>` 必须在
     `<trusted-artifacts>` 之下），且文件未被改写 ⇒ 这一刀只有「红」和「拒读」两种表现，
     没有第三种「当没这回事继续构建」。
   - **本地全绿挡不住 CI 红（PR #189 首轮，三个 gradle 作业同红）**：`android-quality`、
     `contracts/android-contract-build`（windows runner）、`native-policy-artifacts` 报的都是同
     6 个构件、同一个配置名 `classpath`——`guava-parent-33.4.0-jre.pom`、
     `junit-bom-5.10.2.module`、`junit-bom-5.11.0-M2.module`、`junit-bom-5.14.4.module`、
     `kotlin-gradle-plugins-bom-2.2.10.module` 与 `.pom`。入库那份里这些组件**存在但只登记了
     另一半**（`junit-bom:5.10.2` 有 `.pom` 没 `.module`；`kotlin-gradle-plugins-bom` 只有本机
     用得到的 2.4.21）。根因不是平台，是**缓存**：Gradle 只把本次落盘的字节写进文档，
     而本机 `~/.gradle` 的元数据缓存让这些描述文件从来没被取过 ⇒ 生成面看不见它们，
     干净 runner 一解析就红。处置＝生成面一律 `--refresh-dependencies`（强制重取），
     并把权威生成面放到 CI 上跑一次（见第 10 点）。**两个附带事实**：①文档的字节面跟平台走
     （本机文档里只有 `aapt2-…-windows.jar`，`-linux` 零命中），②`FileCollection` 没有 `size()`
     ——写错成 `cfg.incoming.files.size()` 的表现是**脚本编译不过**而不是解析出 0 个文件，
     而脚本编译结果有缓存，不加 `--refresh-dependencies` 的话这个错误形态能躲过本地三轮运行。
   - 覆盖面 466→495 组件那 29 条增量全部来自**参与冲突裁决但未被选中**的版本
     （lifecycle / savedstate / coroutines 的旧候选 + detekt 的 sarif4k、kotlin-logging），
     不是新依赖。这解释了「锁里 284 条坐标、文档里 495 个组件」：字节面按构件登记，
     含解析过但没进最终图的 `.pom`/`.module`。
5. 用例 22 条，拆两个文件（单文件超 300 行红线——`check_file_sizes` 判的，不是审美）：
   `tests/python/gradle_verification_test.py` 12 条（档位现读、三种改弱注入必红、注释行不当赋值、
   workflow 里不许出现 `--dependency-verification=off|lenient`、两条生成面都必须
   `--refresh-dependencies` 且文件面走集合口径、重算面 ⊇ CI 现读任务面（两类豁免都要写理由）、
   构建任务退回清单即判红、root 脚本真的注册了那个任务、删掉文件面必红、
   写回守卫放行 metadata 且继续拒绝版本目录/构建脚本/文档、SECURITY.md 与 settings 决策记录的
   正反双向锚）+ `tests/python/gradle_verification_document_test.py`
   10 条（现树零问题 + 注入必报：两个开关翻转、摘要截断两位、摘要换算法名、空组件、
   artifact 无摘要、整块 `<configuration>` 缺失、命名空间错的同名文档、截断的标签）。
   接线走 `contracts.yml` 既有 job（`contract-source-of-truth`），**没有新开必需检查上下文**
   ——R8-CI-01 那条「Expected — Waiting for status」的教训要求新 context 先在真实运行里见到才能加。
6. 收敛过程自己撞出来的第二条口径缺陷（记在 §3.45 的同型账后面）：把
   `scripts/text_anchors.py:strip_comments` 复用到 workflow 的 **shell 正文**时，`deps/*)` 与
   `*/gradle.lockfile)` 里合法的 `/*`…`*/` 被当成一个 C 系块注释，**中间的真实语句整段消失**——
   写回守卫的 `case "$changed" in` 没了，判据安静地改判空气。处置：单源里增一个具名口径
   `drop_line_comments(text, prefix)`（只按整行前缀剔注释），shell / `.properties` 面用它，
   源码面继续用 `strip_comments`；`tests/python/relock_sop_test.py` 的 `code_only()` 同批改调它
   （不留第十六份副本），`text_anchors.py` 的模块 docstring 把「不并进来的面」从一处如实改成两处。
   教训形状与前两次同型：**口径有单源不等于万能**——一套剔注释规则覆盖不了 glob 面，
   而覆盖不了的表现是**静默少判**，不是报错。
7. 验收口径的差额如实登记：Q55 写的是「CI 里 strict 跑通 `:app:assembleRelease`」。
   本批在**本机**跑通（`:app:assembleRelease` 全量解析，R8 + lintVitalRelease 都过，
   native 门按默认关；`buildEnvironment`、`:app:dependencies --configuration
   debugRuntimeClasspath`、`:app:dependencyInsight --configuration ktlint` 三条图面也都 EXIT=0）。
   CI 侧本批能保证的是 `android-quality`（含 lintDebug/assembleDebugAndroidTest/ktlint/detekt/test）
   与 `contracts.yml` 的 `:app:assembleDebug` 在 strict 下跑，`gradle-dependency-graph.yml` 的
   `assemble`（dependency-submission 的隐式默认任务）在 master push 上跑；
   **`release-android.yml` 的 release 构建要等下一次真实 dispatch/标签**——本批不放行未验的闭环声明。
8. 未做的另一半（不外推）：PGP/trust-keys 治理、`--write-verification-metadata pgp` 档位；
   以及 `buildscript {}` / plugins DSL 的**脚本类路径**——它与版本锁一样不在项目配置面内，
   仍由 root 显式 classpath 地板 + `buildEnvironment` 回读承接（口径未变）。
9. 验证：`pytest tests/python` **713 passed / 1 skipped**（本批 +23：配置面 12 + 文档面 10 + 索引形态 1）；`active_tree_gates all`
   （ruff / bandit / py312-compat）三面 OK——`ET.fromstring` 那处按 `assert_test_counts.py` 的
   既有口径用**行级** `# nosec B314` + 信任边界注记，没有把 B314 加回全局 skips；
   `check_file_sizes` 绿（两个新文件分别 264 / 113 行）；表形 / 链接 / `check_doc_claims` 见本节末
   复跑；四把 `gradle.lockfile` 与 `packages.lock.json` 未改动（本批不抬任何版本）。

10. 第三轮才发现的**索引形态**问题（同一个 dispatch 第二次挡下，run 38445166117）：
    `写回分支` 步骤报「❌ 非依赖证据文件出现在纯重锁运行里：android/gradlew.bat」而中止。
    现读 `git ls-files --eol`：`android/gradlew.bat` 是全仓**唯一**一个 `i/crlf` 的入库文件，
    而 `.gitattributes:10` 写着 `*.bat text eol=crlf`——`text` 意味着入库前该归一成 LF，
    所以那个 CRLF blob 是属性生效之前留下的旧形态。后果不是排版：干净 runner 上任何让这个
    文件 stat 变动的动作，都会使 `git add -A -- android` 重新套 clean 过滤器得到 LF ≠ 索引里的
    CRLF ⇒ **每次 gradle 重锁都长出一个伪 diff**，被写回守卫判成杂项拒绝。
    判定要说清方向：**守卫那次是对的**（它拒绝的确实不是依赖证据），坏的是索引；
    修法是把索引归一（`git add --renormalize android/gradlew.bat`，签出形态不变，
    Windows 上仍是 CRLF），而不是放松守卫或给守卫加白名单。
    常驻判据：`tests/python/gradle_lockfile_shape_test.py::
    test_no_tracked_file_fights_its_own_text_attribute`（全仓扫 `i/crlf` 且属性含 `text`
    的位点，并配一条正面控制证明 `-text` 分支不是空判）。这条若不钉住，下一次 gradle
    重锁会在同一个地方再红一次，而每个人的第一反应都是「守卫太严」——那是最坏的修法。

11. **权威生成面在 CI 上跑通并回填**（第三次 dispatch，run 38446662535，
    `deps/r9-b50-gradle-verification`）：重锁步与写回步都绿，产物是
    `verification-metadata.xml` **+54 行、四把 `gradle.lockfile` 零改动**。新增内容正好补上
    CI 报的那 6 个构件（`guava-parent-33.4.0-jre.pom`、`junit-bom` 5.10.2 / 5.11.0-M2 / 5.14.4
    的 `.module`、`kotlin-gradle-plugins-bom-2.2.10` 的 module + pom），另加冷缓存解析才会碰到的
    BOM 父描述文件（groovy-bom、bc-jdk18on-bom、kotlinx-coroutines-bom 1.6.4/1.7.3/1.8.0、
    guava-parent 33.6.0-jre），以及**平台相关的那一个**：`aapt2-9.4.1-15978811-linux.jar`——
    本机那份只有 `-windows.jar`，这条把第 3 点的「字节面跟平台走」从推断变成实测。
    入库那份因此是 windows（本机）+ ubuntu（dispatch）两轮并集，且这次是**按 SOP 的三面写法**
    （`--refresh-dependencies` + 集合文件面 + 工具任务面）产出的，重锁幂等性在这一轮才真的成立。

### 3.51 R9-B51（2026-10-14，队列 Q61 = R9-AD-15）：把「字节面跟平台走」变成常跑判据

1. 本批做 Q61 里**不需要任何人给话**的那一半，把另一半如实留在队列里。起因不是设想：
   R9-B50 的 `verification-metadata.xml` 是在本机（windows）生成的，`com.android.tools.build:aapt2`
   那一轮只落了 `aapt2-9.4.1-15978811-windows.jar`，`-linux` 形态**零命中**；而 CI 的
   `android-quality` 与 `gradle-dependency-graph` 跑在 ubuntu 上。校验和只登记本次真正落盘的
   字节，所以「一份文档服务两个 runner」这件事等价于要求「每个平台都生成过一次」——
   而当时全仓没有任何东西在判它，缺的那一半要等到下一个用到该构件的 ubuntu 作业当场红才看见
   （R9-B32 是同一个位置：master 面上的作业红，同期 PR 门禁全绿）。
2. 新常驻门禁 `scripts/verify_gradle_platform_coverage.py`：
   - 需求平台**从 workflow 的 `runs-on` 现取**（ubuntu→linux、windows→windows、macos→macos），
     代码里没有 runner 名单——将来加一个 macos runner，这条判据会自动开始要求 macos 形态；
   - 认「构件名带平台后缀」的坐标（`-linux`/`-windows`/`-macos`/`-osx`/`-darwin`，含
     `osx-x86_64.exe`、`macos-aarch64-2.2.10.zip` 这类平台段后面还有版本号的真实命名），
     要求它覆盖**需求集合本身**；
   - **一条被用例钉住的弯路**：第一版判据写成「同坐标各版本取平台并集再比」，看着更聪明，
     但真出事的那一次现场就是「只有一个版本、只在一台机器上重算过」——按版本并集比在这种
     形状下恒绿。用例 `test_single_version_missing_a_platform_is_red` 专门把这条钉住；
   - 判定面塌缩（文档里认不出任何平台后缀构件）⇒ 退出 2 而不是「通过」：AGP 必然拉 aapt2
     的平台包，零命中只可能是解析口径坏了；
   - 豁免表 `PLATFORM_EXCLUSIVE`（坐标→理由）**自己也被判**：无理由、或登记的坐标在文档里
     已经找不到，都判红。当前是空表，用例正面控制着「不许有没理由的豁免」。
3. 现树实况（现读，不是推断）：需要覆盖 `['linux','windows']`；平台相关坐标只有
   `com.android.tools.build:aapt2[9.4.1-15978811←linux,windows]` ⇒ 判据 today 绿。
   证伪四条：删掉 `-linux.jar` ⇒ 红并点名 `['linux']`；删掉 `-windows.jar` ⇒ 红；
   只留一个版本且只有 linux ⇒ 红（旧写法在这里会绿）；把需求集合换成含 macos ⇒ 红。
4. 接线：`contracts.yml` 既有 job（`contract-source-of-truth`）新增一步，**没有新开必需检查
   上下文**（R8-CI-01 的教训口径）。用例 `tests/python/gradle_platform_coverage_test.py` 22 条
   （含 runs-on 解析形态表驱动、平台后缀识别表驱动、塌缩/缺文件/坏文档三条 exit 2、
   豁免表自我判据、以及「SECURITY.md 必须写着按平台是并集」的文档对账）。
5. Q61 记**部分闭环**：判据这一半已常驻；「自动生成面只有 ubuntu」那一半仍在队列里，
   因为补一个 windows 腿要么改 `gradle-relock` 的写入面（两个 job 并发推同一份文件必然互相
   覆盖，得先设计串行或合并策略），要么在 PR 面加 `--refresh-dependencies` 的重下载成本——
   两者都不是本批能顺手定的。
6. 验证：`pytest tests/python` 735 passed / 1 skipped（本批 +22）；`active_tree_gates all`
   （ruff / bandit / py312-compat）OK；行数红线、表形、链接、`check_doc_claims`、
   `check_workflow_shells` 复跑见本节末；四把 `gradle.lockfile`、`packages.lock.json`、
   `verification-metadata.xml` 均未改动（本批不抬任何版本，也不重算任何字节）。

### 3.52 R9-B52（2026-10-14，第九轮自查）：队列状态变成能红的判据，并当场改掉 8 条「写着已落地却没划线」的行

1. 触发点是本批自己撞出来的两处：①写 §3.50 时发现 **§3.48 整节不存在**，而 §二与 §四 有三处
   文字在引用它（引用一个没有的小节，比不写指针更坏——它读起来像已经交代过）；②给 §五 收尾时
   按 `- Q` 数「还剩几条」，发现 Q12 / Q13 / Q14 / Q22 / Q47 / Q39-Q46 六条正文都写着
   「本批已回读确证并落地」，行头却还是**未划线**的开放形态 ⇒ 队列规模虚高，下一轮会把这些
   再做一遍。两类都不是新毛病：第八轮的失账就是「只剩计数、不可回读」，而 §五 存在的唯一理由
   是让人**不用重读代码**就能知道每条的状态。
2. 新常驻门禁 `scripts/verify_ledger_queue_status.py`，两条判据：
   - 划线行（`- ~~Qn …~~`）必须含至少一个能在**同一份台账里**解析到的 `§3.nn` 指针；
   - 未划线行必须含一个**封闭词表**里的开放状态词（待裁决 / 待定稿 / 待设备 / 待实测 /
     部分闭环 / 需给话 / 登记不顺手 / 仍开着 …）——「已完成」这类自造词不算，因为
     用例把词表钉死了（`test_unstruck_rows_need_an_explicit_reason`）。
   判定面塌缩（有 `## 五、待回读队列` 标题却数不出一条队列行）⇒ exit 2 而不是「通过」。
3. 判定面的边界是**改出来的**，不是设想：第一版把 `^## 五、` 当队列段，于是轮 6 的
   「## 五、被推翻的子代理结论」也进了判定面，门禁当场 self-report「有 §五 却数不出一条
   `- Qn` 队列行」并 exit 2——这是**门禁自己**触发了塌缩分支。修法是把标题收紧成
   `^## 五、待回读队列`，并留一条 `test_ledgers_without_a_queue_section_are_out_of_scope`
   把「别的轮的 §五 不参与」钉住（否则下一个改标题格式的人会再撞一次）。
4. 同批改真的 8 处行头：Q12 / Q13 / Q14 划到 §3.9（R9-B10，其中 Q14 的「恒绿旧断言本体」
   由 §3.33 收掉，两个指针都写上进行头）；Q22 / Q47 / Q39-Q46 划到 §3.10 与 §3.20+§3.41；
   Q4 改成**部分闭环**（口径改真在 §3.5，「打通 IPv6 导航面」仍列 §四 待定稿）；
   Q10 补上「待裁决」并说明为什么（桥传输整体迁移是跨端契约变更，不在缺陷批顺手做）。
   改的是**状态标注**，不是判定：一条也没有被重新裁决，未划线行的正文逐字保留。
5. 用例 `tests/python/ledger_queue_status_test.py` 12 条：两条判据各配注入必红 + 正面控制、
   指针只在本文件内解析（跨文件借号＝假闭环）、块边界收在下一条队列行（不许互相借状态词）、
   非队列段的 §五 不参与、段边界收在下一个 `## ` 标题、塌缩与「无事可做」都走 exit 2、以及一条规模正面控制
   （§五 必须数出 ≥40 行、其中 ≥30 行已划线——数不出来就是提取口径坏了）。
   接线走 `contracts.yml` 既有 job（`contract-source-of-truth`），不开新必需检查上下文。
6. 验证：`pytest tests/python` **747 passed / 1 skipped**（本批 +12）；新门禁现跑现绿；
   `active_tree_gates all`（ruff / bandit / py312-compat）OK；行数红线 / 表形 / 链接 /
   `check_doc_claims` / `check_workflow_shells` 全 EXIT 0。本批**不动任何代码行为**：
   四把 `gradle.lockfile`、`packages.lock.json`、`verification-metadata.xml` 零改动。

### 3.53 R9-B53（2026-10-14，队列 Q61 的另一半）：校验和的生成面从一条腿变成两条串行平台的腿

1. 本批落的是 Q61 里那两条形状中的 **①**（给 `gradle-relock` 加 windows 腿），而不选 ②
   （PR 面加一条 `--refresh-dependencies buildEnvironment` 的冷缓存哨兵）。理由是两条买到的
   东西不同：② 只能让「文档不完整」在合并前变红，**补那半个平台仍然要人跑一次**；① 把
   「补」这一步本身变成执行面。②的代价也要如实记：每条 PR 重下一次插件类路径。
2. **两条腿必须串行**（`needs: gradle-relock`），这不是排版偏好。失效形态说清楚：两个 job 若并发，
   它们各自 `actions/checkout` 到**同一个 base commit**（都是 `fetch-depth: 1`），
   先推的那条成功、后推的那条被 non-fast-forward 拒红——那盏红灯读起来像「分支冲突」，
   而真实原因是「腿没有串行」。所以这条不靠人解读红灯，做成**结构事实 + 判据**
   （`test_windows_leg_is_serialized_after_the_ubuntu_leg_and_cannot_write_locks`）。
3. 第二条腿**只重算字节、不重算锁**：版本锁记的是解析结果、跨平台一致（R9-B50 实测两条腿
   同文档无哈希冲突），跟平台的只有字节面。所以 windows 腿不带 `--write-locks`、
   不跑 `verifyDependencyLockCoverage`，**写回守卫也只放校验和文档**——
   那条腿若出现 `*/gradle.lockfile` 的 diff，就是写回面错了（或被人为并发跑），当场拒推。
   ubuntu 腿的守卫仍是两类都放（四把锁 + `verification-metadata.xml`，见 §3.50 第 5 条）。
4. 抽了**两份** composite action，两份都是「两条腿必须同形」的地方：
   · `.github/actions/gradle-checksum-file-face`：文件面那一条命令的唯一出处；
   · `.github/actions/gradle-android-toolchain`：JDK 21 + Gradle 缓存（`cache-dependency-path`
     含版本目录，SP-215/AD-243 口径）+ Android SDK 基线包。装配不同形 ⇒ 两条腿**落盘的构件集合**
     就不可比，字节面差异里会掺进「SDK 包不一样」这种假信号。
   为什么命令必须只有一份：抄两份的漂移形态很具体——一条带 `--refresh-dependencies`、
   另一条不带；或任务清单少一项；表现都是「某平台的构件字节静默缺失」，也就是本批要根除的
   那类失效本身（R9-CI-2 / R9-B16 抽公共执行面是同一课）。判据按**出现次数**判死：
   `generation_corpus()` 把两条腿的 workflow 正文 + action 正文拼成一个语料再数
   （分开数各数各的，合起来才数得出漂移），要求文件面命令恰好 1 处、每条腿对两个 action
   各恰好消费 1 次。
5. windows runner 上仍用 `./gradlew`（Actions 的 `shell: bash` 即 Git Bash）而不是 `gradlew.bat`：
   同一条命令两个平台，不引入第二种命令行形态——那会让「两条腿跑同一份命令」这句判据
   退化成两份文本锚。
6. 判据口径跟着结构改：`tests/python/relock_sop_test.py` 的 `gradle_relock_run()` 原本按
   **步骤名**取正文，而本批把那一步拆成了「图面 + action 消费 + 覆盖自证」几步 ⇒ 改成
   **按 job 收集全部 bash 正文**。按名字取会让「给步骤改名」成为一条无声的绕过
   （本文件其余判据当初就是这个理由不按名字取）。
7. 自己撞的一条假阳性，值得记：第一次写「windows 腿不能写锁」时按「正文里不含 `--write-locks`」判，
   当场红——因为那个词出现在 windows 腿写回步骤的**报错文案**里（`❌ …这条腿不带 --write-locks`）。
   改成要求该行同时含 `gradlew` 才是命令面。这是「文本锚要认载体」的第三次实测
   （R9-B39 注释喂绿、R9-B44 端侧源码、这一次是 prose 冒充命令行）。
8. 300 行红线撞在自己身上：`gradle_verification_test.py` 加完两条腿的判据后 370 行 ⇒
   按「**配置面与对外口径** / **重算面**」拆成两份（新文件 `gradle_relock_surface_test.py`），
   共享词表与 gradle 命令提取口径留在原文件（`FILES_TASK` / `RESOLVE_GRAPH_TASK` /
   `gradle_command_lines`，跨文件 import 走既有先例 `dotnet_suite_composite_wiring_test.py`）。
   拆分不是免费的：三处引用了搬走判据的文件名（`android/settings.gradle.kts` ×2、
   新 action.yml ×2、`gradle_verification_document_test.py` ×1）全部跟着改准——
   留着一个指向**没那条判据的文件**的名字，就是 §3.52 那条「指向不存在的指针」的新形态。
9. 验证（本地）：`pytest tests/python` **749 passed / 1 skipped**（本批 +2 条结构判据、
   拆分不改变用例数口径）；`active_tree_gates all`（ruff / bandit / py312-compat）OK，
   其中 py312-compat 现扫到 **7 个** composite action（新增两份都在判定面内，它是目录现取的）；
   行数红线（新文件 260 行、原文件 155 行，都在 300 内）/ 表形 / 链接 / `check_doc_claims` / `check_workflow_shells`
   （26 个 pwsh 步骤；两条腿的命令都固定 `shell: bash`）/ `verify_ledger_queue_status`
   / `verify_gradle_platform_coverage`（需求平台现取仍为 `['linux','windows']`）
   / `verify_text_anchor_helpers`（实现点仍 5 处）/ `verify_ci_trigger_surface` 全 EXIT 0；
   pin-check 的 grep 口径本地同跑（含 `.github/actions/`）⇒ 全部 40 位 SHA。
   本批**不动任何出货行为**：四把 `gradle.lockfile`、`packages.lock.json`、
   `verification-metadata.xml` 零改动，`android/` 下只动了 `settings.gradle.kts` 的注记。
10. **端到端实证**（`dependency-relock.yml` 两次 dispatch，`--ref fix/r9-b53-…`、
   写回面 `deps/r9-b53-legs-evidence`；两次都跑通 ⇒ 结构判据之外还有真运行）：
   - run **38461734317**（不动文档的那一次）：ubuntu 腿三条命令 `BUILD SUCCESSFUL`（57s / 2m2s / 7s）
     ⇒「✅ 重锁无差异」；windows 腿（`C:\Program Files\Git\bin\git.exe` 那一台）文件面
     `BUILD SUCCESSFUL in 3m 33s` ⇒「✅ windows 腿无差异」。**入库那份就是两条腿的不动点**——
     这与 §3.50 记的 SOP 幂等是同一件事在两个平台上的版本。顺带证伪一条担心：
     `./gradlew` 在 windows runner 的 Git Bash 下可用，不需要 `gradlew.bat` 的第二种命令行形态。
   - run **38463296721**（**注入必红/必补**那一次）：先在 `deps/*` 分支上删掉
     `aapt2-9.4.1-15978811-windows.jar` 的 `<artifact>` 块（3 行），再跑同一个作业。
     ubuntu 腿三条命令全绿、**且没有把那一块补回来**（仍是「✅ 重锁无差异」，零推送）——
     这就是「字节面跟平台走」的直接证据：不是「ubuntu 腿偷懒」，是它**下载不到**那个文件；
     windows 腿随后 `BUILD SUCCESSFUL in 5m 12s`，产出 commit `02ee497b`，diff **恰好 +3 行**、
     只动 `android/gradle/verification-metadata.xml`，补回的 sha256 与被删的那条逐字符相同
     （`5fe3c8ee…`）——同一构件在两个平台上的字节一致，缺的是**登记**而不是内容。
     写回守卫在只放校验和文档的那条腿上按预期放行。两次运行都没有出现并发推送。
   - 这条实证同时是 Q61 验收口径的前半（「两个平台的 gradle 作业在同一份文档下绿」）；
     后半「一次真实的依赖 bump」要等下一条 bump PR，与本批无关，记在 §3.50 第 7 条那一类
     「等下一次真实 dispatch/标签」的位置。

### 3.54 R9-B54（2026-10-14，队列 Q62 = R9-CS-19）：红灯的红因在**用例自己**——测试记录面不再被并发枚举

1. 触发点是 §3.53 那次 PR 的 CI 面：run **38461642255** 的 `windows-contract-build` 红一条
   `Failed: 1, Passed: 900`，栈顶是 `ThreatFeedCoordinatorTests.cs:65`（观测时的行号）的
   `SpinUntil(() => h.Applied.OfType<BlockedHosts>().Any(...))`，异常是
   `InvalidOperationException: Collection was modified; enumeration operation may not execute`。
   同一个 commit 的另外两个触发面全绿——**这类红灯不挑改动内容，只挑时机**。
2. 现读定位（不是猜）：写侧是 `ThreatFeedCoordinator.Start()` 的后台线程（`applyHosts` 与
   `message` 两个回调往 `Harness.Applied` / `Harness.Logs` 里 `Add`），读侧是测试线程每 10ms
   一轮的枚举——两边是同一个 `List<T>`。同批复读的另两处**不是同形，因此没动**：
   `ThreatFeedRefreshScheduleTests` 的 `Delays`/`_logs` 全部在 `await c.BackgroundTask!` 之后才读
   （或只轮询一个 `int` 计数），没有并发枚举；`FakeClock` 那条链本来就是单线程自排的。
   泛化成「文件里有轮询helper + 有 `List<` 字段就判红」会误伤前一种安全形态，
   所以本批只钉住**已知会并发**的三处，不造一个会误判的面。
3. 形状选了**带锁 + 一次性快照**，而不是 `ConcurrentQueue<T>`：后者的枚举自己就写着
   「不是快照、可能瞬时」，而这里的断言靠的正是顺序与整体一致（`_pushed[0]`、`[^1]`、
   `Assert.Single(...)`、`OfType<>().Any()`）。`ThreadSafeRecorder<T>` 的读面只有
   `Snapshot()` / 枚举 / 索引器 / `Count` 四个——**底层 `List` 不外露**，所以「新加一个读取点
   直接碰表」这条回潮路径在类型上就不存在。
4. 跨程序集共享走**链接同一份源文件**（`windows/tests/Aegis.Windows.TestSupport/`，
   与 R9-B45 的 `SourceTextAnchors.cs` 同口径）：新建测试支撑工程要动构建面
   （工程引用、锁文件、发现数下界），链接源码没有这些代价。
5. 一条被红线门禁逼出来的取舍：`CoreDenylistPublisherTests.cs` 是 **299 行零余量**（300 是红线，
   见 `check_file_sizes.py` 的 `lines > LINE_LIMIT`），所以那里**不加 `using`**，
   改用全限定名做同长度替换——加一行注释都会把它推到 300。这不是风格偏好，是门禁的形状。
6. 判据两层，各配实证：
   - **行为层**（`ThreadSafeRecorderTests.Concurrent_record_and_enumerate_never_throw`）：
     8 名写者 × 400 条、4 名读者各跑整条 LINQ 链 + `Count` + `foreach`，断言「一条不丢、
     不重复」以及两条**非空心**证据（`nonEmptyReads > 0`、`enumeratedItems > 0`）。
     重叠是**构造**出来的：读者先经 `CountdownEvent` 报到，0 号写者再播一条种子、
     等读者确实读到过一次非空快照，其余写入才开工；读者的退出条件是「写侧真的结束」，
     不是「我转了几千圈」。
   - **接线层**：三处已知字段必须仍是 `ThreadSafeRecorder<…>`，且代码面（剔注释后）不得再出现
     `Applied.Add(` / `Logs.Add(` / `_pushed.Add(`；判定是个纯函数，注入形态
     `List<IBlockedHosts> Applied` + `Applied.Add(applied)` 必须被它认出（正面控制在
     `An_injected_plain_list_recorder_is_red`）。选接线层而不是只留行为层的理由：改回 `List<T>`
     最容易发生在**解合并冲突**的时候，而那时没人会把它和 CI 的偶发红联系起来。
7. **本批自己撞的那条课（第一版在 CI 红）**：行为层的第一版是 `Task.Run` 起读线程 + 固定
   2000 圈自旋上限，本机全绿，PR #193 的 CI **两次都红**——红在我自己加的那条非空心断言上：
   `Error Message: 读线程从没读到过任何内容：与写侧根本没有重叠`（run 38469671504 与
   38469725331，`Build Windows x64 policy DLL` 那个 job 是同一条用例的第二处红）。
   机理是调度而非同步：自旋的读任务占着线程池 worker，8 个写任务排在后面，而 2 核 runner 上
   读者把圈数烧完就退场了。三条结论都写进了代码注释——
   ①并发用例的**本地全绿不是证据**（与 §3.50 那条 `--refresh-dependencies` 是同一课，
   只是这次红的是我自己写的判据而不是构建缓存）；②「重叠」不能交给调度器，必须握手；
   ③**非空心断言的价值就在这里**：它把一件设计缺陷变成了一条明确的红灯，而不是让这条用例
   安静地空跑而全绿（§3.39 记过的空心门禁那一类）。
   改成专用线程 + 种子握手后的本机实测口径：**带锁 18 连跑（10+8）全绿**（0 次错杀），
   把 `ThreadSafeRecorder` 的三处 `lock` 摘掉后 **6 连跑全红**（0 次漏抓），红的形态是
   `Assert.Equal() Failure: Values differ`——记录面**丢了写入**（不是每次同一条断言先炸，
   但都在这条用例里炸）。两组数都是「连跑次数」而不是「必红/必绿」：并发用例对破坏的捕获
   在原理上是概率性的，本批把**确定性**放在接线层那半，行为层这半只负责把「同步被摘掉」
   这种改法在大概率上撞到红灯。
8. 一条编译坑值得单记：`Enumerable.Range(0, Readers).Select(_ => Task.Run(() => …))` 里
   `_` 是**lambda 参数名**，内层写的 `_ = snapshot.Any(…)` 不是丢弃而是给那个参数赋值——
   `bool` 赋给 `int` 时 CS0029 当场编译失败（运气好），同类型时就是**静默写真参数**。
   改成具名 `slot` 之后，丢弃面才真的是丢弃。
9. 验证：`dotnet test` Core **906 passed**（本批 +5）/ Broker **204 passed**（同一条发布链，
   记录面换型后 0 失败）；`pytest tests/python` **749 passed / 1 skipped**（本批不加 PY 用例）；
   `check_file_sizes`（现扫 553 个源文件，两份新 .cs 都要 `git add` 之后才进扫描面——它是
   `git ls-files` 口径）、`verify_text_anchor_helpers`（实现点仍 5 处）、表形 / 链接 /
   `check_doc_claims` / `check_workflow_shells` / `verify_ledger_queue_status` 全 EXIT 0。
   跑过 dotnet 之后按红线复查 `git status -- '*packages.lock.json'`：**零改动**。
10. 边界（如实）：本批消掉的是**已现读到的**三处并发枚举面，不是「C# 用例从此不会偶发红」。
    下一次同型红灯若来自别的记录面，锚不会替它红——它会红在那条用例自己身上，
    而那时的正确处置是照本条再收一处，而不是重跑一次当没事。

### 3.55 R9-B55（2026-10-14，队列 Q57-② 的处方回读）：「统一到 origDefineProp」不是收口，是一条被现读推翻的处方

1. 本批只做一件事：把 Q57-② 那句「三端『用哪一份定义器』不同形，统一到 `origDefineProp`
   形态才是完整收口」逐条回读。结论是**处方不成立**（不是「不想做」），三条现读事实：
   - **没有任何一端覆写 `Object.defineProperty`**：三端全部出货注入面
     （core 的 8 个 `src/**/*.rs` 共 30 处取用、`FingerprintShield*.cs`、`WebViewHardening*.kt` 10 处）
     里搜不到一处 `Object.defineProperty =`。既然没人换掉它，「用哪一份」就不可能产生行为差。
   - **注入都在 document-start**：Windows 是 `WebView2Hardening.cs:106`
     的 `AddScriptToExecuteOnDocumentCreatedAsync`，Android 是 `WebViewHardening.kt:55` 的
     `WebViewCompat.addDocumentStartJavaScript`（且 R9-AD-1 之后 Android 只有一条 document-start
     脚本，见同文件 `:45-52` 的注释）。⇒ 我们自己的脚本跑起来时，页面脚本**还没有机会**
     篡改任何东西，登记里那句「防页面前篡改」在这个时序下保护的是一个不存在的窗口。
   - **Windows 那次捕获的真实原因在别处**：`FingerprintShield.cs:64-66` 连着捕获
     `origGetOPD` / `origGetOPN` / `origDefineProp`，而它随后**确实覆写**了
     `Object.getOwnPropertyDescriptor` / `getOwnPropertyNames`（原型链反检测那一层，全仓只有
     Windows 有）。捕获是那一段的写法习惯，不是另外两端缺的一道防护。
2. 所以「统一」的代价与收益是：改掉 core 30 处 + Android 10 处**出货注入 JS** 的取用写法，
   换 0 个行为差、0 个安全增益；而真正有站点可观察后果的那半边（Q25-① 的六条高解析通道）
   仍然只能由真机/桌面冒烟证明——两件事不是一个量级，也不是一个方向。
3. 前提做成了**能红的判据**而不是留一段推理（`tests/python/injected_js_parity_test.py` +3 条）：
   - `test_nobody_overwrites_the_definer_the_ends_use`：扫描面现取（glob 四条，不是手抄名单），
     一旦任何出货注入面开始覆写 `Object.defineProperty`，本条红并点名「§3.55 的等价前提失效，
     Q57-② 必须重判」。判据留在这里的理由写在用例注释里：**判据红的时候人会来改结论，
     推理不会**。
   - 正面控制两条：同一个模式必须认出 Windows 真覆写了 `getOwnProperty*`（否则那个 Empty
     可能只是模式瞎了，而它瞎的方向恰好让「不用统一」永远成立）；以及模式单位控制——
     捕获形态 `var origDefineProp = Object.defineProperty;`、取用形态
     `Object.defineProperty(performance, 'now', d)`、比较形态 `===` 都**不能**算覆写
     （把取用认成覆写会让判据在正常代码上假红，而下一次让它变绿的动作就是放松前提）。
     两条都在内存态注入下跑红过一次（本机实测，不改文件）：给 Android 那个面拼一句
     `Object.defineProperty = function () { return 1; };` ⇒ 前提那条报「有出货注入面开始覆写」；
     把 Windows 的 `getOwnProperty*` 赋值替换掉 ⇒ 正面控制那条报「解释要重写」。
     也就是说这两条判据各有会失灵的形状，而不是恒真/恒假。
4. 顺带记下门禁面的一个真实缺口（不在本批修）：`contracts/codegen/verify_injected_js_parity.py`
   的三端扫描面只含 `shield.rs` / `shield/canvas.rs` / 三个 `FingerprintShield*.cs` /
   四个 `WebViewHardening*.kt`，比较的又只是 7 个共用函数——**installer 层（`timer_prec.rs`
   一族）根本不在它的对账面里**。所以「三端注入 JS 同形」这句话在 installer 层目前没有判据；
   Q25-① 落地时必须先决定比较面扩到哪，否则三端会在没人的地方各自漂。本批不顺手扩：
   一扩就要当场判 30+10 处的同形，那是 Q25-① 的活，不是这条处方回读的活。
5. 验证：`pytest tests/python` **752 passed / 1 skipped**（本批 +3）；`active_tree_gates all`
   （ruff / bandit / py312-compat）OK；行数红线（`injected_js_parity_test.py` 221 行 ≤300）/
   表形 / 链接 / `check_doc_claims` / `check_workflow_shells` / `verify_ledger_queue_status`
   / `verify_text_anchor_helpers` 全 EXIT 0；`verify_injected_js_parity.py` 本体现跑仍绿
   （本批没动任何注入 JS 文本）。**零出货代码改动**。

### 3.56 R9-B56（2026-10-14，队列 Q58 = R9-CS-18 的第一步）：把「量不到」写成事实，而不是写成待办

1. 为什么挑 Q58：它是队列里唯一一条 P2 且**卡在一次测量**上——Windows 的下载闸门判的是
   `CoreWebView2DownloadOperation.Uri`（`HostWebView.Downloads.cs:48`），而这条属性到底报
   「入队时请求的地址」还是「跟随 302 之后的落点」，SDK 没写：钉版包自带的 XML 文档只有
   `The URI of the download.` 一句（现读 `~/.nuget/packages/microsoft.web.webview2/1.0.2903.40/
   lib/net462/Microsoft.Web.WebView2.Core.xml`）。Android 侧 R9-B43 能复判，靠的是
   DownloadProvider 会改写 `COLUMN_URI` 这条平台事实；这边没有等价事实，照抄就是猜。
   本批的目标是**把这次测量从你的桌面挪进 CI**；结论是挪了一半，另一半挪不动，原因在下面第 4 条。
2. 落地的这一半：`windows/tools/WebView2SdkSurfaceProbe`（静态反射）+ `compat.yml` 的新 job
   `webview2-download-surface`。它每次重跑打印：SDK 程序集版本、Runtime 版本、下载相关类型的
   属性/事件面、以及全量 `*Download*` 类型清单。CI 首跑（run 38503503998，job 全绿）读到的事实：
   `sdk_assembly=…Version=1.0.2903.40`、`runtime_version=153.0.4234.48`、
   `PROP Uri : String`、`EVENT StateChanged : EventHandler`1`（事件共三个）、
   `TYPE_ABSENT CoreWebView2DownloadCompletedEventArgs` / `…DownloadCompletedHandler`、
   `SDK_DOWNLOAD_TYPE` 共 13 行。这把 R9-B37 那次「反射脚本的一次性结论」变成了每周重跑的面——
   上游哪天补上「完成后」那一族，这份报告会自己从 ABSENT 变成 TYPE，不需要有人记得去读 changelog。
   顺带一条 compat 本职要盯的事实也现读出来了：**runner 的 Runtime 是 153.0.4234.48，本机是
   155.0.4283.45**（v152 起两周一次节奏的正切样本）。
3. 它**不是** PR 门禁：compat 只有 `schedule` + `workflow_dispatch`（用例
   `test_probe_is_a_scheduled_probe_not_a_required_check` 把这条钉住）。理由是探测给的是事实表
   不是判决；把它挂进必需检查会造出「Windows runner 排队 = 全仓 PR 卡死」的形状。
   它红的时候，含义是「这份读不到了」，不是「代码错了」。
4. 挪不动的那一半，以及为什么写在这儿而不是埋在讨论里：动态场景真写过（不可见 WPF 宿主 +
   loopback 双端口 + `302 → 附件` + 一次性 `%TEMP%` 用户数据目录），本机跑到的结果是
   订阅事件那一步就抛：
   ```
   NotImplementedException: Unable to cast to Microsoft.Web.WebView2.Core.Raw.ICoreWebView2_4
       at CoreWebView2.add_DownloadStarting(EventHandler`1 value)
   ```
   即一次性宿主与出货 App 的宿主不是同一个环境（App 里同一行是好的），**探针造不出可信的下载场景**。
   据此动态那半代码删掉了——留一份跑不起来的双分叉在树里，比没有更坏。结论：
   「Uri 跟随不跟随重定向」只能在跑着的 App 里量 ⇒ Q58 仍开着，但它的下一步从
   「要先实测」变成了具体的量法（第 6 条），而且**为什么不能用一次性探针量**这件事有了可回读的原因。
5. 两处顺带的真实修复（都不是风格问题）：
   - `.gitignore` 原来写 `windows/src/**/bin/`——只点 `src` 的名。`windows/tools/` 第一次 build
     就把产物摆进了 `git status`（我 `git add` 时差点提交进去）。改成 `windows/**/bin/`，
     并把它做成能红的判据：`git check-ignore --no-index` 去问三个**还不存在**的假想路径
     （tools/src/tests 三种形状），配正面控制「探针源码本身不得被忽略」——否则「把 windows/** 全忽略」
     也能让那条用例全绿，那是白名单式规则的反向失效。
   - 探针**不建锁**是有意偏离而不是漏配：`verify_lock_rids.py` 扫 `windows/**/packages.lock.json`，
     而它的 `REQUIRED_*` 语义是「出货依赖面」——第一版给工具建锁，当场红在
     「缺 SQLitePCLRaw.lib.e_sqlite3 等 5 项」。代价是「探针量的就是出货那把 SDK」不能再靠锁保证，
     于是换成现读两个 csproj 的 `PackageReference` 版本对账
     （`test_probe_uses_the_same_sdk_version_as_the_shipping_app`）。
6. Q58 的量法（留给装机/桌面那一次，写细到可以直接照做）：在跑着的 App 内挂一个临时观察器，
   `GET /start` 返回 302 到**另一个 loopback 端口**的 `/final.bin`（附件 + 一小段字节），
   在 `DownloadStarting` 与 `StateChanged→Completed` 两个时刻各读一次 `Uri`；
   如果两次里有任何一次报的是 `/final.bin` 那条 URL，入队闸门就能改成「落点复判 + 必要时删除」
   （与 Android 同口径），否则必须走请求侧自行解析跳转（牵连 ADR-009 的制品形态）。
   两个端口而不是同端口不同路径，是为了让结论变成一次字符串比较而不是解释。
7. 验证：`dotnet build windows/tools/… -c Release -r win-x64` 本机 0 错误 0 警告；
   探针本机输出 `runtime_version=155.0.4283.45`（与 CI 的 153.0.4234.48 不同，两侧都记在上面）；
   `pytest tests/python` **759 passed / 1 skipped**（本批 +7）；`active_tree_gates all` 绿；
   `verify_lock_rids`（3 份锁）/ `check_workflow_shells`（27 个 pwsh 步骤）/ `check_file_sizes`
   / `verify_ci_trigger_surface` / 表形 / 链接 / `check_doc_claims` 全 EXIT 0；
   compat 三条 job 在 run 38503503998 全绿。**未动任何出货代码。**

### 3.57 R9-B57（2026-10-14，Q58 的桌面测量）：量到了，但量的结果把这条目的前提推翻了一半

1. 授权与路径：用户批准「跑一次桌面测量」。先试的是**不进桌面**的那条路（把测量塞进 compat 的
   Windows runner），失败原因见 §3.56 第 4 条——那次记的结论是「一次性宿主造不出可信下载场景」。
   **这条结论本批被推翻**：真正的差别不在宿主是否一次性，而在**装配路径**——
   裸 `CreateCoreWebView2ControllerAsync(hwnd)` 与 App 实际走的
   `WebView2` 控件 + `EnsureCoreWebView2Async` 不是同一条路，前者在订阅 `DownloadStarting`
   时抛 `NotImplementedException`（无法转型 `ICoreWebView2_4`），后者一切正常。
   教训按本仓口径记法：**「做不到」的结论必须先排除「我用了一条没人走的路」**，
   否则它会变成一个假的能力边界并写进台账（这次就写了）。
2. 测量本身（本机 Runtime 155.0.4283.45 + SDK 1.0.2903.40，三场景一次跑完）：
   两个 loopback 端口，origin 只发 302，target 只发 `Content-Disposition: attachment`；
   用不同端口而不是同端口两条路径，是为了让结论变成一次字符串比较而不是解释。
   ```
   RESULT S1 start[uri=…:7882/final.bin  state=InProgress] end[… state=Completed written=True]  verdict S1 start=final end=final
   RESULT S2（两跳 /start2 → /mid → /final2.bin）                                              verdict S2 start=final end=final
   RESULT S3（/page 里脚本 click() 一个 href=/start3 download 的链接 → /final3.bin）           verdict S3 start=final end=final
   ```
   三场景同一结论：**在 `DownloadStarting` 那一刻，`CoreWebView2DownloadOperation.Uri` 就已经是
   最后一跳的落点**，到 `Completed` 不变。窗口 off-screen + 透明、文件与用户数据目录都在
   `%TEMP%` 一次性目录里跑完即删（跑完复核 `~/Downloads` 无残留）。
3. 于是 Q58 的原命题**两头都不成立**，按 §六 结案：
   - 前半「闸门判的是入队地址」被测量推翻——被判的那个 `Uri` 就是跳转后的落点；
   - 后半「所以云元数据端点能落盘」也被现读推翻——那个落点会过
     `BrowserPolicyBroker.cs:111-127` 里 `AllowDownload` 的
     `ReservedAddressBoundary.DeniesRaw(origin)`（169.254/16 含 169.254.169.254、
     回环/私网按归一化后判定、**取不到绝对地址也一并拒**），这条正是第七轮 R7-CS1-02 补的。
     两端对齐也在：Android 侧同一形状由 R8-AD-03 落过（`WebViewDownloadTargetGuard` 一族）。
   原条目列的两个修法（完成后复判 + 删文件、或重做下载发起链）因此**都不需要**，
   连它们各自的代价（ADR-009 制品形态牵连）一起作废。
4. 本批自己犯的一次误读，按本仓口径记下来（它正是 Step-3 反复抓的那种形态）：
   我在读完 `DownloadPolicy.RequiresExplicitConfirmation`（只看扩展名与查询串，
   `Core/Downloads/DownloadPolicy.cs:46-50`）之后，一度写下「Windows 下载层没有保留地址硬拒、
   要新登一条 Q63」——**漏看了 broker 层那一道**。判据是「这条策略在哪个函数里」而不是
   「这个文件里有没有」；下载路径的判定横跨 `HostWebView.Downloads.cs` → `DownloadPolicy` →
   `BrowserPolicyBroker.AllowDownload` 三层，只看中间一层就会把已存在的东西报成缺口。
   那次误读在提交前被现读否掉，所以台账里没有 Q63 这一条——**没有的东西不该留号**。
5. 因此本批的可交付物是「一次能被别人重跑的测量」：`--redirect` 模式入仓（含三场景与卫生要求：
   off-screen 窗口、`%TEMP%` 一次性目录、跑完删、逐场景打印 `written=`），compat 仍只跑静态面
   （动态面要有浏览器宿主，属桌面实测面——这点没变，变的只是「桌面能量到」已被证实）。
   `~/Downloads` 跑后复核无残留。

### 3.58 R9-B58（2026-10-14，队列 Q60 = R9-AD-14）：写回面从「一个前缀」改成「调用方声明类别」，规则收进一份能被测的脚本

1. 用户裁决后的形状。Q60 登记时写的就是「改成可写 `dependabot/*` 就是放松一条已被用例钉住的
   写入面不变量 ⇒ 需用户裁决」，本轮批准按推荐做。落地的形状**不是**把内联那行的模式改成
   `deps/*|dependabot/*`，而是让调用方**声明这一类是什么**：dispatch 新增 `target_kind`
   （闭集 `deps` | `dependabot`），`kind=deps` 只写 `deps/*`、`kind=dependabot` 只写
   `dependabot/*`，两类**互斥**——选错 kind 不会悄悄写到另一类分支上（两个方向各有一条用例）。
   `dotnet` 这个 face 明确**没有** dependabot 面：NuGet/pip 的锁由 Dependabot 自己在 PR 里改，
   缺的只有 Gradle 的 sha256 那一面，所以 face=dotnet + kind=dependabot 直接 exit 2，
   `relock` job 的 `if:` 同条件跳过——**不假装支持**比支持一半稳。
2. 规则单源。写回守卫原来是六处内联 `case "$target" in deps/*)`（3 个持 `contents: write` 的
   job × 2 处步骤：job 级 + 写回级二次守卫），要把前缀改成「按 kind 选」就得抄六份能各自漂移的
   真相 ⇒ 收成 `scripts/relock_branch_guard.sh`，调用点只传参。`git diff` 现读被删的内联判断
   恰好 6 处；结构判据 `test_every_write_capable_job_calls_the_guard_twice` 从 yaml 数
   「有写回步骤的 job」并判每个 job ≥2 次调用——把守卫挪进 composite action 仍然算通过，
   **少一处**必须红。
3. **本批最值钱的一条是变异测试，不是那段脚本**。判法写真调 bash（不是文本锚），第一版只断言
   「exit 码 + stderr 非空」，跑 8 个变异有 **3 个活下来**，三个原因是三种不同的病：
   - 删掉整段主干检查（`master | main`）⇒ 全绿。因为 `master` 不以 `deps/` 开头，
     被最后那条前缀通配**顺带**拒了。脚本注释里「这一道是独立检查，不依赖上面那张表」
     因此是一句没人作证的主张——而它恰恰是防「有人把前缀表改成 `master`」的那一道。
   - 把 `refs/*` 窄化成 `refs/heads/*` ⇒ 全绿，同因。
   - 删掉「只有前缀没有名字」那段 ⇒ 全绿。这一条不是冗余而是**死代码**：直接 bash 现测
     `[[ "deps/" != "deps/"?* ]]` 为真 ⇒ `deps/` 在前缀那关就被拒，那段永远到不了，
     而它的注释写着「拼出来能过通配」——**注释是假的**。
   处理分两种，不是一律加断言：前两条**保留规则**但让它为自己作证——拒绝用例新增 `rule` 列，
   断言 stderr 含该规则的措辞，并补一条 `refs/remotes/origin/master`（专抓「窄化成 refs/heads」）；
   第三条**删掉死块**，注释改成「`?*` 已经要求前缀之后至少一个字符」并写明这段来历。
   第二轮 9 个变异：4/1/1/1/3/6/2/1 条失败，只有「把结尾日志换成裸 `exit 0`」全绿——那是
   **等价变异**（少一行日志，判定不变），不算漏洞。
   **等价变异也要记**：不记，下一个人会把「9 个变异全部被抓」当成判据密度的证据，而其中一条
   其实是判据覆盖不到的语义面（日志内容）——只是那一面本来就不属于这条守卫的职责。
   还有一条差点被我写进台账当证据：`exit 2`→`exit 1` 那个变异第一轮报「22 failed」，看着像
   抓得最狠，实际是我的变异脚本吞掉了一个引号、把文件改成了**语法错**（`bash -n` 当场红）。
   于是判据的「抓到」和文件的「坏掉」在输出里长得一模一样。改成先 `bash -n` 再跑，同一个变异
   的实数是 1 failed（就是 face 闭集那条）。**「测试变红」不等于「判据抓到了」**——
   与 §3.39/§3.54 记过的空心门禁同族，只是这次空心的是我自己刚写的判据。
4. 分支名的形状是**量出来的**：`gh pr list --json headRefName` 现读，本仓真实 Dependabot 分支
   的段数 3/4/5 都有——`dependabot/pip/cryptography-50.0.2`、
   `dependabot/gradle/android/minor-and-patch-0bc2cf4c4f`（group 更新）、
   `dependabot/github_actions/gradle/actions/dependency-submission-6.4.0`。
   任何「按段数限形」的规则都会把补录面对其中一部分真实分支关掉，所以脚本只认「前缀 + 至少一个
   字符」，这三条实测形态直接进允许面用例（而不是我自己编一个看着像的名字）。
5. 文档面五处跟着改口，动作统一是**改指向单源而不是再抄一个新值**：`SECURITY.md`、
   `README.md` 依赖面那一句、`android/settings.gradle.kts` 两处（其中 ③ 那句「重锁只写
   `deps/*` 而 Dependabot 的分支名不是它 ⇒ 缺口登记在 Q60」正是这条队列项的**现存证据**，
   现在它描述的是一个已经不存在的缺口）、workflow 头注 ② 与两处内联注释、以及 dispatch 输入
   `branch` 的 description（原文写「必须 deps/ 前缀」，现在前缀取决于 kind——输入框里的话
   也是判据的一部分，写错会让人以为传 `dependabot/…` 是非法输入）。
6. 验收口径的诚实交代。原条目要求「一条真实的 Dependabot gradle bump PR 必须在同一个 PR 里同时
   带来四把 `gradle.lockfile` 与 `verification-metadata.xml` 的 diff 且 CI 全绿」——本批**没有**
   这条：现树没有在途的 Dependabot gradle PR，也无法强制它开一条。落地的是「不需要人再手工补字节」
   这一件事（那是这条队列项存在的理由），实证走 dispatch，证据分支是**我自己建的**
   `dependabot/r9-b58-evidence`（从本批分支切出，再在其上删掉
   `androidx.annotation:annotation:1.9.1` 的校验和条目＝注入一次「新坐标没有条目」的真实后果）。
   为什么不直接用那条遗留的真实分支 `dependabot/gradle/android/minor-and-patch-0bc2cf4c4f`：
   它是 Dependabot 命名空间下的一条真实分支，跑成功会往里推提交——分支名形状已经被第 4 条那三条
   实测形态判住了，没必要借别人的命名空间换这点证据。
7. **但 dispatch 抓到的第一条不是「补没补上」，而是「守卫脚本在它该跑的那一刻还不存在」**。
   run **38520687580** 红在 `bash: scripts/relock_branch_guard.sh: No such file or directory`——
   三个 job 的 job 级守卫步骤原本排在「检出目标分支」**之前**（那是内联 `case` 时代的位置，
   内联代码不需要 workspace 里有文件），换成调用仓库脚本之后，同一个位置调的是一个还不存在的文件：
   runner 在第一次 `actions/checkout` 之前 workspace 是空的。
   当时的两条判据全绿——它们数的是「调用点存在且 ≥2 次」，没有一条判「调用点能不能执行」。
   这是本仓第 N 次同族收敛，形状很具体：**把一份内联逻辑搬进文件时，「搬动」改变的是执行前提，
   不只是可读性**（§3.50 的 `strip_comments` 搬到 shell 正文吃掉真实语句、§3.54 的「本地全绿不是证据」
   都是同一课的不同侧面）。
   修法：三个 job 的守卫步骤都移到 checkout 之后（写回前那一步的二次守卫位置不变——那一步本来
   就在工作区里跑），新增 `test_every_guard_call_sits_after_a_checkout` 判**顺序**本身；
   反向实证做过了：把 gradle 腿的守卫挪回 checkout 之前，这条新用例与那条数调用点的用例**同时红**
   （正面控制在这里是多余的，两条独立判据各自抓到）。
8. dispatch 实证两个方向（都跑在 `dependabot/r9-b58-evidence` 上，`ecosystem=gradle`）：
   - 反例 run **38522538725**（`target_kind=deps` 打到 dependabot 前缀的分支）：conclusion=failure，
     失败步骤是「校验目标分支」，日志正文 `❌ target_kind=deps 只允许写 deps/<名字>（收到：
     'dependabot/r9-b58-evidence'）` + `Process completed with exit code 2`，另两个 job `skipped`
     ——**红因是守卫的措辞而不是脚本缺失**，这条区别就是第 7 条换来的东西。
   - 正例 run（`target_kind=dependabot`）：见下面第 10 条的结果记录（补回被删条目并写回该分支）。
9. 本机验证：`tests/python/relock_branch_guard_test.py` 26 条全绿（6 允许 + 17 拒绝各带规则措辞 +
   3 结构：调用次数、调用顺序、脚本 `bash -n` 可解析），全量 `pytest tests/python`
   **785 passed / 1 skipped**（本批 +26）；`check_file_sizes` 现读拦下一条真事——
   `relock_sop_test.py` 在 HEAD 恰好 300 行（零余量），我把那条守卫断言写成多行消息后变 303 行判红
   ⇒ 改回单行同行替换（与 §3.54 的 `CoreDenylistPublisherTests` 同一口径：不是绕过红线，是同行换掉旧断言）。
   markdown 表形/链接/计数/队列状态/文本锚/触发面/active_tree_gates（ruff+bandit+py312）全过。
10. 正例 dispatch run **38522729632**（`ecosystem=gradle target_kind=dependabot`，
     分支 `dependabot/r9-b58-evidence`）结论 success，三个 job：`Gradle 重锁` success、
     `重算并写回依赖锁（dotnet）` **skipped**（face=dotnet 没有 dependabot 面，`if:` 生效）、
     `Gradle 校验和 windows 腿` success（`needs:` 串行照旧成立）。写回提交
     `ffbbd9c8`（作者 `aegis-relock-bot`）**只**动 `android/gradle/verification-metadata.xml`，
     `+5 / -0`——正是第 6 条删掉的那一个 `<component>` 块被逐字节补回
     （`annotation-1.9.1.module` 的 sha256 与删除前同一个值，组件数回到 501）；
     windows 腿随后无差异可写，所以分支上只有这一条机器人提交。
     于是「新坐标缺条目 ⇒ 没有自动补录路径」这句话在 Gradle 面已经不成立了：
     一条 `dependabot/*` 分支可以被 dispatch 授权补字节，写回面仍然只有一类前缀、仍然到不了 master。

### 3.59 R9-B59（2026-10-14，§四 第 11 项 ② 定稿 + 队列 Q21）：给两份原生向量一份共同信封，并把「平台能不能断这条」变成可推导的字段

1. 用户批准的形状是 **②**（加显式分区字段），不是 ①（把原生变体用例提升成 PR 必需检查）。
   两条都动过前提回读：①的代价是每条 android/** 与 Windows PR 都要跑一次带 `.so`/原生 DLL 的构建，
   而且它把「宿主产不出这一支」这件事变成用例永远抓不到的形状——用例照样绿，因为它断的是核心。
   ②的成本只有一句词表变更，换来的是**任何将来接手的平台执行者都必须声明自己覆盖哪一块**。
2. 落地的语义（写进两份文件的 `description` 与 `scripts/verify_vectors.py` 的注释，不留在提交信息里）：
   `platform_decidable=false` ＝「**宿主在自己的托管判定路径上产不出这一支**，所以平台用例断它是断不真的」，
   不等于「产品里没有这个分支」。实测三处支撑：
   `Aegis.Windows.App.csproj:34-56` 的 `GenerateNativePolicyCoreBuildMarker` 只在
   `-p:RequireNativePolicyCore=true` 时写 `true`，而 PR 必跑的 dotnet 用例面断言的就是
   `NativePolicyCoreBuildRequirementTests.cs:58` 的 `Assert.False(RequiredByThisBuild)` ⇒
   常跑配置里 `BrowserPolicyBroker.cs:285-286` 走 `NativeBridgeDenied("native_confirmation_core_required")`；
   Android 同形（`AndroidBroker.kt:270-286`：无 native core 时 `requestNavigationConfirmation`
   顺延 `evaluateNavigation`）； shipping/Release 才是另一回事（发布链验终物那条姿态串）。
3. **标签不是自由声明**——这是本批的中心判据：`NATIVE_VECTORS[...]["decidable_when"]` 是每条向量
   期望值的推导式（decision：`expected_evaluate != require_confirmation`；确认面整份是常量 false），
   门禁逐条判「标签 == 推导值」，另判两件事：不许**省略**（省略不得被读成默认可判定），
   不许**塌成一块**（全 true / 全 false 都红——塌成一块的分区不描述任何事实）。
   实测形状：43 条里 30 true / 13 false，确认面 5 条全 false。
4. 信封（Q21 那一半）：两份此前**没有共同头部**——decision 有 `version`+`description` 无 `protocol`，
   confirmation 只有 `protocol` 且把修订号焊在字符串尾巴（`aegis-native-navigation-confirmation-v3`）。
   现同形成 `protocol` / `version` / `description` / `vectors` 四键，confirmation 的修订号拆成
   `version: 3`（值来自原字符串，不是新发明的号）。顺手把三个「版本」的歧义写进 description：
   向量文档修订号、`NativePolicyCoreGate.ExpectedAbiVersion=4`、broker 握手串
   （`c_abi/mod.rs:246-253` 实测**只判非空**，向量传 `"1.0"`）是三个互不相同的计数。
   `expected_deny_code → expected_evaluate_code`：`MULTI_STEP_PREFIXES` 早就规定「按协议步骤命名」，
   而 deny 是**值**不是步骤，所以旧名违反的是这份词表自己的规则；两侧同批改（向量 7 处 + Rust 消费者）。
   **改名只落一半会怎样**是被实测过的：把一条向量换回旧名，Rust 用例当场
   `panicked at vectors_decision.rs:69 ... unknown_session_fails_closed: evaluate denial code`
   （`Value::Null` 去比真实码）——所以这条不是「相信同批会做」，是红了就给看。
5. 判据与元层的一处必然冲突（本批唯一的意外）：新用例
   `tests/python/native_vector_partition_test.py` 在**代码里**写出两份原生向量的文件名，
   于是 `verify_vector_consumers.py` 把它算成 PY 消费者、`CONSUMER_MANIFEST` 立刻报漂移——
   这正是 R9-B39 那条口径在起作用（注释不算，代码算）。处理是把它加进 `META_LEVEL`
   而不是改登记表：它判的是信封形状与分区自洽，不是「哪端实现了这个裁决」。
   同批把两处**数 META_LEVEL 成员**的散文（「那五个文件」「15 份」）改成指向集合本身——
   这类计数是第三次撞到的同一形状（§3.41/§3.45）。
6. Q53 第②档的状态因此要说准：**「要怎么闭」被定稿了，「平台执行者为零」这个事实没有被修掉**。
   登记表仍是 `{"RS"}`；将来任何一端真接执行者，它必须只覆盖 `platform_decidable=true` 的 30 条，
   且这条约束由 `verify_vectors.py` 常驻判住——不会再出现「补一份 C# 用例把 13 条断不真的
   `require_confirmation` 也断进去」那种假覆盖（§3.42 逐行否证过的就是这个）。
7. 验证：新增 17 条用例（8 条注入各断言**是哪条规则**红的 + 塌缩用例特意让推导式保持自洽，
   只有那条专门的规则能红 + 一条正面控制「追加合法 require_confirmation 向量必须仍绿」+
   范围、接线、两侧同改等）；`cargo test` 全量 **582 passed / 0 failed**（含两份原生向量用例）；
   全量 `pytest tests/python` **802 passed / 1 skipped**（本批 +17）；
   `verify_vectors` / `verify_vector_consumers` / ruff / bandit / py312 / 行数红线 /
   markdown 三件 / 队列状态 / 文本锚全过。

### 3.60 R9-B60（2026-10-14，现读发现的失活）：R9-B49 那次 dismiss 已经被下一次扫描重开——判据面从来不该建在它上面

1. 触发点是顺手的一次 API 读：并入 #197 之后照例看一眼 Dependabot 状态，现读
   `open=9 / dismissed=0 / fixed=3`（`gh api .../dependabot/alerts?state=…`，2026-10-14T08:46:08Z），
   编号 #12 #11 #10 #9 #8 #7 #6 #3 #2 与 §3.49 那 9 条逐一对上，
   `updated_at` 全部是 **2026-10-14T07:09:5xZ** —— 也就是 #197 squash 完成（07:09:20Z）后
   紧接着的那次扫描。**不是有人删了我们的处置**，是 Dependabot 的正常行为：
   只要 vulnerable 版本仍然可以在依赖图里解析出来，已 dismiss 的告警就会被重开。
   现读锁面正好给出这一条：`org.bouncycastle:bcprov-jdk18on:1.80.2=androidLintTool`，
   而 #12/#11 的范围是 `< 1.85`、#8 是 `>= 1.74, < 1.84`；同批 `1.85` 只出现在 `debugUnitTest*` 三条配置里。
2. 这件事真正值得记的不是那 9 条告警，而是**我们刚把「已在 GitHub 上 dismiss」写进了一份文档**。
   §3.49 的回读是有时间戳的（2026-10-13 16:15Z），那份分诊文档也是——所以它没有说谎；
   但它给读者的**印象**是「这批已经处置完了」，而这个印象的保质期是一次扫描。
   第八轮 R8-CI-06 抓的是「把判定写成已执行」，这次是同族的反向形态：
   **把一次执行写成了持续状态**。修法不是再点一次，而是把状态从「证据」降级成「可读但不可依赖」：
   `tolerable_risk` 的依据是 `verify_gradle_alert_scope_boundary.py` 那句现读结论
   （5 个坐标全在 `androidLintTool` / `ktlint` / `debugUnitTest*`，零命中出货与装机 classpath），
   它在告警重开之后依然成立、依然常驻判住——这正是当初把判据建在坐标归属而不是告警状态上的回报。
3. 因此本批只做两件小事，**不碰服务端**：
   - 分诊文档补一段带时间戳的现读（含机制、编号、范围与锁行证据），并顺手更正同一份文档里
     一个**不存在的枚举值**：`dismissed_reason=tnt` → 实际执行用的是 `tolerable_risk`
     （422 报错清单里根本没有 `tnt`）。留更正记录而不是静默改掉——一份安全处置文档写着
     非法枚举，读的人就没法复核当时到底做了什么。
   - ~~`gradle-dependency-insight.yml` 加一步现读并报告告警状态~~ ——**这条本批撤掉了**，
     原因是实测不成立：Actions 的 `GITHUB_TOKEN` 调 `GET /repos/{owner}/{repo}/dependabot/alerts`
     返回 **403 `Resource not accessible by integration`**（run 38542830575，权限里已写
     `security-events: read`；同一条命令在会话里用**用户凭据**跑则正常返回
     `open=9 / dismissed=0 / fixed=3`）。带着 `continue-on-error` 留着它，作业照样绿而
     日志里只多一段没人读的 403——「有报告」变成假象，比没有更坏。要接这条得配一个只读
     PAT（属新增凭据 ⇒ 用户决定），本批不配。
4. **要不要再处理一次那 9 条**升入 §四 第 12 项待用户定稿：①再 dismiss 一轮（同样理由，
   但下一次扫描还会重开，变成拉锯，且每次点击都是一次对外姿态声明）；②fix-forward——
   把 lint 工具面那份顶到 ≥1.85（动 AGP/lint 工具链版本面，牵连登记表与本文证据）。
   本批默认两个都不做。
5. **为了验证新步骤而跑的那次 dispatch，抓到了旁边那一步早就坏了**（run **38539285993**，
   failure）：失败点不是新加的告警状态步骤，而是它前面的「工具类路径闭包」——那一步写的是
   `python scripts/verify_gradle_alert_scope_boundary.py` 与 `grep android/*/gradle.lockfile`，
   而 job 有 `defaults.run.working-directory: android` ⇒ runner 找的是
   `android/scripts/…`（不存在），glob 也展不开。**自 R9-B49 加进来起这一步从没跑通过**，
   而它是 dispatch-only 诊断面：PR 面全绿，没人去看它红。
   更难受的顺序是：`grep … || echo "(零命中)"` 先执行，把「找不到文件」印成了一句
   看起来像结论的 `(零命中)`，然后最后一行才 exit 2——**日志里失败之前先有一条假陈述**。
   与本批第 2 条是同一族的第三种形态：§3.58 是「调用点存在但脚本还没被检出」，
   这条是「调用点存在但站在另一个目录里」，而它比 §3.58 更隐蔽，因为红的是一条诊断流而不是一条门禁。
6. 修法与判据（都进 PR 面，不再靠人记得跑一次 dispatch）：
   - 那一步加字面量 `working-directory: .`（ sibling 的做法是 `../scripts/…`；这里选前者是因为
     新门禁按**字面** cwd 解析路径，`${{ github.workspace }}` 判不到）；
   - 加「锁一把都没找到 ⇒ exit 1」的前置检查，而不是让 `|| echo "(零命中)"` 有机会把
     判定面塌缩说成一条结论（与 `verify_gradle_alert_scope_boundary.py` 的空锁 exit 2 同口径）；
   - 新常驻门禁 `scripts/verify_workflow_script_paths.py`：每条 `python <路径>.py` 必须在其
     生效 cwd（step → job.defaults.run → workflow.defaults.run）下真实存在；带 `${{ }}` 的
     路径**点名要求人工核**而不是放过——否则「把路径挪进表达式」就是绕过这条判据的合法通道。
     实树现读：16 份 workflow / 146 个 run 步骤全过；接进 `contracts.yml` 的
     `contract-source-of-truth`（紧跟被保护的那条 scope 门禁）。
   - 反向实证：把 `working-directory: .` 那一行删掉 ⇒ 门禁 exit 1 并指名那一步，
     用例里两条同时红（`test_real_tree_has_no_unexecutable_python_calls` 与
     锚住这一步的 `test_the_insight_step_that_started_this_is_now_executable`）；恢复后全绿。
     对照用例同样重要：`python ../scripts/verify_versions.py` 在 cwd=android 下必须**不红**，
     否则这条判据就只是「任何带路径的调用都可疑」。
7. 验证：新增 13 条用例（`tests/python/workflow_script_paths_test.py`），全量
   `pytest tests/python` **815 passed / 1 skipped**；ruff / bandit / py312 / 行数红线 /
   markdown 三件 / 队列状态 / 触发面（16 个 workflow 分类不变）/ 新门禁全过。
   Actions 侧的实跑结果记在下面第 8 条。
8. 第二次 dispatch（run **38542830575**，conclusion=success）把两件事都量出来了：
   - 修好的那一步**终于跑了它该跑的内容**：`=== 四把锁里命中工具的坐标 → configuration 归属
     （找到 4 把锁）===`，随后 `verify_gradle_alert_scope_boundary.py` 输出
     「[ok] 被 dismiss 的 5 个坐标仍只在工具/测试面：logback-core←ktlint；
     commons-lang3←androidLintTool；httpclient←androidLintTool；bcpkix←androidLintTool；
     bcprov←androidLintTool, debugUnitTest*×3」。对照第一次（run 38539285993）同一段位置
     写的是 `grep: android/*/gradle.lockfile: No such file`——「找到 4 把锁」这一句
     就是这一步此前一直在空转的证据。
   - 而**本批原本要加的那步现读告警状态，被这次 dispatch 否掉**（见第 3 条第二个 bullet 的
     撤掉记录：403 `Resource not accessible by integration`）。
     这是「dispatch 证据」的第二种价值：第一次抓到旁边的坏步骤，第二次抓到自己新加能力的
     边界——两者都不是本地跑得出来的。

### 3.61 R9-B61（2026-10-14，第八轮 R8-RS-13 的落地 + 一次接线时的现读自查）：宿主直传输入的规模上限必须待在分配之前

1. 这条登记挂了三轮却没动过，原因就在**它的登记形态**：第八轮 §七 记了 ID 与
   `文件:行号`，本轮 §六 尾部记了一句「**仍未修**，同于第八轮登记，不另立 ID」。
   「不另立 ID」＝不进 §五 队列＝不进任何门禁，于是每一轮审计都会重新发现它一次、
   重新「不另立」一次。本批把两半都做完，并把 §六 那句话改成指向本节的落点。
2. 现读两半（按当前源码，不引用第八轮的 `:219-228`）：
   - `core/rust-policy-core/src/ffi/mod.rs:299-302`：`hex_seed_to_bytes` 先
     `util::hex_decode(hex)` 再用 `try_into` 收口成 `[u8; 32]`。`hex_decode` 对**任意偶数长度**
     先 `Vec::with_capacity(len/2)` 再全量扫描 ⇒ 一条 1 MiB 的 hex 串先换来一次 512 KiB
     分配，而「长度不对」的判定仍落在解码之后。
   - uniffi 面 `FfiBroker::update_host_denylist(Vec<String>)`（`ffi/broker.rs:331`）对
     **条目数、单条长度、批次总字节三项都没有上限**。同一条名单走 C ABI
     （`c_abi/navigation.rs:261`）时由 `c_abi/mod.rs:31` 的 `FFI_INPUT_MAX_BYTES=64KiB`
     经 `read_utf8` 的有界扫描兜住；uniffi 面拿到的是宿主直传的已解析数组，没有对应兜底。
3. 修法（两处都把判定挪到 O(n) 面之前，**数字一个新造都没有**）：
   - `ffi/mod.rs:281` 新增 `HEX_SEED_CHARS = 64`，`:300` 进 `hex_decode` **之前**判
     `hex.len() != HEX_SEED_CHARS ⇒ None`。
   - `ffi/broker/denylist.rs:40` `MAX_ENTRY_BYTES = 256`（与 `broker.rs:77/90/95`、
     `ffi/mod.rs:160` 那四个 256 同口径，也与域名 RFC 上限相容）；`:50`
     `MAX_BATCH_BYTES = 64 * 1024`（与 `c_abi/mod.rs:31`、`ffi/mod.rs:155` 同值）；
     `:99` 单条长度进 `entry_shape_ok`，`:180` 批次总字节在 `trim()/lowercase` **之前**整批拒收。
   - 超限**整批拒收、快照一字不动**：部分写入会让判定读到一份谁都没登记过的名单，
     而拒收对宿主是可发现的（`accepted < input`，与形态校验拒收同一口径）。
   - 死条目那一刀补的是同一句话描述的形状：一条 10 KB 的「host」过得了字符校验，
     然后永久驻进活动快照，而它不可能等于任何被规范化的导航 host（域名上限 253）——
     「已登记但永不生效」比不登记更坏。
4. **上限会不会把真实名单拒掉**——这是本批唯一能静默变成安全回归的方向，逐面现读：
   - Windows 宿主（唯一的在仓调用方）在 `NativePolicyCoreBridge.Denylist.cs:39` 按
     `MaxChunkPayloadBytes = 60 * 1024` 切批，`EnumerateBatches` 的逐元素计费取
     `SerializeToUtf8Bytes(host).Length + 1`（= 原始字节 + 2 引号 + 1 逗号），
     所以一批的**原始 host 字节和 < 60 KiB < 64 KiB**，永不触界。
   - C ABI 面按构造也触不到：入口载荷就是那个 JSON 数组本身，`read_utf8` 判的是
     含括号/引号/逗号的**整段 JSON** ≤ 65536 字节 ⇒ 解出的 host 字节和必然更小。
     这条上限只对 uniffi 直传生效，正是 R8-RS-13 指的那一面。
   - Android 侧现读**没有任何黑名单接线**（`android/app/src/main` 全树 grep `denylist`
     零命中，与 README「未接线」面和 §五 相应队列项一致），因此不存在第三个推送方。
   - 反向对照留成用例：恰上限（2048×32=65536）全收、超 1 字节整批拒收、
     同一份名单拆成两批则两批全收——分批协议（⑨）不受影响。
5. 一条被现读推翻的处方：**不给 `util::hex_decode` 加长度上限**。它看着像「单源收口」
   的正解，但 `session_state.rs:60-62` 合法地在解 1 MB 级 hex——RS-260 当初把
   `MAX_JSON_BYTES` 抬到 `1_125_000` 就是为了 512 KB 状态字节 hex 编码后的往返；
   在公共解码器上加 64 KiB 会**静默打断会话恢复**。判定该待在入口，不在公共件。
6. 能红判据为什么建在文本锚点：「先判长度」与「先解再判」**返回值逐字相同**，
   唯一区别是一次分配发生的时机。计数式 `#[global_allocator]` 能钉住它，但那是把 CI
   挂在 harness 自身的分配噪声上——R9-B54 刚为同类 flaky 红灯付过一整批。于是分两层：
   - 行为面（能红的是**裁决**，不是时机）：`core/rust-policy-core/tests/hex_seed_bound.rs`
     2 条——只有定长种子被解出（1 MiB / 8 MiB 输入拒）、两个宿主可见管线入口对超长种子
     返回空脚本，各配正向对照；`denylist/tests.rs:180/209/221` 3 条钉 256/257、恰上限、
     超 1 字节整批拒收（含「拒收后不留半开会话」）。
   - 判据面 `scripts/verify_ffi_input_bounds.py`：按剔注释口径（`text_anchors.py` 单源，
     R9-B39 / R9-B45）判四件事——守卫排在 `hex_decode(` 之前；`HEX_SEED_CHARS` 与函数
     签名里的 `[u8; N]` 是同一个数（从签名反推 `N*2`，防「护栏与契约不是同一个数」）；
     批次判定排在 `host.trim()` 之前；三面 64 KiB 同值 + 256 与那四个常量同值
     （数字各抄一份就是下一轮的漂移面）。
   - 12 条注入式反向锚（`tests/python/ffi_input_bounds_test.py`，不改工作树）：守卫挪到
     解码后 / 守卫被注释掉 / 常量改 66 / 单条上限删掉 / 批次块挪到 trim 之后 / 整块删除 /
     任一面漂到 32 KiB / `MAX_ENTRY_BYTES` 漂成 512 / 锚点改名 / 文件缺失——逐条摆上去必红。
     其中一条反向对照必须**不红**：三面**一起**改成 32 KiB 时判据为空（一起动是改口径，
     只动一面才是漂移）。
7. 反向实证（不止靠注入用例）：临时删掉 denylist 两处上限 ⇒
   `oversized_entry_is_refused…` 与 `one_byte_over_the_cap…` FAILED，而「恰上限全收」那条
   仍绿；恢复后 `ffi::broker::denylist` 10 条全过。没有这一步，「加了判据」与
   「加了一条永远绿的判据」无法区分。
8. **接线时的现读自查**：给上面这条门禁接进 `contracts.yml` 时发现，R9-B60 自己那一步
   （连同 6 行注记）在同一 job 里被写了两遍（第 1 步与第 19 步），来源是 commit `834520c`
   那次并入。症状不是红，是**门禁跑两遍**＋两份在不同批次各自漂移，而 §3.60 只记了一处
   「接进 contracts.yml」——读的人以为只有一个。副本已删，并做成常驻判据
   `scripts/verify_workflow_step_duplicates.py`（紧跟 R9-B60 那条接进同一 job）。口径三条
   选择与被否的备选：
   - 判**同一 job 内**：`dependency-relock.yml` 的三个「检出目标分支」分属三个持写权限的
     job，守卫必须逐 job 写（R9-CI-2 同口径），跨 job 同体不是重复。
   - 判**整步骤同体**（剔掉 `name`/`id` 后逐字相同）。备选「同一条 python 调用在同一 job
     出现两次」本批实测会报 6 个 job，其中 **5 个是合法重复**（`active_tree_gates.py` 分
     ruff / bandit / py312 三次、`release.yml` publish 步两条脚本各跑两次、
     `release-android.yml` 的 `../scripts/verify_versions.py` 两次……），只有 contracts.yml
     那一个是真的 ⇒ 误报机器不入库。
   - 不判「同名不同体」：Actions 允许步骤重名，「注记同一段话抄两遍」不在这条射程里。
   - 5 条用例（`tests/python/workflow_step_duplicates_test.py`）：现树全绿 + 扫描面不塌缩
     （16 份 workflow / 324 步）、把 R9-B60 的形状摆回内存必红、两条反向对照（跨 job 同体、
     同脚本不同参数都不报）、`run` 多一行即不算重复（防判据退化成「名字撞了就红」）。
9. 行数红线：`ffi/broker.rs` 的导出面注记压成 1 行（理由单源在 `denylist.rs`，抄一份
   就是第二份漂移面），仍在基线 935 内；`ffi/mod.rs` 797 → 809（1 行 const + 5 行顺序
   理由 + 3 行守卫），基线用 `--write-baseline` 重建后**人工 diff 确认只有这一项变化**
   再入库。
10. 验证：`cargo fmt --check` / `cargo clippy --locked --all-features --all-targets
    -- -D warnings` / `cargo test --locked --all-features`（lib 585 条 + 各集成面，含新增
    2 条）全过；`pytest tests/python` **832 passed / 1 skipped**（本批 +17）；ruff / bandit /
    行数红线（现读 561 个受管源文件、基线 86 项）/ 触发面（16 个 workflow 分类不变）/
    workflow 路径门禁（147 个 run 步骤，比 §3.60 记的 146 多一步就是本批这两条新门禁的
    净增）/ 两条新门禁全过。
11. 未做的两件事，写清楚以免下一轮当成已做：①uniffi 面仍只有整批替换一档（分批档位只在
    C ABI 面；R7-RS-03 登记的生成绑定滞后是另一条线）；②上限本身可判，但**宿主如何发现
    自己被拒**只有 Windows 侧成立（`CoreDenylistPublisher.Report` 已有
    `Accepted/Input` 与 `PartiallyPublished`），Python 绑定面与任何 uniffi 直传方都没有
    等价复检——那属接线面，不在本批射程。


### 3.62 R9-B62（2026-10-14，一族三次事故的通则化）：「门禁脚本存在」与「门禁脚本在某个面上被执行」是两件事

1. 这批不是新 bug 的修复，而是**把同一形状收成判据**。三次事故各自的落点：
   R9-CI-4（`verify_xaml_resources.py` 的唯一调用点在 tag 触发的发布流里，PR/push 面零执行，
   四条 pytest 用例又全部 monkeypatch ⇒ 常跑面只证明机制、不证明现树）、AEG-006（向量
   「有形状校验、零真实消费者」）、R9-B60（`gradle-dependency-insight.yml` 那条诊断步骤自
   R9-B49 起就站在错的 cwd 里、从没跑通，而它是 dispatch-only 面，PR 全绿没人去看它红）。
   三次的共同点是**判定写好了、执行面没人核**，每次都靠下一轮人肉现读才发现——所以本批
   把「谁在哪个面上跑它」变成一份登记表加一条常驻判据。
2. 现读执行面（全部按当前字节，不引用任何前轮结论）：16 份 workflow 里 **7 份有
   `pull_request` 触发**（agent-redteam / android-quality / ci / contracts / core-rust /
   native-policy-artifacts / supply-chain）；受管门禁脚本 **35 支**（`scripts` 25 ＋
   `release` 5 ＋ `contracts` 5），其中 **29 支**从 PR 面的调用点可达、**6 支**不可达。
   不可达那 6 支全部登记在册（`contracts/ci/gate-execution-face.yaml:21/29/38/46/54/62`）。
3. 表里两种 `face` 语义不同，别混：`ci` ＝ 有真调用点、但那条流不在 PR 判定面上（发布链与
   探测面，输入在被判时还不存在）；`manual` ＝ 连 CI 执行点都没有、只有 runbook 里一条人跑的命令，
   比 `ci` 更弱，所以登记时必须写清为什么不能进 CI。`why` 非空是硬判据：它是这张表唯一的
   可读信息，也是下一轮判断「该撤还是要动」的依据。
   其中 `release/verify_checksum_json.py`（`:29`）是本轮**新登记**的一支——它此前从没在任何
   面上被登记过，而它正是下面第 4 条那两个备选口径会被判成「可达」的那一支。
4. 三条口径都是**在实测里被逼出来的**，两条备选被数字否掉：
   - **执行点只取 `run:` 正文**（含沿本地 `uses:` 传递的 composite action / 可复用 workflow）。
     同文件对照就是证据：`release.yml:188` 是真调用（算），`release.yml:195` 是把命令抄成
     注记的那一行（不算）。按原文正则判，`verify_artifact_set` 会当场获得一条「CI 执行点」，
     而 runner 上从没执行过它——这条判据就会假绿。
   - **闭包只走非测试文件**（`verify_gate_execution_face.py:46` 的 `TEST_PATH`）。备选
     「允许穿过 `tests/python/`」实测把可达面从 29 抬到 **32**，多出的正是那三支
     `release/tools/*`——它们只被测试 import。`tests/python` 整目录被一条 pytest 步骤收集，
     允许穿过它，「可达」就膨胀成「凡被 import 过的都算跑过」，判据恒真；而 R9-CI-4 的事故
     形状恰好就是「用例全绿＋门禁从没判过现树」。
   - **文件内引用只取 AST 里会进入代码的字符串与 import 名**（`:65-79`：注释天然不在 AST，
     docstring 单独剔）。备选「按原文正则数 `.py` 字面量」实测把可达面从 29 抬到 **30**，
     多出的那支是 `release/verify_checksum_json.py`——它在 PR 面上根本没有调用点，只是被某个
     可达文件的注记提过一次名字。这条口径的教训本仓早就写过：`scripts/text_anchors.py`
     的实测条目 2 记着「docstring 里逐字写了被观察的文件名，于是向量门禁立刻报出新消费者」。
     所以本小节与判据 docstring 里出现的这些文件名**不会**成为调用点，是设计而非漏洞。
5. 判据本体拆成两份，不是审美而是红线逼的：`scripts/workflow_run_face.py`（86 行，只做提取——
   `run:` 正文、本地 `uses:` 传递、生效 cwd 复用 `verify_workflow_script_paths.effective_cwd`）
   ＋ `scripts/verify_gate_execution_face.py`（251 行，只做判定）。第一版单文件 350 行超了
   「基线外新文件 ≤300 行」红线，而 `check_file_sizes.py` 对这种情形的处方就是拆分
   （存量超限才走 `--write-baseline`），没有给新文件开豁免。
6. 判红的六类形状（`violations` `:184-209` ＋ `entry_problems` `:141-178`）：不可达而未登记、
   同一支登记两次、已可达却留在表里（该撤登记）、`face` 不在 ci/manual 词表内、该带的
   `workflow`/`evidence` 缺了或不该带的乱填、证据不实（ci 类那条流的正文其实没调用它／manual 类
   那份文件里根本没有那条命令路径）。判定面塌缩（workflows 目录或登记表缺失、解析失败、
   受管面或 PR 面入口为空）走 **exit 2**，不写成「读不到东西＝通过」。
7. 反向证伪：21 条用例（`tests/python/gate_execution_face_test.py`，全部内存注入、不改工作树），
   其中两条**不靠注入**、直接拿现树做对照——`:144` 钉住「同一份 release.yml 里 188 行算执行点、
   195 行不算」，`:152` 钉住「docstring 里的文件名不算调用点、代码字符串里的算」。
   没有这两条，判据可以在「其实是按原文正则算」的形态下全绿。另有两条 exit 2 用例把
   登记表缺失与 workflows 目录缺失分别摆出来。
8. 接线时顺手现读改掉两条陈旧路径引用（都是 `release/tools/` 目录化改版留下的平铺旧路径）：
   `release/verify_release.py:20` 注记里的 `release/tools/verify_manifest.py:18`（文件已搬，
   且它锚的是仓库根、与本文件锚 `release/` 并不「同一模式」，注记顺带改准）；
   `release/manifests/signing-policy.yaml:32` 的 `release/tools/verify_provenance.py`。
   被否的处方：**不做全树「文档里的仓库路径字面量必须存在」判据**。实测全树 629 条路径字面量
   里 14 条悬空，其中 **11 条是合成夹具**（`agent/a.py`、`scripts/x.py`、
   `scripts/no_such_gate.py` 这类用例自己造的名字）⇒ 那是误报机器。射程收成本批这一条
   执行面判据＋这两处定点修正。
   登记这两行时还自撞一次：新行先写成 `R9-DOC-20`，而 R9-B33 那批早已占用该 ID（Q49
   `docs/runbooks/device-validation.md` 那条），自家
   `tests/python/gate_hollowness_test.py::test_ledger_csv_ids_are_unique` 当场判红（重号会让
   下一轮「按 ID＋位置＋现象去重」把第二条当已登记直接跳过）⇒ 改成 `R9-DOC-21`。
   「绿本身不是结论」这条纪律对本批同样成立：判据在写台账的这一步就拦了一次。
9. 验证：`contracts.yml` 的 `contract-source-of-truth` job 现读 39 条 python 门禁步全部退出 0
   （新那条在第 20 位）；`pytest tests/python` **853 passed / 1 skipped**（本批 +21）；
   ruff / bandit / 行数红线（566 个受管源文件、基线 86 项、两份新文件 251＋86 行都在红线下）；
   触发面分类不变（gates 6 / builds 5 / probes 5）；workflow 步骤面 324 → **325**、
   run 步骤面 147 → **148**，各净增一条，正是本批这条门禁。
10. 未做的两件事，写清楚以免下一轮当成已做：①执行面口径只认 `python <路径>.py`，pwsh /
   gradle / cargo 调用点不在射程内——某支门禁若只被 pwsh 脚本调起，它会落进「不可达」一侧、
   被要求登记并给出证据，退化方向是安全的，但那张表不会自动认出它的真执行面；
   ②本批判的是「不可达要留痕」，**没有**判「不可达这件事本身该不该存在」——把发布链那几支
   挪进 PR 面是接线决策（要人定代价），不在本批射程。


### 3.63 R9-B63（2026-10-14，把 R9-B61 那条通则问完整个导出面）：上限不只该管「分配」，也该管「存」与「回声」

1. 这批不是又找到一个 bug，而是**把上一条通则的射程问全**。R8-RS-13 挂了三轮、R9-B61
   终于把它落地成「先判长度再分配」，但那条判据当时只覆盖它自己的两个落点（种子解码、
   黑名单批次）。本批把同一个问题逐入口问一遍：**宿主直传进来的东西，有没有哪一条既没判长
   就被存下来，或者被写进给宿主看的文案里**。答案是两处，且两处都不是「分配」那一型。
2. 现读枚举口径：不按源码注释数导出面，按**入库的绑定产物**数——
   `core/rust-policy-core/bindings/aegis_policy_core.py:1371-1463`（`FfiBrokerProtocol`
   的 9 支方法）＋ `:1472`（构造子）＋ `:1868-1969`（5 支自由函数）＝ **14 个入口**，
   与 `scripts/verify_uniffi_binding_surface.py` 对账的那份符号集合同源。逐入口把宿主可传
   参数分成四类（已判 / 传递性有界 / 无界但只查表 / 无界且会存或回声）：
   - `try_parse_external` `canonicalize_external` `extract_host`（`ffi/mod.rs:170/179/193`）
     三条走同一条 `ffi_url_length_ok`（64 KiB）；
     `build_fingerprint_pipeline(_with_mode)`（`:219/:260`）走 R9-B61 那条定长种子判定＋
     `MAX_PIPELINE_DOMAIN_BYTES`；
   - `create_session`（`ffi/broker.rs:520`）会话键 256（RS-223）已判；
   - `request_navigation_confirmation`（`:371` 块）委托 `evaluate_navigation`，
     由被委托方判 ⇒ 传递性覆盖；
   - `reject_navigation_confirmation`（`:487`）与 `destroy_session`、
     `advance_document_generation` 返回 `bool`，**没有回声面**；`approve` 的 `nonce`
     只作查表键、四条 deny 文案全静态；
   - 缺口两条：**构造期 `policy_version`** 与 **`evaluate_navigation` 的
     `session_id`/`tab_id`**。
3. 这两条为什么是真缺口：
   - `policy_version` 会被 `clone()` 进**每一条签发的授权**（`ffi/broker.rs:233`），
     账本上限 `MAX_ISSUED_ACTIONS`＝50 000（`:58`）⇒ 一份宿主输入换成 50K 份驻留。
     C ABI 那条 64 KiB（`c_abi::FFI_INPUT_MAX_BYTES`）是为「指针没有 NUL
     终止就无界越读」设的**读**口径，不是**存**口径——uniffi 面的 `String` 由宿主直接
     交进来，而那一面本批之前连「存」这个概念都没有；C ABI 侧本批之前只判空串。
   - 会话键：账本里的键之所以有界，靠的是「池键 ≤256 ⇒ 长键必然查不到」这条**间接**理由；
     而「查不到」恰恰是核心层把这条未判长的原串写进 detail 与 explanation 各一遍的那条路径
     （`core/broker.rs:333-339`）。对照同一份核心层对 nonce 就写得规矩——
     `consume_nonce`（`:429-442`）既判长（`MAX_NONCE_LENGTH`＝128）、文案里只放长度数字，
     所以本批**不动 nonce**，把它当已经写对过的先例。
4. 落地形态：判定收进 `core/rust-policy-core/src/ffi/broker/input_bounds.rs`（92 行）
   而不是留在三个入口各写一遍。理由不是整洁——`raw_url` 那条上限此前在
   `evaluate`/`approve`/`consume` 里内联了三份逐字相同的代码，而 R9-B61 的第二判据拦的
   正是「同一件事写两遍」。三个调用点：`ffi/broker.rs:165`（会话键＋scope＋URL 三段）、
   `:410` 与 `:595`（只判 URL）。构造期那半同理：两面共用一个
   `FfiBroker::policy_version_ok`（`input_bounds.rs:39`），C ABI 据此返回 null
   （`c_abi/mod.rs:251`），uniffi 构造器签名不可失败、据此退回 `DEFAULT_POLICY_VERSION`
   哨兵（`ffi/broker.rs:718`）——收成一个谓词是因为 `c_abi/mod.rs:270` 走的就是
   `FfiBroker::new`，一处改两面生效。
   **口径不变**：拒绝码、判定顺序（会话键 → scope → URL）、空 URL 归
   `canonicalize_external` 判这三样逐字沿用本批之前形态；换码等于换契约，不在本批射程。
5. 三条备选处方被否掉（留此防下一轮重提）：
   ①**给 `contracts/schemas/action.schema.json` 的 `policy_version` 加 `maxLength`**——
   现读该 schema（乃至全仓契约面）**没有任何一处**用 `maxLength`，加它等于开一个新约束维度，
   要三端再生成＋漂移判据；而 256 这条口径本来就在 Rust 侧的短标识符族里（会话键、scope、
   管线 domain、脱敏 host、黑名单单条都是 256）。
   ②**版本上限取 64 KiB**（跟「读」口径同值最省事）——那样 64 KiB×50K 条账本仍是驻留面；
   版本标签的真实取值是 `contracts/policy/action-catalog.yaml` 的 `"1.0"`，256 已是 128 倍余量，
   再长的东西就不是标签而是载荷。
   ③**deny 文案放整串或放前 N 字节**——只放长度数字。判据口径是一句话：
   拒绝一个 N 字节的输入，不该回一条不比它短的文案，**放大即缺陷**。
6. 门禁扩展：`scripts/verify_ffi_input_bounds.py` 227 → **267 行**，判据从 4 条涨到 6 条。
   新增的判据 5 判「单源＋位置」：谓词存在、两面都引用它（任一面退回自己判 `is_empty` 即红）、
   且走在 `FfiBroker::new(` 与 `Self {` 之前。判据 6 判回声面：判定体里三个输入只许以
   `.len()` 形态出现，且字面量里的 `{var}` 内插单独立一条——因为「剔除字面量再找标识符」
   与「字面量内部的内插」是两种不同的漏法，一条判据盖不住（实测：只判前者的话，
   `{session_id}` 这种写法全绿）。`broker.rs` 里再出现 `MAX_FFI_URL_BYTES` 也算红。
   读 Rust 源的四件通用事（键／剔注释／函数体／`usize` 常量）抽进
   `scripts/rust_code_reader.py`（73 行）——两条新判据都写进原文件就越过 300 行红线，
   抽取后门禁留在 267 行；与 §3.62 第 5 点同一情形、同一处方（存量超限才走
   `--write-baseline`，新写文件一律 ≤300）。剔注释口径仍单源
   `scripts/text_anchors.py`，本模块只把「读文件」这一步接上去，所以
   `verify_text_anchor_helpers.py` 的实现点集合不变（现读 5 处，实测绿）。
7. 反向证伪（每条都真红过）：
   - Rust 侧 5 条用例（`ffi/broker/ffi_navigation_tests/input_bounds.rs` 4 条＋
     `c_abi/tests/buffer_boundaries.rs` 1 条）：超长版本串既不进载荷也不进账本（白盒读
     `broker.issued_actions` 确认生效的是哨兵）、卡在 256 上界的版本串逐字保留、
     超长会话键被拒且**两个账本都没被碰**、卡在 256 的会话键仍可正常导航。
   - 两次临时变异证明「能红」：①把会话键守卫短路 ⇒ 新用例红在 `session_not_found`
     且 detail 里出现 `会话 sss…` 原文（这就是回声面的原形态）；②把长度项从谓词里删掉 ⇒
     两条用例红、而 256 边界那条**仍绿**——证明「有上限」与「上限管住了长」是两条独立判据。
     两处变异都已还原。
   - python 侧 11 条注入用例（新文件 `tests/python/ffi_input_bounds_face_test.py`）＋
     主文件扩到的 12 条，全部内存注入、不改工作树。
8. 本批自撞三次，都记下来：
   ①回声断言最初写 `tab = "t"`，而文案里有「tab」这个词 ⇒ `"t" in detail` 恒真，
   一条断言静默失效。改成只对**超长那一侧**断言，并把这次近失写进用例注释。
   ②文案长度上界最初写 `text.len() <= 4 * cap` 这种魔数 ⇒ 放大 1024 倍也判不出来，
   改成 `text.len() < oversized.len()`。
   ③**最值得留的一条**：三条注入锚点最初是从**带注释的源文件**逐字抄的，而门禁读的是
   剔注释后那份 ⇒ `replace` 静默失配，用例变成「什么都没注入也通过」的假绿。门禁本身
   现读是绿的，所以这条只会在用例面暴露——它是 R9-B39（§3.39）与 R9-B44（§3.44）同一课
   的**第三次**撞上，前两次分别教训的是「判据被自己的注记喂绿」与「用例里的文本锚同病」，
   这次是「注入锚点与判据读的文本不同一份」。修法不写成纪律而写成代码：
   `inject()` 把「锚点必须咬得住」做成断言，换不动立刻红。
9. 拆分与红线实况：`ffi/broker.rs` 935 → **909**（−26，判定搬走），基线同批收窄
   （`check_file_sizes.py --write-baseline`，`git diff` 只有这一行）；`c_abi/mod.rs` 仍
   318；`buffer_boundaries.rs` 166 → 183；`ffi_input_bounds_test.py` 152 → 169，
   本批一度涨到 324 越过红线的**基线外 ≤300**那一条，拆分依据是**判据所属的面**
   （分配前 vs 存／回声），不是批次号——新文件
   `tests/python/ffi_input_bounds_face_test.py` 194 行。
10. 验证：`cargo test --lib` **590 passed**（本批 +5）；`pytest tests/python`
    **864 passed / 1 skipped**（本批 +11）；`contract-source-of-truth` 现读 37 条 run 步骤、
    其中含 `python` 的命令行 **39** 条（与 §3.62 同单位）——除 pip 安装步外**逐条实跑**、
    全部退出 0（含 `verify_contract_compatibility.py` 那条三步合并步里的第三腿）；
    本批未新增 CI 步，步骤面不变（16 份 workflow／148 条 run 步骤，
    执行面 35 支受管门禁＝29 可达＋6 登记）；
    ruff／bandit／py312-compat／行数红线（569 个受管源文件、基线 86 项）／
    文档计数／workflow 路径与步骤重号全部 OK；
    门禁自己的 ok 行现读：批次口径三面同值 65536 字节、短标识符口径 **5** 份同值 256 字节
    （族里从 4 份涨到 5 份正是本批加的那条）。`cargo fmt` 与 `cargo clippy --all-targets` 干净。
11. 未做与边界（写清以免下一轮当成已做）：①**uniffi 面仍未接线**（ADR-009 出货两端都走
    C ABI），本批在 uniffi 侧的收益是把两面的口径写成同一份、不再是「C ABI 有、uniffi 没有」，
    不是给宿主新增一条运行时防线；②`policy_version` 的 schema 约束没加（见第 5 条①），
    若日后要加属契约决策；③nonce 无界但只查表这一判定是**本批的推理**而非新判据，
    判据面没有钉住「nonce 文案只放长度」——钉它要先钉住 `MAX_NONCE_LENGTH` 那一族；
    ④`scripts/verify_uniffi_binding_surface.py:56-69` 的 `_brace_body` 与
    `rust_code_reader.fn_body` 同形（差别只在失败值 `""` vs `None`），本批**没有**合并它，
    已作为 Q63 登记在 §5.2.1。


### 3.64 R9-B64（2026-10-14，队列 Q63 = R9-CI-18）：数「第二份实现」的门禁，看不见写成正则常量的那一份

1. 本批只动判据面、不动 Rust 出货代码。Q63 的三条验收判据各自先量再选形状，没有按
   「都换成共用件」这句话直接做——那条处方在②上是错的（见第 4 点）。
   起因的形状是 R9-B45 那次收敛（散在 14+ 份的注释过滤收成 Python／C#／Kotlin 三份单源）
   配了一条常驻门禁 `scripts/verify_text_anchor_helpers.py`，判「实现点集合＝登记集合」；
   但 `MARKERS`（`:51-62`）认的是**字面量调用形态**，而
   `scripts/verify_uniffi_binding_surface.py:43` 把注释形态写进一个 `re.compile` 常量 ⇒
   扫描面走过了这个文件却一条都不匹配 ⇒ 仓里有第 6 份自己写的注释过滤而门禁全绿。

2. 判据①（`_code` 并进单源）——先证等价或更严，再动：
   - 逐文件把两种剔注释文本喂进**同一个**解析器比对导出面三面（方法／构造子／自由函数）：
     现读 `core/rust-policy-core/src` 全树 **78 份 `.rs`，0 份判定不同**；入库绑定
     （`core/rust-policy-core/bindings/aegis_policy_core.py`，2005 行，面为
     9 方法＋1 构造子＋5 自由函数）raw 与剔注释后**符号集合相同**（今天没有符号写在注释里）。
   - 但「等价」不等于「无所谓」——单源**更严**：合成语料实测旧口径在「跨行块注释、续行不
     带星号」里会凭空造出一个只存在于注释里的自由函数，门禁于是判「绑定缺方法」，是一个
     **假红**；而假红最容易被做的处置是改判据而不是改代码，那正是空心化的入口。
     所以按 Q63 两案取第一案（并进单源、删本地实现），不取「登记进 `ALLOWED` 当第 6 处」。
   - `exports_from_src(text, path)`（`:64`）与 `surface_from_binding(text, path)`（`:96`）
     的 `path` 只管一件事：`#` 形态在 Rust 是属性行、在 Python 才是注释。用例
     `tests/python/uniffi_binding_surface_test.py:113` 钉的就是同一份文本在两种 `path`
     下的判定差。旧 `_code`  docstring 写的「保留行号便于人肉对照 file:line」在本模块
     **没有任何消费者**（判定消息只报名字不报行号），随行号一起删掉——记在这里是因为
     下一轮若要把消息改成带行号，就得先解决「块注释匹配会移动行号」这一条。

3. 判据③（大括号配平）：`_brace_body` 删掉，配平收进 `scripts/rust_code_reader.py:59`
   的 `brace_body(text, from_index) -> str | None`，`fn_body`（`:83`）改为在它之上找函数头。
   两份失败语义各自写明（`rust_code_reader.py:63-67`）：`fn_body` 的 `None` 由调用方按
   「判定面塌缩」处理（`verify_ffi_input_bounds.py` 判红或 exit 2）；绑定侧把 `None` 折成
   **空串**（`:84`，与空 `impl` 同值），兜它的是本门禁自己那条「零导出不作通过判定」的 exit 2。
   顺手记一条现读纠正：这两处差的**不只是失败值**，还有入口（一个按字节索引、一个按函数名），
   所以合并只能是往下沉 primitive，不是「删掉一份留一份」。

4. 判据②（`MARKERS` 认正则常量）——三条候选判据在**同一份面**上对照着量：
   - 量法是把 HEAD 那份还没合并的 `verify_uniffi_binding_surface.py` 原文塞回内存态判据面
     （280 份），三条候选各数一边：**A**「一次 `compile` 里含任一注释形态（双斜杠、块起点
     或其转义写法）」命中 **1 处**，就是那个常量；**B**「含双斜杠或非捕获组起点」命中
     **14 处／11 份文件**，其中 **13 处与注释过滤无关**；**C**（本批落地的「两种形态同行同现」）
     同样命中 **1 处**。现树（已合并）三条都是 **0**。
   - 所以被否的是 **B**（已记 §六），不是「宽版会误报」——**A 与 C 今天一样准**，选 C 的理由
     是它对「双斜杠单独出现」零敏感：URL／glob 类正则里出现双斜杠是合法产品逻辑，A 迟早给
     自己造一条假红。这条如实写成**严格性取舍**而不是「误报实测」。
   - 落地的紧判据在 `scripts/verify_text_anchor_helpers.py:61`；**现树命中 0**——唯一这样写的
     那处已在本批删掉，所以这是一条绊线（防下一次有人把就地过滤藏进正则），不是修已发生的漏网。
   - 它**判不到**的三种写法写在同一文件 `:63-70`，不写成全覆盖：①两种形态分在两次
     `compile` 调用里；②块形态写成字符类而不是转义形态；③同一行里两种形态之间隔着右括号。
   - 两条自纠记在这里（都是本批自己抓自己的）：①草稿最初写的数是「宽判据 8 命中其中 7 处
     误报」，那是更早一次会话里**另一条规则**的量，本批按可复现口径重量后对不上，已按上面的
     A／B／C 三档改写；②第一版量 A 时把块起点写成裸的两字符形态——正格里星号是量词，
     「斜杠紧跟星号」意为「零个或多个斜杠」，于是它匹配空串、把 280 份面里的 **66 处**
     `compile` 全算成命中。一条判据的**量具**自己错形时给出的数比没有数更坏：它看起来像证据。

5. 关掉一条绕过路（本批现读新发现，不在 Q63 里）：绑定那半边过去**不剔注释**，符号名出现在
   `#` 注释里也算在面上 ⇒ 「把一行符号注释掉」是一条**不改 Rust、不跑 uniffi_bindgen、
   不动任何 CI** 就能让本门禁变绿的做法。现在它判「绑定缺方法」
   （用例 `tests/python/uniffi_binding_surface_test.py:120`）。现树零差异（第 2 点），所以
   这是关门不是修漏；「注释里的形态不算证据」这条纪律此前只作用在 Rust 半边，是口径没问完。

6. 反向锚与变异回放（「能红」的口径按本批实测写，不按用例条数写）：
   - 单源门禁新增 3 条用例（`tests/python/text_anchor_helpers_test.py:122`／`:138`／`:152`）。
     变异＝把 `MARKERS` 末条撤掉 ⇒ `:122` 与 `:152` 判红、`:138`（只含一种形态不算）仍绿；
     另有一条不靠注入的现读对照：把 HEAD 那份带 `_code` 的实现塞回内存态面，
     多出的实现点恰好是 `scripts/verify_uniffi_binding_surface.py` 自己。
   - 绑定门禁新增 4 条用例（`tests/python/uniffi_binding_surface_test.py:98`／`:105`／
     `:113`／`:120`）。变异＝以 HEAD 的旧实现回放（**保留新签名**，否则 `TypeError`
     会冒充「用例咬得住」）⇒ **3 条判红**；`test_trailing_block_comment_is_not_an_export`
     新旧同绿，它是覆盖面控制（同一行「代码在前、块注释在后」旧口径也不判导出，因为
     `*/` 挡在 `fn` 前面），不是咬合锚——写清以免下一轮把 4 条当成 4 条证据。
   - 全程内存态注入，工作树没有「改了再回滚」。

7. 验证面：`pytest tests/python` **871 passed／1 skipped**（本批 +7：绑定门禁 13→17、
   单源门禁 12→15）；ruff／bandit／py312-compat／行数红线（573 个受管源文件、基线 86 项，
   本批五个被改文件 186／202／88／234／220 行都在 300 以下、没有一个进基线）／文档计数／
   队列状态全部退出 0；三支受影响门禁自跑绿（`verify_text_anchor_helpers`＝实现点 5 处、
   `verify_uniffi_binding_surface`＝导出面一致、`verify_ffi_input_bounds`＝六判据）。
   未跑 cargo：本批没动 Rust 源，`contracts/ci/gate-execution-face.yaml` 与 CI 步骤面
   也没有增减（门禁脚本零新增零删除，执行面登记不变）。

8. 未做与边界（写清以免下一轮当成已做）：①`MARKERS` 判不到的三种写法（第 4 点）；
   ②`strip_comments` 对 Python 的 **docstring 无能为力**（单源自己的 docstring 第 2 条已记
   这一课），所以「绑定半边剔注释」剔的是 `#` 行与块形态，docstring 里写的符号名**仍算在面上**——
   要把 docstring 也剔，得先有一条 AST 面的口径，那是另一个批；③本批没动 uniffi 接线
   （ADR-009 出货两端都走 C ABI），收益全在判据面与那份入库镜像的可信度上；
   ④`core-rust.yml --generated` 那条权威生成腿仍只在 CI 上跑（本机没有跑 uniffi_bindgen，
   所以「入库件与工具链自己生成的结果一致」这句本批没有现读证据，与 R9-RS-2 登记时同口径）；
   ⑤§3.63 第 11 条④留下的那条「本批没有合并 `_brace_body`」由本批第 3 点闭掉。


### 3.65 R9-B65（2026-10-15，接手后的第一条：文档指向单源，可没人验证那根指针）：catalog 的「谁判哪一列」做成注册表，头注与表互为对照

1. 触发点是一条队列项的回读。Q53 第③档原写「`action-catalog.yaml` 的
   `confirmation/risk/audit` 三列也不被 broker 读 ⇒ 两端各说各话」。现读三份东西之后它不成立：
   R9-B46 已把这些列**定稿成治理元数据（设计上就不给运行时读）**，而且已经有反向锚
   （`catalog_governance_columns_test.py::test_broker_never_reads_the_governance_columns`，
   broker 源码剔注释后出现列名即判红）＋正面控制（判定面四列必须真的在 broker 里出现，
   否则反向锚在判空气）。⇒ 照原处方「把三列接进裁决」现在**会撞红**，它不再是一次可自由执行的改进。
   ③剩下的真缺口只有一条：Agent 端 `AG` 命中 0（`CONSUMER_MANIFEST` 现读），
   要不要把红队夹具与 `action-valid/invalid.json` 绑成同一份输入属排期决定 ⇒ 留在 §四/队列。
2. 但回读时抓到一条更小的失实：**头注把那根反向锚指错了文件**——
   第 21 行写 `tests/python/codegen_and_catalog_test.py`，锚其实在隔壁的
   `catalog_governance_columns_test.py`（R9-B46 当时因为前者在行数红线基线里才另开新文件，
   后来头注没跟着改）。这件事本身无害，有害的是**它不可能被发现**：
   「文档改成指向单源」这条纪律我们已经执行了很多次（§3.41/§3.45/§3.58 第 5 条…），
   但从来没有一条判据验证「指向的那份文件真的存在、真的含那条锚」。
   于是本批做的不是改那一行，而是把指针变成能红的东西。
3. 落地形状：注册表 ⇄ 头注 ⇄ 判据文件**三者互为对照**
   （`COLUMN_JUDGES` + `check_pointer_agreement()`，判四件事）——
   表里每个路径必须实存；那份文件的**代码面**（`strip_comments` 后）必须查得到那一列的列名；
   头注必须逐字写出表里的每条路径；锚点文件必须真的含 `GOVERNANCE_COLUMNS`/`BROKER_PATH`/
   `JUDGMENT_COLUMNS` 三个符号。再加一条宽度约束：**指针一律写全路径**，
   裸文件名（头注第 17 行原本写 `analyze_action_catalog.py`）判红——
   本仓同名文件不止一处，裸名等于让下一个读者自己猜。
   注册表值允许是多元组：`read_only` 与 `redteam_fixtures` 确实由两份文件分别判
   （静态一致 vs 执行侧夹具），登记成一元组就是把「谁判」说窄了。
4. 证伪与正面控制（新增 6 条用例，都在 `catalog_governance_columns_test.py`）：
   把锚点指针替换成**历史上真写过的那个错值**（不是编的形状）⇒ 红并指名「反向锚」；
   表指到一份存在但不含该列名的文件 ⇒ 红；指到不存在的文件 ⇒ 红；裸名 ⇒ 红；
   正面控制是「一致的（列、文件、头注）三元组必须不红」，
   以及「注册表必须覆盖 `GOVERNANCE_COLUMNS` 全部四条」——防止表悄悄漏列，
   漏了的那条就回到「没人读也没人判」的装饰字段。
5. Q53 的登记文本按上面的现读改真（保留「登记时曾这么写」的原话），
   CSV `R9-SH-13` 同批回写。**这是第九轮第一次把「文档里的指针」本身纳入判据**，
   而它抓到的第一个缺陷就是它自己的出处那一行。

## 六、复核后判定为不成立（留此防重复上报）
- **「三端应统一到提前捕获的 `origDefineProp`」不成立**（第九轮 R9-B55 / §3.55，登记于 Q57-②）：
  处方写的是「Windows 提前捕获定义器、核心与 Android 直接引用 ⇒ 三端不同形 ⇒ 要收口」，
  回读三条事实后它不成立——①三端出货注入面里**没有一处**给 `Object.defineProperty` 赋值
  （因此「用哪一份」在现树里没有语义差）；②两端注入点都是 document-start API，页面脚本在
  我们的脚本之前没有执行机会，所以「防页面前篡改」保护的窗口不存在；③Windows 的捕获与它
  同段覆写 `getOwnPropertyDescriptor`/`getOwnPropertyNames` 那层独有反检测写在一起，是那段
  的写法习惯而不是别人缺的防护。**反向风险也记在这里**：真要「统一」就是改 core 30 处 +
  Android 10 处出货注入 JS 换 0 个行为差；下一轮若再有人按「三端同形」的直觉报这条，
  先跑 `tests/python/injected_js_parity_test.py::test_nobody_overwrites_the_definer_the_ends_use`
  ——它红了才说明前提变了、这条才值得重判。

- **「Windows 下载闸门只判入队地址 ⇒ 302 到云元数据那型在正典制品上仍在」不成立**
  （第九轮 R9-B57 / §3.57，登记于 Q58 = R9-CS-18）：这条目的前提没被量过——它写的是
  「反射只能给出 `Uri` 这个名字，不等于它报跳转后的地址」，所以修法列了「完成后复判 + 删文件」
  或「重做下载发起链」两案。本机实测三场景（一跳、两跳、页面内 `click()` 触发，
  Runtime 155.0.4283.45 + SDK 1.0.2903.40）：`DownloadStarting` 时刻的
  `CoreWebView2DownloadOperation.Uri` **已经是最后一跳的落点**，`Completed` 时不变
  ⇒ 两案都不需要，代价也一起作废。**下一轮别再按原句上报**。
  而且后半句也不成立：那个落点在放行前会过 `BrowserPolicyBroker.cs:111-127` 的
  `ReservedAddressBoundary.DeniesRaw`（169.254/16 与不可判定地址一律拒，第七轮 R7-CS1-02 落的），
  Android 侧同形由 R8-AD-03 落过——**所以本批不新登任何 Q**（中途我误判过一次「Windows 缺这道门」，
  原因是只看了 `DownloadPolicy` 没看 broker，现读后自纠）。
  顺带留一条方法论：本批第一次「量不到」的结论是假的——那次用的是裸
  `CreateCoreWebView2ControllerAsync`，而 App 走的是控件 + `EnsureCoreWebView2Async`；
  「做不到」之前先怀疑自己走了一条没人走的路。

- **「`MARKERS` 认「注释形态写进正则常量」时，把「含双斜杠**或**非捕获组起点」当判据」不成立**
  （第九轮 R9-B64 / §3.64 第 4 点）：处方只说「认这一类」，落地时把三条候选塞进**同一份**内存态
  判据面各量一边（280 份；量法＝把 HEAD 那份还没合并的门禁原文塞回面里再数，这样「该被抓的那处」
  确实在场）：**A**「一次 `compile` 里含任一注释形态」命中 **1 处**（正是那个被合并的常量），
  **B**「含双斜杠或非捕获组起点」命中 **14 处／11 份文件**、其中 **13 处与注释过滤无关**
  （`check_doc_claims.py` 的计数声明、`verify_uniffi_binding_surface.py` 的
  `_FN_AFTER_ATTR`／`_IMPL_AFTER_ATTR`、`verify_xaml_resources.py`、
  `gradle_lockfile_shape_test.py`、`gradle_relock_surface_test.py`、`injected_js_parity_test.py`、
  `windows_python_encoding_test.py`、`workflow_exit_code_test.py` 等），**C**（落地的
  「两种形态同行同现」）命中 **1 处**；现树（已合并）三条都是 **0**。
  **被否掉的是 B**：本仓正则大量用非捕获组，把 `(?:` 当证据就得为那 13 处各写一条豁免登记——
  那正是 R9-B45 要消灭的「登记面比判据面大」。
  **A 没有被实测到误报**，它今天与 C 一样准；选 C 是**严格性取舍**不是「宽版报错」：A 对
  「双斜杠单独出现」敏感，而 URL／glob 类正则里出现双斜杠是合法产品逻辑，只是判据面上现在恰好
  没有这种正则，所以今天量不到它的假红；C 对此零敏感。
  **下一轮别再按「宽版 8 命中里 7 处误报」上报**——那个数出自更早一次会话里**另一条**规则的口径，
  本批按可现读复现的口径重量后对不上（两处自纠见 §3.64 第 4 点：换口径重数、以及第一版量具把
  块起点写成裸两字符形态，正格里星号是量词、于是匹配空串把 280 份面的 **66 处** `compile` 全算成命中）。
  要重判这条，先跑
  `tests/python/text_anchor_helpers_test.py::test_a_regex_that_is_not_a_comment_filter_is_not_reported`
  ——它红了才说明现树里真出现了「只含一种形态但确实是注释过滤」的新写法、A 才值得换上来。


- **「Android 也缺 window.open 洪水上限」不成立**（第九轮 2026-10-10，落地 Windows 侧上限时
  同批实测）：`android/app/.../BrowserEngine.kt:65` 显式 `setSupportMultipleWindows(false)`，
  全仓 `onCreateWindow` 零命中（唯一的 WebChromeClient 只覆 permission/fileChooser/progress/title），
  平台默认实现返回 false ⇒ 页面无法到达建标签路径；该设置另被
  `BrowserEngineHardeningTest.kt:43` 的 `assertFalse(s.supportMultipleWindows())` 钉住。
  结论：Android 没有这个面，不是漏了这一刀。若将来开多窗口支持（`onCreateWindow` 返回 true），
  **必须先接 Windows 侧同款闸门**（`Core/NewTabGate.cs` 的口径：同源 10 秒 ≤3 次 + 拒绝码）。
- pwsh 步骤「`python` 之后接 `echo` 即吞失败」**不成立**：`$ErrorActionPreference='stop'` +
  末行 `exit $LASTEXITCODE` 形态下原生命令失败仍返回非零（实测），故
  `compat.yml:64-67`、`release-windows.yml:138-149,219-221` 均正确失败，
  `check_workflow_shells.py:123` 的「末条原生命令」前提成立。
- `git diff --exit-code -- <path>` 在 pathspec 不存在时恒返回 0（实测）——但
  `contracts.yml:135,138-141` 三处路径实树均存在，非现行缺陷。
- `shared/shell/manifest.txt` 被清空/缺文件的担忧不成立：`validate_release.py:127-152`
  双向差集已在常跑面兜住，pwsh 侧 `ErrorActionPreference=stop`。
- `release-core.yml:94-95` 的 `cp … || true` 是已注明的非本平台产物 best-effort；
  `gradle-dependency-insight.yml:87` 的 `|| true` 属 dispatch-only 诊断工具（头注声明不进门禁）。
- 27 处 `ubuntu-latest` 未钉本身是第八轮 §八 已接受项；R9-CI-8 只反证其**豁免理由**
  （出货 Android 的 `.so`+APK 恰在未钉版 ubuntu runner 构建，`release-android.yml:47`、
  `release-core.yml:62`），该条本批未实施（改钉版属构建面变更，单独定）。
- SH 分区正面核验（不报即闭环）：`shared/shell/*` 与宿主端**零逐字副本**（全树 md5 比对
  命中 0；Android 经 `android/app/build.gradle.kts:218` 的 `srcDir(../shared/shell)` 直取，
  Windows `dist/` 未入库、`git ls-files dist`=0）；版本四处字面量由
  `scripts/verify_versions.py:37-43` 对账；`contracts/policy/bridge-sinks.yaml` 的 sink
  权威迁移是真的（含模板与 Kotlin 副本双向锚）；node UI 回归 110 例 + snake 30 例本机实测全绿。
- CS 分区交叉核对：csproj ↔ 三把 `packages.lock.json` 的 `resolved` 全部 = 显式钉的 2.1.13
  （锁里 `2.1.12` 只出现在 `Microsoft.Data.Sqlite` 的 dependencies 声明段=上游自述下限）
  ⇒ **R8-DEPS-3 确为真闭环**；同步 DNS/`GetAwaiter().GetResult()` 均在后台线程，UI 线程
  无阻塞；`RejectNavigationConfirmation` 无 KillSwitch 前置属方向正确的 fail-closed，非缺陷。
- RS 分区交叉核对：`rust-toolchain.toml` 1.99.0 与 9 处 workflow 字面量逐处对齐、nightly
  例外恰好一处（#124 一族成立）；canvas 三端 `aegisNoiseMix`/绝对序号/`BYTE_RGBA_GUARD`
  实质一致（B2/⑦ 成立），余量见 Q31；R8-RS-13（`hex_seed_to_bytes` 先 `with_capacity(len/2)`
  后判长度、uniffi 面 `update_host_denylist(Vec<String>)` 无条目数上限）第九轮登记时记为
  「仍未修、不另立 ID」——**已于本批落地**，两半的修法、上限为什么不拒真实名单与能红判据
  见 §3.61（该形态此前不进 §五 队列、不进任何门禁，故每轮重新发现一次；教训是同批第 1 条）。
- **「`consume_navigation` 里宿主可构造的 `FfiAuthorizedAction` 是第三条未判长回声面」不成立**
  （第九轮 R9-B63 / §3.63 现读枚举时量到，判为不成立）：`ffi/broker.rs:589` 那个
  `action: FfiAuthorizedAction` 是 uniffi record，字段全部由宿主递交，而 `validate_action_at`
  （`core/broker.rs:333-339`）确实会把 `action.session_id` 与 `action.policy_version` 整串
  写进 detail 与 explanation——形状与 R9-B63 刚修的那条一模一样。它不成立的理由是**到达路径**：
  在走到核心层之前，`:644` 那条 match 要求 `same_binding(&issued, &action)` 成立，而
  `same_binding`（`ffi/broker.rs:757-768`）逐字段比对**含 `session_id` 与 `policy_version`**
  的账本内 broker 自己签发的那份 ⇒ 走到回声那一步的这两个串必然与账本等值，账本内的会话键由
  `create_session`（`:520`）判 256、版本串由本批判 256；不相等则拿到的是 `:657` 的
  `action_not_issued`，四条文案全静态。`Consumed { session_id }` 那处克隆（`:692`）同受这条
  等值约束。**推理记在这里，判据没有钉它**：钉「到达回声前必须先过逐字段等值」需要跨函数体的
  数据流分析，超出本仓按文本判源码的口径面；下一轮若把 `same_binding` 改成子集比较，
  这条就重新成立——`ffi_navigation_tests` 里有绑定比较清单的用例，改它不会全绿。

## 七、COVERAGE 汇总（置信边界）

六个分区全部返回并各自给出未读清单，共同形态是：**主源集全读、测试面按抽样、生成物与
归档栈不入面**。因此本轮结论的适用范围以各条 `文件:行号` 为限：

- AD：`android/broker/src/main/**` 与 `app/src/main/java` 策略面全读；24 个 `app|broker/src/test`
  文件未逐行 → 凡依赖「某路径全树无测试」的判断（Q1/Q5/Q6）已改写为「已读到的用例形态为 X」。
- CI：16 个 workflow 与 4 个 composite action 全读；`scripts/` 余 11 个脚本正文、
  `contracts/codegen/*.py`、`tests/python` 余 22 个测试文件未逐行（Python 门禁的逐行掏空面
  本轮未展开，不声称全覆盖）。
- SH：`shared/shell/*`、9 份 UI 回归、6 张 schema、3 份 policy 全读；codegen 脚本正文、
  `contracts/vectors/*` 逐文件键与条目计数 + 3 份 invalid 全条目。
- CS：`Chrome/`、`WebView/`、`Broker/`（判据文件）、`Core/UrlSafety` 等全读；
  `Core/` 展示与存储层及多数 xunit 测试仅抽样。
- RS：核心裁决链上的模块全读；`policy/capability/action_policy/…` 等 17 个模块按引用扫描
  确认不在导航链上后让位给注入链取证。
- DOC：四份根文档 + ADR 全量 + product/runbooks 全读；`docs/threat-model/*` 与 10 份设计/
  调研稿未读（仅机扫其 `file:line` 与锚点）。

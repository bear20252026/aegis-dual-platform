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
的取值、不作现行陈述」的日期更正，顺带把 R9-AD-8 的注记失实闭合）。logback 3×low 维持
「不在解析树」原判。

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

- **R9-CS-3**：Windows 未关 `AreDevToolsEnabled`（WebView2 默认 true）与 autofill/密码自动
  保存默认——关闭改变调试与默认 UX，属产品行为变更。
- **R9-SH-5**：`action-catalog.yaml` 的 `confirmation/risk/audit` 三列在 `agent/broker.py` 零消费。
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
  `action-catalog.yaml` 三列（`confirmation/risk/audit`）到底由 broker 消费还是删列并写明
  「治理元数据非判定面」（R9-SH-5，方向是「默认放行改默认需确认」，不默认执行）、
  **IPv6 字面量在导航面**（R9-AD-4 的一半：`[::1]:9000` 这类 authority 被
  `OriginPolicy.kt:104-110` 与 Rust `origin/host_grammar` 一致拒，Windows 反而放行 ⇒
  要打通得解冻核心 host grammar 并增补 `url-origin-*` 向量，是跨三端的解析器语义变更，
  不是「剥个括号」的小改。R9-AD-4 的**口径改真**半边已按第四节处方落地（§3.5：KDoc + 跨层锚用例，判定零改动），剩下的「打通导航面」仍是待定稿项。

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
- Q3 R9-AD-3 | P2 | `WebViewDownloadHandler.kt:139-169` 全树零 `setRedirectsAllowed`：
  闸门只判**入队** URL，DownloadProvider 默认跟随重定向 ⇒ `302 → 169.254.169.254` 仍
  落盘公共目录（PR #130 消除的后果复活路径）。建议完成后用 `COLUMN_URI` 对最终地址复判
  + `remove()` + 留痕；`setRedirectsAllowed(false)` 会打断正当 CDN 重定向（产品代价，不推荐）。
- Q4 R9-AD-4 | P2 | `OriginPolicy.kt:104-110` ↔ `LocalTargetHosts.kt:153-159`：方括号
  IPv6 authority 在导航层一律拒 ⇒ `::1`/ULA 的「放行」永不被判定，而
  `LocalTargetHostsTest.kt:26-28`、`ReservedAddressBoundaryTest.kt:62,68` 用
  `http://[::1]:9000/` 当放行样本，读起来像「IPv6 本机可打开」。建议如实写进 KDoc 与
  测试注释（**不得反向收紧段集**，与 B8 相反）。——**本批已逐行回读并按该处方落地**（§3.5），判定零改动。
- Q5 R9-AD-5 | P3 | `AndroidBroker.kt:189` ↔ `:368`：原生变体进账本的是 64 位裸 hex nonce
  （无 `sessionId:` 前缀）⇒ 关标签的 `removeIf startsWith` 一条都摘不掉，而注释称
  「销毁会话并移除其已消费 nonce」；`AndroidBrokerTest.kt:414-417` 只钉托管路径形态。
  孪生形态见 `BrowserPolicyBroker.NativeNonceLedger`（R8-CS-REG-01 同源，后果轻得多）。
- Q6 R9-AD-6 | P3 | `BrowserViewModelConfirmations.kt:104-108`：下载确认缺「仅当前活动标签
  可消费」的归属校验（导航确认有，AD-158），且 `switchTo` 撤销 pending 导航确认却不撤销
  pending 下载确认 ⇒ 后台标签的危险扩展确认可顶到前台标签被批准。
- Q7 R9-AD-7 | P3 | `TabManager.kt:109-130`：`closeTab` 三条 when 分支的行内注释整体错位
  一条（与类 KDoc AD-254 段的正确对应相反）——按注释读会得出与实现相反的激活位语义。
- ~~Q8 R9-AD-8~~ **本批已闭**（见 §3.0 与 R9-DEPS-1：就地补日期更正注记，不改写历史）。
  原条目：Q8 R9-AD-8 | P3 | `android/build.gradle.kts:13-19` 头注声明「1.85 / 0.9.6 / 3.18.0」，
  `:26-32` 实钉 BC 1.86（且拆三条）、jose4j 0.9.7、commons-lang3 3.21.0 ⇒ 按头注做构建
  类路径分诊会与实树对不上账（`docs/security/android-build-classpath-triage.md` 同账本）。
- Q9 R9-AD-9 | P3 | `DownloadPolicy.kt:96`（`URLDecoder`，`+`→空格）↔
  `WebViewDownloadHandler.kt:210,338-364`（`decodePercentStrict`，`+` 字面）：同一「URL
  路径段」两套解码器，而后者注释正是前者的反驳理由；本仓两处自写纪律「不欢迎第二个解析器」。
- Q10 R9-AD-10 | P3 | `AegisHomeBridge.kt:95-121` + `SecureWebViewFactory.kt:127-132`：
  `addJavascriptInterface` 对象对所有帧可见（本类 KDoc 自述）而判据只取 `webView.url`
  （主框架），受信面是整个 `file:///android_asset/` 前缀（首页 + GeoGebra）⇒ 壳页内跨源
  iframe 可驱动 `navigate/setEngine/setWallpaper/goBack`。实测 `shared/shell` 现零 iframe
  ⇒ 今日无落点，属一次性加固窗口（androidx.webkit 1.17 的 origin-scoped 重载）。

### 5.2 SH（shared 壳层与契约）

- Q11 R9-SH-1 | P2 | `contracts/schemas/release.schema.json:12` 与
  `contracts/schemas/version.schema.json:12` 的 SemVer pattern 仍是旧宽松式（接受
  `2.2.0-01`、`2.2.0-beta.`、`2.2.0-..`），PY-279 只收紧了
  `contracts/schemas/update-manifest.schema.json:26`；而 `release/update_verifier.py:44-53`
  对这些抛 UpdateRejected ⇒ 发布声明说合法、客户端验证器判非法。两张 schema 零向量
  （PY-013 的向量面只覆盖 4/7）。
- Q12 R9-SH-2 | P2 | `tests/ui-regression/start_a11y.test.mjs:25-30` ↔
  `tests/ui-regression/start_page.test.mjs:443-453` ↔ `shared/shell/start.css:244-258,324,353`：
  `mediaBlock()` 把「媒体块」切成「本 at-rule 到下一个 `@media`」而非闭合 `}`，切片
  5313/19189 字符，含块外的 `.veil-btn {`（:324）与 `.engine-item:focus-visible`（:353），
  且不剔注释（块内注记 :245-247 原文就写着 `.engine-item`）。**内存态注入实证**：从
  `start.css:248` 的选择器列表摘掉 `.engine-item, .veil-btn`（即回退 R8-SH-13 半个修复），
  新锁与旧锁 WB-142 双双仍绿；整块退回 40px 形态才红。——**本批已回读确证并落地**（§二 R9-SH-2）。
- Q13 R9-SH-3 | P2 | `tests/ui-regression/start_main.test.mjs:313`：注释写「触发按键不得
  选中引擎（仅 Enter/Space）」，实体是一行 `assert.ok(true)`——零判定，而 `makeHost()`
  已提供 `state.engineCalls` 却未取用。**本批已回读确证并落地**（§二 R9-SH-3）；Enter/Space 正向面零覆盖另记为 R9-SH-12（队列新增 Q47）。
- Q14 R9-SH-4 | P3 | `tests/ui-regression/start_page.test.mjs:403-405`：
  `SNAKE.substring(SNAKE.indexOf("document.addEventListener('keydown'"))` 在 indexOf 返
  `-1` 时退化为全文扫描，而 `if (!isOpen) return;` 在 `shared/shell/start.snake.js`
  出现 2 次（:449 keydown 与触摸处理器）⇒ 实测删除全部 document keydown 注册后仍绿
  （WB-133 的锁）。——**本批已回读确证并落地**（§二 R9-SH-4：外迁成新文件 `tests/ui-regression/snake_guard_slice.test.mjs`，原文件在零余量基线上）。- Q15 R9-SH-5 | P2 | `contracts/policy/action-catalog.yaml:14-35` 声明
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
- Q21 R9-SH-11 | P3 | `contracts/vectors/native-navigation-confirmation.json:2,12-15` ↔
  `native-navigation-decision.json:2-3`：同一原生 ABI 的两份向量信封不一致（前者只有
  `protocol`、无 `version/description`；期望字段名 `expected_request` /
  `expected_request_code` vs `expected_evaluate` / `expected_deny_code`），且仅
  `core/rust-policy-core/src/c_abi/tests/vectors_confirmation.rs` 一份消费者（C#/Kotlin 零）
  ⇒ 属 B9 词表入冻结面的余量，需定稿。

### 5.3 CS（Windows 正典）

- Q22 R9-CS-1 | P2 | `windows/src/Aegis.Windows.App/Chrome/InPrivateWindow.xaml.cs:135-164`：
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
- Q23 R9-CS-2 | P2 | `windows/src/Aegis.Windows.App/Chrome/MainWindow.SourceViewer.cs:29-38,71-75`：
  查看源码（Ctrl+U）的带外抓取 ①不设 `AllowAutoRedirect=false`、落地也不对**最终** URI
  复查 `ReservedAddressBoundary` ⇒ 敌意页 302 跳 `169.254.169.254` 照跟（同仓
  `Core/Favicons/FaviconService.cs:46` 显式关重定向、`Core/Security/ThreatFeed.cs` 复查
  final-uri，唯此出口两者皆无——保留地址边界「四类出口单源」之外的第五类带外 fetch）；
  ②`ReadAsByteArrayAsync` 先整读进内存再比 `SourceMaxBytes` ⇒ 无 Content-Length 预检的
  大响应可 OOM。响应只回显给用户、页面读不到 ⇒ 非逃逸级，但「把内网/元数据内容递给被
  诱导读源码的用户」不该发生。
- Q24 R9-CS-4 | P3 | `windows/src/Aegis.Windows.App/WebView/HostWebView.cs:332-336`：
  每个放行下载 `_trackedDownloads.Add(operation)`，完成**不移除**（仅 `UnwireEvents` 里
  `Clear`）⇒ 长会话累积已完成 `CoreWebView2DownloadOperation` COM 引用，`StopLiveTraffic`
  还对已结束项 `Cancel()`（抛→吞）。

### 5.4 RS（Rust 核心）

- Q25 R9-RS-1 | P2 | `windows/src/Aegis.Windows.App/WebView/FingerprintShield.cs:207` +
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
- Q28 R9-RS-4 | P3 | `core/rust-policy-core/src/https_only.rs:89-125`、
  `src/update_manifest.rs:170-309`、`BridgeGuard::inject_script`：三个策略面在 13 个冻结
  导出符号里**零入口**、两端零消费，而 `README.md:15,71` 仍把「Ed25519 阈值验证」列为
  核心裁决面；`HttpsOnlyState::upgrade` 判的是运营者手工白名单，**不含** B8 的回环/
  RFC1918/CGNAT/`.local` 段豁免 ⇒ 一旦按「迁移到核心」接线，`http://192.168.1.1` 立刻被
  升 https（R8-AD-01 原形态复现）。②建议模块头标「非 B8 判据载体」；①③补导出即改 ABI ⇒ 待定稿。
- Q29 R9-RS-5 | P3 | `core/rust-policy-core/src/c_abi/tests/buffer_boundaries.rs:157-203` ↔
  `windows/src/Aegis.Windows.App/Broker/NativePolicyCoreBridge.DenylistPush.cs:102-131`：
  ⑨ 的四档位协议在 Rust 侧只端到端跑了 0/1，应答字段 `mode/staged/served` 在 Rust 全测试树
  **零断言**（只产出，`src/c_abi/navigation.rs:288-297`），`denylist_mode_invalid` 亦无 ABI
  层用例；而 C# 的提交判定正依赖这三字段（`commit.Staged/Accepted` →
  `denylist_commit_refused`），且那 8 例跑在假核心上、真 DLL 用例不在必需检查（R8-CI-18）
  ⇒ 核心改名/丢字段在 PR 面永不红。
- ~~Q30 R9-RS-6~~ **本批已确证并落地**（§二 裁决行 + §3.13）：修法没走「签名体现不变量」，
  而是让 `is_high_risk_host` 自己取 `:` 前段（函数自证 > 调用方纪律），绕过形态直接消失；
  `169.254.169.254:8080` 判高危、`192.168.1.1:8080` 仍判非高危（B8 裁决保住——先试的
  「段内含 `:` 即判高危」正是被这条既有期望打回的，实测过程记在 §二）。同形绕过在 C#/Kotlin
  孪生里不存在（不收带端口入参），故本批零跨端判定改动。
- ~~Q31 R9-RS-7~~ **本批已确证并落地**（§二 裁决行 + §3.13）：三端片段表 5 段 → 8 段，
  补 `pixels.length === width * height * 4` 与两条 `aegisNoiseRectangle` 调用前缀。
  两次内存态注入（Android 守卫退化、C# 调用改名）旧口径零红、新口径各自判红并已还原。

### 5.2.1 本批落地时新增队列（同口径：必须带 file:line）

- Q47 R9-SH-12 | P3 | `shared/shell/start.main.js:83` ↔ `tests/ui-regression/start_main.test.mjs:307-313`：`Enter`/`空格` 选中引擎这条**正向**判据全仓零覆盖（:83 的 `if (ev.key === 'Enter' || ev.key === ' ')` 无任何用例驱动），而 :87 的方向键分支刚被 R9-SH-3 补上反向判据——只锁一侧意味着「把 Enter 整条删掉」仍全绿。补法：在同一用例里对 `items[1]` 触发 Enter 并断 `state.engineCalls` 增长（`start_main.test.mjs` 在 579 行零余量基线上，需先净减）。
  **本批已落地**（§二 R9-SH-12 / §3.10：正向锚 + 故障注入自证）。

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
- Q39-Q46 R9-DOC-08..15 | P3 | 八条（**R9-B21 已落地 DOC-08/09**：「10 项」改 11 项并点名漏掉的第 11 步；README/SECURITY 的 `:70` → 实调行 `:77`。余六条 DOC-10..15 仍在队列）：`docs/runbooks/windows-run-guide.md:63-66` 写「真机验证
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

- Q48 R9-CI-13 | P3 | `.github/workflows/ci.yml`（`on.push.paths` 8 项）、`core-rust.yml`（3 项）、
  `agent-redteam.yml`（5 项）、`supply-chain.yml`（11 项）：ADR-007 声称「门禁型 workflow 已全部移除
  `paths:` 过滤」而实测这四处仍在过滤 ⇒ 未列路径的改动在这些面上静默不触发、检查名看起来「已过」
  （R8-SH-10 当年只处理了 `ci.yml`）。收口属 CI 触发面变更：runner 时长上升，且若某处 job 已列进必需
  检查，触发条件与 required 集合必须同批核对（R8-CI-01 的「Expected — Waiting for status」教训）⇒ 需用户
  点头后另批做。**R9-B21 只把 ADR 的陈述改真。**
- Q49 R9-DOC-20 | P3 | `docs/runbooks/device-validation.md:19`（Windows 第 6 步「下载 MIME 混淆」预期写
  「下载经 broker 判定（MIME/最终 URL/size）」）：本批只确证了 Android 那一行（Q37→R9-DOC-06），
  **C# 侧未验**——Windows 下载链是否真判 MIME/最终 URL/size 没有实测支撑，故该行仍是一条未核验陈述
  （下一批读 `windows/.../Downloads/` 后改真或续登）。

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

## 六、复核后判定为不成立（留此防重复上报）

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
  后判长度、uniffi 面 `update_host_denylist(Vec<String>)` 无条目数上限）**仍未修**，
  同于第八轮登记，不另立 ID。

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

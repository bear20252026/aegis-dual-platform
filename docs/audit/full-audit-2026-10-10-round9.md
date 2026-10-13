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

| AX-01 | P1（外部第三轮审计 2026-10-11 声称，主代理回读后**降级为「一半保留并落地、一半早已成立」**） | 保留并落地（投递面） | 回读结论要分两段：①「策略链异常时保持原始请求路径」在第八轮 ⑤ 已闭（`HostWebView.WebResourceGuards.cs` 的 `SubresourceDenialFailClosed` 异常回 403 + `subresource_policy_error`），审计报告据此点名的仍是**拒绝之后**那一步：旧代码 `try { e.Response = CreateWebResourceResponse(...) } catch { 只写日志 }`——拒绝已经判出来，合成响应自己抛（COM 对象退休/Environment 释放）却把这条请求退回默认路径 ⇒ **留痕不是拦截**。落地＝两段各自收口：交付返回 false 与交付抛出是同一事实（拒绝没落地）⇒ 都升级到 `CoreWebView2.Stop()`（内核随当前导航一并停掉待发子资源），留重码 `subresource_denial_undeliverable`；不做「换一组参数再试一次」（失败原因是环境失效，换参数不改结局，只会把一次失败刷成两条互不相干的日志）。**关键实现细节**：`escalateStop()` 不能和 `tryDeliver()` 放同一个 try——照直觉写 `try{ if(deliver) return; escalate(); } catch{ log }` 时 tryDeliver 抛出会**跳过升级**，正是审计点名的形态，故拆两段并各自吞（`DeliverDenialNeverThrowsBackToTheEventShim` 用三个同时抛的注入面钉「永不抛出」，含留痕面）。不可达面按 R8-CS-SEC-11 同法补结构锚：handler 本体切片（有界、剔注释）必须含 `DeliverDenial(`/`TryStopWebView` 且**不含** `catch` 与 `e.Response =`，`TryStopWebView` 切片必须真有 `webView.Stop()`。WebView2 真实故障注入（本机无 Runtime）仍属第四节阶段 C，本批只有 JVM/CLR 侧判定面 |
| AX-04 | P1（外部审计声称，主代理回读确证后**保留并落地**） | 保留并落地 | 回读确证：`KillSwitch` 此前只被 broker 的导航/下载/批准入口读取，而 `NtpBridge.Dispatch` 的 `restoreSession`/`importBookmarks`/`importHistory`/`goBack`/`openGeo`/`navigate` 经桥直达数据层与宿主，分发层零检查——README 早期就登记过这个覆盖面缺口，外部审计再次点名为准。落地＝判定单点放在 `Dispatch` 而不是按钮：`SideEffectingOps`（6 项）+ 拒绝码 `lockdown_engaged` + SecurityLog 留痕；**位置选择有实义**——`TryHandle` 对导入三操作走 `Task.Run`（CS-031），判在 `Dispatch` 才使「先排队、后排紧急停止」在执行时被重新验证，判在 `TryHandle` 就退化成入队时快照。判定边界如实登记而非一刀切：只读面（`getEngine`/`getWallpaper`/`bookmarks`/`hasSaved`/`importScan`/`jsError`）冻结期间必须可用（否则设置窗与异常上报一起废、用户看不到状态），`setEngine`/`setWallpaper` 是本机偏好、无网络与数据副作用，同样放行——各有用例钉住，防止下一轮把「统一门禁」误读成「桥里全部拒绝」。反向锚两条：同一批操作在未触发时必须照样落到宿主（证明拒绝来自开关而非「根本没接线」）、同一实例翻转闭包必须立刻生效（证明不是构造时快照）。NTP 桥本身有 `IsTrustedSource` 前置 ⇒ 这不构成远程页面可达路径，审计报告「不能直接认定远程网页能调用这些操作」的限定成立 |
| AX-03 | P1（外部审计声称）→ **主代理裁 P2** | 保留并落地**可直改半边**（详见 §3.22） | 回读：`AegisHomeBridge.isTrustedShellPage()` 判的是顶层文档 URL，`@JavascriptInterface` 不提供调用者 frame 的 Origin——报告说的机制差异属实；但可达链要求「顶层已是壳页 + 壳页内有攻击者可控 frame」，实测 `shared/shell` 四段脚本 + HTML **零 iframe**（`<iframe`/`createElement('iframe')` 均 0 命中，GeoGebra 走 `openGeo` 顶层导航），远程页面自己作为顶层时该判据本就拒 ⇒ 属提前封闭的信任边界，按 P2 排。本批落 CSP 显式 `frame-src 'none'`（把「今天恰好没帧」换成「加帧必须改这行」）+ 5 例常驻锚（两条反向注入实测）；报告另一条处方「拒空/异常 URL」**本已成立**（`isTrustedShellUrl` 对 null/"" 返回 false、`runCatching` 异常按拒，`AegisHomeBridgePrefsTest.kt:149-159` 已钉），按原样登记不重做。迁 WebMessage 传输与「整个 `file:///android_asset/` 前缀受信」两面入 §五 Q50 与 §四 |
| AX-05 / AX-06 | **P1**（外部审计声称，回读确证后保留并落地） | 保留并落地 | 回读确认报告的机制描述属实且比描述更糟：`NativePolicyCoreGate.cs:23-29` 的判定源是「环境变量（只在 CI 那步 shell 里赋值，不随包交付）+ HKCU 标记（普通用户可清除）」，`InstalledBuildMarker.cs:21-25` 甚至自己写着「不能恒真，否则毁掉开发工作流」——于是「不得静默回退到另一套策略实现」这条承诺的实际承载物是一个可删的注册表值；Android 侧 `requireNativePolicyCore` 由构建参数决定，而发布链唯一的锚 （`NativeGateWiringAnchorTest.kt:52-66`）判的是 **workflow YAML 里含不含那行字**，不是编译结果。落地＝要求由**编译进产物**：csproj 的 `GenerateNativePolicyCoreBuildMarker` 目标按 `RequireNativePolicyCore` 生成 `NativePolicyCoreBuildMarker.RequiredByThisBuild`（两条分支都生成，开发构建=false），`Gate.IsRequired` 改三源合一且**构建常量排第一**（纯函数 `ResolveRequirement` 可单测，环境变量仍只认精确 "1"）；发布链改验终物——release-windows 在已发布 dll 的 UTF-16 元数据里找姿态串 `aegis.build.require-native-policy-core=1` 并断言 =0 不出现、并第一次真正打开发布 ZIP 断言 DLL 在里面；release-android 改读 AGP 生成的 BuildConfig（含「找不到生成物即失败」，否则 find 空结果会让后面的 grep 恒真）。**两条实测细节写进注释**：①未被引用的 `const string` 不进元数据（加引用前 grep 命中 0）⇒ App.xaml.cs 那处日志引用是验证手段成立的前提，由测试钉住；②字面量在元数据里是 UTF-16，按 ASCII 找永远 0 命中＝另一种假绿。本机实测两版产物姿态串正确区分。三处文档同步改真（README:23-28、ADR-006:41-45、windows-run-guide:57-68），不留「文档说的≠实树的」。15 例新测试 + Core 832/Broker 204 全绿 |
| AX-02 / AEG-001 | **P1**（外部审计声称，回读后**属实但处方必须改写**）→ 已落地 | 保留并落地（惰性接入） | 缺口是真的：`ffi/broker.rs` 的 `evaluate_navigation` 只调 `validate_action`（第三层），`ContextBroker::evaluate`（broker.rs:247）才串三层，前两个层在 FFI 通路零调用（`broker.rs` 的 H-7 注记自述）。但**照处方直连会拒掉每一次导航**，两条实测事实：①生产构造是 `PolicyEngine::default()`＝空规则，`ActionPolicy::evaluate_opt` 在无规则匹配时返回 None（`action_policy.rs:110` 的 `let rule = best?;`，默认效果只作用于非 opt 的 `evaluate`）⇒ `PolicyEngine::evaluate` 落 `PolicySource::FailSafe` 的恒 Deny；②`CapabilityRegistry::validate` 对未注册 capability 恒拒绝（`capability.rs:156`）而生产注册表恒空。落地口径＝「该层**没有意见**时不改裁决；一旦配置即生效且其 Deny 不可被后面的 Allow 出口改回允许」（单调加严），接入点在会话验证**之前**。9 例新测试的三条关键：未配置时 FFI 拒绝码必须仍是 `session_not_found`（把 FailSafe 当拒绝直连的话这条第一个红）；同一入参配上 deny 规则后必须变 `policy_denied`（一条同时证明「配置生效」与「排在会话验证之前」）；空注册表必须是「未配置」而非「什么都拒」。`RequireConfirmation` 复用既有 `register_pending_approval`，不开第二份授权账；锁毒化仍 fail-closed。今天没有宿主入口注册规则/能力（`register()` 生产零调用）⇒ 出货行为零变更是**设计结果**，价值是把「裁决链不完整」变成「链已闭合、缺的是配置面」。五处文档撤 H-7 陈述（README×2、CLAUDE.md 模块表、ADR-006、ADR-008×2、ADR 索引）；ABI 面零变更（新增都在非导出 impl 块）；577 lib 测试全绿、clippy `-D warnings` 干净；三个零余量文件靠改写更短注记 + `impl Default` 换 derive 守住基线 |
| AEG-006 | P1（外部审计声称，回读后**属实但范围改写**）→ 落地为门禁 + 扩面队列 | 保留并落地（判据化） | 报告说「C# 只连部分向量、Kotlin 主要消费 `url-origin-*`」——按 `git ls-files` 的受管源码面逐份实测（543 个文件，命中口径＝词干作为独立词或完整文件名，排除 markdown 与 `META_LEVEL`（按名遍历整个向量目录的工具面，含门禁自己与它的用例））：**15 份向量里只有 2 份真的两端都跑**（`url-origin-valid/invalid`，CS+AD+RS），11 份有端侧执行者，4 份（`capability-*`/`audit-event-*`）**没有任何端侧执行者**、只被 `validate_vector_schemas.py` 判形状/expected。其余单端事实逐条钉进 `scripts/verify_vector_consumers.py` 的 `CONSUMER_MANIFEST`。两点范围改写：①那四份不是「没人判」——它们的 expected 本就是 `valid`/`deny_schema`，schema 就是判据，不能按「契约件白做」处理；②**Agent 端对契约向量的消费为零**（`AG` 在实测分布里一次都没出现），与 R9-SH-5「`action-catalog.yaml` 的 confirmation/risk/audit 三列 broker 不读」是同一件事的两面。落地＝新常驻门禁（登记表双向不变量 + 跨端支点下界 + 端侧执行者下界 + 扫描面塌缩 exit 2）接进 `contracts.yml` 的 PR 面；注入式自证 8 条从 `--self-test` flag **搬进 pytest**（要人主动敲 flag 的自证＝跑不动的判据，R9-SH-7 同课）；扩面工作另登 §五 Q53 |
| AEG-008 / R9-CS-15 | P3（我登记的原级）→ 用户对 §四 第 9 项说「全部完成」后**落地** | 保留并落地 | 回读确证「仅启动时取一次」属实且**不是**声明与行为不符（旧文案确实明示要重启），所以这是一次行为增强：`ThreatFeedCoordinator` 首刷后进入周期重取（默认 6 小时，节拍/上限/过期倍数三份数字单源在类常量上，界面按 `DefaultRefreshInterval × StaleAfterFactor` 算过期而不是抄一份 18 小时），失败按 2 的幂退避并封顶 24 小时（**只拉长不缩短**——「失败就更快重试」在订阅源 429 时就是自伤），每轮**重读**设置所以改源不需重启，未配置/改成非法值 ⇒ 那一轮零网络活动（原判据不变）。UI 半边把「上次成功更新 / 是否过期」贴上提示位，时间取**缓存文件写入时刻**（`FetchAndStore` 只在抓取+校验+落盘全成功后原子替换，所以它就是「最后一次成功」的权威形态；加字段要同步 SettingsService 快照与两个 XAML 锚，代价远大于收益），保存路径改走 `Active?.RefreshNow()`，旧「要重启才生效」文案连同 XAML 说明句一起撤下并由静态锚反向钉住不得回潮。两条**新出口带来的竞态**是这次改动的实质风险，都已处理并有故障注入锚：①周期循环与「保存即刷」并发 ⇒ 后**完成**的抓取决定最终名单（可能是先发出那个请求的旧结果），加 `_refreshGate` 串行化（改成「已在跑就跳过」会让手动刷新静默失效，不做）；②既有五个用例靠 `await BackgroundTask` 收口防 Dispose 抢缓存文件（CS-350 那笔账），周期化后该任务永不完成 ⇒ 它们必须显式传 `refreshInterval: TimeSpan.Zero`，本类只测启动那一次、周期行为归新用例。坑一条：`TimeSpan.Parse("24:00:00")` 是 **24 天**不是 24 小时（实测断言差值 `24.00:00:00` vs `1.00:00:00`），期望值改成小时数——字符串形态的时间期望值在这里会静默判错一个量级。`MainWindow.xaml.cs`（435 行零余量基线）零改动，调度全在协调器里。本地 Core 859/859、Broker 204/204 全绿（CI 为准）。**残余待裁决**：清空订阅源只停止重取，不解除已生效名单也不删缓存（放松防护的方向）⇒ 新登 §五 Q54 |
| AEG-011 / R8-DEPS-8 | **P2**（外部审计声称 P1，回读后裁 P2：这是加固面缺失而非可利用缺陷）→ 落地 | 保留并落地 | 审计要的两件事里只做了一件半：`dependencyLocking` 已启用，dependency **verification**（整树校验和/签名）没做 ⇒ 新登 §五 Q55。回读把第八轮 R8-DEPS-8 的判据更正为「`lockAllConfigurations()` 覆盖的是项目全部**可解析配置**（含 AGP 变体、测试、lint、ktlint/detekt 工具面），不是只覆盖直接依赖」；AD-155 当年的否决理由「双源维护成本」在 STRICT 下翻转成门禁本身——catalog 改了而锁没重算，解析直接失败而不是静默漂移。**故障注入实证两次**：①删掉 `android/app/gradle.lockfile` ⇒ `Locking strict mode: Configuration ':app:debugCompileClasspath' is locked but does not have lock state`（EXIT=1）；②给模块加一条新依赖 `org.apache.commons:commons-text:1.15.0` ⇒ `Resolved '…commons-text:1.15.0' which is not part of the dependency lock state`（EXIT=1）——这条在**改成 root 单源之后又重跑了一次**（注入点 `:contracts:compileDebugKotlin`），证明单源形态下 enforcement 仍然生效，不是「写在模块脚本里才管用」。顺带抓到一个**判据陷阱**：`:app:dependencies` 报表任务把解析失败吞成 `FAILED` 文本并 EXIT=0——所以「锁是否可消费」绝不能用报表任务证明，必须用真正吃 classpath 的任务；这条决定了 dependency-relock 的 gradle 面怎么写。落地＝锁块**单源**写在 root `android/build.gradle.kts` 的 `subprojects` 作用域（模块脚本零副本；本来按「逐模块各写一份」做，是 `:app` 脚本停在 **316 行零余量基线**放不下第 5 行逼出了这个更好的形状——单源顺带把「新增第五个模块忘记加锁」从静默 fail-open 变成自动覆盖）+ 四把入库 `gradle.lockfile`（app 314 行/四把共 277 个唯一坐标）+ 新常驻 `tests/python/gradle_locking_test.py`（9 例：模块清单从 settings 现取、锁块同形、锁文件形态与精确版本、CI 解析的配置必须在锁里、ktlint/detekt 工具面也进锁、SECURITY.md 与 settings 决策记录对得上）+ `relock_sop_test.py` 的 gradle 半边（**重锁任务清单 ⊇ CI 各 workflow 的解析面**，删一条即判红）+ `dependency-relock.yml` 新增 `gradle-relock` job（ubuntu + 与 android-quality 同款 JDK/SDK 口径，只写 deps/* 分支）。本机限制如实登记：`:app:assembleRelease` 在本机 Windows 跑不动（AAPT2 windows daemon 缺 UCRT），release 面的锁覆盖是用 `:app:dependencies --configuration releaseRuntimeClasspath` + broker/adapter 的 release 配置条目实证到位，真正的 release 构建要等 CI 的 ubuntu runner。 |
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
     dependency **verification**（整树校验和/签名）没做 ⇒ 新登 §五 Q55。
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
- ~~Q6 R9-AD-6~~ **R9-B24 已闭**（§3.24）：`approvePendingDownload` 补 `currentWebView()` 归属判定
  （不符**不清槽**，与导航同口径），`newTab`/`switchTo` 各补 `rejectPendingDownload()`；
  新常驻 `DownloadConfirmationOwnershipTest.kt` 7 例，本地 `:app:testDebugUnitTest` 315 例 0 失败。原条目 ↓
  Q6 R9-AD-6 | **P2**（外部审计 AX-07 同一处，由 P3 提级）| `BrowserViewModelConfirmations.kt:104-108`：下载确认缺「仅当前活动标签
  可消费」的归属校验（导航确认有，AD-158），且 `switchTo` 撤销 pending 导航确认却不撤销
  pending 下载确认 ⇒ 后台标签的危险扩展确认可顶到前台标签被批准。提级理由（本批回读）：
  授权必须绑定具体操作与发起者，同一文件里导航确认已经做对（`BrowserViewModelConfirmations.kt:80`
  的 `pending == null || currentWebView() !== pending.webView` ⇒ 拒），而 `approvePendingDownload`
  （:104-108）取出 pending 即 `proceed()`＝用户批准的对象被换成了另一标签的目标 ⇒ 批次 2。
- Q7 R9-AD-7 | P3 | `TabManager.kt:109-130`：`closeTab` 三条 when 分支的行内注释整体错位
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
- Q10 R9-AD-10 | P3 | `AegisHomeBridge.kt:95-121` + `SecureWebViewFactory.kt:127-132`：
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

- Q55 R9-AD-12 | P2 | `android/settings.gradle.kts:9-15`（`dependencyResolutionManagement` 的两个仓库源）↔ `android/gradle/`（**无** `verification-metadata.xml`）：
  项 10 落的是**版本锁定**（`gradle.lockfile` 记 group:name:version，**不含校验和**），  外部审计 AEG-011 处方里的另一半 **dependency verification**（`--write-verification-metadata  sha256` + `verification-metadata.xml` + 构建时 `--dependency-verification=strict`）没有做。  差别是可利用的：锁防住「今天解析到新版本」，防不住「同一个坐标的构件被换成别的字节」  （仓库被投毒 / 镜像与上游不一致 / 本地缓存被改写都落在锁的覆盖面外）。本批不顺手做的原因：  开启后**任何**新增依赖都要重算校验和，且 Gradle 默认对缺失条目 fail-closed ⇒ 与 Dependabot   的自动 bump 流是产品级流程变更（要先定「谁签、校验和从哪来、trusted artifacts 怎么豁免」）  ⇒ §四 待裁决。验收口径：CI 里 `--dependency-verification=strict` 跑通  `:app:assembleRelease`，且注入「改动某个 jar 的字节」必须判红。

### 5.2 SH（shared 壳层与契约）

- ~~Q11 R9-SH-1~~ **本批已闭**（R9-B35 / §3.35：三张 schema 的 `version.pattern` 合一，并与 `release/update_verifier.py` 逐案等价；release/version 两张 schema 的向量面补齐，`version.schema.json` 从此有消费者）。原条目：Q11 R9-SH-1 | P2 | `contracts/schemas/release.schema.json:12` 与
  `contracts/schemas/version.schema.json:12` 的 SemVer pattern 仍是旧宽松式（接受
  `2.2.0-01`、`2.2.0-beta.`、`2.2.0-..`），PY-279 只收紧了
  `contracts/schemas/update-manifest.schema.json:26`；而 `release/update_verifier.py:44-53`
  对这些抛 UpdateRejected ⇒ 发布声明说合法、客户端验证器判非法。两张 schema 零向量
  （PY-013 的向量面只覆盖 4/7）。
  **登记里有一处需要改准**：PY-279 收紧后的 update-manifest 式**仍放过** `2.2.0-01`
  ——前导零规则不在正则里，而在客户端另一段 `_NUMERIC_ID`（PY-184）。所以本批把三张 schema 一起换成与验证器逐案等价的式子，而不是只把两张旧的改成 PY-279 那份。
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
  （WB-133 的锁）。——**本批已回读确证并落地**（§二 R9-SH-4：外迁成新文件 `tests/ui-regression/snake_guard_slice.test.mjs`，原文件在零余量基线上）。
  **R9-B33 补一刀（§3.33 第 7 条）**：那把恒绿的旧断言当时只是「另有一份强的」，本体仍留在
  `start_page.test.mjs` 里——同批的 WB-141/WB-142 也是同一形态。三段已删（−16 行），其中
  WB-142 的三个控件与 WB-141 的三个系统色并进 `start_a11y.test.mjs` 的按花括号配对切片，
  各带反向锚。**留着的后果就是「新旧双双仍绿」这句话到今天还成立**——删掉才算闭。
- Q15 R9-SH-5 | P2 | `contracts/policy/action-catalog.yaml:14-35` 声明
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
  （此处原写「`native-navigation-decision` 已有 C# 消费者 `BrowserPolicyBrokerNativeGateTests.cs`，
  可作为接法模板」——**已被 R9-B39 推翻**：该文件唯一的命中是 `:260` 的一句解释性注释，
  没有任何代码读这份向量，登记表已改回 `{"RS"}`；Windows 侧至今仍是零执行者）；
  ③Agent 端不消费任何契约向量，而 `action-catalog.yaml` 的 `confirmation/risk/audit` 三列
  也不被 broker 读（R9-SH-5）⇒ 两端各说各话。
  不顺手做的原因：每一档都要在端侧新增/改写裁决实现（不是加测试文件就有数），且第①档与
  AX-02 是同一次改造。门禁已把当前事实钉住：**将来任何一端接上消费者，表不改就判红**，
  所以这笔账不会再变成第二段声明。
  **R9-B39（§3.39）做了第 0 档：先把「消费」这个词本身判干净**——命中口径剔注释后实测
  21 份向量只有 1 份端集变化（`native-navigation-decision` 由虚记的 CS+RS 改回 RS），
  其余 20 份逐份复核确认真在代码里命中；同时把本条上面那句失实的「已有 C# 消费者」改掉。
  三档缺口**仍在**，且现在才是可信的缺口数。

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
- ~~Q49 R9-DOC-20~~ **本批已闭**（R9-B33 / §3.33：`docs/runbooks/device-validation.md:19` 按代码改真，
  读的是 `WebView/HostWebView.cs:268`、`Core/Downloads/DownloadPolicy.cs:46`、
  `Broker/BrowserPolicyBroker.cs:111`、`Core/Downloads/DownloadItem.cs:114` 四处实际链）。
  原条目：Q49 R9-DOC-20 | P3 | `docs/runbooks/device-validation.md:19`（Windows 第 6 步「下载 MIME 混淆」预期写
  「下载经 broker 判定（MIME/最终 URL/size）」）：本批只确证了 Android 那一行（Q37→R9-DOC-06），
  **C# 侧未验**——Windows 下载链是否真判 MIME/最终 URL/size 没有实测支撑，故该行仍是一条未核验陈述
  （下一批读 `windows/.../Downloads/` 后改真或续登）。
  结论：**「判 MIME / 判 size」两句都不成立**（`TotalBytesToReceive` 只喂进度条），真实判定面是
  危险扩展名三候选 + kill-switch + 保留地址 + 会话/标签上下文 + 无确认订阅者 fail-closed。

- Q56 R9-CI-14 | P2 | `.github/workflows/gradle-dependency-graph.yml:14-25`（触发面只有
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
  验证面（见 §四），不在本批顺手改。②残余分歧一处：C# 用它提前捕获的
  `origDefineProp`（`FingerprintShield.cs:66`，防页面前篡改 `Object.defineProperty`），
  核心与 Android 直接引用 `Object.defineProperty`——三端「用哪一份定义器」不同形，
  统一到 `origDefineProp` 形态才是完整收口（本批的三端同形判据只覆盖六个共用片段，
  没有把这条差异算进去，`timer_parity.rs` 的负向锚也只判冻结实例描述符）。

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
   dependency verification 那一刀 ⇒ §五 Q55。
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

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
| R9-RS-8 | P2 | 提升/门禁缺失（已补门禁并落地） | 定稿项 9 步 1：三端各自抄写的那段共享 JS **没有任何门禁判它是否还同形**——`verify_seed_framing_parity.py` 只查要件 token 在不在（有人改算法它照样绿），`tests/canvas_read_channels.rs` 对两端只查 5 段片段（R9-RS-7 记的余量）。落地新门禁 `contracts/codegen/verify_injected_js_parity.py` + 解释层 `injected_js_text.py`，口径是**逐 token** 而非逐字节（逐字节要有一端出生成物＝定稿项 9 步 2，仍在待定稿面）；钉表 7 个共有函数为下界，少一个判「共有面塌缩」不放行 |
| R9-RS-9 | P2 | 问题/三端语义分歧（本批登记不修） | `core/.../shield/canvas.rs:99,106` ↔ `windows/.../FingerprintShield.Canvas.cs:108` ↔ `android/.../WebViewHardeningCanvas.kt:80,112`：两条像素直读包装里「把 proxy/orig 交给 ToStringGuard」的写法三端各不相同——Rust 走 `try { if (window[Symbol.for(REG_SYM)]) …(proxy, orig); }` 配空 catch、C# 调 `registerProxy(...)`、Kotlin 用 `if (__aegisReg) __aegisReg(...)` 且其 **catch 体是 `return orig.apply(...)`**（与 Rust 的空 catch 行为不同）。同批实测还发现两处纯命名漂移已改掉（Kotlin `noiseBit`→`up`、`MAX_NOISE_PIXELS`→`AEGIS_MAX_NOISE_PIXELS`，值本就一致）。注册窗口这条牵动 R8-RS-09 / R9-AD-1 的三端装配，须带测试另批统一；新门禁先把它**显式挂起**并核对「登记项必须仍然不同形」，修齐当天门禁判红一次要求收编 |
| R9-SH-2 | P2 | 保留并落地（锁自身失效） | 逐行回读 Q12 并复现：`start_a11y.test.mjs:25-30` 的 `mediaBlock()` 把「媒体块」切成「本 at-rule 到下一个 `@media`」——coarse 块实际 244-259 行，旧切片却一路带到 :364（19189 字符），块外的 `.veil-btn {`（:324）与 `.engine-item:focus-visible`（:353）都算块内命中，且不剔注释（:245-247 的注记原文就写着 `.engine-item`）。**内存态实证**：从 :248 的保底选择器列表摘掉 `.engine-item, .veil-btn`（即回退 R8-SH-13 半个修复），这把新锁与旧的 WB-142 双双仍绿。→ 改成「去注释 + 花括号配对切闭合块 + 边界自证」，并把判据抽成 `touchProblems(css)` 做反向锚（摘保底、把宽度改回 28px 都必须判红） |
| R9-SH-3 | P2 | 保留并落地（零判定） | Q13 确证：`start_main.test.mjs:313` 注释写「触发按键不得选中引擎（仅 Enter/Space）」，实体是一行 `assert.ok(true)`，而同一 `makeHost()` 已把 `setEngine` 记进 `state.engineCalls` 却没用。→ 换成 `assert.deepEqual(state.engineCalls, [], …)`（该文件是 579 行零余量基线，故净零行：改一行注释 + 一行断言、解构多取一个 `state`）。**故障注入自证**：给 `start.main.js` 的 ArrowDown/ArrowUp 分支加一句 `selectEngine(idx)` ⇒ 该用例立刻判红并打出正确消息；还原后 114/114 绿。Enter/Space 的正向面全仓仍零覆盖，另登 R9-SH-12（队列新增 Q47） |
| R9-SH-4 | P3 | 保留并落地（切片无界） | Q14 确证：`start_page.test.mjs:403-405` 用 `SNAKE.substring(SNAKE.indexOf("document.addEventListener('keydown'"))`——`indexOf` 失配返回 -1 时 `substring(-1)` 按 0 处理 ⇒ 退化全文扫描；命中后又一路读到文末。而 `if (!isOpen) return;` 在 `start.snake.js` 出现两次（键盘 :453、触摸 :472）⇒ 实测删掉键盘那一处仍绿。→ 外迁成新文件 `snake_guard_slice.test.mjs`（原文件 490 行零余量，加边界断言必增行）：有界切片 + 剔注释 + 两条反向锚，其中一条**把旧口径的漏判本身钉成文字**（同一删改下旧写法必须仍“通过”） |
| R9-AD-4 | P2 | 保留并按**第四节处方**落地（不收紧段集） | 逐行回读 Q4 的三处位置：`OriginPolicy.kt:104-110` 的 `!host.contains("[")` 是 AD-299 刻意与 Rust `origin/tests/host_grammar.rs:183-184`（`try_parse_external("https://[::1]:8080/x") == None`）及 contracts 的 url-origin-invalid 向量对齐的**导航入口**判定；而 `LocalTargetHosts.hostOf:83-88` 反过来**剥掉**方括号（P74 那笔账的产物）⇒ `::1`/ULA 在升级豁免层与下载层确是放行形态。两侧都对，缺的只是把关系写下来：对象 KDoc 补该分层事实，新跨层锚用例把「导航拒 / 剥出 `::1` / 下载不拒」三侧各钉一次。用户可见后果如实记：地址栏输 `http://[::1]:9000/` 在 Android 打不开，Windows 能。打通它需解冻核心 host grammar 并增补向量 ⇒ 留在第四节待定稿，**本批零判定改动** |


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
5. **同批未做**：13(a)（把八处 dotnet 命令抽 composite）与 13(c)（出货 builder 钉
   `ubuntu-24.04`）——前者要动四条 workflow 的命令面且与 R9-CI-9 的接线锚耦合，后者
   属用户待定稿面。

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



## 四、待用户定稿（本轮新增两项，其余沿用第八轮 §七）

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
- Q2 R9-AD-2 | P2 | `TranslateEntry.kt:50`（`Uri.encode` 缺省保留 `:/?&=`）+ `:28`
  （`SENSITIVE_QUERY_PARAMS` 只精确匹配 code/state/token）⇒ 带多参页被截成错目标、
  `access_token`/`api_key` 原样外发；`TranslateEntryPrivacyTest.kt:41-47` 把 `keep=me`
  留在全码当期望值。建议改用仓内严格编码器 `SearchEngines.uriEncode`（纯 Kotlin 单源，
  已对 AOSP `Uri.encode` 做过 instrumented 对照矩阵）。
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
- Q17 R9-SH-7 | P2 | `contracts/codegen/verify_contract_compatibility.py:62-64,257-259,214`：
  `DESIGN_NOTATION_MIRRORS` 的 6 个名字恰等于生成镜像全集（两目录各 6 份）⇒ `:257` 一律
  continue、`:259` 的 `_has_real_consumer` 现树不可达；实测 ApprovalContract /
  AuditEventContract / CapabilityContract / UpdateManifestContract / VersionContract 在
  main 源码零真实引用（`VersionContract` 全树零引用）。**第八轮 R8-SH-08 重 derive 成功
  且仍未闭**（该轮只留了计数）。
- Q18 R9-SH-8 | P3 | `shared/shell/start.main.js:165-167` ↔ `shared/shell/start.js:41-49`：
  init 路径的 `getEngine` null 回包既不渲染也不 `bridgeError`（csCall 的惰性 TTL 清扫只在
  下一个请求时触发）⇒ 引擎胶囊永停在 `start.html:38` 硬编码「百度」且零痕迹；对照 WB-138
  已为书签做了 null/[] 分流。
- Q19 R9-SH-9 | P3 | `shared/shell/start.js:93-98`、`shared/shell/start.html:38`、
  `android/.../SearchEngines.kt:36,45`、`windows/.../UrlNormalizer.cs:21,50` ↔
  `scripts/verify_cross_end_lists.py`：引擎 **key 集合**已五端对账，但「默认引擎值」与
  「展示名」两份元数据 4 处手抄零判据 ⇒ 换默认值/改中文名只落一处不会红。
- Q20 R9-SH-10 | P3 | `contracts/vectors/capability-invalid.json` 第 2 条 note 称「schema
  minItems 未设——本向量按用户语义拒绝」，而 `contracts/schemas/capability.schema.json`
  已设 `minItems: 1`（`validate_vector_schemas.py:170-171` 对该文件不设语义豁免）⇒
  拒绝理由就是 minItems，注记是失实陈述。
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
  非策略 fail-open（`_wired` 末位置位 + `IsWired` 仍挡后续导航）。
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
- Q26 R9-RS-2 | P2 | `core/rust-policy-core/bindings/aegis_policy_core.py:1399`（入库生成物
  由 2026-10-03 `495a49c` 产出，不含 2026-10-04 `607d7a1` 新增的 `#[uniffi::export]
  update_host_denylist`）↔ `core/rust-policy-core/src/ffi/broker.rs:331` ↔
  `.github/workflows/core-rust.yml:57-63`：「绑定由锁定 toolchain 单源生成」目前只由一个
  `test -s` 非空断言守着，判的是刚写出的文件、不比漂移 ⇒ 导出面少一个方法在任何门禁里
  都不红；且该 `.py` 全仓零消费者。建议：删这份无人消费的入库件，或把 `test -s` 换成
  「重生成 + 与入库件 diff」。
- Q27 R9-RS-3 | P3 | `core/rust-policy-core/Cargo.toml:41-44`：注记写「getrandom 0.2→0.3，
  0.3 为当前主线」而实际 pin 是 `getrandom = "0.4"`；又写「ed25519-dalek 经 rand_core 0.6
  仍消费 getrandom 0.2」，`Cargo.lock` 实为 rand_core 0.9.5 + getrandom 0.3.4
  （ed25519-dalek 3.0 / curve25519-dalek 5.0）⇒ 下一批依赖决策按注记推断会取错对象。
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
- Q30 R9-RS-6 | P3 | `core/rust-policy-core/src/security_policy.rs:233-275` +
  `src/security_policy/tests/scheme_and_host_predicates.rs:94-105`：`is_high_risk_host` 是
  `pub` 且签名不体现「入参须已剥端口」这条硬不变量，`169.254.169.254:8080` 判**低危**
  并被 `:101` 钉成期望值，安全全靠 `policy_host_of` 单点纪律（`src/ffi/broker.rs:124`）
  ⇒ 未来任一新增调用点忘记剥端口即静默放行元数据端口的非默认端口形态，且无红可看。
- Q31 R9-RS-7 | P3 | `core/rust-policy-core/tests/canvas_read_channels.rs:101-114`：对两端
  只查 5 段片段，不查 `pixels.length === width*height*4` 与两条 `aegisNoiseRectangle`
  调用行 ⇒ 端上删掉 8 位 RGBA 守卫不会红（B2/⑦ 本体一致，此为测试余量）。

### 5.2.1 本批落地时新增队列（同口径：必须带 file:line）

- Q47 R9-SH-12 | P3 | `shared/shell/start.main.js:83` ↔ `tests/ui-regression/start_main.test.mjs:307-313`：`Enter`/`空格` 选中引擎这条**正向**判据全仓零覆盖（:83 的 `if (ev.key === 'Enter' || ev.key === ' ')` 无任何用例驱动），而 :87 的方向键分支刚被 R9-SH-3 补上反向判据——只锁一侧意味着「把 Enter 整条删掉」仍全绿。补法：在同一用例里对 `items[1]` 触发 Enter 并断 `state.engineCalls` 增长（`start_main.test.mjs` 在 579 行零余量基线上，需先净减）。
### 5.5 DOC（文档 vs 实树）

- Q32 R9-DOC-01 | P2 | `README.md:35-37` 仍写「**仍待裁决**：Android 侧 http 一律升 https
  且 `cleartextTrafficPermitted=false`，内网 IP 字面量实际仍不可达（§七 2）；子资源策略链
  异常时的失败闭合方向（§七 5）」——两项均已定稿并落地：`LocalTargetHosts.kt` 存在、
  `android/app/src/main/res/xml/network_security_config.xml:34-41` 有有界
  `cleartextTrafficPermitted="true"` 且显式列 `192.168.1.1`、Windows 侧
  `WebView/HostWebView.WebResourceGuards.cs:37,102` 有 `SubresourceDenialFailClosed`。
- Q33 R9-DOC-02 | P2 | `docs/adr/ADR-007-canonical-stack-and-single-source-guards.md:50`
  写「**C#**：无注入 JS（走 WebView2 Settings 收紧），不在本门禁范围」，实测
  `windows/src/Aegis.Windows.App/WebView/WebView2Hardening.cs:77` 调
  `AddScriptToExecuteOnDocumentCreatedAsync(FingerprintShield.BuildScript(…))`；
  `README.md:43`、`SECURITY.md:34` 均已改称「C# 的文档创建前注入面」。缺的是**该面未纳入
  bridge_guard 对账**，不是「无注入面」。
- Q34 R9-DOC-03 | P2 | 同文件 `:57-58` 写「门禁型 workflow（android-quality/contracts/
  core-rust/agent-redteam/supply-chain/ci）移除全部 `paths:` 过滤」，py-yaml 实测
  `push.paths`：`ci`=8、`core-rust`=3、`agent-redteam`=5、`supply-chain`=11，只有
  `android-quality`/`contracts` 真无过滤 ⇒ 未列路径的改动静默不触发即被判「门禁已过」
  （R8-SH-10 只处理了 `ci.yml` 一处）。
- Q35 R9-DOC-04 | P2 | `docs/architecture-overview.md:91-100` 声明「16 workflow 分层」但
  分解为 6+1+2+2+4=**15**，依赖面只列 `gradle-dependency-graph`/`gradle-dependency-insight`、
  漏 `dependency-relock.yml`（`:151` 又说 16）⇒ `check_doc_claims.py` 只比裸数字
  （正则 `N workflow`），本条全绿而清单少一整面。
- Q36 R9-DOC-05 | P2 | `docs/product/feature-parity-checklist.md:22` M1 行「ESM（探测启用）…
  ☑（SDK 未暴露 API——反射探测，**升级自动生效**）」已被
  `windows/src/Aegis.Windows.App/WebView/WebView2Hardening.cs:34-42` 就地反证（R8-DEPS-1：
  两版 stable DLL 对 `EnhancedSecurityModeState` 均 0 命中，ESM 只在 `-prerelease`）。
- Q37 R9-DOC-06 | P2 | `docs/runbooks/device-validation.md:33` Android 第 4 步预期写
  「经 **broker** 判定（MIME/最终 URL/size/目录）」，实测链是
  `WebViewDownloadHandler.kt:113-114` 的 `WebViewDownloadTargetGuard`（scheme/保留地址）
  + `DownloadPolicy` 扩展名判定（grep mime|size 零命中、不经 `AndroidBroker`）⇒ 按现文
  执行会把「无 size/目录门禁」记成通过；而**已落地**的 #130 下载层保留地址硬拒反而没有任何
  真机步骤。
- Q38 R9-DOC-07 | P2 | 同文件 `:20` Windows 第 7 步未写启用前置：
  `WebView/NavigationConfirmationGate.cs:14-22` 只认 `AEGIS_REQUIRE_NAVIGATION_CONFIRMATION=1`
  或注册表，而 `docs/release/AegisSetup-CSharp.iss:73` 注明该标记**刻意不写**（只写
  `RequireNativePolicyCore`，:79）⇒ 唯一发布制品上面板永不出现，验证人会「看不到面板」
  而误判缺陷，或凭 UI 存在与否签一个无证据的通过（§十一 第 5 类「结论无证据」）。
- Q39-Q46 R9-DOC-08..15 | P3 | 八条：`docs/runbooks/windows-run-guide.md:63-66` 写「真机验证
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

# Android 构建类路径依赖告警分诊（2026-10-03）

**背景**：Gradle-Dependency-Graph 接入（PR #62，SP-246 收尾）后，Dependabot
alerts 首次对 Android 构建面生效——11 项告警（1 critical / 3 high / 4 medium /
3 low）。本文档记录分诊证据、已落地修复与剩余项的处置依据。

## 一、暴露面判定（关键证据）

`gradle-dependency-insight.yml`（dispatch 诊断工具）实测三条 classpath 闭包：

| 闭包 | 受影响包命中 | 结论 |
|---|---|---|
| `:app:debugRuntimeClasspath`（产品 APK 面） | **零命中** | **产品不受影响**——受影响包全部不在出厂制品内 |
| `debugUnitTestRuntimeClasspath`（测试面） | 仅 bcprov（经 Robolectric BOM 约束已解析 **1.85** 修复版） | 测试面干净 |
| build classpath（`buildEnvironment`——构建机面） | bcprov/bcpkix 1.80.2、jose4j 0.9.5（bundletool）、jdom2 2.0.6（jetifier）、commons-lang3 3.16.0（sdklib）、httpclient 4.5.6（sdklib） | **全部为 AGP 9.4.1 构建类路径传递依赖** |

即：受影响代码只在**构建机（dev/CI）执行构建时**存在于 AGP 工具链进程内；
攻击面 = 恶意输入喂给 jetifier/bundletool/sdklib 的构建期场景，产品运行时
零暴露。

## 二、已落地修复（PR #65）

`android/build.gradle.kts` 根加 **buildscript 类路径安全地板**——与 plugins
DSL 类路径同域冲突解析（地板后 insight 复测：classpath 配置内
`commons-lang3:3.16.0 -> 3.18.0`、`bcpkix:1.80.2 -> 1.84` 等箭头实证）：

| 包 | 地板版 | 对应告警 |
|---|---|---|
| bcprov/bcutil-jdk18on | 1.85 | #11(critical)/#12/#8 |
| bcpkix-jdk18on | 1.84 | #7 |
| jose4j | 0.9.6 | #5（已消除） |
| jdom2 | 2.0.6.1 | #4（已消除） |
| commons-lang3 | 3.18.0 | #3 |
| httpclient | 4.5.14（钉版防回退） | #2 |

验证：android-quality（ubuntu）/contracts/native-policy 门禁全绿 +
release-android dispatch 走真实 assembleRelease/打包/对齐链全绿（
含 SP-223 readelf 探针加固——窄输出折行缺陷修复，见该 workflow 注释）。

## 三、剩余告警处置（9 项）

地板后图重提交（08:05Z）仍有 9 项 open：bcprov×3、bcpkix、lang3、
httpclient（AGP 传递）+ logback×3（低危）
——**logback 的「不在本仓任何解析树内」是失实陈述，R9-B49 现读更正**：四把入库锁里
`ch.qos.logback:logback-core:1.3.16=ktlint` 与 `logback-classic:1.3.16=ktlint` 各出现一次
（`android/app/gradle.lockfile:106-107`、`broker:5-6`、`contracts:5-6`、`webview-adapter:15-16`），
父节点是 ktlint-cli 1.8.0 的传递依赖。这句话此前能活下来，是因为
`gradle-dependency-insight.yml` 只扫 `buildEnvironment` + `debugRuntimeClasspath` + 
`debugUnitTestRuntimeClasspath` 三条面，**从没扫过承载这 9 条告警的两条工具面**
（`androidLintTool`、`ktlint`）——本批把这两条面补进该 workflow，并把结论钉成常驻门禁
`scripts/verify_gradle_alert_scope_boundary.py`）。判定：**地板不可达面**——这些版本记录存在于
AGP 插件 detached 配置的独立解析域，用户侧无法对插件内部传递依赖做
版本选择（jose4j/jdom2 之所以能消除，是其脆弱节点仅存在于已修的
classpath 域）。

**判定：tolerable_risk**（构建机侧暴露、产品运行时零命中、上游无稳定修复）。

> **执行结果（2026-10-13 16:15Z 实测，API 回读）**：`open=0` / `dismissed=9` / `fixed=3`；
> 每条 `dismissed_reason=tolerable_risk`、`dismissed_at` 均已写入，逐条
> `dismissed_comment` 含该坐标的锁文件行号与 configuration 名。
> 一个实测到的 API 约束值得记下：**`dismissed_comment` 上限 280 字符**（首次提交 566-763 字符
> 被 422 拒），所以完整证据只能留在本文档，comment 里是指针 + 一行关键证据——
> 这正好是「注释不能替代单源」的又一次实证：如果当初没写这份文档，dismiss 就只能凭记忆。
> 另一次实测：`dismissed_reason` 的合法取值是
> `fix_started / inaccurate / no_bandwidth / not_used / tolerable_risk`（422 报错列出的清单），
> 本文判的是 `tolerable_risk`——**不是** `not_used`：这些坐标确实被构建用着，
> 只是不在出货面上，选错这个枚举值本身就是一种失实陈述。

> **R9-B49（2026-10-13）执行与留痕**：用户授权后，本文档列出的 9 条告警在 GitHub 上以
> `dismissed_reason=tolerable_risk` 正式 dismiss，dismiss comment 逐条引用本文的锁文件
> 行号与配置名。**dismiss 不是终点**：它依赖的事实（这 5 个坐标只在工具/测试类路径里）
> 现在由 `scripts/verify_gradle_alert_scope_boundary.py` 常跑判定——任何一条坐标进
> `release/debug Runtime|Compile Classpath` 或 `debugAndroidTest*Classpath`（装进设备的那份）
> 即判红；上游若把节点整体移除（锁里再也找不到该坐标），也判红——那时登记表与本文要同步，
> 而不是继续挂着一条已无载体的 dismiss。解除条件仍是 AGP 9.5+ 携带修复版传递依赖。
>
> （本段原文写 `dismissed_reason=tnt（对项目不适用）`——那是首稿的措辞，R9-B49 实测
> API 只接受 `fix_started / inaccurate / no_bandwidth / not_used / tolerable_risk`，
> 实际执行用的是 `tolerable_risk`（上一段的 16:15Z 回读就是它）。留这条更正而不是静默改掉：
> 一份安全处置文档里写了一个**不存在的枚举值**，读的人就无法复核当时到底做了什么。）

> **R9-B60（2026-10-14）现读：那 9 条 dismiss 已经被 GitHub 重开，本文不再是「已 dismiss」状态**。
> API 回读（2026-10-14T08:46:08Z 现跑 `gh api .../dependabot/alerts`）：`open=9` / `dismissed=0` / `fixed=3`，9 条编号
> #12 #11 #10 #9 #8 #7 #6 #3 #2，`updated_at` 全部落在 **2026-10-14T07:09:5xZ**——
> 也就是 PR #197 并入（07:09:20Z）之后紧接着的那次扫描。
> 机制不是「谁删了我们的处置」，而是 Dependabot 的正常行为：**只要该 vulnerable 版本仍然
> 可以在依赖图里解析出来，下一次扫描就会把已 dismiss 的告警重开**。现读锁面给出的正是这一条：
> `org.bouncycastle:bcprov-jdk18on:1.80.2=androidLintTool`，而 #12/#11 的范围是 `< 1.85`、
> #8 是 `>= 1.74, < 1.84` ——1.80.2 仍然命中；同批 `1.85` 只出现在 `debugUnitTest*` 三条配置里。
>
> 因此这份文档的**当前状态是 open**，而「tolerable_risk」这个判定成立的依据**不是**告警状态，
> 是 scope 门禁那句现读结论（5 个坐标全在 `androidLintTool` / `ktlint` / `debugUnitTest*`，
> 零命中出货与装机 classpath）。两条可依赖的东西与一条不可依赖的东西就此分开：
> - 可依赖：`verify_gradle_alert_scope_boundary.py`（PR 面常驻，判坐标归属）；
> - 可依赖：本文的判定与证据（锁文件行号 + configuration 名）；
> - **不可依赖**：GitHub 侧的 alert `state`——它会随扫描自行翻转。
> 本想让 `gradle-dependency-insight.yml`（dispatch-only 诊断面）现读并报告告警状态，
> **实测做不到**：Actions 的 `GITHUB_TOKEN` 调 `GET /repos/{owner}/{repo}/dependabot/alerts`
> 返回 **403 `Resource not accessible by integration`**（run 38542830575，权限里已写
> `security-events: read`；同一条命令在会话里用用户凭据跑则正常返回上面那三个数）。
> 那一步因此撤掉——留着它只会输出一段没人读的 403 正文，而它带 `continue-on-error`、
> 作业照样绿，「有报告」就成了一种假象，比没有更坏。以后真要接：需要一个只读 PAT
> （属新增凭据，需仓库所有者点头）。现状保持**状态由人来现读**，判据只建在锁面坐标归属上。
> 同批修好的倒是那条一直坏着的诊断步骤（§3.60 第 5 条：它站在 `working-directory: android`
> 的 job 里找 `scripts/…`，自 R9-B49 起从没跑通过，而失败之前还先打印了一句看起来像结论的
> `(零命中)`）。
> 是否再 dismiss 一次（会再次被重开，形成拉锯）、还是去把 `androidLintTool` 那份 1.80.2
> 顶到 ≥1.85（需要动 AGP/lint 工具面，属构建面变更）——**都是需要仓库所有者点头的操作**，
> 本文只把两个事实与代价写清，不代做决定。

> ⚠ **R8-CI-06 更正（第八轮 2026-10-05）**：本段原文写作「处置：tolerable_risk……
> 附证据 **dismissing**」，把「判定」表述成了「已在 GitHub 上执行的操作」。
> 只读复核实测：9 条告警全部 `state=open`、`dismissed_at` 为 null，`dismissed`
> 计数 0（#11 critical bcprov / #12 high bcprov / #8 #7 #3 #2 medium /
> #10 #9 #6 low）——即这批告警**一条都没有被 dismiss**，只是被分诊过。
> 本表的严重度列与实况一致，问题只在这句状态描述。
>
> dismiss 一条 Dependabot 告警是对该仓安全姿态的正式处置声明（影响所有读该仓
> 告警面的人，且默认不在任何 CI 门禁里留痕），属仓库所有者操作，需你确认后执行。
> 本轮只更正陈述、不代做操作。若确认按「tolerable_risk」正式 dismiss，
> 需要连证据一起写进 dismiss comment，并保留下面的解除条件。（→ 2026-10-13 已按此执行，见下一段）

解除条件：AGP 9.5 stable 发布（当前 alpha——9.5 内 tools/bundletool 预期携带
修复版传递依赖）→ 重开评估，届时地板可整体退役。

| 告警 | 严重度 | 包 | 脆弱版本 → 修复版 |
|---|---|---|---|
| #11 | critical | bcprov-jdk18on | <1.85（Name Constraints bypass） |
| #12 | high | bcprov-jdk18on | <1.85（ASN.1 nesting-depth） |
| #8 | medium | bcprov-jdk18on | LDAP injection <1.84 |
| #7 | medium | bcpkix-jdk18on | Risky Crypto <1.84 |
| #3 | medium | commons-lang3 | Uncontrolled Recursion <3.18.0 |
| #2 | medium | httpclient | XSS <4.5.13（树内已解析 4.5.14） |
| #6/#9/#10 | low×3 | logback-core | 1.5.25/1.5.33/1.5.34 |

## 四、复检规程

1. `gh workflow run gradle-dependency-insight.yml`（master）→ 看 build-env.txt
   命中行与 `->` 解析箭头；
2. AGP 9.5 stable 发布后：bump `libs.versions.toml` 的 agp → 跑 insight 复查
   → 逐一 reopen/复核剩余告警 → 地板退役评估。

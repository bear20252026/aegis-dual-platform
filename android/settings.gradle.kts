pluginManagement {
    repositories {
        google()
        mavenCentral()
        gradlePluginPortal()
    }
}

dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)
    repositories {
        google()
        mavenCentral()
    }
}

// AD-155（审计 2026-09-23 清单·A7 批）的评估原文是「暂不启用」；2026-10-11 由外部第三轮
// 审计 AEG-011 + 用户定稿「全部完成」重开并**启用**。下面是启用后的决策记录（单源——
// 锁块单源写在 root `build.gradle.kts` 的 `subprojects` 作用域里，模块脚本零副本）：
// ① 覆盖面：`:app`/`:broker`/`:webview-adapter`/`:contracts` 四个模块的**全部可解析配置**
//    （`lockAllConfigurations()` + `LockMode.STRICT`，声明一次覆盖全部现有与后续子模块），
//    锁文件是各模块目录下的 `gradle.lockfile`。不覆盖的面如实登记：`buildscript {}` 与
//    plugins DSL 类路径是
//    **脚本类路径**，不在项目配置锁内——那一路的版本事实由 root `build.gradle.kts` 的
//    显式 classpath 地板（七条钉版）+ `gradle-dependency-insight.yml` 的 `buildEnvironment`
//    回读承接，别把「启用了 dependencyLocking」读成「构建机类路径也被锁住了」。
// ② AD-155 的「双源维护成本」这次不构成否决理由：原文担心 catalog 升级后忘 `--write-locks`
//    ⇒ CI/离线解析失败。在 STRICT 下那个失败**就是门禁本身**——它把版本漂移从「静默发生」
//    变成「必红」，所以代价与收益是同一条。重锁已工具化：
//    `.github/workflows/dependency-relock.yml` 的 `gradle` 生态（仅 workflow_dispatch，
//    写回目标前缀由 `target_kind` 选，规则单源 `scripts/relock_branch_guard.sh`，
//    永不写 master）。本地等价命令**不是** `writeLocks` 任务
//    （Gradle 9.8 实测：`Cannot locate tasks that match ':app:writeLocks'`），而是
//    「`./gradlew resolveAllConfigurations --write-locks`」——`--write-locks` 只写本次构建
//    **解析过**的配置，所以解析面必须按模型的集合定义，不能照任务清单抄：R9-B32 实测
//    `:app:androidTestUtil` 这类配置由 AGP 的 UTP 构建监听器解析，不属于任何 gradlew 任务
//    名称面，照清单抄必然漏（漏掉的红不在 PR 面，在 master 的依赖图生成作业上）。
//    判据是 root 里的 `verifyDependencyLockCoverage`（枚举 `canBeResolved` 集合与锁对账），
//    PR 面由 android-quality 跑，重锁面写完锁后同判据自证。
//    常规升级不必人工重锁：**已实证** Dependabot 的 gradle 生态会在同一个 PR 里
//    重算这四把锁（#167，2026-10-12：文件面是「四把 lockfile + libs.versions.toml +
//    wrapper」，且它解析到的配置数只增不减）。
// ③ 锁记「模块坐标 + 版本」，**不含校验和**；字节那一刀由 dependency verification 承担，
//    2026-10-13 由 R9-B50（台账 Q55）启用：`gradle/verification-metadata.xml`（sha256，
//    文档里 `<verify-signatures>false</verify-signatures>`——仓内没有受信 PGP 密钥，
//    打开它只会把解析失败伪装成供应链事件）+ `gradle.properties` 里的
//    `org.gradle.dependency.verification=strict`。文档被改坏时 Gradle **直接拒读**而不是
//    「当没这份文档继续构建」（实测：`<trust>` 放错层级即报 `Unable to read dependency
//    verification metadata`，2026-10-14），所以这一刀没有「静默失效」的第三条路。
//    生效面是**属性**而不是命令行参数，这一点
//    实测过：把 junit 那条 sha256 的末位改一个字符、`./gradlew :broker:testDebugUnitTest`
//    **不带任何校验参数**，45s 后 BUILD FAILED 并点名 `junit-4.13.2.jar (junit:junit:4.13.2)`
//    （报的是 `:broker:detachedConfiguration6`——工具类 detached 配置也在判面内）。
//    两把刀的重算口径**不同**，这是本条的重点：
//    · 版本按**配置的图**重算（`resolveAllConfigurations` 解析每个 `canBeResolved` 的配置图，
//      天然 ⊇ 任何任务清单，见 ②）；
//    · 字节按**配置的文件**重算（新任务 `resolveAllConfigurationFiles` 解析每个
//      `canBeResolved` 配置的 `.files`）。两者不能并成一条：图解析只取 `.pom`/`.module`，
//      一个 `.jar`/`.aar` 都不落盘，而 `--write-verification-metadata` 登记的正是落盘的字节。
//    · 只跑任务面也不行，只跑文件集合也不行：ktlint/detekt/lint/单元测试用的工具类路径是
//      任务执行时现建的 **detached 配置**，不在 `project.configurations` 里，只有跑那几个任务
//      才会落盘——所以重锁面留了这一小份任务清单，它与 CI 的对应关系由
//      `tests/python/gradle_relock_surface_test.py` 从 workflow 原文逐 token 判（构建类任务
//      已从这一面删掉：它们的 classpath 文件归集合口径管，两处各写一份就是两份真相）。
//    · 两条生成面都带 `--refresh-dependencies`。这是本条最贵的一课：校验和文档只能记录
//      本次**真正落盘**的构件，而长命的 `~/.gradle` 元数据缓存可以让一批 parent-pom/BOM
//      描述文件永不落盘——本地三条命令全绿，CI 的干净 runner 在两个平台同红 6 个构件
//      （guava-parent、junit-bom×3、kotlin-gradle-plugins-bom×2，配置名 `classpath`，
//      PR #189 实测）。不强制重取字节，「重算校验和」这句话就是假账。
//    覆盖面还会随解析增长（466→495 组件那批是图解析里「参与冲突裁决但未被选中」的候选版本），
//    且同一坐标的 `.pom`/`.module` 缺位同样会红——字节面按构件登记，不按「最终选了谁」登记。
//    **字节面还跟平台走**（R9-B51 / Q61）：`aapt2` 在 windows 落 `-windows.jar`、在 ubuntu 落
//    `-linux.jar`，两个不同 sha256，所以「一份文档服务两个 runner」要求每个平台都生成过一次。
//    这条不靠记性：`scripts/verify_gradle_platform_coverage.py` 把需求平台从 workflow 的
//    `runs-on` 现取（加一个 macos runner 不需要改判据代码），平台相关坐标缺任一形态即判红。
//    R9-B53（台账 Q61 的另一半）把「每个平台都生成过一次」从人的记性挪进了作业面：
//    `dependency-relock.yml` 的 gradle 生态是**两条腿串行**——`gradle-relock`（ubuntu，版本锁
//    + 字节）之后 `gradle-checksum-windows`（windows-2025，只重算字节、**不带** `--write-locks`）。
//    串行不是排版偏好：两个 job 并发推同一份 `verification-metadata.xml` 会互相覆盖，
//    后推的那一次带着旧检出重算，前一次的增补条目就地消失。文件面命令是**单源**的
//    `.github/actions/gradle-checksum-file-face`，两条腿各 `uses:` 一次——写两遍就是两份真相，
//    改一处漏一处的那类债（`tests/python/gradle_relock_surface_test.py` 按出现次数判死）。
//    执行面与锁同批：`dependency-relock.yml` 的 gradle 生态里 `--write-locks` 那条同时带
//    `--write-verification-metadata sha256`。**先有鸡还是先有蛋已经实证解开**：删掉整个 junit
//    组件块（等于一次版本升级带来的「新坐标没有条目」）后跑同一条命令，BUILD SUCCESSFUL
//    并把条目补了回来——生成模式对缺条目是**补录**不是判红。Dependabot 的 gradle bump PR
//    红在 strict 上是流程的正确表现：跑一次重锁让版本与字节同一批进来。R9-B58 起这一面
//    **不再需要人工搬分支**：dispatch 时选 `target_kind=dependabot`，写回目标落在
//    `dependabot/*`（台账 §五 Q60 因此闭环）。
//    别把 `org.gradle.dependency.verification` 改成 off/lenient 绕红灯（用例判的就是这个）。
// ④ AD-155 留的重开条件「若后续引入动态版本依赖」并未触发（现树仍零动态版本）；
//    真正增量是传递依赖钉版 + 升级必须同批重锁这条流程约束。

rootProject.name = "AegisAndroid"
include(":app")
include(":broker")
include(":webview-adapter")
// A-2 接线（架构审计 2026-08-31）：契约生成物纳入构建——此前 :contracts
// 从未被编译，schema 漂移只能靠 Contracts CI 的新鲜度 diff 间接发现
include(":contracts")

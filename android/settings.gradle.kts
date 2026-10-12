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
//    只写 `deps/*` 分支，永不写 master）。本地等价命令**不是** `writeLocks` 任务
//    （Gradle 9.8 实测：`Cannot locate tasks that match ':app:writeLocks'`），而是
//    「带上 CI 会跑的那批任务 + `--write-locks`」——因为 `--write-locks` 只写本次构建
//    **解析过**的配置，任务清单少一条就有一条配置没有锁状态（判据见
//    tests/python/relock_sop_test.py 的覆盖关系锚）。
//    常规升级不必人工重锁：**已实证** Dependabot 的 gradle 生态会在同一个 PR 里
//    重算这四把锁（#167，2026-10-12：文件面是「四把 lockfile + libs.versions.toml +
//    wrapper」，且它解析到的配置数只增不减）。
// ③ 锁文件记的是「模块坐标 + 版本」，**不含校验和**。给整棵树做哈希/签名验证是
//    dependency verification（`gradle/verification-metadata.xml`）那一刀，本批**不做**、
//    文档也不声称做了（SECURITY.md 的哈希覆盖口径按实写）。
// ④ AD-155 留的重开条件「若后续引入动态版本依赖」并未触发（现树仍零动态版本）；
//    真正增量是传递依赖钉版 + 升级必须同批重锁这条流程约束。

rootProject.name = "AegisAndroid"
include(":app")
include(":broker")
include(":webview-adapter")
// A-2 接线（架构审计 2026-08-31）：契约生成物纳入构建——此前 :contracts
// 从未被编译，schema 漂移只能靠 Contracts CI 的新鲜度 diff 间接发现
include(":contracts")

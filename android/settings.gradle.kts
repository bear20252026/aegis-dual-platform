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

// AD-155（审计 2026-09-23 清单·A7 批）：依赖锁定（enableDependencyLocking）
// 评估记录——结论：暂不启用，保留理由如下（P3 级加固，非缺口）：
// ① 版本面已全量钉死：所有依赖经 gradle/libs.versions.toml 精确版本单源
//    （无动态版本 / 无 -SNAPSHOT / 插件同样入 catalog——AD-242），可复现性
//    与锁文件等价（锁文件的增量价值仅剩传递依赖钉版）。
// ② 双源维护成本为负收益：启用后 catalog 每次升级（如 AD-099 的 JNA
//    5.12→5.19.1）都必须同步 --write-locks 重新生成 4 个模块的 *.lockfile，
//    漏更新即离线/CI 解析失败——引入与「版本单源」目标相悖的第二份
//    需人工同步的版本事实。
// ③ 锁文件与 --refresh-dependencies/依赖审计脚本（verify_release 面）
//    的交互需专项回归，当前批次无真机/CI 预算。
// 若后续引入动态版本依赖（当前为零），此评估必须重开。

rootProject.name = "AegisAndroid"
include(":app")
include(":broker")
include(":webview-adapter")
// A-2 接线（架构审计 2026-08-31）：契约生成物纳入构建——此前 :contracts
// 从未被编译，schema 漂移只能靠 Contracts CI 的新鲜度 diff 间接发现
include(":contracts")

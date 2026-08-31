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

rootProject.name = "AegisAndroid"
include(":app")
include(":broker")
include(":webview-adapter")
// A-2 接线（架构审计 2026-08-31）：契约生成物纳入构建——此前 :contracts
// 从未被编译，schema 漂移只能靠 Contracts CI 的新鲜度 diff 间接发现
include(":contracts")

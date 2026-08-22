plugins {
    id("com.android.application") version "9.3.1" apply false
    // AGP 9.0+ 内置 Kotlin 支持：org.jetbrains.kotlin.android 不再需要（官方迁移指引）
    id("org.jetbrains.kotlin.plugin.compose") version "2.4.10" apply false
    // 工具链 P0：Kotlin 风格检查（ktlint 官方推荐 Gradle 插件，14.2.0 为 2026-03 最新）
    id("org.jlleitschuh.gradle.ktlint") version "14.2.0" apply false
    // 工具链 P0：Kotlin 静态分析/代码异味（detekt 官方 Gradle 插件，版本与 detekt 一致）
    id("io.gitlab.arturbosch.detekt") version "1.23.8" apply false
}

plugins {
    // AD-242（2026-09-26 审计）：插件版本经 gradle/libs.versions.toml 单源
    // （此前本块字面量散落——与 app 依赖 catalog 化口径对齐）
    alias(libs.plugins.android.application) apply false
    // AGP 9.0+ 内置 Kotlin 支持：org.jetbrains.kotlin.android 不再需要（官方迁移指引）
    alias(libs.plugins.kotlin.compose) apply false
    // 工具链 P0：Kotlin 风格检查（ktlint 官方推荐 Gradle 插件）
    alias(libs.plugins.ktlint) apply false
    // 工具链 P0：Kotlin 静态分析/代码异味（detekt 官方 Gradle 插件）
    alias(libs.plugins.detekt) apply false
}

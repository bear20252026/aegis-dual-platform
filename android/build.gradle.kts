plugins {
    id("com.android.application") version "9.3.1" apply false
    // AGP 9.0+ 内置 Kotlin 支持：org.jetbrains.kotlin.android 不再需要（官方迁移指引）
    id("org.jetbrains.kotlin.plugin.compose") version "2.4.10" apply false
}

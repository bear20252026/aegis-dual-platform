import java.util.Properties

plugins {
    id("com.android.application")
    // AGP 9.0+ 内置 Kotlin 支持：org.jetbrains.kotlin.android 不再需要（官方迁移指引）
    id("org.jetbrains.kotlin.plugin.compose")
    // 工具链 P0：Kotlin 风格检查（锁定 ktlint 1.8.0）
    id("org.jlleitschuh.gradle.ktlint")
    // 工具链 P0：Kotlin 静态分析/代码异味（detekt v1.23.8）
    id("io.gitlab.arturbosch.detekt")
}

// 工具链 P0：ktlint 配置（锁定 ktlint 版本，防止插件 patch 版本间默认值漂移）
ktlint {
    version = "1.8.0"
    // 仅检查本模块源码（Android 模块）
    android = true
}

// 工具链 P0：detekt 配置（基线文件对遗留项目友好——首跑生成基线，
// 仅新引入的问题触发失败，存量告警基线化）
detekt {
    buildUponDefaultConfig = true
    allRules = false
    config.setFrom(rootProject.files("detekt.yml"))
    baseline = file("detekt-baseline.xml")
    // 注：detekt 1.23.8 的 jvmTarget 配置在 Gradle 9.7 下类型兼容存疑
    // （JvmTarget/String 均脚本编译错误）——已移除——Kotlin 编译目标 21 由
    // compileOptions + compilerOptions 设置（detekt 跟随——远端 JDK 21 一致）
}

val signingProperties = Properties()
val signingPropertiesFile = rootProject.file("signing.properties")
if (signingPropertiesFile.exists()) {
    signingPropertiesFile.inputStream().use(signingProperties::load)
}
val requireNativePolicyCore =
    providers
        .gradleProperty("requireNativePolicyCore")
        .map { it == "true" }
        .getOrElse(false)

android {
    namespace = "com.aegis.browser"
    compileSdk = 36
    // detekt 兼容修复（ktlint/detekt 门禁）：显式 jvmTarget 21——本地/CI
    // JDK 25 运行时 detekt 的 --jvm-target 25 无效（detekt 仅支持 ≤22）——
    // 锁定 21 与远端 android-quality（JDK 21）一致
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_21
        targetCompatibility = JavaVersion.VERSION_21
    }
    // 注：AGP 9 内置 Kotlin——不再支持 kotlinOptions 块（脚本编译失败）；
    // Kotlin jvmTarget 跟随 compileOptions（Java 21）——detekt 兼容

    defaultConfig {
        applicationId = "com.aegis.browser"
        minSdk = 26
        targetSdk = 36
        versionCode = 20107
        versionName = "2.1.7"
        ndk {
            // 单架构分发（2026-08-30）：仅 arm64-v8a——排除 32 位老架构与
            // x86/x86_64 模拟器 ABI 入包（双保险：上游 dist 只产 arm64）
            abiFilters += listOf("arm64-v8a")
        }
    }

    signingConfigs {
        create("release") {
            // 签名凭据治理（工具链修复）：环境变量优先（凭据零落地，
            // 政府项目推荐），回退 signing.properties（本地开发）。
            val envStore = System.getenv("AEGIS_KEYSTORE_FILE")
            val envStorePass = System.getenv("AEGIS_KEYSTORE_PASSWORD")
            val envAlias = System.getenv("AEGIS_KEY_ALIAS")
            val envKeyPass = System.getenv("AEGIS_KEY_PASSWORD")
            if (envStore != null && envStorePass != null) {
                storeFile = file(envStore)
                storePassword = envStorePass
                keyAlias = envAlias ?: "aegis-release"
                keyPassword = envKeyPass ?: envStorePass
            } else if (signingPropertiesFile.exists()) {
                storeFile = file(signingProperties.getProperty("storeFile"))
                storePassword = signingProperties.getProperty("storePassword")
                keyAlias = signingProperties.getProperty("keyAlias")
                keyPassword = signingProperties.getProperty("keyPassword")
            }
            // 双签名方案（AGP 在 minSdk>=24 时默认关闭 v1——部分国产 ROM
            // 与文件管理器的解析器仍走 v1，v2-only 会报 packageInfo null）
            enableV1Signing = true
            enableV2Signing = true
        }
    }

    buildTypes {
        release {
            if (signingPropertiesFile.exists() ||
                System.getenv("AEGIS_KEYSTORE_FILE") != null
            ) {
                signingConfig = signingConfigs.getByName("release")
            }
            // R8 混淆暂停（2026-08-30）：JNA 按名映射 / androidx.webkit setTag(R$id)
            // 连环踩坑——keep 规则补一个漏一个，真机三连崩。止血：关闭混淆
            // 保可用性（体积 +~7MB），R8 规则全量真机回归后再启用。
            isMinifyEnabled = false
            proguardFiles(
                getDefaultProguardFile("proguard-android-optimize.txt"),
                "proguard-rules.pro",
            )
        }
    }

    packaging {
        resources.excludes += "/META-INF/{AL2.0,LGPL2.1}"
    }

    // AGP 9 默认关闭 BuildConfig 生成；BrowserEngine 依赖 BuildConfig.DEBUG
    sourceSets {
        // 首页资源单一事实源（ADR-007）：shared/shell（start.html + wallpapers）
        // 与 Windows 端（PyInstaller datas）共用同一目录——一处修改两端生效
        getByName("main").assets.srcDir(rootProject.file("../shared/shell"))
    }
    buildFeatures {
        buildConfig = true
    }
}

// AGP 9.0+ 内置 Kotlin：不再需要 kotlin { jvmToolchain() } 块
// （Kotlin 编译由 AGP 管理，使用运行 Gradle 的 JDK；已移除旧配置）

dependencies {
    val composeBom = platform("androidx.compose:compose-bom:2026.06.00")
    implementation(project(":broker"))
    implementation(project(":webview-adapter"))
    implementation(composeBom)
    androidTestImplementation(composeBom)
    implementation("androidx.activity:activity-compose:1.13.0")
    implementation("androidx.compose.ui:ui")
    implementation("androidx.compose.ui:ui-tooling-preview")
    implementation("androidx.compose.material3:material3")
    implementation("androidx.lifecycle:lifecycle-runtime-compose:2.10.0")
    implementation("androidx.webkit:webkit:1.15.0")
    debugImplementation("androidx.compose.ui:ui-tooling")
}

// detekt/Kotlin 编译目标显式 21（与 CI JDK 21 一致——detekt jvm-target 兼容——
// AGP 9 内置 Kotlin 不支持 android 块内 kotlinOptions（脚本编译失败）——
// 任务级配置用 compilerOptions DSL（kotlinOptions 已废弃——Gradle 9.7 编译报错）
tasks.withType<org.jetbrains.kotlin.gradle.tasks.KotlinCompile>().configureEach {
    compilerOptions {
        jvmTarget.set(org.jetbrains.kotlin.gradle.dsl.JvmTarget.JVM_21)
    }
}

// jvmToolchain 21（工具链强制——本地 JDK 25 也能跑 detekt（Gradle 自动用
// JDK 21 工具链——jvm-target 21——与 CI JDK 21 一致——质量门禁验证打通）
java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(21))
    }
}

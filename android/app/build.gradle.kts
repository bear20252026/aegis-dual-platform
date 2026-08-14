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
}

val signingProperties = Properties()
val signingPropertiesFile = rootProject.file("signing.properties")
if (signingPropertiesFile.exists()) {
    signingPropertiesFile.inputStream().use(signingProperties::load)
}

android {
    namespace = "com.aegis.browser"
    compileSdk = 36

    defaultConfig {
        applicationId = "com.aegis.browser"
        minSdk = 26
        targetSdk = 36
        versionCode = 20106
        versionName = "2.1.6"
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
        }
    }

    buildTypes {
        release {
            if (signingPropertiesFile.exists() ||
                System.getenv("AEGIS_KEYSTORE_FILE") != null
            ) {
                signingConfig = signingConfigs.getByName("release")
            }
            isMinifyEnabled = true
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
    buildFeatures {
        buildConfig = true
    }
}

// AGP 9.0+ 内置 Kotlin：不再需要 kotlin { jvmToolchain() } 块
// （Kotlin 编译由 AGP 管理，使用运行 Gradle 的 JDK；已移除旧配置）

dependencies {
    val composeBom = platform("androidx.compose:compose-bom:2026.06.00")
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

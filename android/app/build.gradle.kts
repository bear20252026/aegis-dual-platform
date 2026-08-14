import java.util.Properties

plugins {
    id("com.android.application")
    // AGP 9.0+ 内置 Kotlin 支持：org.jetbrains.kotlin.android 不再需要（官方迁移指引）
    id("org.jetbrains.kotlin.plugin.compose")
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
            if (signingPropertiesFile.exists()) {
                storeFile = file(signingProperties.getProperty("storeFile"))
                storePassword = signingProperties.getProperty("storePassword")
                keyAlias = signingProperties.getProperty("keyAlias")
                keyPassword = signingProperties.getProperty("keyPassword")
            }
        }
    }

    buildTypes {
        release {
            if (signingPropertiesFile.exists()) {
                signingConfig = signingConfigs.getByName("release")
            }
            isMinifyEnabled = true
            proguardFiles(
                getDefaultProguardFile("proguard-android-optimize.txt"),
                "proguard-rules.pro"
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

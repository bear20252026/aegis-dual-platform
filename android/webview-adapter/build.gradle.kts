plugins {
    id("com.android.library")
    id("org.jlleitschuh.gradle.ktlint")
    id("io.gitlab.arturbosch.detekt")
}

ktlint {
    version = libs.versions.ktlint.get()
    android = true
}

detekt {
    buildUponDefaultConfig = true
    allRules = false
    config.setFrom(rootProject.files("detekt.yml"))
    baseline = file("detekt-baseline.xml")
}

android {
    namespace = "com.aegis.webviewadapter"
    compileSdk = 36
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_21
        targetCompatibility = JavaVersion.VERSION_21
    }
    defaultConfig {
        minSdk = 26
    }
    testOptions {
        // AegisWebViewClientTest（AD-007..015）：JVM 单测依赖 android.util.Log
        // 默认值兜底（scheme 解析已纯字符串化——不依赖 android.net.Uri）
        unitTests.isReturnDefaultValues = true
    }
}

dependencies {
    implementation(project(":broker"))
    implementation(libs.androidx.webview)
    // AD-004 配套：LogRedact 行为级单测（JVM 可跑——纯字符串）
    testImplementation(libs.junit)
    // AD-007..015：WebView/AndroidBroker 经 mockito 5 inline mock（final 类可 mock）
    testImplementation(libs.mockito.core)
}

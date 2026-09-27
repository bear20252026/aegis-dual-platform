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
    // AD-186（审计 2026-09-23 清单·A7 批）：broker 的 test 接线显式化——
    // AegisWebViewClientTest 消费 broker 类型（Decision/AuthorizedAction），
    // 旧实现靠 implementation 的传递可见性（AGP 配置演化下不保证）；
    // 显式 testImplementation 固化「测试类路径含 :broker」的契约。
    testImplementation(project(":broker"))
    // AD-004 配套：LogRedact 行为级单测（JVM 可跑——纯字符串）
    testImplementation(libs.junit)
    // AD-007..015：WebView/AndroidBroker 经 mockito 5 inline mock（final 类可 mock）
    testImplementation(libs.mockito.core)
}

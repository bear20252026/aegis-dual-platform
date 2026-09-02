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
}

dependencies {
    implementation(project(":broker"))
    implementation(libs.androidx.webview)
}

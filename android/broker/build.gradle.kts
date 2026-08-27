// 由账号2生成
plugins {
    id("com.android.library")
}

val requireNativePolicyCore = providers.gradleProperty("requireNativePolicyCore")
    .map { it == "true" }
    .getOrElse(false)

android {
    namespace = "com.aegis.broker"
    compileSdk = 36
    buildFeatures {
        buildConfig = true
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_21
        targetCompatibility = JavaVersion.VERSION_21
    }
    defaultConfig {
        minSdk = 26
        buildConfigField("boolean", "REQUIRE_NATIVE_POLICY_CORE", requireNativePolicyCore.toString())
    }
}

dependencies {
    implementation("org.jetbrains.kotlinx:kotlinx-datetime:0.6.2")
    testImplementation("junit:junit:4.13.2")
}

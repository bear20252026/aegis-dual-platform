// 由账号2生成
plugins {
    id("com.android.library")
}

android {
    namespace = "com.aegis.broker"
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
    implementation("org.jetbrains.kotlinx:kotlinx-datetime:0.6.2")
    testImplementation("junit:junit:4.13.2")
}

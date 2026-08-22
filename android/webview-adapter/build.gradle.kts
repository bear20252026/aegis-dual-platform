// 由账号2生成
plugins {
    id("com.android.library")
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
    implementation("androidx.webkit:webkit:1.15.0")
}

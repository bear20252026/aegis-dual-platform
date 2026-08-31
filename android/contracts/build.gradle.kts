// A-2 接线（架构审计 2026-08-31）：:contracts 纳入构建——此前生成物
// 从未被编译（settings 未 include），schema 漂移无法被 CI 捕获。
// 本模块是纯数据模型（contracts/codegen/generate_kotlin.py 产物），
// 无 Android 依赖，保持与 broker 同款 AGP 库形态以统一工具链。
plugins {
    id("com.android.library")
}

android {
    namespace = "com.aegis.contracts"
    compileSdk = 36

    defaultConfig {
        minSdk = 26
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_21
        targetCompatibility = JavaVersion.VERSION_21
    }
}

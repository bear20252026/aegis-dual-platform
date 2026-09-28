// A-2 接线（架构审计 2026-08-31）：:contracts 纳入构建——此前生成物
// 从未被编译（settings 未 include），schema 漂移无法被 CI 捕获。
// 本模块是纯数据模型（contracts/codegen/generate_kotlin.py 产物），
// 无 Android 依赖，保持与 broker 同款 AGP 库形态以统一工具链。
plugins {
    id("com.android.library")
    id("org.jlleitschuh.gradle.ktlint")
    id("io.gitlab.arturbosch.detekt")
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

// 工具链 P0（A-2 门禁扩面 2026-08-31）：与 :app 同款质量门禁
ktlint {
    version = libs.versions.ktlint.get()
    android = true
}

detekt {
    buildUponDefaultConfig = true
    allRules = false
    config.setFrom(rootProject.files("detekt.yml"))
}

// PY-100（审计 2026-09-25）：本模块 src 全部为 generate_kotlin.py 机器产物
// ——detekt 基线按「参数签名」记录，生成物任何字段变化（如 optional 加
// 默认值）都会导致基线失配复现旧违规。生成代码从 detekt 中整体排除
// （契约一致性由 verify_contract_compatibility.py 重生成 diff 门禁保证）。
tasks.withType<io.gitlab.arturbosch.detekt.Detekt>().configureEach {
    include("**/*.kt")
    exclude("**/generated/**")
}

// 由账号2生成
plugins {
    id("com.android.library")
}

val requireNativePolicyCore = providers.gradleProperty("requireNativePolicyCore")
    .map { it == "true" }
    .getOrElse(false)
val nativePolicyCoreDir = providers.gradleProperty("nativePolicyCoreDir")
    .orNull
    ?.let(::file)
val nativePolicyCoreFiles = listOf(
    "arm64-v8a/libaegis_policy_core.so",
    "armeabi-v7a/libaegis_policy_core.so",
    "x86_64/libaegis_policy_core.so",
    "x86/libaegis_policy_core.so",
    "kotlin/uniffi/aegis_policy_core/aegis_policy_core.kt",
)

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
    sourceSets {
        getByName("main").apply {
            nativePolicyCoreDir?.let {
                jniLibs.srcDir(it)
                java.srcDir(it.resolve("kotlin"))
            }
        }
    }
}

if (requireNativePolicyCore) {
    tasks.named("preBuild").configure {
        doFirst {
            check(nativePolicyCoreDir != null) {
                "requireNativePolicyCore=true 时必须设置 -PnativePolicyCoreDir=<ABI 制品目录>"
            }
            nativePolicyCoreFiles.forEach { relativePath ->
                check(nativePolicyCoreDir.resolve(relativePath).isFile) {
                    "缺少受控原生策略制品: ${nativePolicyCoreDir.resolve(relativePath)}"
                }
            }
        }
    }
}

dependencies {
    // ApprovalRequest/AuthorizedAction 的公开 expiresAt 字段使用 Instant；
    // 该类型出现在模块 API 中，消费者必须能在编译期解析它。
    api("org.jetbrains.kotlinx:kotlinx-datetime:0.6.2")
    implementation("net.java.dev.jna:jna:5.12.0@aar")
    testImplementation("junit:junit:4.13.2")
    testImplementation("org.json:json:20230227")
}

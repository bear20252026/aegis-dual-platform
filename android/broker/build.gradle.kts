// 由账号2生成
plugins {
    id("com.android.library")
}

val requireNativePolicyCore =
    providers
        .gradleProperty("requireNativePolicyCore")
        .map { it == "true" }
        .getOrElse(false)
val nativePolicyCoreDir =
    providers
        .gradleProperty("nativePolicyCoreDir")
        .orNull
        ?.let(::file)
val nativePolicyCoreFiles =
    listOf(
        "arm64-v8a/libaegis_policy_core.so",  // 单架构：arm64-v8a
        "kotlin/uniffi/aegis_policy_core/aegis_policy_core.kt",
    )

android {
    namespace = "com.aegis.broker"
    compileSdk = 36
    buildFeatures {
        buildConfig = true
    }
    testOptions {
        // NativePolicyCoreBridge 失败路径用 android.util.Log 留痕——
        // JVM 单测无 Android 框架，默认值兜底（否则 Log.e 未 mock 即崩）
        unitTests.isReturnDefaultValues = true
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_21
        targetCompatibility = JavaVersion.VERSION_21
    }
    defaultConfig {
        minSdk = 26
        buildConfigField("boolean", "REQUIRE_NATIVE_POLICY_CORE", requireNativePolicyCore.toString())
        // M-3 策略域配置单源：导航确认开关并入 broker（app 只读 broker BuildConfig）
        val requireNavigationConfirmation = providers
            .gradleProperty("requireNavigationConfirmation")
            .map { it == "true" }
            .getOrElse(false)
        buildConfigField("boolean", "REQUIRE_NAVIGATION_CONFIRMATION", requireNavigationConfirmation.toString())
        check(!requireNavigationConfirmation || requireNativePolicyCore) {
            "requireNavigationConfirmation=true 时必须同时设置 -PrequireNativePolicyCore=true"
        }
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

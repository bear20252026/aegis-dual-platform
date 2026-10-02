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
        "arm64-v8a/libaegis_policy_core.so", // 单架构：arm64-v8a
        "kotlin/uniffi/aegis_policy_core/aegis_policy_core.kt",
    )

android {
    namespace = "com.aegis.broker"
    compileSdk = 37
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
        val requireNavigationConfirmation =
            providers
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
    // AD-293（2026-10-01 发布链批）：configuration cache 下 doFirst 闭包不得
    // 捕获 Gradle 脚本对象引用（script receiver）——此前的脚本级属性直引使
    // `-PrequireNativePolicyCore=true`（发布链路径）构建即报
    // "cannot serialize Gradle script object references"。先把脚本态值拷入
    // 局部 val（File/String 均可序列化），闭包只引用局部量。
    val configuredNativePolicyCoreDir = nativePolicyCoreDir
    val requiredNativePolicyCoreFiles = nativePolicyCoreFiles
    tasks.named("preBuild").configure {
        doFirst {
            check(configuredNativePolicyCoreDir != null) {
                "requireNativePolicyCore=true 时必须设置 -PnativePolicyCoreDir=<ABI 制品目录>"
            }
            requiredNativePolicyCoreFiles.forEach { relativePath ->
                check(configuredNativePolicyCoreDir.resolve(relativePath).isFile) {
                    "缺少受控原生策略制品: ${configuredNativePolicyCoreDir.resolve(relativePath)}"
                }
            }
        }
    }
}

dependencies {
    // ApprovalRequest/AuthorizedAction 的公开 expiresAt 字段使用 Instant；
    // 该类型出现在模块 API 中，消费者必须能在编译期解析它。
    api(libs.kotlinx.datetime)
    // AD-099（审计 2026-09-23 清单·A6 批）：JNA 5.12.0 → 5.19.1（2026-09 时点
    // 最新稳定版；5.13..5.19 含 Android 目标修复与内部包重构）。JNA 按「方法名」
    // 映射 native 符号——升级后 broker JVM 单测全绿为回归门禁；proguard 侧
    // com.sun.jna.internal.** keep 规则已在位（5.13+ 内部包路径）。
    // AD-318（2026-10-02 审计）：依赖坐标/版本入 catalog（libs.jna）——
    // @aar 分类器无法走 catalog 的旧说法失实（artifact { type } 块即可
    // 表达），唯一字面量依赖随之消除。
    implementation(libs.jna) {
        artifact {
            type = "aar"
        }
    }
    // A-2 接线：契约对齐守卫测试需要对照生成物 ActionContract 的字段面
    // AD-186（审计 2026-09-23 清单·A7 批）：test 接线评估收口——
    // ① :contracts 测试接线已在位（本行，ContractAlignmentTest 消费）；
    // ② :webview-adapter 的 broker→adapter 测试接线不可行：webview-adapter
    //    主源集依赖 :broker，broker 测试源集再依赖回 :webview-adapter 即
    //    构成项目依赖环（Gradle 直接拒绝解析）——保留现状（adapter 侧行为
    //    的回归由 webview-adapter 自身测试面对 broker 类型 mock 覆盖）。
    testImplementation(project(":contracts"))
    testImplementation(libs.junit)
    testImplementation(libs.org.json)
}

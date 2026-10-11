// ============================================================================
// 构建类路径安全地板（2026-10-03 依赖告警处置批）
// ============================================================================
// 背景：Gradle-Dependency-Graph 接线后（SP-246 收尾），Dependabot alerts 首次
// 对 Android 构建面生效——11 项告警（1 critical/3 high/4 medium/3 low）全部
// 指向 AGP 9.4.1 构建类路径的传递依赖（gradle-dependency-insight 工具实证父链）：
//   bcprov/bcpkix 1.80.2、jose4j 0.9.5（bundletool 1.18.3）、
//   jdom2 2.0.6（jetifier-processor）、commons-lang3 3.16.0（sdklib→commons-io）、
//   httpclient 4.5.6（sdklib→httpmime，树内已冲突解析至 4.5.14）。
// 暴露面证明（同工具，runtime.txt 零命中）：debugRuntimeClasspath 闭包不含
// 上述任何包——**产品 APK 不受影响**，本地板只收紧构建机（dev/CI）侧暴露。
// 机制：buildscript 类路径与 plugins DSL 类路径合并后冲突解析取最高版本——
// 显式 classpath 地板把五包抬到修复版（BC 1.80→1.85 / jose4j 0.9.5→0.9.6 /
// jdom2 2.0.6→2.0.6.1 / lang3 3.16→3.18.0 / httpclient 钉 4.5.14）。
// 范围取舍：logback 3×low 不在本树（依赖图另一节点，疑为插件自有类路径），
// 留给 AGP/工具链升级承接——不对不在解析树内的包盲加地板。
// 第九轮复验（2026-10-10，R9-DEPS-1）：上方 1.85 / 0.9.6 / 3.18.0 是 **2026-10-03 首次
// 设地板时**的取值（历史记录，不作现行陈述）；实钉已随上游推进到 BC 1.86（bcprov/bcutil/
// bcpkix 三件）、jose4j 0.9.7、jdom2 2.0.6.1、lang3 3.21.0、httpclient 4.5.14。
// 当日仍开的 9 条 Maven 告警**全部没有 patched 版本可升**——逐包以
// repo1.maven.org/…/maven-metadata.xml 实测：七包当前钉版即最新已发布版
// （bcprov/bcutil/bcpkix 1.86、jose4j 0.9.7、jdom2 2.0.6.1、lang3 3.21.0、httpclient 4.5.14），
// Dependabot 也未为它们开 PR，与此一致。故本轮处置是「结案 + 等上游发版后复检」，
// 不是「已修复」：critical（BC name-constraints 绕过）与 high（BC ASN.1 强制解析）
// 在构建机上仍开放，产品 APK 不受影响（runtime 闭包零命中，实证见分诊文档）。
// logback 3×low 维持原判：不在本树解析闭包内。
// 分诊全文（暴露面证据/剩余告警处置/复检规程）：docs/security/android-build-classpath-triage.md
// 版本来源：各告警的 first_patched_version（11/12→1.85、7→1.84、5→0.9.6、
// 4→2.0.6.1、3→3.18.0、2→4.5.13 已被树解析超集 4.5.14 覆盖——显式钉版防回退）。
buildscript {
    repositories {
        google()
        mavenCentral()
    }
    dependencies {
        classpath("org.bouncycastle:bcprov-jdk18on:1.86")
        classpath("org.bouncycastle:bcutil-jdk18on:1.86")
        classpath("org.bouncycastle:bcpkix-jdk18on:1.86")
        classpath("org.bitbucket.b_c:jose4j:0.9.7")
        classpath("org.jdom:jdom2:2.0.6.1")
        classpath("org.apache.commons:commons-lang3:3.21.0")
        classpath("org.apache.httpcomponents:httpclient:4.5.14")
    }
}

plugins {
    // AD-292（2026-10-01 审计，--warning-mode all 实测）：Gradle 9.8 下仅存的
    // 两条 Deprecated 告警均来自第三方 Gradle 插件内部，非本仓脚本：
    // ① ktlint 插件 14.2.0 —— ReportingExtension.file(String)（Gradle 10 移除）；
    // ② detekt 插件 1.23.8 —— Configuration.setVisible(boolean)（Gradle 11 移除）。
    // 升级插件版本前无法在本仓侧清除——登记待插件上游修复。
    // AD-242（2026-09-26 审计）：插件版本经 gradle/libs.versions.toml 单源
    // （此前本块字面量散落——与 app 依赖 catalog 化口径对齐）
    alias(libs.plugins.android.application) apply false
    // AGP 9.0+ 内置 Kotlin 支持：org.jetbrains.kotlin.android 不再需要（官方迁移指引）
    alias(libs.plugins.kotlin.compose) apply false
    // 工具链 P0：Kotlin 风格检查（ktlint 官方推荐 Gradle 插件）
    alias(libs.plugins.ktlint) apply false
    // 工具链 P0：Kotlin 静态分析/代码异味（detekt 官方 Gradle 插件）
    alias(libs.plugins.detekt) apply false
}

// ── 依赖锁定（第九轮项 10 / AEG-011，2026-10-11 启用）：单源在 root，不在四个模块脚本 ──
// 为什么放这里而不是每个模块各写一份：①「新增第五个模块忘记加锁」没有任何机器会提醒
// （fail-open），而 `subprojects` 作用域自动覆盖后来者（fail-closed）；②`:app` 的构建脚本
// 停在 316 行的零余量基线上（行数红线：基线文件只许减不许增），第 5 行代码塞不进去——
// 是它逼出了这个更好的形状。
// 时序有实义：root 脚本先于子模块脚本求值，所以 `lockAllConfigurations()` 注册在 AGP 创建
// 变体配置、ktlint/detekt 创建工具配置**之前**，这些后续配置一律进锁（实测锁里确有
// debugAndroidTestCompileClasspath / ktlintRuleset / detektPlugins 这些传递与工具面条目）。
// STRICT 虽是 Gradle 缺省值也显式写出——靠缺省就是「缺省一变即静默放松」。
// 覆盖面（脚本类路径不在内）、锁不含校验和、重锁 SOP：单源决策记录在 settings.gradle.kts。
subprojects {
    dependencyLocking {
        lockAllConfigurations()
        lockMode = LockMode.STRICT
    }
}

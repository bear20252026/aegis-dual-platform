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
// 分诊全文（暴露面证据/剩余告警处置/复检规程）：docs/security/android-build-classpath-triage.md
// 版本来源：各告警的 first_patched_version（11/12→1.85、7→1.84、5→0.9.6、
// 4→2.0.6.1、3→3.18.0、2→4.5.13 已被树解析超集 4.5.14 覆盖——显式钉版防回退）。
buildscript {
    repositories {
        google()
        mavenCentral()
    }
    dependencies {
        classpath("org.bouncycastle:bcprov-jdk18on:1.85")
        classpath("org.bouncycastle:bcutil-jdk18on:1.85")
        classpath("org.bouncycastle:bcpkix-jdk18on:1.84")
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

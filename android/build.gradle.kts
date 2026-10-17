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
// 范围取舍（R9-B49 现读更正）：logback 3×low 曾被判「不在本树」——四把入库锁里
// logback-core/-classic:1.3.16=ktlint 各一条（ktlint-cli 1.8.0 的传递依赖，见
// android/app/gradle.lockfile:106-107 等四处），所以「不在解析树内」不成立。
// 仍不加地板：抬 linter 自身类路径的日志实现会改 ktlint 运行时，而这三个节点只在
// 构建期存在。边界改由常驻门禁判定，不靠注释声明（见下面那条 verify_ 脚本）。
// 第九轮复验（2026-10-10，R9-DEPS-1）：上方 1.85 / 0.9.6 / 3.18.0 是 **2026-10-03 首次
// 设地板时**的取值（历史记录，不作现行陈述）；实钉已随上游推进到 BC 1.86（bcprov/bcutil/
// bcpkix 三件）、jose4j 0.9.7、jdom2 2.0.6.1、lang3 3.21.0、httpclient 4.5.14。
// 当日仍开的 9 条 Maven 告警**全部没有 patched 版本可升**——逐包以
// repo1.maven.org/…/maven-metadata.xml 实测：七包当前钉版即最新已发布版
// （bcprov/bcutil/bcpkix 1.86、jose4j 0.9.7、jdom2 2.0.6.1、lang3 3.21.0、httpclient 4.5.14），
// Dependabot 也未为它们开 PR，与此一致。故本轮处置是「结案 + 等上游发版后复检」，
// 不是「已修复」：critical（BC name-constraints 绕过）与 high（BC ASN.1 强制解析）
// 在构建机上仍开放，产品 APK 不受影响（runtime 闭包零命中，实证见分诊文档）。
// logback 3×low 的原判已被推翻（见上一段）：它在 ktlint 配置里，只是不在出货面。
// 本地板达不到的两条工具面（androidLintTool / ktlint）才是这 9 条告警的落点，
// 其边界由 scripts/verify_gradle_alert_scope_boundary.py 常跑判定：这 5 个坐标一旦
// 进 release/debug Runtime|Compile Classpath 或 debugAndroidTest*（装进设备的那份）即判红。
// R9-B89 就地更正（2026-10-17）：上面那段「9 条告警全部没有 patched 版本可升 ⇒ 只能结案等上游」
// 只对了一半，而且对的那半不在告警的落点上。区分两件事：①**buildscript/插件类路径**确实已钉在
// 各包最新已发布版（1.86/0.9.7/2.0.6.1/3.21.0/4.5.14），那一面「无升级可做」是真的；
// ②但告警实际命中的是 **androidLintTool / ktlint 两条工具配置**，那里被 dependency locking
// 钉在 1.80.2（< patched 1.85），而 locking 会压过 buildscript 地板——所以「等上游」是错的诊断，
// 可做的是给自己那条配置加常驻 force（见下面 subprojects 里的 R9-B89 块）+ 重锁。
// 仍成立的部分：产品 APK 不受影响（runtime 闭包零命中）；logback×3 在 ktlint 配置，本批不动。
// 未证的一项：GitHub 侧扫描是否因此闭合——只能等下一次扫描复核，不写成结论。
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

    // R9-B89（2026-10-17，§四 第 12 项定稿「fix-forward」）：lint 工具面的 BC 三件抬到 1.86。
    // 为什么 buildscript 上面那条 classpath 地板（1.86）不够：`androidLintTool` 走的是子项目
    // 配置解析，实测 `dependencyInsight` 的选择原因是
    // 「By constraint: Dependency version enforced by Dependency Locking」——锁把它钉在 1.80.2，
    // 于是同一棵树里 buildscript 已 1.86、lint 工具面仍 1.80.2（告警范围 < 1.85 因此一直不闭）。
    // 为什么地板必须常驻而不是改一次锁：探针实测「删掉 force 再跑例行 `--write-locks`」，
    // 锁**退回 1.80.2**（1m3s）——只改锁不钉 force，下一次重锁就静默回退。
    // 范围：只 `matching { it.name == "androidLintTool" }`，不碰出货面
    // （`verify_gradle_alert_scope_boundary.py` 判的就是这条边界，坐标进 Runtime/Compile
    // 或 debugAndroidTest* 即红）。commons-lang3／httpclient 同配置同理由一起收；
    // logback 3×low 在 `ktlint` 配置——抬它会改 linter 自身日志实现，本批不动（见上面第 15-19 行）。
    configurations.matching { it.name == "androidLintTool" }.all {
        resolutionStrategy.force(
            "org.bouncycastle:bcprov-jdk18on:1.86",
            "org.bouncycastle:bcutil-jdk18on:1.86",
            "org.bouncycastle:bcpkix-jdk18on:1.86",
            "org.apache.commons:commons-lang3:3.21.0",
            "org.apache.httpcomponents:httpclient:4.5.14",
        )
    }

    // R9-B32（2026-10-12，master 实测红灯）：锁的**覆盖面**不能靠「手抄一份任务清单」。
    // 第九轮批次的重锁面是照 CI 的 gradlew 任务列表抄的，而 `:app:androidTestUtil` 这类
    // 配置**不属于任何任务的名称面**——它由 AGP 的 UTP 构建监听器在依赖图生成时解析。
    // 后果实测：`gradle-dependency-graph.yml` 连续两次在 master 上红
    // （`Locking strict mode: Configuration ':app:androidTestUtil' is locked but does not
    // have lock state`），而所有 PR 门禁当时全绿——「清单抄对了」完全不等于「锁覆盖全了」。
    // 这个任务把判据改成枚举模型里的真实集合：每个 `canBeResolved` 的配置都必须在锁里有
    // 状态（坐标条目或 `empty=` 里出现过），缺一个就 fail-closed 列出全部缺口。
    // 用**图解析**而非文件解析：锁记的是版本，`.files` 会连带要求本模块产物已构建，
    // 那是构建执行面的事，不是锁完整性的事（实测库模块的 androidTest 文件解析会因此假失败）。
    tasks.register("verifyDependencyLockCoverage") {
        notCompatibleWithConfigurationCache("执行期枚举 configurations——新变体配置必须也能被看到")
        doLast {
            val lock = project.file("gradle.lockfile")
            if (!lock.isFile) {
                throw GradleException(
                    "${project.path} 没有 gradle.lockfile——启用了依赖锁定却没有锁文件，" +
                        "STRICT 下任何解析都会当场红"
                )
            }
            val covered = mutableSetOf<String>()
            lock.readLines().forEach { line ->
                if (line.isBlank() || line.startsWith("#")) return@forEach
                val idx = line.indexOf('=')
                if (idx >= 0) {
                    line.substring(idx + 1).split(',').forEach { name ->
                        if (name.isNotBlank()) covered += name.trim()
                    }
                }
            }
            val resolvable = project.configurations
                .filter { it.isCanBeResolved }
                .mapTo(mutableSetOf()) { it.name }
            val missing = resolvable - covered
            if (missing.isNotEmpty()) {
                throw GradleException(
                    "${project.path} 有 ${missing.size} 个可解析配置在锁里没有状态：" +
                        missing.sorted().joinToString(", ") +
                        "——重锁面漏了它们（照任务清单抄必然漏掉监听器解析的配置）；" +
                        "跑 dependency-relock.yml 的 gradle 面补齐：先 resolveAllConfigurations 全量解析写锁，再跑回本检查自证"
                )
            }
            println("锁覆盖检查通过：${project.path} 的 ${resolvable.size} 个可解析配置全部有锁状态")
        }
    }

    // 重锁用：把每个可解析配置的**依赖图**解析一遍，让 `--write-locks` 写全状态。
    // 刻意不因单个配置解析失败而中断（监听器类配置在无设备环境下可能解析不动），
    // 但最终由 verifyDependencyLockCoverage 判成败——解析是手段，覆盖是判据。
    tasks.register("resolveAllConfigurations") {
        notCompatibleWithConfigurationCache("执行期枚举并解析 configurations")
        doLast {
            project.configurations.filter { it.isCanBeResolved }.forEach { cfg ->
                val outcome = try {
                    cfg.incoming.resolutionResult.root
                    "OK"
                } catch (e: Exception) {
                    "FAIL ${e.message?.lineSequence()?.firstOrNull()}"
                }
                println("解析 ${project.path}:${cfg.name} -> $outcome")
            }
        }
    }

    // 校验和用（R9-B50）：把每个可解析配置的**产物文件**解析一遍。与上面那条的差别就是本行的
    // 存在理由：`resolutionResult.root` 只走依赖图，Gradle 为此只取 `.pom`/`.module`；
    // 而 `--write-verification-metadata` 登记的是本次**真正落盘的字节**，图解析一个
    // `.jar`/`.aar` 都不下。用集合口径而不是抄任务清单，理由与 `resolveAllConfigurations`
    // 同一条（R9-B32）：任何任务解析到的配置都在这个集合里。
    // 逐配置 try/catch 是有意的：库模块的 androidTest 类配置在产物未构建时解析不动
    // （② 里那条实测），这里要的是「尽可能多地下」，覆盖判据仍归 verifyDependencyLockCoverage。
    // 不能只靠本行的一面：ktlint/detekt/lint/测试这些**工具 detached 配置**是任务执行时才创建的，
    // 不在 `project.configurations` 里，所以重锁面仍要跑那几个任务（见 dependency-relock.yml）。
    tasks.register("resolveAllConfigurationFiles") {
        notCompatibleWithConfigurationCache("执行期枚举并解析 configurations 的产物文件")
        doLast {
            project.configurations.filter { it.isCanBeResolved }.forEach { cfg ->
                val outcome = try {
                    // FileCollection 没有 size()，`.files` 才是 Set<File>——写错一层的表现是
                    // 脚本编译不过，而不是解析出零个文件（--refresh-dependencies 逼它真编译了一次才发现）。
                    val resolved = cfg.incoming.files.files
                    "OK (${resolved.size} 个文件)"
                } catch (e: Exception) {
                    "FAIL ${e.message?.lineSequence()?.firstOrNull()}"
                }
                println("解析文件 ${project.path}:${cfg.name} -> $outcome")
            }
        }
    }
}

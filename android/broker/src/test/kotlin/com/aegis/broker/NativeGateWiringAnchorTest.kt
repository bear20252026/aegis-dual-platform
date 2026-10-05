package com.aegis.broker

import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File

/**
 * R8-AD-09（第八轮审计 2026-10-04）：原生门禁在**发布链里真的被启用**这件事的静态锚。
 *
 * 复核结论（对本条的定性做降级）：子代理把
 * `AndroidBrokerTest.defaultNativePolicyCoreGateClosesWhenBuildRequiresNativeCore`
 * 判为「两分支都记通过 ⇒ 不可能失败」。回读后不成立——那是**变体自适应**断言：默认变体
 * 断「放行托管 Broker」，置位变体断「block + 拒绝码」，两侧各有真断言，任一侧被破坏都会红。
 *
 * 真正剩下的两个缺口是本文件负责的：
 * 1. 「置位变体确实被跑过」此前只由两个 workflow 里的 `--tests` 字符串撑着——删掉那两行
 *    参数，整套原生门禁语义在发布链里静默消失，而所有 JVM 用例仍全绿（R6-26/R7-CS2-04
 *    「机制建了没接线」同族）。现按 B4 的 InstalledBuildMarkerTests 同法，把 workflow
 *    文本钉成断言。
 * 2. 置位变体在 JVM 宿主（x86_64 Linux）上加载的是 arm64 `.so`，它验的其实是
 *    「核心不可得即关闭」而非「核心缺失/ABI 失配」——这层局限如实记录，不假装已覆盖。
 *    （minified release 的运行时冒烟门禁缺口另记 R8-AD-06，属发布链基建。）
 */
class NativeGateWiringAnchorTest {
    
    private fun repoRoot(): File {
        var dir: File? = File(System.getProperty("user.dir")).absoluteFile
        repeat(8) {
            val candidate = File(dir, ".github/workflows/release-android.yml")
            if (candidate.isFile) {
                return dir!!
            }
            dir = dir?.parentFile
        }
        error("未找到 .github/workflows/release-android.yml（请在仓库内运行测试）")
    }

    /** 取 assembleRelease 那条命令所在的步骤块（到下一个 `- name:` 为止）。 */
    private fun assembleReleaseBlock(path: File): String {
        val text = path.readText()
        val marker = ":app:assembleRelease"
        val start = text.indexOf(marker)
        assertTrue("${path.name} 里没有 :app:assembleRelease 步骤", start >= 0)
        val tail = text.substring(start).lines()
        val stepStart = tail.drop(1).indexOfFirst { it.startsWith("      - name:") }
        return if (stepStart < 0) {
            tail.joinToString(" ")
        } else {
            tail.take(stepStart + 1).joinToString(" ")
        }
    }

    @Test
    fun releaseBuildActuallyEnablesNativeGateAndConfirmationPanel() {
        // 发布 APK 若漏传这两个标志，出货面就退回「无原生核心 / 无确认面板」，
        // 而所有 JVM 用例照常全绿——这正是本轮要钉住的失效形态。
        val workflow = File(repoRoot(), ".github/workflows/release-android.yml")
        val block = assembleReleaseBlock(workflow)
        assertTrue(
            "assembleRelease 未传 -PrequireNativePolicyCore=true",
            block.contains("-PrequireNativePolicyCore=true"),
        )
        assertTrue(
            "assembleRelease 未传 -PrequireNavigationConfirmation=true（确认流在发布物里静默关闭）",
            block.contains("-PrequireNavigationConfirmation=true"),
        )
    }

    @Test
    fun gateVariantTestIsStillDrivenByBothWorkflowsFilters() {
        // 两处 `--tests` 过滤器与本方法名必须逐字对齐：改方法名而不改过滤器，
        // Gradle 报「No tests found for given includes」并把发布链打成红——
        // 第八轮 B3 首次推送即由这条实跑暴露，故钉成常驻断言。
        val name = "com.aegis.broker.AndroidBrokerTest.defaultNativePolicyCoreGateClosesWhenBuildRequiresNativeCore"
        val release = File(repoRoot(), ".github/workflows/release-android.yml").readText()
        val native = File(repoRoot(), ".github/workflows/native-policy-artifacts.yml").readText()
        assertTrue("release-android.yml 的 --tests 过滤器丢失或改名不同步", release.contains("--tests $name"))
        assertTrue("native-policy-artifacts.yml 的 --tests 过滤器丢失或改名不同步", native.contains("--tests $name"))
    }

    @Test
    fun buildConfigFlagNameStaysSingleSourced() {
        // 门禁读取的 BuildConfig 字段名与 gradle 侧的注入必须同名——此前 EXPECTED_C_ABI_VERSION
        // 曾在 Gate 与 Bridge 双份定义（AD-068 收敛理由同源）。此处断言三处字面一致。
        val root = repoRoot()
        val gate = File(root, "android/broker/src/main/kotlin/com/aegis/broker/NativePolicyCoreGate.kt")
        val gradle = File(root, "android/broker/build.gradle.kts")
        val gateText = gate.readText()
        val gradleText = gradle.readText()
        assertTrue(gateText.contains("BuildConfig.REQUIRE_NATIVE_POLICY_CORE"))
        assertTrue(gradleText.contains("buildConfigField(\"boolean\", \"REQUIRE_NATIVE_POLICY_CORE\""))
    }
}

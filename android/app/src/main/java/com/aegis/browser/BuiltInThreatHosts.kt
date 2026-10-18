package com.aegis.browser

import android.content.Context
import com.aegis.broker.AndroidBroker
import com.aegis.broker.CoreDenylistOutcome
import com.aegis.broker.CoreDenylistUpdateResult
import com.aegis.broker.ThreatHostFeed
import java.io.InputStream

/**
 * 出厂内置威胁 host 名单的装载与发布（R9-B95 / 队列 Q51 的机制半边）。
 *
 * 这一层为什么单独存在（而不是在 broker 里直接读文件）：asset 读取要 `Context`，而
 * `:broker` 刻意保持「无 Android 类型 ⇒ 纯 JVM 可测」的契约（`LocalTargetHosts.kt` 头部
 * 就写着这条）。所以解析与协议留在 `:broker`（`ThreatHostFeed` / `CoreDenylistPush`），
 * 这里只做三件事：读出 asset 文本、交给 broker 灌核心、把结论写进 logcat。
 *
 * **默认行为逐字不变**：内置名单当前为空（`android/app/src/main/assets/threat/hosts.txt`
 * 的头注写着为什么），核心侧「空集合 = 不拦」⇒ 装载结果应是 `Published(0/0)`。这条链的价值
 * 不在今天拦了什么，而在「灌入口真实存在且会留痕」——所有者给出名单内容之后不需要再改机制。
 *
 * 留痕口径：只写数量与短码，不写 host 明文（本仓对日志里的 host/URL 一律要过
 * `LogSanitize`/`LogRedact`，这里干脆不输出，比再套一层脱敏更可靠）。
 */
object BuiltInThreatHosts {
    /** 内置件是仓库里的一个文本文件，超限即视为异常并按「未发布」留痕——
     * 不静默截断：截断一份名单等于悄悄放行被截掉的那部分。按**字符**计（asset 是文本），
     * 与核心按字节计的载荷上限是两个不同判据，别混用。 */
    private const val MAX_FEED_CHARS = 512 * 1024

    /** 在后台线程调用（`AegisApplication` 的 broker 预热线程）。返回结论供测试断言；
     * 生产调用点忽略返回值——本函数自己负责留痕，不抛异常上导航路径，也**永不返回 null**：
     * 「桥不在」「asset 读不出」都是结论里的一个短码，不是让调用方去猜的缺席。 */
    fun publish(
        context: Context,
        broker: AndroidBroker,
    ): CoreDenylistUpdateResult {
        val text = readBuiltInFeed(context)
        if (text == null) {
            // 「没读到」与「读到但没灌进去」是两个数：input 也记 0，不冒充有一名单被拒
            return trace(CoreDenylistUpdateResult.notPublished(0, "built_in_feed_unavailable"))
        }
        val parsed = ThreatHostFeed.parse(text)
        if (parsed.rejected.isNotEmpty()) {
            // 「有 N 行看着像条目却形态非法」必须可见：静默丢掉就是本仓反复记的
            // 「读起来像工作，实际什么都没拦」
            android.util.Log.w(TAG, "内置名单有 ${parsed.rejected.size} 条非法形态条目被拒收")
        }
        return trace(broker.updateThreatHostDenylist(parsed.hosts), "parsed=${parsed.hosts.size}")
    }

    /** 读 asset 文本；缺失或超限一律返回 null（调用方按未发布留痕，不猜空名单）。 */
    private fun readBuiltInFeed(context: Context): String? =
        try {
            context.assets.open(ThreatHostFeed.BUILT_IN_ASSET_PATH).use { stream -> readCapped(stream) }
        } catch (expected: Exception) {
            // 变量名承担 detekt 的豁免（与 AegisApplication 预热线程同口径）：asset 面的失败
            // 形态是开集（IOException / 超限的 IllegalStateException / ROM 自定义 RuntimeException），
            // 而**任何一种的处置都相同**——按未发布留痕，不让它上导航路径。
            android.util.Log.e(TAG, "内置名单读取失败: ${expected.javaClass.simpleName}")
            null
        }

    private fun readCapped(stream: InputStream): String {
        val builder = StringBuilder()
        stream.bufferedReader().use { reader ->
            reader.lineSequence().forEach { line ->
                builder.append(line).append('\n')
                check(builder.length <= MAX_FEED_CHARS) { "built-in feed exceeds $MAX_FEED_CHARS chars" }
            }
        }
        return builder.toString()
    }

    /** 结论落 logcat：Published 走 i，其余两态走 w（名单不完整与链断了都要人看）。 */
    private fun trace(
        result: CoreDenylistUpdateResult,
        extra: String = "",
    ): CoreDenylistUpdateResult {
        val line = "核心黑名单 ${result.outcome} accepted=${result.accepted}/input=${result.input} $extra"
        val tail = "batches=${result.batches} detail=${result.detail}"
        if (result.outcome == CoreDenylistOutcome.Published) {
            android.util.Log.i(TAG, "$line $tail")
        } else {
            android.util.Log.w(TAG, "$line $tail")
        }
        return result
    }

    private const val TAG = "AegisThreatFeed"
}

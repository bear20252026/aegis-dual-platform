package com.aegis.broker

import org.json.JSONObject

/**
 * 原生黑名单注入的**分批协议**（R9-B95；与 Windows
 * `windows/src/Aegis.Windows.App/Broker/NativePolicyCoreBridge.DenylistPush.cs`
 * 同一套协议，第八轮 ⑨ 的 Android 半边）。
 *
 * 为什么必须存在：核心对单批调用的第三参从布尔扩成档位——0 追加 / 1 整批替换 /
 * 2 开一次暂存会话 / 3 提交会话。**提交之前判定读的始终是上一份完整快照**。既往形状
 * （首批 `clear=1` 立即清空 + 只装入第一批）意味着一份 5 MiB 名单的约 85 批推送窗口内，
 * 未推到的恶意 host 一律 Allow；任一批失败则核心永久保留前缀，而端侧没有任何办法分辨
 * 「完整快照」与「残缺前缀」。半途失败现在只是「没提交」，活动快照纹丝不动。
 *
 * 混版三态缺一不可有明确行为（与 Windows 逐条对应）：
 * · 新宿主 + 新核心：应答回显 `mode` ⇒ 走暂存 + 提交。
 * · 新宿主 + 旧核心（只回显 `clear`）：退回既往的分批替换链，并保留
 *   `core_lacks_clear_parameter` 那条判据——**不假装拿到了原子性**。
 * · 旧宿主 + 新核心：只发 0/1，走的仍是既往路径，逐字不变。
 *
 * 与 Windows 的**三处有意不一致**（不是漏抄，逐条有理由）：
 * ① 结论成员名：Windows `PartiallyPublished` / 这里 `PartialAccept`，语义同（已生效但不完整）。
 * ② Windows 有 `ExportMissing`——它按「可选导出探测一次」行事；Android 走 JNA，符号缺席
 *    在调用点抛 `UnsatisfiedLinkError`，因此折叠成 `NotPublished` + `native_policy_core_*`
 *    短码，由 [NativePolicyCoreBridge] 负责降级，不额外造一个探不到底的枚举。
 * ③ 结果字段：Windows 带 `CoreEchoesClear`（只服务它自己的分批判据），这里带 `batches`
 *    （留痕要写「几批推完」）；两边的 NotPublished 都保留**真实 accepted**，
 *    Windows 的 `NotPublished()` 工厂把 accepted 归零、但它的 LegacyPush 也带真实前缀数，
 *    这里统一取后者那一档。
 *
 * 协议是纯逻辑（`send` 注入），因为 R8-CI-18 那一课：真 JNI 路径的用例在 PR 门禁里
 * 集体早退，等于没有覆盖——协议层必须在无 `.so` 的常跑面里可直测。
 */
internal object CoreDenylistPush {
    /** 与核心 `denylist::MODE_*` 逐值对应（跨语言常量，改一边必须改另一边；
     * 由 `AbiSurfaceAlignmentTest` 拿 Kotlin 侧常量对账 Rust 源码里的定义）。 */
    const val MODE_APPEND = 0

    const val MODE_REPLACE = 1
    const val MODE_BEGIN = 2
    const val MODE_COMMIT = 3

    /** 核心对**这一批**的应答（与「这一轮整体怎么样」的结论类型分工同 Windows）。 */
    data class Ack(
        val published: Boolean,
        val accepted: Int,
        val input: Int,
        val echoesClear: Boolean,
        val echoesMode: Boolean,
        val staged: Boolean,
        val detail: String,
    )

    /**
     * 解析注入应答。信封**刻意不含 abi_version**（与决策信封不同），所以能力探测
     * 只能靠字段自身：`mode` 在场 = 该核心支持暂存协议；只有 `clear` = 3 参旧核心；
     * 两者皆无 = 2 参旧核心（会忽略多余实参）。
     */
    fun parseAck(
        payload: String,
        offered: Int,
    ): Ack {
        val root = JSONObject(payload)
        if (root.optString("decision") != "ok") {
            val code =
                root
                    .optJSONObject("reason")
                    ?.optString("code")
                    ?.takeIf { it.isNotEmpty() }
                    ?: "native_denylist_response_not_ok"
            return Ack(false, 0, offered, false, false, false, code)
        }
        val accepted = readNonNegative(root, "accepted")
        // 核心如实回报 input；应答缺失时退回本地 offered 数（不虚报成功）
        val input = if (root.has("input")) readNonNegative(root, "input") else offered
        return Ack(
            published = true,
            accepted = accepted,
            input = input,
            echoesClear = root.has("clear"),
            echoesMode = root.has("mode"),
            staged = root.optBoolean("staged"),
            detail = "accepted=$accepted/input=$input",
        )
    }

    /** 推送整份协议。`send` 是「发一批并拿回应答」的注入点（真实现走 JNA，测试走假核心）。 */
    fun drive(
        batches: List<List<String>>,
        input: Int,
        send: (batch: List<String>, mode: Int) -> Ack,
    ): CoreDenylistUpdateResult {
        if (batches.isEmpty()) {
            return result(CoreDenylistOutcome.NotPublished, 0, input, 0, "denylist_no_batch")
        }
        val first = send(batches.first(), if (batches.size == 1) MODE_REPLACE else MODE_BEGIN)
        return when {
            !first.published -> aborted(first, input, batches.size, 0, "首批被拒")

            // 一批即完整：mode=1 的整批替换本就原子（少一次 FFI 往返）
            batches.size == 1 -> applied(first.accepted, input, batches.size, "single_batch")

            // 旧核心不回显 mode：不给它发提交批，退回既往链并如实记代价
            !first.echoesMode -> legacy(first, batches, send, input)

            else -> staged(first, batches, input, send)
        }
    }

    private fun staged(
        first: Ack,
        batches: List<List<String>>,
        input: Int,
        send: (batch: List<String>, mode: Int) -> Ack,
    ): CoreDenylistUpdateResult {
        var accepted = first.accepted
        var failure: CoreDenylistUpdateResult? = null
        var index = 1
        while (index < batches.size && failure == null) {
            val ack = send(batches[index], MODE_APPEND)
            failure = if (ack.published) null else aborted(ack, input, batches.size, index, "追加批被拒")
            accepted += ack.accepted
            index++
        }
        if (failure == null) {
            val commit = send(emptyList(), MODE_COMMIT)
            failure =
                when {
                    !commit.published -> {
                        aborted(commit, input, batches.size, batches.size, "提交被拒")
                    }

                    !commit.staged && commit.accepted == 0 -> {
                        refused(accepted, input, batches.size)
                    }

                    else -> {
                        null
                    }
                }
        }
        return failure ?: applied(accepted, input, batches.size, "staged_commit")
    }

    /** 既往协议（R7-RS-02）：首批 `clear=1` 立即生效 + 其余追加，只在核心不回显
     * `mode` 时走这里。中止时核心侧留下的确实是**已推送前缀**，所以 detail 必须那样写——
     * 这条措辞本身就是缺陷记录。 */
    private fun legacy(
        first: Ack,
        batches: List<List<String>>,
        send: (batch: List<String>, mode: Int) -> Ack,
        input: Int,
    ): CoreDenylistUpdateResult {
        var accepted = first.accepted
        var failure: CoreDenylistUpdateResult? = null
        if (!first.echoesClear) {
            // 2 参旧核心会忽略档位实参并按整批替换行事：继续推下去只会让名单变成「最后一批」
            failure =
                result(
                    CoreDenylistOutcome.NotPublished,
                    accepted,
                    input,
                    batches.size,
                    "core_lacks_clear_parameter@0（核心侧保留已推送前缀 $accepted 条）",
                )
        }
        var index = 1
        while (index < batches.size && failure == null) {
            val ack = send(batches[index], MODE_APPEND)
            failure =
                if (ack.published) {
                    null
                } else {
                    result(
                        CoreDenylistOutcome.NotPublished,
                        accepted,
                        input,
                        batches.size,
                        "denylist_chunk_failed@$index（核心侧保留已推送前缀 $accepted 条）",
                    )
                }
            accepted += ack.accepted
            index++
        }
        return failure ?: applied(accepted, input, batches.size, "legacy_replace_then_append")
    }

    private fun refused(
        accepted: Int,
        input: Int,
        batches: Int,
    ): CoreDenylistUpdateResult {
        // 核心没标 staged 也没接受任何条目 = 它没把暂存换进活动快照；与「首批被拒」分开记，
        // 因为两者的排障动作不同（前者要查会话是否开成，后者要查载荷是否越界）。
        val detail = "denylist_commit_refused"
        return result(CoreDenylistOutcome.NotPublished, accepted, input, batches, detail)
    }

    private fun aborted(
        ack: Ack,
        input: Int,
        batches: Int,
        index: Int,
        why: String,
    ): CoreDenylistUpdateResult =
        CoreDenylistUpdateResult(
            CoreDenylistOutcome.NotPublished,
            ack.accepted,
            input,
            batches,
            "denylist_staged_push_aborted@$index（$why；${ack.detail}）——未提交，核心侧仍服务上一份完整黑名单快照",
        )

    private fun applied(
        accepted: Int,
        input: Int,
        batches: Int,
        how: String,
    ): CoreDenylistUpdateResult =
        if (accepted < input) {
            result(
                CoreDenylistOutcome.PartialAccept,
                accepted,
                input,
                batches,
                "denylist_partial_accept accepted=$accepted input=$input（$how）",
            )
        } else {
            result(CoreDenylistOutcome.Published, accepted, input, batches, how)
        }

    private fun result(
        outcome: CoreDenylistOutcome,
        accepted: Int,
        input: Int,
        batches: Int,
        detail: String,
    ): CoreDenylistUpdateResult = CoreDenylistUpdateResult(outcome, accepted, input, batches, detail)

    private fun readNonNegative(
        root: JSONObject,
        key: String,
    ): Int = root.optInt(key, 0).coerceAtLeast(0)
}

/** 一轮推送的整体结论。`detail` 是给 logcat/审计用的短码，**不含 host 明文**。
 *
 * 公开而非 internal：`:app` 侧的装载器要把它写进留痕，而 Kotlin 的 internal 不跨模块——
 * 与其在 broker 侧再造一个「翻译成字符串」的中间口径，不如把结论本身做成两端同一份类型
 * （与 Windows 的 `CoreDenylistUpdateResult`/`CoreDenylistOutcome` 同形；差档见文件头注）。 */
enum class CoreDenylistOutcome {
    /** 核心如实收下了全部条目（空名单的 0/0 也算 Published：链跑过，名单就是空）。 */
    Published,

    /** 有条目被核心按形态拒收——名单**已生效但不完整**，必须留痕。 */
    PartialAccept,

    /** 没生效。与 Published(0) 必须可分辨：前者是「链断了」，后者是「链在跑、名单为空」。 */
    NotPublished,
}

/** 见 [CoreDenylistOutcome] 的说明——结论类型公开，协议实现仍留在 [CoreDenylistPush] 内部。
 * `batches` 是本端多出来的留痕字段，对应 Windows 的 `CoreEchoesClear`（头注「三处有意不一致」③）。 */
data class CoreDenylistUpdateResult(
    val outcome: CoreDenylistOutcome,
    val accepted: Int,
    val input: Int,
    val batches: Int,
    val detail: String,
) {
    companion object {
        /** 一轮根本没开始的结论（桥不在、asset 读不出）：accepted 恒 0、批次数如实 0。
         * 与协议中途失败的分工是「有没有发出过批」——后者由 [CoreDenylistPush] 带真实前缀数。 */
        fun notPublished(
            input: Int,
            detail: String,
        ): CoreDenylistUpdateResult = CoreDenylistUpdateResult(CoreDenylistOutcome.NotPublished, 0, input, 0, detail)
    }
}

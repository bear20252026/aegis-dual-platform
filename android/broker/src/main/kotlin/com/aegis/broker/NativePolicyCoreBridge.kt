package com.aegis.broker

import com.sun.jna.Library
import com.sun.jna.Native
import com.sun.jna.Pointer
import kotlin.time.Instant

/**
 * Android 侧的 Rust 策略核心受控桥接。
 *
 * 接口只传递 UTF-8 字符串与不透明指针；Rust 分配的响应字符串始终由同一动态库释放。
 * 任何库加载、ABI、JSON 协议或调用异常都以 null/false 返回给 Broker，由 Broker 失败闭合。
 */
class NativePolicyCoreBridge private constructor(
    private val native: NativePolicyCoreAbi,
    private val broker: Pointer,
) : AutoCloseable {
    fun createSession(
        sessionId: String,
        tabId: String,
        generation: Long,
        ttlSeconds: Long,
    ): Boolean =
        invokeBoolean {
            native.aegis_policy_core_broker_create_session(broker, sessionId, tabId, generation, ttlSeconds)
        }

    fun destroySession(sessionId: String): Boolean =
        invokeBoolean {
            native.aegis_policy_core_broker_destroy_session(broker, sessionId)
        }

    fun advanceDocumentGeneration(
        sessionId: String,
        tabId: String,
        nextGeneration: Long,
    ): Boolean =
        invokeBoolean {
            native.aegis_policy_core_broker_advance_document_generation(broker, sessionId, tabId, nextGeneration)
        }

    fun evaluateNavigation(
        sessionId: String,
        tabId: String,
        generation: Long,
        rawUrl: String,
        scope: String,
    ): Decision? =
        invokeDecision {
            native.aegis_policy_core_broker_evaluate_navigation_json(
                broker,
                sessionId,
                tabId,
                generation,
                rawUrl,
                scope,
            )
        }

    /** 登记由 Rust 核心托管的待审批导航；结果不会包含可立即消费的授权。 */
    fun requestNavigationConfirmation(
        sessionId: String,
        tabId: String,
        generation: Long,
        rawUrl: String,
        scope: String,
    ): Decision? =
        invokeDecision {
            native.aegis_policy_core_broker_request_navigation_confirmation_json(
                broker,
                sessionId,
                tabId,
                generation,
                rawUrl,
                scope,
            )
        }

    /** 仅用 Rust 核心登记的 nonce 显式批准，核心重新返回原始绑定授权。 */
    fun approveNavigationConfirmation(
        request: ApprovalRequest,
        rawUrl: String,
        scope: String,
    ): Decision? =
        invokeDecision {
            native.aegis_policy_core_broker_approve_navigation_confirmation_json(
                broker,
                request.nonce,
                rawUrl,
                scope,
            )
        }

    /** 显式拒绝待审批导航；调用异常、未知或已撤销 nonce 一律返回 false。 */
    fun rejectNavigationConfirmation(request: ApprovalRequest): Boolean =
        invokeBoolean { native.aegis_policy_core_broker_reject_navigation_confirmation(broker, request.nonce) }

    fun consumeNavigation(
        action: AuthorizedAction,
        rawUrl: String,
        scope: String,
    ): Boolean {
        val decision =
            invokeDecision {
                native.aegis_policy_core_broker_consume_navigation_json(broker, actionToJson(action), rawUrl, scope)
            }
        // AD-237（2026-09-26 审计）：deny 折叠为 false 时原因不静默——code/
        // detail 留痕（原生核心拒绝此前零痕迹，排障与审计面缺失）。
        if (decision is Decision.Deny) {
            android.util.Log.w(
                "AegisBroker",
                "native consumeNavigation 拒绝: code=${decision.reason.code} " +
                    "detail=${decision.reason.detail}",
            )
        }
        return decision is Decision.Allow
    }

    /**
     * 释放 Rust broker 指针。
     *
     * AD-236（2026-09-26 审计）：生产接线中本桥随 AndroidBroker 存活至进程
     * 退出——会话级资源已由 destroySession 逐会话释放，broker 指针为进程级
     * 生命周期（显式 close 调用点全工程为零，不为对齐 AutoCloseable 惯例而
     * 虚构中途释放——进程退出由 OS 回收）。保留实现为未来多 broker 生命周期
     * （如配置热重载）预留确定性释放面。
     */
    override fun close() {
        native.aegis_policy_core_broker_free(broker)
    }

    // JNI 边界必须吞掉所有异常转 fail-closed 布尔值（同名规则豁免见 C ABI 注释）
    @Suppress("TooGenericExceptionCaught")
    private fun invokeBoolean(call: () -> Byte): Boolean =
        try {
            call() == 1.toByte()
        } catch (e: LinkageError) {
            android.util.Log.e("AegisBroker", "native 调用链接失败: ${e.javaClass.simpleName}: ${e.message}")
            false
        } catch (e: Exception) {
            android.util.Log.e("AegisBroker", "native 调用异常: ${e.javaClass.simpleName}: ${e.message}")
            false
        }

    @Suppress("TooGenericExceptionCaught")
    private fun invokeDecision(call: () -> Pointer?): Decision? =
        try {
            val response = call() ?: return null
            try {
                parseDecisionJson(response.getString(0, "UTF-8"))
            } finally {
                native.aegis_policy_core_string_free(response)
            }
        } catch (e: LinkageError) {
            android.util.Log.e("AegisBroker", "native 决策链接失败: ${e.javaClass.simpleName}: ${e.message}")
            null
        } catch (e: Exception) {
            android.util.Log.e("AegisBroker", "native 决策异常: ${e.javaClass.simpleName}: ${e.message}")
            null
        }

    /**
     * 把威胁 host 快照注入原生核心黑名单（R9-B95 / 队列 Q51 的机制半边）。
     *
     * 空集合 = 清空并放行（核心侧默认绝不 deny-all），因此「内置名单为空」这一步
     * 与既往行为逐字一致——但注入仍然要发生：`Published(0/0)` 与 `NotPublished`
     * 的分别是「链在跑、名单为空」与「链断了」，前者才是可审计的状态。
     *
     * 生命周期：本桥的 `close()` 全工程零调用点（AD-236 记的进程级 broker 生命周期），
     * 故此处不需要租约；**若将来接 close，必须与本方法同批改**（Windows 侧的
     * TryAcquireLease 就是为这件事立的）。返回结果由调用方留痕，本函数不吞任何失败。
     */
    fun updateHostDenylist(hosts: List<String>): CoreDenylistUpdateResult {
        val batches = ThreatHostFeed.batches(hosts)
        return CoreDenylistPush.drive(batches, hosts.size) { batch, mode ->
            invokeDenylist(ThreatHostFeed.encode(batch), mode, batch.size)
        }
    }

    /** 单批注入：应答解析成 `Ack`；符号缺席/异常一律降级为 NotPublished 的短码，
     * 不抛给导航路径（旧 .so 没有这个导出时，出货 APK 不得因此变砖）。 */
    @Suppress("TooGenericExceptionCaught")
    private fun invokeDenylist(
        payload: String,
        mode: Int,
        offered: Int,
    ): CoreDenylistPush.Ack =
        try {
            val response =
                native
                    .aegis_policy_core_broker_update_host_denylist_json(broker, payload, mode)
                    ?: return CoreDenylistPush.Ack(
                        false,
                        0,
                        offered,
                        false,
                        false,
                        false,
                        "native_denylist_null_response",
                    )
            try {
                CoreDenylistPush.parseAck(response.getString(0, "UTF-8"), offered)
            } finally {
                native.aegis_policy_core_string_free(response)
            }
        } catch (e: LinkageError) {
            android.util.Log.e("AegisBroker", "native 黑名单注入链接失败: ${e.javaClass.simpleName}")
            CoreDenylistPush.Ack(false, 0, offered, false, false, false, "native_denylist_unavailable")
        } catch (e: Exception) {
            android.util.Log.e("AegisBroker", "native 黑名单注入异常: ${e.javaClass.simpleName}")
            CoreDenylistPush.Ack(false, 0, offered, false, false, false, "native_denylist_call_failed")
        }

    // JNI 绑定函数名必须与 C ABI 符号逐字一致（snake_case）——豁免命名规范
    @Suppress("ktlint:standard:function-naming", "ktlint:standard:property-naming")
    private interface NativePolicyCoreAbi : Library {
        fun aegis_policy_core_abi_version(): Int

        fun aegis_policy_core_broker_new(policyVersion: String): Pointer?

        fun aegis_policy_core_broker_free(broker: Pointer)

        fun aegis_policy_core_string_free(response: Pointer)

        fun aegis_policy_core_broker_create_session(
            broker: Pointer,
            sessionId: String,
            tabId: String,
            generation: Long,
            ttlSeconds: Long,
        ): Byte

        fun aegis_policy_core_broker_destroy_session(
            broker: Pointer,
            sessionId: String,
        ): Byte

        fun aegis_policy_core_broker_advance_document_generation(
            broker: Pointer,
            sessionId: String,
            tabId: String,
            nextGeneration: Long,
        ): Byte

        fun aegis_policy_core_broker_evaluate_navigation_json(
            broker: Pointer,
            sessionId: String,
            tabId: String,
            generation: Long,
            rawUrl: String,
            scope: String,
        ): Pointer?

        fun aegis_policy_core_broker_request_navigation_confirmation_json(
            broker: Pointer,
            sessionId: String,
            tabId: String,
            generation: Long,
            rawUrl: String,
            scope: String,
        ): Pointer?

        fun aegis_policy_core_broker_approve_navigation_confirmation_json(
            broker: Pointer,
            nonce: String,
            rawUrl: String,
            scope: String,
        ): Pointer?

        fun aegis_policy_core_broker_reject_navigation_confirmation(
            broker: Pointer,
            nonce: String,
        ): Byte

        fun aegis_policy_core_broker_consume_navigation_json(
            broker: Pointer,
            actionJson: String,
            rawUrl: String,
            scope: String,
        ): Pointer?

        // 审计第六轮遗留缺口 / R9-B95 的 Android 半边：第三参在 v4 起是档位
        // （0 追加 / 1 整批替换 / 2 开暂存会话 / 3 提交），取值域与核心
        // ffi/broker/denylist.rs 的 MODE_* 逐值对应，由 AbiSurfaceAlignmentTest 对账。
        @Suppress("FunctionNaming") // C ABI 符号名逐字映射（JNA 按方法名找符号），与其余导出同口径
        fun aegis_policy_core_broker_update_host_denylist_json(
            broker: Pointer,
            hostsJson: String,
            mode: Int,
        ): Pointer?
    }

    companion object {
        fun tryCreate(policyVersion: String): NativePolicyCoreBridge? =
            try {
                val native = Native.load("aegis_policy_core", NativePolicyCoreAbi::class.java)
                if (native.aegis_policy_core_abi_version() != EXPECTED_C_ABI_VERSION) {
                    // 诊断留痕（真机排障：so 在但 ABI 与 Kotlin 期望不一致）
                    android.util.Log.e("AegisBroker", "native abi_version mismatch: expected $EXPECTED_C_ABI_VERSION")
                    null
                } else {
                    val broker = native.aegis_policy_core_broker_new(policyVersion)
                    if (broker == null) {
                        android.util.Log.e("AegisBroker", "aegis_policy_core_broker_new returned null")
                    }
                    broker?.let { NativePolicyCoreBridge(native, it) }
                }
            } catch (e: LinkageError) {
                // 诊断留痕（真机排障：libjnidispatch/libaegis_policy_core 加载失败——
                // 典型为 R8 混淆掉 JNA 按名映射的 Abi 接口，见 app/proguard-rules.pro）
                android.util.Log.e("AegisBroker", "native core load failed: ${e.javaClass.simpleName}: ${e.message}")
                null
            } catch (e: Exception) {
                android.util.Log.e("AegisBroker", "native core init failed: ${e.javaClass.simpleName}: ${e.message}")
                null
            }

        /** 编解码已外移到 `NativePolicyCoreCodec.kt`（行数红线只许减不许增）；
         *  保留这条委托是为了引用面逐字不变（AndroidBrokerTest 仍按类名调用）。 */
        internal fun parseDecisionJson(payload: String): Decision = parseNativeDecisionJson(payload)
    }
}

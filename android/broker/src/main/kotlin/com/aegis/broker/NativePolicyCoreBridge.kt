package com.aegis.broker

import com.sun.jna.Library
import com.sun.jna.Native
import com.sun.jna.Pointer
import kotlinx.datetime.Instant
import org.json.JSONObject

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
    ): Boolean = invokeBoolean { native.aegis_policy_core_broker_create_session(broker, sessionId, tabId, generation, ttlSeconds) }

    fun destroySession(sessionId: String): Boolean = invokeBoolean { native.aegis_policy_core_broker_destroy_session(broker, sessionId) }

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
        val actionJson =
            JSONObject()
                .put("session_id", action.sessionId)
                .put("tab_id", action.tabId)
                .put("document_generation", action.documentGeneration)
                .put("origin", action.origin)
                .put("method", action.method)
                .put("canonical_parameters", action.canonicalParameters)
                .put("scope", action.scope)
                .put("expires_at", action.expiresAt.epochSeconds)
                .put("nonce", action.nonce)
                .put("policy_version", action.policyVersion)
                .put("explanation", action.explanation)
                .toString()
        return invokeDecision {
            native.aegis_policy_core_broker_consume_navigation_json(broker, actionJson, rawUrl, scope)
        } is Decision.Allow
    }

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
    }

    companion object {
        // C ABI v3 新增 Rust 托管的确认登记、批准兑换与拒绝接口。
        private const val EXPECTED_ABI_VERSION = 3

        fun tryCreate(policyVersion: String): NativePolicyCoreBridge? =
            try {
                val native = Native.load("aegis_policy_core", NativePolicyCoreAbi::class.java)
                if (native.aegis_policy_core_abi_version() != EXPECTED_ABI_VERSION) {
                    // 诊断留痕（真机排障：so 在但 ABI 与 Kotlin 期望不一致）
                    android.util.Log.e("AegisBroker", "native abi_version mismatch: expected $EXPECTED_ABI_VERSION")
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

        internal fun parseDecisionJson(payload: String): Decision {
            val root = JSONObject(payload)
            check(root.getInt("abi_version") == EXPECTED_ABI_VERSION) { "native ABI response mismatch" }
            return when (root.getString("decision")) {
                "allow" -> {
                    val action = root.getJSONObject("action")
                    Decision.Allow(
                        AuthorizedAction(
                            sessionId = action.getString("session_id"),
                            tabId = action.getString("tab_id"),
                            documentGeneration = action.getLong("document_generation"),
                            origin = action.getString("origin"),
                            method = action.getString("method"),
                            canonicalParameters = action.getString("canonical_parameters"),
                            scope = action.getString("scope"),
                            expiresAt = Instant.fromEpochSeconds(action.getLong("expires_at")),
                            nonce = action.getString("nonce"),
                            policyVersion = action.getString("policy_version"),
                            explanation = action.optString("explanation", ""),
                        ),
                    )
                }

                "deny" -> {
                    val reason = root.getJSONObject("reason")
                    Decision.Deny(
                        DenyReason(
                            code = reason.getString("code"),
                            detail = reason.getString("detail"),
                            explanation = reason.optString("explanation", ""),
                        ),
                    )
                }

                "require_confirmation" -> {
                    val request = root.getJSONObject("request")
                    Decision.RequireConfirmation(
                        ApprovalRequest(
                            origin = request.getString("origin"),
                            method = request.getString("method"),
                            path = request.getString("path"),
                            scope = request.getString("scope"),
                            expiresAt = Instant.fromEpochSeconds(request.getLong("expires_at")),
                            nonce = request.getString("nonce"),
                        ),
                    )
                }

                else -> {
                    throw IllegalArgumentException("unsupported native decision")
                }
            }
        }
    }
}

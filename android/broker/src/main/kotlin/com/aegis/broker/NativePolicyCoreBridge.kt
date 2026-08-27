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
    fun createSession(sessionId: String, tabId: String, generation: Long, ttlSeconds: Long): Boolean =
        invokeBoolean { native.aegis_policy_core_broker_create_session(broker, sessionId, tabId, generation, ttlSeconds) }

    fun destroySession(sessionId: String): Boolean =
        invokeBoolean { native.aegis_policy_core_broker_destroy_session(broker, sessionId) }

    fun advanceDocumentGeneration(sessionId: String, tabId: String, nextGeneration: Long): Boolean =
        invokeBoolean {
            native.aegis_policy_core_broker_advance_document_generation(broker, sessionId, tabId, nextGeneration)
        }

    fun evaluateNavigation(
        sessionId: String,
        tabId: String,
        generation: Long,
        rawUrl: String,
        scope: String,
    ): Decision? = invokeDecision {
        native.aegis_policy_core_broker_evaluate_navigation_json(
            broker, sessionId, tabId, generation, rawUrl, scope,
        )
    }

    fun consumeNavigation(action: AuthorizedAction, rawUrl: String, scope: String): Boolean {
        val actionJson = JSONObject()
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

    private fun invokeBoolean(call: () -> Byte): Boolean = try {
        call() == 1.toByte()
    } catch (_: LinkageError) {
        false
    } catch (_: Exception) {
        false
    }

    private fun invokeDecision(call: () -> Pointer?): Decision? = try {
        val response = call() ?: return null
        try {
            parseDecisionJson(response.getString(0, "UTF-8"))
        } finally {
            native.aegis_policy_core_string_free(response)
        }
    } catch (_: LinkageError) {
        null
    } catch (_: Exception) {
        null
    }

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
        fun aegis_policy_core_broker_destroy_session(broker: Pointer, sessionId: String): Byte
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
        fun aegis_policy_core_broker_consume_navigation_json(
            broker: Pointer,
            actionJson: String,
            rawUrl: String,
            scope: String,
        ): Pointer?
    }

    companion object {
        private const val expectedAbiVersion = 1

        fun tryCreate(policyVersion: String): NativePolicyCoreBridge? = try {
            val native = Native.load("aegis_policy_core", NativePolicyCoreAbi::class.java)
            if (native.aegis_policy_core_abi_version() != expectedAbiVersion) return null
            val broker = native.aegis_policy_core_broker_new(policyVersion) ?: return null
            NativePolicyCoreBridge(native, broker)
        } catch (_: LinkageError) {
            null
        } catch (_: Exception) {
            null
        }

        internal fun parseDecisionJson(payload: String): Decision {
            val root = JSONObject(payload)
            check(root.getInt("abi_version") == expectedAbiVersion) { "native ABI response mismatch" }
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
                else -> throw IllegalArgumentException("unsupported native decision")
            }
        }
    }
}

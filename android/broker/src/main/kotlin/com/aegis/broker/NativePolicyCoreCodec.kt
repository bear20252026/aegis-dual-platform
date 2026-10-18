package com.aegis.broker

import org.json.JSONObject
import kotlin.time.Instant

// 原生决策信封的编解码（自 NativePolicyCoreBridge 外移，R9-B95）。
//
// 为什么外移而不是就地加：那个文件停在 332 行的基线额度上（SP-255 行数红线是 ratchet——
// 基线内只许减不许增），而本批要往里加黑名单注入的绑定与协议驱动。与 Windows 侧同一取舍：
// NativePolicyCoreBridge.Denylist.cs 的头部就写着「拆成 partial 文件与 MainWindow.*.cs 同法
// （行数红线只许减不许增）」。Kotlin 没有 partial，所以把纯编解码拆出来——它不碰句柄、
// 不碰租约，拆走之后桥接文件反而更小；两份映射仍由同一批用例判（桥内保留一行委托，
// 测试引用面 NativePolicyCoreBridge.parseDecisionJson 逐字不变）。

/**
 * AD-144（审计 2026-09-23 清单·A6 批）：AuthorizedAction → 协议 JSON 映射抽具名函数——
 * 原手工 JSONObject 链内联在 consumeNavigation 调用点，字段面与决策解析的
 * `allow.action` 解析面靠人工对齐；抽函数后映射点单一可读，字段增减只改此一处。
 */
internal fun actionToJson(action: AuthorizedAction): String =
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

/**
 * 决策信封 → 端侧 `Decision`。
 *
 * AD-163：未知 decision 形态**抛异常**而不是折叠成 Deny——抛出让调用点走
 * 失败闭合（`invokeDecision` 捕获后返回 null ⇒ Broker 拒绝导航），
 * 折叠成 Deny 会把「协议不认识」误报成「核心认识并拒绝」。
 */
internal fun parseNativeDecisionJson(payload: String): Decision {
    val root = JSONObject(payload)
    check(root.getInt("abi_version") == EXPECTED_C_ABI_VERSION) { "native ABI response mismatch" }
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

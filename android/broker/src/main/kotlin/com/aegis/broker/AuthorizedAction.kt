package com.aegis.broker

import kotlinx.datetime.Instant

/**
 * 阶段 D（蓝图 android/broker）：AuthorizedAction——唯一允许进入副作用服务的凭据
 * （ADR-002——与 contracts action.schema.json 一致）。绑定 session/tab/
 * document_generation/origin/method/scope/expires_at/nonce/policy_version——
 * 任一字段变化使批准失效。
 */
data class AuthorizedAction(
    val sessionId: String,
    val tabId: String,
    val documentGeneration: Long,
    val origin: String,
    val method: String,
    val canonicalParameters: String,
    val scope: String,
    val expiresAt: Instant,
    val nonce: String,
    val policyVersion: String,
)

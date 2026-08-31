package com.aegis.broker

import kotlinx.datetime.Instant

/**
 * 阶段 D（蓝图 android/broker）：类型化安全决策——与 contracts（action/approval
 * schema + vectors）一致——不再用 bool/回调"记录但继续"。
 * Decision = Allow(AuthorizedAction) | RequireConfirmation | Deny（默认拒绝 fail-closed）。
 */
sealed interface Decision {
    data class Allow(
        val action: AuthorizedAction,
    ) : Decision

    data class RequireConfirmation(
        val request: ApprovalRequest,
    ) : Decision

    data class Deny(
        val reason: DenyReason,
    ) : Decision
}

/** 审批请求（高风险副作用——原生确认 UI——绑定参数与一次性 nonce——重放拒绝）。 */
data class ApprovalRequest(
    val origin: String,
    val method: String,
    val path: String,
    val scope: String,
    val expiresAt: Instant,
    val nonce: String,
)

/** 拒绝原因（类型化——fail-closed——审计可追溯）。 */
data class DenyReason(
    val code: String,
    val detail: String,
    val explanation: String = "",
)

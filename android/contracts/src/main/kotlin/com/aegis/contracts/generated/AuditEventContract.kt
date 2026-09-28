// 由 contracts/codegen/generate_kotlin.py 生成（蓝图阶段 B——契约事实来源——请勿手工编辑）
package com.aegis.contracts.generated

data class AuditEventContract(
    val event_id: String,
    val timestamp: String,
    val decision: String,
    val scope: String,
    val origin: String,
    val reason: String? = null,
    val tab_id: String? = null,
)

/** PY-188（2026-09-26 审计）：AuditEventContract 值域常量——schema enum/const 单源，属性保持基础类型以兼容既有消费方。 */
object AuditEventContractValues {
    const val DECISION_ALLOW: String = "allow" // enum: allow | deny | require_confirmation
    const val DECISION_DENY: String = "deny" // enum: allow | deny | require_confirmation
    const val DECISION_REQUIRE_CONFIRMATION: String = "require_confirmation" // enum: allow | deny | require_confirmation
}

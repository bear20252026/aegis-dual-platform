// 由 contracts/codegen/generate_kotlin.py 生成（蓝图阶段 B——契约事实来源——请勿手工编辑）
package com.aegis.contracts.generated

data class AuditEvent.schema(
    val event_id: String,
    val timestamp: String,
    val decision: String,
    val scope: String,
    val origin: String,
    val reason: String,
    val tab_id: String,
)

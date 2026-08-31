// 由 contracts/codegen/generate_kotlin.py 生成（蓝图阶段 B——契约事实来源——请勿手工编辑）
package com.aegis.contracts.generated

data class ActionContract(
    val session_id: String,
    val tab_id: String,
    val document_generation: Long,
    val origin: String,
    val method: String,
    val canonical_parameters: String,
    val scope: String,
    val expires_at: String,
    val nonce: String,
    val policy_version: String,
)

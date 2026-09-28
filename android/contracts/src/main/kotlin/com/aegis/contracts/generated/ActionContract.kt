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

/** PY-188（2026-09-26 审计）：ActionContract 值域常量——schema enum/const 单源，属性保持基础类型以兼容既有消费方。 */
object ActionContractValues {
    const val METHOD_GET: String = "GET" // enum: GET | POST | PUT | DELETE | NAVIGATE | DOWNLOAD
    const val METHOD_POST: String = "POST" // enum: GET | POST | PUT | DELETE | NAVIGATE | DOWNLOAD
    const val METHOD_PUT: String = "PUT" // enum: GET | POST | PUT | DELETE | NAVIGATE | DOWNLOAD
    const val METHOD_DELETE: String = "DELETE" // enum: GET | POST | PUT | DELETE | NAVIGATE | DOWNLOAD
    const val METHOD_NAVIGATE: String = "NAVIGATE" // enum: GET | POST | PUT | DELETE | NAVIGATE | DOWNLOAD
    const val METHOD_DOWNLOAD: String = "DOWNLOAD" // enum: GET | POST | PUT | DELETE | NAVIGATE | DOWNLOAD
}

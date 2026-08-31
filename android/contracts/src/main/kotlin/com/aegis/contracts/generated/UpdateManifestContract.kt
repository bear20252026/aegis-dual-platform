// 由 contracts/codegen/generate_kotlin.py 生成（蓝图阶段 B——契约事实来源——请勿手工编辑）
package com.aegis.contracts.generated

data class UpdateManifestContract(
    val schema: Long,
    val product: String,
    val version: String,
    val channel: String,
    val expires_at: String,
    val artifacts: List<Any>,
    val signatures: List<Any>,
)

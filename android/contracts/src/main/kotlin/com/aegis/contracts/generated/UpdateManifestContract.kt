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

/** PY-188（2026-09-26 审计）：UpdateManifestContract 值域常量——schema enum/const 单源，属性保持基础类型以兼容既有消费方。 */
object UpdateManifestContractValues {
    const val SCHEMA: Long = 1 // const: 1
    const val PRODUCT: String = "Aegis" // const: Aegis
    const val CHANNEL_STABLE: String = "stable" // enum: stable | beta | nightly
    const val CHANNEL_BETA: String = "beta" // enum: stable | beta | nightly
    const val CHANNEL_NIGHTLY: String = "nightly" // enum: stable | beta | nightly
}

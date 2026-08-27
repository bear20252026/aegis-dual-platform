// 由 contracts/codegen/generate_kotlin.py 生成（蓝图阶段 B——契约事实来源——请勿手工编辑）
package com.aegis.contracts.generated

data class CapabilityContract(
    val scope: String,
    val actions: List<String>,
    val resources: List<String>,
    val requires_confirmation: Boolean,
)

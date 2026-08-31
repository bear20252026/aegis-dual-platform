package com.aegis.contracts

/**
 * 阶段 D（蓝图 android/contracts）：contracts 生成的 Kotlin 模型——唯一安全协议
 * 事实来源（蓝图 contracts/——schemas 六类对象冻结 + vectors 测试向量——
 * JSON 11/11 有效）。本目录引用 contracts/（不手工维护平行 Schema——蓝图禁止）。
 * 生成方式：contracts/codegen（generate_kotlin.py——蓝图阶段 B）——
 * 当前阶段最小：引用说明 + 版本（完整 codegen 按蓝图迭代）。
 */
object Contracts {
    const val CONTRACT_ROOT = "../../../../contracts"
    const val POLICY_VERSION = "1.0" // 与 contracts/version.schema.json 语义一致
}

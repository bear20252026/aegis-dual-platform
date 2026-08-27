package com.aegis.broker

/**
 * 原生策略核心的显式启用门禁。
 *
 * 默认构建不启用原生策略核心，保留经验证的 Kotlin Broker。若构建显式要求原生核心，
 * 则原生库、ABI 与完整性验证必须全部就绪；否则任何导航均失败闭合，绝不静默回退。
 */
fun interface NativePolicyCoreGate {
    fun probe(): NativePolicyCoreGateResult
}

data class NativePolicyCoreGateResult(
    val allowsPlatformBroker: Boolean,
    val denialCode: String? = null,
) {
    companion object {
        fun disabled() = NativePolicyCoreGateResult(allowsPlatformBroker = true)

        fun enabled() = NativePolicyCoreGateResult(allowsPlatformBroker = true)

        fun block(denialCode: String) = NativePolicyCoreGateResult(
            allowsPlatformBroker = false,
            denialCode = denialCode,
        )
    }
}

object DefaultNativePolicyCoreGate : NativePolicyCoreGate {
    override fun probe(): NativePolicyCoreGateResult =
        if (BuildConfig.REQUIRE_NATIVE_POLICY_CORE) {
            // 原生 Kotlin 绑定和各 ABI .so 制品尚未被接入应用。显式启用时拒绝而非分叉执行。
            NativePolicyCoreGateResult.block("native_policy_core_not_packaged")
        } else {
            NativePolicyCoreGateResult.disabled()
        }
}

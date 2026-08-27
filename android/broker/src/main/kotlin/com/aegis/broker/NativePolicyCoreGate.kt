package com.aegis.broker

import com.sun.jna.Library
import com.sun.jna.Native

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

        fun block(denialCode: String) = NativePolicyCoreGateResult(
            allowsPlatformBroker = false,
            denialCode = denialCode,
        )
    }
}

object DefaultNativePolicyCoreGate : NativePolicyCoreGate {
    private const val expectedAbiVersion = 1

    override fun probe(): NativePolicyCoreGateResult {
        if (!BuildConfig.REQUIRE_NATIVE_POLICY_CORE) return NativePolicyCoreGateResult.disabled()
        val abiVersion = try {
            Native.load("aegis_policy_core", NativePolicyCoreAbi::class.java)
                .aegis_policy_core_abi_version()
        } catch (_: LinkageError) {
            return NativePolicyCoreGateResult.block("native_policy_core_unavailable")
        } catch (_: Exception) {
            return NativePolicyCoreGateResult.block("native_policy_core_probe_failed")
        }
        if (abiVersion != expectedAbiVersion) {
            return NativePolicyCoreGateResult.block("native_policy_core_abi_mismatch")
        }
        return NativePolicyCoreGateResult.enabled()
    }
}

private interface NativePolicyCoreAbi : Library {
    fun aegis_policy_core_abi_version(): Int
}

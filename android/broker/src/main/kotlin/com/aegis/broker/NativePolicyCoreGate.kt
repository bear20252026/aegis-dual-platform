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
        /**
         * AD-145（审计 2026-09-23 清单·A6 批）：双工厂合并——原 disabled()/
         * enabled() 二者产出完全相同的放行结果（差异只在调用点的语义注释），
         * 属无差别重复工厂。合并为单一 [allowed]；Disabled（构建未要求原生
         * 核心）与 Enabled（原生核心探测通过）两种语境共用同一放行值。
         */
        fun allowed() = NativePolicyCoreGateResult(allowsPlatformBroker = true)

        fun block(denialCode: String) =
            NativePolicyCoreGateResult(
                allowsPlatformBroker = false,
                denialCode = denialCode,
            )
    }
}

object DefaultNativePolicyCoreGate : NativePolicyCoreGate {
    /**
     * AD-080（2026-09-26 审计）：探测结果进程级缓存。probe 位于 Broker 每次
     * 导航/审批评估的热路径（evaluateNavigation/approve/consume 等多处调用），
     * 原实现每次都 Native.load 新建 JNA 代理并跨 JNI 探测；而探测结果由
     * 编译期开关 + 库存在性/ABI 常量决定，进程内不变。缓存 block 结果与
     * 门禁 fail-closed 语义一致（库缺失/ABI 失配是确定性状态，非瞬时故障）。
     */
    @Volatile
    private var cachedResult: NativePolicyCoreGateResult? = null

    override fun probe(): NativePolicyCoreGateResult = cachedResult ?: probeOnce().also { cachedResult = it }

    private fun probeOnce(): NativePolicyCoreGateResult =
        when (val probe = probeAbiVersion()) {
            is AbiProbe.Disabled -> {
                // Disabled = 构建未要求原生核心（放行）；Enabled = 探测通过（放行）
                // ——二者共用 allowed() 单一工厂（AD-145）。
                NativePolicyCoreGateResult.allowed()
            }

            is AbiProbe.Unavailable -> {
                NativePolicyCoreGateResult.block("native_policy_core_unavailable")
            }

            is AbiProbe.Failed -> {
                NativePolicyCoreGateResult.block("native_policy_core_probe_failed")
            }

            is AbiProbe.Version -> {
                if (probe.value == EXPECTED_C_ABI_VERSION) {
                    NativePolicyCoreGateResult.allowed()
                } else {
                    NativePolicyCoreGateResult.block("native_policy_core_abi_mismatch")
                }
            }
        }

    /** ABI 探测单出口（try/catch 表达式）——错误码分类保留原三态语义。 */
    private fun probeAbiVersion(): AbiProbe =
        if (!BuildConfig.REQUIRE_NATIVE_POLICY_CORE) {
            AbiProbe.Disabled
        } else {
            try {
                AbiProbe.Version(
                    Native
                        .load("aegis_policy_core", NativePolicyCoreAbi::class.java)
                        .aegis_policy_core_abi_version(),
                )
            } catch (_: LinkageError) {
                AbiProbe.Unavailable
            } catch (_: Exception) {
                AbiProbe.Failed
            }
        }

    /** 探测结果分类（Disabled = 构建未要求原生核心，直通 Kotlin Broker）。 */
    private sealed interface AbiProbe {
        data object Disabled : AbiProbe

        data object Unavailable : AbiProbe

        data object Failed : AbiProbe

        data class Version(
            val value: Int,
        ) : AbiProbe
    }
}

/**
 * C ABI 版本单源（全库审计 2026-09-02 收敛）：此前 EXPECTED_ABI_VERSION 在
 * NativePolicyCoreGate 与 NativePolicyCoreBridge 双份定义——ABI 升级时漏改
 * 任一处即出现「门禁通过、桥接失配」（或反之）的静默漂移。v3 新增 Rust
 * 托管的确认登记、批准兑换与拒绝接口；v4（第八轮 ⑨，R8-RS-14）把黑名单注入的
 * clear 参数扩成档位（0 追加 / 1 整批替换 / 2 开暂存会话 / 3 提交），消除
 * 「约 85 批推送期间判定读不完整名单」的窗口。探测不一致即拒绝加载（不降级）。
 */
internal const val EXPECTED_C_ABI_VERSION = 4

// JNI 绑定函数名必须与 C ABI 符号逐字一致（snake_case）——豁免命名规范
@Suppress("ktlint:standard:function-naming")
private interface NativePolicyCoreAbi : Library {
    fun aegis_policy_core_abi_version(): Int
}

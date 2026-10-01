// 由 contracts/codegen/generate_kotlin.py 生成（蓝图阶段 B——契约事实来源——请勿手工编辑）
package com.aegis.contracts.generated

data class UpdateManifestContract(
    val schema: Long,
    val product: String,
    val version: String,
    val channel: String,
    val expires_at: String,
    val artifacts: List<UpdateManifestContractArtifact>,
    val signatures: List<UpdateManifestContractSignature>,
)

/** PY-243（2026-10-01 审计）：UpdateManifestContractArtifact 嵌套子模型——schema 数组 items 单源（字段获得编译期锚点，不再降级 Any）。 */
data class UpdateManifestContractArtifact(
    val platform: String,
    val format: String,
    val url: String,
    val sha256: String,
    val size: Long,
)

/** PY-188（2026-09-26 审计）：UpdateManifestContractArtifact 值域常量——schema enum/const 单源，属性保持基础类型以兼容既有消费方。 */
object UpdateManifestContractArtifactValues {
    const val PLATFORM_WINDOWS_X64: String = "windows-x64" // enum: windows-x64 | android-universal
    const val PLATFORM_ANDROID_UNIVERSAL: String = "android-universal" // enum: windows-x64 | android-universal
    const val FORMAT_MSIX: String = "msix" // enum: msix | appinstaller | apk | aab | inno-setup-exe | exe | zip
    const val FORMAT_APPINSTALLER: String = "appinstaller" // enum: msix | appinstaller | apk | aab | inno-setup-exe | exe | zip
    const val FORMAT_APK: String = "apk" // enum: msix | appinstaller | apk | aab | inno-setup-exe | exe | zip
    const val FORMAT_AAB: String = "aab" // enum: msix | appinstaller | apk | aab | inno-setup-exe | exe | zip
    const val FORMAT_INNO_SETUP_EXE: String = "inno-setup-exe" // enum: msix | appinstaller | apk | aab | inno-setup-exe | exe | zip
    const val FORMAT_EXE: String = "exe" // enum: msix | appinstaller | apk | aab | inno-setup-exe | exe | zip
    const val FORMAT_ZIP: String = "zip" // enum: msix | appinstaller | apk | aab | inno-setup-exe | exe | zip
}

/** PY-243（2026-10-01 审计）：UpdateManifestContractSignature 嵌套子模型——schema 数组 items 单源（字段获得编译期锚点，不再降级 Any）。 */
data class UpdateManifestContractSignature(
    val key_id: String,
    val sig: String,
)

/** PY-188（2026-09-26 审计）：UpdateManifestContract 值域常量——schema enum/const 单源，属性保持基础类型以兼容既有消费方。 */
object UpdateManifestContractValues {
    const val SCHEMA: Long = 1 // const: 1
    const val PRODUCT: String = "Aegis" // const: Aegis
    const val CHANNEL_STABLE: String = "stable" // enum: stable | beta | nightly
    const val CHANNEL_BETA: String = "beta" // enum: stable | beta | nightly
    const val CHANNEL_NIGHTLY: String = "nightly" // enum: stable | beta | nightly
}

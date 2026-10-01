// 由 contracts/codegen/generate_csharp.py 生成（蓝图阶段 B——契约事实来源——请勿手工编辑）
using System.Collections.Generic;
namespace Aegis.Windows.Contracts.Generated;

public sealed record UpdateManifestContract(
    long schema,
    string product,
    string version,
    string channel,
    string expires_at,
    List<UpdateManifestContractArtifact> artifacts,
    List<UpdateManifestContractSignature> signatures
);

/// <summary>PY-243（2026-10-01 审计）：UpdateManifestContractArtifact 嵌套子模型——schema 数组 items 单源（字段获得编译期锚点，不再降级 object）。</summary>
public sealed record UpdateManifestContractArtifact(
    string platform,
    string format,
    string url,
    string sha256,
    long size
);

/// <summary>PY-188（2026-09-26 审计）：UpdateManifestContractArtifact 值域常量——schema enum/const 单源，属性保持基础类型以兼容既有消费方。</summary>
public static class UpdateManifestContractArtifactValues
{
    public const string PlatformWindowsX64 = "windows-x64";  // enum: windows-x64 | android-universal
    public const string PlatformAndroidUniversal = "android-universal";  // enum: windows-x64 | android-universal
    public const string FormatMsix = "msix";  // enum: msix | appinstaller | apk | aab | inno-setup-exe | exe | zip
    public const string FormatAppinstaller = "appinstaller";  // enum: msix | appinstaller | apk | aab | inno-setup-exe | exe | zip
    public const string FormatApk = "apk";  // enum: msix | appinstaller | apk | aab | inno-setup-exe | exe | zip
    public const string FormatAab = "aab";  // enum: msix | appinstaller | apk | aab | inno-setup-exe | exe | zip
    public const string FormatInnoSetupExe = "inno-setup-exe";  // enum: msix | appinstaller | apk | aab | inno-setup-exe | exe | zip
    public const string FormatExe = "exe";  // enum: msix | appinstaller | apk | aab | inno-setup-exe | exe | zip
    public const string FormatZip = "zip";  // enum: msix | appinstaller | apk | aab | inno-setup-exe | exe | zip
}

/// <summary>PY-243（2026-10-01 审计）：UpdateManifestContractSignature 嵌套子模型——schema 数组 items 单源（字段获得编译期锚点，不再降级 object）。</summary>
public sealed record UpdateManifestContractSignature(
    string key_id,
    string sig
);

/// <summary>PY-188（2026-09-26 审计）：UpdateManifestContract 值域常量——schema enum/const 单源，属性保持基础类型以兼容既有消费方。</summary>
public static class UpdateManifestContractValues
{
    public const long Schema = 1;  // const: 1
    public const string Product = "Aegis";  // const: Aegis
    public const string ChannelStable = "stable";  // enum: stable | beta | nightly
    public const string ChannelBeta = "beta";  // enum: stable | beta | nightly
    public const string ChannelNightly = "nightly";  // enum: stable | beta | nightly
}

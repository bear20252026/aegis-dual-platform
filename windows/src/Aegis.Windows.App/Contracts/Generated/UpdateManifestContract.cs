// 由 contracts/codegen/generate_csharp.py 生成（蓝图阶段 B——契约事实来源——请勿手工编辑）
using System.Collections.Generic;
namespace Aegis.Windows.Contracts.Generated;

public sealed record UpdateManifestContract(
    long schema,
    string product,
    string version,
    string channel,
    string expires_at,
    List<object> artifacts,
    List<object> signatures
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

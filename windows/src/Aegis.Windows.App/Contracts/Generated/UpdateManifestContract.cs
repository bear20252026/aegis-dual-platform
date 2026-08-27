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
    List<object> signatures,
);

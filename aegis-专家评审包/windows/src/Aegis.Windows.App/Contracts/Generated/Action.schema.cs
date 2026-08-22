// 由 contracts/codegen/generate_csharp.py 生成（蓝图阶段 B——契约事实来源——请勿手工编辑）
namespace Aegis.Windows.Contracts.Generated;

public sealed record Action.schema(
    string session_id,
    string tab_id,
    long document_generation,
    string origin,
    string method,
    string canonical_parameters,
    string scope,
    string expires_at,
    string nonce,
    string policy_version,
);

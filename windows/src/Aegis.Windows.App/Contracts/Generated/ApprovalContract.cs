// 由 contracts/codegen/generate_csharp.py 生成（蓝图阶段 B——契约事实来源——请勿手工编辑）
using System.Collections.Generic;
namespace Aegis.Windows.Contracts.Generated;

public sealed record ApprovalContract(
    string origin,
    string method,
    string path,
    string scope,
    string expires_at,
    string nonce
);

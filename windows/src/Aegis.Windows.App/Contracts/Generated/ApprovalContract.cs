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

/// <summary>PY-188（2026-09-26 审计）：ApprovalContract 值域常量——schema enum/const 单源，属性保持基础类型以兼容既有消费方。</summary>
public static class ApprovalContractValues
{
    public const string MethodGET = "GET";  // enum: GET | POST | PUT | DELETE | NAVIGATE | DOWNLOAD
    public const string MethodPOST = "POST";  // enum: GET | POST | PUT | DELETE | NAVIGATE | DOWNLOAD
    public const string MethodPUT = "PUT";  // enum: GET | POST | PUT | DELETE | NAVIGATE | DOWNLOAD
    public const string MethodDELETE = "DELETE";  // enum: GET | POST | PUT | DELETE | NAVIGATE | DOWNLOAD
    public const string MethodNAVIGATE = "NAVIGATE";  // enum: GET | POST | PUT | DELETE | NAVIGATE | DOWNLOAD
    public const string MethodDOWNLOAD = "DOWNLOAD";  // enum: GET | POST | PUT | DELETE | NAVIGATE | DOWNLOAD
}

// 由 contracts/codegen/generate_csharp.py 生成（蓝图阶段 B——契约事实来源——请勿手工编辑）
namespace Aegis.Windows.Contracts.Generated;

public sealed record AuditEventContract(
    string event_id,
    string timestamp,
    string decision,
    string scope,
    string origin,
    string? reason = null,
    string? tab_id = null
);

/// <summary>PY-188（2026-09-26 审计）：AuditEventContract 值域常量——schema enum/const 单源，属性保持基础类型以兼容既有消费方。</summary>
public static class AuditEventContractValues
{
    public const string DecisionAllow = "allow";  // enum: allow | deny | require_confirmation
    public const string DecisionDeny = "deny";  // enum: allow | deny | require_confirmation
    public const string DecisionRequireConfirmation = "require_confirmation";  // enum: allow | deny | require_confirmation
}

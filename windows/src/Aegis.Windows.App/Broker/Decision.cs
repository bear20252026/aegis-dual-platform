namespace Aegis.Windows.Broker;

using System;

/// <summary>阶段 C（蓝图）：类型化安全决策——不再用 bool/空字符串作为安全模型。
/// Decision = Allow(AuthorizedAction) | RequireConfirmation | Deny。</summary>
public abstract record Decision
{
    public sealed record Allow(AuthorizedAction Action) : Decision;
    public sealed record RequireConfirmation(ApprovalRequest Request) : Decision;
    public sealed record Deny(DenyReason Reason) : Decision;
}

/// <summary>审批请求（高风险副作用——原生确认 UI——绑定参数与一次性 nonce）。</summary>
public sealed record ApprovalRequest(
    string Origin,
    string Method,
    string Path,
    string Scope,
    DateTime ExpiresAt,
    string Nonce);

/// <summary>拒绝原因（类型化——fail-closed——审计可追溯）。</summary>
public sealed record DenyReason(string Code, string Detail);

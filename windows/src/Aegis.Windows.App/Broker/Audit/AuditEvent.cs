namespace Aegis.Windows.Broker.Audit;

using System;

/// <summary>阶段 C：脱敏审计事件（蓝图 audit-event schema——不含 token/网页内容/
/// query secret——决策记录可审计——预算/终止开关依据）。</summary>
public sealed record AuditEvent(
    string EventId,
    DateTime Timestamp,
    string Decision,
    string Scope,
    string Origin,
    string? Reason);

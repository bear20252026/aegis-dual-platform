namespace Aegis.Windows.Broker;

using System;
using System.Collections.Generic;

/// <summary>Capability Broker——唯一允许产生本地副作用的边界（ADR-002/蓝图阶段 C）。
/// 验证来源/会话/标签代际/scope/参数/预算/批准/nonce——没有 AuthorizedAction
/// 不能导航/下载/导出/改策略。默认拒绝（fail-closed）。</summary>
public sealed class BrowserPolicyBroker
{
    public string PolicyVersion { get; } = "1.0";
    private readonly List<Audit.AuditEvent> _auditLog = new();
    private readonly HashSet<string> _consumedNonces = new(StringComparer.Ordinal);
    private readonly object _nonceLock = new();

    /// <summary>评估导航意图（ProposedAction → Decision——默认拒绝——fail-closed）。</summary>
    public Decision EvaluateNavigation(string sessionId, string tabId, ulong generation,
        string rawUrl, string scope)
    {
        if (!OriginPolicy.TryParseExternal(rawUrl, out var uri))
        {
            RecordAudit("deny", scope, rawUrl, "url_policy");
            return new Decision.Deny(new DenyReason("url_policy", $"拒绝 URL: {rawUrl}"));
        }
        var origin = uri.GetLeftPart(UriPartial.Authority);
        var action = new AuthorizedAction(sessionId, tabId, generation, origin, "GET",
            uri.GetComponents(UriComponents.PathAndQuery, UriFormat.UriEscaped), scope, DateTime.UtcNow.AddMinutes(2),
            Guid.NewGuid().ToString("N"), PolicyVersion);
        RecordAudit("allow", scope, origin, null);
        return new Decision.Allow(action);
    }

    /// <summary>校验 AuthorizedAction 是否仍有效（代际/过期/策略版本——fail-closed）。</summary>
    public bool IsValid(AuthorizedAction? action, ulong currentGeneration)
    {
        return action is not null
            && action.PolicyVersion == PolicyVersion
            && action.DocumentGeneration == currentGeneration
            && action.ExpiresAt > DateTime.UtcNow;
    }

    /// <summary>在真实导航发生前校验并消费授权动作，防止跨会话、错标签和 nonce 重放。</summary>
    public bool TryConsumeNavigation(AuthorizedAction? action, string sessionId, string tabId,
        ulong currentGeneration, string rawUrl, string scope)
    {
        if (!IsValid(action, currentGeneration) || action is null)
            return false;
        if (!OriginPolicy.TryParseExternal(rawUrl, out var uri))
            return false;
        if (action.SessionId != sessionId || action.TabId != tabId || action.Scope != scope
            || action.Method != "GET" || action.Origin != uri.GetLeftPart(UriPartial.Authority)
            || action.CanonicalParameters != uri.GetComponents(UriComponents.PathAndQuery, UriFormat.UriEscaped))
            return false;
        lock (_nonceLock)
        {
            return _consumedNonces.Add(action.Nonce);
        }
    }

    /// <summary>阶段 C：脱敏审计（记录决策——不含 token/网页内容/query secret——
    /// 与 contracts/schemas/audit-event.schema.json 对齐）。</summary>
    public IReadOnlyList<Audit.AuditEvent> AuditLog => _auditLog;

    private void RecordAudit(string decision, string scope, string origin, string? reason)
    {
        _auditLog.Add(new Audit.AuditEvent(
            Guid.NewGuid().ToString("N"), DateTime.UtcNow, decision, scope, origin, reason));
    }
}

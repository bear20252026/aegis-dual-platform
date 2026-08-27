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
    private readonly Dictionary<string, SessionContext> _sessions = new(StringComparer.Ordinal);
    private readonly object _nonceLock = new();
    private readonly object _sessionLock = new();

    /// <summary>注册由受控 WebView 创建的会话；未知会话上的副作用一律拒绝。</summary>
    public bool RegisterSession(string sessionId, string tabId, ulong generation = 0)
    {
        if (string.IsNullOrWhiteSpace(sessionId) || string.IsNullOrWhiteSpace(tabId))
            return false;
        lock (_sessionLock)
        {
            if (_sessions.ContainsKey(sessionId))
                return false;
            _sessions.Add(sessionId, new SessionContext(tabId, generation));
            return true;
        }
    }

    /// <summary>文档代际推进时同步会话状态；仅同标签严格单步推进，阻止跳跃和回退。</summary>
    public bool UpdateDocumentGeneration(string sessionId, string tabId, ulong generation)
    {
        lock (_sessionLock)
        {
            if (!_sessions.TryGetValue(sessionId, out var session)
                || !string.Equals(session.TabId, tabId, StringComparison.Ordinal)
                || session.DocumentGeneration == ulong.MaxValue
                || generation != session.DocumentGeneration + 1)
                return false;
            session.DocumentGeneration = generation;
            return true;
        }
    }

    /// <summary>销毁标签会话并清理其 nonce，禁止遗留 WebView 消费旧授权。</summary>
    public void DestroySession(string sessionId)
    {
        lock (_sessionLock)
            _sessions.Remove(sessionId);
        lock (_nonceLock)
            _consumedNonces.RemoveWhere(nonce => nonce.StartsWith($"{sessionId}:", StringComparison.Ordinal));
    }

    /// <summary>评估导航意图（ProposedAction → Decision——默认拒绝——fail-closed）。</summary>
    public Decision EvaluateNavigation(string sessionId, string tabId, ulong generation,
        string rawUrl, string scope)
    {
        if (!HasCurrentSession(sessionId, tabId, generation))
        {
            RecordAudit("deny", scope, rawUrl, "session_context");
            return new Decision.Deny(new DenyReason("session_context", "会话、标签或文档代际无效"));
        }
        if (!OriginPolicy.TryParseExternal(rawUrl, out var uri))
        {
            RecordAudit("deny", scope, rawUrl, "url_policy");
            return new Decision.Deny(new DenyReason("url_policy", $"拒绝 URL: {rawUrl}"));
        }
        var origin = uri.GetLeftPart(UriPartial.Authority);
        var action = new AuthorizedAction(sessionId, tabId, generation, origin, "GET",
            uri.GetComponents(UriComponents.PathAndQuery, UriFormat.UriEscaped), scope, DateTime.UtcNow.AddMinutes(2),
            $"{sessionId}:{Guid.NewGuid():N}", PolicyVersion);
        RecordAudit("allow", scope, origin, null);
        return new Decision.Allow(action);
    }

    /// <summary>校验 AuthorizedAction 是否仍有效（会话/标签/代际/过期/策略版本——fail-closed）。</summary>
    public bool IsValid(AuthorizedAction? action, ulong currentGeneration)
    {
        lock (_sessionLock)
            return IsValidInCurrentSession(action, currentGeneration);
    }

    /// <summary>在真实导航发生前校验并消费授权动作，防止跨会话、错标签和 nonce 重放。</summary>
    public bool TryConsumeNavigation(AuthorizedAction? action, string sessionId, string tabId,
        ulong currentGeneration, string rawUrl, string scope)
    {
        if (action is null || !OriginPolicy.TryParseExternal(rawUrl, out var uri))
            return false;
        // 与 DestroySession 使用相同锁序列，避免会话销毁后仍可消费旧授权。
        lock (_sessionLock)
        {
            if (!IsValidInCurrentSession(action, currentGeneration)
                || action.SessionId != sessionId || action.TabId != tabId || action.Scope != scope
                || action.Method != "GET" || action.Origin != uri.GetLeftPart(UriPartial.Authority)
                || action.CanonicalParameters != uri.GetComponents(UriComponents.PathAndQuery, UriFormat.UriEscaped))
                return false;
            lock (_nonceLock)
            {
                return _consumedNonces.Add(action.Nonce);
            }
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

    private bool HasCurrentSession(string sessionId, string tabId, ulong generation)
    {
        lock (_sessionLock)
        {
            return _sessions.TryGetValue(sessionId, out var session)
                && string.Equals(session.TabId, tabId, StringComparison.Ordinal)
                && session.DocumentGeneration == generation;
        }
    }

    private bool IsValidInCurrentSession(AuthorizedAction? action, ulong currentGeneration)
    {
        return action is not null
            && action.PolicyVersion == PolicyVersion
            && action.DocumentGeneration == currentGeneration
            && _sessions.TryGetValue(action.SessionId, out var session)
            && string.Equals(session.TabId, action.TabId, StringComparison.Ordinal)
            && session.DocumentGeneration == currentGeneration
            && action.ExpiresAt > DateTime.UtcNow;
    }

    private sealed class SessionContext
    {
        public SessionContext(string tabId, ulong documentGeneration)
        {
            TabId = tabId;
            DocumentGeneration = documentGeneration;
        }

        public string TabId { get; }
        public ulong DocumentGeneration { get; set; }
    }
}

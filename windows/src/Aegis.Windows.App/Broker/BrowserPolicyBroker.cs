namespace Aegis.Windows.Broker;

using System;
using System.Collections.Generic;
using Aegis.Windows.Core.Security;

/// <summary>Capability Broker——唯一允许产生本地副作用的边界（ADR-002/蓝图阶段 C）。
/// 验证来源/会话/标签代际/scope/参数/预算/批准/nonce——没有 AuthorizedAction
/// 不能导航/下载/导出/改策略。默认拒绝（fail-closed）。</summary>
public sealed class BrowserPolicyBroker : IDisposable
{
    public string PolicyVersion { get; } = "1.0";
    // 与 Rust 侧 broker.rs 的 MAX_CONSUMED_NONCES 保持对等：达到上限即 fail-closed 拒绝，
    // 绝不淘汰旧 nonce（以免削弱一次性/重放保护）。
    private const int MaxConsumedNonces = 50_000;
    private readonly List<Audit.AuditEvent> _auditLog = new();
    private readonly HashSet<string> _consumedNonces = new(StringComparer.Ordinal);
    private readonly Dictionary<string, SessionContext> _sessions = new(StringComparer.Ordinal);
    private readonly object _nonceLock = new();
    private readonly object _sessionLock = new();
    private readonly Func<NativePolicyCoreGateResult> _nativePolicyCoreGate;
    private readonly NativePolicyCoreBridge? _nativePolicyCoreBridge;
    private readonly bool _nativePolicyCoreRequired;
    // M1-T2（ADR-009）：威胁黑名单（可变引用——订阅刷新后整体替换快照）。
    // 策略数据归 broker（ADR-002：broker 唯一策略裁决点），HostWebView 只消费。
    private IBlockedHosts _blockedHosts;
    private bool _disposed;
    // M4-a（ADR-009 审计遗留清零）：KillSwitch 此前全仓零调用点（审计实证）。
    // broker 持有单例，导航/下载/确认全链强制检查；Chrome 经属性暴露触发。
    public KillSwitch KillSwitch { get; } = new();

    public BrowserPolicyBroker(
        Func<NativePolicyCoreGateResult>? nativePolicyCoreGate = null,
        NativePolicyCoreBridge? nativePolicyCoreBridge = null,
        IBlockedHosts? blockedHosts = null)
    {
        _nativePolicyCoreGate = nativePolicyCoreGate ?? NativePolicyCoreGate.ProbeFromEnvironment;
        _nativePolicyCoreRequired = NativePolicyCoreGate.IsRequired;
        if (_nativePolicyCoreRequired)
            NativePolicyCoreBridge.TryCreate(PolicyVersion, NativePolicyCoreGate.LibraryPath, out _nativePolicyCoreBridge);
        else
            _nativePolicyCoreBridge = nativePolicyCoreBridge;
        _blockedHosts = blockedHosts ?? NoBlockedHosts.Instance;
    }

    /// <summary>替换黑名单快照（订阅源后台刷新完成时调用——原子换引用）。</summary>
    public void UpdateBlockedHosts(IBlockedHosts blockedHosts) =>
        _blockedHosts = blockedHosts ?? NoBlockedHosts.Instance;

    /// <summary>子资源层黑名单查询（HostWebView WebResourceRequested 真拦截——
    /// 命中返回 403 stub。导航层的同名单独在 EvaluateNavigation 内强制）。</summary>
    public bool IsHostBlocked(string host) => _blockedHosts.IsBlocked(host);

    /// <summary>M3 下载授权（ADR-009：下载策略的原生兑现）：会话/标签/代际
    /// 校验通过后登记允许下载（危险扩展已由调用方完成用户确认）。
    /// Rust 契约当前无 download scope——授权在托管 broker 完成（审计留痕），
    /// 未来契约扩展 download 动作时迁移至原生核心托管。</summary>
    public bool AllowDownload(string sessionId, string tabId, string origin,
        string fileName, bool userConfirmed)
    {
        if (KillSwitch.IsEngaged)
        {
            RecordAudit("deny", "download", origin, "kill_switch_engaged");
            return false;
        }
        lock (_sessionLock)
        {
            if (_disposed || !_sessions.TryGetValue(sessionId, out var session)
                || session.TabId != tabId)
            {
                RecordAudit("deny", "download", origin, "download_session_context");
                return false;
            }
        }
        RecordAudit("allow", "download", origin,
            userConfirmed ? "user_confirmed" : null);
        SecurityLog.Write($"[download] 允许下载: {fileName}（来源 {origin}，"
                          + (userConfirmed ? "用户已确认危险扩展" : "常规下载") + "）");
        return true;
    }

    /// <summary>注册由受控 WebView 创建的会话；未知会话上的副作用一律拒绝。</summary>
    public bool RegisterSession(string sessionId, string tabId, ulong generation = 0)
    {
        if (string.IsNullOrWhiteSpace(sessionId) || string.IsNullOrWhiteSpace(tabId))
            return false;
        lock (_sessionLock)
        {
            if (_sessions.ContainsKey(sessionId))
                return false;
            if (_nativePolicyCoreRequired && (_nativePolicyCoreBridge is null
                || !_nativePolicyCoreBridge.CreateSession(sessionId, tabId, generation, 120)))
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
            if (_nativePolicyCoreRequired && (_nativePolicyCoreBridge is null
                || !_nativePolicyCoreBridge.AdvanceDocumentGeneration(sessionId, tabId, generation)))
                return false;
            session.DocumentGeneration = generation;
            return true;
        }
    }

    /// <summary>销毁标签会话并清理其 nonce，禁止遗留 WebView 消费旧授权。</summary>
    public void DestroySession(string sessionId)
    {
        if (_nativePolicyCoreRequired)
            _nativePolicyCoreBridge?.DestroySession(sessionId);
        lock (_sessionLock)
            _sessions.Remove(sessionId);
        lock (_nonceLock)
            _consumedNonces.RemoveWhere(nonce => nonce.StartsWith($"{sessionId}:", StringComparison.Ordinal));
    }

    /// <summary>评估导航意图（ProposedAction → Decision——默认拒绝——fail-closed）。</summary>
    public Decision EvaluateNavigation(string sessionId, string tabId, ulong generation,
        string rawUrl, string scope)
    {
        if (KillSwitch.IsEngaged)
        {
            RecordAudit("deny", scope, rawUrl, "kill_switch_engaged");
            return new Decision.Deny(new DenyReason("kill_switch_engaged", "紧急终止开关已触发——全部导航冻结"));
        }
        if (!AllowsNavigationUnderNativePolicyRequirement(scope, rawUrl, out var nativeDenied))
            return nativeDenied;
        if (_nativePolicyCoreRequired)
        {
            if (_nativePolicyCoreBridge is null)
                return NativeBridgeDenied(scope, "native_policy_core_bridge_unavailable");
            var nativeDecision = _nativePolicyCoreBridge.EvaluateNavigation(sessionId, tabId, generation, rawUrl, scope);
            RecordNativeDecision(scope, nativeDecision);
            return nativeDecision;
        }
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
        // M1-T2：威胁黑名单门禁（host 精确+子域后缀匹配；命中 fail-closed 留痕）
        if (_blockedHosts.IsBlocked(uri.Host))
        {
            RecordAudit("deny", scope, rawUrl, "threat_blocklist");
            SecurityLog.Write($"[threat] 导航拒绝（黑名单命中）: {rawUrl}");
            return new Decision.Deny(new DenyReason("threat_blocklist", "该地址在恶意站点黑名单中，已被拦截。"));
        }
        var origin = uri.GetLeftPart(UriPartial.Authority);
        var action = new AuthorizedAction(sessionId, tabId, generation, origin, "GET",
            uri.GetComponents(UriComponents.PathAndQuery, UriFormat.UriEscaped), scope, DateTime.UtcNow.AddMinutes(2),
            $"{sessionId}:{Guid.NewGuid():N}", PolicyVersion);
        RecordAudit("allow", scope, origin, null);
        return new Decision.Allow(action);
    }

    /// <summary>
    /// 登记需要显式用户确认的导航。确认状态与可兑换授权仅存在于 Rust 核心；
    /// 默认托管路径不得自行重建或签发确认授权。
    /// </summary>
    public Decision RequestNavigationConfirmation(string sessionId, string tabId, ulong generation,
        string rawUrl, string scope)
    {
        if (!AllowsNavigationUnderNativePolicyRequirement(scope, rawUrl, out var nativeDenied))
            return nativeDenied;
        if (!_nativePolicyCoreRequired || _nativePolicyCoreBridge is null)
            return NativeBridgeDenied(scope, "native_confirmation_core_required");
        var decision = _nativePolicyCoreBridge.RequestNavigationConfirmation(sessionId, tabId, generation, rawUrl, scope);
        RecordNativeDecision(scope, decision);
        return decision;
    }

    /// <summary>仅将原生核心已登记的确认请求兑换为其原始绑定授权；异常和不匹配均拒绝。</summary>
    public Decision ApproveNavigationConfirmation(ApprovalRequest request, string rawUrl, string scope)
    {
        if (KillSwitch.IsEngaged)
        {
            RecordAudit("deny", request.Scope, request.Origin, "kill_switch_engaged");
            return new Decision.Deny(new DenyReason("kill_switch_engaged", "紧急终止开关已触发——批准链冻结"));
        }
        if (!AllowsNavigationUnderNativePolicyRequirement(scope, rawUrl, out var nativeDenied))
            return nativeDenied;
        if (!_nativePolicyCoreRequired || _nativePolicyCoreBridge is null)
            return NativeBridgeDenied(scope, "native_confirmation_core_required");
        var decision = _nativePolicyCoreBridge.ApproveNavigationConfirmation(request, rawUrl, scope);
        RecordNativeDecision(scope, decision);
        return decision;
    }

    /// <summary>显式拒绝确认请求；未知 nonce、桥接故障或非原生模式均失败闭合。</summary>
    public bool RejectNavigationConfirmation(ApprovalRequest request)
    {
        if (!_nativePolicyCoreGate().AllowsPlatformBroker
            || !_nativePolicyCoreRequired
            || _nativePolicyCoreBridge is null
            || !_nativePolicyCoreBridge.RejectNavigationConfirmation(request))
            return false;
        RecordAudit("deny", request.Scope, request.Origin, "confirmation_rejected");
        return true;
    }

    /// <summary>
    /// 下载请求默认拒绝（审计 C1——全面审计 2026-09-04）：当前契约没有
    /// 下载授权动作，DownloadStarting 不得绕过 broker 直接放行；调用方
    /// （HostWebView）据此 Handled 抑制原生下载流程，本方法仅留痕。
    /// 与「没有 AuthorizedAction 不能导航/下载/导出」的类声明对齐。
    /// </summary>
    public void DenyDownload(string sessionId, string tabId, string origin)
    {
        RecordAudit("deny", "download", origin, "download_not_authorized");
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
        if (!_nativePolicyCoreGate().AllowsPlatformBroker)
            return false;
        if (action is null)
            return false;
        if (_nativePolicyCoreRequired)
        {
            if (_nativePolicyCoreBridge is null)
                return false;
            lock (_sessionLock)
            {
                if (!IsValidInCurrentSession(action, currentGeneration)
                    || action.SessionId != sessionId || action.TabId != tabId)
                    return false;
                if (!_nativePolicyCoreBridge.TryConsumeNavigation(action, rawUrl, scope))
                    return false;
                // 原生 nonce 是裸的（无前缀），须加 sessionId 前缀与托管路径一致，
                // 否则 DestroySession 的 RemoveWhere("sessionId:") 清不掉 →
                // _consumedNonces 永不清理，满 MAX 后 TryRecordConsumedNonce 恒
                // false → 该 broker 全站导航永久锁死（自 DoS，审计发现 F）。
                return TryRecordConsumedNonce($"{sessionId}:{action.Nonce}");
            }
        }
        if (!OriginPolicy.TryParseExternal(rawUrl, out var uri))
            return false;
        // 与 DestroySession 使用相同锁序列，避免会话销毁后仍可消费旧授权。
        lock (_sessionLock)
        {
            if (!IsValidInCurrentSession(action, currentGeneration)
                || action.SessionId != sessionId || action.TabId != tabId || action.Scope != scope
                || action.Method != "GET" || action.Origin != uri.GetLeftPart(UriPartial.Authority)
                || action.CanonicalParameters != uri.GetComponents(UriComponents.PathAndQuery, UriFormat.UriEscaped))
                return false;
            return TryRecordConsumedNonce(action.Nonce);
        }
    }

    /// <summary>阶段 C：脱敏审计（记录决策——不含 token/网页内容/query secret——
    /// 与 contracts/schemas/audit-event.schema.json 对齐）。</summary>
    public IReadOnlyList<Audit.AuditEvent> AuditLog => _auditLog;

    public void Dispose()
    {
        if (_disposed)
            return;
        _disposed = true;
        lock (_sessionLock)
            _sessions.Clear();
        lock (_nonceLock)
            _consumedNonces.Clear();
        _nativePolicyCoreBridge?.Dispose();
        GC.SuppressFinalize(this);
    }

    private void RecordAudit(string decision, string scope, string origin, string? reason)
    {
        _auditLog.Add(new Audit.AuditEvent(
            Guid.NewGuid().ToString("N"), DateTime.UtcNow, decision, scope, origin, reason));
    }

    /// <summary>记录已消费 nonce；达上限即 fail-closed 拒绝（与 Rust 侧 broker.rs 对等）。
    /// 不淘汰旧 nonce，避免削弱一次性/重放保护。</summary>
    private bool TryRecordConsumedNonce(string nonce)
    {
        lock (_nonceLock)
        {
            if (_consumedNonces.Count >= MaxConsumedNonces)
                return false;
            return _consumedNonces.Add(nonce);
        }
    }

    private bool AllowsNavigationUnderNativePolicyRequirement(
        string scope,
        string rawUrl,
        out Decision.Deny nativeDenied)
    {
        var result = _nativePolicyCoreGate();
        if (result.AllowsPlatformBroker)
        {
            nativeDenied = null!;
            return true;
        }
        var code = result.DenialCode ?? "native_policy_core_unavailable";
        RecordAudit("deny", scope, "native-policy-core", code);
        nativeDenied = new Decision.Deny(new DenyReason(code, "已启用的原生策略核心不可用或不兼容"));
        return false;
    }

    private Decision.Deny NativeBridgeDenied(string scope, string code)
    {
        RecordAudit("deny", scope, "native-policy-core", code);
        return new Decision.Deny(new DenyReason(code, "已启用的原生策略核心桥接不可用"));
    }

    private void RecordNativeDecision(string scope, Decision decision)
    {
        switch (decision)
        {
            case Decision.Allow allow:
                RecordAudit("allow", scope, allow.Action.Origin, null);
                break;
            case Decision.Deny deny:
                RecordAudit("deny", scope, "native-policy-core", deny.Reason.Code);
                break;
            case Decision.RequireConfirmation confirmation:
                RecordAudit("require_confirmation", confirmation.Request.Scope, confirmation.Request.Origin, null);
                break;
        }
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

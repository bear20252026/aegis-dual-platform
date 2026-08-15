namespace Aegis.Windows.Broker.Approval;

using System;
using System.Collections.Generic;

/// <summary>阶段 C（蓝图 Broker/Approval）：审批管理——消费 Decision.
/// RequireConfirmation——nonce 一次性消费/过期/参数绑定（approval schema——
/// approvals-replay-and-expiry 向量：重放/过期拒绝）。原生确认 UI 经
/// Chrome 展示目标 Origin/方法/路径/scope/过期——批准令牌绑定参数与一次性 nonce。</summary>
public sealed class ApprovalManager
{
    private readonly Dictionary<string, AuthorizedAction> _issued = new();
    private readonly HashSet<string> _consumedNonces = new();

    /// <summary>登记审批（ApprovalRequest——高风险副作用——原生确认前）。</summary>
    public string Register(ApprovalRequest request)
    {
        if (_consumedNonces.Contains(request.Nonce))
            throw new InvalidOperationException("nonce 已使用（重放拒绝——approvals-replay 向量）");
        _issued[request.Nonce] = new AuthorizedAction("session", "tab", 0, request.Origin,
            request.Method, request.Path, request.Scope, request.ExpiresAt, request.Nonce, "1.0");
        return request.Nonce;
    }

    /// <summary>消费批准（一次性 nonce——重放拒绝——过期拒绝——fail-closed）。</summary>
    public AuthorizedAction? Consume(string nonce)
    {
        if (!_issued.TryGetValue(nonce, out var action))
            return null;
        _issued.Remove(nonce);
        _consumedNonces.Add(nonce);  // 一次性消费（重放拒绝）
        if (action.ExpiresAt <= DateTime.UtcNow)
            return null;  // 过期拒绝（approvals-expiry 向量）
        return action;
    }
}

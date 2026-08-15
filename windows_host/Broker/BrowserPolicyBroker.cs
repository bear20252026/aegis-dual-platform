namespace Aegis.Host.Broker;

using System;

/// <summary>Capability Broker——唯一允许产生本地副作用的边界（专家最终路线）。
/// 验证来源/会话/标签代际/scope/参数/预算/批准/nonce——没有 AuthorizedAction
/// 不能导航/下载/导出/改策略。默认拒绝（fail-closed）。</summary>
public sealed class BrowserPolicyBroker
{
    public string PolicyVersion { get; } = "1.0";

    /// <summary>评估导航意图（ProposedAction → Decision——默认拒绝——fail-closed）。</summary>
    public Decision EvaluateNavigation(string sessionId, string tabId, ulong generation,
        string rawUrl, string scope)
    {
        if (!OriginPolicy.TryParseExternal(rawUrl, out var uri))
            return new Decision.Deny(new DenyReason("url_policy", $"拒绝 URL: {rawUrl}"));
        var origin = $"{uri.Scheme}://{uri.Host}";
        var action = new AuthorizedAction(sessionId, tabId, generation, origin, "GET",
            uri.PathAndQuery, scope, DateTime.UtcNow.AddMinutes(2),
            Guid.NewGuid().ToString("N"), PolicyVersion);
        return new Decision.Allow(action);
    }

    /// <summary>校验 AuthorizedAction 是否仍有效（代际/过期/策略版本——fail-closed）。
    /// 任一字段变化使批准失效（专家最终路线）。</summary>
    public bool IsValid(AuthorizedAction? action, ulong currentGeneration)
    {
        return action is not null
            && action.PolicyVersion == PolicyVersion
            && action.DocumentGeneration == currentGeneration
            && action.ExpiresAt > DateTime.UtcNow;
    }
}

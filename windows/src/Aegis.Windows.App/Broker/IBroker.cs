namespace Aegis.Windows.Broker;

using System;

/// <summary>Broker 能力面（ADR-002「唯一策略裁决边界」）。HostWebView 只依赖此
/// 接口、不再引用具体 sealed 类——导航/会话/下载/威胁的全套授权可从真实
/// BrowserPolicyBroker 解耦，便于以假实现做导航策略单测。方法即该边界对外
/// 暴露的最小授权面（全部 fail-closed）。</summary>
public interface IBroker : IDisposable
{
    /// <summary>注册由受控 WebView 创建的会话；未知会话上的副作用一律拒绝。</summary>
    bool RegisterSession(string sessionId, string tabId, ulong generation = 0);

    /// <summary>销毁标签会话并清理其 nonce，禁止遗留 WebView 消费旧授权。</summary>
    void DestroySession(string sessionId);

    /// <summary>文档代际推进时同步会话状态；仅同标签严格单步推进，阻止跳跃和回退。</summary>
    bool UpdateDocumentGeneration(string sessionId, string tabId, ulong generation);

    /// <summary>评估导航意图（ProposedAction → Decision——默认拒绝——fail-closed）。</summary>
    Decision EvaluateNavigation(string sessionId, string tabId, ulong generation, string rawUrl, string scope);

    /// <summary>登记需要显式用户确认的导航。确认状态与可兑换授权仅存在于原生核心。</summary>
    Decision RequestNavigationConfirmation(string sessionId, string tabId, ulong generation, string rawUrl, string scope);

    /// <summary>将原生核心已登记的确认请求兑换为其原始绑定授权；异常和不匹配均拒绝。</summary>
    Decision ApproveNavigationConfirmation(ApprovalRequest request, string rawUrl, string scope);

    /// <summary>显式拒绝确认请求；未知 nonce、桥接故障或非原生模式均失败闭合。</summary>
    bool RejectNavigationConfirmation(ApprovalRequest request);

    /// <summary>在真实导航发生前校验并消费授权动作，防止跨会话、错标签和 nonce 重放。</summary>
    bool TryConsumeNavigation(
        AuthorizedAction? action,
        string sessionId,
        string tabId,
        ulong currentGeneration,
        string rawUrl,
        string scope);

    /// <summary>下载授权（危险扩展已由调用方完成用户确认）。</summary>
    bool AllowDownload(string sessionId, string tabId, string origin, string fileName, bool userConfirmed);

    /// <summary>下载请求默认拒绝——留痕。</summary>
    void DenyDownload(string sessionId, string tabId, string origin);

    /// <summary>子资源层黑名单查询（HostWebView WebResourceRequested 真拦截）。</summary>
    bool IsHostBlocked(string host);
}
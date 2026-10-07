namespace Aegis.Windows.WebView;

using System;
using Aegis.Windows.Broker;
using Aegis.Windows.Chrome.Ntp;
using Aegis.Windows.Core.Security;
using Microsoft.Web.WebView2.Core;

/// <summary>HostWebView 的子资源守卫分片（第八轮 ⑤，用户 2026-10-07 定稿）：
/// WebResourceRequested 的拦截面 + 「策略链异常 ⇒ 单条请求失败闭合」的判定核。
/// 拆出既给 ⑤ 留出行数额度（HostWebView.cs 在 593 行零余量基线上），也与
/// HostWebView.NavigationGuards.cs / HostWebView.TrackerBlocks.cs 同构。</summary>
public sealed partial class HostWebView
{
    /// <summary>⑤ 新增审计码：子资源策略链自身异常 ⇒ 这一条请求被回绝。
    /// 与其余拒绝码同名单源口径（拒绝码词表入 contracts 属 B9 余量）。</summary>
    internal const string SubresourcePolicyErrorCode = "subresource_policy_error";

    /// <summary>子资源链的处置：null = 放行原始请求；非 null = 给**这一条**请求
    /// 回一份错误响应。之所以不是 `e.Cancel`：
    /// `CoreWebView2WebResourceRequestedEventArgs` 没有 Cancel（SDK 实测成员只有
    /// Request/Response/ResourceContext/GetDeferral/RequestedSourceKind），
    /// 「取消单请求」在本事件里的唯一手段就是填 Response——403 与策略拒绝同形态。</summary>
    internal readonly record struct WebResourceDenial(int Status, string ReasonPhrase);

    /// <summary>DNT 注入 + 子资源真拦截（WebResourceRequested 原生返回 403——
    /// pywebview 时代只能标记不能拦截的缺口，原生 API 直接闭合）。拦截面两条：
    /// 威胁黑名单，以及保留地址边界（R7-CS1-01——链路本地/云元数据/组播/保留段，
    /// 与导航层同一谓词单源 ReservedAddressBoundary）。</summary>
    private void OnWebResourceRequested(CoreWebView2 webView, CoreWebView2WebResourceRequestedEventArgs e)
    {
        // ⑤（第八轮，用户 2026-10-07 定稿）：CS-310 的取舍原来只留了一半——
        // 「单请求异常不影响其他请求」是对的，但「异常时保持原始响应路径」等于
        // 策略层自己出 bug 就默认放行，除了一行日志零痕迹。现改为：异常按该单条
        // 请求失败闭合（403 + 审计码 subresource_policy_error），其余请求不受影响。
        // 不整页 403、不改导航语义（那是待裁决 1 的域，本批不越界）。
        var denial = SubresourceDenialFailClosed(
            () => EvaluateSubresource(webView, e),
            () => RedactUrl(e.Request.Uri));
        if (denial is null)
            return;
        try
        {
            e.Response = webView.Environment.CreateWebResourceResponse(
                null, denial.Value.Status, denial.Value.ReasonPhrase, "Content-Type: text/plain");
        }
        catch (Exception ex)
        {
            // 连错误响应都造不出（COM 已退休/环境已销毁）：这一条只能回到默认路径。
            // 如实留痕而不是假装拦住，但绝不把异常抛回事件 shim（那会炸掉进程）。
            TryWriteSecurityLog(
                $"[webresource] 拒绝响应构造失败，该请求保留默认路径: {ex.GetType().Name}: {ex.Message}");
        }
    }

    /// <summary>策略链求值（黑名单 → 保留地址边界 → 跟踪防护分级）。
    /// 返回 null 即放行；两条拒绝出口的日志文案与拆分前逐字相同。</summary>
    private WebResourceDenial? EvaluateSubresource(
        CoreWebView2 webView, CoreWebView2WebResourceRequestedEventArgs e)
    {
        e.Request.Headers.SetHeader("DNT", "1");
        if (!Uri.TryCreate(e.Request.Uri, UriKind.Absolute, out var uri)
            || (uri.Scheme != Uri.UriSchemeHttp && uri.Scheme != Uri.UriSchemeHttps))
            return null;
        // 威胁黑名单 + 保留地址边界（远程页把元数据/链路本地目标改写成
        // <img>/fetch 时，导航层的边界管不到这里——子资源层必须自己判一次）
        var deniedBy = _broker.IsHostBlocked(uri.Host) ? "黑名单"
            : ReservedAddressBoundary.DeniesRaw(e.Request.Uri) ? "保留地址边界" : null;
        if (deniedBy is not null)
        {
            SecurityLog.Write($"[threat] 子资源拦截（{deniedBy}命中）: {RedactUrl(e.Request.Uri)}");
            return new WebResourceDenial(403, "Blocked");
        }
        // 跟踪防护分级（P1——对齐 Edge 基础/均衡/严格）
        var level = _privacy.ProtectionLevel;
        if (level <= 0)
            return null;
        var pageHost = ResolvePageHost(webView.Source);
        // 受信虚拟主机（NTP/GeoGebra）子资源：黑名单仍拦截（上文已处理），
        // 但跳过第三方/跟踪判定——严格模式 + 跨站导航过渡期会把自带页的
        // JS/WASM 误判为第三方而 403（pageHost 仍是旧的远程 host）。
        var isVirtualHostAsset = NtpAssets.IsVirtualHostUrl(e.Request.Uri);
        var isTracker = Core.Privacy.TrackerList.IsTracker(uri.Host);
        var blockContext = e.ResourceContext is CoreWebView2WebResourceContext.Script
            or CoreWebView2WebResourceContext.Fetch
            or CoreWebView2WebResourceContext.Image;
        if (isTracker
            || (level >= 2 && blockContext && !isVirtualHostAsset
                && !Core.Privacy.TrackerList.IsSameSite(uri.Host, pageHost)))
        {
            RecordTrackerBlock(uri, level, e.ResourceContext);
            return new WebResourceDenial(403, "Blocked");
        }
        return null;
    }

    /// <summary>⑤ 的判定核：求值期任何抛出都按「该单条请求失败闭合」处置。
    /// 提 internal 纯函数与 `IsAuthorizedFailClosed` 同因——handler 本体要 COM
    /// 对象，没有这层就没有可在常跑门禁里断言的判定面。URL 收 `Func<string>`
    /// 而不是字符串：取 URL 本身也可能抛（`e.Request` 已退休），那不该成为
    /// 「连回绝都做不到」的理由。</summary>
    internal static WebResourceDenial? SubresourceDenialFailClosed(
        Func<WebResourceDenial?> evaluate, Func<string> urlForLog)
    {
        try
        {
            return evaluate();
        }
        catch (Exception ex)
        {
            TryWriteSecurityLog(
                $"[webresource] 策略链异常——按单条请求失败闭合回绝: {ex.GetType().Name}: {ex.Message} url={ReadOrPlaceholder(urlForLog)} code={SubresourcePolicyErrorCode}");
            return new WebResourceDenial(403, "Blocked");
        }
    }

    private static string ReadOrPlaceholder(Func<string> read)
    {
        try
        {
            return read();
        }
        catch (Exception)
        {
            return "(URL 不可读)";
        }
    }

    /// <summary>留痕面自己不许抛——原 CS-310 内层 try 同因：日志不可用不能变成
    /// 把异常上抛回事件 shim（那会炸进程）的理由。</summary>
    private static void TryWriteSecurityLog(string line)
    {
        try
        {
            SecurityLog.Write(line);
        }
        catch (Exception)
        {
            // 尽力留痕即止
        }
    }
}

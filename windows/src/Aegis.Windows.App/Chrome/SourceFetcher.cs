namespace Aegis.Windows.Chrome;

using System;
using System.Net.Http;
using System.Threading.Tasks;
using Aegis.Windows.Core.Security;

/// <summary>源码查看器（Ctrl+U）的带外抓取编排（CS-377 拆分后的独立判定体）。
///
/// 修的形态（R9-B33，第九轮队列 Q23）：此前这里是一个默认配置的
/// <see cref="HttpClient"/>——**默认跟随重定向**，且把整个响应体先读进内存再比上限。
/// 两处都不是安全判断，只是「没人想过」：
/// • 页面里一个 `302 → http://169.254.169.254/...` 就会把云元数据内容当成「网页源码」
///   摆在窗口里给被诱导的用户看；顶层导航会取消这条跳转，带外抓取不会。
/// • 无 Content-Length 的大响应（或 gzip 后仍然巨大的流）先完整进内存才报「超过 5MB」。
///
/// 现在的规则：重定向**手动逐跳**（上限 <see cref="MaxRedirectHops"/>），每一跳都过
/// <see cref="HttpFetchGuard.RedirectProblem"/>；协议不得离开 http/https，落点不得进保留地址。
/// 首跳不判保留地址——那是用户自己打开的地址，2026-10-04 的裁决要求本机/内网可打开；
/// 重定向目标不是用户选的，所以它不享有那条豁免。响应体走有界读取。</summary>
internal static class SourceFetcher
{
    /// <summary>重定向跳数上限——与威胁订阅源同值（那边 `MaxAutomaticRedirections = 3`），
    /// 刻意不写成「无限跟随」。</summary>
    internal const int MaxRedirectHops = 3;

    /// <summary>[Ok]=假时 [Reason] 必非空；[Reason] 是要给用户看的短句，不是异常堆栈。</summary>
    internal readonly record struct Outcome(bool Ok, string? Text, string? Reason);

    private static Outcome Fail(string reason) => new(false, null, reason);

    internal static async Task<Outcome> FetchAsync(HttpClient client, string url, int maxBytes)
    {
        var current = url;
        for (var hop = 0; ; hop++)
        {
            if (!Uri.TryCreate(current, UriKind.Absolute, out var uri))
                return Fail("地址无法解析为绝对 URL");
            // 首跳只判协议；后续每一跳判协议 + 保留地址（见类型注释的裁决边界）
            if (HttpFetchGuard.RedirectProblem(uri, isFirstHop: hop == 0) is { } problem)
                return Fail(problem);

            // ResponseHeadersRead 是这条链上真正的「不整包进内存」开关：默认的
            // ResponseContentRead 会在 GetAsync 返回前把响应体全部缓冲，那样下面的
            // 有界读取就只是「缓冲完再量一遍」——CS-232 想挡的无界分配仍然成立。
            using var response = await client.GetAsync(uri, HttpCompletionOption.ResponseHeadersRead);

            if ((int)response.StatusCode is >= 300 and <= 399)
            {
                if (hop >= MaxRedirectHops)
                    return Fail($"重定向超过 {MaxRedirectHops} 跳上限");
                if (response.Headers.Location is not { } location)
                    return Fail("重定向响应缺少 Location 头");
                // 相对 Location 基于**当前这一跳**的地址解析（不是基于最初地址）
                current = new Uri(uri, location).ToString();
                continue;
            }

            if (!response.IsSuccessStatusCode)
                return Fail($"远端返回 {(int)response.StatusCode}");

            var bytes = await HttpFetchGuard.ReadBoundedAsync(response, maxBytes);
            if (bytes is null)
                return Fail($"源码超过 {maxBytes / (1024 * 1024)}MB 上限");
            return new Outcome(true, System.Text.Encoding.UTF8.GetString(bytes), null);
        }
    }
}

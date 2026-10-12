namespace Aegis.Windows.Core.Security;

using System;
using System.IO;
using System.Net.Http;
using System.Threading.Tasks;

/// <summary>带外抓取（out-of-band fetch）的两条共用护栏：有界响应体读取与重定向落点判定。
///
/// 为什么要单源（R9-B33，第九轮队列 Q23/Q9 同批）：这两条规则此前各自长在
/// `ThreatFeed.FetchAndStore` 私有方法里，第二条抓取路径（源码查看器）出现时最可能的
/// 走法就是**再抄一份**——本仓对「第二个 URL 解析器 / 第二份判定」的排斥是同一条纪律。
///
/// 护栏本体：
/// • <see cref="ReadBoundedAsync"/>：先信 Content-Length，再按块读并在超过上限时立刻停手，
///   **超大响应绝不先整包进内存**（`ReadAsByteArrayAsync()` 后长度比较＝先 OOM 再判定）。
/// • <see cref="RedirectProblem"/>：重定向落点仍须在 http/https 内，且不得落进保留地址
///   （169.254/16 链路本地含云元数据端点）。**首跳不判**：首跳目标是用户自己打开的地址，
///   2026-10-04 的裁决是「本机与内网必须能打开」；重定向目标不是用户选的，所以由页面说话。
///   这组谓词与顶层导航/授权消费/子资源/下载四处同源，都走
///   <see cref="Broker.ReservedAddressBoundary"/>。</summary>
internal static class HttpFetchGuard
{
    /// <summary>读满上限后再多读一块就判定失败——返回 null 表示「超限」，调用方给原因。
    /// 两条历史口径随实现一起搬过来（不是装饰，是防回退）：
    /// • CS-132：超限用 null 哨兵表达，此前 `new byte[max + 1]` 分配 5MB 只为说一个比特；
    /// • CS-232：Content-Length 缺失时按上限**截断**——此前先全量读进内存再检查，
    ///   被劫持的源可以借此触发无界内存分配。</summary>
    internal static async Task<byte[]?> ReadBoundedAsync(HttpResponseMessage response, long maxBytes)
    {
        if (response.Content.Headers.ContentLength is long declared && declared > maxBytes)
            return null;
        await using var stream = await response.Content.ReadAsStreamAsync();
        using var buffer = new MemoryStream();
        var chunk = new byte[64 * 1024];
        while (buffer.Length <= maxBytes)
        {
            var read = await stream.ReadAsync(chunk, 0, chunk.Length);
            if (read <= 0)
                break;
            buffer.Write(chunk, 0, read);
        }
        return buffer.Length > maxBytes ? null : buffer.ToArray();
    }

    /// <summary>重定向落点判定：null＝可以跟；否则返回拒绝原因（进用户可见反馈与日志）。
    /// [isFirstHop] 为真时只判协议，不判保留地址（见类型注释里的裁决边界）。</summary>
    internal static string? RedirectProblem(Uri? target, bool isFirstHop)
    {
        if (target is null)
            return "重定向目标无法解析为绝对地址";
        if (!string.Equals(target.Scheme, Uri.UriSchemeHttp, StringComparison.OrdinalIgnoreCase)
            && !string.Equals(target.Scheme, Uri.UriSchemeHttps, StringComparison.OrdinalIgnoreCase))
            return $"抓取被重定向到非 http/https 协议（{target.Scheme}）——拒绝";
        if (!isFirstHop && Broker.ReservedAddressBoundary.Denies(target))
            return "重定向落在保留地址（链路本地/云元数据）——拒绝";
        return null;
    }
}

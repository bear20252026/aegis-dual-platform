namespace Aegis.Windows.Core.Privacy;

using System;
using System.Collections.Generic;
using System.Linq;

/// <summary>跟踪防护分级（对齐 Edge：基础/均衡/严格）。
/// - 基础(0)：仅威胁黑名单（既有）；
/// - 均衡(1)：+ 已知跟踪器域名拦截（内置清单，后缀匹配）；
/// - 严格(2)：+ 拦截全部第三方请求（非当前站点域的子资源——可能偶有站点受影响，用户显式选择）。</summary>
public static class TrackerList
{
    /// <summary>已知跟踪/广告域（后缀匹配；适度规模的可信清单）。</summary>
    private static readonly string[] Domains =
    [
        // 广告网络
        "doubleclick.net", "googlesyndication.com", "googletagservices.com",
        "googleadservices.com", "adnxs.com", "pubmatic.com", "rubiconproject.com",
        "criteo.com", "criteo.net", "taboola.com", "outbrain.com", "moatads.com",
        "amazon-adsystem.com", "adsrvr.org", "casalemedia.com", "openx.net",
        "smartadserver.com", "teads.tv", "yieldmo.com", "sharethrough.com",
        "media.net", "revcontent.com", "mgid.com", "zedo.com", "mopub.com",
        "applovin.com", "adcolony.com",
        // 分析/统计
        "google-analytics.com", "analytics.google.com", "hotjar.com",
        "mixpanel.com", "segment.io", "segment.com", "scorecardresearch.com",
        "quantserve.com", "chartbeat.com", "nr-data.net", "fullstory.com",
        "clarity.ms", "growingio.com", "sensorsdata.cn", "thinkingdata.cn",
        // 社交追踪
        "connect.facebook.net", "facebook.net", "ads-twitter.com",
        "analytics.tiktok.com", "ads.linkedin.com", "px.ads.linkedin.com",
        "snap.licdn.com",
        // 国内统计
        "hm.baidu.com", "pos.baidu.com", "mmstat.com", "tanx.com", "cnzz.com",
        "umeng.com",
    ];

    // CS-136：清单预展开为倒序单集——host 的每个祖先域后缀不再逐点段切片
    // 分配（每请求多次堆分配），倒序前缀经 span 备用查找零分配探测
    //（"a.doubleclick.net" 的后缀命中 ⇔ "ten.kcilcbuod.a" 以 "ten.kcilcbuod" 为标签边界前缀）。
    private static readonly HashSet<string> ReversedDomains = new(
        Domains.Select(ReverseDomain), StringComparer.Ordinal);

    private static readonly HashSet<string>.AlternateLookup<ReadOnlySpan<char>> ReversedLookup =
        ReversedDomains.GetAlternateLookup<ReadOnlySpan<char>>();

    private static string ReverseDomain(string domain)
    {
        var chars = domain.ToCharArray();
        Array.Reverse(chars);
        return new string(chars);
    }

    public static bool IsTracker(string host)
    {
        if (string.IsNullOrEmpty(host))
            return false;
        var h = host.TrimEnd('.').ToLowerInvariant();
        if (h.Length == 0 || h.Length > 253)
            return false;
        // 倒序渐进构造：每遇 '.' 即得到一个完整的"倒序祖先域"候选——
        // 整个匹配过程零切片分配
        Span<char> buffer = stackalloc char[254];
        var len = 0;
        for (var i = h.Length - 1; i >= 0; i--)
        {
            var c = h[i];
            if (c == '.' && ReversedLookup.Contains(buffer.Slice(0, len)))
                return true;
            buffer[len++] = c;
        }
        return ReversedLookup.Contains(buffer.Slice(0, len));
    }

    /// <summary>是否同站（host 相等或为其子域——严格模式第三方判定）。
    /// CS-137：尾字符+EndsWith(span 语义) 判定——此前 "." + p 每调用拼接分配。</summary>
    public static bool IsSameSite(string host, string pageHost)
    {
        var h = (host ?? string.Empty).TrimEnd('.').ToLowerInvariant();
        var p = (pageHost ?? string.Empty).TrimEnd('.').ToLowerInvariant();
        if (h.Length == p.Length)
            return string.Equals(h, p, StringComparison.Ordinal);
        return h.Length > p.Length
            && h[h.Length - p.Length - 1] == '.'
            && h.EndsWith(p, StringComparison.Ordinal);
    }
}

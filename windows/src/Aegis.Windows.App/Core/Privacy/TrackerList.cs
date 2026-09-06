namespace Aegis.Windows.Core.Privacy;

using System;
using System.Collections.Generic;

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

    private static readonly HashSet<string> Set = new(Domains, StringComparer.OrdinalIgnoreCase);

    public static bool IsTracker(string host)
    {
        if (string.IsNullOrEmpty(host))
            return false;
        var h = host.TrimEnd('.').ToLowerInvariant();
        if (Set.Contains(h))
            return true;
        // 后缀匹配（子域）：a.doubleclick.net → doubleclick.net
        var idx = h.IndexOf('.', 1);
        while (idx > 0 && idx < h.Length - 1)
        {
            if (Set.Contains(h[(idx + 1)..]))
                return true;
            idx = h.IndexOf('.', idx + 1);
        }
        return false;
    }

    /// <summary>是否同站（host 相等或为其子域——严格模式第三方判定）。</summary>
    public static bool IsSameSite(string host, string pageHost)
    {
        var h = (host ?? string.Empty).TrimEnd('.').ToLowerInvariant();
        var p = (pageHost ?? string.Empty).TrimEnd('.').ToLowerInvariant();
        return h == p || h.EndsWith("." + p, StringComparison.OrdinalIgnoreCase);
    }
}

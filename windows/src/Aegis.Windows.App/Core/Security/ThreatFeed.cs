namespace Aegis.Windows.Core.Security;

using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Net.Http;

/// <summary>威胁黑名单语义（Python threat_feed.py 移植——精确 + 子域后缀匹配）。
/// 纯逻辑可单测；经 IBlockedHosts 注入 broker，作为导航/子资源统一策略数据。</summary>
public interface IBlockedHosts
{
    /// <summary>host（已小写、去尾点）是否命中黑名单（精确或任意祖先域后缀）。</summary>
    bool IsBlocked(string host);
}

/// <summary>黑名单集合实现（集合不可变快照——刷新后整体替换引用）。</summary>
public sealed class BlockedHosts : IBlockedHosts
{
    private readonly HashSet<string> _hosts;

    public BlockedHosts(IEnumerable<string> hosts) =>
        _hosts = new HashSet<string>(
            hosts.Select(h => h.Trim().ToLowerInvariant().TrimEnd('.')),
            StringComparer.Ordinal);

    public bool IsBlocked(string host)
    {
        if (string.IsNullOrWhiteSpace(host))
            return false;
        var normalized = host.Trim().ToLowerInvariant().TrimEnd('.');
        if (normalized.Length == 0)
            return false;
        if (_hosts.Contains(normalized))
            return true;
        // 子域后缀匹配：evil.example.com 命中 blocked 的 example.com
        var parts = normalized.Split('.');
        for (var i = 1; i < parts.Length; i++)
        {
            if (_hosts.Contains(string.Join('.', parts[i..])))
                return true;
        }
        return false;
    }
}

/// <summary>空黑名单（未配置订阅源——一律放行，不影响浏览）。</summary>
public sealed class NoBlockedHosts : IBlockedHosts
{
    public static readonly NoBlockedHosts Instance = new();

    public bool IsBlocked(string host) => false;
}

/// <summary>恶意站点订阅源（Python threat_feed.py 语义移植）：
/// https 强制（明文可投毒）/ 5MB 上限 / 临时文件+原子替换落盘 /
/// AdBlock 主机语法子集（||host^）/ 注释行。</summary>
public static class ThreatFeedUpdater
{
    private const long MaxBytes = 5 * 1024 * 1024;

    /// <summary>校验订阅源地址：仅 https（file:// 需显式离线开关）。非法返回 null。</summary>
    public static string? ValidateFeedUrl(string? feedUrl, bool allowFileForOfflineTest = false)
    {
        if (string.IsNullOrWhiteSpace(feedUrl))
            return null;
        if (!Uri.TryCreate(feedUrl.Trim(), UriKind.Absolute, out var uri))
            return null;
        if (uri.Scheme == Uri.UriSchemeHttps)
            return feedUrl.Trim();
        if (uri.Scheme == Uri.UriSchemeFile && allowFileForOfflineTest)
            return feedUrl.Trim();
        return null;
    }

    /// <summary>解析订阅源一行文本为域名；无效返回 null（Python parse_feed_line 同语义）。</summary>
    public static string? ParseFeedLine(string line)
    {
        var text = line.Trim();
        if (text.Length == 0 || text.StartsWith('!') || text.StartsWith('#'))
            return null;
        if (text.StartsWith("||"))
            text = text[2..];
        if (text.EndsWith("^"))
            text = text[..^1];
        // 去协议与路径残留
        var schemeEnd = text.IndexOf("://", StringComparison.Ordinal);
        if (schemeEnd >= 0)
            text = text[(schemeEnd + 3)..];
        var slash = text.IndexOf('/');
        if (slash >= 0)
            text = text[..slash];
        text = text.Trim().TrimEnd('^').ToLowerInvariant();
        if (text.Length == 0 || (text.Length == 1 && text[0] == ':'))
            return null;
        if (!text.Contains('.') && text != "localhost")
            return null;
        return text;
    }

    /// <summary>拉取订阅源并写入缓存文件（原子替换）。失败抛异常由调用方留痕。</summary>
    public static IReadOnlyList<string> FetchAndStore(string feedUrl, string cachePath)
    {
        using var handler = new HttpClientHandler();
        using var http = new HttpClient(handler) { Timeout = TimeSpan.FromSeconds(15) };
        using var response = http.GetAsync(feedUrl).GetAwaiter().GetResult();
        response.EnsureSuccessStatusCode();
        var bytes = response.Content.ReadAsByteArrayAsync().GetAwaiter().GetResult();
        if (bytes.Length > MaxBytes)
            throw new InvalidOperationException("订阅源过大（超过 5MB 上限）");

        var domains = new List<string>();
        var seen = new HashSet<string>(StringComparer.Ordinal);
        using var reader = new StreamReader(new MemoryStream(bytes));
        while (reader.ReadLine() is { } line)
        {
            var domain = ParseFeedLine(line);
            if (domain is not null && seen.Add(domain))
                domains.Add(domain);
        }

        var dir = Path.GetDirectoryName(cachePath);
        if (!string.IsNullOrEmpty(dir))
            Directory.CreateDirectory(dir);
        var tmp = cachePath + ".tmp";
        File.WriteAllLines(tmp, domains);
        File.Move(tmp, cachePath, overwrite: true);
        return domains;
    }

    /// <summary>加载缓存黑名单快照（文件缺失/损坏返回空——fail-safe）。</summary>
    public static IReadOnlyList<string> LoadCached(string cachePath)
    {
        try
        {
            if (!File.Exists(cachePath))
                return Array.Empty<string>();
            return File.ReadAllLines(cachePath)
                .Select(l => l.Trim())
                .Where(l => l.Length > 0)
                .ToList();
        }
        catch (IOException)
        {
            return Array.Empty<string>();
        }
    }
}

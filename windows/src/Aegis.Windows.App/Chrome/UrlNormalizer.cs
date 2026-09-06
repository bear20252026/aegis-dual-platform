namespace Aegis.Windows.Chrome;

using System;
using System.Collections.Generic;
using System.Text.RegularExpressions;

/// <summary>
/// 地址栏输入归一单源（Windows 端——与 Android SearchEngines.kt 跨端契约对齐，
/// 语义同 legacy/windows-pywebview url_utils.normalize_url）：
/// ① 空输入 → null（拒绝）
/// ② about:blank → 原样放行
/// ③ 带 scheme：仅 http/https 放行；其余（file:/javascript:/data: 等）
///    → null（fail-closed——杜绝补 https:// 拼接盲区）
/// ④ 无 scheme：含空格或不含点号 → 搜索词拼引擎 URL；否则当域名补 https
/// ⑤ 完整 URL 内空格编码为 %20（浏览器惯例）
/// 最终导航仍经 NavigationStarting → Broker 决策——本类只做输入归一，不做授权。
/// </summary>
public static class UrlNormalizer
{
    public const string DefaultEngine = "baidu";

    /// <summary>搜索引擎展示顺序（UI 下拉/首页菜单按此排列）。</summary>
    public static readonly IReadOnlyList<string> EngineOrder =
    [
        "baidu", "bing", "google", "sogou", "so360",
        "duckduckgo", "brave", "startpage", "ecosia", "yandex",
    ];

    /// <summary>主流搜索引擎表（key → 搜索 URL 前缀；市场主流全覆盖）。</summary>
    public static readonly IReadOnlyDictionary<string, string> EngineUrls =
        new Dictionary<string, string>(StringComparer.Ordinal)
        {
            ["baidu"] = "https://www.baidu.com/s?wd=",
            ["bing"] = "https://www.bing.com/search?q=",
            ["google"] = "https://www.google.com/search?q=",
            ["sogou"] = "https://www.sogou.com/web?query=",
            ["so360"] = "https://www.so.com/s?q=",
            ["duckduckgo"] = "https://duckduckgo.com/?q=",
            ["brave"] = "https://search.brave.com/search?q=",
            ["startpage"] = "https://www.startpage.com/sp/search?query=",
            ["ecosia"] = "https://www.ecosia.org/search?q=",
            ["yandex"] = "https://yandex.com/search/?text=",
        };

    /// <summary>引擎展示名单源（中文优先；工具栏/设置/首页菜单共用）。</summary>
    public static readonly IReadOnlyDictionary<string, string> EngineNames =
        new Dictionary<string, string>(StringComparer.Ordinal)
        {
            ["baidu"] = "百度",
            ["bing"] = "必应",
            ["google"] = "谷歌",
            ["sogou"] = "搜狗",
            ["so360"] = "360搜索",
            ["duckduckgo"] = "DuckDuckGo",
            ["brave"] = "Brave",
            ["startpage"] = "Startpage",
            ["ecosia"] = "Ecosia",
            ["yandex"] = "Yandex",
        };

    /// <summary>引擎展示名（未知 key 回退 key 本身）。</summary>
    public static string EngineName(string key) =>
        EngineNames.GetValueOrDefault(key, key);

    /// <summary>RFC 3986 scheme 前缀识别（末尾必须有冒号）。</summary>
    private static readonly Regex SchemePrefix = new(@"^([a-zA-Z][a-zA-Z0-9+.\-]*):", RegexOptions.Compiled);

    /// <summary>统一输入归一。返回 null 表示拒绝导航（空输入 / 非导航 scheme）。</summary>
    public static string? Normalize(string? input, string engineKey = DefaultEngine)
    {
        var trimmed = input?.Trim();
        if (string.IsNullOrEmpty(trimmed))
            return null;
        if (trimmed.Equals("about:blank", StringComparison.OrdinalIgnoreCase))
            return "about:blank";

        var schemeMatch = SchemePrefix.Match(trimmed);
        if (schemeMatch is { Success: true } match)
        {
            var scheme = match.Groups[1].Value.ToLowerInvariant();
            // host:port（冒号后是数字端口）不是协议——如 localhost:8080、
            // example.com:8080。此前被 SchemePrefix 误判为非导航 scheme 而
            // 拒绝（预存 bug）。落到本机/域名导航处理。
            var after = trimmed[match.Length..];
            if (after.Length > 0 && char.IsDigit(after[0]))
            {
                if (IsExplicitLocalHostName(trimmed))
                    return SchemeForLocal(trimmed) + trimmed;
                if (!trimmed.Contains(' ') && trimmed.Contains('.')
                    && !trimmed.EndsWith(".", StringComparison.Ordinal))
                    return SchemeForLocal(trimmed) + trimmed;
            }
            else if (scheme is not ("http" or "https"))
            {
                return null;  // fail-closed：file:/javascript:/data: 等绝不补全或拼接
            }
            else
            {
                return trimmed.Replace(" ", "%20");
            }
        }

        // 显式本机名（localhost / foo.localhost，可含端口）直接导航到本机 http，
        // 不走搜索词——放开本地开发访问（对标 Chrome 对 localhost 的行为）。
        if (IsExplicitLocalHostName(trimmed))
            return SchemeForLocal(trimmed) + trimmed;

        if (!trimmed.Contains(' ') && trimmed.Contains('.') && !trimmed.EndsWith(".", StringComparison.Ordinal))
            return SchemeForLocal(trimmed) + trimmed;

        return EngineUrls.GetValueOrDefault(engineKey, EngineUrls[DefaultEngine]) + EscapeQuery(trimmed);
    }

    /// <summary>输入是否为显式本机名（localhost / *.localhost，可含端口）。
    /// IP 字面量经 SchemeForLocal 处理，无需在此分支。</summary>
    private static bool IsExplicitLocalHostName(string input)
    {
        var colon = input.IndexOf(':');
        var host = (colon >= 0 ? input[..colon] : input).TrimEnd('.').ToLowerInvariant();
        return host.Equals("localhost", StringComparison.Ordinal)
            || host.EndsWith(".localhost", StringComparison.Ordinal);
    }

    /// <summary>无 scheme 的裸主机名默认补协议。本机名（localhost/.localhost/回环
    /// 及任意 IP 字面量）补 http——本地/内网服务器通常只跑 http，对标 Chrome 对
    /// localhost 与裸 IP 的行为；其它域名补 https。</summary>
    private static string SchemeForLocal(string input)
    {
        var host = input;
        var slash = host.IndexOf('/');
        if (slash >= 0)
            host = host[..slash];  // 去路径，如 api.localhost/x → api.localhost
        var colon = host.IndexOf(':');
        if (colon >= 0)
            host = host[..colon];  // 剥离端口，如 localhost:8080 / 127.0.0.1:8080
        host = host.TrimEnd('.').ToLowerInvariant();
        if (System.Net.IPAddress.TryParse(host, out _))
            return "http://";  // IP 字面量（含 127.0.0.1 回环）
        if (host.Equals("localhost", StringComparison.Ordinal) || host.EndsWith(".localhost", StringComparison.Ordinal))
            return "http://";
        return "https://";
    }

    /// <summary>EscapeDataString 后保留 "/"（对齐 Android Uri.encode(text, "/") 语义）。</summary>
    private static string EscapeQuery(string text) =>
        Uri.EscapeDataString(text).Replace("%2F", "/", StringComparison.Ordinal);
}

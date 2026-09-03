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

    public static readonly IReadOnlyDictionary<string, string> EngineUrls =
        new Dictionary<string, string>(StringComparer.Ordinal)
        {
            ["baidu"] = "https://www.baidu.com/s?wd=",
            ["bing"] = "https://www.bing.com/search?q=",
            ["google"] = "https://www.google.com/search?q=",
            ["sogou"] = "https://www.sogou.com/web?query=",
        };

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

        var scheme = SchemePrefix.Match(trimmed) is { Success: true } match
            ? match.Groups[1].Value.ToLowerInvariant()
            : null;
        if (scheme is not null)
        {
            if (scheme is not ("http" or "https"))
                return null;  // fail-closed：file:/javascript:/data: 等绝不补全或拼接
            return trimmed.Replace(" ", "%20");
        }

        if (!trimmed.Contains(' ') && trimmed.Contains('.') && !trimmed.EndsWith(".", StringComparison.Ordinal))
            return "https://" + trimmed;

        return EngineUrls.GetValueOrDefault(engineKey, EngineUrls[DefaultEngine]) + EscapeQuery(trimmed);
    }

    /// <summary>EscapeDataString 后保留 "/"（对齐 Android Uri.encode(text, "/") 语义）。</summary>
    private static string EscapeQuery(string text) =>
        Uri.EscapeDataString(text).Replace("%2F", "/", StringComparison.Ordinal);
}

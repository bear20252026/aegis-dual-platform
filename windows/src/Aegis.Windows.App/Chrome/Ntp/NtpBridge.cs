namespace Aegis.Windows.Chrome.Ntp;

using System;
using System.Collections.Generic;
using System.Text.Json;

/// <summary>新标签页宿主桥（M3——start.html Host 适配层的 C# 端实现）。
/// 安全边界：
/// - 仅受信 NTP 虚拟主机来源的 WebMessage 被处理（IsTrustedSource）；
///   远程页面 WebMessage 被宿主 per-origin 关闭 + 本桥双重校验；
/// - 壁纸/引擎/导入来源全部走白名单校验，非法参数 fail-closed；
/// - 书签/导入数据经本桥注入页面（渲染数据非页面自行读取）；
/// - 导航意图不直接产生副作用——归一后交 WebView NavigationStarting→
///   Broker 决策（与地址栏同一条唯一授权路径）。</summary>
public sealed class NtpBridge
{
    private readonly Services _services;

    /// <summary>宿主服务快照（由受信 chrome 注入——本类不创建任何副作用域）。</summary>
    public sealed record Services(
        Func<string> SearchEngine,
        Action<string> SetSearchEngine,
        Func<string> Wallpaper,
        Action<string> SetWallpaper,
        Func<IReadOnlyList<Core.Bookmarks.Bookmark>> Bookmarks,
        Func<int> SavedSessionCount,
        Action RestoreSession,
        Action<string?> Navigate,
        Func<bool> GoBack,
        Func<bool> OpenGeo,
        Func<IReadOnlyList<ImportSourceSnapshot>> ImportSources,
        Func<string?, (int Imported, int Total, IReadOnlyList<ImportResult> Results)> ImportBookmarks,
        Func<int, string?, (int Imported, int Total, IReadOnlyList<ImportResult> Results)> ImportHistory);

    public sealed record ImportSourceSnapshot(string Browser, bool Bookmarks, bool History);

    public sealed record ImportResult(string Browser, int Imported, int Total);

    public NtpBridge(Services services) => _services = services;

    /// <summary>来源校验：仅 NTP 虚拟主机（https + 固定 host + 默认端口）。</summary>
    public static bool IsTrustedSource(string? source) =>
        Uri.TryCreate(source, UriKind.Absolute, out var uri)
        && uri.Scheme == Uri.UriSchemeHttps
        && uri.Host.Equals(NtpAssets.HostName, StringComparison.OrdinalIgnoreCase)
        && uri.IsDefaultPort;

    /// <summary>分发一条 WebMessage（JSON）。非受信来源/格式非法 → 静默忽略。
    /// respond 注入由调用方提供（PostWebMessageAsJson）——本类不持有 WebView。</summary>
    public void TryHandle(string? source, string messageJson, Action<object?> respond)
    {
        if (!IsTrustedSource(source))
            return;
        long id;
        string op;
        JsonElement args;
        try
        {
            using var document = JsonDocument.Parse(messageJson);
            var root = document.RootElement;
            if (root.ValueKind != JsonValueKind.Object
                || !root.TryGetProperty("__aegis", out var marker) || marker.GetInt64() != 1
                || !root.TryGetProperty("id", out var idElement)
                || !root.TryGetProperty("op", out var opElement) || opElement.ValueKind != JsonValueKind.String)
                return;
            id = idElement.GetInt64();
            op = opElement.GetString()!;
            args = root.TryGetProperty("args", out var argsElement) && argsElement.ValueKind == JsonValueKind.Array
                ? argsElement.Clone()
                : JsonSerializer.SerializeToElement(Array.Empty<object>());
        }
        catch (JsonException)
        {
            return;  // 非协议消息忽略
        }
        respond(new { __aegisRes = 1, id, result = Dispatch(op, args) });
    }

    /// <summary>操作分发（纯函数——依赖经 Services 注入，全量可单测）。</summary>
    public object? Dispatch(string op, JsonElement args)
    {
        switch (op)
        {
            case "getEngine":
                var current = _services.SearchEngine();
                var engines = new List<object>();
                foreach (var key in Chrome.UrlNormalizer.EngineOrder)
                    engines.Add(new { key, name = Chrome.UrlNormalizer.EngineName(key) });
                return new { engine = current, engines };
            case "setEngine":
                if (ArgString(args, 0) is { } engine
                    && Chrome.UrlNormalizer.EngineUrls.ContainsKey(engine))
                {
                    _services.SetSearchEngine(engine);
                }
                return null;
            case "getWallpaper":
                return _services.Wallpaper();
            case "setWallpaper":
                if (ArgString(args, 0) is { } wallpaper
                    && NtpAssets.IsWallpaperAllowed(wallpaper))
                {
                    _services.SetWallpaper(wallpaper);
                }
                return null;
            case "navigate":
                if (ArgString(args, 0) is { } target)
                {
                    // 归一在桥内完成：① 非导航协议（javascript:/file:/data: 等）
                    // fail-closed；② **使用当前搜索引擎**拼搜索 URL——此前漏传
                    // 引擎导致首页搜索永远走默认百度（搜索切换失效的根因）
                    var normalized = Chrome.UrlNormalizer.Normalize(
                        target, _services.SearchEngine());
                    if (normalized is not null)
                        _services.Navigate(normalized);
                }
                return null;
            case "goBack":
                return _services.GoBack();
            case "openGeo":
                return _services.OpenGeo();
            case "hasSaved":
                return _services.SavedSessionCount();
            case "restoreSession":
                _services.RestoreSession();
                return null;
            case "bookmarks":
                var bookmarks = new List<object>();
                foreach (var bookmark in _services.Bookmarks())
                    bookmarks.Add(new { title = bookmark.Title, url = bookmark.Url });
                return bookmarks;
            case "importScan":
                var sources = new List<object>();
                foreach (var source in _services.ImportSources())
                    sources.Add(new { browser = source.Browser, bookmarks = source.Bookmarks, history = source.History });
                return sources;
            case "importBookmarks":
                return ImportOutcome(_services.ImportBookmarks(ArgString(args, 0)));
            case "importHistory":
                return ImportOutcome(_services.ImportHistory(
                    ArgInt(args, 0, 500) is { } limit ? Math.Clamp(limit, 1, 2000) : 500,
                    ArgString(args, 1)));
            case "jsError":
                Core.Security.SecurityLog.Write($"[ntp] 页面异常: {ArgString(args, 0) ?? "unknown"}");
                return null;
            default:
                return null;  // 未知操作 fail-closed 忽略
        }
    }

    private static object ImportOutcome(
        (int Imported, int Total, IReadOnlyList<ImportResult> Results) outcome)
    {
        var results = new List<object>();
        foreach (var result in outcome.Results)
            results.Add(new { browser = result.Browser, imported = result.Imported, total = result.Total });
        return new { imported = outcome.Imported, total = outcome.Total, results };
    }

    private static string? ArgString(JsonElement args, int index) =>
        args.ValueKind == JsonValueKind.Array
        && args.GetArrayLength() > index
        && args[index].ValueKind == JsonValueKind.String
            ? args[index].GetString()
            : null;

    private static int? ArgInt(JsonElement args, int index, int fallback)
    {
        if (args.ValueKind != JsonValueKind.Array || args.GetArrayLength() <= index)
            return null;
        return args[index].ValueKind switch
        {
            JsonValueKind.Number => args[index].TryGetInt32(out var value) ? value : fallback,
            JsonValueKind.String when int.TryParse(args[index].GetString(), out var parsed) => parsed,
            _ => null,
        };
    }
}

namespace Aegis.Windows.Core.Bookmarks;

using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text.Json;

/// <summary>Chrome/Edge 书签导入（Python browser_import.py 语义移植）：
/// 解析 Bookmarks JSON（roots.bookmark_bar/other/synced 递归——深度有界，
/// 构造的深嵌套文件不再触发 StackOverflow 进程崩溃），
/// 仅接受 http/https（javascript: 等坏条目过滤——与 Python 同口径），
/// 入库幂等去重；探测 Default + Profile 1..9 多配置目录。</summary>
public static class BookmarkImporter
{
    private const int MaxDepth = 64;
    private const int MaxTitleChars = 256;
    private const int MaxUrlChars = 2048;

    /// <summary>标准安装位置探测（Chrome/Edge 的 Default + Profile 1..9）。</summary>
    public static IReadOnlyList<ImportSource> DetectSources()
    {
        var local = Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData);
        var sources = new List<ImportSource>();
        AddIfExists(sources, "chrome", Path.Combine(
            local, "Google", "Chrome", "User Data", "Default", "Bookmarks"));
        AddIfExists(sources, "edge", Path.Combine(
            local, "Microsoft", "Edge", "User Data", "Default", "Bookmarks"));
        for (var i = 1; i <= 9; i++)
        {
            AddIfExists(sources, $"chrome(profile {i})", Path.Combine(
                local, "Google", "Chrome", "User Data", $"Profile {i}", "Bookmarks"));
            AddIfExists(sources, $"edge(profile {i})", Path.Combine(
                local, "Microsoft", "Edge", "User Data", $"Profile {i}", "Bookmarks"));
        }
        return sources;
    }

    /// <summary>解析书签文件为候选列表（http/https 过滤在解析时完成）。</summary>
    public static IReadOnlyList<BookmarkCandidate> Parse(string bookmarksJsonPath)
    {
        using var document = JsonDocument.Parse(File.ReadAllText(bookmarksJsonPath));
        var candidates = new List<BookmarkCandidate>();
        if (!document.RootElement.TryGetProperty("roots", out var roots))
            return candidates;
        foreach (var root in roots.EnumerateObject())
        {
            if (root.Value.ValueKind == JsonValueKind.Object)
                Walk(root.Value, candidates, depth: 0);
        }
        return candidates;
    }

    /// <summary>导入到书签库（幂等——重复 URL 计入 total 不计入 imported；
    /// 单事务批量写入）。</summary>
    public static (int Imported, int Total) ImportTo(
        BookmarkStore store, IEnumerable<BookmarkCandidate> candidates) =>
        store.Import(candidates.Select(c => (TrimTitle(c.Title), c.Url)));

    private static string TrimTitle(string title) =>
        title.Length > MaxTitleChars ? title[..MaxTitleChars] : title;

    private static void Walk(JsonElement node, List<BookmarkCandidate> into, int depth)
    {
        if (depth > MaxDepth)
            return;  // 深度有界——构造文件不再可触发栈溢出
        if (node.TryGetProperty("type", out var type)
            && type.ValueKind == JsonValueKind.String
            && type.GetString() == "url"
            && node.TryGetProperty("url", out var urlElement)
            && node.TryGetProperty("name", out var nameElement)
            && Uri.TryCreate(urlElement.GetString(), UriKind.Absolute, out var uri)
            && (uri.Scheme == Uri.UriSchemeHttp || uri.Scheme == Uri.UriSchemeHttps)
            && uri.ToString().Length <= MaxUrlChars)
        {
            var title = nameElement.GetString() ?? uri.Host;
            into.Add(new BookmarkCandidate(TrimTitle(title), uri.ToString()));
        }
        if (node.TryGetProperty("children", out var children)
            && children.ValueKind == JsonValueKind.Array)
        {
            foreach (var child in children.EnumerateArray())
                Walk(child, into, depth + 1);
        }
    }

    private static void AddIfExists(List<ImportSource> into, string browser, string path)
    {
        if (File.Exists(path))
            into.Add(new ImportSource(browser, path));
    }
}

/// <summary>导入来源（浏览器名 + Bookmarks 文件路径）。</summary>
public sealed record ImportSource(string Browser, string Path);

/// <summary>书签候选（解析产物——已过滤非 http/https）。</summary>
public sealed record BookmarkCandidate(string Title, string Url);

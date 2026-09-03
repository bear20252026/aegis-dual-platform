namespace Aegis.Windows.Core.Bookmarks;

using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text.Json;

/// <summary>Chrome/Edge 书签导入（Python browser_import.py 语义移植）：
/// 解析 Bookmarks JSON（roots.bookmark_bar/other/synced 递归），
/// 仅接受 http/https（javascript: 等坏条目过滤——与 Python 同口径），
/// 入库幂等去重。</summary>
public static class BookmarkImporter
{
    /// <summary>标准安装位置探测（Chrome/Edge 的 Default 配置目录）。</summary>
    public static IReadOnlyList<ImportSource> DetectSources()
    {
        var local = Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData);
        var sources = new List<ImportSource>();
        AddIfExists(sources, "chrome", Path.Combine(
            local, "Google", "Chrome", "User Data", "Default", "Bookmarks"));
        AddIfExists(sources, "edge", Path.Combine(
            local, "Microsoft", "Edge", "User Data", "Default", "Bookmarks"));
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
                Walk(root.Value, candidates);
        }
        return candidates;
    }

    /// <summary>导入到书签库（幂等——重复 URL 计入 total 不计入 imported）。</summary>
    public static (int Imported, int Total) ImportTo(
        BookmarkStore store, IEnumerable<BookmarkCandidate> candidates)
    {
        var imported = 0;
        var total = 0;
        foreach (var candidate in candidates)
        {
            total++;
            if (store.Add(candidate.Title, candidate.Url))
                imported++;
        }
        return (imported, total);
    }

    private static void Walk(JsonElement node, List<BookmarkCandidate> into)
    {
        if (node.TryGetProperty("type", out var type)
            && type.ValueKind == JsonValueKind.String
            && type.GetString() == "url"
            && node.TryGetProperty("url", out var urlElement)
            && node.TryGetProperty("name", out var nameElement)
            && Uri.TryCreate(urlElement.GetString(), UriKind.Absolute, out var uri)
            && (uri.Scheme == Uri.UriSchemeHttp || uri.Scheme == Uri.UriSchemeHttps))
        {
            into.Add(new BookmarkCandidate(nameElement.GetString() ?? uri.Host, uri.ToString()));
        }
        if (node.TryGetProperty("children", out var children)
            && children.ValueKind == JsonValueKind.Array)
        {
            foreach (var child in children.EnumerateArray())
                Walk(child, into);
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

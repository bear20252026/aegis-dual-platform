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

    /// <summary>标准安装位置探测（Chrome/Edge 的 Default + Profile 1..9）。
    /// CS-231：探测路径共享单源。</summary>
    public static IReadOnlyList<ImportSource> DetectSources() =>
        Core.Import.ImportProbe.Probe("Bookmarks")
            .Select(p => new ImportSource(p.Browser, p.Path))
            .ToList();

    /// <summary>解析书签文件为候选列表（http/https 过滤在解析时完成）。
    /// CS-100：损坏 JSON/不可读文件此前直接上抛到导入向导——导入是可选功能，
    /// 与 HistoryImporter 同口径：任何解析失败返回空，绝不影响浏览。</summary>
    public static IReadOnlyList<BookmarkCandidate> Parse(string bookmarksJsonPath)
    {
        try
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
        catch (Exception)
        {
            return [];  // 损坏/缺失/不可读 → 空结果（fail-safe）
        }
    }

    /// <summary>导入到书签库（幂等——重复 URL 计入 total 不计入 imported；
    /// 单事务批量写入）。</summary>
    public static (int Imported, int Total) ImportTo(
        BookmarkStore store, IEnumerable<BookmarkCandidate> candidates) =>
        store.Import(candidates.Select(c => (TrimTitle(c.Title), c.Url)));

    /// <summary>CS-101：标题截断代理对安全——硬切 [..256] 可把 UTF-16 代理对
    /// 劈成孤立代理（emoji 标题截断即乱码落库）；边界落在高代理上时回退一位。</summary>
    internal static string TrimTitle(string title)
    {
        if (title.Length <= MaxTitleChars)
            return title;
        var cut = MaxTitleChars;
        if (char.IsHighSurrogate(title[cut - 1]))
            cut--;
        return title[..cut];
    }

    private static void Walk(JsonElement node, List<BookmarkCandidate> into, int depth)
    {
        if (depth > MaxDepth)
            return;  // 深度有界——构造文件不再可触发栈溢出
        if (node.TryGetProperty("type", out var type)
            && type.ValueKind == JsonValueKind.String
            && type.GetString() == "url"
            && node.TryGetProperty("url", out var urlElement)
            && Uri.TryCreate(urlElement.GetString(), UriKind.Absolute, out var uri)
            && (uri.Scheme == Uri.UriSchemeHttp || uri.Scheme == Uri.UriSchemeHttps)
            && uri.ToString().Length <= MaxUrlChars)
        {
            // CS-105：name 缺省/非字符串回退 host（对齐 Python `name or host`
            // 口径——此前整个条目因缺 name 被丢弃）
            var title = node.TryGetProperty("name", out var nameElement)
                    && nameElement.ValueKind == JsonValueKind.String
                ? nameElement.GetString()
                : null;
            if (string.IsNullOrWhiteSpace(title))
                title = uri.Host;
            into.Add(new BookmarkCandidate(TrimTitle(title!), uri.ToString()));
        }
        if (node.TryGetProperty("children", out var children)
            && children.ValueKind == JsonValueKind.Array)
        {
            foreach (var child in children.EnumerateArray())
                Walk(child, into, depth + 1);
        }
    }

}

/// <summary>导入来源（浏览器名 + Bookmarks 文件路径）。</summary>
public sealed record ImportSource(string Browser, string Path);

/// <summary>书签候选（解析产物——已过滤非 http/https）。</summary>
public sealed record BookmarkCandidate(string Title, string Url);

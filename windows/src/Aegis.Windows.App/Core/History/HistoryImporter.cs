namespace Aegis.Windows.Core.History;

using System;
using System.Collections.Generic;
using System.IO;
using Microsoft.Data.Sqlite;

/// <summary>Chrome/Edge 历史导入（M3 导入向导——Python browser_import.py
/// parse_history_db 语义移植）。安全边界：
/// - 只读打开：先拷贝到临时文件再以 ReadOnly 打开副本——源库可能正被
///   浏览器进程锁定（对齐 Python immutable 语义且不要求源库可共享）；
/// - 仅接受 http/https 条目（javascript: 等坏数据与书签导入同口径过滤）；
/// - 解析失败返回空（导入是可选功能，绝不影响浏览）；
/// - 历史是访问流水：入库无去重（HistoryStore.Add 追加语义——与 Python 一致）。</summary>
public static class HistoryImporter
{
    /// <summary>探测本机 Chrome/Edge 历史库（仅存在性检查——不读取内容）。</summary>
    public static IReadOnlyList<ImportSource> DetectSources()
    {
        var local = Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData);
        var sources = new List<ImportSource>();
        AddIfExists(sources, "chrome", Path.Combine(
            local, "Google", "Chrome", "User Data", "Default", "History"));
        AddIfExists(sources, "edge", Path.Combine(
            local, "Microsoft", "Edge", "User Data", "Default", "History"));
        return sources;
    }

    /// <summary>解析历史库（拷贝只读副本——锁定安全）。返回最近 limit 条
    /// http/https 访问（时间倒序——Chrome urls.last_visit_time 为微秒级
    /// WebKit 时间戳，仅作排序键，不做绝对时间换算）。</summary>
    public static IReadOnlyList<HistoryCandidate> Parse(string historyDbPath, int limit)
    {
        var temporary = Path.Combine(Path.GetTempPath(), Path.GetRandomFileName());
        try
        {
            File.Copy(historyDbPath, temporary);
            return ParseCopy(temporary, limit);
        }
        catch (Exception)
        {
            return Array.Empty<HistoryCandidate>();  // 锁定/损坏 → 空结果（可选功能）
        }
        finally
        {
            try
            {
                File.Delete(temporary);
            }
            catch (IOException)
            {
                // 临时文件删除失败不影响导入结果
            }
        }
    }

    /// <summary>导入到历史库。返回（新增计数, 解析总数）——历史为访问流水，
    /// 新增=解析条数（与 Python import_history 计数语义一致）。</summary>
    public static (int Imported, int Total) ImportTo(
        HistoryStore store, IEnumerable<HistoryCandidate> candidates)
    {
        var imported = 0;
        var total = 0;
        foreach (var candidate in candidates)
        {
            total++;
            store.Add(candidate.Url, candidate.Title);
            imported++;
        }
        return (imported, total);
    }

    private static List<HistoryCandidate> ParseCopy(string copyPath, int limit)
    {
        var connection = new SqliteConnection(new SqliteConnectionStringBuilder
        {
            DataSource = copyPath,
            Mode = SqliteOpenMode.ReadOnly,
            Pooling = false,
        }.ToString());
        try
        {
            connection.Open();
            using var select = connection.CreateCommand();
            select.CommandText = "SELECT url, title FROM urls ORDER BY last_visit_time DESC LIMIT $lim";
            select.Parameters.AddWithValue("$lim", Math.Clamp(limit, 1, 2000));
            var candidates = new List<HistoryCandidate>();
            using var reader = select.ExecuteReader();
            while (reader.Read())
            {
                var url = reader.IsDBNull(0) ? string.Empty : reader.GetString(0);
                var title = reader.IsDBNull(1) ? string.Empty : reader.GetString(1);
                if (Uri.TryCreate(url, UriKind.Absolute, out var uri)
                    && (uri.Scheme == Uri.UriSchemeHttp || uri.Scheme == Uri.UriSchemeHttps))
                {
                    candidates.Add(new HistoryCandidate(title, url));
                }
            }
            return candidates;
        }
        catch (SqliteException)
        {
            return [];  // 非历史库/无 urls 表 → 空（fail-safe）
        }
        finally
        {
            connection.Dispose();
        }
    }

    private static void AddIfExists(List<ImportSource> into, string browser, string path)
    {
        if (File.Exists(path))
            into.Add(new ImportSource(browser, path));
    }
}

/// <summary>历史导入来源（浏览器名 + History 库路径）。</summary>
public sealed record ImportSource(string Browser, string Path);

/// <summary>历史候选（解析产物——已过滤非 http/https）。</summary>
public sealed record HistoryCandidate(string Title, string Url);

namespace Aegis.Windows.Core.History;

using System;
using System.Collections.Generic;
using System.IO;
using Microsoft.Data.Sqlite;

/// <summary>历史记录（ADR-009 D2：SQLite + FTS5 全文检索）。
/// 对齐并超越 Python history_store.py：M2 起查看/清除 UI 真实可达
/// （Python 侧只写不清——审计隐私合规缺陷在正典栈补齐）。
/// 敏感口径：title/url 存储不含 query secret 的承诺由调用方保证
/// （与 Python 同口径——存原始 URL；FTS 索引内容 = url+title）。</summary>
public sealed class HistoryStore
{
    private readonly string _dbPath;

    public HistoryStore(string dbPath) => _dbPath = dbPath;

    /// <summary>记录一次访问（去重不必要——历史按次数累积符合浏览语义）。</summary>
    public void Add(string url, string title)
    {
        if (string.IsNullOrWhiteSpace(url))
            return;
        using var connection = Open();
        using var insert = connection.CreateCommand();
        insert.CommandText = "INSERT INTO visits(url, title, visited_at) VALUES($u,$t,$v)";
        insert.Parameters.AddWithValue("$u", url);
        insert.Parameters.AddWithValue("$t", title);
        insert.Parameters.AddWithValue("$v", DateTime.UtcNow.ToString("o"));
        insert.ExecuteNonQuery();
    }

    /// <summary>历史搜索（url+title 子串匹配）。决策记录：原计划 FTS5，
    /// 但 unicode61 tokenizer 对 CJK 连续串不分词——中文子串查询（本项目
    /// 主场景）无法命中，LIKE 是正确工具（数据量级 ≤10^4 行，性能无虞）；
    /// ADR-009 D2 已按实现学习修正。</summary>
    public IReadOnlyList<HistoryEntry> Search(string query, int limit = 100) =>
        string.IsNullOrWhiteSpace(query) ? Recent(limit) : LikeSearch(query, limit);

    /// <summary>最近访问（时间倒序）。</summary>
    public IReadOnlyList<HistoryEntry> Recent(int limit = 100)
    {
        using var connection = Open();
        using var select = connection.CreateCommand();
        select.CommandText = "SELECT id, url, title, visited_at FROM visits ORDER BY visited_at DESC, id DESC LIMIT $lim";
        return ReadEntries(select, limit);
    }

    /// <summary>清空全部历史（不可恢复——UI 层负责确认提示）。</summary>
    public void Clear()
    {
        using var connection = Open();
        using var delete = connection.CreateCommand();
        delete.CommandText = "DELETE FROM visits";
        delete.ExecuteNonQuery();
    }

    private List<HistoryEntry> ReadEntries(SqliteCommand select, int limit)
    {
        select.Parameters.AddWithValue("$lim", limit);
        // 参数在此统一注入（Recent/Search 均经此路径——避免同名参数二次添加）
        using var reader = select.ExecuteReader();
        var list = new List<HistoryEntry>();
        while (reader.Read())
            list.Add(new HistoryEntry(reader.GetInt64(0), reader.GetString(1), reader.GetString(2), reader.GetString(3)));
        return list;
    }

    private List<HistoryEntry> LikeSearch(string query, int limit)
    {
        using var connection = Open();
        using var select = connection.CreateCommand();
        select.CommandText = "SELECT id, url, title, visited_at FROM visits WHERE url LIKE $q OR title LIKE $q ORDER BY visited_at DESC LIMIT $lim";
        select.Parameters.AddWithValue("$q", $"%{query}%");
        return ReadEntries(select, limit);
    }

    private SqliteConnection Open()
    {
        var directory = Path.GetDirectoryName(_dbPath);
        if (!string.IsNullOrEmpty(directory))
            Directory.CreateDirectory(directory);
        var connection = new SqliteConnection(new SqliteConnectionStringBuilder
        {
            DataSource = _dbPath,
            Mode = SqliteOpenMode.ReadWriteCreate,
            Pooling = false,
        }.ToString());
        try
        {
            connection.Open();
            using var ensure = connection.CreateCommand();
            ensure.CommandText = """
                CREATE TABLE IF NOT EXISTS visits(
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    url TEXT NOT NULL,
                    title TEXT NOT NULL DEFAULT '',
                    visited_at TEXT NOT NULL);
""";
            ensure.ExecuteNonQuery();
            return connection;
        }
        catch
        {
            connection.Dispose();
            throw;
        }
    }
}

/// <summary>历史条目。</summary>
public sealed record HistoryEntry(long Id, string Url, string Title, string VisitedAt);

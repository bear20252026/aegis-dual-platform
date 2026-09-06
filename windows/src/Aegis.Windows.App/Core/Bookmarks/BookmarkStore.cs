namespace Aegis.Windows.Core.Bookmarks;

using System;
using System.Collections.Generic;
using System.IO;
using Microsoft.Data.Sqlite;

/// <summary>书签存储（ADR-009 D2：SQLite 数据层；Python bookmark_store.py
/// 语义对齐——Add 幂等去重 / Contains / All / Remove）。Pooling 关闭理由
/// 同 TabSessionStore（不锁 db 文件）。</summary>
public sealed class BookmarkStore
{
    private readonly string _dbPath;

    public BookmarkStore(string dbPath) => _dbPath = dbPath;

    /// <summary>添加书签；URL 重复为 no-op 并返回 false（幂等）。</summary>
    public bool Add(string title, string url)
    {
        if (string.IsNullOrWhiteSpace(url))
            return false;
        using var connection = Open();
        using var insert = connection.CreateCommand();
        insert.CommandText = "INSERT OR IGNORE INTO bookmarks(title, url, created_at) VALUES($t,$u,$c)";
        insert.Parameters.AddWithValue("$t", title);
        insert.Parameters.AddWithValue("$u", url);
        insert.Parameters.AddWithValue("$c", DateTime.UtcNow.ToString("o"));
        return insert.ExecuteNonQuery() > 0;
    }

    /// <summary>按 URL 移除书签。</summary>
    public bool Remove(string url)
    {
        using var connection = Open();
        using var delete = connection.CreateCommand();
        delete.CommandText = "DELETE FROM bookmarks WHERE url = $u";
        delete.Parameters.AddWithValue("$u", url);
        return delete.ExecuteNonQuery() > 0;
    }

    /// <summary>按 ID 移除书签（书签管理器使用）。</summary>
    public bool RemoveById(long id)
    {
        using var connection = Open();
        using var delete = connection.CreateCommand();
        delete.CommandText = "DELETE FROM bookmarks WHERE id = $id";
        delete.Parameters.AddWithValue("$id", id);
        return delete.ExecuteNonQuery() > 0;
    }

    /// <summary>重命名书签标题（书签管理器使用）。</summary>
    public bool Rename(long id, string title)
    {
        if (string.IsNullOrWhiteSpace(title))
            return false;
        using var connection = Open();
        using var update = connection.CreateCommand();
        update.CommandText = "UPDATE bookmarks SET title = $t WHERE id = $id";
        update.Parameters.AddWithValue("$t", title);
        update.Parameters.AddWithValue("$id", id);
        return update.ExecuteNonQuery() > 0;
    }

    /// <summary>清空全部书签（不可恢复——UI 层负责确认）。</summary>
    public void ClearAll()
    {
        using var connection = Open();
        using var delete = connection.CreateCommand();
        delete.CommandText = "DELETE FROM bookmarks";
        delete.ExecuteNonQuery();
    }

    /// <summary>URL 是否已收藏（收藏按钮状态判定）。</summary>
    public bool Contains(string url)
    {
        using var connection = Open();
        using var select = connection.CreateCommand();
        select.CommandText = "SELECT COUNT(1) FROM bookmarks WHERE url = $u";
        select.Parameters.AddWithValue("$u", url);
        return Convert.ToInt64(select.ExecuteScalar()) > 0;
    }

    /// <summary>全部书签（按加入顺序）。</summary>
    public IReadOnlyList<Bookmark> All()
    {
        using var connection = Open();
        using var select = connection.CreateCommand();
        select.CommandText = "SELECT id, title, url FROM bookmarks ORDER BY id";
        using var reader = select.ExecuteReader();
        var list = new List<Bookmark>();
        while (reader.Read())
            list.Add(new Bookmark(reader.GetInt64(0), reader.GetString(1), reader.GetString(2)));
        return list;
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
                CREATE TABLE IF NOT EXISTS bookmarks(
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    url TEXT NOT NULL UNIQUE,
                    created_at TEXT NOT NULL)
                """;
            ensure.ExecuteNonQuery();
            return connection;
        }
        catch
        {
            connection.Dispose();  // 建表失败释放句柄（单测教训：防文件锁定泄漏）
            throw;
        }
    }
}

/// <summary>书签记录。</summary>
public sealed record Bookmark(long Id, string Title, string Url);

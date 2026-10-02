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
    // CS-029（审计 2026-09-25）：DDL once——此前每次 Open 都跑 CREATE TABLE
    // IF NOT EXISTS（All() 每 ~150ms 被调用，DDL 纯开销）。失败不置位——下次重试。
    private volatile bool _schemaReady;

    public BookmarkStore(string dbPath) => _dbPath = dbPath;

    /// <summary>添加书签；URL 重复为 no-op 并返回 false（幂等）。
    /// CS-340（2026-10-01 审计）：Add/Rename/Import 补长度钳制（CS-319 只落
    /// HistoryStore）——页面可控任意长 title/URL 此前可落库回读渲染；
    /// 复用 TextLimits.Clamp 代理对安全口径（2048 URL / 256 标题）。</summary>
    public bool Add(string title, string url)
    {
        if (string.IsNullOrWhiteSpace(url) || string.IsNullOrWhiteSpace(title))
            return false;
        using var connection = Open();
        using var insert = connection.CreateCommand();
        insert.CommandText = "INSERT OR IGNORE INTO bookmarks(title, url, created_at) VALUES($t,$u,$c)";
        insert.Parameters.AddWithValue("$t", Aegis.Windows.Core.TextLimits.Clamp(title, Aegis.Windows.Core.TextLimits.MaxTitleChars));
        insert.Parameters.AddWithValue("$u", Aegis.Windows.Core.TextLimits.Clamp(url, Aegis.Windows.Core.TextLimits.MaxUrlChars));
        // CS-286：UTC round-trip 口径——与 HistoryStore.visited_at 一致（C8 已统一）；
        // 两库时间戳同源，跨库排序/对账不再有本地时偏移错位
        insert.Parameters.AddWithValue("$c", DateTime.UtcNow.ToString("o"));
        return insert.ExecuteNonQuery() > 0;
    }

    /// <summary>批量导入（单连接单事务——此前逐条 Add 每条一个连接生命周期 +
    /// 建表 DDL，导入 1000 条即 1000 次连接往返）。返回（新增数, 总数）。</summary>
    public (int Imported, int Total) Import(
        IEnumerable<(string Title, string Url)> candidates)
    {
        var imported = 0;
        var total = 0;
        using var connection = Open();
        using var transaction = connection.BeginTransaction();
        using var insert = connection.CreateCommand();
        insert.Transaction = transaction;
        insert.CommandText = "INSERT OR IGNORE INTO bookmarks(title, url, created_at) VALUES($t,$u,$c)";
        var title = insert.Parameters.Add("$t", SqliteType.Text);
        var url = insert.Parameters.Add("$u", SqliteType.Text);
        var createdAt = insert.Parameters.Add("$c", SqliteType.Text);
        foreach (var candidate in candidates)
        {
            if (string.IsNullOrWhiteSpace(candidate.Url) || string.IsNullOrWhiteSpace(candidate.Title))
                continue;
            total++;
            // CS-340：导入路径同口径钳制（BookmarkImporter 的上限此前只过滤
            // 不截断——恰超限条目整条丢弃；库层钳制后保留前缀）
            title.Value = Aegis.Windows.Core.TextLimits.Clamp(candidate.Title, Aegis.Windows.Core.TextLimits.MaxTitleChars);
            url.Value = Aegis.Windows.Core.TextLimits.Clamp(candidate.Url, Aegis.Windows.Core.TextLimits.MaxUrlChars);
            createdAt.Value = DateTime.UtcNow.ToString("o");
            if (insert.ExecuteNonQuery() > 0)
                imported++;
        }
        transaction.Commit();
        return (imported, total);
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

    /// <summary>重命名书签标题（书签管理器使用）。CS-340：标题钳制 256。</summary>
    public bool Rename(long id, string title)
    {
        if (string.IsNullOrWhiteSpace(title))
            return false;
        using var connection = Open();
        using var update = connection.CreateCommand();
        update.CommandText = "UPDATE bookmarks SET title = $t WHERE id = $id";
        update.Parameters.AddWithValue("$t", Aegis.Windows.Core.TextLimits.Clamp(title, Aegis.Windows.Core.TextLimits.MaxTitleChars));
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

    /// <summary>全部书签（按加入顺序）。
    /// CS-353（2026-10-01 审计）：库损坏 BLOB 行抛 InvalidCastException 此前
    /// 裸逃逸（书签管理器 Reload 直接炸窗）——归并空 + SecurityLog 留痕
    ///（fail-safe：书签栏为空可恢复，进程不可崩）。</summary>
    public IReadOnlyList<Bookmark> All()
    {
        try
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
        catch (Exception ex) when (ex is SqliteException or InvalidCastException or InvalidOperationException or IOException)
        {
            Security.SecurityLog.Write(
                $"[bookmark] 书签读取失败（回退空列表）: {ex.GetType().Name}: {ex.Message}");
            return Array.Empty<Bookmark>();
        }
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
            // busy_timeout：与书签管理器窗口并发写（改名/删除/导入）时不再
            // 依赖默认 30s 忙等后抛 "database is locked"
            using (var busy = connection.CreateCommand())
            {
                busy.CommandText = "PRAGMA busy_timeout=5000";
                busy.ExecuteNonQuery();
            }
            if (!_schemaReady)
            {
                using var ensure = connection.CreateCommand();
                ensure.CommandText = """
                    CREATE TABLE IF NOT EXISTS bookmarks(
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        title TEXT NOT NULL,
                        url TEXT NOT NULL UNIQUE,
                        created_at TEXT NOT NULL)
                    """;
                ensure.ExecuteNonQuery();
                _schemaReady = true;
            }
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

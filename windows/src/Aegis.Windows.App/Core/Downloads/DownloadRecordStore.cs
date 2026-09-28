namespace Aegis.Windows.Core.Downloads;

using System;
using System.Collections.Generic;
using System.IO;
using Microsoft.Data.Sqlite;

/// <summary>下载记录持久化（SQLite）：保存已完成/失败下载，重启后仍可查看。
/// 全部参数绑定。记录有界保留（默认 500 条——超限才修剪最旧，CS-118：
/// 此前每次插入都跑全表子查询 DELETE，常态纯开销）。</summary>
public sealed class DownloadRecordStore
{
    private const int MaxRows = 500;

    private readonly string _dbPath;
    // CS-115：DDL once——此前每次 Open 都跑 CREATE TABLE IF NOT EXISTS。
    // 失败不置位——下次重试。口径对齐 BookmarkStore（CS-029）。
    private volatile bool _schemaReady;

    public DownloadRecordStore(string dbPath) => _dbPath = dbPath;

    public sealed record DownloadRecord(long Id, string FileName, string FilePath, string Url, long SizeBytes, string CompletedAt);

    public void Add(string fileName, string filePath, string url, long sizeBytes, string completedAt)
    {
        using var c = Open();
        using var transaction = c.BeginTransaction();
        using (var cmd = c.CreateCommand())
        {
            cmd.Transaction = transaction;
            cmd.CommandText = "INSERT INTO downloads(file_name, file_path, url, size_bytes, completed_at) VALUES($f,$p,$u,$s,$t)";
            cmd.Parameters.AddWithValue("$f", fileName ?? "");
            cmd.Parameters.AddWithValue("$p", filePath ?? "");
            cmd.Parameters.AddWithValue("$u", url ?? "");
            cmd.Parameters.AddWithValue("$s", sizeBytes);
            cmd.Parameters.AddWithValue("$t", completedAt ?? "");
            cmd.ExecuteNonQuery();
        }
        // CS-118：仅超限修剪——先 COUNT 短路，未超上限不跑 DELETE 子查询
        long count;
        using (var counter = c.CreateCommand())
        {
            counter.Transaction = transaction;
            counter.CommandText = "SELECT COUNT(*) FROM downloads";
            count = Convert.ToInt64(counter.ExecuteScalar());
        }
        if (count > MaxRows)
        {
            using var prune = c.CreateCommand();
            // 有界保留：常年使用不无限累积（此前仅读取 LIMIT，表本身无上限）
            prune.Transaction = transaction;
            prune.CommandText = "DELETE FROM downloads WHERE id NOT IN (SELECT id FROM downloads ORDER BY id DESC LIMIT $max)";
            prune.Parameters.AddWithValue("$max", MaxRows);
            prune.ExecuteNonQuery();
        }
        transaction.Commit();
    }

    public IReadOnlyList<DownloadRecord> All(int limit = 200)
    {
        using var c = Open();
        using var cmd = c.CreateCommand();
        cmd.CommandText = "SELECT id, file_name, file_path, url, size_bytes, completed_at FROM downloads ORDER BY id DESC LIMIT $lim";
        // CS-116：负 limit 在 SQLite 语义为"无上限"——钳为 1 起（无界返回/内存）
        cmd.Parameters.AddWithValue("$lim", Math.Max(1, limit));
        using var r = cmd.ExecuteReader();
        var list = new List<DownloadRecord>();
        while (r.Read())
            list.Add(new DownloadRecord(r.GetInt64(0), r.GetString(1), r.GetString(2), r.GetString(3), r.GetInt64(4), r.GetString(5)));
        return list;
    }

    public void Clear()
    {
        using var c = Open();
        using var cmd = c.CreateCommand();
        cmd.CommandText = "DELETE FROM downloads";
        cmd.ExecuteNonQuery();
    }

    private SqliteConnection Open()
    {
        var dir = Path.GetDirectoryName(_dbPath);
        if (!string.IsNullOrEmpty(dir)) Directory.CreateDirectory(dir);
        var conn = new SqliteConnection(new SqliteConnectionStringBuilder { DataSource = _dbPath, Mode = SqliteOpenMode.ReadWriteCreate, Pooling = false }.ToString());
        try
        {
            conn.Open();
            // CS-099：busy_timeout 与其余三库统一——并发写时快速忙等重试
            using (var busy = conn.CreateCommand())
            {
                busy.CommandText = "PRAGMA busy_timeout=5000";
                busy.ExecuteNonQuery();
            }
            if (!_schemaReady)
            {
                using var ensure = conn.CreateCommand();
                ensure.CommandText = "CREATE TABLE IF NOT EXISTS downloads(id INTEGER PRIMARY KEY AUTOINCREMENT, file_name TEXT NOT NULL DEFAULT '', file_path TEXT NOT NULL DEFAULT '', url TEXT NOT NULL DEFAULT '', size_bytes INTEGER NOT NULL DEFAULT 0, completed_at TEXT NOT NULL DEFAULT '')";
                ensure.ExecuteNonQuery();
                _schemaReady = true;
            }
            return conn;
        }
        catch
        {
            // CS-114：打开/建表失败释放句柄（对齐 BookmarkStore 单测教训）
            conn.Dispose();
            throw;
        }
    }
}

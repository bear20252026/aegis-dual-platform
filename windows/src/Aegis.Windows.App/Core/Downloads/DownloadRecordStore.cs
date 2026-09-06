namespace Aegis.Windows.Core.Downloads;

using System;
using System.Collections.Generic;
using System.IO;
using Microsoft.Data.Sqlite;

/// <summary>下载记录持久化（SQLite）：保存已完成/失败下载，重启后仍可查看。
/// 全部参数绑定。</summary>
public sealed class DownloadRecordStore
{
    private readonly string _dbPath;

    public DownloadRecordStore(string dbPath) => _dbPath = dbPath;

    public sealed record DownloadRecord(long Id, string FileName, string FilePath, string Url, long SizeBytes, string CompletedAt);

    public void Add(string fileName, string filePath, string url, long sizeBytes, string completedAt)
    {
        using var c = Open();
        using var cmd = c.CreateCommand();
        cmd.CommandText = "INSERT INTO downloads(file_name, file_path, url, size_bytes, completed_at) VALUES($f,$p,$u,$s,$t)";
        cmd.Parameters.AddWithValue("$f", fileName ?? "");
        cmd.Parameters.AddWithValue("$p", filePath ?? "");
        cmd.Parameters.AddWithValue("$u", url ?? "");
        cmd.Parameters.AddWithValue("$s", sizeBytes);
        cmd.Parameters.AddWithValue("$t", completedAt ?? "");
        cmd.ExecuteNonQuery();
    }

    public IReadOnlyList<DownloadRecord> All(int limit = 200)
    {
        using var c = Open();
        using var cmd = c.CreateCommand();
        cmd.CommandText = "SELECT id, file_name, file_path, url, size_bytes, completed_at FROM downloads ORDER BY id DESC LIMIT $lim";
        cmd.Parameters.AddWithValue("$lim", limit);
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
        conn.Open();
        using var ensure = conn.CreateCommand();
        ensure.CommandText = "CREATE TABLE IF NOT EXISTS downloads(id INTEGER PRIMARY KEY AUTOINCREMENT, file_name TEXT NOT NULL DEFAULT '', file_path TEXT NOT NULL DEFAULT '', url TEXT NOT NULL DEFAULT '', size_bytes INTEGER NOT NULL DEFAULT 0, completed_at TEXT NOT NULL DEFAULT '')";
        ensure.ExecuteNonQuery();
        return conn;
    }
}
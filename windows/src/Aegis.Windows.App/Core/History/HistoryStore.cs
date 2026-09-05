namespace Aegis.Windows.Core.History;

using System;
using System.Collections.Generic;
using System.IO;
using Microsoft.Data.Sqlite;

/// <summary>历史记录（ADR-009 D2：SQLite）。升级版支持：
/// - 每次访问记录本地日期 + 时刻（visited_at ISO + visited_date yyyy-MM-dd，便于按日期查询）；
/// - 按日期查询 / 文本+日期组合查询 / 单条删除 / 日期列表；
/// - 全部外部输入走参数绑定（安全约束：不拼接 SQL）。
/// 敏感口径：title/url 存储不含 query secret 的承诺由调用方保证。</summary>
public sealed class HistoryStore
{
    private readonly string _dbPath;

    public HistoryStore(string dbPath) => _dbPath = dbPath;

    /// <summary>记录一次访问（追加——历史按次数累积；本地时间+日期）。</summary>
    public void Add(string url, string title)
    {
        if (string.IsNullOrWhiteSpace(url))
            return;
        var now = DateTime.Now;
        using var connection = Open();
        using var insert = connection.CreateCommand();
        insert.CommandText = """
            INSERT INTO visits(url, title, visited_at, visited_date)
            VALUES($u,$t,$v,$d)
            """;
        insert.Parameters.AddWithValue("$u", url);
        insert.Parameters.AddWithValue("$t", title ?? string.Empty);
        insert.Parameters.AddWithValue("$v", now.ToString("o"));
        insert.Parameters.AddWithValue("$d", now.ToString("yyyy-MM-dd"));
        insert.ExecuteNonQuery();
    }

    /// <summary>最近访问（时间倒序）。</summary>
    public IReadOnlyList<HistoryEntry> Recent(int limit = 200) =>
        Read("SELECT id, url, title, visited_at, visited_date FROM visits ORDER BY visited_at DESC LIMIT $lim", limit);

    /// <summary>按文本搜索（url/title 子串），可限定某日（date=yyyy-MM-dd 或 null 不限）。
    /// 全部参数绑定——LIKE 通配在绑定值中，不参与 SQL 拼接。</summary>
    public IReadOnlyList<HistoryEntry> Search(string query, string? date = null, int limit = 200)
    {
        if (string.IsNullOrWhiteSpace(query))
            return date is null ? Recent(limit) : ByDate(date, limit);
        using var connection = Open();
        using var select = connection.CreateCommand();
        select.CommandText = string.IsNullOrEmpty(date)
            ? "SELECT id, url, title, visited_at, visited_date FROM visits WHERE url LIKE $q OR title LIKE $q ORDER BY visited_at DESC LIMIT $lim"
            : "SELECT id, url, title, visited_at, visited_date FROM visits WHERE (url LIKE $q OR title LIKE $q) AND visited_date = $d ORDER BY visited_at DESC LIMIT $lim";
        select.Parameters.AddWithValue("$q", $"%{query}%");
        select.Parameters.AddWithValue("$lim", limit);
        if (!string.IsNullOrEmpty(date))
            select.Parameters.AddWithValue("$d", date);
        using var reader = select.ExecuteReader();
        return ReadEntries(reader);
    }

    /// <summary>指定日期（yyyy-MM-dd，本地时区）的访问，时间倒序。</summary>
    public IReadOnlyList<HistoryEntry> ByDate(string date, int limit = 500)
    {
        using var connection = Open();
        using var select = connection.CreateCommand();
        select.CommandText = """
            SELECT id, url, title, visited_at, visited_date
            FROM visits WHERE visited_date = $d ORDER BY visited_at DESC LIMIT $lim
            """;
        select.Parameters.AddWithValue("$d", date);
        select.Parameters.AddWithValue("$lim", limit);
        using var reader = select.ExecuteReader();
        return ReadEntries(reader);
    }

    /// <summary>全部有记录的日期（yyyy-MM-dd，倒序）——供 UI 日期筛选下拉。</summary>
    public IReadOnlyList<string> Dates(int limit = 90)
    {
        using var connection = Open();
        using var select = connection.CreateCommand();
        select.CommandText = "SELECT DISTINCT visited_date FROM visits ORDER BY visited_date DESC LIMIT $lim";
        select.Parameters.AddWithValue("$lim", limit);
        using var reader = select.ExecuteReader();
        var list = new List<string>();
        while (reader.Read())
        {
            if (!reader.IsDBNull(0))
                list.Add(reader.GetString(0));
        }
        return list;
    }

    /// <summary>按日期区间查询（from/to=yyyy-MM-dd，可为空不限一端），可叠加文本。
    /// 全部参数绑定。空文本+空区间回退 Recent。</summary>
    public IReadOnlyList<HistoryEntry> SearchRange(string query, string? from, string? to, int limit = 1000)
    {
        var hasText = !string.IsNullOrWhiteSpace(query);
        var hasFrom = !string.IsNullOrEmpty(from);
        var hasTo = !string.IsNullOrEmpty(to);
        if (!hasText && !hasFrom && !hasTo)
            return Recent(limit);
        using var connection = Open();
        using var select = connection.CreateCommand();
        var clauses = new List<string>();
        if (hasText)
            clauses.Add("(url LIKE $q OR title LIKE $q)");
        if (hasFrom)
            clauses.Add("visited_date >= $from");
        if (hasTo)
            clauses.Add("visited_date <= $to");
        select.CommandText = $"SELECT id, url, title, visited_at, visited_date FROM visits WHERE {string.Join(" AND ", clauses)} ORDER BY visited_at DESC LIMIT $lim";
        if (hasText)
            select.Parameters.AddWithValue("$q", $"%{query}%");
        if (hasFrom)
            select.Parameters.AddWithValue("$from", from);
        if (hasTo)
            select.Parameters.AddWithValue("$to", to);
        select.Parameters.AddWithValue("$lim", limit);
        using var reader = select.ExecuteReader();
        return ReadEntries(reader);
    }

    /// <summary>删除单条历史（不可恢复——UI 层负责确认）。</summary>
    public bool Delete(long id)
    {
        using var connection = Open();
        using var delete = connection.CreateCommand();
        delete.CommandText = "DELETE FROM visits WHERE id = $id";
        delete.Parameters.AddWithValue("$id", id);
        return delete.ExecuteNonQuery() > 0;
    }

    /// <summary>清空全部历史（不可恢复——UI 层负责确认）。</summary>
    public void Clear()
    {
        using var connection = Open();
        using var delete = connection.CreateCommand();
        delete.CommandText = "DELETE FROM visits";
        delete.ExecuteNonQuery();
    }

    private IReadOnlyList<HistoryEntry> Read(string sql, int limit)
    {
        using var connection = Open();
        using var select = connection.CreateCommand();
        select.CommandText = sql;
        select.Parameters.AddWithValue("$lim", limit);
        using var reader = select.ExecuteReader();
        return ReadEntries(reader);
    }

    private static List<HistoryEntry> ReadEntries(SqliteDataReader reader)
    {
        var list = new List<HistoryEntry>();
        while (reader.Read())
        {
            var visitedAt = reader.IsDBNull(3) ? string.Empty : reader.GetString(3);
            var visitedDate = reader.IsDBNull(4) ? string.Empty : reader.GetString(4);
            list.Add(new HistoryEntry(
                reader.GetInt64(0),
                reader.IsDBNull(1) ? string.Empty : reader.GetString(1),
                reader.IsDBNull(2) ? string.Empty : reader.GetString(2),
                visitedAt,
                visitedDate));
        }
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
                CREATE TABLE IF NOT EXISTS visits(
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    url TEXT NOT NULL,
                    title TEXT NOT NULL DEFAULT '',
                    visited_at TEXT NOT NULL,
                    visited_date TEXT NOT NULL DEFAULT '');
                """;
            ensure.ExecuteNonQuery();
            MigrateAddVisitedDate(connection);
            // 性能索引：按日期/时间查询与排序走索引（千条级数据毫秒返回）
            using (var index = connection.CreateCommand())
            {
                index.CommandText = """
                    CREATE INDEX IF NOT EXISTS idx_visits_date_time
                        ON visits(visited_date, visited_at DESC);
                    """;
                index.ExecuteNonQuery();
            }
            // 失效空日期行归一（迁移回填遗漏的残留——归为「未知日期」以免分组遗漏）
            using (var sanitize = connection.CreateCommand())
            {
                sanitize.CommandText = "UPDATE visits SET visited_date = '未知日期' WHERE visited_date = '' OR visited_date IS NULL";
                sanitize.ExecuteNonQuery();
            }
            return connection;
        }
        catch
        {
            connection.Dispose();
            throw;
        }
    }

    /// <summary>旧库迁移：visits 无 visited_date 列时补列（新安装直接建表含列）。</summary>
    private static void MigrateAddVisitedDate(SqliteConnection connection)
    {
        bool hasColumn;
        using (var pragma = connection.CreateCommand())
        {
            pragma.CommandText = "PRAGMA table_info(visits)";
            using var reader = pragma.ExecuteReader();
            hasColumn = false;
            while (reader.Read())
            {
                if (string.Equals(reader.GetString(1), "visited_date", StringComparison.OrdinalIgnoreCase))
                {
                    hasColumn = true;
                    break;
                }
            }
        }
        if (hasColumn)
            return;
        using var alter = connection.CreateCommand();
        alter.CommandText = "ALTER TABLE visits ADD COLUMN visited_date TEXT NOT NULL DEFAULT ''";
        alter.ExecuteNonQuery();
        // 回填已存在行：由 visited_at 推导本地日期（已存储 ISO，取前 10 位）
        using var backfill = connection.CreateCommand();
        backfill.CommandText = "UPDATE visits SET visited_date = substr(visited_at, 1, 10) WHERE visited_date = '' OR visited_date IS NULL";
        backfill.ExecuteNonQuery();
    }
}

/// <summary>历史条目（含本地日期 yyyy-MM-dd 与 ISO 时刻——UI 分组/按日查询用）。</summary>
public sealed record HistoryEntry(long Id, string Url, string Title, string VisitedAt, string VisitedDate);

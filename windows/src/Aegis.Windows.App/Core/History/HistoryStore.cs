namespace Aegis.Windows.Core.History;

using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using Microsoft.Data.Sqlite;

/// <summary>历史记录（ADR-009 D2：SQLite）。升级版支持：
/// - 每次访问记录 UTC 时刻 + 本地日期（visited_at 为 UTC round-trip ISO——
///   CS-090：本地时字符串在 DST 回拨时段按字典序排序错位；visited_date 仍为
///   本地 yyyy-MM-dd——按日分组口径不变）；
/// - 按日期查询 / 文本+日期组合查询 / 单条删除 / 日期列表；
/// - 全部外部输入走参数绑定（安全约束：不拼接 SQL）；用户搜索词中的
///   LIKE 通配符（%/_/\）转义为字面量——通配符注入不改变搜索语义。
/// 敏感口径：title/url 存储不含 query secret 的承诺由调用方保证。
/// 建表/迁移/索引只在该库的进程首次打开时执行一次（此前每次 Add/查询
/// 都跑 5 条 DDL/DML——每次导航的纯开销）。</summary>
public sealed class HistoryStore
{
    private const int MaxRows = 50000;
    private const int PruneEveryAdds = 256;
    // CS-319（2026-09-26 审计）：库层统一长度上限——BookmarkImporter 有
    // 2048/256 上限而手写路径（Star_Click 直 Add）无上限可写入任意长串；
    // 与导入口径锁定（代理对安全截断）
    // CS-369（2026-10-01 审计）：常量与截断实现单源化到 Core.TextLimits
    //（此前与 BookmarkImporter/BookmarkManagerWindow 三处独立维护）；
    // 本处保留同义转发（既有测试引用 HistoryStore.MaxUrlChars/ClampText）
    internal const int MaxUrlChars = TextLimits.MaxUrlChars;
    internal const int MaxTitleChars = TextLimits.MaxTitleChars;

    private static readonly ConcurrentDictionary<string, byte> InitializedDbs = new(StringComparer.OrdinalIgnoreCase);
    // CS-091：双检锁宿主换成独立锁对象——锁 ConcurrentDictionary 实例与其
    // 自身内部锁语义混淆，且锁粒度无理由绑定集合身份
    private static readonly object InitLock = new();
    // CS-085：目录只建一次（静态记录）——此前每次 Open 都 Directory.CreateDirectory
    private static readonly ConcurrentDictionary<string, byte> CreatedDirectories = new(StringComparer.OrdinalIgnoreCase);
    private readonly string _dbPath;
    private readonly int _maxRows;
    private readonly int _pruneEveryAdds;
    private int _addCounter;

    public HistoryStore(string dbPath)
        : this(dbPath, MaxRows, PruneEveryAdds) { }

    /// <summary>CS-084：修剪阈值注入——常态 50k 行/256 次触发离线不可测，
    /// 测试以小阈值直测修剪行为（不改变生产路径）。</summary>
    internal HistoryStore(string dbPath, int maxRows, int pruneEveryAdds)
    {
        _dbPath = dbPath;
        _maxRows = Math.Max(1, maxRows);
        _pruneEveryAdds = Math.Max(1, pruneEveryAdds);
    }

    /// <summary>记录一次访问（追加——历史按次数累积；UTC 时刻+本地日期）。
    /// 返回是否真实写入（导入计数用）。磁盘异常不向导航事件上抛（此前
    /// SQLite 异常会沿 NavigationCompleted 触发全局未处理异常弹窗）——
    /// 记录日志后丢弃本条。</summary>
    public bool Add(string url, string title)
    {
        if (string.IsNullOrWhiteSpace(url))
            return false;
        try
        {
            var now = DateTime.Now;
            using var connection = Open();
            using var insert = connection.CreateCommand();
            insert.CommandText = """
                INSERT INTO visits(url, title, visited_at, visited_date)
                VALUES($u,$t,$v,$d)
                """;
            insert.Parameters.AddWithValue("$u", ClampText(url, MaxUrlChars));
            insert.Parameters.AddWithValue("$t", ClampText(title ?? string.Empty, MaxTitleChars));
            insert.Parameters.AddWithValue("$v", DateTime.UtcNow.ToString("o", CultureInfo.InvariantCulture));
            // CS-089：InvariantCulture——部分文化默认日历（佛历/回历等）会把
            // "yyyy" 格式化为非公历年，按日分组随之整体漂移
            insert.Parameters.AddWithValue("$d", now.ToString("yyyy-MM-dd", CultureInfo.InvariantCulture));
            insert.ExecuteNonQuery();
            // 有界保留：定期修剪最旧记录（常年使用不无界增长）
            if (System.Threading.Interlocked.Increment(ref _addCounter) % _pruneEveryAdds == 0)
            {
                using var prune = connection.CreateCommand();
                prune.CommandText = "DELETE FROM visits WHERE id NOT IN (SELECT id FROM visits ORDER BY id DESC LIMIT $max)";
                prune.Parameters.AddWithValue("$max", _maxRows);
                prune.ExecuteNonQuery();
            }
            return true;
        }
        catch (Exception ex)
        {
            Security.SecurityLog.Write(
                $"[history] 记录写入失败（丢弃本条）: {ex.GetType().Name}: {ex.Message}");
            return false;
        }
    }

    /// <summary>CS-028（审计 2026-09-25）：LIMIT 绑定值统一下界钳制——SQLite
    /// LIMIT 负值语义为"无上限"，此前 limit<=0 直接进 SQL（无界返回/无界内存）。</summary>
    private static int ClampLimit(int limit) => Math.Max(1, limit);

    /// <summary>CS-399（2026-10-02 审计）：批量导入——单连接 + 事务 + 每 256 条
    /// 修剪（与 Add 的 PruneEveryAdds 同口径）。此前 HistoryImporter.ImportTo
    /// 逐条调 Add（每条新开 SQLite 连接再关闭；千条导入即千次连接建立）。
    /// 返回真实写入条数（空白 URL 跳过）；磁盘异常吞掉并回滚（导入是可选
    /// 功能——异常时事务整体回滚，无半批状态）。</summary>
    public int ImportBatch(IEnumerable<(string Url, string Title)> rows)
    {
        var written = 0;
        try
        {
            using var connection = Open();
            using var transaction = connection.BeginTransaction();
            using var insert = connection.CreateCommand();
            insert.Transaction = transaction;
            insert.CommandText = """
                INSERT INTO visits(url, title, visited_at, visited_date)
                VALUES($u,$t,$v,$d)
                """;
            var urlParam = insert.Parameters.Add("$u", SqliteType.Text);
            var titleParam = insert.Parameters.Add("$t", SqliteType.Text);
            var atParam = insert.Parameters.Add("$v", SqliteType.Text);
            var dateParam = insert.Parameters.Add("$d", SqliteType.Text);
            var counter = 0;
            foreach (var (url, title) in rows)
            {
                if (string.IsNullOrWhiteSpace(url))
                    continue;
                var now = DateTime.Now;
                urlParam.Value = ClampText(url, MaxUrlChars);
                titleParam.Value = ClampText(title ?? string.Empty, MaxTitleChars);
                atParam.Value = DateTime.UtcNow.ToString("o", CultureInfo.InvariantCulture);
                // CS-089：InvariantCulture——部分文化默认日历会把 yyyy 漂移
                dateParam.Value = now.ToString("yyyy-MM-dd", CultureInfo.InvariantCulture);
                insert.ExecuteNonQuery();
                written++;
                if (++counter % _pruneEveryAdds == 0)
                    PruneWithinBatch(connection, transaction);
            }
            PruneWithinBatch(connection, transaction);  // 尾部收口（对齐 _maxRows）
            transaction.Commit();
            return written;
        }
        catch (Exception ex)
        {
            Security.SecurityLog.Write(
                $"[history] 批量导入失败（事务回滚，无半批状态）: {ex.GetType().Name}: {ex.Message}");
            return 0;
        }
    }

    /// <summary>CS-399：批内有界保留修剪（与 Add 的周期修剪同一条 SQL）。</summary>
    private void PruneWithinBatch(Microsoft.Data.Sqlite.SqliteConnection connection, Microsoft.Data.Sqlite.SqliteTransaction transaction)
    {
        using var prune = connection.CreateCommand();
        prune.Transaction = transaction;
        prune.CommandText = "DELETE FROM visits WHERE id NOT IN (SELECT id FROM visits ORDER BY id DESC LIMIT $max)";
        prune.Parameters.AddWithValue("$max", _maxRows);
        prune.ExecuteNonQuery();
    }

    /// <summary>CS-319：代理对安全截断（emoji 等增补平面字符不劈成孤立代理）。
    /// 提 internal 供直测；CS-369 起实现单源在 Core.TextLimits.Clamp。</summary>
    internal static string ClampText(string text, int maxChars) =>
        TextLimits.Clamp(text, maxChars);

    /// <summary>最近访问（时间倒序）。
    /// CS-301（2026-09-26 审计）：补 id 决胜列——分页查询均有 ", id DESC" 而
    /// 此处没有：同一秒多条记录时列表与分页顺序不一致（可能重复跳行）。</summary>
    internal IReadOnlyList<HistoryEntry> Recent(int limit = 200)
    {
        using var connection = Open();
        using var select = connection.CreateCommand();
        select.CommandText = "SELECT id, url, title, visited_at, visited_date FROM visits ORDER BY visited_at DESC, id DESC LIMIT $lim";
        select.Parameters.AddWithValue("$lim", ClampLimit(limit));
        using var reader = select.ExecuteReader();
        return ReadEntries(reader);
    }
    /// <summary>按 URL 子串查询（时间倒序）。
    /// CS-401（2026-10-02 审计）：建议控制器消费口径单源——此前其 SQL 侧用
    /// Search（url OR title 双列命中），MergeRows 又只保留 URL 命中行，标题
    /// 命中的行白白查询传输；按 ChromeControllersTests 锁定的「历史仅 URL
    /// 命中」口径在 SQL 侧收窄。LIKE 大小写语义与 Search 相同（仅 ASCII
    /// 不区分——非 ASCII 精确匹配）。</summary>
    public IReadOnlyList<HistoryEntry> SearchByUrl(string query, int limit = 200)
    {
        if (string.IsNullOrWhiteSpace(query))
            return Recent(limit);
        using var connection = Open();
        using var select = connection.CreateCommand();
        select.CommandText = """
            SELECT id, url, title, visited_at, visited_date FROM visits
            WHERE url LIKE $q ESCAPE '\' ORDER BY visited_at DESC, id DESC LIMIT $lim
            """;
        select.Parameters.AddWithValue("$q", $"%{HistoryFilter.LikeEscape(query)}%");
        select.Parameters.AddWithValue("$lim", ClampLimit(limit));
        using var reader = select.ExecuteReader();
        return ReadEntries(reader);
    }
    /// <summary>统计匹配筛选的访问总数（页码分页用——分页条显示总页数）。</summary>
    public long Count(string? query, string? from, string? to)
    {
        var filter = HistoryFilter.Build(query, from, to);
        using var connection = Open();
        using var select = connection.CreateCommand();
        select.CommandText = "SELECT COUNT(*) FROM visits" +
            (filter.IsEmpty ? "" : " WHERE " + filter.WhereSql);
        filter.Bind(select, query, from, to);
        return Convert.ToInt64(select.ExecuteScalar());
    }

    /// <summary>按页查询（页码分页：OFFSET 跳页）。排序 (visited_at, id) 倒序。
    /// 空筛选回退 Recent（同 offset 逻辑）。全部参数绑定。</summary>
    public IReadOnlyList<HistoryEntry> SearchRangePage(string? query, string? from, string? to,
        int pageSize, int offset)
    {
        var filter = HistoryFilter.Build(query, from, to);
        if (filter.IsEmpty)
            return RecentPage(pageSize, offset);
        using var connection = Open();
        using var select = connection.CreateCommand();
        select.CommandText = "SELECT id, url, title, visited_at, visited_date FROM visits WHERE " +
            filter.WhereSql +
            " ORDER BY visited_at DESC, id DESC LIMIT $ps OFFSET $off";
        filter.Bind(select, query, from, to);
        select.Parameters.AddWithValue("$ps", Math.Max(1, pageSize));
        select.Parameters.AddWithValue("$off", Math.Max(0, offset));
        using var reader = select.ExecuteReader();
        return ReadEntries(reader);
    }

    /// <summary>最近访问按页查询（页码分页空筛选路径）。</summary>
    internal IReadOnlyList<HistoryEntry> RecentPage(int pageSize, int offset)
    {
        using var connection = Open();
        using var select = connection.CreateCommand();
        select.CommandText = "SELECT id, url, title, visited_at, visited_date FROM visits ORDER BY visited_at DESC, id DESC LIMIT $ps OFFSET $off";
        select.Parameters.AddWithValue("$ps", Math.Max(1, pageSize));
        select.Parameters.AddWithValue("$off", Math.Max(0, offset));
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
        // CS-085：目录只建一次（静态记录命中后跳过系统调用；CreateDirectory 幂等）
        var directory = Path.GetDirectoryName(_dbPath);
        if (!string.IsNullOrEmpty(directory) && CreatedDirectories.TryAdd(directory, 1))
            Directory.CreateDirectory(directory);
        var connection = new SqliteConnection(new SqliteConnectionStringBuilder
        {
            DataSource = _dbPath,
            Mode = SqliteOpenMode.ReadWriteCreate,
            // Pooling=false 的权衡（CS-086）：连接不进池——db 文件不被进程长期
            // 锁定（妨碍备份/删除/单测直接删库）；代价是每次开连接约几十微秒，
            // 导航频率下可忽略。与其余三库同口径。
            Pooling = false,
        }.ToString());
        try
        {
            connection.Open();
            // CS-099：busy_timeout 与其余三库统一——历史窗口查询与导航写入
            // 并发时快速忙等重试，而非默认即抛 "database is locked"
            using (var busy = connection.CreateCommand())
            {
                busy.CommandText = "PRAGMA busy_timeout=5000";
                busy.ExecuteNonQuery();
            }
            EnsureSchema(connection);
            return connection;
        }
        catch
        {
            connection.Dispose();
            throw;
        }
    }

    /// <summary>建表/迁移/索引/清洗——每库每进程仅执行一次（此前每次打开连接
    /// 都执行 5 条 DDL/DML，每次导航完成的纯开销）。</summary>
    private void EnsureSchema(SqliteConnection connection)
    {
        if (InitializedDbs.ContainsKey(_dbPath))
            return;
        lock (InitLock)
        {
            if (InitializedDbs.ContainsKey(_dbPath))
                return;
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
            using (var timeIndex = connection.CreateCommand())
            {
                // 纯时间倒序查询（Recent/Search 默认排序）的配套索引——此前
                // 仅有 (date,time) 复合索引，该路径走不上索引需额外排序
                timeIndex.CommandText = """
                    CREATE INDEX IF NOT EXISTS idx_visits_time_id
                        ON visits(visited_at DESC, id DESC);
                    """;
                timeIndex.ExecuteNonQuery();
            }
            // 失效空日期行归一（迁移回填遗漏的残留——归为「未知日期」以免分组遗漏）
            using (var sanitize = connection.CreateCommand())
            {
                sanitize.CommandText = "UPDATE visits SET visited_date = '未知日期' WHERE visited_date = '' OR visited_date IS NULL";
                sanitize.ExecuteNonQuery();
            }
            InitializedDbs[_dbPath] = 1;
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

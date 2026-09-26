namespace Aegis.Windows.Core.Tabs;

using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using Microsoft.Data.Sqlite;

/// <summary>标签会话持久化（ADR-009 D2：数据层统一 SQLite）。纯存储——
/// 无 UI/WebView 依赖（dbPath 注入，可单测）。含 is_pinned 列（固定标签跨会话），
/// 旧库自动迁移补列。恢复 URL 的安全校验不在此层——导航本身经 broker 决策，
/// 本层只负责忠实存取（防御纵深：篡改的会话文件最坏触发 broker 拒绝+错误页）。</summary>
public sealed class TabSessionStore
{
    private readonly string _dbPath;
    // CS-030（审计 2026-09-25）：DDL+迁移 once——此前每次 Open 都跑
    // CREATE TABLE + PRAGMA table_info 迁移探测（低频库的纯开销）。
    // 失败不置位——下次重试。
    private volatile bool _schemaReady;

    public TabSessionStore(string dbPath) => _dbPath = dbPath;

    /// <summary>会话行（含固定态）。</summary>
    public sealed record SessionTab(string TabId, string Url, string Title, bool IsPinned);

    /// <summary>保存当前会话（先清后写——小表全量重写最简且无增量漂移）。
    /// 磁盘异常不上抛（每次导航完成都会调用——此前磁盘满/库被锁时每次导航
    /// 弹一次全局异常）——记录日志后放弃本次快照。</summary>
    public void Save(IReadOnlyList<Tab> tabs, string? currentTabId)
    {
        try
        {
            using var connection = Open();
            using var transaction = connection.BeginTransaction();
            using (var clear = connection.CreateCommand())
            {
                clear.Transaction = transaction;
                clear.CommandText = "DELETE FROM tabs";
                clear.ExecuteNonQuery();
            }
            for (var i = 0; i < tabs.Count; i++)
            {
                using var insert = connection.CreateCommand();
                insert.Transaction = transaction;
                insert.CommandText = """
                    INSERT INTO tabs(position, tab_id, url, title, is_current, is_pinned)
                    VALUES($p,$t,$u,$ti,$c,$pin)
                    """;
                insert.Parameters.AddWithValue("$p", i);
                insert.Parameters.AddWithValue("$t", tabs[i].TabId);
                insert.Parameters.AddWithValue("$u", tabs[i].Url);
                insert.Parameters.AddWithValue("$ti", tabs[i].Title);
                insert.Parameters.AddWithValue("$c", tabs[i].TabId == currentTabId ? 1 : 0);
                insert.Parameters.AddWithValue("$pin", tabs[i].IsPinned ? 1 : 0);
                insert.ExecuteNonQuery();
            }
            transaction.Commit();
        }
        catch (Exception ex)
        {
            Security.SecurityLog.Write(
                $"[session] 会话保存失败（放弃本次快照）: {ex.GetType().Name}: {ex.Message}");
        }
    }

    /// <summary>加载上次会话；无记录/库损坏返回空（fail-safe——不阻断启动）。
    /// is_current 丢失（旧库/异常）时回退末位标签。</summary>
    public IReadOnlyList<SessionTab> Load() => Load(out _);

    public IReadOnlyList<SessionTab> Load(out string? currentTabId)
    {
        currentTabId = null;
        if (!File.Exists(_dbPath))
            return Array.Empty<SessionTab>();
        try
        {
            using var connection = Open();
            using var select = connection.CreateCommand();
            // CS-186：position 不再 SELECT（仅作排序键）——读取列数减一
            select.CommandText = "SELECT tab_id, url, title, is_current, is_pinned FROM tabs ORDER BY position";
            using var reader = select.ExecuteReader();
            var tabs = new List<SessionTab>();
            while (reader.Read())
            {
                var tab = new SessionTab(
                    reader.GetString(0),
                    reader.IsDBNull(1) ? string.Empty : reader.GetString(1),
                    reader.IsDBNull(2) ? "新标签页" : reader.GetString(2),
                    !reader.IsDBNull(4) && reader.GetInt64(4) == 1);
                tabs.Add(tab);
                if (!reader.IsDBNull(3) && reader.GetInt64(3) == 1)
                    currentTabId = tab.TabId;
            }
            currentTabId ??= tabs.LastOrDefault()?.TabId;
            return tabs;
        }
        catch (Exception ex) when (ex is SqliteException or IOException or InvalidOperationException)
        {
            Security.SecurityLog.Write(
                $"[session] 会话读取失败（回退空会话）: {ex.GetType().Name}: {ex.Message}");
            return Array.Empty<SessionTab>();  // 库损坏 → 空会话（不阻断启动——fail-safe）
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
            // 会话库为低频小表读写——连接池会让 db 文件被进程长期锁定
            // （妨碍备份/删除/升级迁移），显式关闭（单测暴露的真实问题）
            Pooling = false,
        }.ToString());
        try
        {
            connection.Open();
            // CS-099：busy_timeout 与其余三库统一——并发写时快速忙等重试
            using (var busy = connection.CreateCommand())
            {
                busy.CommandText = "PRAGMA busy_timeout=5000";
                busy.ExecuteNonQuery();
            }
            if (!_schemaReady)
            {
                using var ensure = connection.CreateCommand();
                ensure.CommandText = """
                    CREATE TABLE IF NOT EXISTS tabs(
                        position INTEGER NOT NULL,
                        tab_id TEXT NOT NULL,
                        url TEXT NOT NULL,
                        title TEXT NOT NULL,
                        is_current INTEGER NOT NULL DEFAULT 0,
                        is_pinned INTEGER NOT NULL DEFAULT 0)
                    """;
                ensure.ExecuteNonQuery();
                // 旧库迁移：补 is_pinned 列
                var hasPinned = false;
                using (var pragma = connection.CreateCommand())
                {
                    pragma.CommandText = "PRAGMA table_info(tabs)";
                    using var reader = pragma.ExecuteReader();
                    while (reader.Read())
                        if (string.Equals(reader.GetString(1), "is_pinned", StringComparison.OrdinalIgnoreCase))
                            hasPinned = true;
                }
                if (!hasPinned)
                {
                    using var alter = connection.CreateCommand();
                    alter.CommandText = "ALTER TABLE tabs ADD COLUMN is_pinned INTEGER NOT NULL DEFAULT 0";
                    alter.ExecuteNonQuery();
                }
                _schemaReady = true;
            }
            return connection;
        }
        catch
        {
            // 建表失败（如库损坏）时若不释放已打开的连接，db 文件句柄泄漏
            connection.Dispose();
            throw;
        }
    }
}

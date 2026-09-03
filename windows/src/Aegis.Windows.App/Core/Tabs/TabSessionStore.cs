namespace Aegis.Windows.Core.Tabs;

using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using Microsoft.Data.Sqlite;

/// <summary>标签会话持久化（ADR-009 D2：数据层统一 SQLite）。纯存储——
/// 无 UI/WebView 依赖（dbPath 注入，可单测）。恢复 URL 的安全校验不在此层
/// ——导航本身经 broker 决策（NavigationStarting 强制），本层只负责忠实
/// 存取（防御纵深：篡改的会话文件最坏触发 broker 拒绝+错误页，不会绕过门禁）。</summary>
public sealed class TabSessionStore
{
    private readonly string _dbPath;

    public TabSessionStore(string dbPath) => _dbPath = dbPath;

    /// <summary>保存当前会话（先清后写——小表全量重写最简且无增量漂移）。</summary>
    public void Save(IReadOnlyList<Tab> tabs, string? currentTabId)
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
            insert.CommandText = "INSERT INTO tabs(position, tab_id, url, title, is_current) VALUES($p,$t,$u,$ti,$c)";
            insert.Parameters.AddWithValue("$p", i);
            insert.Parameters.AddWithValue("$t", tabs[i].TabId);
            insert.Parameters.AddWithValue("$u", tabs[i].Url);
            insert.Parameters.AddWithValue("$ti", tabs[i].Title);
            insert.Parameters.AddWithValue("$c", tabs[i].TabId == currentTabId ? 1 : 0);
            insert.ExecuteNonQuery();
        }
        transaction.Commit();
    }

    /// <summary>加载上次会话；无记录/库损坏返回空（fail-safe——不阻断启动）。
    /// is_current 丢失（旧库/异常）时回退末位标签。</summary>
    public IReadOnlyList<Tab> Load() => Load(out _);

    public IReadOnlyList<Tab> Load(out string? currentTabId)
    {
        currentTabId = null;
        if (!System.IO.File.Exists(_dbPath))
            return Array.Empty<Tab>();
        try
        {
            using var connection = Open();
            using var select = connection.CreateCommand();
            select.CommandText = "SELECT position, tab_id, url, title, is_current FROM tabs ORDER BY position";
            using var reader = select.ExecuteReader();
            var tabs = new List<Tab>();
            while (reader.Read())
            {
                var tab = new Tab(
                    reader.GetString(1),
                    reader.IsDBNull(2) ? string.Empty : reader.GetString(2),
                    reader.IsDBNull(3) ? "新标签页" : reader.GetString(3));
                tabs.Add(tab);
                if (!reader.IsDBNull(4) && reader.GetInt64(4) == 1)
                    currentTabId = tab.TabId;
            }
            currentTabId ??= tabs.LastOrDefault()?.TabId;
            return tabs;
        }
        catch (SqliteException)
        {
            return Array.Empty<Tab>();  // 库损坏 → 空会话（不阻断启动——fail-safe）
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
            using var ensure = connection.CreateCommand();
            ensure.CommandText = """
                CREATE TABLE IF NOT EXISTS tabs(
                    position INTEGER NOT NULL,
                    tab_id TEXT NOT NULL,
                    url TEXT NOT NULL,
                    title TEXT NOT NULL,
                    is_current INTEGER NOT NULL DEFAULT 0)
                """;
            ensure.ExecuteNonQuery();
            return connection;
        }
        catch
        {
            // 单测暴露的真实缺陷：建表失败（如库损坏）时若不释放已打开的
            // 连接，db 文件句柄泄漏（后续备份/删除被锁定）。释放后原样抛出。
            connection.Dispose();
            throw;
        }
    }
}

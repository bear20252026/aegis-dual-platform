namespace Aegis.Windows.Core.History;

using System.Collections.Generic;
using System.Text;
using Microsoft.Data.Sqlite;

/// <summary>历史查询筛选子句单源（CS-087：此前 SearchRange/Count/SearchRangePage/
/// SearchRangePaged 四处重复构建同形 WHERE——文本+日期区间组合，一处改三处漏）。
/// 文本子句对 url/title 各绑定一次（$q/$t），日期为本地 yyyy-MM-dd 字面量比较。</summary>
internal readonly record struct HistoryFilter(string WhereSql, bool HasText, bool HasFrom, bool HasTo)
{
    /// <summary>空筛选（无任何子句——调用方回退 Recent/RecentPage 路径）。</summary>
    public bool IsEmpty => WhereSql.Length == 0;

    public static HistoryFilter Build(string? query, string? from, string? to)
    {
        var hasText = !string.IsNullOrWhiteSpace(query);
        var hasFrom = !string.IsNullOrEmpty(from);
        var hasTo = !string.IsNullOrEmpty(to);
        var clauses = new List<string>(3);
        if (hasText) clauses.Add("(url LIKE $q ESCAPE '\\' OR title LIKE $t ESCAPE '\\')");
        if (hasFrom) clauses.Add("visited_date >= $from");
        if (hasTo) clauses.Add("visited_date <= $to");
        return new HistoryFilter(string.Join(" AND ", clauses), hasText, hasFrom, hasTo);
    }

    /// <summary>把 Build 对应的绑定值挂到命令上（调用方自行绑定 $lim/$off 等分页参数）。</summary>
    public void Bind(SqliteCommand command, string? query, string? from, string? to)
    {
        if (HasText)
        {
            var pattern = $"%{LikeEscape(query ?? string.Empty)}%";
            command.Parameters.AddWithValue("$q", pattern);
            command.Parameters.AddWithValue("$t", pattern);
        }
        if (HasFrom) command.Parameters.AddWithValue("$from", from);
        if (HasTo) command.Parameters.AddWithValue("$to", to);
    }

    /// <summary>LIKE 绑定值转义：%/_/\ 作为字面量匹配（用户搜索 "%报告" 时
    /// % 被当通配符会改变搜索语义）。CS-092：单遍扫描替代三连 Replace
    /// （每次全串扫描+中间串分配）。</summary>
    internal static string LikeEscape(string query)
    {
        var builder = new StringBuilder(query.Length + 8);
        foreach (var ch in query)
        {
            if (ch is '\\' or '%' or '_')
                builder.Append('\\');
            builder.Append(ch);
        }
        return builder.ToString();
    }
}

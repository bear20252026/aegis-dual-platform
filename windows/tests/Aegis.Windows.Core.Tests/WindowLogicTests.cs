namespace Aegis.Windows.Core.Tests;

using System.Windows;
using Aegis.Windows.Core;
using Xunit;

/// <summary>C13 批（审计 2026-09-26）：独立窗口纯函数面直测——历史 host 提取
/// （CS-161）、书签过滤谓词（CS-165）、睡眠下拉索引（CS-169）、日历周偏移
/// （CS-176）。仅触达静态方法（无 STA 依赖）。</summary>
public sealed class WindowLogicTests
{
    // ===== CS-161：HistoryWindow.TryHost =====

    [Theory]
    [InlineData("https://example.com/x?a=1", "example.com")]
    [InlineData("http://Sub.Example.COM/", "sub.example.com")]
    [InlineData("not a url", "not a url")]      // 解析失败原样回退
    [InlineData("about:blank", "about:blank")]  // 无 host 形态原样回退
    public void TryHost_ExtractsHostOrFallsBack(string url, string expected) =>
        Assert.Equal(expected, Aegis.Windows.Chrome.HistoryWindow.TryHost(url));

    // ===== CS-165：BookmarkManagerWindow.MatchesQuery =====

    [Theory]
    [InlineData("示例", "https://a.cn", "示例", true)]           // 标题命中
    [InlineData("标题甲", "https://a.cn", "a.cn", true)]         // URL 命中
    [InlineData("标题甲", "https://a.cn", "甲", true)]           // 单字命中
    [InlineData("标题甲", "https://ABC.cn/x", "abc", true)]      // 大小写不敏感（CS-162）
    [InlineData("标题甲", "https://a.cn", "zzz", false)]         // 未命中
    [InlineData("标题甲", "https://a.cn", null, true)]           // 空查询全过
    [InlineData("标题甲", "https://a.cn", "", true)]
    public void MatchesQuery_TitleOrUrlCaseInsensitive(
        string title, string url, string? query, bool expected) =>
        Assert.Equal(expected,
            Aegis.Windows.Chrome.BookmarkManagerWindow.MatchesQuery(title, url, query));

    // ===== CS-169：SettingsWindow.SleepIndex =====

    [Theory]
    [InlineData(0, 0)]
    [InlineData(15, 1)]
    [InlineData(30, 2)]   // 默认档
    [InlineData(60, 3)]
    [InlineData(99, 2)]   // 非法回退 30 分钟档
    [InlineData(-5, 2)]
    public void SleepIndex_MapsMinutesToComboIndex(int minutes, int expected) =>
        Assert.Equal(expected, Aegis.Windows.Chrome.SettingsWindow.SleepIndex(minutes));

    // ===== CS-176：DateField.MondayOffset =====

    [Theory]
    [InlineData(DayOfWeek.Monday, 0)]     // 周一首列
    [InlineData(DayOfWeek.Sunday, 6)]     // 周日末列
    [InlineData(DayOfWeek.Wednesday, 2)]
    public void MondayOffset_WeekStartsMonday(DayOfWeek day, int expected) =>
        Assert.Equal(expected, Aegis.Windows.Chrome.DateField.MondayOffset(day));
}

/// <summary>C18 批（审计 2026-09-26）：SecurityLog 行为直测（CS-246/247——
/// 目录注入面 + 转义/截断契约）与 AppPaths 测试重置（CS-248）。</summary>
public sealed class SecurityLogTests : IDisposable
{
    private readonly string _dir =
        Path.Combine(Path.GetTempPath(), $"aegis_seclog_{Guid.NewGuid():N}");

    public SecurityLogTests()
    {
        Directory.CreateDirectory(_dir);
        Aegis.Windows.Core.Security.SecurityLog.SecurityLogDirOverride = _dir;
    }

    [Fact]
    public void Write_EscapesNewlines_PreventingInjection()
    {
        // CS-247：换行转义——页面可控字符串不能再注入伪造日志行
        Aegis.Windows.Core.Security.SecurityLog.Write("第一行\r\n第二行\\结束");

        var text = ReadLog();
        Assert.Single(text.Split(Environment.NewLine, StringSplitOptions.RemoveEmptyEntries)
            .Where(l => l.Contains("第一行")));
        Assert.DoesNotContain(text, "第一行" + Environment.NewLine);
    }

    [Fact]
    public void Write_TruncatesOversizedMessages()
    {
        // CS-247：超长消息截断至 4000 + 省略标记
        Aegis.Windows.Core.Security.SecurityLog.Write(new string('x', 5000));

        var text = ReadLog();
        var line = Assert.Single(text.Split(Environment.NewLine, StringSplitOptions.RemoveEmptyEntries)
            .Where(l => l.Contains("xxxx")));
        Assert.True(line.Length < 4100);
        Assert.EndsWith("…(截断)", line);
    }

    private string ReadLog() =>
        File.ReadAllText(Path.Combine(_dir, "security.log"));

    public void Dispose()
    {
        Aegis.Windows.Core.Security.SecurityLog.SecurityLogDirOverride = null;
        try { Directory.Delete(_dir, true); } catch (IOException) { }
    }
}

public sealed class AppPathsTests
{
    [Fact]
    public void ResetForTest_HonorsEnvironmentOverride()
    {
        // CS-248：静态冻结路径经 ResetForTest 可在测试中重定向并还原
        var original = AppPaths.DataDir;
        var temp = Path.Combine(Path.GetTempPath(), $"aegis_paths_{Guid.NewGuid():N}");
        try
        {
            Environment.SetEnvironmentVariable("AEGIS_DATA_DIR", temp);
            AppPaths.ResetForTest();
            Assert.Equal(temp, AppPaths.DataDir);
            Assert.EndsWith("tabs.db", AppPaths.SessionDbPath, StringComparison.Ordinal);
        }
        finally
        {
            Environment.SetEnvironmentVariable("AEGIS_DATA_DIR", null);
            AppPaths.ResetForTest();
            Directory.CreateDirectory(original);  // 确保还原后目录存在性语义不变
            Assert.Equal(original, AppPaths.DataDir);
        }
    }
}

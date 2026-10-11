namespace Aegis.Windows.Core.Tests;

using System;
using System.IO;
using Aegis.Windows.Core.Security;
using Xunit;

/// <summary>Q52（外部第三轮审计 AEG-008）第二半：设置界面那句「上次成功更新 / 是否过期」。
///
/// `ThreatFeedCacheStatus.Describe` 是纯函数，判定与措辞都在这里可单测；界面只负责贴。
/// 本文件同时钉住**接线**本身：Core.Tests 起不了 WPF 窗口，所以对源码文本做静态锚
/// （正向锚 = 保存路径确实经 Active?.RefreshNow()；反向锚 = 「生效于下次启动」这句
/// 已经不再真的话必须从 SettingsWindow 的两个文件里消失——留着它就是谎报）。</summary>
public sealed class ThreatFeedCacheStatusTests
{
    private static readonly DateTimeOffset Now =
        new(2026, 10, 11, 12, 0, 0, TimeSpan.Zero);

    private static readonly TimeSpan StaleAfter = TimeSpan.FromHours(18);   // 3 × 6 小时

    private static string DescribeAt(DateTimeOffset lastWriteUtc) =>
        ThreatFeedCacheStatus.Describe(lastWriteUtc.UtcDateTime, Now, StaleAfter);

    [Fact]
    public void Missing_cache_says_so_instead_of_a_fabricated_time()
    {
        var text = ThreatFeedCacheStatus.Describe(null, Now, StaleAfter);
        Assert.Contains("尚无成功更新记录", text);
        Assert.DoesNotContain("分钟前", text);
    }

    [Theory]
    [InlineData(-0.5, "刚刚")]
    [InlineData(-5, "5 分钟前")]
    [InlineData(-70, "1 小时前")]
    [InlineData(-300, "5 小时前")]
    [InlineData(-30 * 60, "1 天前")]
    public void Age_bands_are_fixed_not_culture_dependent(double minutes, string expected) =>
        Assert.Contains(expected, DescribeAt(Now.AddMinutes(minutes)));

    [Fact]
    public void Only_a_gap_beyond_the_stale_window_is_called_a_failure()
    {
        // 一个周期内的空档是正常节拍，不该吓唬用户；超过 3 倍节拍才算「可能已失效」。
        Assert.DoesNotContain("可能已失效", DescribeAt(Now.AddHours(-2)));
        Assert.Contains("可能已失效", DescribeAt(Now.AddHours(-19)));
        Assert.Contains("已超过预期更新周期", DescribeAt(Now.AddHours(-19)));
    }

    [Fact]
    public void Future_timestamp_is_reported_as_just_now_not_negative_age()
    {
        // 系统时钟被往回调过（或缓存由别处写入更早/更晚时刻）时，绝不能用
        // 「-3 分钟前」这种产物——负数落在 <1 分钟档里显示成「刚刚」。
        Assert.Contains("刚刚", DescribeAt(Now.AddMinutes(3)));
    }

    [Fact]
    public void Join_does_not_invent_empty_punctuation()
    {
        // 分隔符是换行而不是「；」：两侧句子都以「。」结尾，用「；」硬连会产出「。；」
        Assert.Equal("a", ThreatFeedCacheStatus.Join("a", null));
        Assert.Equal("b", ThreatFeedCacheStatus.Join(null, "b"));
        Assert.Equal("a\nb", ThreatFeedCacheStatus.Join("a", "b"));
        Assert.Equal(string.Empty, ThreatFeedCacheStatus.Join(null, null));
        Assert.Equal("a", ThreatFeedCacheStatus.Join("a", string.Empty));
    }

    [Fact]
    public void Opening_the_window_keeps_the_explanation_and_appends_the_status()
    {
        // 界面打开时是「XAML 说明句 + 状态行」两段——把 Text 直接赋成状态行会把说明抹掉
        const string xaml = "每行一个域名的纯文本黑名单（导航与子资源拦截）。";
        Assert.Equal(
            xaml + "\n上次成功更新：刚刚。",
            ThreatFeedCacheStatus.Join(xaml, DescribeAt(Now.AddSeconds(-10))));
    }

    [Fact]
    public void Stale_threshold_comes_from_the_same_constant_as_the_cadence()
    {
        Assert.Equal(3, ThreatFeedCoordinator.StaleAfterFactor);
        Assert.Equal(
            TimeSpan.FromHours(18),
            ThreatFeedCoordinator.DefaultRefreshInterval * ThreatFeedCoordinator.StaleAfterFactor);
        // 界面必须用这两个常量算过期，不许抄一份 18 小时——抄了就会跟节拍悄悄错位。
        var source = ReadChromeFile("SettingsWindow.xaml.cs");
        Assert.Contains("DefaultRefreshInterval", source);
        Assert.Contains("StaleAfterFactor", source);
    }

    // ===== 界面接线锚（起不了 WPF 窗口，只能锚源码文本） =====

    [Fact]
    public void SettingsWindow_wires_the_saved_feed_to_an_immediate_refresh()
    {
        var source = ReadChromeFile("SettingsWindow.xaml.cs");
        Assert.Contains("ThreatFeedCoordinator.Active?.RefreshNow()", source);
        Assert.DoesNotContain(ObsoleteRestartWording, source);
    }

    [Fact]
    public void SettingsWindow_xaml_help_text_no_longer_promises_next_launch()
    {
        Assert.DoesNotContain(
            ObsoleteRestartWording, ReadChromeFile("SettingsWindow.xaml"));
    }

    private const string ObsoleteRestartWording = "生效于下次启动";

    /// <summary>向上定位 Chrome 目录（测试输出层级随 RID 变化，逐级上溯按仓库布局标记定位，
    /// 不依赖固定层数——同款口径见 XamlBindingStaticAnchorTests）。</summary>
    private static string ReadChromeFile(string fileName)
    {
        var dir = new DirectoryInfo(AppContext.BaseDirectory);
        while (dir is not null)
        {
            var candidate = Path.Combine(
                dir.FullName, "windows", "src", "Aegis.Windows.App", "Chrome", fileName);
            if (File.Exists(candidate))
                return File.ReadAllText(candidate);
            dir = dir.Parent!;
        }
        // 显式 throw：Assert.Fail 的 DoesNotReturn 标注会让其后的代码在
        // TreatWarningsAsErrors 下变成 CS0162
        throw new InvalidOperationException($"未定位到 Chrome/{fileName}（仓库布局契约）");
    }
}

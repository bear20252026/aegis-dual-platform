namespace Aegis.Windows.Core.Tests;

using System.Collections.Generic;
using Aegis.Windows.Core;
using Aegis.Windows.Core.Privacy;
using Aegis.Windows.Core.Tabs;
using Xunit;

/// <summary>基础工具类单测（测试缺口批次 1）：ThemeColor 全格式解析回退契约
///（含 10 位 hex 历史事故形态回归——#FFB3FFFFFF 曾两处崩溃）、ZoomStore
/// 边界钳制与归一移除、TrackerList 精确/后缀/大小写语义。</summary>
public class UtilityClassesTests
{
    // ============ ThemeColor ============

    [Theory]
    [InlineData("#FF102030", 0xFF, 0x10, 0x20, 0x30)]   // 8 位 AARRGGBB
    [InlineData("102030", 0xFF, 0x10, 0x20, 0x30)]      // 6 位 RRGGBB（无 #）
    [InlineData("#ABC", 0xFF, 0xAA, 0xBB, 0xCC)]        // 3 位短格式
    [InlineData("#9ABC", 0x99, 0xAA, 0xBB, 0xCC)]       // 4 位 ARGB 短格式
    public void ThemeColor_Parses_AllLegalFormats(string hex, byte a, byte r, byte g, byte b)
    {
        var brush = ThemeColor.ParseBrush(hex);
        Assert.Equal(a, brush.Color.A);
        Assert.Equal(r, brush.Color.R);
        Assert.Equal(g, brush.Color.G);
        Assert.Equal(b, brush.Color.B);
        Assert.True(brush.IsFrozen);
    }

    [Theory]
    [InlineData(null)]
    [InlineData("")]
    [InlineData("   ")]
    [InlineData("#FFB3FFFFFF")]  // 10 位——历史崩溃形态（合法长度仅 3/4/6/8）
    [InlineData("#GGHHII")]      // 非十六进制
    [InlineData("#12345")]       // 5 位
    [InlineData("#1234567890")]  // 10 位数字
    public void ThemeColor_IllegalInput_FallsBackToWhite_NeverThrows(string? hex)
    {
        var brush = ThemeColor.ParseBrush(hex);
        Assert.Equal(0xFF, brush.Color.A);
        Assert.Equal(0xFF, brush.Color.R);
        Assert.Equal(0xFF, brush.Color.G);
        Assert.Equal(0xFF, brush.Color.B);
    }

    // ============ ZoomStore ============

    [Fact]
    public void ZoomStore_Get_MissingOrOutOfRange_FallsBackToOne()
    {
        ZoomStore.Load(new Dictionary<string, double>());
        Assert.Equal(1.0, ZoomStore.Get("unknown.example"));
        // 低于最小值的历史遗留数据回退 1.0（脏数据防御）
        ZoomStore.Load(new Dictionary<string, double> { ["a.example"] = 0.05 });
        Assert.Equal(1.0, ZoomStore.Get("a.example"));
    }

    [Fact]
    public void ZoomStore_Set_ClampsToUnifiedBounds_AndNormalizesOne()
    {
        ZoomStore.Load(new Dictionary<string, double>());
        ZoomStore.Set("b.example", 9.9);
        Assert.Equal(ZoomStore.MaxZoom, ZoomStore.Get("b.example"));
        ZoomStore.Set("b.example", 0.01);
        Assert.Equal(ZoomStore.MinZoom, ZoomStore.Get("b.example"));
        // 1.0 归一移除（不存冗余项）
        ZoomStore.Set("b.example", 1.0);
        Assert.Empty(ZoomStore.Snapshot());
        // null/空 host 不抛
        ZoomStore.Set(null!, 1.5);
        ZoomStore.Set("", 1.5);
    }

    [Fact]
    public void ZoomStore_Set_FiresChangedOnce()
    {
        ZoomStore.Load(new Dictionary<string, double>());
        var fired = 0;
        ZoomStore.Changed += OnChanged;
        try
        {
            ZoomStore.Set("c.example", 1.5);
            ZoomStore.Set("c.example", 1.25);
            ZoomStore.Set("c.example", 1.25);  // 同值重复写仍通知（幂等但语义不丢）
            Assert.Equal(3, fired);
        }
        finally
        {
            ZoomStore.Changed -= OnChanged;
        }
        return;
        void OnChanged() => fired++;
    }

    [Fact]
    public void ZoomStore_Get_HostCaseInsensitive()
    {
        ZoomStore.Load(new Dictionary<string, double> { ["Example.COM"] = 1.75 });
        Assert.Equal(1.75, ZoomStore.Get("example.com"));
    }

    // ============ TrackerList ============

    [Theory]
    [InlineData("doubleclick.net")]           // 精确命中
    [InlineData("a.doubleclick.net")]         // 子域后缀命中
    [InlineData("AD.DoubleClick.Net")]        // 大小写不敏感
    [InlineData("stats.g.doubleclick.net.")]  // 多级子域 + 尾点
    public void TrackerList_MatchesTrackerHosts(string host)
    {
        Assert.True(TrackerList.IsTracker(host));
    }

    [Theory]
    [InlineData(null)]
    [InlineData("")]
    [InlineData("example.com")]
    [InlineData("notdoubleclick.net")]        // 前缀伪装不误报（非后缀域）
    [InlineData("doubleclick.net.evil.io")]   // 清单域作子串前缀不误报
    public void TrackerList_NonTrackerHosts_Pass(string? host)
    {
        Assert.False(TrackerList.IsTracker(host!));
    }
}

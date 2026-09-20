namespace Aegis.Windows.Core.Tests;

using Aegis.Windows.Chrome;
using Xunit;

/// <summary>缩放步进策略单测（上帝对象拆分·第七批）——增量叠加与边界钳制
/// [MinZoom, MaxZoom]，对齐会话内与持久化统一口径（0.25–3.0）。</summary>
public class ZoomPolicyTests
{
    [Fact]
    public void Stepping_Accumulates()
    {
        Assert.Equal(1.1, ZoomPolicy.ApplyStep(1.0, 0.1), 3);
        Assert.Equal(1.0, ZoomPolicy.ApplyStep(1.1, -0.1), 3);
    }

    [Theory]
    [InlineData(0.24)]   // 低于下限
    [InlineData(0.25)]   // 下限本身
    [InlineData(3.0)]    // 上限本身
    [InlineData(3.01)]   // 高于上限
    [InlineData(-5.0)]
    [InlineData(99.0)]
    public void Stepping_ClampsToUnifiedBounds(double current)
    {
        var stepped = ZoomPolicy.ApplyStep(current, 0.0);
        Assert.InRange(stepped, TabRuntime.MinZoom, TabRuntime.MaxZoom);
    }

    [Fact]
    public void ZoomInto_SaturatesAtMax_NotBelow()
    {
        Assert.Equal(TabRuntime.MaxZoom, ZoomPolicy.ApplyStep(TabRuntime.MaxZoom, 0.5));
        Assert.Equal(TabRuntime.MaxZoom, ZoomPolicy.ApplyStep(2.9, 0.5));
        Assert.Equal(TabRuntime.MinZoom, ZoomPolicy.ApplyStep(TabRuntime.MinZoom, -10));
    }
}
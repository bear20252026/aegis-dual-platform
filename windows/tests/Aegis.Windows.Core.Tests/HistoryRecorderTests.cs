namespace Aegis.Windows.Core.Tests;

using Aegis.Windows.Core.History;
using Xunit;

/// <summary>M2 历史记录判定的单测：内部页面（首页/画板/空白页）不入历史，
/// 普通站点记录——杜绝「历史被首页占满」。</summary>
public sealed class HistoryRecorderTests
{
    [Theory]
    [InlineData("https://example.com/page", true)]
    [InlineData("http://example.com/", true)]
    [InlineData("https://ntp.aegis.local/start.html", false)]
    [InlineData("https://geo.aegis.local/GeoGebra/HTML5/5.0/GeoGebra.html", false)]
    [InlineData("about:blank", false)]
    [InlineData("javascript:void(0)", false)]
    [InlineData("file:///C:/x.html", false)]
    [InlineData("not a url", false)]
    [InlineData("", false)]
    [InlineData(null, false)]
    public void RecordsOnlyExternalHttpHttpsPages(string? url, bool expected) =>
        Assert.Equal(expected, HistoryRecorder.IsRecordableUrl(url));
}

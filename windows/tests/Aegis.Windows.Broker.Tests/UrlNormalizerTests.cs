namespace Aegis.Windows.Broker.Tests;

using Aegis.Windows.Chrome;
using Xunit;

/// <summary>
/// UrlNormalizer 跨端契约测试——断言集对齐 legacy/windows-pywebview
/// selftest_api_bridge.py 的 normalize_url 检查 + Android SearchEngines.kt
/// P0-2 语义（搜索词 vs 网址判定、非导航 scheme fail-closed）。
/// </summary>
public sealed class UrlNormalizerTests
{
    [Fact]
    public void 补Https协议()
    {
        Assert.Equal("https://example.com", UrlNormalizer.Normalize("example.com"));
        Assert.Equal("https://a.cn", UrlNormalizer.Normalize("a.cn"));
    }

    [Fact]
    public void Http与Https绝对Url保留()
    {
        Assert.Equal("http://a.cn", UrlNormalizer.Normalize("http://a.cn"));
        Assert.Equal("https://a.cn/x?y=1#z", UrlNormalizer.Normalize("https://a.cn/x?y=1#z"));
    }

    [Fact]
    public void 空格编码为百分号二十()
    {
        Assert.Equal("https://a.cn/a%20b", UrlNormalizer.Normalize("https://a.cn/a b"));
    }

    [Fact]
    public void 搜索词走默认引擎()
    {
        Assert.Equal("https://www.baidu.com/s?wd=hello%20world", UrlNormalizer.Normalize("hello world"));
        Assert.Equal("https://www.baidu.com/s?wd=weather", UrlNormalizer.Normalize("weather"));
    }

    [Fact]
    public void 搜索词可指定引擎()
    {
        Assert.Equal("https://www.bing.com/search?q=hello", UrlNormalizer.Normalize("hello", "bing"));
        Assert.Equal("https://www.sogou.com/web?query=hello", UrlNormalizer.Normalize("hello", "sogou"));
        Assert.Equal("https://www.baidu.com/s?wd=hello", UrlNormalizer.Normalize("hello", "unknown-engine"));
    }

    [Fact]
    public void 搜索词内的斜杠保留()
    {
        // Uri.encode(text, "/") 语义："/" 不编码（对齐 Android 端）
        Assert.Equal("https://www.baidu.com/s?wd=a/b", UrlNormalizer.Normalize("a/b"));
    }

    [Fact]
    public void 空输入拒绝()
    {
        Assert.Null(UrlNormalizer.Normalize(null));
        Assert.Null(UrlNormalizer.Normalize(""));
        Assert.Null(UrlNormalizer.Normalize("   "));
    }

    [Fact]
    public void 非导航Scheme一律FailClosed()
    {
        Assert.Null(UrlNormalizer.Normalize("file:///C:/x"));
        Assert.Null(UrlNormalizer.Normalize("javascript:alert(1)"));
        Assert.Null(UrlNormalizer.Normalize("data:text/html,x"));
        // 无冒号无点号的裸词不是 scheme——按搜索词处理（对齐 Android classifyInput）
        Assert.Equal("https://www.baidu.com/s?wd=file", UrlNormalizer.Normalize("file"));
    }

    [Fact]
    public void AboutBlank原样放行()
    {
        Assert.Equal("about:blank", UrlNormalizer.Normalize("about:blank"));
        Assert.Equal("about:blank", UrlNormalizer.Normalize("ABOUT:BLANK"));
    }

    [Fact]
    public void 无点号输入视为搜索词()
    {
        Assert.Equal("https://www.baidu.com/s?wd=localhost", UrlNormalizer.Normalize("localhost"));
    }

    [Fact]
    public void 前后空白裁剪()
    {
        Assert.Equal("https://example.com", UrlNormalizer.Normalize("  example.com  "));
    }
}

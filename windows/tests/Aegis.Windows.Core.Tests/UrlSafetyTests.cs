namespace Aegis.Windows.Core.Tests;

using System.Net;
using Aegis.Windows.Core;
using Xunit;

/// <summary>外部链接打开 URL 安全判定单测：仅公网 http/https，拒绝
/// localhost/回环/私有/保留/组播/链路本地等（安全约束锁定）。</summary>
public sealed class UrlSafetyTests
{
    [Theory]
    [InlineData("https://www.baidu.com/", true)]
    [InlineData("http://example.com/x", true)]
    [InlineData("https://example.com", true)]
    [InlineData("http://example.com", true)]
    // 非 http/https
    [InlineData("javascript:void(0)", false)]
    [InlineData("file:///C:/x.html", false)]
    [InlineData("data:text/html,hi", false)]
    [InlineData("about:blank", false)]
    [InlineData("", false)]
    [InlineData(null, false)]
    [InlineData("not a url", false)]
    public void AcceptsOnlyPublicHttpHttps(string? url, bool expected) =>
        Assert.Equal(expected, UrlSafety.IsPublicHttpUrl(url));

    [Theory]
    [InlineData("https://localhost/x", false)]
    [InlineData("https://localhost", false)]
    [InlineData("https://foo.localhost/x", false)]
    [InlineData("http://127.0.0.1/x", false)]
    [InlineData("http://127.0.0.2", false)]
    [InlineData("http://10.0.0.5", false)]
    [InlineData("http://172.16.0.9", false)]
    [InlineData("http://172.31.255.255", false)]
    [InlineData("http://192.168.1.1", false)]
    [InlineData("http://169.254.169.254/x", false)]   // 云元数据/链路本地
    [InlineData("http://100.64.0.1", false)]          // CGNAT 保留
    [InlineData("http://0.0.0.0", false)]
    [InlineData("http://224.0.0.1", false)]           // 组播
    [InlineData("http://255.255.255.255", false)]
    [InlineData("https://[::1]", false)]              // IPv6 回环
    [InlineData("http://192.168.001.001", false)]     // 规范化后仍是私有
    public void RejectsLoopbackAndPrivateAndReserved(string url, bool expected) =>
        Assert.Equal(expected, UrlSafety.IsPublicHttpUrl(url));
}
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

    // ── 本地开发访问放开：CanOpenHttpUrl 允许公网 + 本机/回环/hosts 域名 ──
    [Theory]
    [InlineData("https://www.baidu.com/", true)]
    [InlineData("https://example.com", true)]
    [InlineData("http://localhost/", true)]            // 本机放行
    [InlineData("http://localhost:8080", true)]
    [InlineData("http://foo.localhost/x", true)]
    [InlineData("http://127.0.0.1/x", true)]           // 回环放行
    [InlineData("http://127.0.0.1:8080", true)]
    [InlineData("http://[::1]/", true)]                // IPv6 回环放行
    [InlineData("http://192.168.1.1", false)]          // 私有非本机仍拒
    [InlineData("http://10.0.0.5", false)]
    [InlineData("http://169.254.169.254/x", false)]    // 链路本地仍拒
    [InlineData("javascript:void(0)", false)]
    [InlineData("file:///C:/x.html", false)]
    [InlineData("data:text/html,hi", false)]
    [InlineData(null, false)]
    [InlineData("not a url", false)]
    public void CanOpenHttpUrlAllowsPublicAndLocalHosts(string? url, bool expected) =>
        Assert.Equal(expected, UrlSafety.CanOpenHttpUrl(url));

    [Theory]
    [InlineData("localhost", true)]
    [InlineData("foo.localhost", true)]
    [InlineData("127.0.0.1", true)]                    // 回环
    [InlineData("127.0.0.2", true)]                    // 整个 127/8 回环段
    [InlineData("::1", true)]                          // IPv6 回环
    [InlineData("192.168.1.1", false)]                 // 私有非回环
    [InlineData("10.0.0.5", false)]
    [InlineData("8.8.8.8", false)]                     // 公网
    [InlineData("", false)]
    public void IsLocalHostOrResolvesLocalHostFastPath(string host, bool expected) =>
        Assert.Equal(expected, UrlSafety.IsLocalHostOrResolvesLocalHost(host));

    // —— 边界补强批次：非点分十进制 IPv4 编码与 IPv6 特殊段 ——

    [Theory]
    [InlineData("http://127.1/x", false)]             // 简写 127.1 = 127.0.0.1
    [InlineData("http://2130706433/x", false)]        // 十进制整数 = 127.0.0.1
    [InlineData("http://0x7f000001/x", false)]        // 十六进制 = 127.0.0.1
    [InlineData("http://127.0.1/x", false)]           // 三段简写
    [InlineData("http://0.0.0.0", false)]             // 未指定
    [InlineData("http://[::ffff:192.168.1.1]/x", false)] // IPv4-mapped IPv6 → 私网
    [InlineData("http://[::ffff:127.0.0.1]/x", false)]   // IPv4-mapped IPv6 → 回环
    [InlineData("http://[fc00::1]/x", false)]         // IPv6 ULA 私网
    [InlineData("http://[fd00::1]/x", false)]         // IPv6 ULA 私网
    [InlineData("http://[fec0::1]/x", false)]         // IPv6 site-local
    [InlineData("http://[ff02::1]/x", false)]         // IPv6 组播
    [InlineData("http://192.0.2.1/x", false)]         // TEST-NET 文档段
    [InlineData("http://198.18.0.1/x", false)]        // 基准测试段
    [InlineData("http://255.255.255.255", false)]     // 广播
    public void RejectsIpv4AlternateEncodingsAndIpv6SpecialRanges(string url, bool expected) =>
        Assert.Equal(expected, UrlSafety.IsPublicHttpUrl(url));

    [Fact]
    public void BareHexPrefixHostDoesNotThrow()
    {
        // CS-002 回归：host=="0x" 时此前 Convert.ToInt64 抛 FormatException
        // （新窗口请求 http://0x/ 即崩）——守卫后按"非公网主机名"处理
        var ex = Record.Exception(() => UrlSafety.IsPublicHttpUrl("http://0x/"));
        Assert.Null(ex);
        // "0x" 无有效 hex 位——按普通公网主机名放行（DNS 解析失败自然拦截），
        // 不再落入十六进制转换分支
        Assert.True(UrlSafety.IsPublicHttpUrl("http://0x/"));
        Assert.False(UrlSafety.IsPublicHttpUrl("http://0x0/"));  // 0x0 = 0.0.0.0
    }
}

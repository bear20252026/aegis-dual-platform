namespace Aegis.Windows.Core.Tests;

using Aegis.Windows.Chrome;
using Aegis.Windows.WebView;
using Xunit;

/// <summary>C11 批（审计 2026-09-26）：地址栏归一补测——未知引擎回退、尾点
/// 判搜索词、about:blank 大小写、host:port 带路径、裸 IPv6 字面量（CS-140）、
/// 输入层与升级豁免层同判（R8-CS-SEC-15）。</summary>
public sealed class UrlNormalizerTests
{
    // ===== CS-138：未知引擎回退默认引擎 =====

    [Theory]
    [InlineData("hello world")]
    [InlineData("天气 查询")]
    public void UnknownEngineKeyFallsBackToDefaultEngine(string query)
    {
        var normalized = UrlNormalizer.Normalize(query, "not-a-real-engine");

        Assert.NotNull(normalized);
        Assert.StartsWith(UrlNormalizer.EngineUrls[UrlNormalizer.DefaultEngine], normalized);
    }

    [Fact]
    public void KnownEngineKeyUsesThatEngine()
    {
        Assert.StartsWith("https://duckduckgo.com/?q=",
            UrlNormalizer.Normalize("hello world", "duckduckgo"));
    }

    // ===== CS-139：尾点输入判搜索词（不补 scheme 导航） =====

    [Theory]
    [InlineData("example.")]
    [InlineData("example.com..")]
    public void TrailingDotInputTreatedAsSearchQuery(string query)
    {
        var normalized = UrlNormalizer.Normalize(query);

        Assert.StartsWith(UrlNormalizer.EngineUrls[UrlNormalizer.DefaultEngine], normalized);
    }

    [Fact]
    public void NullInputReturnsNull()
    {
        // CS-254：null 入参拒绝（不抛）
        Assert.Null(UrlNormalizer.Normalize(null));
        Assert.Null(UrlNormalizer.Normalize(null, "bing"));
    }

    // ===== CS-141：about:blank 大小写不敏感 =====

    [Theory]
    [InlineData("ABOUT:BLANK")]
    [InlineData("About:Blank")]
    [InlineData("about:blank")]
    public void AboutBlankIsCaseInsensitive(string input) =>
        Assert.Equal("about:blank", UrlNormalizer.Normalize(input));

    // ===== CS-142：host:port 带路径导航 =====

    [Theory]
    [InlineData("localhost:8080/x", "http://localhost:8080/x")]
    [InlineData("127.0.0.1:8080/x", "http://127.0.0.1:8080/x")]
    [InlineData("example.com:8080/x", "https://example.com:8080/x")]
    public void HostPortWithPathNavigates(string input, string expected) =>
        Assert.Equal(expected, UrlNormalizer.Normalize(input));

    // ===== CS-140：裸 IPv6 字面量补 http（此前被当搜索词） =====

    [Theory]
    [InlineData("::1", "http://[::1]")]
    [InlineData("[::1]", "http://[::1]")]
    [InlineData("[::1]:8080", "http://[::1]:8080")]
    [InlineData("[::1]/x", "http://[::1]/x")]
    [InlineData("::1/x", "http://[::1]/x")]
    public void BareIpv6LiteralNavigates(string input, string expected) =>
        Assert.Equal(expected, UrlNormalizer.Normalize(input));

    [Fact]
    public void LetterLeadingColonedInputStaysFailClosed()
    {
        // 字母起始形如 scheme（"fe80:"）——维持 fail-closed 拒绝，不抢道为 IPv6
        Assert.Null(UrlNormalizer.Normalize("fe80::1"));
        // 冒号起始但非合法 IPv6——回退搜索词（与既有行为一致）
        var normalized = UrlNormalizer.Normalize(":::");
        Assert.StartsWith(UrlNormalizer.EngineUrls[UrlNormalizer.DefaultEngine], normalized!);
    }

    // ══════════ CS-417（2026-10-02 审计）：跨端契约用例分区 ══════════
    // 以下用例自 Broker.Tests/UrlNormalizerTests.cs 整文件迁入（原文件全部为
    // 纯 Normalize 断言、零 broker 消费——同名分裂两套件掩盖归一层回归覆盖
    // 的归属）。断言集对齐 legacy/windows-pywebview selftest_api_bridge.py 的
    // normalize_url 检查 + Android SearchEngines.kt P0-2 语义。

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
        Assert.Equal("https://www.baidu.com/s?wd=hello", UrlNormalizer.Normalize("hello"));
    }

    [Fact]
    public void 本机域名导航到本机Http而非搜索()
    {
        // 放开本地开发访问：localhost/foo.localhost（可含端口）直接导航 http，
        // 不再当搜索词处理（对标 Chrome 对 localhost 的行为）。
        Assert.Equal("http://localhost", UrlNormalizer.Normalize("localhost"));
        Assert.Equal("http://localhost:8080", UrlNormalizer.Normalize("localhost:8080"));
        Assert.Equal("http://api.localhost/x", UrlNormalizer.Normalize("api.localhost/x"));
    }

    [Fact]
    public void 本机与内网目标补Http_公网目标补Https()
    {
        // R8-CS-SEC-15（2026-10-08）：判据改为复用 UrlSafety.IsPublicHost。
        // 本用例原来叫「回环与IP字面量补Http」并写着「任意 IP 字面量默认补 http」——
        // 那正是第三个裁决源：公网 IP 在这里被判去 http，升级层却按公网改写 https，
        // 两处相反；`.local`/`.internal` 反过来在这里补 https 而升级层认它是内网名。
        Assert.Equal("http://127.0.0.1", UrlNormalizer.Normalize("127.0.0.1"));
        Assert.Equal("http://127.0.0.1:8080", UrlNormalizer.Normalize("127.0.0.1:8080"));
        Assert.Equal("http://192.168.1.1:8080", UrlNormalizer.Normalize("192.168.1.1:8080"));
        Assert.Equal("http://10.0.0.5", UrlNormalizer.Normalize("10.0.0.5"));
        Assert.Equal("http://100.64.1.2", UrlNormalizer.Normalize("100.64.1.2"));  // CGNAT/Tailscale
        Assert.Equal("http://my-nas.local", UrlNormalizer.Normalize("my-nas.local"));  // mDNS
        Assert.Equal("http://printer.internal/x", UrlNormalizer.Normalize("printer.internal/x"));
        Assert.Equal("http://0177.0.0.1", UrlNormalizer.Normalize("0177.0.0.1"));  // 八进制编码归一后仍是回环
        // 公网域名与公网 IP 字面量都补 https（此前公网 IP 补 http，等于白补——升级层还会改写）
        Assert.Equal("https://example.com", UrlNormalizer.Normalize("example.com"));
        Assert.Equal("https://example.com:8080", UrlNormalizer.Normalize("example.com:8080"));
        Assert.Equal("https://8.8.8.8", UrlNormalizer.Normalize("8.8.8.8"));
    }

    [Theory]
    [InlineData("my-nas.local")]
    [InlineData("printer.example.internal")]
    [InlineData("api.localhost")]
    [InlineData("127.0.0.1")]
    [InlineData("192.168.1.1")]
    [InlineData("100.64.1.2")]
    [InlineData("example.com")]
    [InlineData("8.8.8.8")]
    public void 输入层补的scheme与升级豁免层同判(string host)
    {
        // R8-CS-SEC-15 的回归锚：同一次导航里，地址栏补的 scheme 必须与
        // HostWebView.IsExemptFromHttpsUpgrade 的结论一致——补 http 当且仅当该 host
        // 豁免 HTTPS-only 升级。判据合一前两者对 `my-nas.local` 给出相反答案，
        // 用户敲裸域名就打不开（第七轮 B8「本机与内网必须能打开」在输入框这一步被关掉）。
        // 公网 host 一侧预置 DNS 缓存为「非本机」：豁免判定否则走冷缓存 fail-closed，
        // 结论虽相同但依赖解析时序（CS-339/382 的缓存面，测试里不留这种依赖）。
        UrlSafety.SeedLocalHostCacheForTests(host, isLocal: false);
        var normalized = UrlNormalizer.Normalize(host)!;
        var upgradedToHttp = normalized.StartsWith("http://", StringComparison.Ordinal);
        Assert.Equal(HostWebView.IsExemptFromHttpsUpgrade(host), upgradedToHttp);
    }

    [Fact]
    public void 前后空白裁剪()
    {
        Assert.Equal("https://example.com", UrlNormalizer.Normalize("  example.com  "));
    }
}

namespace Aegis.Windows.Core.Tests;

using System;
using System.Collections.Generic;
using System.IO;
using System.Net;
using System.Net.Http;
using System.Threading;
using System.Threading.Tasks;
using Aegis.Windows.Chrome;
using Aegis.Windows.Core.Security;
using Xunit;

/// <summary>R9-B33（第九轮队列 Q23）：源码查看器带外抓取的重定向复判与体积上限。
///
/// 修的形态：抓取用的是默认配置的 HttpClient ⇒ 自动跟随重定向且落点无人复判（页面一个
/// `302 → http://169.254.169.254/...` 就能把云元数据当「网页源码」摆给被诱导的用户看，
/// 而顶层导航对同一跳会取消并留痕）；响应体先 <c>ReadAsByteArrayAsync()</c> 全量进内存
/// 再比 5MB 上限（无 Content-Length 的流可以先吃满内存再被拒）。
///
/// 判据全部走 stub handler，不碰网络：handler 记录每一跳实际请求的绝对地址，所以
/// 「第二跳根本没发出去」「相对 Location 基于当前跳解析」这类细节是在被断言的。
/// 反向锚形态：把逐跳复判拆掉（回到 AllowAutoRedirect=true + 一次 GetAsync），
/// <see cref="RedirectIntoLinkLocalIsRefusedBeforeTheSecondRequest"/> 会拿到 `pwned`
/// 正文并通过，<see cref="RedirectChainIsFollowedAgainstTheCurrentHop"/> 的请求列表
/// 会只剩一条——两条一起保证这组用例不是恒绿的。</summary>
public sealed class SourceFetcherTests
{
    private const int MaxBytes = 5 * 1024 * 1024;

    /// <summary>按当前跳地址给响应，并记下每个被真正请求过的绝对地址。</summary>
    private sealed class StubHandler : HttpMessageHandler
    {
        private readonly Func<string, HttpResponseMessage> _respond;

        public List<string> Requested { get; } = new();

        public StubHandler(Func<string, HttpResponseMessage> respond) => _respond = respond;

        protected override Task<HttpResponseMessage> SendAsync(
            HttpRequestMessage request, CancellationToken cancellationToken)
        {
            Requested.Add(request.RequestUri!.ToString());
            return Task.FromResult(_respond(request.RequestUri!.ToString()));
        }
    }

    /// <summary>无长度、读多少给多少的流——用来证明「超限即停手」真的停手。</summary>
    private sealed class EndlessStream : Stream
    {
        public long Pulled { get; private set; }

        public override bool CanRead => true;

        public override bool CanSeek => false;

        public override bool CanWrite => false;

        public override long Length => throw new NotSupportedException();

        public override long Position { get => 0; set { } }

        public override int Read(byte[] buffer, int offset, int count)
        {
            Pulled += count;
            return count;
        }

        public override void Flush() { }

        public override long Seek(long offset, SeekOrigin origin) => throw new NotSupportedException();

        public override void SetLength(long value) => throw new NotSupportedException();

        public override void Write(byte[] buffer, int offset, int count) => throw new NotSupportedException();
    }

    private static HttpResponseMessage Text(string body) =>
        new(HttpStatusCode.OK) { Content = new StringContent(body) };

    private static HttpResponseMessage Found(string location) =>
        new(HttpStatusCode.Found) { Headers = { Location = new Uri(location, UriKind.RelativeOrAbsolute) } };

    private static HttpResponseMessage DeclaredOversize(long declared)
    {
        var response = new HttpResponseMessage(HttpStatusCode.OK) { Content = new ByteArrayContent(new byte[4]) };
        response.Content.Headers.ContentLength = declared;
        return response;
    }

    private static async Task<SourceFetcher.Outcome> FetchAsync(string url, StubHandler handler)
    {
        using var client = new HttpClient(handler);
        return await SourceFetcher.FetchAsync(client, url, MaxBytes);
    }

    [Fact]
    public async Task Plain200ReturnsTheBody()
    {
        var result = await FetchAsync("https://example.com/a", new StubHandler(_ => Text("<html>ok</html>")));
        Assert.True(result.Ok);
        Assert.Equal("<html>ok</html>", result.Text);
    }

    [Fact]
    public async Task Non2xxWithoutRedirectFailsWithTheStatusCode()
    {
        var result = await FetchAsync("https://example.com/a",
            new StubHandler(_ => new HttpResponseMessage(HttpStatusCode.InternalServerError)));
        Assert.False(result.Ok);
        Assert.Contains("500", result.Reason);
    }

    [Fact]
    public async Task FirstHopToReservedAddressIsAllowedBecauseNavigationAlreadyJudgedIt()
    {
        // 能进地址栏就说明这一跳已经过了顶层导航那同一道闸（同一个 ReservedAddressBoundary
        // 谓词源），这里再判一次只是重复；而「本机与内网必须能打开」是 2026-10-04 的裁决。
        var result = await FetchAsync("http://169.254.169.254/latest/user-data",
            new StubHandler(_ => Text("metadata")));
        Assert.True(result.Ok);
        Assert.Equal("metadata", result.Text);
    }

    [Fact]
    public async Task RedirectIntoLinkLocalIsRefusedBeforeTheSecondRequest()
    {
        var handler = new StubHandler(url =>
            url.Contains("example.com") ? Found("http://169.254.169.254/latest/meta-data/") : Text("pwned"));
        var result = await FetchAsync("https://example.com/page", handler);
        Assert.False(result.Ok);
        Assert.Contains("保留地址", result.Reason);
        Assert.Equal(new[] { "https://example.com/page" }, handler.Requested);
    }

    [Fact]
    public async Task RedirectOutOfHttpFamilyIsRefused()
    {
        var result = await FetchAsync("https://example.com/page", new StubHandler(_ => Found("file:///c:/x")));
        Assert.False(result.Ok);
        Assert.Contains("非 http/https", result.Reason);
    }

    [Fact]
    public async Task RedirectChainIsFollowedAgainstTheCurrentHop()
    {
        var handler = new StubHandler(url => url.EndsWith("/y") ? Text("deep") : Found("/y"));
        var result = await FetchAsync("https://example.com/x", handler);
        Assert.True(result.Ok);
        Assert.Equal("deep", result.Text);
        // 相对 Location 以**当前跳**为基（若按最初地址拼接，这里会得到同一个 /x）
        Assert.Equal(new[] { "https://example.com/x", "https://example.com/y" }, handler.Requested);
    }

    [Fact]
    public async Task TooManyRedirectsStopsAtTheCap()
    {
        var handler = new StubHandler(_ => Found("/loop"));
        var result = await FetchAsync("https://example.com/a", handler);
        Assert.False(result.Ok);
        Assert.Contains("重定向超过 3 跳上限", result.Reason);
        Assert.Equal(4, handler.Requested.Count);   // 第 0..3 跳各请求一次后停手
    }

    [Fact]
    public async Task RedirectWithoutLocationFailsInsteadOfReRequestingTheSameUrl()
    {
        var handler = new StubHandler(_ => new HttpResponseMessage(HttpStatusCode.Found));
        var result = await FetchAsync("https://example.com/a", handler);
        Assert.False(result.Ok);
        Assert.Contains("Location", result.Reason);
        Assert.Single(handler.Requested);
    }

    [Fact]
    public async Task DeclaredOversizeIsRefusedWithoutReadingTheBody()
    {
        var result = await FetchAsync("https://example.com/a",
            new StubHandler(_ => DeclaredOversize(50L * 1024 * 1024)));
        Assert.False(result.Ok);
        Assert.Contains("5MB 上限", result.Reason);
    }

    [Fact]
    public async Task ChunkedOversizeStopsJustPastTheCap()
    {
        var stream = new EndlessStream();
        var result = await FetchAsync("https://example.com/a", new StubHandler(_ =>
            new HttpResponseMessage(HttpStatusCode.OK) { Content = new StreamContent(stream) }));
        Assert.False(result.Ok);
        Assert.Contains("5MB 上限", result.Reason);
        // 旧写法（先 ReadAsByteArrayAsync 再比长度）会把这条流读到底；
        // 有界读取到上限再多一块就停手——所以拉取量必须是「刚刚越过 5MB」而不是几十 MB。
        Assert.InRange(stream.Pulled, MaxBytes, MaxBytes + 128 * 1024);
    }

    [Fact]
    public void GuardChecksProtocolOnEveryHopAndAddressOnlyAfterTheFirst()
    {
        Assert.Null(HttpFetchGuard.RedirectProblem(new Uri("http://192.168.1.20/"), isFirstHop: true));
        Assert.Null(HttpFetchGuard.RedirectProblem(new Uri("http://169.254.169.254/x"), isFirstHop: true));
        Assert.Null(HttpFetchGuard.RedirectProblem(new Uri("http://192.168.1.20/"), isFirstHop: false));
        Assert.Contains("保留地址", HttpFetchGuard.RedirectProblem(new Uri("http://169.254.169.254/x"), isFirstHop: false));
        Assert.Contains("协议", HttpFetchGuard.RedirectProblem(new Uri("ftp://h/x"), isFirstHop: false));
        Assert.Contains("无法解析", HttpFetchGuard.RedirectProblem(null, isFirstHop: false));
    }
}

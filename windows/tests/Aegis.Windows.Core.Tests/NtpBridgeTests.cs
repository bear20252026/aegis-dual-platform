namespace Aegis.Windows.Core.Tests;

using System.Text.Json;
using Aegis.Windows.Chrome.Ntp;
using Aegis.Windows.Core.Bookmarks;
using Xunit;

/// <summary>M3 新标签页宿主桥单测：来源白名单/操作分发/参数 fail-closed
/// （ADR-009 D4：机制必须可单测——桥数据面不碰 WebView，全量纯逻辑）。</summary>
public sealed class NtpBridgeTests
{
    private static NtpBridge.Services FakeServices(
        string? engine = null,
        Action<string>? onSetEngine = null,
        string? wallpaper = null,
        Action<string>? onSetWallpaper = null,
        Action<string>? onNavigate = null,
        Action? onRestore = null) => new(
        SearchEngine: () => engine ?? "baidu",
        SetSearchEngine: onSetEngine ?? (_ => { }),
        Wallpaper: () => wallpaper ?? NtpAssets.DefaultWallpaper,
        SetWallpaper: onSetWallpaper ?? (_ => { }),
        Bookmarks: () => new List<Bookmark> { new(1, "示例", "https://example.com") },
        SavedSessionCount: () => 3,
        RestoreSession: onRestore ?? (() => { }),
        Navigate: onNavigate ?? (_ => { }),
        GoBack: () => true,
        OpenGeo: () => false,
        ImportSources: () => new List<NtpBridge.ImportSourceSnapshot>
        {
            new("chrome", true, true),
        },
        ImportBookmarks: _ => (0, 0, new List<NtpBridge.ImportResult>()),
        ImportHistory: (_, _) => (0, 0, new List<NtpBridge.ImportResult>()));

    [Theory]
    [InlineData("https://ntp.aegis.local/start.html", true)]
    [InlineData("http://ntp.aegis.local/start.html", false)]
    [InlineData("https://evil.example/start.html", false)]
    [InlineData("https://ntp.aegis.local:8080/start.html", false)]
    [InlineData("not a url", false)]
    [InlineData(null, false)]
    public void IsTrustedSourceAcceptsOnlyNtpHttpsOrigin(string? source, bool expected) =>
        Assert.Equal(expected, NtpBridge.IsTrustedSource(source));

    [Fact]
    public void GetEngineReturnsCurrentAndFullEngineTable()
    {
        var bridge = new NtpBridge(FakeServices(engine: "bing"));

        var result = bridge.Dispatch("getEngine", EmptyArgs());

        var json = JsonSerializer.Serialize(result);
        Assert.Contains("\"engine\":\"bing\"", json);
        Assert.Contains("baidu", json);
        Assert.Contains("sogou", json);
    }

    [Fact]
    public void SetEngineOnlyAcceptsKnownEngineKeys()
    {
        var applied = new List<string>();
        var bridge = new NtpBridge(FakeServices(onSetEngine: applied.Add));

        bridge.Dispatch("setEngine", Args("sogou"));
        bridge.Dispatch("setEngine", Args("duckduckgo"));

        Assert.Equal(["sogou"], applied);
    }

    [Fact]
    public void SetWallpaperOnlyAcceptsWhitelistedNames()
    {
        var applied = new List<string>();
        var bridge = new NtpBridge(FakeServices(onSetWallpaper: applied.Add));

        bridge.Dispatch("setWallpaper", Args("aurora-lime.jpg"));
        bridge.Dispatch("setWallpaper", Args("../../etc/passwd"));
        bridge.Dispatch("setWallpaper", Args("aurora-unknown.jpg"));

        Assert.Equal(["aurora-lime.jpg"], applied);
    }

    [Fact]
    public void NavigateRejectsNonNavigationProtocols()
    {
        var navigated = new List<string?>();
        var bridge = new NtpBridge(FakeServices(onNavigate: navigated.Add));

        bridge.Dispatch("navigate", Args("javascript:alert(1)"));
        bridge.Dispatch("navigate", Args("https://example.com/page"));

        // javascript: 在归一层 fail-closed；https 目标进入授权路径
        Assert.Equal(["https://example.com/page"], navigated);
    }

    [Fact]
    public void RestoreSessionAndHasSavedDispatch()
    {
        var restored = 0;
        var bridge = new NtpBridge(FakeServices(onRestore: () => restored++));

        Assert.Equal(3, bridge.Dispatch("hasSaved", EmptyArgs()));
        bridge.Dispatch("restoreSession", EmptyArgs());
        Assert.Equal(1, restored);
    }

    [Fact]
    public void BookmarksExposeTitleAndUrlOnly()
    {
        var bridge = new NtpBridge(FakeServices());

        var json = JsonSerializer.Serialize(bridge.Dispatch("bookmarks", EmptyArgs()));

        Assert.Contains("https://example.com", json);
        Assert.Contains("title", json);
    }

    [Fact]
    public void UnknownOperationIsIgnored() =>
        Assert.Null(new NtpBridge(FakeServices()).Dispatch("evilOp", EmptyArgs()));

    [Fact]
    public void TryHandleIgnoresUntrustedSourcesAndMalformedMessages()
    {
        var bridge = new NtpBridge(FakeServices());
        object? response = null;
        void Respond(object? result) => response = result;

        bridge.TryHandle("https://evil.example", "{\"__aegis\":1,\"id\":1,\"op\":\"hasSaved\"}", Respond);
        bridge.TryHandle("https://ntp.aegis.local", "not json", Respond);
        bridge.TryHandle("https://ntp.aegis.local", "{\"id\":1,\"op\":\"hasSaved\"}", Respond);

        Assert.Null(response);
    }

    [Fact]
    public void TryHandleRespondsWithCorrelationId()
    {
        var bridge = new NtpBridge(FakeServices());
        object? response = null;

        bridge.TryHandle(
            "https://ntp.aegis.local/start.html",
            "{\"__aegis\":1,\"id\":42,\"op\":\"hasSaved\",\"args\":[]}",
            result => response = result);

        var json = JsonSerializer.Serialize(response);
        Assert.Contains("\"id\":42", json);
        Assert.Contains("\"__aegisRes\":1", json);
    }

    [Fact]
    public void WallpaperWhitelistMatchesPythonBundle()
    {
        // 与 Python asset_scheme.WALLPAPERS 四张一致（跨端契约）
        Assert.Equal(4, NtpAssets.Wallpapers.Count);
        Assert.Contains("aurora-twilight.jpg", NtpAssets.Wallpapers);
        Assert.True(NtpAssets.IsWallpaperAllowed("aurora-magenta.jpg"));
        Assert.False(NtpAssets.IsWallpaperAllowed("aurora-magenta.jpg%00.js"));
        Assert.False(NtpAssets.IsWallpaperAllowed(null));
    }

    private static JsonElement EmptyArgs() => Args();

    private static JsonElement Args(params string[] values)
    {
        var raw = values.Length == 0
            ? "[]"
            : "[" + string.Join(",", values.Select(v => JsonSerializer.Serialize(v))) + "]";
        return JsonSerializer.Deserialize<JsonElement>(raw);
    }
}

namespace Aegis.Windows.Core.Tests;

using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text.Json;
using Aegis.Windows.Broker;
using Aegis.Windows.Chrome;
using Aegis.Windows.WebView;
using Xunit;

/// <summary>R8-CS-SEC-15（第八轮 2026-10-08）：跨端共享向量文件的 Windows 消费端。
///
/// `android/app/src/test/resources/search-normalize-vectors.json` 的 description 一直
/// 写着「跨端契约」，但第八轮之前**只有 Android 消费**——Windows 输入层另写了一套
/// 「补哪个 scheme」的判据（任意 IP 字面量补 http、只认 localhost 家族），与升级豁免层
/// `IsPublicHost` 相反，于是声明与实况不符（一条无人核验的共享契约等于没有契约）。
/// 本类把那条声明变成事实：逐条驱动 `UrlNormalizer.Normalize`。
///
/// 共享的口径是**判定类 + 补的 scheme**；字符串可以因两端既有差异而不等
/// （Windows 保留输入大小写；八进制 IPv4 在 Android 由 normalize 链内的 OriginPolicy
/// 拒、在 Windows 由导航层拒）。这类差异走向量里的 `windows_url` 覆盖——覆盖值本身
/// 也是断言（改坏了照样红），且条目数被
/// <see cref="CrossEndStringDivergencesStayExplicitAndBounded"/> 钉住，防止「跨端单源」
/// 静默退化成两端各表。</summary>
public sealed class SearchNormalizeVectorTests
{
    private const string VectorFile = "android/app/src/test/resources/search-normalize-vectors.json";

    /// <summary>两端字符串确有差异的条目数（大小写 2 条 + 层序 1 条）——扩容必须写原因。</summary>
    private const int DocumentedCrossEndDivergences = 3;

    private sealed record Vector(
        string Input,
        string Kind,
        string? ExpectedUrl,
        string? WindowsUrl,
        string? Note);

    // 缺席的 expected_url / windows_url 以 null 传入（Theory 形参声明为 string?）；
    // null! 只是压掉「object 数组元素非空」的编译器提示，不是「这里不会为 null」。
    public static IEnumerable<object[]> Vectors =>
        Load().Select(v => new object[] { v.Input, v.Kind, v.ExpectedUrl!, v.WindowsUrl! });

    [Theory]
    [MemberData(nameof(Vectors))]
    public void WindowsMatchesTheSharedVectors(
        string input,
        string kind,
        string? expectedUrl,
        string? windowsUrl)
    {
        var actual = UrlNormalizer.Normalize(input);
        switch (kind)
        {
            case "EMPTY":
            case "FORBIDDEN_SCHEME":
                // 拒绝类两端同判：Windows 也返回 null——绝不把 file:/javascript:/data:
                // 拼成「看起来能导航」的 URL（杜绝补 scheme 盲区）
                Assert.Null(actual);
                return;
            case "SEARCH":
                // 搜索词：跨端不锁具体引擎（向量 expected_url 因此为 null），
                // 只锁「走引擎拼接」——产出裸导航 URL 就是把搜索词当网址打开了
                Assert.NotNull(actual);
                Assert.True(
                    UrlNormalizer.EngineUrls.Values.Any(
                        prefix => actual!.StartsWith(prefix, StringComparison.Ordinal)),
                    $"搜索词未走引擎拼接: 「{input}」→ {actual}");
                return;
        }

        // DOMAIN / ABOUT_BLANK / ABSOLUTE_URL
        Assert.NotNull(actual);
        if (windowsUrl is not null)
            Assert.Equal(windowsUrl, actual);
        else if (expectedUrl is not null)
            Assert.Equal(expectedUrl, actual);

        // 两端真正的共同锚是 scheme：字符串允许按上面登记的差异不等，
        // 但同一个输入补 http 还是 https 必须同判（R8-CS-SEC-15 的全部意义）。
        if (expectedUrl is not null)
            Assert.Equal(SchemeOf(expectedUrl), SchemeOf(actual!));
    }

    [Fact]
    public void CrossEndStringDivergencesStayExplicitAndBounded()
    {
        var divergent = Load()
            .Where(v => v.WindowsUrl is not null && v.WindowsUrl != v.ExpectedUrl)
            .ToList();
        Assert.Equal(DocumentedCrossEndDivergences, divergent.Count);
        // 每条差异都必须在向量的 note 里写清「为什么两端不同」——没有原因的覆盖就是漂移，
        // 而「Android 侧 expected_url 为 null」也算一种已写明的差异（层序：它在自己
        // normalize 链里就被 OriginPolicy 拒了，Windows 到导航层才拒）。
        Assert.All(divergent, v => Assert.False(string.IsNullOrWhiteSpace(v.Note)));
    }

    [Fact]
    public void PublicIpLiteralNoLongerGetsHttpFromTheInputLayer()
    {
        // 旧判据（任意 IP 字面量补 http）产出的 http 会被 HTTPS-only 升级层改写回
        // https——因为升级层问的是 IsPublicHost，两处相反。合一后输入层不再白补。
        Assert.Equal("https://8.8.8.8", UrlNormalizer.Normalize("8.8.8.8"));
        Assert.True(UrlSafety.IsPublicHost("8.8.8.8"));
        Assert.False(HostWebView.IsExemptFromHttpsUpgrade("8.8.8.8"));
    }

    [Fact]
    public void ReservedLiteralKeepsHttpOnWindowsAndIsDeniedAtTheBoundary()
    {
        // 登记 R8-CS-SEC-17 的残余差异：Windows 输入层与升级豁免层现在同问
        // IsPublicHost，而「非公网」集合比 Android `LocalTargetHosts` 的本机/内网段集
        // **宽**——链路本地等保留段在 Windows 判非公网（补 http、不升级），Android 判
        // 非本机（保持 https）。终态一致且都不是逃逸：本端由保留地址边界给出拒绝码。
        Assert.Equal("http://169.254.169.254", UrlNormalizer.Normalize("169.254.169.254"));
        Assert.True(ReservedAddressBoundary.DeniesRaw("http://169.254.169.254"));
    }

    [Fact]
    public void OctalIpv4VectorIsRejectedByTheNavigationLayerInstead()
    {
        // 层序差异（向量的 windows_url 已钉住前半段）：Android 的 normalize 链内嵌
        // OriginPolicy，整条归一直接返回 null；Windows 的输入层不查策略，产出 URL 后
        // 由导航层同判拒绝。两端都是「打不开」，只是拒绝发生在不同层。
        Assert.Equal("http://0177.0.0.1", UrlNormalizer.Normalize("0177.0.0.1"));
        Assert.False(OriginPolicy.TryParseExternal("http://0177.0.0.1", out _));
    }

    private static string SchemeOf(string url) =>
        Uri.TryCreate(url, UriKind.Absolute, out var parsed) ? parsed.Scheme : url;

    private static List<Vector> Load()
    {
        var payload = File.ReadAllText(Path.Combine(RepoRoot(), VectorFile));
        return JsonSerializer.Deserialize<JsonElement>(payload)
            .GetProperty("vectors")
            .EnumerateArray()
            .Select(vector => new Vector(
                vector.GetProperty("input").GetString()!,
                vector.GetProperty("expected_kind").GetString()!,
                ReadOptional(vector, "expected_url"),
                ReadOptional(vector, "windows_url"),
                ReadOptional(vector, "note")))
            .ToList();
    }

    private static string? ReadOptional(JsonElement vector, string name) =>
        vector.TryGetProperty(name, out var value) && value.ValueKind != JsonValueKind.Null
            ? value.GetString()
            : null;

    /// <summary>按仓库相对路径直读——共享文件不复制进输出目录（复制件会与 Android
    /// 侧的原件漂移，正是本项要消除的「两份事实源」）。</summary>
    private static string RepoRoot()
    {
        var dir = new DirectoryInfo(AppContext.BaseDirectory);
        while (dir is not null)
        {
            if (File.Exists(Path.Combine(dir.FullName, VectorFile)))
                return dir.FullName;
            dir = dir.Parent;
        }

        throw new DirectoryNotFoundException($"未找到共享向量文件 {VectorFile}（请在仓库内运行测试）");
    }
}

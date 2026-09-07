namespace Aegis.Windows.Core.Tests;

using System.IO;
using System.Text.Json;
using Aegis.Windows.Broker;
using Aegis.Windows.Core;
using Aegis.Windows.Core.Downloads;
using Aegis.Windows.Core.Settings;
using Xunit;

/// <summary>全仓审计整改回归（2026-09-07）——锁定本轮修复的安全/健壮性
/// 边界：IP 编码绕过、OriginPolicy host 校验、下载策略、设置 null 防护、
/// 缩放统一口径、非法 URL 输入归一。</summary>
public sealed class AuditRegressionTests : IDisposable
{
    private readonly string _dir =
        Path.Combine(Path.GetTempPath(), $"aegis_audit_{System.Guid.NewGuid():N}");

    // ═══ UrlSafety：IPv4-mapped IPv6 / 组播 / 非点分 IP 编码 ═══

    [Theory]
    [InlineData("::ffff:192.168.1.1")]   // IPv4-mapped 私网——此前判公网
    [InlineData("::ffff:127.0.0.1")]     // IPv4-mapped 回环——此前判公网
    [InlineData("ff02::1")]              // IPv6 组播 ff00::/8
    [InlineData("fe80::1")]              // 链路本地
    [InlineData("fc00::1")]              // ULA fc00::/7
    [InlineData("fd12:3456::1")]         // ULA（fd 开头）
    [InlineData("fec0::1")]              // site-local fec0::/10
    public void RejectsNonPublicIpv6(string ip) =>
        Assert.False(UrlSafety.IsPublicIp(System.Net.IPAddress.Parse(ip)));

    [Fact]
    public void AcceptsPublicIpv6()
    {
        Assert.True(UrlSafety.IsPublicIp(System.Net.IPAddress.Parse("2606:4700::1111")));
        // IPv4-mapped 公网地址仍放行（按内嵌 IPv4 判定）
        Assert.True(UrlSafety.IsPublicIp(System.Net.IPAddress.Parse("::ffff:8.8.8.8")));
    }

    [Theory]
    [InlineData("2130706433")]    // 十进制整数 = 127.0.0.1——此前判"公网主机名"
    [InlineData("0x7f000001")]    // 十六进制
    [InlineData("127.1")]         // 简写
    [InlineData("10.1")]          // 简写私网
    [InlineData("192.168.001.001")] // .NET TryParse 拒绝但 OS 解析器接受
    public void RejectsAlternateIpv4Encodings(string host) =>
        Assert.False(UrlSafety.IsPublicHost(host));

    [Fact]
    public void AcceptsNormalPublicHost() =>
        Assert.True(UrlSafety.IsPublicHost("example.com"));

    // ═══ OriginPolicy：host 白名单校验 ═══

    [Theory]
    [InlineData("https://example.com./x", false)]   // 尾点 host
    [InlineData("https://exa mple.com/", false)]    // 空白（控制字符路径之外）
    [InlineData("https://example.com:99999/", false)] // 非法端口
    public void OriginPolicyHostValidation(string url, bool expected)
    {
        var ok = OriginPolicy.TryParseExternal(url, out _);
        Assert.Equal(expected, ok);
    }

    // ═══ DownloadPolicy：查询串按参数值判定 + 保留名净化 ═══

    [Theory]
    [InlineData("https://evil.com/download?f=x.exe&sig=abc", "a.bin", true)]   // 尾缀参数不再漏判
    [InlineData("https://evil.com/download?v=2&f=exe", "a.txt", false)]        // 无扩展直链不误报
    [InlineData("https://evil.com/x.lnk", "b.txt", true)]
    [InlineData("https://evil.com/x.reg?z=1", "b.txt", true)]
    public void DownloadPolicyQueryParams(string url, string fileName, bool expected) =>
        Assert.Equal(expected, DownloadPolicy.RequiresExplicitConfirmation(url, fileName));

    [Theory]
    [InlineData("CON")]
    [InlineData("con.txt")]
    [InlineData("COM1")]
    [InlineData("PRN.dat")]
    public void SanitizeFileNameDefusesReservedNames(string raw)
    {
        var name = DownloadPolicy.SanitizeFileName(raw);
        var stem = name.Split('.')[0];
        Assert.False(stem.Equals("CON", System.StringComparison.OrdinalIgnoreCase));
        Assert.False(stem.Equals("COM1", System.StringComparison.OrdinalIgnoreCase));
        Assert.False(stem.Equals("PRN", System.StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void SanitizeFileNameCapsLength()
    {
        var raw = new string('a', 500) + ".exe";
        var name = DownloadPolicy.SanitizeFileName(raw);
        Assert.True(name.Length <= 201);
        Assert.EndsWith(".exe", name);
    }

    // ═══ Settings：null ZoomByHost / 缩放统一口径 ═══

    [Fact]
    public void SnapshotSurvivesNullZoomByHost()
    {
        // settings.json 手编 "ZoomByHost": null ——此前 ToSnapshot 抛
        // ArgumentNullException 且发生在启动链（应用无法启动）
        var json = "{\"ZoomByHost\": null}";
        var model = JsonSerializer.Deserialize<AppSettings>(json);
        Assert.NotNull(model);
        var svc = new SettingsService(Path.Combine(Mkdir(), $"s_{System.Guid.NewGuid():N}.json"));
        svc.Apply(model!);  // 不抛即通过
        Assert.Empty(svc.Snapshot.ZoomByHost);
    }

    [Fact]
    public void NormalizeKeepsQuarterZoom()
    {
        // 缩放统一 0.25–3.0：此前持久化钳 1.0–3.0——0.5 被静默重置为 1.0
        var svc = new SettingsService(Path.Combine(Mkdir(), $"s_{System.Guid.NewGuid():N}.json"));
        svc.Apply(new AppSettings
        {
            ZoomByHost = new System.Collections.Generic.Dictionary<string, double> { ["a.com"] = 0.5 },
        });
        Assert.Equal(0.5, svc.Snapshot.ZoomByHost["a.com"]);
    }

    [Fact]
    public void SettingsLoadBacksUpCorruptFile()
    {
        var path = Path.Combine(Mkdir(), $"bad_{System.Guid.NewGuid():N}.json");
        File.WriteAllText(path, "{ not valid json !!");
        var loaded = AppSettings.Load(path);  // 不抛 + 回退默认
        Assert.Equal(Chrome.UrlNormalizer.DefaultEngine, loaded.SearchEngine);
        Assert.True(File.Exists(path + ".bak"));  // 坏文件已备份（不再静默覆盖丢失）
    }

    // ═══ UrlNormalizer：非法 URI 字符 / 非法 scheme 输入不抛 ═══

    [Theory]
    [InlineData("http://")]                       // 此前 new Uri 抛 UriFormatException
    [InlineData("https://")]                      // 同上
    [InlineData("http://<script>|{bad}")]         // 非法字符剥离
    public void NormalizeNeverReturnsUnparseableUri(string input)
    {
        var result = Chrome.UrlNormalizer.Normalize(input);
        if (result is null)
            return;  // 拒绝也合法
        Assert.True(System.Uri.TryCreate(result, System.UriKind.Absolute, out _),
            $"归一产物必须可解析: {result}");
    }

    [Fact]
    public void NormalizeStripsControlCharacters()
    {
        var result = Chrome.UrlNormalizer.Normalize("example.com\a\b");
        Assert.NotNull(result);
        Assert.DoesNotContain('\a', result);
    }

    private string Mkdir()
    {
        Directory.CreateDirectory(_dir);
        return _dir;
    }

    public void Dispose()
    {
        try { Directory.Delete(_dir, true); } catch (IOException) { }
    }
}

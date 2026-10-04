using Aegis.Windows.Broker;
using Aegis.Windows.Core.Security;
using Xunit;

namespace Aegis.Windows.Broker.Tests;

/// <summary>审计第七轮 R7-CS2-02（2026-10-04）+ 同轮用户裁决改口径：
/// 「本机与内网必须能打开」后，本层只拦**根本不是任何设备**的地址形态
///（链路本地/云元数据/组播/广播/保留/文档测试段/未指定地址）。
///
/// 三重锚定：① 谓词矩阵逐形态（含八进制/十进制整数/简写/IPv6 变体——编码变体
/// 归一化前的拒绝就是可绕过的拒绝）；② 导航、消费、下载三类出口各自的拒绝码与
/// 审计留痕；③ 源码静态锚，证明子资源层（HostWebView.OnWebResourceRequested）
/// 真的调用了同一谓词。该边界是**纯托管层拒绝码**，Rust 核心向量里没有它，
/// 没有本类就等于零判定锚（与 R6-26「接入面零调用者」同一失效模式）。</summary>
public sealed class ReservedAddressBoundaryTests : IDisposable
{
    // 与 BrowserPolicyBrokerTests 同口径：拒绝路径会写 security.log，
    // 重定向到临时目录，绝不落真实用户目录
    private string LogDir { get; } =
        Path.Combine(Path.GetTempPath(), $"aegis_rab_log_{Guid.NewGuid():N}");

    public ReservedAddressBoundaryTests()
    {
        Directory.CreateDirectory(LogDir);
        SecurityLog.SecurityLogDirOverride = LogDir;
    }

    public void Dispose()
    {
        SecurityLog.SecurityLogDirOverride = null;
        try { Directory.Delete(LogDir, true); } catch (IOException) { }
    }

    /// <summary>托管模式 broker（门禁显式放行、不要求原生桥）——判定与 CI 环境变量解耦，
    /// 使本类在原生 job 与普通 job 里断言的是同一件事。</summary>
    private static BrowserPolicyBroker ManagedBroker()
    {
        var broker = new BrowserPolicyBroker(
            nativePolicyCoreGate: () => NativePolicyCoreGateResult.Enabled(),
            nativePolicyCoreRequiredForTests: false);
        Assert.True(broker.RegisterSession("session-1", "tab-1"));
        return broker;
    }

    // ① 谓词矩阵：(URL, 是否应被保留地址边界拒绝)
    public static TheoryData<string, bool> BoundaryMatrix => new()
    {
        // —— 拒绝：不是任何设备的地址形态 ——
        { "http://169.254.169.254/latest/meta-data/", true },   // 云元数据
        { "http://169.254.1.1/", true },                        // 链路本地
        { "http://169.254.1/", true },                          // 简写 = 169.254.1.0
        { "http://2852168190/", true },                        // 十进制整数 = 元数据 IP
        { "http://0251.0376.0251.0376/", true },               // 八进制 = 元数据 IP
        { "http://224.0.0.1/", true },                          // 组播
        { "http://255.255.255.255/", true },                    // 广播
        { "http://0.0.0.0/", true },                            // 未指定
        { "http://192.0.2.1/", true },                          // TEST-NET-1
        { "http://198.51.100.7/", true },                      // TEST-NET-2
        { "http://203.0.113.7/", true },                       // TEST-NET-3
        { "http://198.18.0.1/", true },                         // 基准测试段
        { "http://[fe80::1]/", true },                          // IPv6 链路本地
        { "http://[ff02::1]/", true },                          // IPv6 组播
        { "http://[::ffff:169.254.169.254]/", true },          // IPv4-mapped 元数据
        { "", true },                                           // 取不到 host = 不可判定

        // —— 放行：本机与内网（2026-10-04 用户裁决）——
        { "http://127.0.0.1:6379/", false },                    // 本机服务
        { "http://localhost/admin", false },
        { "http://0177.0.0.1/", false },                        // 八进制回环仍是回环
        { "http://[::1]/", false },                             // IPv6 回环
        { "http://192.168.1.1/set_config", false },             // 路由器/NAS
        { "http://10.0.0.1/", false },
        { "http://172.16.5.4/", false },
        { "http://100.64.0.1/", false },                        // CGNAT/Tailscale
        { "http://[fd00::12]/", false },                        // IPv6 ULA
        { "http://my-nas.local/", false },                      // mDNS 主机名
        { "http://printer.internal/", false },
        { "https://ntp.aegis.local/", false },                  // 宿主自有页面
        { "https://geo.aegis.local/geogebra/index.html", false },
        { "https://ntp.aegis.local:8443/", false },             // 主机名形态：本层不再按端口判
        { "https://example.com/path", false },
        { "https://8.8.8.8/", false },
    };

    [Theory]
    [MemberData(nameof(BoundaryMatrix))]
    public void Predicate_Matrix(string url, bool expected)
    {
        if (url.Length == 0)
        {
            Assert.True(ReservedAddressBoundary.DeniesRaw(url));   // 下载入口：空即拒
            return;
        }
        // 走真实入口形态（子资源/下载拿到的就是裸串），不走解析后的 Uri——
        // 编码变体在 Uri.Host 上已被归一，裸串才复现得出 Chromium 看到的东西
        Assert.Equal(expected, ReservedAddressBoundary.DeniesRaw(url));
    }

    [Fact]
    public void LocalAndLanTargets_AreOpenableByRuling()
    {
        // 用户裁决（2026-10-04）：本机与内网要能打开——这几条是裁决的核心对象，
        // 单独钉住，防止后来者把"SSRF 加固"理解成"恢复私网拒绝"而静默改回去
        foreach (var url in new[]
                 {
                     "http://127.0.0.1:8080/", "http://localhost:3000/",
                     "http://192.168.1.254/", "http://10.1.2.3/", "http://[fd00::1]/",
                 })
        {
            Assert.False(ReservedAddressBoundary.Denies(new Uri(url)), url);
        }
    }

    [Fact]
    public void DenyCode_IsSingleSource()
    {
        Assert.Equal("reserved_address", ReservedAddressBoundary.DenyCode);
        Assert.Equal(ReservedAddressBoundary.DenyCode, ReservedAddressBoundary.Reason.Code);
    }

    // ② 导航出口
    [Theory]
    [InlineData("http://169.254.169.254/latest/meta-data/")]
    [InlineData("http://169.254.1.1/")]
    [InlineData("http://224.0.0.1/")]
    public void EvaluateNavigation_DeniesReservedTargetWithExactCode(string url)
    {
        var broker = ManagedBroker();

        var denied = Assert.IsType<Decision.Deny>(
            broker.EvaluateNavigation("session-1", "tab-1", 0, url, "navigation"));

        Assert.Equal("reserved_address", denied.Reason.Code);
        Assert.Contains(broker.AuditLog, e =>
            e.Decision == "deny" && e.Scope == "navigation" && e.Reason == "reserved_address");
    }

    [Theory]
    [InlineData("http://127.0.0.1:6379/")]
    [InlineData("http://localhost/admin")]
    [InlineData("http://192.168.1.1/set_config")]
    [InlineData("http://my-nas.local/")]
    public void EvaluateNavigation_LocalAndLanTargets_AreAllowed(string url)
    {
        var broker = ManagedBroker();

        Assert.IsType<Decision.Allow>(
            broker.EvaluateNavigation("session-1", "tab-1", 0, url, "navigation"));
        Assert.DoesNotContain(broker.AuditLog, e => e.Reason == "reserved_address");
    }

    [Theory]
    [InlineData("http://2852168190/")]            // 十进制整数（Chromium → 元数据 IP）
    [InlineData("http://0251.0376.0251.0376/")]   // 八进制点分
    [InlineData("http://169.254.1/")]            // 简写
    public void EvaluateNavigation_EncodedReservedForms_NeverAllowed(string url)
    {
        // 编码变体可能先被 OriginPolicy 以 url_policy 挡下（同样 fail-closed）——
        // 本用例钉的是"绝不放行"，拒绝码不锁死，避免与协议层判定顺序耦合
        var broker = ManagedBroker();
        Assert.IsType<Decision.Deny>(
            broker.EvaluateNavigation("session-1", "tab-1", 0, url, "navigation"));
    }

    [Fact]
    public void PureNumericAndHexHosts_AreDeniedAsEncodingEvasion()
    {
        // 平台差异实证：.NET 把 2852168190 解析成 170.0.161.254，Chromium 按
        // inet_aton 解析成 169.254.169.254（云元数据）。判据取"更严的一侧"。
        Assert.True(ReservedAddressBoundary.DeniesRaw("http://2852168190/"));
        Assert.True(ReservedAddressBoundary.DeniesRaw("http://0xa9fea9fe/"));
        Assert.True(ReservedAddressBoundary.DeniesRaw("http://169.254.1/"));
    }

    [Fact]
    public void TryConsumeNavigation_RechecksBoundaryOnForgedAction()
    {
        // 消费点复判：原生核心签发的元数据授权或调用方伪造动作都不得兑换
        var broker = ManagedBroker();
        var forged = new AuthorizedAction(
            "session-1", "tab-1", 0, "http://169.254.169.254", "GET", "/latest/meta-data/",
            "navigation", DateTime.UtcNow.AddMinutes(1), "forged-nonce", broker.PolicyVersion);

        Assert.False(broker.TryConsumeNavigation(
            forged, "session-1", "tab-1", 0, "http://169.254.169.254/latest/meta-data/", "navigation"));
        Assert.Contains(broker.AuditLog, e =>
            e.Decision == "deny" && e.Reason == "reserved_address");
    }

    // ② 下载出口（R7-CS1-02——此前该门从不看 URL）
    [Theory]
    [InlineData("http://169.254.169.254/latest/user-data")]
    [InlineData("http://0.0.0.0/dump")]
    [InlineData("http://0251.0376.0251.0376/creds")]
    public void AllowDownload_DeniesReservedTargetWithExactCode(string url)
    {
        var broker = ManagedBroker();

        Assert.False(broker.AllowDownload("session-1", "tab-1", url, "payload", userConfirmed: true));
        Assert.Contains(broker.AuditLog, e =>
            e.Decision == "deny" && e.Scope == "download" && e.Reason == "reserved_address");
    }

    [Theory]
    [InlineData("https://example.com/file.zip")]
    [InlineData("http://192.168.1.10/firmware.bin")]     // 局域网 NAS/路由器固件——按裁决可下载
    [InlineData("http://127.0.0.1:8080/export")]
    public void AllowDownload_PublicAndLanTargets_Allowed(string url)
    {
        var broker = ManagedBroker();

        Assert.True(broker.AllowDownload("session-1", "tab-1", url, "file.zip", userConfirmed: false));
        Assert.DoesNotContain(broker.AuditLog, e => e.Reason == "reserved_address");
    }

    [Theory]
    [InlineData("")]
    [InlineData("not a url")]
    public void AllowDownload_UnparsableTargetDeniesFailClosed(string url)
    {
        // 取不到 host = 无法判定 = 拒绝（与调用方「读不到元数据即按危险处理」同口径）
        var broker = ManagedBroker();

        Assert.False(broker.AllowDownload("session-1", "tab-1", url, "file.zip", userConfirmed: true));
        Assert.Contains(broker.AuditLog, e =>
            e.Decision == "deny" && e.Scope == "download" && e.Reason == "reserved_address");
    }

    // ③ 静态锚：谓词必须被三层真实调用（只定义不接线正是 R6-26 的失效形态）
    [Fact]
    public void BoundaryIsWiredIntoAllAdmissionLayers()
    {
        var appDir = FindAppSourceDir();
        var brokerSource = File.ReadAllText(
            Path.Combine(appDir, "Broker", "BrowserPolicyBroker.cs"));
        var webViewSource = File.ReadAllText(
            Path.Combine(appDir, "WebView", "HostWebView.cs"));

        // 导航（原生前置 + 托管）+ 消费 + 下载 = broker 内至少 4 处调用
        const string needle = "ReservedAddressBoundary.Denies";
        var calls = CountOccurrences(brokerSource, needle);
        Assert.True(calls >= 4, $"BrowserPolicyBroker.cs 只出现 {calls} 次边界调用");
        // 子资源层：OnWebResourceRequested 内必须调用同一谓词
        var handler = SliceMethod(webViewSource, "private void OnWebResourceRequested");
        Assert.Contains("ReservedAddressBoundary.DeniesRaw(", handler);
        // 旧口径不得复活：拒绝码改名后若仍有 "private_network" 字面量，说明两条面分叉
        Assert.DoesNotContain("private_network", brokerSource);
        Assert.DoesNotContain("PrivateNetworkBoundary", brokerSource + webViewSource);
    }

    private static int CountOccurrences(string haystack, string needle)
    {
        var count = 0;
        for (var index = haystack.IndexOf(needle, StringComparison.Ordinal);
             index >= 0;
             index = haystack.IndexOf(needle, index + needle.Length, StringComparison.Ordinal))
            count++;
        return count;
    }

    /// <summary>取方法名起始到方法收尾的源码片段（大括号配平）。</summary>
    private static string SliceMethod(string source, string signature)
    {
        var start = source.IndexOf(signature, StringComparison.Ordinal);
        Assert.True(start >= 0, $"未在源码中找到 {signature}");
        var open = source.IndexOf('{', start);
        var depth = 0;
        for (var i = open; i < source.Length; i++)
        {
            if (source[i] == '{') depth++;
            else if (source[i] == '}' && --depth == 0) return source[start..(i + 1)];
        }
        throw new InvalidOperationException("方法体大括号不配平");
    }

    private static string FindAppSourceDir()
    {
        var dir = new DirectoryInfo(AppContext.BaseDirectory);
        while (dir is not null)
        {
            var candidate = Path.Combine(dir.FullName, "windows", "src", "Aegis.Windows.App");
            if (File.Exists(Path.Combine(candidate, "Aegis.Windows.App.csproj")))
                return candidate;
            dir = dir.Parent!;
        }
        throw new InvalidOperationException("未定位到 windows/src/Aegis.Windows.App（仓库布局契约）");
    }
}

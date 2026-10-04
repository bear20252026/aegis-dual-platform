using Aegis.Windows.Broker;
using Aegis.Windows.Core.Security;
using Xunit;

namespace Aegis.Windows.Broker.Tests;

/// <summary>审计第七轮（2026-10-04·R7-CS2-02）：隐私网络边界的判定锚。
/// 该边界是**纯托管层拒绝码**——Rust 核心向量里没有 private_network，导航主链的
/// 跨语言向量兜不住它；此前 windows/tests 全仓零断言（任何人把检查挪到会话校验之后、
/// 或在桥缺失分支提前 return，708 例仍全绿——与 R6-26「接入面零调用者」同一失效模式）。
/// 本类三重锚定：① 谓词矩阵逐形态（含八进制/IPv6/.local/端口豁免）；
/// ② 导航、消费、下载三类出口各自的拒绝码与审计留痕；③ 源码静态锚，证明子资源层
/// （HostWebView.OnWebResourceRequested）真的调用了同一谓词，而不是只有定义。</summary>
public sealed class PrivateNetworkBoundaryTests : IDisposable
{
    // 与 BrowserPolicyBrokerTests 同口径：下载/导航拒绝会写 security.log，
    // 重定向到临时目录，绝不落真实用户目录
    private string LogDir { get; } =
        Path.Combine(Path.GetTempPath(), $"aegis_pnb_log_{Guid.NewGuid():N}");

    public PrivateNetworkBoundaryTests()
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

    // ① 谓词矩阵：(URL, 是否应判为隐私网络边界内)
    public static TheoryData<string, bool> BoundaryMatrix => new()
    {
        { "http://127.0.0.1:6379/", true },           // 本机服务（redis）
        { "http://localhost/admin", true },
        { "http://192.168.1.1/set_config", true },     // 路由器管理口
        { "http://169.254.169.254/latest/meta-data/", true },  // 云元数据
        { "http://10.0.0.1/", true },
        { "http://[::1]/", true },                    // IPv6 回环（带方括号形态）
        { "http://0177.0.0.1/", true },               // 前导零八进制 = 127.0.0.1
        { "http://100.64.0.1/", true },               // CGNAT
        { "https://8.8.8.8/", false },                // 公网 IP 对照
        { "https://example.com/path", false },
        { "https://ntp.aegis.local/", false },        // 宿主虚拟主机豁免（首页）
        { "https://geo.aegis.local/geogebra/index.html", false },
        { "https://ntp.aegis.local:8443/", true },    // 非默认端口：不在映射面内
        { "http://ntp.aegis.local/", true },           // 明文不是虚拟主机映射协议
    };

    [Theory]
    [MemberData(nameof(BoundaryMatrix))]
    public void Predicate_Matrix(string url, bool expected)
    {
        Assert.True(Uri.TryCreate(url, UriKind.Absolute, out var uri), url);
        Assert.Equal(expected, PrivateNetworkBoundary.Denies(uri));
    }

    [Fact]
    public void DenyCode_IsSingleSource()
    {
        // 拒绝码与文案单源：审计 reason 与 UI 文案不得各写一份字符串
        Assert.Equal("private_network", PrivateNetworkBoundary.DenyCode);
        Assert.Equal(PrivateNetworkBoundary.DenyCode, PrivateNetworkBoundary.Reason.Code);
    }

    // ② 导航出口
    [Theory]
    [InlineData("http://127.0.0.1:6379/")]
    [InlineData("http://localhost/admin")]
    [InlineData("http://192.168.1.1/set_config")]
    [InlineData("http://169.254.169.254/latest/meta-data/")]
    public void EvaluateNavigation_DeniesPrivateTargetWithExactCode(string url)
    {
        var broker = ManagedBroker();

        var denied = Assert.IsType<Decision.Deny>(
            broker.EvaluateNavigation("session-1", "tab-1", 0, url, "navigation"));

        Assert.Equal("private_network", denied.Reason.Code);
        Assert.Contains(broker.AuditLog, e =>
            e.Decision == "deny" && e.Scope == "navigation" && e.Reason == "private_network");
    }

    [Theory]
    [InlineData("http://[::1]/")]
    [InlineData("http://0177.0.0.1/")]
    [InlineData("http://100.64.0.1/")]
    public void EvaluateNavigation_EncodedPrivateForms_NeverAllowed(string url)
    {
        // 编码变体可能被 OriginPolicy 以 url_policy 先挡下（同样 fail-closed）——
        // 本用例钉的是"绝不放行"，具体拒绝码不锁死，避免与协议层判定顺序耦合
        var broker = ManagedBroker();
        Assert.IsType<Decision.Deny>(
            broker.EvaluateNavigation("session-1", "tab-1", 0, url, "navigation"));
    }

    [Theory]
    [InlineData("https://example.com/path")]
    [InlineData("https://ntp.aegis.local/")]
    [InlineData("https://geo.aegis.local/geogebra/index.html")]
    public void EvaluateNavigation_PublicAndVirtualHostTargetsNotDenyedByBoundary(string url)
    {
        // 公网对照 + 宿主虚拟主机豁免仍在（过度收紧会让首页/画板全被拒——
        // R7-RS-05 同口径：每个私网段两侧都要有公网对照）
        var broker = ManagedBroker();
        Assert.IsType<Decision.Allow>(
            broker.EvaluateNavigation("session-1", "tab-1", 0, url, "navigation"));
    }

    [Fact]
    public void TryConsumeNavigation_RechecksBoundaryOnForgedAction()
    {
        // 消费点复判：原生核心签发的内网授权或调用方伪造动作都不得兑换
        var broker = ManagedBroker();
        var forged = new AuthorizedAction(
            "session-1", "tab-1", 0, "http://169.254.169.254", "GET", "/latest/meta-data/",
            "navigation", DateTime.UtcNow.AddMinutes(1), "forged-nonce", broker.PolicyVersion);

        Assert.False(broker.TryConsumeNavigation(
            forged, "session-1", "tab-1", 0, "http://169.254.169.254/latest/meta-data/", "navigation"));
        Assert.Contains(broker.AuditLog, e =>
            e.Decision == "deny" && e.Reason == "private_network");
    }

    // ② 下载出口（R7-CS1-02——此前该门从不看 URL）
    [Theory]
    [InlineData("http://169.254.169.254/latest/user-data")]
    [InlineData("http://127.0.0.1:8080/export")]
    [InlineData("http://192.168.1.1/firmware.bin")]
    public void AllowDownload_DeniesPrivateTargetWithExactCode(string url)
    {
        var broker = ManagedBroker();

        Assert.False(broker.AllowDownload("session-1", "tab-1", url, "payload", userConfirmed: true));
        Assert.Contains(broker.AuditLog, e =>
            e.Decision == "deny" && e.Scope == "download" && e.Reason == "private_network");
    }

    [Fact]
    public void AllowDownload_PublicTargetStillAllowed()
    {
        // 对照：边界不得把常规下载一并挡死（否则本条门禁红在"过度收紧"上）
        var broker = ManagedBroker();

        Assert.True(broker.AllowDownload(
            "session-1", "tab-1", "https://example.com/file.zip", "file.zip", userConfirmed: false));
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
            e.Decision == "deny" && e.Scope == "download" && e.Reason == "private_network");
    }

    // ③ 静态锚：谓词必须被三层真实调用（只定义不接线正是 R6-26 的失效形态）
    [Fact]
    public void BoundaryIsWiredIntoAllThreeAdmissionLayers()
    {
        var appDir = FindAppSourceDir();
        var brokerSource = File.ReadAllText(
            Path.Combine(appDir, "Broker", "BrowserPolicyBroker.cs"));
        var webViewSource = File.ReadAllText(
            Path.Combine(appDir, "WebView", "HostWebView.cs"));

        // 导航（原生前置 + 托管）+ 消费 + 下载 = broker 内至少 4 处调用
        Assert.True(CountOccurrences(brokerSource, "PrivateNetworkBoundary.Denies") >= 4,
            $"BrowserPolicyBroker.cs 只出现 {CountOccurrences(brokerSource, "PrivateNetworkBoundary.Denies")} 次边界调用");
        // 子资源层：OnWebResourceRequested 内必须调用同一谓词
        var handler = SliceMethod(webViewSource, "private void OnWebResourceRequested");
        Assert.Contains("PrivateNetworkBoundary.Denies(", handler);
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

    /// <summary>取方法名起始到下一个同级方法之前的源码片段（大括号配平）。</summary>
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

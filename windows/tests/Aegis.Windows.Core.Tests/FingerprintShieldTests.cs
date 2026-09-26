namespace Aegis.Windows.Core.Tests;

using Aegis.Windows.WebView;
using Xunit;

/// <summary>M3 指纹防护全量管道单测（JS 不可在 dotnet 内执行——锁定脚本
/// 构造契约：种子参数化、确定性输出、关键防护阶段齐备、种子不落盘外传面）。</summary>
public sealed class FingerprintShieldTests
{
    private const string SeedA = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef";

    // ===== CS-185（审计 2026-09-26）：非法种子入口拒绝 =====

    [Theory]
    [InlineData(null)]
    [InlineData("")]
    [InlineData("0123456789abcdef")]                                        // 过短
    [InlineData("0123456789ABCDEF0123456789ABCDEF0123456789ABCDEF0123456789ABCDEF12")]  // 大写（契约小写）
    [InlineData("g123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef")]    // 非 hex
    [InlineData("'; evil(); '0123456789abcdef0123456789abcdef0123456789abc")]           // 注入形态
    public void BuildScript_RejectsInvalidSeeds(string? seed)
    {
        Assert.Throws<ArgumentException>(() => FingerprintShield.BuildScript(seed!));
    }

    [Fact]
    public void NewSessionSeedIs64HexCharsAndUnique()
    {
        var first = FingerprintShield.NewSessionSeed();
        var second = FingerprintShield.NewSessionSeed();

        Assert.Matches("^[0-9a-f]{64}$", first);
        Assert.Matches("^[0-9a-f]{64}$", second);
        Assert.NotEqual(first, second);  // 每会话独立种子（加密随机）
    }

    [Fact]
    public void BuildScriptIsDeterministicPerSeed() =>
        Assert.Equal(
            FingerprintShield.BuildScript(SeedA),
            FingerprintShield.BuildScript(SeedA));

    [Fact]
    public void BuildScriptEmbedsSeedOnlyInConstant()
    {
        var script = FingerprintShield.BuildScript(SeedA);

        Assert.Contains($"var SEED = '{SeedA}';", script);
        Assert.DoesNotContain(SeedA, FingerprintShield.BuildScript("ff" + SeedA[2..]));
    }

    [Fact]
    public void BuildScriptContainsAllHardeningStages()
    {
        var script = FingerprintShield.BuildScript(SeedA);

        // 红蓝对抗关键阶段（对齐 Python fingerprint_pipeline.py 结构）
        Assert.Contains("getOwnPropertyDescriptor", script);   // FIX-1/2 原型链
        Assert.Contains("Function.prototype.toString", script); // ToStringGuard
        Assert.Contains("deriveSeed", script);                  // PerSiteSeed
        Assert.Contains("toDataURL", script);                   // Canvas
        Assert.Contains("WebGLRenderingContext", script);       // WebGLSpoof
        Assert.Contains("hardwareConcurrency", script);
        Assert.Contains("createOscillator", script);            // AudioContext
        Assert.Contains("getBattery", script);
        Assert.Contains("RTCPeerConnection", script);           // FIX-3 WebRTC
        Assert.Contains("availWidth", script);                  // Letterbox
        Assert.Contains("gclid", script);                       // fetch 追踪参数剥离
        Assert.Contains("FontFaceSet", script);                 // 字体枚举
        Assert.Contains("performance.now", script);             // TimerPrecision
    }

    [Fact]
    public void CanvasPerturbationNeverWritesBackToVisibleCanvas()
    {
        // 修 Python「putImageData 污染可见画布」缺陷——画布写回只允许发生在
        // 离屏副本 tmp 上
        var script = FingerprintShield.BuildScript(SeedA);

        var canvasProxy = script[script.IndexOf("var canvasProxy", StringComparison.Ordinal)..];
        canvasProxy = canvasProxy[..canvasProxy.IndexOf("WebGL", StringComparison.Ordinal)];
        Assert.Contains("createElement('canvas')", canvasProxy);
        Assert.Contains("origToDataURL.apply(tmp", canvasProxy);
        Assert.DoesNotContain("putImageData(imageData, 0, 0);\n                return origToDataURL.apply(this", canvasProxy);
    }

    [Fact]
    public void MaxViewportDimsReturnsInt32Array()
    {
        // CS-006 回归：MAX_VIEWPORT_DIMS(0x0D3A) 规范要求 Int32Array——
        // Float32Array 可被类型检测识破（legacy 栈已修，C# 移植版漏改）
        var script = FingerprintShield.BuildScript(SeedA);
        Assert.DoesNotContain("Float32Array", script);
        Assert.Contains("new Int32Array([16384, 16384])", script);
    }

    [Fact]
    public void WindowSizeOverrideCapturesOriginalGetter()
    {
        // RS-001 孪生回归：window 尺寸覆盖必须先捕获原 getter——getter 内
        // 再读同名属性即无限自递归（页面首次读 innerWidth 即栈溢出）
        var script = FingerprintShield.BuildScript(SeedA);
        Assert.Contains("origGetOPD.call(Object, window, 'innerWidth')", script);
        Assert.DoesNotContain("return roundTo(window.innerWidth", script);
        Assert.DoesNotContain("return roundTo(window.innerHeight", script);
    }

    [Fact]
    public void TrackingParamStripIsCaseInsensitive()
    {
        // RS-010 孪生回归：注入 JS 的参数剥离大小写不敏感（Gclid 变体绕过）
        var script = FingerprintShield.BuildScript(SeedA);
        Assert.Contains("lowerSet[k.toLowerCase()]", script);
        Assert.DoesNotContain("searchParams.has(p)", script);
    }
}

/// <summary>C14 批（审计 2026-09-26）：WebView2 加收紧面直测（CS-183——
/// 受信本地虚拟主机白名单零覆盖补齐）。</summary>
public sealed class WebView2HardeningTests
{
    [Theory]
    [InlineData("ntp.aegis.local", true)]
    [InlineData("NTP.AEGIS.LOCAL", true)]     // 大小写不敏感
    [InlineData("chrome.aegis.local", true)]  // 预留宿主在白名单
    [InlineData("evil.example", false)]
    [InlineData("sub.ntp.aegis.local", false)] // 子域不匹配（精确白名单）
    [InlineData("", false)]
    public void IsTrustedLocalHost_ExactWhitelistOnly(string host, bool expected) =>
        Assert.Equal(expected, WebView2Hardening.IsTrustedLocalHost(host));
}

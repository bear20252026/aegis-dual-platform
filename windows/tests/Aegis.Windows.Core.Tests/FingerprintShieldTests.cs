namespace Aegis.Windows.Core.Tests;

using Aegis.Windows.WebView;
using Xunit;

/// <summary>M3 指纹防护全量管道单测（JS 不可在 dotnet 内执行——锁定脚本
/// 构造契约：种子参数化、确定性输出、关键防护阶段齐备、种子不落盘外传面）。</summary>
public sealed class FingerprintShieldTests
{
    private const string SeedA = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef";

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
}

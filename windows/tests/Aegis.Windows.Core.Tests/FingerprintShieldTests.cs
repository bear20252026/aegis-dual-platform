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
        var canvasProxy = SliceCanvasProxy();

        Assert.Contains("createElement('canvas')", canvasProxy);
        Assert.Contains("origToDataURL.apply(tmp", canvasProxy);
        Assert.DoesNotContain("putImageData(imageData, 0, 0);\n                return origToDataURL.apply(this", canvasProxy);
    }

    // ===== CS-335/336（2026-10-01 审计）：canvas 噪声门禁删除 + per-site 种子 =====

    /// <summary>截取 canvas 代理段（var canvasProxy 到代理注册行之前——
    /// 段内注释含 "WebGL" 字样，不能以它作段尾标记）。</summary>
    private string SliceCanvasProxy()
    {
        var script = FingerprintShield.BuildScript(SeedA);
        var slice = script[script.IndexOf("var canvasProxy", StringComparison.Ordinal)..];
        return slice[..slice.IndexOf("registerProxy(canvasProxy", StringComparison.Ordinal)];
    }

    [Fact]
    public void CanvasNoise_HasNo2dContextGate_OffscreenCopyCoversWebglCanvases()
    {
        // CS-335（P1）：删除 getContext('2d') 门禁——WebGL 画布取 2d 上下文得
        // null 即无噪声回退，且无上下文画布被永久锁 2d。改离屏副本 drawImage
        // 取像素（对 2d/WebGL 画布同路径生效）；原画布上下文绝不被触碰
        var canvasProxy = SliceCanvasProxy();

        Assert.DoesNotContain("this.getContext", canvasProxy);
        Assert.Contains("tmp.getContext('2d')", canvasProxy);
        Assert.Contains("drawImage(this, 0, 0)", canvasProxy);  // 离屏副本取像素——WebGL 同路径
    }

    [Fact]
    public void CanvasNoise_UsesPerSiteSeed_CachedOnceAtLoad()
    {
        // CS-336：噪声种子改 per-site siteSeed——此前用会话级 SEED（同用户跨站
        // 噪声相同，可跨站关联），且 siteSeed 计算后零引用（死代码）；
        // siteSeed 在 IIFE 加载时缓存一次
        var script = FingerprintShield.BuildScript(SeedA);
        Assert.Contains("var siteSeed = deriveSeed(SEED, getETLD1(location.hostname));", script);

        var canvasProxy = SliceCanvasProxy();
        Assert.Contains("parseInt(siteSeed.slice(0, 8), 16)", canvasProxy);
        Assert.DoesNotContain("parseInt(SEED.slice(0, 8), 16)", canvasProxy);
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
        // CS-331：lowerSet 提升为 IIFE 顶层 TRACKING_LOWER 冻结集（每次
        // fetch/XHR 不再重建 ~40 键对象——请求热路径重复分配）
        var script = FingerprintShield.BuildScript(SeedA);
        Assert.Contains("TRACKING_LOWER[k.toLowerCase()]", script);
        Assert.DoesNotContain("searchParams.has(p)", script);
        // 冻结集只构建一次（顶层），函数体内不再逐次 forEach 构建
        var buildOnce = "TRACKING_PARAMS.forEach(function(p) { TRACKING_LOWER[p.toLowerCase()] = true; });";
        Assert.Contains(buildOnce, script);
    }

    // ===== C19b 批（审计 2026-09-26）：CS-300 时间戳自曝面 =====

    [Fact]
    public void DateNowOverride_StaysIntegerMilliseconds()
    {
        // CS-300：Date.now 分支不得套随机抖动——非整数（Number.isInteger
        // (Date.now())===false）一行即识破防护存在
        var script = FingerprintShield.BuildScript(SeedA);
        Assert.Contains("function reducePrecisionInteger(v) { return Math.round(reducePrecision(v)); }", script);
        var dateBranch = script[script.IndexOf("var origDateNow = Date.now", StringComparison.Ordinal)..];
        dateBranch = dateBranch[..dateBranch.IndexOf("} catch(e) {}", StringComparison.Ordinal)];
        Assert.Contains("return reducePrecisionInteger(origDateNow())", dateBranch);
        Assert.DoesNotContain("return reducePrecision(origDateNow())", script);
    }

    [Fact]
    public void PerformanceNowOverride_IsMonotonicNonDecreasing()
    {
        // CS-300：performance.now 钳单调非递减——随机抖动产生时间回退
        //（t2 < t1）本身就是检测信号
        var script = FingerprintShield.BuildScript(SeedA);
        Assert.Contains("if (v < lastPerf) v = lastPerf;", script);
        Assert.Contains("var lastPerf = -Infinity;", script);
        // 旧实现（无钳制）不得残留
        Assert.DoesNotContain("return reducePrecision(origPerfNow());", script);
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

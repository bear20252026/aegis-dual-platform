namespace Aegis.Windows.Broker.Tests;

using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Runtime.InteropServices;
using Aegis.Windows.Core.Security;
using Xunit;

/// <summary>审计第六轮遗留缺口收口（2026-10-04）：核心 host 黑名单注入绑定
/// <c>aegis_policy_core_broker_update_host_denylist_json</c> 的应答解析与真·跨界往返。
/// 应答解析用例无条件执行（纯托管，钉住 accepted/input 与"非 ok 不得报成功"口径）。
/// 跨界用例沿用本仓反假绿锚点口径（见 BrowserPolicyBrokerTests 的
/// DeclaredNativeModeMustActuallyRoundTripAndSupportTwoCoexistingBrokers）：
/// 一旦声明原生模式就必须真跑一次并硬断言，两个分支（核心已支持该入口 / 旧核心
/// 缺该入口）都有确定结论，绝不"环境缺失就 return 报绿"。</summary>
public sealed class NativePolicyCoreDenylistTests : IDisposable
{
    private const string HostDenylistExport = "aegis_policy_core_broker_update_host_denylist_json";

    private readonly string _logDir =
        Path.Combine(Path.GetTempPath(), $"aegis_native_denylist_{Guid.NewGuid():N}");

    private readonly Xunit.Abstractions.ITestOutputHelper _output;

    public NativePolicyCoreDenylistTests(Xunit.Abstractions.ITestOutputHelper output)
    {
        _output = output;
        Directory.CreateDirectory(_logDir);
        SecurityLog.SecurityLogDirOverride = _logDir;
        CoreDenylistPublisher.ResetForTests();
    }

    public void Dispose()
    {
        CoreDenylistPublisher.ResetForTests();
        SecurityLog.SecurityLogDirOverride = null;
        try { Directory.Delete(_logDir, true); } catch (IOException) { }
    }

    private string[] LogLines()
    {
        var path = Path.Combine(_logDir, "security.log");
        return File.Exists(path) ? File.ReadAllLines(path) : Array.Empty<string>();
    }

    // ===== 应答解析（不需要原生库，恒执行） =====

    [Fact]
    public void ParseUpdateResponse_OkEnvelope_PreservesAcceptedAgainstInput()
    {
        var result = NativePolicyCoreBridge.ParseUpdateResponse(
            """{"decision":"ok","accepted":2,"input":3}""", 3);

        Assert.True(result.Published);
        Assert.Equal(CoreDenylistOutcome.PartiallyPublished, result.Outcome);
        Assert.Equal(2, result.Accepted);
        Assert.Equal(3, result.Input);
        Assert.Equal(1, result.RejectedEntryCount);
    }

    [Fact]
    public void ParseUpdateResponse_FullAccept_IsNotPartial()
    {
        var result = NativePolicyCoreBridge.ParseUpdateResponse(
            """{"decision":"ok","accepted":40,"input":40}""", 40);

        Assert.Equal(CoreDenylistOutcome.Published, result.Outcome);
        Assert.Equal(0, result.RejectedEntryCount);
    }

    [Fact]
    public void ParseUpdateResponse_CoreDenyEnvelope_IsNeverReportedAsPublished()
    {
        // 核心侧的 deny 信封（含分配失败 FALLBACK，abi_version=0）——
        // "没接上"绝不能被读成"接上了"
        var result = NativePolicyCoreBridge.ParseUpdateResponse(
            """{"abi_version":0,"decision":"deny","reason":{"code":"ffi_response_alloc","detail":"response allocation failed","explanation":"denied by boundary"}}""",
            5);

        Assert.False(result.Published);
        Assert.Equal(CoreDenylistOutcome.NotPublished, result.Outcome);
        Assert.Equal("ffi_response_alloc", result.Detail);
        Assert.Equal(5, result.RejectedEntryCount);  // 整批都没进核心
    }

    [Fact]
    public void ParseUpdateResponse_UnparsableOrCountless_IsNotPublishedFully()
    {
        Assert.Equal(CoreDenylistOutcome.NotPublished,
            NativePolicyCoreBridge.ParseUpdateResponse("not json", 2).Outcome);
        // ok 但没带计数：按"0 条被接受"处理（宁可低估，不虚报成功）
        var countless = NativePolicyCoreBridge.ParseUpdateResponse("""{"decision":"ok"}""", 2);
        Assert.True(countless.Published);
        Assert.Equal(CoreDenylistOutcome.PartiallyPublished, countless.Outcome);
        Assert.Equal(2, countless.RejectedEntryCount);
    }

    [Fact]
    public void MissingExportOutcome_IsDistinguishableFromFailure()
    {
        // 缺符号（旧 DLL）与"调用失败"是两回事：前者只留痕一次、且不得伪装成失败
        var missing = CoreDenylistUpdateResult.MissingExport(3);
        Assert.False(missing.Published);
        Assert.Equal(CoreDenylistOutcome.ExportMissing, missing.Outcome);
        Assert.Equal(3, missing.RejectedEntryCount);
    }

    // ===== 真·跨界（声明原生模式时必跑，两分支都硬断言） =====

    [Fact]
    public void HostDenylistInjectionAgainstRealCoreEitherDeniesAtCoreOrDegradesExplicitly()
    {
        if (!NativePolicyCoreGate.IsRequired)
            return;  // 未声明原生模式（托管裁决 job）——跨界断言由原生 job 执行，锚点同口径

        var bridge = Assert.IsAssignableFrom<NativePolicyCoreBridge>(
            NativePolicyCoreBridgeHub.Acquire("1.0"));
        try
        {
            // 独立探针：不信被测试代码的解析结论，直接查导出表
            var exportPresent = ExportIsPresent();
            _output.WriteLine($"[DENYLIST-E2E] 原生模式已声明；导出表探针 exportPresent={exportPresent}");
            var result = bridge.UpdateHostDenylist(new[] { "core-denylist-e2e.example" });
            Assert.Equal(1, result.Input);

            if (exportPresent)
            {
                _output.WriteLine("PROVEN-BRANCH: 核心已支持注入入口——断言核心侧 threat_blocklist 拒绝");
                Assert.Equal(CoreDenylistOutcome.Published, result.Outcome);
                Assert.Equal(1, result.Accepted);
                Assert.True(bridge.CreateSession("denylist-e2e", "tab-1", 0, 120));
                var deny = Assert.IsType<Decision.Deny>(bridge.EvaluateNavigation(
                    "denylist-e2e", "tab-1", 0, "https://core-denylist-e2e.example/", "navigation"));
                Assert.Equal("threat_blocklist", deny.Reason.Code);
                // 未注入的 host 必须仍放行——本入口绝不默认 deny-all
                Assert.IsType<Decision.Allow>(bridge.EvaluateNavigation(
                    "denylist-e2e", "tab-1", 0, "https://allowed-e2e.example/", "navigation"));
            }
            else
            {
                // 降级路径（本 checkout 的预构建 DLL 即此形态）：不抛、如实回报
                // "核心黑名单未发布"，且老核心的导航链完好如初
                _output.WriteLine("PROVEN-BRANCH: 旧核心缺该导出——断言降级（未发布 + 导航链完好）");
                Assert.Equal(CoreDenylistOutcome.ExportMissing, result.Outcome);
                Assert.False(result.Published);
                Assert.True(bridge.CreateSession("denylist-e2e", "tab-1", 0, 120));
                Assert.IsType<Decision.Allow>(bridge.EvaluateNavigation(
                    "denylist-e2e", "tab-1", 0, "https://allowed-e2e.example/", "navigation"));
            }
        }
        finally
        {
            // 绝不把测试条目留在进程级核心 broker 上（会污染后续用例的裁决）
            bridge.UpdateHostDenylist(Array.Empty<string>());
            NativePolicyCoreBridgeHub.Release(bridge);
        }
    }

    [Fact]
    public void DisposedBridge_DenylistInjectionFailsClosedWithoutThrowing()
    {
        if (!NativePolicyCoreGate.IsRequired)
            return;  // 同上：R6 生命周期回归的跨界面

        var bridge = Assert.IsAssignableFrom<NativePolicyCoreBridge>(
            NativePolicyCoreBridgeHub.Acquire("1.0"));
        NativePolicyCoreBridgeHub.Release(bridge);  // 引用归零即真正释放
        Assert.Null(NativePolicyCoreBridgeHub.Shared);

        // Dispose 之后不得再进 DLL（不得 DangerousGetHandle）——如实回报未发布
        var result = bridge.UpdateHostDenylist(new[] { "after-dispose.example" });
        _output.WriteLine($"PROVEN-BRANCH: 已释放桥的注入调用 outcome={result.Outcome} detail={result.Detail}");
        Assert.False(result.Published);
        Assert.Equal(CoreDenylistOutcome.NotPublished, result.Outcome);
        Assert.Equal("bridge_disposed", result.Detail);
    }

    [Fact]
    public void BridgeAcquisitionByHub_RepushesCurrentSnapshotIntoCore()
    {
        if (!NativePolicyCoreGate.IsRequired)
            return;  // 同上：本用例证明 Hub→publisher 的真实接线

        // 生产接线：桥来源取进程级共享持有者，应答来自真实核心（不加模拟缝）
        CoreDenylistPublisher.BridgeProviderForTests = () => NativePolicyCoreBridgeHub.Shared;
        // 排空前序用例可能残留的引用，确保观察到的是"无桥→有桥"这一次跃迁；
        // 排不空即红（本仓不接受"环境不满足就静默通过"）
        while (NativePolicyCoreBridgeHub.Shared is { } leaked)
            NativePolicyCoreBridgeHub.Release(leaked);
        Assert.Null(CoreDenylistPublisher.CorePushForTests);  // 不加模拟缝——本用例走真实桥与真实核心
        Assert.Null(NativePolicyCoreBridgeHub.Shared);        // 观察到的必须是"无桥→有桥"这一次跃迁

        new SharedBlockedHosts().Publish(new BlockedHosts(["hub-repush-e2e.example"]));
        Assert.DoesNotContain(LogLines(), l => l.Contains("原生桥建立"));

        var bridge = Assert.IsAssignableFrom<NativePolicyCoreBridge>(
            NativePolicyCoreBridgeHub.Acquire("1.0"));
        try
        {
            // 桥建立的那一刻必须将当前快照补推进核心（否则整会话核心空名单）
            var line = Assert.Single(LogLines(), l => l.Contains("原生桥建立"));
            _output.WriteLine($"PROVEN-BRANCH: Hub→publisher 补推留痕：{line}");
            Assert.True(
                line.Contains("已发布 1/1") || line.Contains("未导出 host 黑名单入口"),
                $"桥建立补推的留痕必须是两种真实结论之一，实际：{line}");
        }
        finally
        {
            bridge.UpdateHostDenylist(Array.Empty<string>());
            NativePolicyCoreBridgeHub.Release(bridge);
        }
    }

    /// <summary>直接查模块导出表（与桥实现无关的对照探针）。缺库即抛——
    /// 本文件的跨界用例绝不"探测不到就当通过"。</summary>
    private static bool ExportIsPresent()
    {
        var name = NativePolicyCoreGate.LibraryPath ?? "aegis_policy_core";
        if (!NativeLibrary.TryLoad(name, out var handle))
            throw new InvalidOperationException("原生模式已声明但策略核心库加载失败");
        try
        {
            return NativeLibrary.TryGetExport(handle, HostDenylistExport, out _);
        }
        finally
        {
            NativeLibrary.Free(handle);
        }
    }
}

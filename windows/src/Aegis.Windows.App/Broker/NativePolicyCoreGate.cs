namespace Aegis.Windows.Broker;

using System;
using System.Runtime.InteropServices;

/// <summary>
/// 原生策略核心的显式启用门禁。
/// 默认关闭时保持经验证的 C# Broker 路径；显式启用后，任意库加载或 ABI 探测失败均拒绝副作用，
/// 禁止静默切换到另一套策略实现。
/// </summary>
public static class NativePolicyCoreGate
{
    public const string EnableEnvironmentVariable = "AEGIS_REQUIRE_NATIVE_POLICY_CORE";
    public const string LibraryPathEnvironmentVariable = "AEGIS_NATIVE_POLICY_CORE_PATH";
    /// <summary>C ABI v3 提供策略核心托管的确认登记、批准和拒绝入口。</summary>
    public const uint ExpectedAbiVersion = 3;

    public static bool IsRequired =>
        string.Equals(Environment.GetEnvironmentVariable(EnableEnvironmentVariable), "1", StringComparison.Ordinal)
        // 审计第六轮（2026-10-04）：第二来源——安装期标记（HKCU，见
        // InstalledBuildMarker 的键路径与理由）。环境变量只在 CI 构建步的 shell
        // 里赋值，不随安装包交付，于是出货制品的运行时恒 Disabled()：
        // aegis_policy_core.dll 随包发布却从不被咨询。标记只存在于已安装的
        // 发布构建，故 dotnet build 的开发机恒走 Disabled()（不毁掉开发工作流）。
        || InstalledBuildMarker.IsSet(InstalledBuildMarker.NativePolicyCoreValueName);

    /// <summary>库路径仅由环境变量指定（开发/CI 指向 dist 里的构建产物）；
    /// 安装构建不写该值——DLL 与 exe 同目录，缺省库名 "aegis_policy_core"
    /// 由 LoadLibrary 的应用目录搜索命中。</summary>
    public static string? LibraryPath => Environment.GetEnvironmentVariable(LibraryPathEnvironmentVariable);

    /// <summary>启动期/决策期门禁探测。名称保留 "FromEnvironment"（调用点已
    /// 稳定）——判定源为环境变量 + 安装期标记两者，见 IsRequired。
    /// 语义不变：未要求 → Disabled() 放行托管 broker；要求而库不可用 →
    /// Block() 且绝不回退到另一套策略实现。</summary>
    public static NativePolicyCoreGateResult ProbeFromEnvironment()
    {
        if (!IsRequired)
            return NativePolicyCoreGateResult.Disabled();

        return ProbeLibrary(LibraryPath ?? "aegis_policy_core");
    }

    /// <summary>
    /// 探测指定的策略核心库。仅供启动期门禁和构建制品测试使用；失败信息不包含本机绝对路径。
    /// </summary>
    public static NativePolicyCoreGateResult ProbeLibrary(string libraryNameOrPath)
    {
        if (string.IsNullOrWhiteSpace(libraryNameOrPath))
            return NativePolicyCoreGateResult.Block("native_policy_core_path_invalid");

        if (!NativeLibrary.TryLoad(libraryNameOrPath, out var handle))
            return NativePolicyCoreGateResult.Block("native_policy_core_unavailable");

        try
        {
            if (!NativeLibrary.TryGetExport(handle, "aegis_policy_core_abi_version", out var symbol))
                return NativePolicyCoreGateResult.Block("native_policy_core_abi_symbol_missing");

            var abiVersion = Marshal.GetDelegateForFunctionPointer<AbiVersionDelegate>(symbol)();
            return abiVersion == ExpectedAbiVersion
                ? NativePolicyCoreGateResult.Enabled()
                : NativePolicyCoreGateResult.Block("native_policy_core_abi_mismatch");
        }
        catch (Exception)
        {
            return NativePolicyCoreGateResult.Block("native_policy_core_probe_failed");
        }
        finally
        {
            NativeLibrary.Free(handle);
        }
    }

    [UnmanagedFunctionPointer(CallingConvention.Cdecl)]
    private delegate uint AbiVersionDelegate();
}

/// <summary>原生策略核心门禁的可审计结果；错误码不包含 URL、令牌或网页内容。</summary>
public sealed record NativePolicyCoreGateResult(bool AllowsPlatformBroker, string? DenialCode)
{
    public static NativePolicyCoreGateResult Disabled() => new(true, null);

    public static NativePolicyCoreGateResult Enabled() => new(true, null);

    public static NativePolicyCoreGateResult Block(string denialCode) => new(false, denialCode);
}

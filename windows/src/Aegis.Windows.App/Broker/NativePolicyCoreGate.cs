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
    public const uint ExpectedAbiVersion = 1;

    public static NativePolicyCoreGateResult ProbeFromEnvironment()
    {
        if (!string.Equals(Environment.GetEnvironmentVariable(EnableEnvironmentVariable), "1", StringComparison.Ordinal))
            return NativePolicyCoreGateResult.Disabled();

        return ProbeLibrary("aegis_policy_core");
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

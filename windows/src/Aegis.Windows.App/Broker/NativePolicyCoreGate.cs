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
    /// <summary>C ABI v3 提供策略核心托管的确认登记、批准和拒绝入口；
    /// <b>v4</b>（第八轮 ⑨，R8-RS-14）把黑名单注入的 <c>clear</c> 参数扩成档位
    /// （0 追加 / 1 整批替换 / 2 开暂存会话 / 3 提交），消除「约 85 批推送期间
    /// 判定读的是不完整名单」这一窗口。宿主与核心必须同版：探测不一致时门禁
    /// fail-closed 拒绝加载，绝不静默换另一套策略实现。</summary>
    public const uint ExpectedAbiVersion = 4;

    /// <summary>三个判定源合一（AX-05）：编译进产物的构建要求 ⇒ 环境变量 ⇒ 安装期标记。
    /// 短路顺序有语义：构建常量随 exe/dll 走，清注册表、脱离安装器、直接双击 EXE
    /// 都摘不掉它；环境变量保留给开发/CI 显式打开（不随安装包交付）；HKCU 标记是
    /// 第六轮给「已安装构建」加的第二来源，现在仍是第三来源（旧安装升级上来、
    /// 或用户手工设置的场景）。</summary>
    public static bool IsRequired =>
        ResolveRequirement(
            NativePolicyCoreBuildMarker.RequiredByThisBuild,
            Environment.GetEnvironmentVariable(EnableEnvironmentVariable),
            InstalledBuildMarker.IsSet(InstalledBuildMarker.NativePolicyCoreValueName));

    /// <summary>纯判定面（可单测——真实注册表与环境变量不可 JVM/CLR 侧注入）。
    /// 任一源要求即要求；环境变量只认精确 "1"（与 InstalledBuildMarker 的
    /// DWORD 1 / 字符串 "1" 同口径，"true"/"0"/乱值都不算打开）。</summary>
    internal static bool ResolveRequirement(
        bool requiredByBuild, string? environmentValue, bool installedMarkerSet) =>
        requiredByBuild
        || string.Equals(environmentValue, "1", StringComparison.Ordinal)
        || installedMarkerSet;

    /// <summary>库路径仅由环境变量指定（开发/CI 指向 dist 里的构建产物）；
    /// 安装构建不写该值——DLL 与 exe 同目录，缺省库名 "aegis_policy_core"
    /// 由 LoadLibrary 的应用目录搜索命中。</summary>
    public static string? LibraryPath => Environment.GetEnvironmentVariable(LibraryPathEnvironmentVariable);

    /// <summary>启动期/决策期门禁探测。名称保留 "FromEnvironment"（调用点已
    /// 稳定）——判定源是三个：编译进产物的构建要求 + 环境变量 + 安装期标记，见 IsRequired。
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

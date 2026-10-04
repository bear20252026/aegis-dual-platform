namespace Aegis.Windows.Broker;

using System;
using System.Runtime.InteropServices;
using System.Text.Json.Serialization;

/// <summary>NativePolicyCoreBridge 的原生互操作爿（自同名主文件拆出以守单文件
/// 行数红线）——职责是「如何跨越 ABI 边界」：JSON 线格式记录、两个 SafeHandle
/// 与全部 C 导出委托签名。主文件只留决策入口与租约纪律（R7-CS1-15：
/// 一切跨界调用必须先取得引用计数租约，取不到即 fail-closed）。</summary>
public sealed partial class NativePolicyCoreBridge
{
    private sealed record NativeAction(
        [property: JsonPropertyName("session_id")] string SessionId,
        [property: JsonPropertyName("tab_id")] string TabId,
        [property: JsonPropertyName("document_generation")] ulong DocumentGeneration,
        [property: JsonPropertyName("origin")] string Origin,
        [property: JsonPropertyName("method")] string Method,
        [property: JsonPropertyName("canonical_parameters")] string CanonicalParameters,
        [property: JsonPropertyName("scope")] string Scope,
        [property: JsonPropertyName("expires_at")] long ExpiresAt,
        [property: JsonPropertyName("nonce")] string Nonce,
        [property: JsonPropertyName("policy_version")] string PolicyVersion);

    /// <summary>CS-207：原生库句柄 SafeHandle——**镜像常驻，终结不 FreeLibrary**
    /// （R7-CS1-15：卸载后仍可能被调用的委托即越界访问入口）。保留 SafeHandle
    /// 形态只为与 broker 句柄一致的关闭语义（IsClosed/IsInvalid 仍可用）。</summary>
    private sealed class NativeLibraryHandle : SafeHandle
    {
        internal NativeLibraryHandle(IntPtr pointer) : base(IntPtr.Zero, true) => SetHandle(pointer);

        public override bool IsInvalid => handle == IntPtr.Zero;

        protected override bool ReleaseHandle()
        {
            // R7-CS1-15（第七轮·崩溃转储实证）：不释放镜像——常驻进程。
            // 崩溃转储的模块列表里 aegis_policy_core.dll 已不在场，即 0xC0000005
            // 来自"调用已卸载镜像中的函数指针"：委托（delegate）指向镜像地址，而它的
            // 生命周期与某一个桥实例并不一对一（桥可被 Dispose/终结，委托却被另一个仍
            // 在用的桥持有；门禁探测另有 TryLoad/Free 配平）。只要任何委托还可能被调用，
            // FreeLibrary 就是越界访问入口。原 CS-376 只处理"Free 抛异常"，未处理
            // "Free 成功才是缺陷"。进程退出时由 OS 统一回收映射。
            return true;
        }
    }

    /// <summary>CS-207：原生 broker 句柄 SafeHandle——关键终结兜底 brokerFree。</summary>
    private sealed class NativeBrokerHandle : SafeHandle
    {
        private readonly BrokerFreeDelegate _free;

        internal NativeBrokerHandle(IntPtr pointer, BrokerFreeDelegate free) : base(IntPtr.Zero, true)
        {
            SetHandle(pointer);
            _free = free;
        }

        public override bool IsInvalid => handle == IntPtr.Zero;

        protected override bool ReleaseHandle()
        {
            _free(handle);
            return true;
        }
    }

    [UnmanagedFunctionPointer(CallingConvention.Cdecl)]
    private delegate uint AbiVersionDelegate();
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)]
    private delegate IntPtr BrokerNewDelegate(IntPtr policyVersion);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)]
    private delegate void BrokerFreeDelegate(IntPtr broker);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)]
    private delegate void StringFreeDelegate(IntPtr response);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)]
    private delegate byte CreateSessionDelegate(IntPtr broker, IntPtr sessionId, IntPtr tabId, ulong generation, ulong ttlSeconds);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)]
    private delegate byte DestroySessionDelegate(IntPtr broker, IntPtr sessionId);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)]
    private delegate byte AdvanceGenerationDelegate(IntPtr broker, IntPtr sessionId, IntPtr tabId, ulong nextGeneration);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)]
    private delegate IntPtr EvaluateNavigationDelegate(IntPtr broker, IntPtr sessionId, IntPtr tabId, ulong generation, IntPtr rawUrl, IntPtr scope);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)]
    private delegate IntPtr RequestNavigationConfirmationDelegate(IntPtr broker, IntPtr sessionId, IntPtr tabId, ulong generation, IntPtr rawUrl, IntPtr scope);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)]
    private delegate IntPtr ApproveNavigationConfirmationDelegate(IntPtr broker, IntPtr nonce, IntPtr rawUrl, IntPtr scope);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)]
    private delegate byte RejectNavigationConfirmationDelegate(IntPtr broker, IntPtr nonce);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)]
    private delegate IntPtr ConsumeNavigationDelegate(IntPtr broker, IntPtr actionJson, IntPtr rawUrl, IntPtr scope);
}

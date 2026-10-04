namespace Aegis.Windows.Broker;

using System;
using System.Runtime.InteropServices;
using System.Text.Json;

/// <summary>
/// 受控 Rust 策略核心桥接。它只使用明确的 C ABI 导出和 UTF-8 JSON，不向托管端暴露 Rust 内存布局。
/// 所有加载、解析或 ABI 异常均被调用方转换为拒绝，禁止退回到另一套策略实现。
/// </summary>
public sealed partial class NativePolicyCoreBridge : IDisposable
{
    private const uint ExpectedAbiVersion = NativePolicyCoreGate.ExpectedAbiVersion;
    // CS-207：裸 IntPtr 换 SafeHandle——关键终结兜底释放（Dispose 遗漏时
    // 原生库句柄/broker 仍由临界终结器回收）
    private readonly NativeLibraryHandle _library;
    private readonly NativeBrokerHandle _brokerHandle;
    private readonly BrokerFreeDelegate _brokerFree;
    private readonly StringFreeDelegate _stringFree;
    private readonly CreateSessionDelegate _createSession;
    private readonly DestroySessionDelegate _destroySession;
    private readonly AdvanceGenerationDelegate _advanceGeneration;
    private readonly EvaluateNavigationDelegate _evaluateNavigation;
    private readonly RequestNavigationConfirmationDelegate _requestNavigationConfirmation;
    private readonly ApproveNavigationConfirmationDelegate _approveNavigationConfirmation;
    private readonly RejectNavigationConfirmationDelegate _rejectNavigationConfirmation;
    private readonly ConsumeNavigationDelegate _consumeNavigation;
    private bool _disposed;

    /// <summary>审计第七轮（2026-10-03·latent）：**不得**再直接
    /// DangerousGetHandle 透传指针——此前 `Broker => _brokerHandle.DangerousGetHandle()`
    /// 绕过引用计数，取指针与调用之间可被 Dispose/终结器释放（use-after-free 进
    /// DLL 蹦床）。全部原生调用改走 TryAcquireLease/ReleaseLease（AddRef/Release
    /// 成对），并在入口检 _disposed。仅在持有租约期间调用本属性。</summary>
    private IntPtr Broker => _brokerHandle.DangerousGetHandle();

    /// <summary>取得 broker 使用期引用（DangerousAddRef）。返回 false 即不得调用
    /// 任何原生入口（已 Dispose/句柄失效）——fail-closed。
    /// R7-CS1-04/15：入口判 IsUsable（此前该属性全仓零引用＝伪装成守卫的死代码，
    /// 而八个原生入口又不检 _disposed 直取指针，实测原生模式下测试主机
    /// 0xC0000005 use-after-free）。</summary>
    private bool TryAcquireLease()
    {
        if (!IsUsable)
            return false;
        try
        {
            var success = false;
            _brokerHandle.DangerousAddRef(ref success);
            return success;
        }
        catch (Exception)
        {
            // 句柄已释放/关闭（Dispose 或终结器先行）——不猜测引用计数，直接拒绝
            return false;
        }
    }

    private void ReleaseLease()
    {
        try
        {
            _brokerHandle.DangerousRelease();
        }
        catch (Exception)
        {
            // 引用已随 Dispose 归零——不存在可撤销的原生副作用
        }
    }

    /// <summary>R7-CS1-15（第七轮·原生模式下实测 0xC0000005）：唯一的原生调用出口。
    /// 先取得引用计数租约（Dispose/终结竞争下句柄不得在调用期间被释放），再在租约
    /// 内取 broker 指针。取不到租约一律返回 whenUnavailable（bool → false，
    /// Decision → Deny）——"猜测句柄仍然有效"正是越界访问的入口。</summary>
    private T InvokeLeased<T>(Func<IntPtr, T> operation, T whenUnavailable)
    {
        if (!TryAcquireLease())
            return whenUnavailable;
        try
        {
            return operation(Broker);
        }
        finally
        {
            ReleaseLease();
        }
    }

    /// <summary>决策类入口在租约不可得时的拒绝（与协议异常分码，便于归因）。</summary>
    private static Decision DisposedDeny(string detail) =>
        Deny("native_policy_core_disposed", detail);

    /// <summary>审计第七轮（2026-10-03）：原生调用统一守卫——
    /// Dispose/终结之后一律 fail-closed（此前 CreateSession/EvaluateNavigation/
    /// TryConsumeNavigation 等全部入口不检 _disposed，释放后仍可进 DLL）。</summary>
    private bool IsUsable => !_disposed && !_brokerHandle.IsClosed && !_brokerHandle.IsInvalid;

    private NativePolicyCoreBridge(
        IntPtr library,
        IntPtr broker,
        BrokerFreeDelegate brokerFree,
        StringFreeDelegate stringFree,
        CreateSessionDelegate createSession,
        DestroySessionDelegate destroySession,
        AdvanceGenerationDelegate advanceGeneration,
        EvaluateNavigationDelegate evaluateNavigation,
        RequestNavigationConfirmationDelegate requestNavigationConfirmation,
        ApproveNavigationConfirmationDelegate approveNavigationConfirmation,
        RejectNavigationConfirmationDelegate rejectNavigationConfirmation,
        ConsumeNavigationDelegate consumeNavigation)
    {
        _library = new NativeLibraryHandle(library);
        _brokerHandle = new NativeBrokerHandle(broker, brokerFree);
        _brokerFree = brokerFree;
        _stringFree = stringFree;
        _createSession = createSession;
        _destroySession = destroySession;
        _advanceGeneration = advanceGeneration;
        _evaluateNavigation = evaluateNavigation;
        _requestNavigationConfirmation = requestNavigationConfirmation;
        _approveNavigationConfirmation = approveNavigationConfirmation;
        _rejectNavigationConfirmation = rejectNavigationConfirmation;
        _consumeNavigation = consumeNavigation;
    }

    public static bool TryCreate(string policyVersion, string? libraryPath, out NativePolicyCoreBridge? bridge)
    {
        bridge = null;
        if (string.IsNullOrWhiteSpace(policyVersion)
            || !NativeLibrary.TryLoad(libraryPath ?? "aegis_policy_core", out var libraryPointer))
            return false;

        var library = new NativeLibraryHandle(libraryPointer);
        try
        {
            var abiVersion = GetDelegate<AbiVersionDelegate>(library.DangerousGetHandle(), "aegis_policy_core_abi_version")();
            if (abiVersion != ExpectedAbiVersion)
                return false;  // 失败路径由 finally 统一释放

            var brokerNew = GetDelegate<BrokerNewDelegate>(library.DangerousGetHandle(), "aegis_policy_core_broker_new");
            var brokerFree = GetDelegate<BrokerFreeDelegate>(library.DangerousGetHandle(), "aegis_policy_core_broker_free");
            var stringFree = GetDelegate<StringFreeDelegate>(library.DangerousGetHandle(), "aegis_policy_core_string_free");
            var createSession = GetDelegate<CreateSessionDelegate>(library.DangerousGetHandle(), "aegis_policy_core_broker_create_session");
            var destroySession = GetDelegate<DestroySessionDelegate>(library.DangerousGetHandle(), "aegis_policy_core_broker_destroy_session");
            var advanceGeneration = GetDelegate<AdvanceGenerationDelegate>(library.DangerousGetHandle(), "aegis_policy_core_broker_advance_document_generation");
            var evaluateNavigation = GetDelegate<EvaluateNavigationDelegate>(library.DangerousGetHandle(), "aegis_policy_core_broker_evaluate_navigation_json");
            var requestNavigationConfirmation = GetDelegate<RequestNavigationConfirmationDelegate>(library.DangerousGetHandle(), "aegis_policy_core_broker_request_navigation_confirmation_json");
            var approveNavigationConfirmation = GetDelegate<ApproveNavigationConfirmationDelegate>(library.DangerousGetHandle(), "aegis_policy_core_broker_approve_navigation_confirmation_json");
            var rejectNavigationConfirmation = GetDelegate<RejectNavigationConfirmationDelegate>(library.DangerousGetHandle(), "aegis_policy_core_broker_reject_navigation_confirmation");
            var consumeNavigation = GetDelegate<ConsumeNavigationDelegate>(library.DangerousGetHandle(), "aegis_policy_core_broker_consume_navigation_json");
            var versionPointer = Utf8(policyVersion);
            try
            {
                var broker = brokerNew(versionPointer);
                if (broker == IntPtr.Zero)
                    return false;  // 失败路径由 finally 统一释放
                bridge = new NativePolicyCoreBridge(
                    libraryPointer,
                    broker,
                    brokerFree,
                    stringFree,
                    createSession,
                    destroySession,
                    advanceGeneration,
                    evaluateNavigation,
                    requestNavigationConfirmation,
                    approveNavigationConfirmation,
                    rejectNavigationConfirmation,
                    consumeNavigation);
                return true;
            }
            finally
            {
                Marshal.FreeCoTaskMem(versionPointer);
            }
        }
        catch (Exception)
        {
            return false;  // 失败路径由 finally 统一释放
        }
        finally
        {
            // 成功时句柄所有权已移交 bridge 实例——仅失败路径在此释放
            if (bridge is null)
                library.Dispose();
        }
    }

    public bool CreateSession(string sessionId, string tabId, ulong generation, ulong ttlSeconds) =>
        InvokeLeased(broker => InvokeTwoStrings(sessionId, tabId, (session, tab) =>
            _createSession(broker, session, tab, generation, ttlSeconds) == 1), false);

    public bool DestroySession(string sessionId) =>
        InvokeLeased(broker => InvokeOneString(sessionId, session =>
            _destroySession(broker, session) == 1), false);

    public bool AdvanceDocumentGeneration(string sessionId, string tabId, ulong nextGeneration) =>
        InvokeLeased(broker => InvokeTwoStrings(sessionId, tabId, (session, tab) =>
            _advanceGeneration(broker, session, tab, nextGeneration) == 1), false);

    public Decision EvaluateNavigation(string sessionId, string tabId, ulong generation, string rawUrl, string scope)
    {
        try
        {
            return InvokeLeased(broker => InvokeFourStrings(sessionId, tabId, rawUrl, scope,
                (session, tab, url, requestedScope) =>
                    ParseDecision(_evaluateNavigation(broker, session, tab, generation, url, requestedScope))),
                DisposedDeny("原生策略核心桥已释放，拒绝跨界导航裁决"));
        }
        catch (Exception)
        {
            return Deny("native_policy_core_protocol", "原生策略核心响应无效或不可读取");
        }
    }

    /// <summary>登记由策略核心保留的确认型导航；返回值绝不包含可立即消费的授权。</summary>
    public Decision RequestNavigationConfirmation(string sessionId, string tabId, ulong generation, string rawUrl, string scope)
    {
        try
        {
            return InvokeLeased(broker => InvokeFourStrings(sessionId, tabId, rawUrl, scope,
                (session, tab, url, requestedScope) =>
                    ParseDecision(_requestNavigationConfirmation(broker, session, tab, generation, url, requestedScope))),
                DisposedDeny("原生策略核心桥已释放，拒绝登记确认请求"));
        }
        catch (Exception)
        {
            return Deny("native_policy_core_protocol", "原生策略核心确认请求无效或不可读取");
        }
    }

    /// <summary>仅按原生核心登记的 nonce 显式批准，并由核心返回原始绑定授权。</summary>
    public Decision ApproveNavigationConfirmation(ApprovalRequest request, string rawUrl, string scope)
    {
        try
        {
            return InvokeLeased(broker => InvokeThreeStrings(request.Nonce, rawUrl, scope,
                (nonce, url, requestedScope) =>
                    ParseDecision(_approveNavigationConfirmation(broker, nonce, url, requestedScope))),
                DisposedDeny("原生策略核心桥已释放，拒绝兑换确认授权"));
        }
        catch (Exception)
        {
            return Deny("native_policy_core_protocol", "原生策略核心确认批准响应无效或不可读取");
        }
    }

    /// <summary>显式拒绝待审批导航；异常、未知 nonce 或桥已释放均返回 false。</summary>
    public bool RejectNavigationConfirmation(ApprovalRequest request)
    {
        try
        {
            return InvokeLeased(broker => InvokeOneString(request.Nonce,
                nonce => _rejectNavigationConfirmation(broker, nonce) == 1), false);
        }
        catch (Exception)
        {
            return false;
        }
    }

    public bool TryConsumeNavigation(AuthorizedAction action, string rawUrl, string scope)
    {
        try
        {
            var actionJson = JsonSerializer.Serialize(new NativeAction(
                action.SessionId,
                action.TabId,
                action.DocumentGeneration,
                action.Origin,
                action.Method,
                action.CanonicalParameters,
                action.Scope,
                new DateTimeOffset(action.ExpiresAt).ToUnixTimeSeconds(),
                action.Nonce,
                action.PolicyVersion));
            return InvokeLeased(broker => InvokeThreeStrings(actionJson, rawUrl, scope,
                (serializedAction, url, requestedScope) =>
                    ParseDecision(_consumeNavigation(broker, serializedAction, url, requestedScope)) is Decision.Allow),
                false);
        }
        catch (Exception)
        {
            return false;
        }
    }

    public void Dispose()
    {
        if (_disposed)
            return;
        _disposed = true;
        _brokerHandle.Dispose();
        _library.Dispose();
        GC.SuppressFinalize(this);
    }

    private Decision ParseDecision(IntPtr response)
    {
        if (response == IntPtr.Zero)
            throw new InvalidOperationException("native response pointer is null");
        try
        {
            var payload = Marshal.PtrToStringUTF8(response)
                ?? throw new InvalidOperationException("native response was not UTF-8");
            return ParseDecisionPayload(payload);
        }
        finally
        {
            _stringFree(response);
        }
    }

    /// <summary>解析 Rust C ABI JSON；未知决策保留为拒绝，避免协议升级时意外放行。</summary>
    internal static Decision ParseDecisionPayload(string payload)
    {
        using var document = JsonDocument.Parse(payload);
        var root = document.RootElement;
        if (root.GetProperty("abi_version").GetUInt32() != ExpectedAbiVersion)
            throw new InvalidOperationException("native response ABI mismatch");
        return root.GetProperty("decision").GetString() switch
        {
            "allow" => new Decision.Allow(ParseAction(root.GetProperty("action"))),
            "require_confirmation" => new Decision.RequireConfirmation(ParseApprovalRequest(root.GetProperty("request"))),
            "deny" => new Decision.Deny(ParseDeny(root.GetProperty("reason"))),
            _ => Deny("native_policy_core_decision_invalid", "原生策略核心返回了未支持的决策"),
        };
    }

    private static AuthorizedAction ParseAction(JsonElement action)
    {
        var expiresAt = DateTimeOffset.FromUnixTimeSeconds(action.GetProperty("expires_at").GetInt64()).UtcDateTime;
        return new AuthorizedAction(
            action.GetProperty("session_id").GetString() ?? throw new InvalidOperationException(),
            action.GetProperty("tab_id").GetString() ?? throw new InvalidOperationException(),
            action.GetProperty("document_generation").GetUInt64(),
            action.GetProperty("origin").GetString() ?? throw new InvalidOperationException(),
            action.GetProperty("method").GetString() ?? throw new InvalidOperationException(),
            action.GetProperty("canonical_parameters").GetString() ?? throw new InvalidOperationException(),
            action.GetProperty("scope").GetString() ?? throw new InvalidOperationException(),
            expiresAt,
            action.GetProperty("nonce").GetString() ?? throw new InvalidOperationException(),
            action.GetProperty("policy_version").GetString() ?? throw new InvalidOperationException());
    }

    private static ApprovalRequest ParseApprovalRequest(JsonElement request) => new(
        request.GetProperty("origin").GetString() ?? throw new InvalidOperationException(),
        request.GetProperty("method").GetString() ?? throw new InvalidOperationException(),
        request.GetProperty("path").GetString() ?? throw new InvalidOperationException(),
        request.GetProperty("scope").GetString() ?? throw new InvalidOperationException(),
        DateTimeOffset.FromUnixTimeSeconds(request.GetProperty("expires_at").GetInt64()).UtcDateTime,
        request.GetProperty("nonce").GetString() ?? throw new InvalidOperationException());

    private static DenyReason ParseDeny(JsonElement reason) => new(
        reason.GetProperty("code").GetString() ?? "native_policy_core_denied",
        reason.GetProperty("detail").GetString() ?? "原生策略核心拒绝请求");

    private static Decision.Deny Deny(string code, string detail) => new(new DenyReason(code, detail));

    private static TDelegate GetDelegate<TDelegate>(IntPtr library, string export) where TDelegate : Delegate
    {
        if (!NativeLibrary.TryGetExport(library, export, out var pointer))
            throw new EntryPointNotFoundException(export);
        return Marshal.GetDelegateForFunctionPointer<TDelegate>(pointer);
    }

    private static IntPtr Utf8(string value) => Marshal.StringToCoTaskMemUTF8(value);

    private static bool InvokeOneString(string first, Func<IntPtr, bool> operation)
    {
        var firstPointer = Utf8(first);
        try { return operation(firstPointer); }
        finally { Marshal.FreeCoTaskMem(firstPointer); }
    }

    // CS-206：逐个分配嵌套 try/finally——第二个及后续 Utf8 分配若抛
    // （OOM），此前已分配的指针泄漏
    private static bool InvokeTwoStrings(string first, string second, Func<IntPtr, IntPtr, bool> operation)
    {
        var firstPointer = Utf8(first);
        try
        {
            var secondPointer = Utf8(second);
            try { return operation(firstPointer, secondPointer); }
            finally { Marshal.FreeCoTaskMem(secondPointer); }
        }
        finally { Marshal.FreeCoTaskMem(firstPointer); }
    }

    private static T InvokeThreeStrings<T>(string first, string second, string third, Func<IntPtr, IntPtr, IntPtr, T> operation)
    {
        var firstPointer = Utf8(first);
        try
        {
            var secondPointer = Utf8(second);
            try
            {
                var thirdPointer = Utf8(third);
                try { return operation(firstPointer, secondPointer, thirdPointer); }
                finally { Marshal.FreeCoTaskMem(thirdPointer); }
            }
            finally { Marshal.FreeCoTaskMem(secondPointer); }
        }
        finally { Marshal.FreeCoTaskMem(firstPointer); }
    }

    private static T InvokeFourStrings<T>(
        string first,
        string second,
        string third,
        string fourth,
        Func<IntPtr, IntPtr, IntPtr, IntPtr, T> operation)
    {
        var firstPointer = Utf8(first);
        try
        {
            var secondPointer = Utf8(second);
            try
            {
                var thirdPointer = Utf8(third);
                try
                {
                    var fourthPointer = Utf8(fourth);
                    try { return operation(firstPointer, secondPointer, thirdPointer, fourthPointer); }
                    finally { Marshal.FreeCoTaskMem(fourthPointer); }
                }
                finally { Marshal.FreeCoTaskMem(thirdPointer); }
            }
            finally { Marshal.FreeCoTaskMem(secondPointer); }
        }
        finally { Marshal.FreeCoTaskMem(firstPointer); }
    }
}

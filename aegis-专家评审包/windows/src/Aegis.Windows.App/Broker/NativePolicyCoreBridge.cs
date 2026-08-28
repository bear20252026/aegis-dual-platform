namespace Aegis.Windows.Broker;

using System;
using System.Runtime.InteropServices;
using System.Text.Json;

/// <summary>
/// 受控 Rust 策略核心桥接。它只使用明确的 C ABI 导出和 UTF-8 JSON，不向托管端暴露 Rust 内存布局。
/// 所有加载、解析或 ABI 异常均被调用方转换为拒绝，禁止退回到另一套策略实现。
/// </summary>
public sealed class NativePolicyCoreBridge : IDisposable
{
    private const uint ExpectedAbiVersion = NativePolicyCoreGate.ExpectedAbiVersion;
    private readonly IntPtr _library;
    private readonly IntPtr _broker;
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
        _library = library;
        _broker = broker;
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
            || !NativeLibrary.TryLoad(libraryPath ?? "aegis_policy_core", out var library))
            return false;

        try
        {
            var abiVersion = GetDelegate<AbiVersionDelegate>(library, "aegis_policy_core_abi_version")();
            if (abiVersion != ExpectedAbiVersion)
            {
                NativeLibrary.Free(library);
                return false;
            }

            var brokerNew = GetDelegate<BrokerNewDelegate>(library, "aegis_policy_core_broker_new");
            var brokerFree = GetDelegate<BrokerFreeDelegate>(library, "aegis_policy_core_broker_free");
            var stringFree = GetDelegate<StringFreeDelegate>(library, "aegis_policy_core_string_free");
            var createSession = GetDelegate<CreateSessionDelegate>(library, "aegis_policy_core_broker_create_session");
            var destroySession = GetDelegate<DestroySessionDelegate>(library, "aegis_policy_core_broker_destroy_session");
            var advanceGeneration = GetDelegate<AdvanceGenerationDelegate>(library, "aegis_policy_core_broker_advance_document_generation");
            var evaluateNavigation = GetDelegate<EvaluateNavigationDelegate>(library, "aegis_policy_core_broker_evaluate_navigation_json");
            var requestNavigationConfirmation = GetDelegate<RequestNavigationConfirmationDelegate>(library, "aegis_policy_core_broker_request_navigation_confirmation_json");
            var approveNavigationConfirmation = GetDelegate<ApproveNavigationConfirmationDelegate>(library, "aegis_policy_core_broker_approve_navigation_confirmation_json");
            var rejectNavigationConfirmation = GetDelegate<RejectNavigationConfirmationDelegate>(library, "aegis_policy_core_broker_reject_navigation_confirmation");
            var consumeNavigation = GetDelegate<ConsumeNavigationDelegate>(library, "aegis_policy_core_broker_consume_navigation_json");
            var versionPointer = Utf8(policyVersion);
            try
            {
                var broker = brokerNew(versionPointer);
                if (broker == IntPtr.Zero)
                {
                    NativeLibrary.Free(library);
                    return false;
                }
                bridge = new NativePolicyCoreBridge(
                    library,
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
            NativeLibrary.Free(library);
            return false;
        }
    }

    public bool CreateSession(string sessionId, string tabId, ulong generation, ulong ttlSeconds) =>
        InvokeTwoStrings(sessionId, tabId, (session, tab) =>
            _createSession(_broker, session, tab, generation, ttlSeconds) == 1);

    public bool DestroySession(string sessionId) =>
        InvokeOneString(sessionId, session => _destroySession(_broker, session) == 1);

    public bool AdvanceDocumentGeneration(string sessionId, string tabId, ulong nextGeneration) =>
        InvokeTwoStrings(sessionId, tabId, (session, tab) =>
            _advanceGeneration(_broker, session, tab, nextGeneration) == 1);

    public Decision EvaluateNavigation(string sessionId, string tabId, ulong generation, string rawUrl, string scope)
    {
        try
        {
            return InvokeFourStrings(sessionId, tabId, rawUrl, scope, (session, tab, url, requestedScope) =>
                ParseDecision(_evaluateNavigation(_broker, session, tab, generation, url, requestedScope)));
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
            return InvokeFourStrings(sessionId, tabId, rawUrl, scope, (session, tab, url, requestedScope) =>
                ParseDecision(_requestNavigationConfirmation(_broker, session, tab, generation, url, requestedScope)));
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
            return InvokeThreeStrings(request.Nonce, rawUrl, scope, (nonce, url, requestedScope) =>
                ParseDecision(_approveNavigationConfirmation(_broker, nonce, url, requestedScope)));
        }
        catch (Exception)
        {
            return Deny("native_policy_core_protocol", "原生策略核心确认批准响应无效或不可读取");
        }
    }

    /// <summary>显式拒绝待审批导航；异常或未知 nonce 均返回 false。</summary>
    public bool RejectNavigationConfirmation(ApprovalRequest request)
    {
        try
        {
            return InvokeOneString(request.Nonce, nonce => _rejectNavigationConfirmation(_broker, nonce) == 1);
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
            return InvokeThreeStrings(actionJson, rawUrl, scope, (serializedAction, url, requestedScope) =>
                ParseDecision(_consumeNavigation(_broker, serializedAction, url, requestedScope)) is Decision.Allow);
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
        _brokerFree(_broker);
        NativeLibrary.Free(_library);
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

    private static bool InvokeTwoStrings(string first, string second, Func<IntPtr, IntPtr, bool> operation)
    {
        var firstPointer = Utf8(first);
        var secondPointer = Utf8(second);
        try { return operation(firstPointer, secondPointer); }
        finally
        {
            Marshal.FreeCoTaskMem(firstPointer);
            Marshal.FreeCoTaskMem(secondPointer);
        }
    }

    private static T InvokeThreeStrings<T>(string first, string second, string third, Func<IntPtr, IntPtr, IntPtr, T> operation)
    {
        var firstPointer = Utf8(first);
        var secondPointer = Utf8(second);
        var thirdPointer = Utf8(third);
        try { return operation(firstPointer, secondPointer, thirdPointer); }
        finally
        {
            Marshal.FreeCoTaskMem(firstPointer);
            Marshal.FreeCoTaskMem(secondPointer);
            Marshal.FreeCoTaskMem(thirdPointer);
        }
    }

    private static T InvokeFourStrings<T>(
        string first,
        string second,
        string third,
        string fourth,
        Func<IntPtr, IntPtr, IntPtr, IntPtr, T> operation)
    {
        var firstPointer = Utf8(first);
        var secondPointer = Utf8(second);
        var thirdPointer = Utf8(third);
        var fourthPointer = Utf8(fourth);
        try { return operation(firstPointer, secondPointer, thirdPointer, fourthPointer); }
        finally
        {
            Marshal.FreeCoTaskMem(firstPointer);
            Marshal.FreeCoTaskMem(secondPointer);
            Marshal.FreeCoTaskMem(thirdPointer);
            Marshal.FreeCoTaskMem(fourthPointer);
        }
    }

    private sealed record NativeAction(
        [property: System.Text.Json.Serialization.JsonPropertyName("session_id")] string SessionId,
        [property: System.Text.Json.Serialization.JsonPropertyName("tab_id")] string TabId,
        [property: System.Text.Json.Serialization.JsonPropertyName("document_generation")] ulong DocumentGeneration,
        [property: System.Text.Json.Serialization.JsonPropertyName("origin")] string Origin,
        [property: System.Text.Json.Serialization.JsonPropertyName("method")] string Method,
        [property: System.Text.Json.Serialization.JsonPropertyName("canonical_parameters")] string CanonicalParameters,
        [property: System.Text.Json.Serialization.JsonPropertyName("scope")] string Scope,
        [property: System.Text.Json.Serialization.JsonPropertyName("expires_at")] long ExpiresAt,
        [property: System.Text.Json.Serialization.JsonPropertyName("nonce")] string Nonce,
        [property: System.Text.Json.Serialization.JsonPropertyName("policy_version")] string PolicyVersion);

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

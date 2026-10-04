namespace Aegis.Windows.Broker;

using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;
using System.Text.Json;

/// <summary>
/// 审计第六轮遗留缺口收口（2026-10-04）：威胁 host 黑名单注入的 C ABI 绑定
/// （<c>aegis_policy_core_broker_update_host_denylist_json</c>）。
/// 拆成 partial 文件与 <c>MainWindow.*.cs</c> 同法（行数红线只许减不许增）。
/// 兼容性硬约束：核心侧新增本入口时 **没有** 递增 ABI 版本（仍为 v3），
/// 所以 abi_version 探测无法区分"有该导出"与"没有该导出的旧 DLL"——本绑定
/// 按可选导出惰性解析（TryGetExport 同口径）。符号缺席即降级为
/// "核心黑名单未发布"（调用方留痕），不抛异常、不影响任何导航决策，
/// 已装应用对着旧 DLL 运行不得因此变砖。
/// 生命周期口径沿用 CS-207/R6：原生入口只在持有 broker 租约期间调用；
/// 解析导出时另取库句柄租约（DangerousAddRef/Release 成对），入口检 _disposed。
/// </summary>
public sealed partial class NativePolicyCoreBridge
{
    private const string HostDenylistExport = "aegis_policy_core_broker_update_host_denylist_json";

    // 可选导出的惰性解析缓存：一个桥实例对应一个已加载模块，导出表不会热换，
    // 故探测一次即定终身（缺席就恒缺席，无需每轮刷新重探）。
    private readonly object _hostDenylistLock = new();
    private UpdateHostDenylistDelegate? _hostDenylistEntry;
    private bool _hostDenylistProbed;

    /// <summary>把威胁 host 快照注入原生核心黑名单（整批替换语义——空集合即清空，
    /// 核心侧未设置时恒放行，绝不默认 deny-all）。任何失败都以
    /// <see cref="CoreDenylistUpdateResult.Outcome"/> 如实回报，
    /// 调用方**不得**把失败当成"黑名单已生效"。</summary>
    public CoreDenylistUpdateResult UpdateHostDenylist(IReadOnlyCollection<string> hosts)
    {
        var input = hosts.Count;
        // 租约先行：持有期间 Dispose 无法释放 broker，也就无法释放库句柄
        //（Dispose 先 broker 后 library）——解析与调用共用同一不变式
        if (!TryAcquireLease())
            return CoreDenylistUpdateResult.NotPublished(input, "bridge_disposed");
        try
        {
            var entry = ResolveHostDenylistEntry();
            return entry is null
                ? CoreDenylistUpdateResult.MissingExport(input)
                : InvokeHostDenylist(entry, hosts, input);
        }
        catch (Exception)
        {
            // 与既有原生入口同口径：编组/解析异常一律收敛为"未发布"，绝不外逃
            //（黑名单发布是增强面，不得成为导航链的新失败面）
            return CoreDenylistUpdateResult.NotPublished(input, "native_policy_core_protocol");
        }
        finally
        {
            ReleaseLease();
        }
    }

    private UpdateHostDenylistDelegate? ResolveHostDenylistEntry()
    {
        lock (_hostDenylistLock)
        {
            if (!_hostDenylistProbed)
            {
                _hostDenylistProbed = true;
                _hostDenylistEntry = LoadHostDenylistEntry();
            }
            return _hostDenylistEntry;
        }
    }

    /// <summary>可选导出解析——失败态（句柄不可用/符号缺席）一律返回 null，
    /// 不抛 EntryPointNotFoundException（那是 <see cref="GetDelegate"/> 的必需导出语义）。</summary>
    private UpdateHostDenylistDelegate? LoadHostDenylistEntry()
    {
        if (_disposed || _library.IsClosed || _library.IsInvalid)
            return null;  // R6 生命周期守卫：不取已释放句柄
        var held = false;
        try
        {
            _library.DangerousAddRef(ref held);
            if (!held)
                return null;
            return NativeLibrary.TryGetExport(_library.DangerousGetHandle(), HostDenylistExport, out var pointer)
                ? Marshal.GetDelegateForFunctionPointer<UpdateHostDenylistDelegate>(pointer)
                : null;  // 旧版 DLL：符号缺席是既定兼容态，不是错误
        }
        catch (Exception)
        {
            return null;
        }
        finally
        {
            if (held)
                _library.DangerousRelease();
        }
    }

    private CoreDenylistUpdateResult InvokeHostDenylist(
        UpdateHostDenylistDelegate entry,
        IReadOnlyCollection<string> hosts,
        int input)
    {
        // 入参形态是 JSON 字符串数组（核心侧 serde 反序列化为 Vec<String>）；
        // host 已由 BlockedHosts 归一（小写、去尾点），此处不再加工。
        var payload = JsonSerializer.Serialize(new List<string>(hosts));
        var hostsPointer = Utf8(payload);
        IntPtr response;
        try
        {
            response = entry(Broker, hostsPointer);
        }
        finally
        {
            Marshal.FreeCoTaskMem(hostsPointer);
        }
        if (response == IntPtr.Zero)
            return CoreDenylistUpdateResult.NotPublished(input, "native_response_pointer_null");
        try
        {
            var text = Marshal.PtrToStringUTF8(response);
            return text is null
                ? CoreDenylistUpdateResult.NotPublished(input, "native_response_not_utf8")
                : ParseUpdateResponse(text, input);
        }
        finally
        {
            _stringFree(response);
        }
    }

    /// <summary>解析注入应答 <c>{"decision":"ok","accepted":N,"input":M}</c>。
    /// 注意该信封不带 abi_version（与决策信封不同），故不能复用
    /// <see cref="ParseDecisionPayload"/>。非 ok 应答（含核心侧分配失败的
    /// FALLBACK deny 信封）一律如实回报未发布并带出 reason.code；
    /// accepted &lt; input 原样保留给调用方留痕——被拒条目在核心侧是
    /// "看起来在工作的黑名单里的永久死条目"，静默吞掉正是本缺口藏五轮的原因。</summary>
    internal static CoreDenylistUpdateResult ParseUpdateResponse(string payload, int input)
    {
        try
        {
            using var document = JsonDocument.Parse(payload);
            var root = document.RootElement;
            var decision = root.TryGetProperty("decision", out var value) ? value.GetString() : null;
            if (decision != "ok")
                return CoreDenylistUpdateResult.NotPublished(
                    input,
                    root.TryGetProperty("reason", out var reason) &&
                    reason.TryGetProperty("code", out var code)
                        ? code.GetString() ?? "native_denylist_denied"
                        : "native_denylist_response_not_ok");
            var accepted = ReadCount(root, "accepted");
            // 核心如实回报 input；应答缺失时退回本地 offered 数（不虚报成功）
            var offered = root.TryGetProperty("input", out _) ? ReadCount(root, "input") : input;
            return CoreDenylistUpdateResult.Apply(accepted, offered);
        }
        catch (Exception)
        {
            return CoreDenylistUpdateResult.NotPublished(input, "native_denylist_response_unparsable");
        }
    }

    private static int ReadCount(JsonElement root, string name) =>
        root.TryGetProperty(name, out var value) && value.TryGetInt32(out var number) && number >= 0
            ? number
            : 0;

    [UnmanagedFunctionPointer(CallingConvention.Cdecl)]
    private delegate IntPtr UpdateHostDenylistDelegate(IntPtr broker, IntPtr hostsJson);
}

/// <summary>原生核心黑名单注入结果。<see cref="CoreDenylistPublisher"/> 据此
/// 落可观测日志；<see cref="ExportMissing"/> 与 <see cref="NotPublished"/> 都表示
/// "核心侧本轮没有生效"，区别只在是否可归因于旧版 DLL（前者只留痕一次）。</summary>
public enum CoreDenylistOutcome
{
    /// <summary>核心已接受整批快照（accepted == input）。</summary>
    Published,

    /// <summary>核心已接受，但有条目被拒（accepted &lt; input）——必须显式观测。</summary>
    PartiallyPublished,

    /// <summary>已加载的核心 DLL 未导出注入入口（旧版核心）——降级，不是错误。</summary>
    ExportMissing,

    /// <summary>桥不可用/应答异常/核心拒绝——本轮未发布。</summary>
    NotPublished,
}

/// <summary>注入结果快照（不含 host 内容与任何本机路径——可安全落日志）。</summary>
public sealed record CoreDenylistUpdateResult(
    CoreDenylistOutcome Outcome,
    int Accepted,
    int Input,
    string Detail)
{
    /// <summary>核心侧是否真的拿到了这一批条目。</summary>
    public bool Published => Outcome is CoreDenylistOutcome.Published or CoreDenylistOutcome.PartiallyPublished;

    /// <summary>被核心形态校验/去重拒收的条目数（托管侧仍拦，核心侧永不命中）。</summary>
    public int RejectedEntryCount => Published ? Math.Max(Input - Accepted, 0) : Input;

    internal static CoreDenylistUpdateResult Apply(int accepted, int input) => new(
        accepted < input ? CoreDenylistOutcome.PartiallyPublished : CoreDenylistOutcome.Published,
        accepted,
        input,
        accepted < input ? "partial_accept" : "ok");

    internal static CoreDenylistUpdateResult MissingExport(int input) =>
        new(CoreDenylistOutcome.ExportMissing, 0, input, "denylist_export_missing");

    internal static CoreDenylistUpdateResult NotPublished(int input, string detail) =>
        new(CoreDenylistOutcome.NotPublished, 0, input, detail);
}

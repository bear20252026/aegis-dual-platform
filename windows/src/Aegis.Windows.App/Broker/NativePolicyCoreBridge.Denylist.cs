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
/// 审计第七轮 R7-RS-02（2026-10-04）：本入口新增第三个参数 <c>clear</c>
/// （0=追加，非0=先清空再接受本批）。核心侧的 64KiB 单载荷上限
///（<c>FFI_INPUT_MAX_BYTES</c>）遇上托管侧允许的 5 MiB 订阅源，整批替换
/// 必然注入失败——故本类现按上限切批推送（首批 clear=1，其余 clear=0）。
/// 参数是就地加的（符号名未变、ABI 版本仍为 v3），因此符号名探测区分不了
/// "2 参旧核心"与"3 参新核心"：对着 2 参旧核心调用时多传的实参被忽略，
/// 行为退化为既往的整批替换（内存安全，x64 cdecl 下多余参数不被解引用），
/// 但分批会各自整批替换 → 最终快照只剩最后一批（⑨ 已由「暂存 + 提交」消除，见
/// 回显是本类唯一的"核心是否真带该参数"探针（信封不含 abi_version）：多批
/// 推送时首批不回显即中止并记 <c>core_lacks_clear_parameter</c>，核心侧留下的
/// 前缀规模如实写进 Detail——绝不静默推完 86 批换回一个残缺名单。单批推送
/// 无需该判据（clear=1 与旧核心的整批替换同义，行为与既往一致）。
/// 应用与核心 DLL 由同一构建产出、同一安装器投递，混版态属增量替换事故面。
/// </summary>
public sealed partial class NativePolicyCoreBridge
{
    private const string HostDenylistExport = "aegis_policy_core_broker_update_host_denylist_json";

    /// <summary>单批载荷字节上限：核心 <c>read_utf8</c> 在 64KiB 处拒批
    ///（<c>core/rust-policy-core/src/c_abi/mod.rs</c> 的 FFI_INPUT_MAX_BYTES）。
    /// 留 ~4KiB 余量给数组括号与逐批计费的序列化误差——宁可多切一刀，
    /// 也不能让任何一批撞上上限（撞上的那一批是被拒、不是被截断）。</summary>
    private const int MaxChunkPayloadBytes = 60 * 1024;

    // 可选导出的惰性解析缓存：一个桥实例对应一个已加载模块，导出表不会热换，
    // 故探测一次即定终身（缺席就恒缺席，无需每轮刷新重探）。
    private readonly object _hostDenylistLock = new();
    private UpdateHostDenylistDelegate? _hostDenylistEntry;
    private bool _hostDenylistProbed;

    /// <summary>把威胁 host 快照注入原生核心黑名单。空集合即清空，
    /// 核心侧未设置时恒放行，绝不默认 deny-all。快照超过单载荷上限时
    /// 按 <see cref="MaxChunkPayloadBytes"/> 分批（首批清空、其余追加），
    /// 因此不再是"整批替换一次成功/一次失败"。任何失败都以
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
                : PushInChunks(entry, hosts, input);
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

    /// <summary>清空/追加两阶段分块推送（R7-RS-02）。首批 <c>clear=true</c> 建立快照、
    /// 其余 <c>clear=false</c> 追加。两种中止条件：某一批被核心整体拒收（非形态拒收），
    /// 或多批场景下首批应答不带 <c>clear</c> 回显——符号名区分不了 2 参与 3 参核心，
    /// 回显是唯一探针；缺回显还继续推，每批都会整批抹掉前一批，最终快照只剩最后一批
    ///（又一个"看起来在工作"的残缺名单，正是本条要修的形态）。单批推送不需该判据：
    /// clear=1 与旧核心的整批替换同义，行为与既往一致。中止时核心侧留下的是**已推送
    /// 前缀**而非上一份快照（首批即带清空），故 Detail 如实带出前缀规模与停在哪一批，
    /// 绝不写成"完好无损"。形态拒收（accepted &lt; input）不中止：托管侧仍在拦那些
    /// 条目，与既往单批口径一致，汇总后以 PartiallyPublished 呈现。</summary>
    // ⑨（第八轮 R8-RS-14）：档位协议（暂存 + 提交，混版三态）在
    // NativePolicyCoreBridge.DenylistPush.cs——那里是纯逻辑，可在无原生 DLL 的
    // 常跑门禁里直测；本类只负责编组与租约。
    private CoreDenylistUpdateResult PushInChunks(
        UpdateHostDenylistDelegate entry, IReadOnlyCollection<string> hosts, int input)
    {
        var batches = EnumerateBatches(hosts);
        return DriveDenylistPush(
            batches,
            (batch, mode) => InvokeHostDenylist(entry, batch, mode),
            input);
    }

    /// <summary>按核心单载荷上限切批（逐元素 UTF-8 字节计费，+1 为元素间逗号）。
    /// 空快照也必须产出一个空批——"清空核心名单"正是靠 clear=true 的空批表达，
    /// 不推空批就会让已撤销的条目在核心侧残留。internal 同 ParseUpdateResponse：
    /// 纯函数可直接钉（NativeDenylistChunkingTests），不扩公开 API。</summary>
    internal static List<List<string>> EnumerateBatches(IReadOnlyCollection<string> hosts)
    {
        var batches = new List<List<string>>();
        var current = new List<string>();
        var budget = 2;  // 数组本身的 "[]"
        foreach (var host in hosts)
        {
            var cost = JsonSerializer.SerializeToUtf8Bytes(host).Length + 1;
            if (current.Count > 0 && budget + cost > MaxChunkPayloadBytes)
            {
                batches.Add(current);
                current = [];
                budget = 2;
            }
            current.Add(host);
            budget += cost;
        }
        batches.Add(current);
        return batches;
    }

    private DenylistAck InvokeHostDenylist(
        UpdateHostDenylistDelegate entry,
        List<string> hosts,
        int mode)
    {
        var input = hosts.Count;
        // 入参形态是 JSON 字符串数组（核心侧 serde 反序列化为 Vec<String>）；
        // host 已由 BlockedHosts 归一（小写、去尾点），此处不再加工。
        var payload = JsonSerializer.Serialize(hosts);
        var hostsPointer = Utf8(payload);
        IntPtr response;
        try
        {
            response = entry(Broker, hostsPointer, mode);
        }
        finally
        {
            Marshal.FreeCoTaskMem(hostsPointer);
        }
        if (response == IntPtr.Zero)
            return new DenylistAck(false, 0, input, false, false, false, -1,
                "native_response_pointer_null");
        try
        {
            var text = Marshal.PtrToStringUTF8(response);
            return text is null
                ? new DenylistAck(false, 0, input, false, false, false, -1,
                    "native_response_not_utf8")
                : ParseDenylistAck(text, input);
        }
        finally
        {
            _stringFree(response);
        }
    }

    /// <summary>解析注入应答 <c>{"decision":"ok","accepted":N,"input":M}</c>。
    /// 注意该信封不带 abi_version（与决策信封不同），故不能复用
    /// <see cref="ParseDecisionPayload"/>；能力探测靠 <c>clear</c>/<c>mode</c> 字段自身
    ///（见 <see cref="ParseDenylistAck"/>）。本方法只保留既有对外语义：非 ok 一律
    /// 如实回报未发布并带出 reason.code，accepted &lt; input 原样留给调用方——被拒条目
    /// 在核心侧是"看起来在工作的黑名单里的永久死条目"，静默吞掉正是本缺口藏五轮的原因。</summary>
    internal static CoreDenylistUpdateResult ParseUpdateResponse(string payload, int input)
    {
        var ack = ParseDenylistAck(payload, input);
        return ack.Published
            ? CoreDenylistUpdateResult.Apply(ack.Accepted, ack.Input, ack.EchoesClear)
            : CoreDenylistUpdateResult.NotPublished(input, ack.Detail);
    }

    [UnmanagedFunctionPointer(CallingConvention.Cdecl)]
    private delegate IntPtr UpdateHostDenylistDelegate(IntPtr broker, IntPtr hostsJson, int clear);
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

/// <summary>注入结果快照（不含 host 内容与任何本机路径——可安全落日志）。
/// <see cref="CoreEchoesClear"/> 只服务于分批判据（所加载核心是否真带
/// <c>clear</c> 参数），不参与 <see cref="Published"/> 语义。</summary>
public sealed record CoreDenylistUpdateResult(
    CoreDenylistOutcome Outcome,
    int Accepted,
    int Input,
    string Detail,
    bool CoreEchoesClear = false)
{
    /// <summary>核心侧是否真的拿到了这一批条目。</summary>
    public bool Published => Outcome is CoreDenylistOutcome.Published or CoreDenylistOutcome.PartiallyPublished;

    /// <summary>被核心形态校验/去重拒收的条目数（托管侧仍拦，核心侧永不命中）。</summary>
    public int RejectedEntryCount => Published ? Math.Max(Input - Accepted, 0) : Input;

    internal static CoreDenylistUpdateResult Apply(int accepted, int input, bool coreEchoesClear = false) => new(
        accepted < input ? CoreDenylistOutcome.PartiallyPublished : CoreDenylistOutcome.Published,
        accepted,
        input,
        accepted < input ? "partial_accept" : "ok",
        coreEchoesClear);

    internal static CoreDenylistUpdateResult MissingExport(int input) =>
        new(CoreDenylistOutcome.ExportMissing, 0, input, "denylist_export_missing");

    internal static CoreDenylistUpdateResult NotPublished(int input, string detail) =>
        new(CoreDenylistOutcome.NotPublished, 0, input, detail);
}

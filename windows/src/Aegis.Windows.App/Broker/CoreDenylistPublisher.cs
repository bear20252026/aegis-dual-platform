namespace Aegis.Windows.Broker;

using System;
using System.Collections.Generic;
using System.Threading;
using Aegis.Windows.Core.Security;

/// <summary>
/// 审计第六轮遗留缺口收口（2026-10-04）：把威胁订阅源快照发布进原生核心的
/// host 黑名单——核心侧的 deny-by-content 层自交付起零调用点（台账原话
/// "接入面已交付、无端调用"），Windows 的黑名单完全活在托管侧。
/// 单一权威源：推送的集合取自 <see cref="BlockedHosts.Hosts"/>，即托管侧
/// IsBlocked 正在用的那个集合的只读包装（不复制、不分叉）；进程级唯一持有者
/// <see cref="SharedBlockedHosts.Publish"/> 是本类唯一生产调用方，主窗与无痕窗
/// 的 broker 注入的是同一持有者，故一次发布即"全窗口托管判定 + 原生核心"同时生效。
/// 两个推送时机（缺一即缺口复发）：
/// ①快照变更——启动加载缓存 + 每一次订阅源刷新（ThreatFeedCoordinator 两条
///   apply 路径都收敛到 UpdateBlockedHosts → Publish）；
/// ②共享桥建立——桥只在原生核心真正接入时存在，且可能晚于第一次快照加载才
///   出现（broker 构造时机）；不在这里补推一次，本会话核心就带着空名单跑到底，
///   而托管侧拦得好好的（零痕迹，正是本缺陷的藏身方式）。
/// 原生核心未接入（环境变量与安装期标记都没置位 → 无桥）时无条件**无操作**，
/// 不是错误、不留痕（每次都成立即噪声）。旧版 DLL 缺导出时降级为"未发布"，
/// 只留痕一次。日志只记计数与原因码：不含 host 内容、不含任何本机绝对路径。
/// </summary>
public static class CoreDenylistPublisher
{
    private static readonly object Gate = new();
    private static IReadOnlyCollection<string>? _latest;
    private static int _missingExportLogged;

    /// <summary>CS-364 同型测试缝：桥提供者。生产恒 null → 取进程级共享桥
    ///（<see cref="NativePolicyCoreBridgeHub.Shared"/>，全进程一个，
    /// 所以一次推送同时覆盖主窗与无痕窗）。</summary>
    internal static Func<NativePolicyCoreBridge?>? BridgeProviderForTests;

    /// <summary>CS-364 同型测试缝：伪造核心应答，让"推送了几次""accepted &lt; input
    /// 是否留痕"这类断言在无原生 DLL 的机器上也确定性成立。生产恒 null。</summary>
    internal static Func<IReadOnlyCollection<string>, CoreDenylistUpdateResult>? CorePushForTests;

    /// <summary>当前权威快照（诊断/测试探针；null = 本会话尚未加载过任何快照）。</summary>
    internal static IReadOnlyCollection<string>? CurrentSnapshot
    {
        get { lock (Gate) return _latest; }
    }

    /// <summary>托管快照变更的唯一生产入口（由 <see cref="SharedBlockedHosts.Publish"/>
    /// 调用）。不可枚举的来源绝不猜——宁可保留核心侧旧快照并大声留痕。</summary>
    public static void OnManagedSnapshotChanged(IBlockedHosts snapshot)
    {
        var hosts = snapshot switch
        {
            BlockedHosts enumerated => enumerated.Hosts,
            // 空名单显式下推到核心（核心侧空集合 = 放行，与托管侧同口径；
            // 不下推才会让已撤销的条目在核心侧残留）
            NoBlockedHosts => (IReadOnlyCollection<string>)Array.Empty<string>(),
            _ => null,
        };
        if (hosts is null)
        {
            SecurityLog.Write("[core-denylist] 快照源不可枚举（自定义 IBlockedHosts）"
                              + "——核心黑名单本轮未更新，托管侧拦截不受影响");
            return;
        }
        lock (Gate) _latest = hosts;
        Push("订阅源快照更新");
    }

    /// <summary>共享桥建立时由 <see cref="NativePolicyCoreBridgeHub"/> 调用：
    /// 把当前快照补推一次（桥后建而不补推 = 核心整会话空名单）。</summary>
    public static void OnSharedBridgeCreated() => Push("原生桥建立");

    /// <summary>测试隔离：进程级静态状态归零（每个用例 Dispose 调用）。</summary>
    internal static void ResetForTests()
    {
        lock (Gate) _latest = null;
        BridgeProviderForTests = null;
        CorePushForTests = null;
        Interlocked.Exchange(ref _missingExportLogged, 0);
    }

    private static void Push(string trigger)
    {
        IReadOnlyCollection<string>? hosts;
        lock (Gate) hosts = _latest;
        if (hosts is null)
            return;  // 还没有任何快照——核心保持默认空名单（放行），与既往一致
        var bridge = BridgeProviderForTests is null ? NativePolicyCoreBridgeHub.Shared : BridgeProviderForTests();
        var simulated = CorePushForTests;
        if (bridge is null && simulated is null)
            return;  // 原生核心未接入（无桥）——无操作，不是错误
        Report(simulated is not null ? simulated(hosts) : bridge!.UpdateHostDenylist(hosts), trigger, hosts.Count);
    }

    private static void Report(CoreDenylistUpdateResult result, string trigger, int offered)
    {
        switch (result.Outcome)
        {
            case CoreDenylistOutcome.ExportMissing:
                // 只留痕一次：旧版核心缺导出是既定兼容态，每轮刷新重复写盘没有信息量
                if (Interlocked.Exchange(ref _missingExportLogged, 1) == 0)
                    SecurityLog.Write($"[core-denylist] {trigger}：已加载的 aegis_policy_core.dll 未导出 "
                                      + $"host 黑名单入口（offered {offered} 条）——核心黑名单未发布，"
                                      + "托管侧拦截不受影响；需重新构建原生核心才能在核心侧兑现拦截");
                return;
            case CoreDenylistOutcome.NotPublished:
                SecurityLog.Write($"[core-denylist] {trigger}：核心黑名单未发布"
                                  + $"（offered {offered} 条，原因 {result.Detail}）——托管侧拦截不受影响");
                return;
            case CoreDenylistOutcome.PartiallyPublished:
                // 这条必须显眼：被拒条目在核心侧是永久死条目，却伪装成"订阅源在工作的黑名单"
                SecurityLog.Write($"[core-denylist] {trigger}：核心只接受 {result.Accepted}/{result.Input} 条——"
                                  + $"{result.RejectedEntryCount} 条被核心形态校验拒收，"
                                  + "它们在核心侧是永不命中的死条目（托管侧仍在拦截）");
                return;
            default:
                SecurityLog.Write($"[core-denylist] {trigger}：核心黑名单已发布 "
                                  + $"{result.Accepted}/{result.Input} 条");
                return;
        }
    }
}

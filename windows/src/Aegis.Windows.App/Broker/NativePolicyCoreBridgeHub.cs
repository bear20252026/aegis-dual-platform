namespace Aegis.Windows.Broker;

using System;

/// <summary>审计第七轮（2026-10-03·latent：仅在 AEGIS_REQUIRE_NATIVE_POLICY_CORE=1
/// 的原生模式下生效）：原生策略核心桥的进程级共享持有者。
/// 为什么必须共享：Rust 侧 aegis_policy_core_broker_new 强制「进程内单活 broker」
///（RS-140），已存在存活 broker 时返回 null。此前每个 BrowserPolicyBroker 各自
/// TryCreate：主窗在组合根先建掉唯一的 broker #1，无痕窗 broker 的字段初始器
/// 只能拿到 null → 原生模式下无痕窗每一帧导航/每一次下载全部
/// native_policy_core_bridge_unavailable（实测缺陷）。
/// 语义：全进程只创建一个桥，broker 构造引用计数 +1、Dispose 计数 -1，归零才
/// 真正释放（释放后如需再开窗可重建——原生侧单活约束随 broker_free 解除）。
/// broker 侧不得直接 Dispose 共享桥，必须走 Release。</summary>
public static class NativePolicyCoreBridgeHub
{
    private static readonly object Gate = new();
    private static NativePolicyCoreBridge? _shared;
    private static int _references;

    /// <summary>当前共享桥（未创建时为 null——只读探针，不计数）。供测试与
    /// 诊断判定"原生模式是否真的接上了核心"。</summary>
    public static NativePolicyCoreBridge? Shared
    {
        get { lock (Gate) return _shared; }
    }

    /// <summary>取得共享桥（必要时创建）。返回 null 表示原生核心不可用——
    /// 调用方（broker）必须 fail-closed，绝不回退到另一套策略实现。
    /// factory 为测试/装配注入缝（生产恒为 NativePolicyCoreBridge.TryCreate）。</summary>
    public static NativePolicyCoreBridge? Acquire(
        string policyVersion, Func<NativePolicyCoreBridge?>? factory = null)
    {
        NativePolicyCoreBridge? bridge;
        var freshlyCreated = false;
        lock (Gate)
        {
            // 失败结果不入缓存：库文件可能随后就位（与 CS-323 门禁探测的
            // "失败按 TTL 重试"口径一致）——但同一进程内的成功结果恒复用，
            // 绝不再建第二个原生 broker
            if (_shared is null)
            {
                _shared = factory is not null ? factory() : Create(policyVersion);
                freshlyCreated = _shared is not null;
            }
            if (_shared is null)
                return null;
            _references++;
            bridge = _shared;
        }
        // 审计第六轮遗留缺口收口（2026-10-04）：桥从无到有的那一刻必须把当前
        // 威胁快照补推进核心——broker 可能在第一次订阅源加载完成之后才建桥，
        // 不补推则核心整会话带空名单运行（托管侧拦得好好的，零痕迹）。
        // 锁外通知：CoreDenylistPublisher 会回读本类的 Shared 探针。
        if (freshlyCreated)
            CoreDenylistPublisher.OnSharedBridgeCreated();
        return bridge;
    }

    /// <summary>归还引用（broker.Dispose 路径）。引用归零才释放桥；释放后置空，
    /// 后续 Acquire 可重建。null 入参为无操作（非原生模式的常态）。</summary>
    public static void Release(NativePolicyCoreBridge? bridge)
    {
        if (bridge is null)
            return;
        NativePolicyCoreBridge? doomed = null;
        lock (Gate)
        {
            if (!ReferenceEquals(_shared, bridge))
                return;  // 非共享实例（测试注入的独立桥）——由注入方自行释放
            if (--_references > 0)
                return;
            doomed = _shared;
            _shared = null;
            _references = 0;
        }
        doomed?.Dispose();  // 锁外释放——Dispose 走原生 broker_free（可能阻塞）
    }

    /// <summary>当前引用数（诊断/测试用）。生产语义：>0 即原生核心在位。</summary>
    internal static int ReferenceCount
    {
        get { lock (Gate) return _references; }
    }

    private static NativePolicyCoreBridge? Create(string policyVersion)
    {
        NativePolicyCoreBridge.TryCreate(policyVersion, NativePolicyCoreGate.LibraryPath, out var bridge);
        return bridge;
    }
}

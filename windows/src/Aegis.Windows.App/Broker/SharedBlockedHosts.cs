namespace Aegis.Windows.Broker;

using Aegis.Windows.Core.Security;

/// <summary>审计第七轮（2026-10-03）：进程级共享威胁黑名单持有者（P1）。
/// 与 <see cref="KillSwitch.Shared"/>（CS-291）同款模式——此前威胁订阅源刷新
/// 只把快照 apply 到主窗口那一个 broker 的实例字段（MainWindow
/// StartThreatFeedRefresh → _broker.UpdateBlockedHosts），无痕窗口 broker 的
/// 字段自构造起恒为 NoBlockedHosts：每条无痕会话的 denylist 永久为空，
/// 已知恶意 host 照常导航，HostWebView.OnWebResourceRequested 的 IsHostBlocked
/// 也永不 403——隐私路径是全进程保护最弱的一条（与 CS-291 修复前的
/// KillSwitch fail-open 同一缺陷类）。
/// 组合根（MainWindowDependencies.Defaults / InPrivateWindow）把本单例注入
/// 每个 broker，Publish 一次即全窗口同步生效。volatile 整体替换引用，
/// 与 broker 侧 _blockedHosts 的既有线程安全口径一致。</summary>
public sealed class SharedBlockedHosts : IBlockedHosts
{
    /// <summary>进程级唯一实例（缺省空名单——未配置订阅源时一律放行，不影响浏览）。</summary>
    public static SharedBlockedHosts Shared { get; } = new();

    private volatile IBlockedHosts _hosts = NoBlockedHosts.Instance;

    /// <summary>发布新快照（订阅源刷新完成时调用——原子换引用）。null 回退空名单，
    /// 与 <see cref="BrowserPolicyBroker.UpdateBlockedHosts"/> 口径一致。</summary>
    public void Publish(IBlockedHosts? hosts) => _hosts = hosts ?? NoBlockedHosts.Instance;

    public bool IsBlocked(string host) => _hosts.IsBlocked(host);
}

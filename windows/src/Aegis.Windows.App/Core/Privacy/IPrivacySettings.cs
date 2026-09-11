namespace Aegis.Windows.Core.Privacy;

/// <summary>运行时隐私策略读取面。HostWebView 依赖此接口而非直接引用静态
/// PrivacySettings——解耦 WebView 适配层与全局可变状态，导航/跟踪分级决策
/// 可注入假实现做单测。默认实现 [LivePrivacySettings] 仍读进程级静态（单一
/// 运行时事实源，由 SettingsService.Apply 写入）。</summary>
public interface IPrivacySettings
{
    /// <summary>HTTPS-only：http 顶层导航主动升级为 https。</summary>
    bool HttpsOnly { get; }

    /// <summary>跟踪防护分级（0=关 / 1=均衡 / 2=严格）。</summary>
    int ProtectionLevel { get; }
}

/// <summary>默认实现：读取进程级静态 PrivacySettings 当前值（实时——设置
/// 改动即时生效，与旧行为一致）。</summary>
public sealed class LivePrivacySettings : IPrivacySettings
{
    /// <summary>进程内共享单例（无状态——只做静态转发）。</summary>
    public static readonly LivePrivacySettings Instance = new();

    private LivePrivacySettings() { }

    public bool HttpsOnly => PrivacySettings.HttpsOnly;

    public int ProtectionLevel => PrivacySettings.ProtectionLevel;
}
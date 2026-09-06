namespace Aegis.Windows.Core.Privacy;

using System;

/// <summary>运行期隐私策略（HostWebView 读取；由主窗口在启动/设置变更时写入）。
/// 独立于 AppSettings 持久层——WebView 原生事件无需访问设置文件即可快速取用。
/// 安全 DNS 变化需重启生效（环境参数构建一次）。</summary>
public static class PrivacySettings
{
    /// <summary>跟踪防护级别：0 基础 / 1 均衡 / 2 严格。</summary>
    public static int ProtectionLevel = 1;

    /// <summary>HTTPS-only：http 自动升级 https（无 https 的站点会失败并提示）。</summary>
    public static bool HttpsOnly = true;

    /// <summary>安全 DNS（DoH）：随环境参数生效，改动需重启。</summary>
    public static bool SecureDns = true;
}

namespace Aegis.Windows.WebView;

using System;

/// <summary>
/// 确认型导航的显式 rollout 门禁。默认关闭以保持既有浏览体验；开启后要求 Rust
/// 原生核心已启用，任何缺少确认协调能力的情况均由 HostWebView 失败闭合。
/// </summary>
public static class NavigationConfirmationGate
{
    public const string EnableEnvironmentVariable = "AEGIS_REQUIRE_NAVIGATION_CONFIRMATION";

    public static bool IsRequired =>
        string.Equals(Environment.GetEnvironmentVariable(EnableEnvironmentVariable), "1", StringComparison.Ordinal);
}

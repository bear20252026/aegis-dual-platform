namespace Aegis.Windows.WebView;

using System;
using Aegis.Windows.Broker;

/// <summary>
/// 确认型导航的显式 rollout 门禁。默认关闭以保持既有浏览体验；开启后要求 Rust
/// 原生核心已启用，任何缺少确认协调能力的情况均由 HostWebView 失败闭合。
/// </summary>
public static class NavigationConfirmationGate
{
    public const string EnableEnvironmentVariable = "AEGIS_REQUIRE_NAVIGATION_CONFIRMATION";

    public static bool IsRequired =>
        string.Equals(Environment.GetEnvironmentVariable(EnableEnvironmentVariable), "1", StringComparison.Ordinal)
        // 审计第六轮（2026-10-04）：与 NativePolicyCoreGate 同形的第二来源——
        // 安装期标记（同一登记处的另一个值名，两 Gate 共用 InstalledBuildMarker
        // 以免键路径漂移）。安装器当前**不写**此值，故出厂默认仍为关闭——完整
        // 理由记在 InstalledBuildMarker.NavigationConfirmationValueName（要点：
        // 核心现在的高危判据是本机/私网 host，Windows 两点已硬拒＝死路径；且确认
        // 链不复判托管黑名单，而核心的黑名单注入入口尚无 C# 绑定与调用点）。
        || InstalledBuildMarker.IsSet(InstalledBuildMarker.NavigationConfirmationValueName);
}

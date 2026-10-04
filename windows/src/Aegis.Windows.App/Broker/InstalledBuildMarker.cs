namespace Aegis.Windows.Broker;

using System;
using Microsoft.Win32;

/// <summary>
/// 审计第六轮（2026-10-04）：安装期写入的"出厂裁决模式"标记——注册表键路径与
/// 值名的**单一登记处**，由 <see cref="NativePolicyCoreGate"/>、
/// <see cref="Aegis.Windows.WebView.NavigationConfirmationGate"/> 与
/// docs/release/AegisSetup-CSharp.iss 三方对齐（InstalledBuildMarkerTests 逐字
/// 对账 iss 与本类常量——本仓反复复发的故障模式正是"两处字符串各写各的"，
/// 同 TrustedChromeUiOrigins 的收敛理由）。
/// 要修的断链：AEGIS_REQUIRE_NATIVE_POLICY_CORE 只在 CI 构建步的 shell 里赋值，
/// 既不随安装包交付也不进入终端用户进程环境——于是 aegis_policy_core.dll 随包
/// 发布却从不被咨询，出货制品的导航裁决与构建期被测路径不是同一条（前五轮
/// 未被发现，因为决策路径差异零痕迹，见第六轮台账"分端裁决现状"）。
/// 为什么是 HKCU：安装脚本 PrivilegesRequired=lowest 为按用户安装（不提权），
/// HKLM 写入需要管理员；HKCU 是安装器可写、应用可读、无需提升的落点。安装器在
/// 64 位模式（ArchitecturesInstallIn64BitMode=x64compatible）下写的正是 x64 应用
/// 默认读取的视图。
/// 为什么不能把"必须原生核心"改成恒真：Aegis.Windows.App.csproj 仅在
/// -p:RequireNativePolicyCore=true 且给定存在路径时才拷贝 DLL，普通 dotnet build
/// 产物没有 DLL——恒真则每个开发构建启动即 ProbeLibrary 失败并全导航
/// fail-closed（毁掉开发工作流）。因此该要求只由安装期标记或环境变量驱动，
/// 开发机恒为 Disabled()。
/// </summary>
public static class InstalledBuildMarker
{
    /// <summary>标记所在键（HKCU 下相对路径）——iss 的 Subkey 必须逐字一致。</summary>
    public const string RegistrySubKeyPath = @"Software\Aegis Browser";

    /// <summary>出厂强制 Rust 策略核心参与裁决（DWORD 1）。</summary>
    public const string NativePolicyCoreValueName = "RequireNativePolicyCore";

    /// <summary>出厂强制导航确认门（DWORD 1）。安装器**刻意不写**此值——理由必须
    /// 记实（"Rust 把每一个 Allow 都转成 RequireConfirmation"这一旧前提已被核心侧
    /// R6-21 改掉，不能拿过期理由支撑一个出厂开关）：
    /// ①核心的高危判据现在是本机/私网 host，而 Windows 在 EvaluateNavigation 与
    ///   TryConsumeNavigation 两点都已硬拒这类 host → 标记置位只会得到"弹确认面板
    ///   后被同一边界再拒"的死路径，零安全增益；
    /// ②确认链（RequestNavigationConfirmation → RequireConfirmation → Approve →
    ///   TryConsumeNavigation）不复判托管黑名单 _blockedHosts。核心侧的注入入口
    ///   aegis_policy_core_broker_update_host_denylist_json 现已有 C# 绑定与调用点
    ///  （订阅源快照经 CoreDenylistPublisher 从进程级唯一持有者单源注入，核心的
    ///   consume_navigation 会复判）——因此这条口子**只在所发布的核心 DLL 确实导出
    ///   该入口时**才闭合：对着缺该导出的旧 DLL 出厂启用，仍等于给黑名单 host 开一条
    ///   "用户点一次批准即放行"的面。
    /// 顺序要求：其②（先把 ThreatFeedCoordinator 的快照喂给核心、黑名单单源化）已
    /// 达成；其①（零安全增益）未消解，故出厂态仍为关闭。机制与本类另一个标记完全
    /// 对称，该开关仍只由环境变量在受控构建/测试里置位。</summary>
    public const string NavigationConfirmationValueName = "RequireNavigationConfirmation";

    /// <summary>审计第六轮（2026-10-04）：值读取注入缝（与 CS-364 租约工厂缝
    /// 同型）——用例注入假读取器即可断言"注册表源单独成立"，不依赖真实
    /// 注册表写入；生产恒为 null（走 Registry.CurrentUser 只读打开）。</summary>
    internal static Func<string, string, object?>? ValueReaderForTests;

    /// <summary>安装期标记是否置位（DWORD 1 或字符串 "1"）。键/值缺失、类型
    /// 不符、无读取权限一律 false——开发机常态，绝不向调用方抛异常。</summary>
    public static bool IsSet(string valueName) => ReadValue(valueName) switch
    {
        int number => number == 1,
        string text => string.Equals(text, "1", StringComparison.Ordinal),
        _ => false,
    };

    private static object? ReadValue(string valueName)
    {
        try
        {
            var reader = ValueReaderForTests;
            if (reader is not null)
                return reader(RegistrySubKeyPath, valueName);

            // 只读打开当前用户键：不创建、不写入、不要求提升（值内容不入库、
            // 不进日志——标记本身不是用户数据，但仍按最小暴露处理）
            using var key = Registry.CurrentUser.OpenSubKey(RegistrySubKeyPath);
            return key?.GetValue(valueName);
        }
        catch (Exception)
        {
            // 注册表 hive 不可用/权限异常按未置位处理：门禁的第二来源不能
            // 成为新的启动失败面（fail-closed 语义仍由 ProbeLibrary 承担）
            return null;
        }
    }
}

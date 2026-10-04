using Aegis.Windows.Broker;
using Aegis.Windows.WebView;
using Xunit;

namespace Aegis.Windows.Broker.Tests;

/// <summary>审计第六轮（2026-10-04）：安装期标记作为两个门禁的第二来源。
/// 背景（出货断链）：AEGIS_REQUIRE_NATIVE_POLICY_CORE 只在 CI 构建步的 shell
/// 里赋值，不随安装包交付也不进入终端用户进程环境——运行时恒 Disabled()，
/// aegis_policy_core.dll 随包发布却从不被咨询。
/// 测试面用 InstalledBuildMarker.ValueReaderForTests 注入假注册表（CS-364
/// 工厂缝同型）——用例既不写也不读真实注册表，因此可在任何机器上确定性运行。
/// 三条必钉的性质：①仅标记置位即要求原生核心（本次修复的目的）；
/// ②环境变量路径仍然有效（CI/开发手动开启）；③两者皆无 → Disabled()
/// 放行托管 broker（普通 dotnet build 无 DLL，若门禁恒真则开发构建启动即
/// 全导航 fail-closed——反毁掉开发工作流的锚）。
/// 本类逐用例在构造期清空两个环境变量并在 Dispose 还原（原生 job 会在进程
/// 环境里置 1，见 release-windows.yml），不污染同程序集的原生往返用例。</summary>
public sealed class InstalledBuildMarkerTests : IDisposable
{
    private readonly string? _previousNativeEnvironment =
        Environment.GetEnvironmentVariable(NativePolicyCoreGate.EnableEnvironmentVariable);
    private readonly string? _previousConfirmationEnvironment =
        Environment.GetEnvironmentVariable(NavigationConfirmationGate.EnableEnvironmentVariable);
    private readonly Func<string, string, object?>? _previousReader = InstalledBuildMarker.ValueReaderForTests;

    /// <summary>假注册表内容：键为 "&lt;子键&gt;|&lt;值名&gt;"。</summary>
    private Dictionary<string, object?> Values { get; } = new(StringComparer.Ordinal);

    /// <summary>假注册表被读取的 (子键, 值名) 序列——钉住"读的就是登记处那一处"，
    /// 并使"标记被真正咨询"可断言（不依赖 DLL 是否在位）。</summary>
    private List<(string SubKey, string ValueName)> Reads { get; } = new();

    public InstalledBuildMarkerTests()
    {
        Environment.SetEnvironmentVariable(NativePolicyCoreGate.EnableEnvironmentVariable, null);
        Environment.SetEnvironmentVariable(NavigationConfirmationGate.EnableEnvironmentVariable, null);
        InstalledBuildMarker.ValueReaderForTests = (subKey, valueName) =>
        {
            Reads.Add((subKey, valueName));
            return Values.TryGetValue($"{subKey}|{valueName}", out var value) ? value : null;
        };
    }

    public void Dispose()
    {
        InstalledBuildMarker.ValueReaderForTests = _previousReader;
        Environment.SetEnvironmentVariable(
            NativePolicyCoreGate.EnableEnvironmentVariable, _previousNativeEnvironment);
        Environment.SetEnvironmentVariable(
            NavigationConfirmationGate.EnableEnvironmentVariable, _previousConfirmationEnvironment);
    }

    private void Mark(string valueName, object? value) =>
        Values[$"{InstalledBuildMarker.RegistrySubKeyPath}|{valueName}"] = value;

    // ===== ①：仅安装期标记（终端用户常态——环境变量不存在） =====

    [Fact]
    public void NativePolicyCoreGate_RegistryMarkerAlone_RequiresNativeCore()
    {
        Mark(InstalledBuildMarker.NativePolicyCoreValueName, 1);

        Assert.True(NativePolicyCoreGate.IsRequired);
        // 确实读了登记处的这一处（键路径与值名逐字来自 InstalledBuildMarker——
        // 与安装脚本的对账见 InstallerScript_* 用例）
        Assert.Contains((InstalledBuildMarker.RegistrySubKeyPath, InstalledBuildMarker.NativePolicyCoreValueName), Reads);
    }

    [Fact]
    public void NavigationConfirmationGate_RegistryMarkerAlone_RequiresConfirmation()
    {
        Mark(InstalledBuildMarker.NavigationConfirmationValueName, 1);

        Assert.True(NavigationConfirmationGate.IsRequired);
        Assert.Contains(
            (InstalledBuildMarker.RegistrySubKeyPath, InstalledBuildMarker.NavigationConfirmationValueName), Reads);
    }

    // ===== ②：环境变量源仍然有效（CI 原生 job / 开发手动开启） =====

    [Fact]
    public void NativePolicyCoreGate_EnvironmentVariableAlone_RequiresNativeCore()
    {
        Environment.SetEnvironmentVariable(NativePolicyCoreGate.EnableEnvironmentVariable, "1");

        Assert.True(NativePolicyCoreGate.IsRequired);
    }

    [Fact]
    public void NavigationConfirmationGate_EnvironmentVariableAlone_RequiresConfirmation()
    {
        Environment.SetEnvironmentVariable(NavigationConfirmationGate.EnableEnvironmentVariable, "1");

        Assert.True(NavigationConfirmationGate.IsRequired);
    }

    // ===== ③：两者皆无 = 开发机构建常态（反"恒真"毁掉 dotnet build） =====

    [Fact]
    public void NativePolicyCoreGate_NeitherSource_ProbeIsDisabledAndAllowsManagedBroker()
    {
        Assert.False(NativePolicyCoreGate.IsRequired);

        // Disabled() 形态：允许平台 broker、无拒绝码——启动不 fail-closed
        //（普通 dotnet build 产物没有 aegis_policy_core.dll，若门禁恒真
        //  此处即 Block("native_policy_core_unavailable") → 全部导航被拒）
        var result = NativePolicyCoreGate.ProbeFromEnvironment();
        Assert.True(result.AllowsPlatformBroker);
        Assert.Null(result.DenialCode);
        Assert.Equal(NativePolicyCoreGateResult.Disabled(), result);
    }

    [Fact]
    public void NavigationConfirmationGate_NeitherSource_NotRequired()
    {
        Assert.False(NavigationConfirmationGate.IsRequired);
    }

    // ===== 两个标记互不串门（同一登记处、不同值名） =====

    [Fact]
    public void NativeCoreMarker_DoesNotEnableConfirmationGate_AndViceVersa()
    {
        Mark(InstalledBuildMarker.NativePolicyCoreValueName, 1);
        Assert.True(NativePolicyCoreGate.IsRequired);
        // 两个标记各管各的门：置了原生核心标记不得顺带打开确认门——确认门的
        // 出厂态由 InstalledBuildMarker.NavigationConfirmationValueName 的注释
        // 单独支撑（本机/私网已由托管层硬拒 + 确认链不复判托管黑名单）
        Assert.False(NavigationConfirmationGate.IsRequired);

        Values.Clear();
        Reads.Clear();
        Mark(InstalledBuildMarker.NavigationConfirmationValueName, 1);
        Assert.True(NavigationConfirmationGate.IsRequired);
        Assert.False(NativePolicyCoreGate.IsRequired);
    }

    // ===== 读取面的取值容忍度与"绝不抛出" =====

    [Theory]
    [InlineData(1, true)]
    [InlineData(0, false)]
    [InlineData(2, false)]
    public void IsSet_DwordValue_OnlyOneMeansOptedIn(int value, bool expected)
    {
        Mark(InstalledBuildMarker.NativePolicyCoreValueName, value);

        Assert.Equal(expected, InstalledBuildMarker.IsSet(InstalledBuildMarker.NativePolicyCoreValueName));
    }

    [Theory]
    [InlineData("1", true)]
    [InlineData("0", false)]
    [InlineData("true", false)]
    [InlineData(null, false)]
    public void IsSet_StringValueOrAbsence_OnlyExactOneMeansOptedIn(string? value, bool expected)
    {
        Mark(InstalledBuildMarker.NativePolicyCoreValueName, value);

        Assert.Equal(expected, InstalledBuildMarker.IsSet(InstalledBuildMarker.NativePolicyCoreValueName));
    }

    [Fact]
    public void IsSet_ReaderThrows_IsFalseWithoutException()
    {
        // 缺键/缺值是开发机常态；hive 异常同样绝不逃出——第二来源不能
        // 变成新的启动失败面（fail-closed 语义仍由 ProbeLibrary 承担）
        InstalledBuildMarker.ValueReaderForTests = (_, _) =>
            throw new UnauthorizedAccessException("模拟注册表不可读");

        Assert.False(InstalledBuildMarker.IsSet(InstalledBuildMarker.NativePolicyCoreValueName));
        Assert.False(NativePolicyCoreGate.IsRequired);
        Assert.True(NativePolicyCoreGate.ProbeFromEnvironment().AllowsPlatformBroker);
    }

    // ===== 与安装脚本的对账（本仓复发故障模式=两处字符串各写各的） =====

    [Fact]
    public void InstallerScript_RegistryMarkerLines_MatchMarkerConstantsVerbatim()
    {
        var iss = File.ReadAllText(FindInstallerScriptPath());

        // 写入的正是本类登记的键与值名，且为 DWORD 1、卸载时删除（同一行——
        // 拆到两行就成了"另一个值写 1"，逐行取而非全文 Contains）
        var line = iss
            .Split('\n')
            .Single(l => l.Contains($@"ValueName: ""{InstalledBuildMarker.NativePolicyCoreValueName}""", StringComparison.Ordinal));
        Assert.StartsWith(
            $@"Root: HKCU; Subkey: ""{InstalledBuildMarker.RegistrySubKeyPath}""" +
            $@"; ValueType: dword; ValueName: ""{InstalledBuildMarker.NativePolicyCoreValueName}""" +
            @"; ValueData: ""1"";",
            line.TrimStart(),
            StringComparison.Ordinal);
        Assert.Contains("uninsdeletevalue", line, StringComparison.Ordinal);
        // HKCU 成立的前提：按用户安装、不提权（改成管理员安装即需重新评估 hive）
        Assert.Contains(@"PrivilegesRequired=lowest", iss, StringComparison.Ordinal);
    }

    [Fact]
    public void InstallerScript_DoesNotShipNavigationConfirmationMarker()
    {
        // 刻意不写确认门标记（完整理由见 InstalledBuildMarker 的
        // NavigationConfirmationValueName 注释）。真要出厂启用时本用例应
        // **主动失败并被推翻**：其成立前提之一——给 C# 绑定
        // aegis_policy_core_broker_update_host_denylist_json 并把订阅源快照喂进核心
        // ——已由 CoreDenylistPublisher 达成（HostDenylistInjection… 与
        // CoreDenylistPublisherTests 锁定），但"零安全增益"那条前提仍未消解，
        // 故出厂态保持关闭；推翻它需要新的论证，而不是顺手加一行 [Registry]。
        var iss = File.ReadAllText(FindInstallerScriptPath());

        Assert.DoesNotContain(
            $@"ValueName: ""{InstalledBuildMarker.NavigationConfirmationValueName}""", iss, StringComparison.Ordinal);
    }

    /// <summary>向上定位安装脚本（测试输出层级随 RID 变化——按仓库布局标记
    /// 上溯，不依赖固定层数，与 Core.Tests 的 XAML 锚点用例同法）。
    /// 找不到即显式 throw：本用例绝不"环境缺失就静默通过"（R6-13 的假绿教训）。</summary>
    private static string FindInstallerScriptPath()
    {
        var dir = new DirectoryInfo(AppContext.BaseDirectory);
        while (dir is not null)
        {
            var candidate = Path.Combine(dir.FullName, "docs", "release", "AegisSetup-CSharp.iss");
            if (File.Exists(candidate))
                return candidate;
            dir = dir.Parent!;
        }
        throw new InvalidOperationException(
            "未定位到 docs/release/AegisSetup-CSharp.iss（仓库布局契约）");
    }
}

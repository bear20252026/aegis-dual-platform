using System.IO;
using Xunit;

namespace Aegis.Windows.Broker.Tests;

/// <summary>审计第七轮 R7-CS1-04/15：原生跨界纪律的常驻静态锚。
/// 缺陷形态是实测出来的，不是推出来的——原生模式下跑 Core.Tests 时测试主机
/// `0xC0000005` 崩溃（崩溃前通过的用例数不稳定：667/403/389/502），崩溃转储的
/// 模块列表里 `aegis_policy_core.dll` **已不在场**，即 AV 来自"调用已卸载镜像中的
/// 函数指针"；而桥的八个原生入口此前直取 `DangerousGetHandle()`、不检 `_disposed`，
/// 注释里声称的租约守卫（`TryAcquireLease/ReleaseLease`）只有黑名单一处消费，
/// `IsUsable` 全仓零引用＝伪装成守卫的死代码（R6-26「接入面零调用者」同型）。
/// 这三条都可以被"改回去而测试仍全绿"，所以钉成源码锚——运行期锚无法稳定复现
/// GC/终结时序，把它当唯一防线就是假保证。</summary>
public sealed class NativePolicyCoreBridgeLeaseTests
{
    private static string BridgeSource => ReadBridge("NativePolicyCoreBridge.cs");

    private static string InteropSource => ReadBridge("NativePolicyCoreBridge.NativeInterop.cs");

    private static string ReadBridge(string name)
    {
        var dir = new DirectoryInfo(AppContext.BaseDirectory);
        while (dir is not null)
        {
            var candidate = Path.Combine(
                dir.FullName, "windows", "src", "Aegis.Windows.App", "Broker", name);
            if (File.Exists(candidate))
                return File.ReadAllText(candidate);
            dir = dir.Parent!;
        }
        throw new InvalidOperationException($"未定位到 Broker/{name}（仓库布局契约）");
    }

    /// <summary>八个原生入口的名单——新增入口必须一并登记（漏一个就是漏一道门）。</summary>
    private static readonly string[] NativeEntries =
    [
        "CreateSession", "DestroySession", "AdvanceDocumentGeneration",
        "EvaluateNavigation", "RequestNavigationConfirmation",
        "ApproveNavigationConfirmation", "RejectNavigationConfirmation",
        "TryConsumeNavigation",
    ];

    [Theory]
    [MemberData(nameof(NativeEntryNames))]
    public void EveryNativeEntryTakesALeaseBeforeCrossing(string entry)
    {
        var source = BridgeSource;
        var start = source.IndexOf($"public bool {entry}(", StringComparison.Ordinal);
        if (start < 0)
            start = source.IndexOf($"public Decision {entry}(", StringComparison.Ordinal);
        Assert.True(start >= 0, $"原生入口 {entry} 未找到——入口被改名/删除也要同步本锚");

        var body = source[start..(source.IndexOf("\n    public ", start + 10,
            StringComparison.Ordinal) > 0
            ? source.IndexOf("\n    public ", start + 10, StringComparison.Ordinal)
            : source.Length)];
        Assert.Contains("InvokeLeased(", body);
    }

    public static TheoryData<string> NativeEntryNames()
    {
        var data = new TheoryData<string>();
        foreach (var entry in NativeEntries)
            data.Add(entry);
        return data;
    }

    [Fact]
    public void BrokerPointerIsOnlyReadInsideTheLeaseHelper()
    {
        // 裸指针获取点必须只有一处，且就在租约里——入口自己 DangerousGetHandle
        // 就绕过引用计数（use-after-free 的入口）。只数代码行：注释里的历史记述
        // 不算读取点（把注释也数进去，锚点会因写解释而变红，最终被人删掉）。
        // 行尾判据不得依赖运行平台：仓库加了 .gitattributes（* text=auto eol=lf）后，
        // 源文件在 Windows runner 上也是 LF，而 Environment.NewLine 是 CRLF——用它切分
        // 会把整份文件当成一行，注释过滤静默失效，本锚点从 1 变 2（第八轮 B6 由 CI 暴露）。
        var code = string.Join("\n",
            BridgeSource.Replace("\r\n", "\n").Split('\n', StringSplitOptions.None)
                .Where(line => !line.TrimStart().StartsWith("//", StringComparison.Ordinal)));
        Assert.Equal(1, CountOf(code, "_brokerHandle.DangerousGetHandle()"));
        var take = code.IndexOf("return operation(Broker);", StringComparison.Ordinal);
        var lease = code.IndexOf("private T InvokeLeased<T>", StringComparison.Ordinal);
        Assert.True(lease >= 0 && take > lease, "唯一读取点必须位于 InvokeLeased 之内");
        // 八个入口一律把 broker 当参数交给 operation——自己传给委托即绕过租约
        Assert.Equal(0, CountOf(code, "Broker,"));
    }

    private static int CountOf(string haystack, string needle)
    {
        var count = 0;
        for (var i = haystack.IndexOf(needle, StringComparison.Ordinal);
             i >= 0; i = haystack.IndexOf(needle, i + needle.Length, StringComparison.Ordinal))
            count++;
        return count;
    }

    [Fact]
    public void IsUsableGuardIsActuallyConsumed()
    {
        // R7-CS1-04：该属性此前全仓零引用（注释把它写成守卫，代码里是死代码）
        var source = BridgeSource;
        var definition = source.IndexOf("private bool IsUsable", StringComparison.Ordinal);
        Assert.True(definition >= 0, "IsUsable 已消失——租约入口检查须同步改名，不能留空档");
        Assert.True(source[definition..].Contains("IsUsable")
                || source[..definition].Contains("if (!IsUsable)"),
            "IsUsable 无任何消费者＝伪装成守卫的死代码");
        Assert.Contains("if (!IsUsable)", source);
    }

    [Fact]
    public void NativeImageIsNeverUnloadedWhileDelegatesMayStillBeCalled()
    {
        // R7-CS1-15 根因锚：NativeLibraryHandle.ReleaseHandle 不得再 FreeLibrary。
        // 故障注入实测：把 NativeLibrary.Free 加回去 → 原生模式 Core.Tests 在
        // 第 45 例即中止（Unreachable/AV）；常驻后同一条命令 711/711 连跑两轮通过。
        var release = InteropSource[InteropSource.IndexOf(
            "class NativeLibraryHandle", StringComparison.Ordinal)..];
        release = release[..release.IndexOf("class NativeBrokerHandle", StringComparison.Ordinal)];
        Assert.DoesNotContain("NativeLibrary.Free", release);
    }

    [Fact]
    public void NativeModeCoreTestsAreGatedInCi()
    {
        // 缺口本身也要钉住：此前唯一以 AEGIS_REQUIRE_NATIVE_POLICY_CORE=1 真跑的
        // 作业只跑 Broker.Tests，Core.Tests 从未走过跨界路径——所以崩溃藏了五轮。
        var workflow = Path.Combine(FindRepoRoot(), ".github", "workflows", "native-policy-artifacts.yml");
        var text = File.ReadAllText(workflow);
        var native = text.IndexOf("AEGIS_REQUIRE_NATIVE_POLICY_CORE = \"1\"", StringComparison.Ordinal);
        Assert.True(native >= 0, "原生模式开关不再在作业里置位");
        var core = text.IndexOf("Aegis.Windows.Core.Tests", native, StringComparison.Ordinal);
        Assert.True(core > native, "原生模式下没有跑 Core.Tests");
        var publish = text.IndexOf("dotnet publish", core, StringComparison.Ordinal);
        Assert.True(publish > core, "Core.Tests 之后缺少 publish 步（判定被吞退出码的老形态）");
        Assert.Contains("原生模式 Core.Tests 失败", text);  // $LASTEXITCODE 显式断言在位
    }

    private static string FindRepoRoot()
    {
        var dir = new DirectoryInfo(AppContext.BaseDirectory);
        while (dir is not null && !File.Exists(Path.Combine(dir.FullName, "CLAUDE.md")))
            dir = dir.Parent!;
        Assert.NotNull(dir);
        return dir!.FullName;
    }
}

namespace Aegis.Windows.Core.Tests;

using System;
using System.IO;
using System.Linq;
using Xunit;

/// <summary>R9-CS-1（第九轮 2026-10-10）：无痕窗 core-ready 接线段的**对偶锚**。
///
/// 主窗那段在 R8-CS-SEC-07 就包上了 `TabRuntimeLifetime.RunCoreReadyFailClosed`，
/// 而无痕窗仍是裸 lambda——逐行回读确证：`runtime.OnCoreReady(core)` 内的 broker
/// `RegisterSession` 在会话池满时抛 `InvalidOperationException`，这条回调又经
/// Dispatcher 派发（抛出无观察方）⇒ 留下「已挂载可见、却没接上策略处理器」的标签，
/// 会话还在池里。原测试只有主窗锚、没有无痕窗锚，所以这道缺口全绿存在了两轮。
///
/// 行为面（留痕码、拆除恰好一次、取标签 id 失败也留痕）由 `CoreReadyFailClosedTests`
/// 对纯函数核直测，本文件不重复；这里钉的是**接线形状**：包装必须在、早退语义必须保住、
/// 两段不能又长回一个文件里。反向锚用内存态字符串做——把包装删掉必须判红，
/// 否则这条锚和被它检查的缺陷一样是恒真的。</summary>
public sealed class InPrivateCoreReadyWiringTests
{
    private const string HostSource =
        "windows/src/Aegis.Windows.App/Chrome/InPrivateWindow.xaml.cs";
    private const string CoreReadySource =
        "windows/src/Aegis.Windows.App/Chrome/InPrivateWindow.CoreReady.cs";

    /// <summary>仓库根：向上找到 CLAUDE.md（与 CoreReadyFailClosedTests 同口径——固定
    /// `../..` 层数会被 `-r win-x64` 多出来的那层输出目录打回「找不到文件」）。</summary>
    private static string RepoRoot()
    {
        var dir = new DirectoryInfo(AppContext.BaseDirectory);
        while (dir is not null && !File.Exists(Path.Combine(dir.FullName, "CLAUDE.md")))
        {
            dir = dir.Parent;
        }

        return dir?.FullName ?? throw new DirectoryNotFoundException("找不到仓库根（CLAUDE.md）");
    }

    /// <summary>只取**非注释**行：形状锚不能把「注释里提到的旧写法」当成回归
    /// （第八轮 R8-CS-SEC 系列的教训——注记里写着旧形态，锚就恒真）。</summary>
    private static string Read(string relative) =>
        string.Join(
            '\n',
            File.ReadAllLines(Path.Combine(RepoRoot(), relative))
                .Where(line => !line.TrimStart().StartsWith("//", StringComparison.Ordinal)));

    /// <summary>判据本体：返回形状问题清单，空 = 通过。</summary>
    private static string[] Problems(string host, string coreReady)
    {
        var problems = new System.Collections.Generic.List<string>();
        if (!coreReady.Contains("TabRuntimeLifetime.RunCoreReadyFailClosed("))
            problems.Add("接线体未包失败闭合核（抛出无观察方 ⇒ 半接线标签 + 会话泄漏）");
        if (!coreReady.Contains("() => WireCoreReady(runtime, tab)"))
            problems.Add("失败闭合核包的必须是接线体本身（包成空 lambda 等于没有闭合）");
        if (!coreReady.Contains("() => _tabs.CloseTab(tab.TabId)"))
            problems.Add("拆除必须走完整关闭路径 TabManager.CloseTab（只收协调器会留死条目）");
        if (!coreReady.Contains("if (!e.IsSuccess)"))
            problems.Add("入口必须先判 SDK 成功——初始化失败时没有可接线的 core");
        if (!coreReady.Contains("if (_closed || !_runtimes.ContainsKey(tab.TabId))"))
            problems.Add("「窗口已关/标签已不在」的早退必须留在包装之前（否则会对不在的标签 CloseTab）");
        if (!coreReady.Contains("runtime.OnCoreReady(core);"))
            problems.Add("接线必须经 TabRuntime.OnCoreReady（broker 会话注册在这里）");
        if (host.Contains("runtime.OnCoreReady(core);"))
            problems.Add("接线体又长回宿主文件了——零余量基线会把它挤成内联形态，正是本缺陷的成因");
        if (!host.Contains("+= (_, e) => OnCoreReady(e, runtime, tab);"))
            problems.Add("宿主侧必须只留一行订阅（对偶锚的另一半：入口形状）");
        return problems.ToArray();
    }

    [Fact]
    public void InPrivateCoreReady_HasTheSameFailClosedShapeAsMainWindow()
    {
        Assert.Empty(Problems(Read(HostSource), Read(CoreReadySource)));
    }

    [Fact]
    public void RemovingTheWrapper_IsCaughtByTheAnchor()
    {
        var coreReady = Read(CoreReadySource)
            .Replace("TabRuntimeLifetime.RunCoreReadyFailClosed(", "/* 回退成内联形态 */ InvokeNothing(");
        Assert.Contains(
            Problems(Read(HostSource), coreReady),
            problem => problem.Contains("失败闭合"));
    }

    [Fact]
    public void MovingTheWiringBackIntoTheHost_IsCaughtByTheAnchor()
    {
        // 复现「接线体又长回宿主文件」：在宿主代码里追加一次真实调用（Read 已剔注释，
        // 所以只有真调用能触发这条锚——用注释复现就说明锚是假的）。
        var host = Read(HostSource) + "\n                runtime.OnCoreReady(core);\n";
        Assert.Contains(Problems(host, Read(CoreReadySource)), problem => problem.Contains("宿主文件"));
    }

    [Fact]
    public void TeardownMustGoThroughTheFullClosePath()
    {
        var coreReady = Read(CoreReadySource).Replace("() => _tabs.CloseTab(tab.TabId)", "() => _runtimeCoordinator.Close(tab.TabId)");
        Assert.Contains(
            Problems(Read(HostSource), coreReady),
            problem => problem.Contains("完整关闭路径"));
    }

    [Fact]
    public void BothWindowsNowShareOneFailClosedCore()
    {
        // 两窗都调同一个纯函数核——「同款」由单源保证，而不是两处各抄一份再靠测试比对。
        var main = Read("windows/src/Aegis.Windows.App/Chrome/MainWindow.Tabs.CoreReady.cs");
        Assert.Contains("TabRuntimeLifetime.RunCoreReadyFailClosed(", main);
        Assert.Equal(
            2,
            new[] { main, Read(CoreReadySource) }.Count(text => text.Contains("RunCoreReadyFailClosed(")));
    }
}

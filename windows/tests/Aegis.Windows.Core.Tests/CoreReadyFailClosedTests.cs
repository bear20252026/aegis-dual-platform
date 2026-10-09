namespace Aegis.Windows.Core.Tests;

using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using Aegis.Windows.Chrome;
using Xunit;

/// <summary>R8-CS-SEC-05 / R8-CS-SEC-07（第八轮 2026-10-08）：
/// document-ready 接线段的失败闭合核，与无痕窗横幅的收起写点。
///
/// 两条都是「回读确证后才登记」的项，各自的确证方式不同：
/// • CS-SEC-07 的抛出面在真机才可能出现（会话池满 / COM 退休），单测够不到 WebView2，
///   所以判定核做成纯函数直测（留痕码、拆除恰好一次、二次失败不重抛）；外迁本身
///   用形态锚钉住——写回内联形态即红。
/// • CS-SEC-05 的「横幅永不收起」是读出来的（本文件级事实：全文件只有一处
///   `ErrorPagePanel` 赋值且恒置 Visible），收起规则做成可断言的小方法。</summary>
public sealed class CoreReadyFailClosedTests : IDisposable
{
    private const string TabsSource =
        "windows/src/Aegis.Windows.App/Chrome/MainWindow.Tabs.cs";
    private const string CoreReadySource =
        "windows/src/Aegis.Windows.App/Chrome/MainWindow.Tabs.CoreReady.cs";
    private const string InPrivateSource =
        "windows/src/Aegis.Windows.App/Chrome/InPrivateWindow.xaml.cs";
    private const string InPrivateUiSource =
        "windows/src/Aegis.Windows.App/Chrome/InPrivateWindow.NavigationUi.cs";

    private readonly string _logDir =
        Path.Combine(Path.GetTempPath(), $"aegis_coreready_{Guid.NewGuid():N}");

    public CoreReadyFailClosedTests()
    {
        Directory.CreateDirectory(_logDir);
        Aegis.Windows.Core.Security.SecurityLog.SecurityLogDirOverride = _logDir;
    }

    public void Dispose()
    {
        Aegis.Windows.Core.Security.SecurityLog.SecurityLogDirOverride = null;
        try
        {
            Directory.Delete(_logDir, true);
        }
        catch (IOException)
        {
            // 临时目录被外部清走——测试自身已收尾，不影响判定
        }
    }

    private string LoggedText() =>
        string.Concat(Directory.GetFiles(_logDir).Select(File.ReadAllText));

    private static void Run(Action wire, Func<string> tabId, List<string> events) =>
        TabRuntimeLifetime.RunCoreReadyFailClosed(wire, tabId, () => events.Add("teardown"));

    // ===== 判定核的行为面 =====

    [Fact]
    public void SuccessfulWiring_TearsNothingDownAndLogsNothing()
    {
        // 反向控制：正常路径必须一行都不写、一次都不拆——否则这条修复本身
        // 就成了「每个新标签都被拆掉」的新缺陷。
        var events = new List<string>();
        Run(() => events.Add("wire"), () => "tab-ok", events);

        Assert.Equal(new[] { "wire" }, events);
        Assert.Empty(Directory.GetFiles(_logDir));
    }

    [Theory]
    [InlineData(nameof(InvalidOperationException))]
    [InlineData(nameof(NullReferenceException))]
    [InlineData(nameof(ObjectDisposedException))]
    [InlineData(nameof(KeyNotFoundException))]
    public void AnyWiringException_TearsTheTabDownExactlyOnce(string kind)
    {
        // 真实抛出面：OnCoreReady 内的 broker RegisterSession（会话池 1024 满即抛
        // InvalidOperationException）、COM/控件退休（ObjectDisposed）、NTP 桥依赖缺失。
        // KeyNotFoundException 顶替 COMException 一类：判定核判的是「任何抛出」。
        var events = new List<string>();
        void Wire()
        {
            events.Add("wire");
            throw kind switch
            {
                nameof(NullReferenceException) => new NullReferenceException(),
                nameof(ObjectDisposedException) => new ObjectDisposedException("CoreWebView2"),
                nameof(KeyNotFoundException) => new KeyNotFoundException("ntp 资源缺失"),
                _ => new InvalidOperationException("会话池已满"),
            };
        }

        Run(Wire, () => "tab-42", events);

        Assert.Equal(new[] { "wire", "teardown" }, events);
    }

    [Fact]
    public void WiringFailure_IsRecordedWithTheAuditCodeAndTabId()
    {
        var events = new List<string>();
        Run(() => throw new InvalidOperationException("RegisterSession 拒绝"),
            () => "tab-77", events);

        var text = LoggedText();
        Assert.Contains(TabRuntimeLifetime.CoreReadyErrorCode, text);
        Assert.Contains("core_ready_error", text);
        Assert.Contains("InvalidOperationException", text);
        Assert.Contains("tab-77", text);
    }

    [Fact]
    public void TeardownFailure_IsLoggedAndNeverRethrown()
    {
        // 二次失败面：拆除自己再抛也不能把异常送回 COM 事件——那正是本修复要消除的
        // 「冒到 Dispatcher 全局弹窗」。残余（标签可能存活）如实留痕，不假装拦住。
        var events = new List<string>();
        void Wire() => throw new InvalidOperationException("接线失败");

        TabRuntimeLifetime.RunCoreReadyFailClosed(
            Wire,
            () => "tab-9",
            () =>
            {
                events.Add("teardown-attempted");
                throw new ObjectDisposedException("CoreWebView2Controller");
            });

        Assert.Equal(new[] { "teardown-attempted" }, events);
        var text = LoggedText();
        Assert.Contains("core_ready_error", text);
        Assert.Contains(TabRuntimeLifetime.CoreReadyTeardownErrorCode, text);
        Assert.Contains("core_ready_teardown_failed", text);
    }

    [Fact]
    public void UnreadableTabId_StillTearsTheTabDown()
    {
        // 取标签 id 也可能抛（控件已退休）——那不该成为「既不留痕也不拆除」的理由。
        var events = new List<string>();
        Run(() => throw new InvalidOperationException("接线失败"),
            () => throw new NullReferenceException(), events);

        Assert.Equal(new[] { "teardown" }, events);
        var text = LoggedText();
        Assert.Contains("core_ready_error", text);
        Assert.Contains("<unavailable:NullReferenceException>", text);
    }

    // ===== 形态锚（行为不可达的部分；先剔注释 + 带正面控制） =====

    [Fact]
    public void RegistrationNoLongerCarriesTheInlineWiring()
    {
        var tabs = CodeOnly(TabsSource);
        Assert.Contains("CoreWebView2InitializationCompleted += (_, e) => OnCoreReady(e, runtime, tab);", tabs);
        // 旧内联形态必须已经离开这个文件（否则就是两份接线代码并存）
        Assert.DoesNotContain("NtpAssets.BindVirtualHosts(core)", tabs);
        Assert.DoesNotContain("runtime.OnCoreReady(core);", tabs);

        // 正面控制：同一条判据在目标文件里必须是「有」——不然上面两条
        // 只是因为文件读空了而恒真
        var moved = CodeOnly(CoreReadySource);
        Assert.Contains("NtpAssets.BindVirtualHosts(core)", moved);
        Assert.Contains("runtime.OnCoreReady(core);", moved);
    }

    [Fact]
    public void SdkFailureIsCheckedBeforeEnteringTheFailClosedCore()
    {
        var moved = CodeOnly(CoreReadySource);
        var guard = RequiredIndex(moved, "!e.IsSuccess");
        var core = RequiredIndex(moved, "TabRuntimeLifetime.RunCoreReadyFailClosed(");
        Assert.True(guard < core,
            "必须先判 SDK 初始化成功再进判定核——否则 !e.IsSuccess 分支里的失败会被当成接线异常处理");
        // 拆除必须走完整关闭路径（TabManager.CloseTab → TabClosed → OnTabClosed），
        // 只调协调器会留下「runtime 已销毁、标签还在条上」的死条目
        Assert.Contains("_tabs.CloseTab(tab.TabId)", moved);
        Assert.DoesNotContain("_runtimeCoordinator.Close(tab.TabId)", moved);
    }

    [Fact]
    public void InPrivateBannerHasACollapseWritePoint()
    {
        var main = CodeOnly(InPrivateSource);
        var ui = CodeOnly(InPrivateUiSource);
        Assert.Contains("DismissRejectionOnceNavigated(ok)", main);
        Assert.Contains("ErrorPagePanel.Visibility = Visibility.Collapsed;", ui);

        // 正面控制 + 规则边界：只在成功时收起，失败不把拒绝洗成静默
        Assert.Contains("ErrorPagePanel.Visibility = Visibility.Visible;", ui);
        Assert.Contains("if (navigationSucceeded)", ui);
    }

    /// <summary>读源码并剔注释行——修复说明里常逐字抄着被禁的旧形态，
    /// 不剔就是自己的注记把自己打红（第八轮两次实测撞到）。</summary>
    private static string CodeOnly(string relative) =>
        string.Join(
            "\n",
            File.ReadAllLines(Path.Combine(RepoRoot(), relative))
                .Where(line => !line.TrimStart().StartsWith("//", StringComparison.Ordinal)));

    private static int RequiredIndex(string code, string anchor)
    {
        var index = code.IndexOf(anchor, StringComparison.Ordinal);
        Assert.True(index >= 0, $"锚点缺失：{anchor}");
        return index;
    }

    private static string RepoRoot()
    {
        var dir = new DirectoryInfo(AppContext.BaseDirectory);
        while (dir is not null)
        {
            if (File.Exists(Path.Combine(dir.FullName, "CLAUDE.md")))
            {
                return dir.FullName;
            }

            dir = dir.Parent;
        }

        throw new DirectoryNotFoundException("未找到仓库根（CLAUDE.md）");
    }
}

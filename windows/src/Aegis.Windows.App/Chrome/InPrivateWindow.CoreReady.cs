namespace Aegis.Windows.Chrome;

using System;
using Aegis.Windows.Core.Tabs;
using Microsoft.Web.WebView2.Core;

/// <summary>
/// 无痕窗 document-ready（`CoreWebView2InitializationCompleted`）接线段（R9-CS-1，
/// 第九轮 2026-10-10）。逐行回读确证的缺口：主窗同一段在 R8-CS-SEC-07 已经包上
/// `TabRuntimeLifetime.RunCoreReadyFailClosed`，而这里仍是裸 lambda 体 ⇒ 一旦抛出
///（`runtime.OnCoreReady` 内的 broker `RegisterSession` 在会话池 1024 满时抛
/// `InvalidOperationException` 是现成路径）就留下「已挂载可见、却没接上策略处理器」的标签，
/// 且会话在池里泄漏；而该回调经 Dispatcher 派发，抛出**没有观察方**（只会被
/// `App.xaml.cs` 的 30 秒频控弹窗吞掉）。
///
/// 修法与主窗同形，且**不改既有早退语义**：
/// • `!e.IsSuccess` → 只留痕（没有可接线的 core，谈不上拆除）；
/// • `_closed || !_runtimes.ContainsKey` → 原样直接返回（标签已不在，CloseTab 反而是新副作用）；
/// • 其余接线整体交给 `RunCoreReadyFailClosed`：留痕 + 走 `TabManager.CloseTab` 的完整
///   关闭路径（触发 TabClosed ⇒ 收协调器与集合/地址栏）。原则与主窗一致：
///   **宁可少一个标签，不留一个不受策略保护的标签**。
///
/// 为什么外迁成新文件：`InPrivateWindow.xaml.cs` 在零余量行数基线上（只许减不许增），
/// 就地加包装必然增行——与 `MainWindow.Tabs.CoreReady.cs`（R8-CS-SEC-07）同一处置。
/// 接线体本身逐字搬移，只把 `tab`/`runtime` 从闭包捕获改成方法参数。
///
/// 行为面（留痕码、拆除恰好一次、取标签 id 失败也要留痕）由
/// `CoreReadyFailClosedTests` 对纯函数核直测；本文件侧的形状锚在
/// `InPrivateCoreReadyWiringTests`（缺包装即红）——两窗有**对偶锚**，不再是主窗独一份。
/// </summary>
public partial class InPrivateWindow
{
    /// <summary>初始化回调入口：SDK 侧失败与「标签已不在」只留痕/直接返回，
    /// 接线侧失败换成「留痕 + 拆除该标签」。</summary>
    private void OnCoreReady(
        CoreWebView2InitializationCompletedEventArgs e, TabRuntime runtime, Tab tab)
    {
        // CS-358（2026-10-01 审计）：初始化失败留痕（主窗同分支有
        // SecurityLog——此前无痕窗口静默空白不可诊断）
        if (!e.IsSuccess)
        {
            Core.Security.SecurityLog.Write(
                $"[inprivate] 标签 {tab.TabId} WebView2 初始化失败: {e.InitializationException?.Message ?? "e.IsSuccess=false（未知原因）"}");
            return;
        }

        if (_closed || !_runtimes.ContainsKey(tab.TabId))
            return;

        TabRuntimeLifetime.RunCoreReadyFailClosed(
            () => WireCoreReady(runtime, tab),
            () => tab.TabId,
            () => _tabs.CloseTab(tab.TabId));
    }

    /// <summary>接线体，自 `InPrivateWindow.xaml.cs` 的初始化回调逐字搬入。</summary>
    private void WireCoreReady(TabRuntime runtime, Tab tab)
    {
        var core = runtime.Control.CoreWebView2;
        Ntp.NtpAssets.BindVirtualHosts(core);
        runtime.OnCoreReady(core);
        // CS-281：此订阅为每标签一次性初始化回调，生命周期与 runtime
        // 对象一致（随 runtime 释放整体回收）——无需显式退订
        WireNtpBridge(runtime, core);
        if (Ntp.NtpAssets.IsVirtualHostUrl(tab.Url))
        {
            // 延迟导航（映射传播等待+失败重试）同样复用协调器——
            // 执行前重新校验 runtime 引用/令牌/窗口存活
            _runtimeCoordinator.PostDelayedNavigation(
                tab.TabId, tab.Url, () => !_closed && IsLoaded);
        }
        else
        {
            TabRuntime.Navigate(runtime, tab.Url);
        }
    }
}

namespace Aegis.Windows.Chrome;

using System;
using Aegis.Windows.Core.Tabs;
using Microsoft.Web.WebView2.Core;

/// <summary>
/// document-ready（`CoreWebView2InitializationCompleted`）接线段（R8-CS-SEC-07，
/// 第八轮 2026-10-08）。整段自 `MainWindow.Tabs.cs` **逐字外迁**——只做了统一
/// 减 4 空格的缩进平移，语句与注释一字未改；外迁的直接原因是那里在 423 行
/// 零余量基线上，而这条回调必须包上失败闭合（先净减 60 行才放得下判定入口）。
///
/// 为什么原来必须有 try：`BindVirtualHosts` / `runtime.OnCoreReady`（内含 broker
/// `RegisterSession`，会话池 1024 满即抛 `InvalidOperationException`）/ 首次
/// `Navigate` / `CreateNtpBridge` 全在 WebView2 初始化回调里执行，而
/// `TabRuntimeLifetime.InitializeAsync` 只观察 `Runtime.InitAsync()` 的异常 ⇒
/// **这条回调的抛出没有观察方**，此前一路冒到 Dispatcher 的全局未处理异常弹窗
/// （`App.xaml.cs` 30s 频控后静默），留下「一个能显示、却没接上策略处理器的标签」，
/// 且 `IsWired` 可能已半置位（R7-CS1-06 同族）。
///
/// 失败闭合判据单源在 `TabRuntimeLifetime.RunCoreReadyFailClosed`（纯函数，行为面由
/// `CoreReadyFailClosedTests` 直测：留痕码、拆除恰好一次、取标签 id 失败也要留痕）。
/// 本文件另留一条形态锚：注册点必须走 `OnCoreReady`，且入口必须先判 SDK 成功再进
/// 判定核——写回内联形态即红。
/// </summary>
public partial class MainWindow
{
    /// <summary>初始化回调入口：SDK 侧失败只留痕（没有可接线的 core），
    /// 接线侧失败换成「留痕 + 拆除该标签」。</summary>
    private void OnCoreReady(
        CoreWebView2InitializationCompletedEventArgs e, TabRuntime runtime, Tab tab)
    {
                if (!e.IsSuccess)
                {
                    Core.Security.SecurityLog.Write(
                        $"[init] 标签 {tab.TabId} 初始化失败: {e.InitializationException?.Message ?? "e.IsSuccess=false（未知原因）"}");
                    return;
                }

        TabRuntimeLifetime.RunCoreReadyFailClosed(
            () => WireCoreReady(runtime, tab),
            () => tab.TabId,
            // 拆除必须走**完整**关闭路径：TabManager.CloseTab 会触发 TabClosed，
            // 由 OnTabClosed 收协调器（runtime 销毁）+ 集合/地址栏更新。
            // 只调 _runtimeCoordinator.Close 会留下「runtime 已销毁、标签还在条上」
            // 的死条目——那比半接线标签更难理解。原则：宁可少一个标签，
            // 不留一个不受策略保护的标签。
            () => _tabs.CloseTab(tab.TabId));
    }

    /// <summary>原回调体，逐字搬入（缩进整体减 4）。</summary>
    private void WireCoreReady(TabRuntime runtime, Tab tab)
    {
                var core = runtime.Control.CoreWebView2;
                Ntp.NtpAssets.BindVirtualHosts(core);
                runtime.OnCoreReady(core);
                // 虚拟主机地址（NTP/画板）：映射就绪后才导航，且**推迟到下一
                // Dispatcher 周期**——同一调用栈里 SetVirtualHostNameToFolderMapping
                // 后立即导航会因映射尚未传播到渲染进程而 ConnectionAborted
                //（实机复现：点主页能渲染、初始化时同步导航即 abort）。推迟后
                // 与「点主页成功」路径一致。
                if (Chrome.Ntp.NtpAssets.IsVirtualHostUrl(tab.Url))
                {
                    // 经协调器延迟导航：执行前重新校验 runtime 引用/令牌/窗口状态，
                    // 避免在已释放控件上设 Source 抛异常（「新建标签删不掉」防护）。
                    _runtimeCoordinator.PostDelayedNavigation(tab.TabId, tab.Url, () => IsLoaded);
                }
                else
                {
                    // 普通站点：初始化（含虚拟主机映射）就绪后立即导航。
                    // 修复：此前用 else if (!_restoring) 导致会话恢复时普通标签
                    // 初始化后不导航（停留在空标签）——恢复与否都应导航。
                    TabRuntime.Navigate(runtime, tab.Url);
                }
                // M3 新标签页宿主桥：通道绑定到受信 NTP **顶层文档**——远程页面
                // per-origin 关闭 WebMessage，且本桥要求顶层来源就是 ntp.aegis.local
                //（内嵌 iframe 伪装 ntp 来源的请求在顶层门禁处拒绝——ADR-003 无桥
                // 保证的纵深防御）；导航意图回归 NavigationStarting→broker 唯一路径
                var ntp = CreateNtpBridge(runtime);
                core.WebMessageReceived += (_, ev) =>
                {
                    // 顶层文档（core.Source）必须是 NTP 虚拟主机；发送来源（ev.Source）
                    // 由 NtpBridge 二次校验。二者任一不符即静默忽略——帧内嵌不可达。
                    if (!Ntp.NtpAssets.IsTopLevelNtpDocument(core))
                        return;
                    try
                    {
                        ntp.TryHandle(
                            ev.Source, ev.WebMessageAsJson,
                            result =>
                            {
                                // restoreSession 会同步拆除当前标签（含发送标签）——
                                // core 可能已被释放；响应注入必须容错，绝不抛未处理异常
                                try
                                {
                                    core.PostWebMessageAsJson(
                                        System.Text.Json.JsonSerializer.Serialize(result));
                                }
                                catch (Exception)
                                {
                                    // 发送标签已随会话重建销毁——响应无处可达，静默丢弃
                                }
                            },
                            // CS-031：导入 I/O 移出 UI 线程，完成后回投 UI 线程注入响应
                            action => Dispatcher.BeginInvoke(action));
                    }
                    catch (Exception ex)
                    {
                        // 桥内服务（书签/历史 SQLite、导入）异常不得沿 WebMessageReceived
                        // 冒泡成全局未处理异常弹窗——记录后吞掉
                        Core.Security.SecurityLog.Write(
                            $"[ntp] 桥处理异常: {ex.GetType().Name}: {ex.Message}");
                    }
                };
    }
}

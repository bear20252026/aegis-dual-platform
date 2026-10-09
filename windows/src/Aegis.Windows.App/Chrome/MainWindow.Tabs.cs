namespace Aegis.Windows.Chrome;

using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Threading.Tasks;
using System.Windows;
using System.Windows.Input;
using Aegis.Windows.Broker;
using Aegis.Windows.Core;
using Aegis.Windows.Core.Bookmarks;
using Aegis.Windows.Core.History;
using Aegis.Windows.Core.Security;
using Aegis.Windows.Core.Settings;
using Aegis.Windows.Core.Tabs;
using Microsoft.Web.WebView2.Core;

// CS-377（2026-10-02 审计）：MainWindow 上帝文件拆分（1424 行→每文件 ≤500）
// ——本文件为 partial 扩展：纯代码移动，零行为变化（WindowSharedChrome.cs
//  同款先例）。职责：标签生命周期与标签条交互（CreateRuntime 事件接线/切换/导航完成/睡眠唤醒/拖拽排序）
public partial class MainWindow
{
    // ================= 标签生命周期（TabManager 事件 → runtime 管理） =================

    /// <summary>创建标签的 UI 运行时并挂入容器（不激活——激活由 TabSwitched 统一）。</summary>
    private void OnTabOpened(Tab tab) => CreateRuntime(tab, tab.Url);

    private void CreateRuntime(Tab tab, string initialUrl)
    {
        // 日志脱敏：不落 query（token/搜索词）。
        // CS-325（2026-09-26 审计）：改调 UrlRedactor.Redact 单源——此前内联
        // 手写同形逻辑且回退分支缺 256 截断（双源漂移面）
        Core.Security.SecurityLog.Write(
            $"[tab] 创建标签 {tab.TabId} url={Core.Security.UrlRedactor.Redact(initialUrl)}");
        var runtime = _runtimeCoordinator.Create(_broker, tab).Runtime;
        // R8-CS-SEC-07（第八轮 2026-10-08）：接线段整段外迁到 MainWindow.Tabs.CoreReady.cs
        // 并包上失败闭合——此前这条回调的抛出没有观察方，现场只留一个未接线的标签。
        runtime.Control.CoreWebView2InitializationCompleted += (_, e) => OnCoreReady(e, runtime, tab);
        runtime.NavigationCompleted += (ok, status) => OnTabNavigationCompleted(tab.TabId, ok, status);
        // M4 下载管理面板：授权通过的 DownloadOperation 注入共享数据源
        // CS-260：与初始化/导入路径统一为 BeginInvoke——WebView2 事件线程
        // 不应被 UI 线程任务同步阻塞
        // CS-344（2026-10-01 审计）：终态持久化（含 URL 落 downloads.db）随
        // DownloadRecordStore 一并移除——All() 零生产调用（重启后无消费面），
        // 带 token 的 URL 无收益常驻磁盘；会话内管理由 _downloads + CS-333 有界
        runtime.DownloadOperationStarted += (operation, dangerous) => Dispatcher.BeginInvoke(() =>
        {
            var item = new Core.Downloads.DownloadItem(
                operation,
                System.IO.Path.GetFileName(operation.ResultFilePath ?? string.Empty),
                operation.Uri ?? string.Empty,
                dangerous);
            _downloads.Insert(0, item);
            TrimDownloadItems();
        });
        // M1 加载指示接线：导航开始显示不定态条，完成/失败隐藏
        runtime.NavigationStarted += () =>
        {
            if (tab.TabId == _activeTabId)
                LoadingBar.Visibility = Visibility.Visible;
        };
        runtime.Host.NavigationConfirmationRequested += (_, e) => _approval.Request(tab.TabId, e);
        runtime.Host.NavigationConfirmationResolved += (_, _) => _approval.Resolved();
        // CS-355（2026-10-01 审计）：策略拒绝原因可见——broker 的 DenyReason
        // 此前在 HostWebView 内被丢弃（导航只是"无反应"）；记录待
        // NavigationCompleted(OperationCanceled) 分支呈现（该分支此前把错误页
        // 一律收起——拒绝零可见反馈）
        // CS-386（2026-10-02 审计）：按 tabId 存取——呈现与清除限定同标签
        runtime.NavigationDenied += message =>
        {
            _pendingDenyMessages[tab.TabId] = message;
            if (tab.TabId == _activeTabId)
                ShowRejection(message);
        };
        // target=_blank / window.open 链接：不再静默丢弃，改为验证地址后
        // 在当前窗口新建标签打开（对齐主流浏览器）。放行面 = 保留地址边界
        // 之外（R8-CS-SEC-06 与第七轮 B8 裁决合一：本机与内网必须能打开，
        // 故 192.168/10/172.16 与 my-nas.local 这类目标不再被该通道拒）。
        runtime.NewWindowRequested += targetUrl =>
        {
            if (!Core.UrlSafety.CanOpenHttpUrl(targetUrl))
            {
                ShowFeedback("已拒绝打开该链接（链路本地/云元数据/保留地址）", isWarning: true);
                return;
            }
            _tabs.NewTab(targetUrl);
        };
        // M3 危险扩展下载确认（审计补缺——此前 DownloadConfirmationRequested
        // 全仓零订阅者 → 危险下载恒被静默拒绝，该功能形同虚设）。用户显式
        // 确认才放行；窗口已关闭/异常仍 fail-closed 拒绝。
        // CS-370（2026-10-01 审计）：确认对话框单源到 WindowSharedChrome
        //（与无痕窗共用——此前两窗各持一份同形 MessageBox）
        runtime.DownloadConfirmationRequested += (downloadUrl, fileName) =>
            WindowSharedChrome.ConfirmDangerousDownload(this, downloadUrl, fileName);
        // 视觉树挂载 + 初始化统一由协调器驱动（Create 已完成两者——
        // 显式初始化含安全 DNS 等参数，完成后触发 CoreWebView2InitializationCompleted，
        // 上方处理器负责映射+导航）。
    }

    /// <summary>M3：虚拟主机资源映射与 NTP 顶层文档门禁统一在 NtpAssets
    ///（主窗口与无痕窗口共用单源——此前两份逐行复制漂移）。</summary>

    /// <summary>M3：新标签页宿主桥组装（逻辑在 NtpBridgeFactory——上帝对象
    /// 拆分第二批；保留薄转发以维持 CreateRuntime 内单一装配点）。</summary>
    private Chrome.Ntp.NtpBridge CreateNtpBridge(TabRuntime runtime) =>
        _ntpBridgeFactory.Create(runtime);

    /// <summary>CS-333：下载集合有界——超阈值自尾部移除最早的非进行中条目
    ///（进行中保留；条目持有的原生操作对象随之释放）。</summary>
    private void TrimDownloadItems()
    {
        for (var i = _downloads.Count - 1; i >= 0 && _downloads.Count > MaxDownloadItems; i--)
        {
            if (_downloads[i].StateKind != Core.Downloads.DownloadItemState.InProgress)
                _downloads.RemoveAt(i);
        }
    }

    private void OnTabClosed(string tabId)
    {
        _runtimeCoordinator.Close(tabId);
        // CS-386：随标签销毁清掉其待呈现拒绝槽位（不再驻留增长）
        _pendingDenyMessages.Remove(tabId);
        SaveSession();
        // CS-393（2026-10-02 审计）：关掉最后一个标签（CloseTab 返回 null——
        // 集合已空）后窗口滞留空壳——用户显式关最后一个标签即关窗；会话重建期
        //（RestoreSavedSession 先清后建）瞬时空集不触发（_restoringSession 守卫）
        if (_tabs.Tabs.Count == 0 && !_restoringSession)
            Close();
    }

    private void OnTabSwitched(Tab tab)
    {
        var previousId = _activeTabId;
        _activeTabId = tab.TabId;
        tab.LastActivated = DateTime.Now;
        if (tab.IsSleeping)
            WakeTab(tab);  // 睡眠标签激活 → 复活（重建 WebView 实例）
        // CS-257：仅翻转旧/新两个 runtime——此前每次切换遍历全部 runtime
        // 重设四属性（10+ 标签时纯开销）。WebView2 是 HWND 承载控件：仅切
        // Visibility 在部分 WPF 版本中不足以刷新层级，显式控制 Z 序、命中
        // 测试和可见性（ApprovalOverlay 的 Z=10 仍保持最顶层）。
        foreach (var id in new[] { previousId, tab.TabId })
        {
            if (id is null || !_runtimes.TryGetValue(id, out var runtime))
                continue;
            // CS-371：四属性翻转单源（与无痕窗共用——此前两份同形副本）
            WindowSharedChrome.ApplyTabVisibility(runtime.Control, id == _activeTabId);
        }
        WebViewHost.UpdateLayout();
        SyncAddressBar(tab.Url);
        // CS-283：SelectionChanged 回调同步抛出时抑制标志必须复位——finally 包裹
        _suppressTabSelection = true;
        try
        {
            TabStrip.SelectedItem = tab;
        }
        finally
        {
            _suppressTabSelection = false;
        }
    }

    private void OnTabNavigationCompleted(string tabId, bool isSuccess, CoreWebView2WebErrorStatus status)
    {
        var tab = _tabs.Tabs.FirstOrDefault(t => t.TabId == tabId);
        if (tab is null)
            return;
        var isActive = tabId == _activeTabId;
        // NTP 虚拟主机映射传播期间可能先收到 ConnectionAborted；协调器已
        // 注册有界重试。不要把这个内部瞬态失败渲染成错误页，否则用户会先
        // 看到乱码/错误文档，随后才跳回主页面。
        if (isActive && !isSuccess
            && Ntp.NtpAssets.IsVirtualHostUrl(tab.Url)
            && status == CoreWebView2WebErrorStatus.ConnectionAborted)
        {
            LoadingBar.Visibility = Visibility.Visible;
            ErrorPagePanel.Visibility = Visibility.Collapsed;
            return;
        }
        if (isActive && !isSuccess && status != CoreWebView2WebErrorStatus.OperationCanceled)
        {
            ErrorPage.Text = $"导航失败：{status}（已拒绝/无法加载）";
            ErrorPagePanel.Visibility = Visibility.Visible;
        }
        else if (isActive)
        {
            // CS-355：策略拒绝的取消导航（OperationCanceled）此前直接收起错误
            // 页——拒绝原因零可见反馈；有待呈现的拒绝说明时改呈现之
            // CS-386：呈现限定本标签的待呈现拒绝（不再消费其它标签的槽位）
            if (!isSuccess && status == CoreWebView2WebErrorStatus.OperationCanceled
                && _pendingDenyMessages.TryGetValue(tabId, out var deny))
            {
                ShowRejection(deny);
            }
            else
            {
                ErrorPagePanel.Visibility = Visibility.Collapsed;
            }
        }
        // CS-386：清除同样限定本标签（其它标签的待呈现拒绝不被误清）
        _pendingDenyMessages.Remove(tabId);
        if (isActive)
        {
            LoadingBar.Visibility = Visibility.Collapsed;
            SyncAddressBar(tab.Url);
        }
        // 浏览历史记录（M2 缺口修复——此前仅导入写入，浏览从未落库）：
        // 成功导航 + 历史开关开 + 非内部页（首页/画板/空白页——避免「历史
        // 全被首页占满」）。后台标签完成导航同样记录。
        if (isSuccess && _settings.HistoryEnabled
            && Core.History.HistoryRecorder.IsRecordableUrl(tab.Url))
        {
            // CS-299（2026-09-26 审计）：历史写入移出 UI 线程——_history.Add
            // 每次新建 SQLite 连接+INSERT+周期修剪，此前在导航完成的 UI 线程
            // 同步执行（与 CS-031/159 "IO 移出 UI 线程" 口径相悖）。链式追加
            // 保证写入顺序（同标签快速连续导航时 visited_at 不逆序）；异常在
            // HistoryStore.Add 内部已吞（不向 ContinueWith 链传播）
            var url = tab.Url;
            var title = tab.Title;
            _historyWriteTail = _historyWriteTail.ContinueWith(
                _ => _history.Add(url, title));
        }
        // 每次导航完成即落盘（对齐 Python 栈崩溃恢复能力——强杀/崩溃后
        // 重启仍可恢复到最后的页面集合，而非仅正常关闭时的快照）
        SaveSession();
    }

    /// <summary>虚拟主机首帧有界重试耗尽（协调器事件）：停止加载条并展示明确
    /// 错误——瞬态抑制只针对映射传播期，重试放弃后必须让用户可见失败。</summary>
    private void OnNtpNavigationFailed(string tabId, CoreWebView2WebErrorStatus status)
    {
        if (tabId != _activeTabId)
            return;  // 仅对激活标签反映 UI 状态
        LoadingBar.Visibility = Visibility.Collapsed;
        ErrorPage.Text = $"首页资源加载失败：{status}（已重试，无法加载）";
        ErrorPagePanel.Visibility = Visibility.Visible;
    }

    // ================= 标签条交互 =================

    private void NewTab_Click(object sender, RoutedEventArgs e) => _tabs.NewTab(HomeUrl);

    private void TabClose_Click(object sender, RoutedEventArgs e)
    {
        // tabId 来源：优先按钮 Tag（="{Binding TabId}"）；Tag 未命中时回退到
        // 按钮 DataContext（列表项即 Tab），两者兼取保证关闭可靠触发
        if (sender is not System.Windows.FrameworkElement fe)
            return;
        var tabId = fe.Tag as string
            ?? (fe.DataContext as Core.Tabs.Tab)?.TabId;
        // CS-411（2026-10-02 审计）：守卫单源化到 WindowSharedChrome.CloseTabSafely
        //（SecurityLog 留痕 + try/catch 不阻断——与无痕窗共用）
        WindowSharedChrome.CloseTabSafely(_tabs, tabId);
    }

    private void TabStrip_SelectionChanged(object sender, System.Windows.Controls.SelectionChangedEventArgs e)
    {
        if (_suppressTabSelection)
            return;
        if (TabStrip.SelectedItem is Core.Tabs.Tab tab)
            _tabs.SwitchTo(tab.TabId);
    }

    /// <summary>显式标签点击切换（兜底）：自定义 ListBoxItem 模板里同时有
    /// 关闭按钮与 DockPanel 子元素，部分环境下仅靠 SelectionChanged 的
    /// 隐式命中可能失效（表现为「新建了标签但点击切不过去」）。此处直接
    /// 命中标签项即切换，命中关闭按钮则交给其自身的 Click（不动手切换）。</summary>
    private void TabStrip_PreviewMouseLeftButtonDown(object sender, MouseButtonEventArgs e)
    {
        // 记录按下起点——拖拽需超过阈值移动才判定为拖拽（防误触发吞点击）
        _tabDrag.RecordDragStart(e.GetPosition(TabStrip));
        if (TabStrip.InputHitTest(e.GetPosition(TabStrip)) is not DependencyObject hit)
            return;
        var node = hit;
        while (node is not null && node is not System.Windows.Controls.ListBoxItem)
            node = System.Windows.Media.VisualTreeHelper.GetParent(node);
        if (node is not System.Windows.Controls.ListBoxItem item
            || item.DataContext is not Core.Tabs.Tab tab)
            return;
        // 命中关闭按钮（✕）→ 让按钮自己的 Click 处理关闭，不在此切换
        var probe = hit;
        while (probe is not null)
        {
            if (probe is System.Windows.Controls.Button button && ReferenceEquals(button.Tag, tab.TabId))
                return;
            probe = System.Windows.Media.VisualTreeHelper.GetParent(probe);
        }
        _tabs.SwitchTo(tab.TabId);
    }



    private TabRuntime? ActiveRuntime() =>
        _activeTabId is not null && _runtimes.TryGetValue(_activeTabId, out var r) ? r : null;

    private void ZoomActive(double delta)
    {
        var rt = ActiveRuntime();
        if (rt?.Control.CoreWebView2 is null)
            return;
        var host = Uri.TryCreate(rt.Control.CoreWebView2.Source, UriKind.Absolute, out var u)
            ? u.Host : null;
        // 与 ZoomStore/设置归一同口径（clamp 边界在 ZoomPolicy——上帝对象拆分·第七批）
        var z = ZoomPolicy.ApplyStep(rt.Control.ZoomFactor, delta);
        rt.Control.ZoomFactor = z;
        if (host is not null)
            Core.Tabs.ZoomStore.Set(host, z);
    }

    private void SleepCheck()
    {
        var minutes = _settings.SleepMinutes;
        if (minutes <= 0 || _activeTabId is null)
            return;
        foreach (var tab in TabSleepPolicy.SelectTabsToSleep(
                     _tabs.Tabs, _activeTabId, minutes, DateTime.Now,
                     tabId => _runtimes.ContainsKey(tabId)))
        {
            _runtimeCoordinator.Sleep(tab.TabId);
            tab.IsSleeping = true;
        }
    }

    private void WakeTab(Tab tab)
    {
        if (_runtimes.ContainsKey(tab.TabId))
            return;
        tab.IsSleeping = false;
        CreateRuntime(tab, tab.Url);
    }

    private Core.Tabs.Tab? TabItemAt(System.Windows.Point p)
    {
        var element = TabStrip.InputHitTest(p) as DependencyObject;
        while (element is not null && element is not System.Windows.Controls.ListBoxItem)
            element = System.Windows.Media.VisualTreeHelper.GetParent(element);
        return (element as System.Windows.Controls.ListBoxItem)?.DataContext as Core.Tabs.Tab;
    }

    // ================= M1 标签条拖拽排序（逻辑在 TabStripDragController） =================

    private void TabStrip_PreviewMouseMove(object sender, MouseEventArgs e) =>
        _tabDrag.HandlePreviewMouseMove(e);

    private void TabStrip_DragOver(object sender, DragEventArgs e) =>
        _tabDrag.HandleDragOver(e);

    private void TabStrip_Drop(object sender, DragEventArgs e) =>
        _tabDrag.HandleDrop(e);


}

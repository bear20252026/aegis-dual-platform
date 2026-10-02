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
//  同款先例）。职责：源码查看器（共享抓取客户端 + Ctrl+U 后台抓取编排）
public partial class MainWindow
{
    // CS-064：源码抓取共享客户端（连接池 5 分钟回收——DNS 变更可感知）
    private static readonly System.Net.Http.HttpClient SourceFetchClient = CreateSourceFetchClient();

    private static System.Net.Http.HttpClient CreateSourceFetchClient()
    {
        var client = new System.Net.Http.HttpClient(
            new System.Net.Http.SocketsHttpHandler { PooledConnectionLifetime = TimeSpan.FromMinutes(5) })
        {
            Timeout = TimeSpan.FromSeconds(SourceFetchTimeoutSec),
        };
        client.DefaultRequestHeaders.UserAgent.ParseAdd("Mozilla/5.0 (AegisBrowser-SourceViewer)");
        return client;
    }

    private const int SourceFetchTimeoutSec = 15;     // 源码查看抓取超时
    private const int SourceMaxBytes = 5 * 1024 * 1024; // 源码查看大小上限

    /// <summary>M3 源码查看器（Ctrl+U）：后台线程抓取当前页（15s/5MB 上限），
    /// 全转义纯文本展示于独立窗口——查看源码永不等于执行源码
    /// （Python api_bridge.view_source 语义移植）。</summary>
    private void OpenSourceViewer()
    {
        var tab = _tabs.Current;
        if (tab is null
            || !Uri.TryCreate(tab.Url, UriKind.Absolute, out var uri)
            || (uri.Scheme != Uri.UriSchemeHttp && uri.Scheme != Uri.UriSchemeHttps))
        {
            ShowFeedback("当前页面不支持查看源代码（仅限 http/https）", isWarning: true);
            return;
        }
        // CS-229：虚拟主机 URL 在 WebView 外不可解析——后台抓源必失败，
        // 前置拦截并提示（不再让用户等 15s 超时后看失败反馈）
        if (Ntp.NtpAssets.IsVirtualHostUrl(tab.Url))
        {
            ShowFeedback("内部页面不支持查看源代码", isWarning: true);
            return;
        }
        var url = tab.Url;
        ShowFeedback("正在获取页面源代码…");
        Task.Run(async () =>
        {
            try
            {
                // CS-064（审计 2026-09-25）：静态共享客户端——此前每次查看源码
                // new HttpClient（SocketException 端口耗尽经典面）
                using var response = await SourceFetchClient.GetAsync(url);
                response.EnsureSuccessStatusCode();
                var bytes = await response.Content.ReadAsByteArrayAsync();
                if (bytes.Length > SourceMaxBytes)
                    throw new InvalidOperationException("源码超过 5MB 上限");
                var text = System.Text.Encoding.UTF8.GetString(bytes);
                Dispatcher.Invoke(() =>
                {
                    // 抓取期间主窗口可能已关闭——Owner=已关闭窗口会抛异常
                    if (!IsLoaded)
                        return;
                    var viewer = new SourceViewerWindow(url, text) { Owner = this };
                    viewer.ApplyTheme(_settings.Theme);
                    _sourceViewerWindows.RemoveAll(w => !w.IsLoaded);
                    _sourceViewerWindows.Add(viewer);
                    viewer.Show();
                    ShowFeedback("源码已加载（全转义，零脚本执行）");
                });
            }
            catch (Exception ex)
            {
                // CS-154：失败分支同样守卫 IsLoaded——抓取期间窗口关闭时
                // ShowFeedback 触碰已卸载控件会抛（成功分支已有守卫）
                Dispatcher.Invoke(() =>
                {
                    if (!IsLoaded)
                        return;
                    ShowFeedback($"获取源码失败：{ex.Message}", isWarning: true);
                });
            }
        });
    }

}

namespace Aegis.Windows.Chrome;

using System;
using System.Collections.ObjectModel;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Threading;
using Aegis.Windows.Core.Downloads;

/// <summary>下载管理面板（M4——ADR-009 D3：pywebview 天花板特性的完整原生
/// 兑现）。条目数据 = DownloadItem（INPC）；进度经 DispatcherTimer 轮询原生
/// DownloadOperation.Progress（500ms）。暂停/恢复/取消/打开文件夹全部为
/// 受信 chrome 按钮直达原生 API——远程页面无任何触达通道（ADR-003）。</summary>
public partial class DownloadsWindow : Window
{
    private readonly DispatcherTimer _timer;

    public DownloadsWindow(ObservableCollection<DownloadItem> items)
    {
        InitializeComponent();
        DownloadsList.ItemsSource = items;
        _timer = new DispatcherTimer(DispatcherPriority.Background)
        {
            Interval = TimeSpan.FromMilliseconds(500),
        };
        _timer.Tick += (_, _) => RefreshAll();
        _timer.Start();
        // CS-171：隐藏时暂停轮询、显示时恢复——此前窗口隐藏后仍每 500ms 空转
        IsVisibleChanged += (_, e) =>
        {
            if ((bool)e.NewValue)
                _timer.Start();
            else
                _timer.Stop();
        };
        Closed += (_, _) => _timer.Stop();
    }

    /// <summary>主窗口主题联动（浅色模式下不再永远深色）。</summary>
    public void ApplyTheme(string? theme) => WindowTheme.Apply(this, theme);

    private void RefreshAll()
    {
        if (DownloadsList.ItemsSource is not ObservableCollection<DownloadItem> items)
            return;
        // CS-170：索引 for 迭代——此前 ToList() 每 500ms 全表复制
        for (var i = 0; i < items.Count; i++)
            items[i].Refresh();
    }

    /// <summary>CS-174：清空列表——只移除已完成/已取消/已中断条目（进行中
    /// 保留；不删除已落盘文件）。</summary>
    private void ClearList_Click(object sender, RoutedEventArgs e)
    {
        if (DownloadsList.ItemsSource is not ObservableCollection<DownloadItem> items || items.Count == 0)
            return;
        var confirmed = MessageBox.Show(this, "从列表移除已完成/已取消/已中断的条目（不删除已下载文件）？",
            "清空列表", MessageBoxButton.YesNo, MessageBoxImage.Question);
        if (confirmed != MessageBoxResult.Yes)
            return;
        for (var i = items.Count - 1; i >= 0; i--)
        {
            if (items[i].StateKind != DownloadItemState.InProgress)
                items.RemoveAt(i);
        }
    }

    private static DownloadItem? ItemOf(object sender) =>
        (sender as FrameworkElement)?.DataContext as DownloadItem;

    private void Pause_Click(object sender, RoutedEventArgs e) => ItemOf(sender)?.Pause();

    private void Resume_Click(object sender, RoutedEventArgs e) => ItemOf(sender)?.Resume();

    private void Cancel_Click(object sender, RoutedEventArgs e) => ItemOf(sender)?.Cancel();

    /// <summary>打开下载所在文件夹（explorer /select——受信 chrome 本地能力，
    /// 仅打开系统文件管理器定位文件，不执行文件本身）。</summary>
    private void OpenFile_Click(object sender, RoutedEventArgs e)
    {
        if (sender is FrameworkElement { DataContext: DownloadItem item })
        {
            // CS-172：危险扩展条目打开前二次确认（此前经确认下载后可直接执行）
            if (item.Dangerous
                && MessageBox.Show(this, $"「{item.FileName}」为危险扩展文件，打开可能运行程序。确定打开？",
                    "危险文件", MessageBoxButton.YesNo, MessageBoxImage.Warning) != MessageBoxResult.Yes)
                return;
            var path = item.FilePath;
            if (string.IsNullOrEmpty(path) || !File.Exists(path))
            {
                MessageBox.Show(this, "文件尚未下载完成或已移动。", "打开文件",
                    MessageBoxButton.OK, MessageBoxImage.Information);
                return;
            }
            try
            {
                System.Diagnostics.Process.Start(new System.Diagnostics.ProcessStartInfo(path)
                {
                    UseShellExecute = true,
                });
            }
            catch (Exception ex)
            {
                MessageBox.Show(this, $"无法打开文件: {ex.Message}", "错误",
                    MessageBoxButton.OK, MessageBoxImage.Error);
            }
        }
    }

    private void ShowInFolder_Click(object sender, RoutedEventArgs e)
    {
        if ((sender as FrameworkElement)?.DataContext is not DownloadItem item)
            return;
        string? path = null;
        try
        {
            path = item.Operation.ResultFilePath;
        }
        catch (Exception)
        {
            // 元数据不可读——降级为反馈缺失
        }
        if (string.IsNullOrWhiteSpace(path) || !File.Exists(path))
        {
            MessageBox.Show(this, "下载文件尚未就绪或已移动。", "打开文件夹",
                MessageBoxButton.OK, MessageBoxImage.Information);
            return;
        }
        try
        {
            // CS-173：ArgumentList 传参——此前手工拼引号转义串（引号注入面）；
            // 参数边界由进程 API 负责
            var psi = new System.Diagnostics.ProcessStartInfo("explorer.exe")
            {
                UseShellExecute = false,
            };
            psi.ArgumentList.Add("/select," + path);
            Process.Start(psi);
        }
        catch (Exception ex)
        {
            MessageBox.Show(this, $"无法打开文件夹: {ex.Message}", "错误",
                MessageBoxButton.OK, MessageBoxImage.Error);
        }
    }
}

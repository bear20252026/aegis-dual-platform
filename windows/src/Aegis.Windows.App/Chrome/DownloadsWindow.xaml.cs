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
        Closed += (_, _) => _timer.Stop();
    }

    private void RefreshAll()
    {
        if (DownloadsList.ItemsSource is not ObservableCollection<DownloadItem> items)
            return;
        foreach (var item in items.ToList())
            item.Refresh();
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
        Process.Start("explorer.exe", $"/select,\"{path}\"");
    }
}

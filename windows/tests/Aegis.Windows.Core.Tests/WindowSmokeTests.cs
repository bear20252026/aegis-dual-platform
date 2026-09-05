namespace Aegis.Windows.Core.Tests;

using System.Collections.ObjectModel;
using System.Threading;
using Aegis.Windows.Chrome;
using Aegis.Windows.Core.Downloads;
using Aegis.Windows.Core.History;
using Xunit;

/// <summary>WPF 窗口构造冒烟测试（回归防护）：在 STA 线程实例化窗口，
/// 捕获「XAML 初始化期事件引用未初始化控件 → NullReferenceException」一类
/// 构造即崩溃的缺陷（历史窗口曾因 ChipAll IsChecked=True 触发早于控件初始化而 NRE）。
/// 任何窗口构造抛异常都会让本测试失败——防止同类问题复发。</summary>
public sealed class WindowSmokeTests
{
    [Fact]
    public void HistoryWindowConstructsAndAppliesBothThemesWithoutThrowing()
    {
        RunSta(() =>
        {
            var store = new HistoryStore(Path.Combine(Path.GetTempPath(), Path.GetRandomFileName()));
            var w = new HistoryWindow(store);
            // ApplyTheme 会替换资源字典值 → 触发 XAML 延迟资源的创建/解析。
            // 曾因非法颜色字面量（#FFB3FFFFFF，10 位十六进制）在此抛
            // FormatException「令牌无效」→ 历史窗口闪退。深浅各调一次锁定。
            w.ApplyTheme("dark");
            w.ApplyTheme("light");
        });
    }

    [Fact]
    public void DownloadsWindowConstructsWithoutThrowing()
    {
        RunSta(() =>
        {
            var items = new ObservableCollection<DownloadItem>();
            _ = new DownloadsWindow(items);
        });
    }

    private static void RunSta(Action action)
    {
        Exception? caught = null;
        var thread = new Thread(() =>
        {
            try
            {
                action();
            }
            catch (Exception ex)
            {
                caught = ex;
            }
        });
        thread.SetApartmentState(ApartmentState.STA);
        thread.Start();
        thread.Join();
        Assert.Null(caught);  // 构造抛异常 → 回归失败
    }
}

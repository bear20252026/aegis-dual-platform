namespace Aegis.Windows.Chrome;

using System.Windows;

/// <summary>
/// 无痕窗口的导航 UI 状态段（R8-CS-SEC-05，第八轮 2026-10-08）：确认面板/拒绝横幅
/// 与地址栏、前进后退按钮的可用性收拢在这里。三条状态各有唯一写点，判据都写在方法上。
///
/// 为什么单独成文件：`InPrivateWindow.xaml.cs` 在 432 行零余量基线上，而本项要新增
/// 一条「横幅收起」的写点——先净减才能加，与 `HostWebView.WebResourceGuards.cs`、
/// `MainWindow.Tabs.CoreReady.cs` 同一手法（文本逐字搬，不改语义）。
/// </summary>
public partial class InPrivateWindow
{
    /// <summary>导航控件可用性（确认面板打开时禁用，防止绕过待确认状态）。</summary>
    private void SetNavigationControlsEnabled(bool isEnabled)
    {
        AddressBar.IsEnabled = isEnabled;
        BackButton.IsEnabled = isEnabled;
        ForwardButton.IsEnabled = isEnabled;
        RefreshButton.IsEnabled = isEnabled;
    }

    /// <summary>呈现策略拒绝原因（B4 那批「静默拒绝改可见」在无痕窗的同款落点）。</summary>
    private void ShowRejection(string message)
    {
        ErrorPage.Text = message;
        ErrorPagePanel.Visibility = Visibility.Visible;
    }

    /// <summary>
    /// R8-CS-SEC-05：横幅的**收起**写点。此前本窗口只有 `ShowRejection` 一处
    /// `ErrorPagePanel` 赋值且恒置 Visible ⇒ 被拒一次后横幅常驻，即使随后已经正常
    /// 打开页面（主窗在 `OnTabNavigationCompleted` 里有 Collapsed 路径，两端不对称）。
    /// 判据保守：**只在导航成功时收起**——失败的导航保留上一条拒绝说明（那正是它该
    /// 待着的地方），不把「拒绝」洗成「静默」。
    /// </summary>
    private void DismissRejectionOnceNavigated(bool navigationSucceeded)
    {
        if (navigationSucceeded)
        {
            ErrorPagePanel.Visibility = Visibility.Collapsed;
        }
    }
}

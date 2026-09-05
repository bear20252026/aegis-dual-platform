namespace Aegis.Windows.Chrome;

using System.Linq;
using System.Windows;
using Aegis.Windows.Broker;
using Aegis.Windows.Core.Security;
using Aegis.Windows.Core.Settings;

/// <summary>设置窗口（M4-b）：AppSettings 全字段 UI 化——每个设置有真实消费者
/// （诚实性原则：引擎→地址栏归一；历史→导航记录；威胁源→启动刷新）。
/// 紧急终止开关（M4-a）：触发即冻结全部导航/下载/批准（重启恢复）。</summary>
public partial class SettingsWindow : Window
{
    private readonly AppSettings _settings;
    private readonly BrowserPolicyBroker _broker;
    private readonly MainWindow _owner;
    private bool _suppressEvents;

    public SettingsWindow(AppSettings settings, BrowserPolicyBroker broker, MainWindow owner)
    {
        InitializeComponent();
        _settings = settings;
        _broker = broker;
        _owner = owner;
        _suppressEvents = true;
        EngineBox.ItemsSource = UrlNormalizer.EngineOrder
            .Select(k => new { Key = k, Name = UrlNormalizer.EngineName(k) })
            .ToList();
        EngineBox.DisplayMemberPath = "Name";
        EngineBox.SelectedValuePath = "Key";
        EngineBox.SelectedValue = _settings.SearchEngine;
        HistoryToggle.IsChecked = _settings.HistoryEnabled;
        ThreatFeedBox.Text = _settings.ThreatFeedUrl;
        ThemeBox.SelectedIndex = string.Equals(_settings.Theme, "light", System.StringComparison.OrdinalIgnoreCase) ? 1 : 0;
        if (_broker.KillSwitch.IsEngaged)
            KillSwitchButton.IsEnabled = false;
        _suppressEvents = false;
    }

    private void EngineBox_SelectionChanged(object sender, System.Windows.Controls.SelectionChangedEventArgs e)
    {
        if (_suppressEvents || EngineBox.SelectedValue is not string engine)
            return;
        _settings.SearchEngine = engine;
        Save();
    }

    private void HistoryToggle_Changed(object sender, RoutedEventArgs e)
    {
        if (_suppressEvents)
            return;
        _settings.HistoryEnabled = HistoryToggle.IsChecked == true;
        Save();
    }

    private void ThemeBox_SelectionChanged(object sender, System.Windows.Controls.SelectionChangedEventArgs e)
    {
        if (_suppressEvents || ThemeBox.SelectedIndex < 0)
            return;
        _settings.Theme = ThemeBox.SelectedIndex == 1 ? "light" : "dark";
        Save();
        _owner.ApplyTheme(_settings.Theme);
    }

    private void ThreatFeedBox_LostFocus(object sender, RoutedEventArgs e)
    {
        var raw = ThreatFeedBox.Text.Trim();
        // 诚实性校验：非法地址（非 https）拒绝保存并回显——绝不静默接受
        if (raw.Length > 0 && ThreatFeedUpdater.ValidateFeedUrl(raw) is null)
        {
            ThreatFeedHint.Text = "地址无效（仅支持 https://）——未保存。";
            ThreatFeedHint.Foreground = new System.Windows.Media.SolidColorBrush(
                System.Windows.Media.Color.FromRgb(0xFC, 0xA5, 0xA5));
            return;
        }
        _settings.ThreatFeedUrl = raw;
        Save();
        ThreatFeedHint.Text = "已保存；生效于下次启动（导航与子资源拦截）。";
        ThreatFeedHint.Foreground = new System.Windows.Media.SolidColorBrush(
            System.Windows.Media.Color.FromRgb(0x94, 0xA3, 0xB8));
    }

    private void KillSwitch_Click(object sender, RoutedEventArgs e)
    {
        var confirmed = MessageBox.Show(
            this,
            "将立即冻结全部导航、下载与批准链（重启应用后恢复）。确定触发？",
            "紧急终止",
            MessageBoxButton.YesNo,
            MessageBoxImage.Warning);
        if (confirmed != MessageBoxResult.Yes)
            return;
        _broker.KillSwitch.Engage();
        KillSwitchButton.IsEnabled = false;
        KillSwitchState.Text = "已触发——全部导航与下载冻结中。";
        SecurityLog.Write("[security] 紧急终止开关已触发（设置窗口）");
    }

    private void Done_Click(object sender, RoutedEventArgs e) => Close();

    private void Save() => _settings.Save(AppSettings.DefaultPath);
}

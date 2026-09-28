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
    // CS-168：KillSwitch 已触发文案单源（构造器与触发后回显两处共用）
    private const string KillSwitchEngagedText = "已触发——全部导航与下载冻结中。";

    // CS-167：提示前景刷预建冻结——此前每次校验输入 new 两把刷子
    private static readonly System.Windows.Media.Brush HintErrorBrush = FrozenHintBrush(0xFC, 0xA5, 0xA5);
    private static readonly System.Windows.Media.Brush HintMutedBrush = FrozenHintBrush(0x94, 0xA3, 0xB8);

    private static System.Windows.Media.SolidColorBrush FrozenHintBrush(byte r, byte g, byte b)
    {
        var brush = new System.Windows.Media.SolidColorBrush(System.Windows.Media.Color.FromRgb(r, g, b));
        brush.Freeze();
        return brush;
    }

    private readonly AppSettings _settings;
    private readonly BrowserPolicyBroker _broker;
    private readonly MainWindow _owner;
    private readonly Core.Settings.SettingsService _settingsService;
    private bool _suppressEvents;

    public SettingsWindow(AppSettings settings, BrowserPolicyBroker broker, MainWindow owner,
        Core.Settings.SettingsService settingsService)
    {
        InitializeComponent();
        // CS-226：Esc 关闭设置窗（对话框惯例——此前无键盘关闭路径）
        PreviewKeyDown += (_, e) =>
        {
            if (e.Key == System.Windows.Input.Key.Escape)
                Close();
        };
        _settings = settings;
        _broker = broker;
        _owner = owner;
        _settingsService = settingsService;
        _suppressEvents = true;
        // CS-235：复用 MainWindow.EngineOption——此前同形匿名类型双定义
        EngineBox.ItemsSource = UrlNormalizer.EngineOrder
            .Select(k => new MainWindow.EngineOption(k, UrlNormalizer.EngineName(k)))
            .ToList();
        EngineBox.DisplayMemberPath = nameof(MainWindow.EngineOption.Name);
        EngineBox.SelectedValuePath = nameof(MainWindow.EngineOption.Key);
        EngineBox.SelectedValue = _settings.SearchEngine;
        HistoryToggle.IsChecked = _settings.HistoryEnabled;
        ThreatFeedBox.Text = _settings.ThreatFeedUrl;
        ThemeBox.SelectedIndex = string.Equals(_settings.Theme, "light", System.StringComparison.OrdinalIgnoreCase) ? 1 : 0;
        SleepCombo.SelectedIndex = SleepIndex(_settings.SleepMinutes);
        ProtectionCombo.SelectedIndex = Clamp(_settings.ProtectionLevel);
        HttpsCheck.IsChecked = _settings.HttpsOnly;
        DnsCheck.IsChecked = _settings.SecureDns;
        if (_broker.KillSwitch.IsEngaged)
        {
            KillSwitchButton.IsEnabled = false;
            KillSwitchState.Text = KillSwitchEngagedText;
        }
        _suppressEvents = false;
    }

    /// <summary>主窗口主题联动（浅色模式下不再永远深色）。</summary>
    public void ApplyTheme(string? theme) => WindowTheme.Apply(this, theme);

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
            ThreatFeedHint.Foreground = HintErrorBrush;
            return;
        }
        _settings.ThreatFeedUrl = raw;
        Save();
        ThreatFeedHint.Text = "已保存；生效于下次启动（导航与子资源拦截）。";
        ThreatFeedHint.Foreground = HintMutedBrush;
    }

    /// <summary>CS-169：提 internal 直测（分钟值 → 下拉索引，非法回退 30 分钟档）。</summary>
    internal static int SleepIndex(int minutes) => minutes switch { 0 => 0, 15 => 1, 60 => 3, _ => 2 };
    private static int Clamp(int v) => v < 0 ? 0 : v > 2 ? 2 : v;

    private void SleepCombo_Changed(object sender, System.Windows.Controls.SelectionChangedEventArgs e)
    {
        if (_suppressEvents) return;
        _settings.SleepMinutes = SleepCombo.SelectedIndex switch { 0 => 0, 1 => 15, 2 => 30, 3 => 60, _ => 30 };
        Save();
    }

    private void ProtectionCombo_Changed(object sender, System.Windows.Controls.SelectionChangedEventArgs e)
    {
        if (_suppressEvents) return;
        _settings.ProtectionLevel = Clamp(ProtectionCombo.SelectedIndex);
        Save();  // Apply 统一刷新 PrivacySettings 并原子写盘
    }

    private void Privacy_Changed(object sender, RoutedEventArgs e)
    {
        if (_suppressEvents) return;
        _settings.HttpsOnly = HttpsCheck.IsChecked == true;
        _settings.SecureDns = DnsCheck.IsChecked == true;
        Save();  // Apply 统一刷新 PrivacySettings 并原子写盘
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
        KillSwitchState.Text = KillSwitchEngagedText;
        SecurityLog.Write("[security] 紧急终止开关已触发（设置窗口）");
    }

    private void Done_Click(object sender, RoutedEventArgs e) => Close();

    private void Save() => _settingsService.Apply(_settings);
}

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
        // Q52：打开时把「上次成功更新 / 是否过期」续接在 XAML 那句说明之后——
        // 直接赋值会把说明抹掉（Join 在状态行为空时原样返回已有文案）。
        ThreatFeedHint.Text = Core.Security.ThreatFeedCacheStatus.Join(
            ThreatFeedHint.Text, ThreatFeedStatusLine());
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
        // Q52（外部第三轮审计 AEG-008）：旧文案把「要重启才生效」当成既定行为，两件事上
        // 已经不真——①刷新现在按节拍自己重取并按当前值重新解析源，②保存后这里就发起
        // 一次立即刷新。保留诚实的一半：立即刷新是后台任务，成败要看日志与缓存时间，
        // 所以提示只说「已按新源尝试刷新」，并把「上次成功更新」的事实摆出来。
        // 措辞是静态锚判定的面（ThreatFeedCacheStatusTests 反向钉住旧说法不得回潮）。
        var kicked = Core.Security.ThreatFeedCoordinator.Active?.RefreshNow() ?? false;
        ThreatFeedHint.Text = Core.Security.ThreatFeedCacheStatus.Join(
            raw.Length == 0
                ? "已清空订阅源：此后不再自动重取，当前名单仍会继续拦截。"
                : kicked
                    ? "已保存；已按新源发起刷新。"
                    : "已保存；将在下一个更新周期内生效。",
            ThreatFeedStatusLine());
        ThreatFeedHint.Foreground = HintMutedBrush;
    }

    /// <summary>Q52：订阅源提示位的「上次成功更新 / 是否过期」一行。
    /// 时间取缓存文件的写入时刻——`FetchAndStore` 只在抓取+校验+落盘全成功后原子替换，
    /// 所以它就是「最后一次成功」的权威形态，不需要再加一份会漂移的进程内副本，
    /// 也不必给 AppSettings 加字段（那要同步 SettingsService 快照与两个 XAML 锚）。
    /// 读文件时间失败当作「无记录」：设置界面绝不因为一句提示崩掉。</summary>
    private string ThreatFeedStatusLine()
    {
        if (string.IsNullOrWhiteSpace(_settings.ThreatFeedUrl))
            return string.Empty;
        System.DateTime? written = null;
        try
        {
            if (System.IO.File.Exists(Core.AppPaths.ThreatFeedCachePath))
                written = System.IO.File.GetLastWriteTimeUtc(Core.AppPaths.ThreatFeedCachePath);
        }
        catch (System.Exception)
        {
            written = null;
        }
        return Core.Security.ThreatFeedCacheStatus.Describe(
            written,
            System.DateTimeOffset.UtcNow,
            Core.Security.ThreatFeedCoordinator.DefaultRefreshInterval
            * Core.Security.ThreatFeedCoordinator.StaleAfterFactor);
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

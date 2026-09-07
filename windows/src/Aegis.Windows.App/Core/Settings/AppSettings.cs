namespace Aegis.Windows.Core.Settings;

using System;
using System.Collections.Generic;
using System.IO;
using System.Text.Json;

/// <summary>应用设置（ADR-009 D2：强类型 + 诚实性——每个字段必须有真实消费者，
/// CI 门禁与评审双把关；杜绝 Python 栈 30+ 影子配置的历史病灶）。
/// JSON 持久化（低频小文件，SQLite 留给数据型存储）。</summary>
public sealed class AppSettings
{
    private static readonly JsonSerializerOptions JsonOptions = new()
    {
        WriteIndented = true,
        // 窗口位置默认 NaN（未保存过）需可往返——允许命名浮点字面量
        NumberHandling = System.Text.Json.Serialization.JsonNumberHandling.AllowNamedFloatingPointLiterals,
    };

    /// <summary>搜索引擎 key（消费者：MainWindow 地址栏归一）。非法值回退默认。</summary>
    public string SearchEngine { get; set; } = Chrome.UrlNormalizer.DefaultEngine;

    /// <summary>历史记录开关（消费者：导航完成记录）。默认开——与 Chrome 惯例一致。</summary>
    public bool HistoryEnabled { get; set; } = true;

    /// <summary>威胁黑名单订阅源（消费者：启动刷新——仅 https，设置窗口校验）。</summary>
    public string ThreatFeedUrl { get; set; } = "";

    /// <summary>新标签页壁纸文件名（消费者：NtpBridge——白名单校验，与 Python
    /// ntp_wallpaper 同语义；空值回退 NtpAssets.DefaultWallpaper）。</summary>
    public string NtpWallpaper { get; set; } = "";

    /// <summary>浏览器 chrome 主题（"dark"/"light"——消费者：MainWindow.ApplyTheme）。
    /// 默认深色（历史遗留美学）；切换经设置窗口。</summary>
    public string Theme { get; set; } = "dark";

    // ── 窗口状态（消费者：MainWindow 启动恢复/关闭保存）──
    public double WindowLeft { get; set; } = double.NaN;
    public double WindowTop { get; set; } = double.NaN;
    public double WindowWidth { get; set; } = 1200;
    public double WindowHeight { get; set; } = 800;
    public bool WindowMaximized { get; set; }

    // ── 行为 / 隐私（消费者：MainWindow / HostWebView / WebViewEnvironment）──
    /// <summary>后台标签睡眠分钟（0=关闭——释放 WebView 内存）。</summary>
    public int SleepMinutes { get; set; } = 30;

    /// <summary>跟踪防护级别：0 基础 / 1 均衡 / 2 严格。</summary>
    public int ProtectionLevel { get; set; } = 1;

    /// <summary>HTTPS-only：http 自动升级 https。</summary>
    public bool HttpsOnly { get; set; } = true;

    /// <summary>安全 DNS（DoH）——环境参数，重启生效。</summary>
    public bool SecureDns { get; set; } = true;

    /// <summary>每站点缩放因子（host → 0.25~3.0；消费者：TabRuntime 导航应用/保存）。</summary>
    public Dictionary<string, double> ZoomByHost { get; set; } = new();

    public static string DefaultPath =>
        Path.Combine(AppPaths.DataDir, "settings.json");

    /// <summary>读取设置。任何读取/解析失败都回退默认值且**不抛出**（此前
    /// UnauthorizedAccessException 等直接上抛导致 MainWindow 构造失败、应用
    /// 无法启动）；坏文件先备份为 .bak——启动链随即 Apply(默认值) 会覆盖原
    /// 文件，无备份则用户设置永久丢失。</summary>
    public static AppSettings Load(string path)
    {
        try
        {
            if (!File.Exists(path))
                return new AppSettings();
            var settings = JsonSerializer.Deserialize<AppSettings>(File.ReadAllText(path), JsonOptions);
            return settings ?? new AppSettings();
        }
        catch (Exception ex)
        {
            BackupCorruptFile(path);
            Security.SecurityLog.Write(
                $"[settings] 读取失败（回退默认，原文件已备份 .bak）: {ex.GetType().Name}: {ex.Message}");
            return new AppSettings();  // fail-safe
        }
    }

    /// <summary>把无法解析的设置文件改名备份（尽力而为——失败静默）。</summary>
    private static void BackupCorruptFile(string path)
    {
        try
        {
            if (File.Exists(path))
                File.Copy(path, path + ".bak", overwrite: true);
        }
        catch (Exception)
        {
            // 备份失败不阻断启动
        }
    }

    /// <summary>保存设置（原子写：temp+Replace——此前直写，半写崩溃即损坏；
    /// 仅测试使用，运行期唯一写入口是 SettingsService.Apply）。</summary>
    public void Save(string path)
    {
        var dir = Path.GetDirectoryName(path);
        if (!string.IsNullOrEmpty(dir))
            Directory.CreateDirectory(dir);
        var temp = path + ".tmp." + Guid.NewGuid().ToString("N");
        try
        {
            File.WriteAllText(temp, JsonSerializer.Serialize(this, JsonOptions));
            if (File.Exists(path)) File.Replace(temp, path, null);
            else File.Move(temp, path);
        }
        finally
        {
            if (File.Exists(temp)) File.Delete(temp);
        }
    }
}

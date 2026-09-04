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

    public static string DefaultPath =>
        Path.Combine(AppPaths.DataDir, "settings.json");

    public static AppSettings Load(string path)
    {
        try
        {
            if (!File.Exists(path))
                return new AppSettings();
            var settings = JsonSerializer.Deserialize<AppSettings>(File.ReadAllText(path), JsonOptions);
            return settings ?? new AppSettings();
        }
        catch (IOException)
        {
            return new AppSettings();  // 读取失败回退默认（fail-safe）
        }
        catch (JsonException)
        {
            return new AppSettings();
        }
    }

    public void Save(string path)
    {
        var dir = Path.GetDirectoryName(path);
        if (!string.IsNullOrEmpty(dir))
            Directory.CreateDirectory(dir);
        File.WriteAllText(path, JsonSerializer.Serialize(this, JsonOptions));
    }
}

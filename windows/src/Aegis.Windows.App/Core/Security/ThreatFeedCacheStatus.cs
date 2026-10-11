namespace Aegis.Windows.Core.Security;

using System;

/// <summary>缓存文件能给出的「最后一次成功更新」事实（Q52，外部第三轮审计 AEG-008）。
///
/// 为什么不另设一个「上次成功时间」字段：`ThreatFeedUpdater.FetchAndStore` 只在
/// 抓取+校验+落盘全部成功后原子替换缓存文件（tmp+Move），所以文件的写入时间就是
/// 「最后一次成功更新」的权威值——再加一份进程内状态只会多出一个会漂移的副本，
/// 而且要持久化就得动 AppSettings/SettingsService 快照与两个 XAML 锚
/// （`XamlBindingStaticAnchorTests`、`verify_xaml_resources`），代价远大于收益。
///
/// 文案是纯函数：设置界面只负责把它贴到提示位，判定与措辞在这里可单测。</summary>
internal static class ThreatFeedCacheStatus
{
    /// <summary>缓存文件写入时间 ⇒ 人类可读的「上次成功更新 / 是否过期」。
    /// [lastWriteUtc] 传 null 表示文件不存在或从未成功。超过 [staleAfter] 仍未成功过一次
    /// 才算「可能已失效」——一个周期内的空档是正常节拍，不该吓唬用户。
    /// 只显示相对时长（不显示绝对时刻），所以「按 UTC 取的文件时间」对用户是不可见的
    /// 内部口径，不进文案；数字用固定不变格式（不随区域设置变），否则同一份缓存会显示成
    /// 两个「几分钟前」，用例断言与截图对比都会被这种抖动打红。</summary>
    internal static string Describe(DateTime? lastWriteUtc, DateTimeOffset now, TimeSpan staleAfter)
    {
        if (lastWriteUtc is null)
            return "尚无成功更新记录（缓存缺失或从未取回）。";
        var age = now - new DateTimeOffset(
            DateTime.SpecifyKind(lastWriteUtc.Value, DateTimeKind.Utc), TimeSpan.Zero);
        // 时钟被往回调过 ⇒ age 可能为负，落进「刚刚」档而不是显示「-3 分钟前」
        var ago = age.TotalMinutes switch
        {
            < 1 => "刚刚",
            < 60 => $"{(int)age.TotalMinutes} 分钟前",
            < 24 * 60 => $"{(int)age.TotalHours} 小时前",
            _ => $"{(int)age.TotalDays} 天前",
        };
        var stale = age > staleAfter
            ? "——已超过预期更新周期，名单可能已失效"
            : string.Empty;
        return $"上次成功更新：{ago}{stale}。";
    }

    /// <summary>把提示拼起来（分隔符单源：已有的提示非空时另起一行续接，
    /// 免得出现「（）；」这种空括号尾巴，也免得两句以「。」结尾被「；」硬连成一坨）。
    /// 界面打开时的「已有提示」就是 XAML 里那句说明文字——先续接再赋值，
    /// 直接赋值会把说明抹掉。</summary>
    internal static string Join(string? existing, string? addition) =>
        string.IsNullOrEmpty(addition)
            ? existing ?? string.Empty
            : string.IsNullOrEmpty(existing)
                ? addition
                : existing + "\n" + addition;
}

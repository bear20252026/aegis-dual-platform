namespace Aegis.Windows.Core;

/// <summary>CS-369（2026-10-01 审计）：标题/URL 长度上限单源——此前 2048/256
/// 常量在 BookmarkImporter、HistoryStore、BookmarkManagerWindow 三处独立维护
/// （一处调整漏两处即库间口径漂移）。ClampText 代理对安全截断同步收敛
///（原实现于 HistoryStore——CS-319）。</summary>
internal static class TextLimits
{
    /// <summary>URL 上限（页面可控串落库统一 2048）。</summary>
    internal const int MaxUrlChars = 2048;

    /// <summary>标题上限（页面可控串落库统一 256）。</summary>
    internal const int MaxTitleChars = 256;

    /// <summary>代理对安全截断：截断点落在高代理项上回退一位，不产生孤立代理。</summary>
    internal static string Clamp(string text, int maxChars)
    {
        if (text.Length <= maxChars)
            return text;
        var cut = maxChars;
        if (char.IsHighSurrogate(text[cut - 1]))
            cut--;
        return text[..cut];
    }
}

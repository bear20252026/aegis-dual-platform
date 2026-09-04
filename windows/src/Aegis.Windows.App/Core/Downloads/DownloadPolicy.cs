namespace Aegis.Windows.Core.Downloads;

using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;

/// <summary>下载策略（ADR-009 M3：宿主控制粒度的原生兑现——pywebview 硬编码
/// 禁用下载的天花板在正典栈不复存在）。判定语义对齐 Android DownloadPolicy
/// （批次 1 修复后版本）：净化后文件名 ∪ URL 去查询串路径段，去尾点+小写化
/// 后取扩展名——`x.exe.`（尾点）与 `/download?file=x.exe`（查询串直链）均命中。
/// 文件名净化对齐 Android sanitizeFileName：剥路径段/控制字符/尾点。</summary>
public static class DownloadPolicy
{
    /// <summary>危险扩展名集（可执行/脚本/磁盘镜像——对齐 Android 侧口径）。</summary>
    private static readonly HashSet<string> DangerousExtensions = new(StringComparer.Ordinal)
    {
        "exe", "msi", "msix", "appx", "bat", "cmd", "com", "scr", "pif",
        "ps1", "vbs", "vbe", "js", "jse", "wsf", "wsh", "hta", "cpl",
        "jar", "apk", "dll", "sys", "vhd", "iso",
    };

    /// <summary>该下载是否需要用户显式确认（危险扩展命中）。
    /// 候选集：净化文件名 ∪ URL 路径末段 ∪ 完整查询串（`/download?file=x.exe`
    /// 类直链在无 Content-Disposition 时同样命中——单测锁定的强判定）。</summary>
    public static bool RequiresExplicitConfirmation(string url, string suggestedFileName) =>
        DangerousExtensions.Contains(ExtractExtension(suggestedFileName))
        || DangerousExtensions.Contains(ExtractExtension(UrlPathLastSegment(url)))
        || DangerousExtensions.Contains(ExtractExtension(UriQuery(url)));

    /// <summary>净化服务器建议文件名：剥路径段、去控制字符/尾点，空结果回退默认名。</summary>
    public static string SanitizeFileName(string? raw)
    {
        var name = (raw ?? string.Empty).Trim();
        // 只取末段（服务器可给 /../../evil.exe 形态）
        var lastSlash = name.LastIndexOfAny(['/', '\\']);
        if (lastSlash >= 0)
            name = name[(lastSlash + 1)..];
        var chars = name.Where(c => !char.IsControl(c)).ToArray();
        name = new string(chars).Trim().TrimEnd('.');
        return name.Length > 0 ? name : "aegis_download";
    }

    /// <summary>URL 去查询串后的最后路径段（Content-Disposition 缺失时的判定候选）。</summary>
    private static string UrlPathLastSegment(string url) =>
        Uri.TryCreate(url, UriKind.Absolute, out var uri)
            ? Uri.UnescapeDataString(uri.AbsolutePath.Split('/').LastOrDefault() ?? string.Empty)
            : string.Empty;

    private static string UriQuery(string url) =>
        Uri.TryCreate(url, UriKind.Absolute, out var uri) ? uri.Query : string.Empty;

    private static string ExtractExtension(string fileName)
    {
        var normalized = fileName.Trim().ToLowerInvariant().TrimEnd('.');
        var dot = normalized.LastIndexOf('.');
        return dot >= 0 && dot < normalized.Length - 1 ? normalized[(dot + 1)..] : string.Empty;
    }
}

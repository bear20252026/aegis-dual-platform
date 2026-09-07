namespace Aegis.Windows.Core.Downloads;

using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;

/// <summary>下载策略（ADR-009 M3：宿主控制粒度的原生兑现——pywebview 硬编码
/// 禁用下载的天花板在正典栈不复存在）。判定语义对齐 Android DownloadPolicy
/// （批次 1 修复后版本）：净化后文件名 ∪ URL 去查询串路径段，去尾点+小写化
/// 后取扩展名——`x.exe.`（尾点）与 `/download?file=x.exe`（查询串直链）均命中。
/// 查询串判定按参数值取扩展（此前整串取尾点：`?f=x.exe&sig=abc` 因尾缀拼接
/// 而漏判）。文件名净化对齐 Android sanitizeFileName：剥路径段/控制字符/
/// 尾点/Windows 保留设备名/超长截断。</summary>
public static class DownloadPolicy
{
    private const int MaxFileNameChars = 200;

    /// <summary>危险扩展名集（可执行/脚本/磁盘镜像——对齐 Android 侧口径并
    /// 补齐 lnk/reg/chm/scf/msc/diagcab/py 等 Windows 侧载体）。</summary>
    private static readonly HashSet<string> DangerousExtensions = new(StringComparer.Ordinal)
    {
        "exe", "msi", "msix", "appx", "bat", "cmd", "com", "scr", "pif",
        "ps1", "vbs", "vbe", "js", "jse", "wsf", "wsh", "hta", "cpl",
        "jar", "apk", "dll", "sys", "vhd", "iso",
        "lnk", "reg", "chm", "scf", "msc", "diagcab", "py", "pyw", "msh", "msh1", "msh2", "psm1",
    };

    /// <summary>Windows 保留设备名（CON/PRN/AUX/NUL/COM1-9/LPT1-9）——作文件名
    /// 时写盘行为异常，净化时追加后缀规避。</summary>
    private static readonly HashSet<string> ReservedDeviceNames = new(StringComparer.OrdinalIgnoreCase)
    {
        "CON", "PRN", "AUX", "NUL",
        "COM1", "COM2", "COM3", "COM4", "COM5", "COM6", "COM7", "COM8", "COM9",
        "LPT1", "LPT2", "LPT3", "LPT4", "LPT5", "LPT6", "LPT7", "LPT8", "LPT9",
    };

    /// <summary>该下载是否需要用户显式确认（危险扩展命中）。
    /// 候选集：净化文件名 ∪ URL 路径末段 ∪ 查询串各参数值（`/download?file=x.exe`
    /// 类直链在无 Content-Disposition 时同样命中——单测锁定的强判定）。</summary>
    public static bool RequiresExplicitConfirmation(string url, string suggestedFileName) =>
        DangerousExtensions.Contains(ExtractExtension(suggestedFileName))
        || DangerousExtensions.Contains(ExtractExtension(UrlPathLastSegment(url)))
        || QueryContainsDangerousExtension(UriQuery(url));

    /// <summary>查询串按参数值判定（`f=x.exe&sig=abc` 命中；此前整串取尾点
    /// 只在查询恰好以扩展结尾时才命中）。</summary>
    private static bool QueryContainsDangerousExtension(string query)
    {
        if (string.IsNullOrEmpty(query))
            return false;
        foreach (var pair in query.TrimStart('?').Split('&', StringSplitOptions.RemoveEmptyEntries))
        {
            var value = pair.Contains('=', StringComparison.Ordinal)
                ? pair[(pair.IndexOf('=', StringComparison.Ordinal) + 1)..]
                : pair;
            var segment = Uri.UnescapeDataString(value.Split('/').LastOrDefault() ?? string.Empty);
            if (DangerousExtensions.Contains(ExtractExtension(segment)))
                return true;
        }
        return false;
    }

    /// <summary>净化服务器建议文件名：剥路径段、去控制字符/尾点、规避 Windows
    /// 保留设备名、超长截断（保留扩展名），空结果回退默认名。</summary>
    public static string SanitizeFileName(string? raw)
    {
        var name = (raw ?? string.Empty).Trim();
        // 只取末段（服务器可给 /../../evil.exe 形态）
        var lastSlash = name.LastIndexOfAny(['/', '\\']);
        if (lastSlash >= 0)
            name = name[(lastSlash + 1)..];
        var chars = name.Where(c => !char.IsControl(c)).ToArray();
        name = new string(chars).Trim().TrimEnd('.');
        if (name.Length == 0)
            return "aegis_download";
        // 保留设备名（含带扩展形态 "CON.txt"）在词干内追加后缀——
        // "CON.txt" → "CON_file.txt"（Windows 对 CON.* 全族保留，仅在
        // 末尾追加不解除保留）
        var dot = name.IndexOf('.');
        var stem = dot >= 0 ? name[..dot] : name;
        if (ReservedDeviceNames.Contains(stem))
        {
            var rest = dot >= 0 ? name[dot..] : string.Empty;
            name = stem + "_file" + rest;
        }
        if (name.Length > MaxFileNameChars)
        {
            // 超长截断保留扩展名（与 Rust sanitize_filename 同语义）
            var ext = Path.GetExtension(name);
            var stemLen = name.Length - ext.Length;
            var keep = Math.Max(1, MaxFileNameChars - ext.Length);
            if (stemLen > keep)
                name = name[..keep].TrimEnd('.') + ext;
            else
                name = name[..MaxFileNameChars].TrimEnd('.');
        }
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
        var normalized = (fileName ?? string.Empty).Trim().ToLowerInvariant().TrimEnd('.');
        var dot = normalized.LastIndexOf('.');
        return dot >= 0 && dot < normalized.Length - 1 ? normalized[(dot + 1)..] : string.Empty;
    }
}

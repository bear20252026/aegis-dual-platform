namespace Aegis.Windows.Core.History;

using System;

/// <summary>浏览历史「可记录 URL」判定（M2 记录缺口修复）。内部页面
/// （新标签页/离线画板虚拟主机、about:blank、非 http/https）不入历史——
/// 否则每次新建标签/回首页都会把 `ntp.aegis.local/start.html` 灌进历史
/// （「历史全被首页占满」）。纯静态判定，全量可单测。</summary>
public static class HistoryRecorder
{
    public static bool IsRecordableUrl(string? url)
    {
        if (string.IsNullOrWhiteSpace(url))
            return false;
        if (!Uri.TryCreate(url, UriKind.Absolute, out var uri))
            return false;
        if (uri.Scheme != Uri.UriSchemeHttp && uri.Scheme != Uri.UriSchemeHttps)
            return false;
        if (uri.Host.Equals(Chrome.Ntp.NtpAssets.HostName, StringComparison.OrdinalIgnoreCase))
            return false;  // 新标签页首页——不记历史
        if (uri.Host.Equals(Chrome.Ntp.NtpAssets.GeoHostName, StringComparison.OrdinalIgnoreCase))
            return false;  // 离线几何画板——不记历史
        return true;
    }
}

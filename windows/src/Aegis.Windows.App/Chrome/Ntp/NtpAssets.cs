namespace Aegis.Windows.Chrome.Ntp;

using System;
using System.Collections.Generic;
using System.IO;

/// <summary>新标签页资产定位（M3——ADR-009 D2-3：start.html 跨端单源经
/// SetVirtualHostNameToFolderMapping 加载）。安全边界：
/// - 虚拟主机只映射发布输出内的 ntp/ 目录——不暴露文件系统路径；
/// - 壁纸白名单：仅随包登记的固定文件名可被设置/渲染（对齐 Python
///   asset_scheme.WALLPAPERS），任何其他名称 fail-closed 拒绝；
/// - 画板资源（GeoGebra bundle）未随包时 fail-closed 降级（与 Python
///   open_geogebra 的「资源缺失→不可用」语义一致）。</summary>
public static class NtpAssets
{
    /// <summary>NTP 虚拟主机名（https scheme 由 WebView2 虚拟主机机制提供）。</summary>
    public const string HostName = "ntp.aegis.local";

    /// <summary>NTP 入口 URL（每标签新建页/主页按钮的目标地址）。</summary>
    public const string Url = "https://" + HostName + "/start.html";

    /// <summary>离线几何画板虚拟主机名（资源随包时才映射）。</summary>
    public const string GeoHostName = "geo.aegis.local";

    /// <summary>GeoGebra bundle 入口（相对资源根的固定路径——编译期常量）。</summary>
    public const string GeoEntryPath = "GeoGebra/HTML5/5.0/GeoGebra.html";

    /// <summary>默认壁纸（对齐 Python _DEFAULT_WALLPAPER）。</summary>
    public const string DefaultWallpaper = "aurora-twilight.jpg";

    /// <summary>壁纸白名单（对齐 Python asset_scheme.WALLPAPERS——新增壁纸
    /// 须随单源 shell/wallpapers 一同登记，否则拒绝）。</summary>
    public static readonly IReadOnlyList<string> Wallpapers = new[]
    {
        "aurora-magenta.jpg",
        "aurora-lime.jpg",
        "aurora-twilight.jpg",
        "aurora-violet.jpg",
    };

    /// <summary>壁纸名称白名单校验（非白名单 → false，fail-closed）。</summary>
    public static bool IsWallpaperAllowed(string? name)
    {
        if (string.IsNullOrWhiteSpace(name))
            return false;
        foreach (var item in Wallpapers)
        {
            if (item == name)
                return true;
        }
        return false;
    }

    /// <summary>是否为受信虚拟主机地址（NTP/画板）。此类地址的首次导航必须在
    /// SetVirtualHostNameToFolderMapping 映射就绪之后发起——构造时预置 Source
    /// 会在映射前解析 → 空白页（首页无法显示的根因）。</summary>
    public static bool IsVirtualHostUrl(string? url) =>
        !string.IsNullOrWhiteSpace(url)
        && Uri.TryCreate(url, UriKind.Absolute, out var uri)
        && (uri.Host.Equals(HostName, StringComparison.OrdinalIgnoreCase)
            || uri.Host.Equals(GeoHostName, StringComparison.OrdinalIgnoreCase));

    /// <summary>定位发布输出的 ntp/ 资源根（exe 旁——csproj 单源拷贝）。
    /// 缺失返回 null（虚拟主机不映射——NTP 显示宿主错误页，绝不回退 file://）。</summary>
    public static string? ResolveContentRoot()
    {
        var candidate = Path.Combine(AppContext.BaseDirectory, "ntp", "start.html");
        return File.Exists(candidate)
            ? Path.GetDirectoryName(candidate)!
            : null;
    }

    /// <summary>定位离线几何画板资源根（含 GeoEntryPath 的目录）。查找顺序：
    /// ① 环境变量 AEGIS_GEOGEBRA_DIR；② exe 旁 geogebra/（发布可随包）。
    /// 未随包返回 null——上层 fail-closed 降级，按钮置灰提示。</summary>
    public static string? ResolveGeoRoot()
    {
        var fromEnv = Environment.GetEnvironmentVariable("AEGIS_GEOGEBRA_DIR");
        if (!string.IsNullOrWhiteSpace(fromEnv) && IsGeoRoot(fromEnv))
            return Path.GetFullPath(fromEnv);
        var besideExe = Path.Combine(AppContext.BaseDirectory, "geogebra");
        return IsGeoRoot(besideExe) ? besideExe : null;
    }

    private static bool IsGeoRoot(string dir) =>
        File.Exists(Path.Combine(dir, GeoEntryPath));
}

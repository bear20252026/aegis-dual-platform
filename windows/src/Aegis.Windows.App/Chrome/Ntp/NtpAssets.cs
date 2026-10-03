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
    /// <summary>NTP 虚拟主机名（https scheme 由 WebView2 虚拟主机机制提供）。
    /// 审计第七轮（2026-10-03）：常量单源上提到 Broker.TrustedChromeUiOrigins——
    /// 导航层的私有/回环拒绝必须为宿主虚拟主机豁免，两处判定不同源即漂移
    ///（首页/画板被自家策略拒掉的实机风险）。</summary>
    public const string HostName = Broker.TrustedChromeUiOrigins.NtpHost;

    /// <summary>NTP 入口 URL（每标签新建页/主页按钮的目标地址）。</summary>
    public const string Url = "https://" + HostName + "/start.html";

    /// <summary>离线几何画板虚拟主机名（资源随包时才映射）。单源同上。</summary>
    public const string GeoHostName = Broker.TrustedChromeUiOrigins.GeoHost;

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

    // CS-193：进程级缓存——exe 旁资源布局进程内不变，此前每标签创建都
    // File.Exists 打一次盘（缺失结果同样缓存：发布物缺失是稳定态）
    private static string? _contentRoot;
    private static bool _contentRootResolved;

    /// <summary>定位发布输出的 ntp/ 资源根（exe 旁——csproj 单源拷贝）。
    /// 缺失返回 null（虚拟主机不映射——NTP 显示宿主错误页，绝不回退 file://）。</summary>
    public static string? ResolveContentRoot()
    {
        if (_contentRootResolved)
            return _contentRoot;
        var candidate = Path.Combine(AppContext.BaseDirectory, "ntp", "start.html");
        _contentRoot = File.Exists(candidate)
            ? Path.GetDirectoryName(candidate)!
            : null;
        _contentRootResolved = true;
        return _contentRoot;
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

    /// <summary>把 NTP/画板虚拟主机映射到发布输出资源根（主窗口与无痕窗口
    /// 共用——此前两份逐行复制漂移）。资源缺失的映射跳过（上层 fail-closed）。
    /// CS-334（2026-10-01 审计·P1）：AccessKind 用 Deny——Allow 等效 ACAO:*
    /// 全放行，任意远程站点 fetch https://ntp.aegis.local/start.html 即可读
    /// NTP/GeoGebra 资产，一行探测即可识别 Aegis 用户（指纹防护被单点旁路，
    /// GeoGebra 整包也被任意外站热链）。Deny 只拒跨源请求：NTP 自身文档加载
    /// 自身子资源是同源请求不受影响；远程页探测必失败（无 ACAO 头可读）。
    /// CS-373（2026-10-01 审计）：成功映射日志进程级只记一次——此前每标签
    /// 3-4 行（N 标签 3N 行冲刷 1MB 取证日志）；资源缺失失败仍每次留痕。</summary>
    public static void BindVirtualHosts(Microsoft.Web.WebView2.Core.CoreWebView2 core)
    {
        var ntpRoot = ResolveContentRoot();
        if (ntpRoot is not null)
        {
            core.SetVirtualHostNameToFolderMapping(
                HostName, ntpRoot,
                Microsoft.Web.WebView2.Core.CoreWebView2HostResourceAccessKind.Deny);
            LogBindOnce(ref _ntpBindLogged, $"[init] {HostName} 已映射 -> {ntpRoot}（AccessKind=Deny——跨源拒读，防远程页探测指纹）");
        }
        else
        {
            // 失败不折叠——NTP 加载失败时需区分「资源根缺失」与「映射未生效」
            Core.Security.SecurityLog.Write(
                $"[init] ntp 资源根缺失（BaseDirectory={AppContext.BaseDirectory}）");
        }
        var geoRoot = ResolveGeoRoot();
        if (geoRoot is not null)
        {
            core.SetVirtualHostNameToFolderMapping(
                GeoHostName, geoRoot,
                Microsoft.Web.WebView2.Core.CoreWebView2HostResourceAccessKind.Deny);
            LogBindOnce(ref _geoBindLogged, $"[init] {GeoHostName} 已映射 -> {geoRoot}（AccessKind=Deny）");
        }
        // geo 缺失是稳定常态（画板包未随包即 fail-closed 降级）——不刷日志
    }

    private static bool _ntpBindLogged;
    private static bool _geoBindLogged;

    private static void LogBindOnce(ref bool logged, string message)
    {
        if (logged)
            return;
        Core.Security.SecurityLog.Write(message);
        logged = true;
    }

    /// <summary>NTP 宿主桥的顶层文档门禁：core.Source 为当前顶层文档（非任一
    /// iframe）。远程顶层页面即使内嵌 ntp.aegis.local 帧，顶层来源仍为远程
    /// host → 拒绝；从根上封死「帧内嵌复用受信桥」的绕过面。</summary>
    public static bool IsTopLevelNtpDocument(Microsoft.Web.WebView2.Core.CoreWebView2 core) =>
        Uri.TryCreate(core.Source, UriKind.Absolute, out var uri)
        && uri.Host.Equals(HostName, StringComparison.OrdinalIgnoreCase);
}

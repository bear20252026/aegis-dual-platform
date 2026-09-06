namespace Aegis.Windows.WebView;

using System;
using System.IO;
using System.Threading.Tasks;
using Aegis.Windows.Core.Privacy;
using Microsoft.Web.WebView2.Core;

/// <summary>共享 WebView2 环境（全局单例——所有标签共用，避免多环境开销）。
/// - 默认环境：应用正常浏览；启用安全 DNS（DoH，阿里公共解析——国内可达）时注入
///   --dns-over-https 参数（构建一次，改动需重启）。
/// - InPrivate 环境：独立临时用户数据目录（隔离 cookie/缓存），关闭后尽力清理。</summary>
public static class WebViewEnvironment
{
    private static Task<CoreWebView2Environment>? _shared;
    private static CoreWebView2Environment? _inPrivate;
    private static string? _inPrivateDir;

    /// <summary>共享环境（惰性创建——参数依 PrivacySettings.SecureDns）。</summary>
    public static Task<CoreWebView2Environment> SharedAsync()
    {
        _shared ??= CreateAsync(null);
        return _shared;
    }

    /// <summary>InPrivate 环境（独立用户目录）。</summary>
    public static async Task<CoreWebView2Environment> InPrivateAsync()
    {
        if (_inPrivate is not null)
            return _inPrivate;
        _inPrivateDir = Path.Combine(
            Path.GetTempPath(), "Aegis.InPrivate." + Guid.NewGuid().ToString("N"));
        _inPrivate = await CreateAsync(_inPrivateDir);
        return _inPrivate;
    }

    /// <summary>尽力清理 InPrivate 临时目录（在相关 WebView 全部销毁后调用）。</summary>
    public static void CleanupInPrivate()
    {
        if (_inPrivateDir is null)
            return;
        var dir = _inPrivateDir;
        _inPrivateDir = null;
        _inPrivate = null;
        _ = Task.Run(() =>
        {
            for (var i = 0; i < 5; i++)
            {
                try
                {
                    if (Directory.Exists(dir))
                        Directory.Delete(dir, true);
                    return;
                }
                catch (Exception)
                {
                    System.Threading.Thread.Sleep(800);  // WebView2 可能仍持有锁——重试
                }
            }
        });
    }

    private static async Task<CoreWebView2Environment> CreateAsync(string? userDataFolder)
    {
        var options = new CoreWebView2EnvironmentOptions();
        if (PrivacySettings.SecureDns && userDataFolder is null)
        {
            options.AdditionalBrowserArguments =
                "--dns-over-https-mode=secure " +
                "--dns-over-https-templates=https://dns.alidns.com/dns-query";
        }
        return await CoreWebView2Environment.CreateAsync(null, userDataFolder, options);
    }
}

namespace Aegis.Windows.WebView;

using System;
using System.Collections.Generic;
using System.IO;
using System.Threading;
using System.Threading.Tasks;
using Aegis.Windows.Core.Privacy;
using Microsoft.Web.WebView2.Core;

/// <summary>共享 WebView2 环境（全局单例——所有标签共用，避免多环境开销）。
/// - 默认环境：应用正常浏览；启用安全 DNS（DoH，阿里公共解析——国内可达）时注入
///   --dns-over-https 参数（构建一次，改动需重启）。
/// - InPrivate 环境：每个无痕窗口一个独立临时用户数据目录（互相隔离 cookie/缓存），
///   全部无痕窗口关闭后才清理临时目录（引用计数——早关的窗口不再删掉
///   存活窗口仍在使用的数据目录）。</summary>
public static class WebViewEnvironment
{
    private static Task<CoreWebView2Environment>? _shared;
    private static readonly object _inPrivateLock = new();
    private static readonly List<string> _inPrivateDirs = new();

    /// <summary>共享环境（惰性创建——参数依 PrivacySettings.SecureDns）。</summary>
    public static Task<CoreWebView2Environment> SharedAsync()
    {
        _shared ??= CreateAsync(null);
        return _shared;
    }

    /// <summary>InPrivate 环境（每个无痕窗口独立用户目录）。返回租约——窗口
    /// 关闭时 Dispose，最后一个租约释放后异步清理全部临时目录。</summary>
    public static async Task<InPrivateEnvironmentLease> InPrivateAsync()
    {
        string dir;
        CoreWebView2Environment env;
        // 创建过程（含目录约定）与登记必须原子——两个无痕窗口并发首开时
        // 不能共享同一目录（隔离承诺）。
        lock (_inPrivateLock)
        {
            dir = Path.Combine(
                Path.GetTempPath(), "Aegis.InPrivate." + Guid.NewGuid().ToString("N"));
            _inPrivateDirs.Add(dir);
        }
        try
        {
            env = await CreateAsync(dir);
        }
        catch
        {
            lock (_inPrivateLock) { _inPrivateDirs.Remove(dir); }
            throw;
        }
        return new InPrivateEnvironmentLease(dir, env);
    }

    /// <summary>登记目录的清理（在相关 WebView 全部销毁后调用）。</summary>
    internal static void ReleaseInPrivateDir(string dir)
    {
        lock (_inPrivateLock)
        {
            if (!_inPrivateDirs.Remove(dir))
                return;  // 已被其它窗口触发清理
        }
        _ = Task.Run(() => DeleteWithRetry(dir));
    }

    private static void DeleteWithRetry(string dir)
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

/// <summary>单个无痕窗口的环境租约：窗口持有一份，Dispose 即归还；全部归还后
/// 触发临时目录清理。Dispose 幂等（窗口 Closing/OnClosed 双路径安全）。</summary>
public sealed class InPrivateEnvironmentLease : IDisposable
{
    private readonly string _dir;
    private int _released;

    internal InPrivateEnvironmentLease(string dir, CoreWebView2Environment environment)
    {
        _dir = dir;
        Environment = environment;
    }

    public CoreWebView2Environment Environment { get; }

    public void Dispose()
    {
        if (Interlocked.Exchange(ref _released, 1) == 1)
            return;
        WebViewEnvironment.ReleaseInPrivateDir(_dir);
    }
}

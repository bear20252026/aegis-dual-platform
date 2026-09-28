namespace Aegis.Windows.WebView;

using System;
using System.Collections.Generic;
using System.IO;
using System.Threading;
using System.Threading.Tasks;
using Aegis.Windows.Core.Privacy;
using Aegis.Windows.Core.Security;
using Microsoft.Web.WebView2.Core;

/// <summary>共享 WebView2 环境（全局单例——所有标签共用，避免多环境开销）。
/// - 默认环境：应用正常浏览；启用安全 DNS（DoH，阿里公共解析——国内可达）时注入
///   --dns-over-https 参数（构建一次，改动需重启）。
/// - InPrivate 环境：每个无痕窗口一个独立临时用户数据目录（互相隔离 cookie/缓存），
///   全部无痕窗口关闭后才清理临时目录（引用计数——早关的窗口不再删掉
///   存活窗口仍在使用的数据目录）。</summary>
public static class WebViewEnvironment
{
    // CS-178：Lazy（ExecutionAndPublication）——`??=` 赋值非原子，两个标签
    // 并发首开可各建一个环境（其中一个连同其浏览器进程泄漏）
    private static readonly Lazy<Task<CoreWebView2Environment>> Shared =
        new(() => CreateAsync(null));

    private static readonly object _inPrivateLock = new();
    private static readonly List<string> _inPrivateDirs = new();

    // CS-181：临时目录清理重试参数（WebView2 子进程退出有延迟——锁定窗口内删除必然失败）
    private const int DeleteRetryCount = 5;
    private const int DeleteRetryDelayMs = 800;

    /// <summary>共享环境（惰性创建——参数依 PrivacySettings.SecureDns）。</summary>
    public static Task<CoreWebView2Environment> SharedAsync() => Shared.Value;

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
        for (var i = 0; i < DeleteRetryCount; i++)
        {
            try
            {
                if (Directory.Exists(dir))
                    Directory.Delete(dir, true);
                return;
            }
            catch (Exception)
            {
                System.Threading.Thread.Sleep(DeleteRetryDelayMs);  // WebView2 可能仍持有锁——重试
            }
        }
        // CS-180：重试全败不再静默——临时目录残留可观测（磁盘占用/隐私审计）
        SecurityLog.Write($"[inprivate] 无痕临时目录清理失败（保留待下次清理）: {dir}");
    }

    private static async Task<CoreWebView2Environment> CreateAsync(string? userDataFolder)
    {
        var options = new CoreWebView2EnvironmentOptions();
        // CS-179：DoH 仅注入默认环境为既定口径——无痕隔离承诺由独立临时数据
        // 目录兑现；DoH 为进程级浏览器参数且依赖设置快照时点（无痕窗口随开
        // 随关）。如需为无痕单独启用，按 device-validation runbook 真机评估后放开。
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

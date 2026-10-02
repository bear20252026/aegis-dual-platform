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
    // CS-178：门闩串行化——`??=` 赋值非原子，两个标签并发首开可各建一个环境
    //（其中一个连同其浏览器进程泄漏）。
    // CS-347（2026-10-01 审计）：失败可重置——Lazy 会把 Faulted 任务永久缓存，
    // 首建失败（如 WebView2 运行时未装/用户目录被锁）后所有标签不可用到重启。
    // 改 SemaphoreSlim 门闩：成功结果保留单次创建语义（恒缓存），失败不缓存
    //（下次调用重试）。
    private static readonly SemaphoreSlim SharedGate = new(1, 1);
    private static Task<CoreWebView2Environment>? _shared;

    private static readonly object _inPrivateLock = new();
    private static readonly List<string> _inPrivateDirs = new();

    // CS-181：临时目录清理重试参数（WebView2 子进程退出有延迟——锁定窗口内删除必然失败）
    private const int DeleteRetryCount = 5;
    private const int DeleteRetryDelayMs = 800;
    private const string InPrivateDirPrefix = "Aegis.InPrivate.";

    /// <summary>共享环境（惰性创建——参数依 PrivacySettings.SecureDns）。
    /// 并发首开串行化；创建失败不缓存（下次重试），成功后单例。</summary>
    public static async Task<CoreWebView2Environment> SharedAsync()
    {
        var cached = _shared;
        if (cached is not null)
            return await cached;
        await SharedGate.WaitAsync();
        try
        {
            if (_shared is null)
            {
                // 仅成功结果入缓存；异常向上抛且不留 Faulted 任务
                var environment = await CreateAsync(null);
                _shared = Task.FromResult(environment);
            }
            return await _shared;
        }
        finally
        {
            SharedGate.Release();
        }
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
                Path.GetTempPath(), InPrivateDirPrefix + Guid.NewGuid().ToString("N"));
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

    // CS-352 测试缝：登记/撤销"本进程在用"目录（孤儿清理的跳过分支）——
    // 不触发清理副作用，测试结束撤销即可
    internal static void RegisterInPrivateDirForTests(string dir)
    {
        lock (_inPrivateLock)
            _inPrivateDirs.Add(dir);
    }

    internal static void UnregisterInPrivateDirForTests(string dir)
    {
        lock (_inPrivateLock)
            _inPrivateDirs.Remove(dir);
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

    /// <summary>CS-352（2026-10-01 审计）：启动扫描 %TEMP% 清理崩溃残留的
    /// 无痕临时目录——正常退出路径经引用计数清理，崩溃/强杀后永久残留
    //（隐私承诺失效）。仅删除本进程未持有的 Aegis.InPrivate.* 目录；删除
    /// 失败（被并发实例的浏览器进程锁定等）跳过留痕，不打断启动。
    /// tempRoot 参数为测试注入缝（生产恒为真实 %TEMP%）。</summary>
    internal static int CleanupOrphanInPrivateDirs(string? tempRoot = null)
    {
        var root = tempRoot ?? Path.GetTempPath();
        string[] candidates;
        try
        {
            candidates = Directory.GetDirectories(root, InPrivateDirPrefix + "*");
        }
        catch (Exception)
        {
            return 0;  // %TEMP% 不可读——不打断启动
        }
        lock (_inPrivateLock)
        {
            var removed = 0;
            foreach (var candidate in candidates)
            {
                if (_inPrivateDirs.Contains(candidate))
                    continue;  // 本进程在用（无痕窗口存活）
                try
                {
                    Directory.Delete(candidate, recursive: true);
                    removed++;
                }
                catch (Exception)
                {
                    // 并发实例持有/句柄未释放——留待下次启动（失败可观测）
                    SecurityLog.Write($"[inprivate] 崩溃残留无痕目录清理失败（跳过）: {candidate}");
                }
            }
            if (removed > 0)
                SecurityLog.Write($"[inprivate] 已清理崩溃残留无痕临时目录 {removed} 个");
            return removed;
        }
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

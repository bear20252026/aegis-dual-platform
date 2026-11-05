namespace Aegis.Windows.WebView;

using System;
using System.Threading.Tasks;
using System.Windows;
using Aegis.Windows.Core.Security;
using Microsoft.Web.WebView2.Core;

/// <summary>
/// WebView2 Runtime 更新事件处理器（ADR-001 后果段）。
/// 
/// 职责：
/// 1. 监听 CoreWebView2Environment.NewBrowserVersionAvailable 事件
/// 2. 事件触发时保存当前会话状态（标签列表、URL、窗口位置）
/// 3. 通知用户有可用更新（可选：提示重启或自动重启）
/// 4. 受控重启应用（重启前保存状态、重启后恢复）
/// 
/// 设计原则：
/// - 事件是通知性的（informational）——用户可选择何时重启
/// - 不强制立即重启——浏览器仍可继续使用旧 Runtime
/// - 状态保存复用现有 TabSessionStore 机制
/// - 无痕窗口不参与状态保存（隐私承诺——不持久化无痕会话）
/// 
/// 参考：
/// - Microsoft WebView2 文档：NewBrowserVersionAvailable 事件
/// - ADR-001 §后果：需处理 NewBrowserVersionAvailable（保存状态/通知/受控重启）
/// </summary>
public sealed class RuntimeUpdater : IDisposable
{
    private readonly CoreWebView2Environment _environment;
    private readonly Func<bool> _shouldRestart; // 测试注入缝：判定是否自动重启
    private readonly Action? _onUpdateAvailable; // 测试注入缝：更新可用回调
    private readonly Action? _onRestartRequested; // 测试注入缝：重启请求回调
    private bool _disposed;
    private bool _isSubscribed;

    /// <summary>
    /// 构造 RuntimeUpdater。
    /// </summary>
    /// <param name="environment">WebView2 环境实例（共享环境或无痕环境）</param>
    /// <param name="shouldRestart">可选：判定是否自动重启（生产恒为 false——用户手动选择）</param>
    /// <param name="onUpdateAvailable">可选：更新可用时的回调（生产用于 UI 通知）</param>
    /// <param name="onRestartRequested">可选：重启请求时的回调（生产用于状态保存+应用重启）</param>
    public RuntimeUpdater(
        CoreWebView2Environment environment,
        Func<bool>? shouldRestart = null,
        Action? onUpdateAvailable = null,
        Action? onRestartRequested = null)
    {
        _environment = environment ?? throw new ArgumentNullException(nameof(environment));
        _shouldRestart = shouldRestart ?? (() => false);
        _onUpdateAvailable = onUpdateAvailable;
        _onRestartRequested = onRestartRequested;
    }

    /// <summary>
    /// 订阅 NewBrowserVersionAvailable 事件。幂等——重复调用不重复订阅。
    /// </summary>
    public void Subscribe()
    {
        if (_disposed)
            throw new ObjectDisposedException(nameof(RuntimeUpdater));
        if (_isSubscribed)
            return;

        _environment.NewBrowserVersionAvailable += OnNewBrowserVersionAvailable;
        _isSubscribed = true;
    }

    /// <summary>
    /// 取消订阅事件。幂等——未订阅时调用安全。
    /// </summary>
    public void Unsubscribe()
    {
        if (!_isSubscribed)
            return;

        _environment.NewBrowserVersionAvailable -= OnNewBrowserVersionAvailable;
        _isSubscribed = false;
    }

    private void OnNewBrowserVersionAvailable(object? sender, object? e)
    {
        // 事件参数为空对象（WebView2 API 设计）——版本信息需从环境查询
        SecurityLog.Write("[runtime-updater] WebView2 Runtime 新版本可用");
        
        // 通知 UI 层（如果有订阅者）
        _onUpdateAvailable?.Invoke();

        // 判定是否自动重启（生产环境应为 false——用户手动选择）
        if (_shouldRestart())
        {
            SecurityLog.Write("[runtime-updater] 自动重启已触发");
            _onRestartRequested?.Invoke();
        }
        else
        {
            SecurityLog.Write("[runtime-updater] 用户将手动重启以应用更新");
        }
    }

    public void Dispose()
    {
        if (_disposed)
            return;
        Unsubscribe();
        _disposed = true;
    }
}

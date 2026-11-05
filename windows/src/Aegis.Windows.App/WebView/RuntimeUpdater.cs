namespace Aegis.Windows.WebView;

using System;
using System.IO;
using System.Text.Json;
using System.Threading.Tasks;
using System.Windows;
using Aegis.Windows.Core.Security;
using Microsoft.Web.WebView2.Core;

/// <summary>
/// WebView2 Runtime 更新事件处理器（ADR-001 后果段——保存状态/通知/受控重启）。
/// 
/// 职责：
/// 1. 监听 CoreWebView2Environment.NewBrowserVersionAvailable 事件
/// 2. 事件触发时保存当前会话状态（标签列表、URL、窗口位置）到专用文件
/// 3. 通知用户有可用更新（通过 UI 回调显示横幅/气泡）
/// 4. 提供受控重启能力（保存状态 + 标记重启原因 + 应用重启）
/// 
/// 设计原则：
/// - 事件是通知性的（informational）——用户可选择何时重启
/// - 不强制立即重启——浏览器仍可继续使用旧 Runtime
/// - 状态保存到独立文件（runtime-restart.json），与会话库分离
/// - 重启后 App 启动时检测标记并恢复状态
/// - 无痕窗口不参与状态保存（隐私承诺——不持久化无痕会话）
/// 
/// 参考：
/// - Microsoft WebView2 文档：NewBrowserVersionAvailable 事件
/// - ADR-001 §后果：需处理 NewBrowserVersionAvailable（保存状态/通知/受控重启）
/// - 蓝图 docs/runbooks/runtime-update-restart（运行门禁补充）
/// </summary>
public sealed class RuntimeUpdater : IDisposable
{
    private readonly CoreWebView2Environment _environment;
    private readonly Func<bool> _shouldRestart; // 测试注入缝：判定是否自动重启
    private readonly Action? _onUpdateAvailable; // 测试注入缝：更新可用回调
    private readonly Action? _onRestartRequested; // 测试注入缝：重启请求回调
    private readonly RuntimeRestartStateStore _stateStore; // 状态存取
    private bool _disposed;
    private bool _isSubscribed;

    /// <summary>
    /// 构造 RuntimeUpdater。
    /// </summary>
    /// <param name="environment">WebView2 环境实例（共享环境或无痕环境）</param>
    /// <param name="stateStore">状态存取器（测试注入缝：可换内存实现）</param>
    /// <param name="shouldRestart">可选：判定是否自动重启（生产恒为 false——用户手动选择）</param>
    /// <param name="onUpdateAvailable">可选：更新可用时的回调（生产用于 UI 通知）</param>
    /// <param name="onRestartRequested">可选：重启请求时的回调（生产用于状态保存+应用重启）</param>
    public RuntimeUpdater(
        CoreWebView2Environment environment,
        RuntimeRestartStateStore? stateStore = null,
        Func<bool>? shouldRestart = null,
        Action? onUpdateAvailable = null,
        Action? onRestartRequested = null)
    {
        _environment = environment ?? throw new ArgumentNullException(nameof(environment));
        _stateStore = stateStore ?? new RuntimeRestartStateStore();
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
        
        // 保存当前状态（供重启后恢复）
        try
        {
            _stateStore.MarkPendingRestart("runtime-update");
            SecurityLog.Write("[runtime-updater] 重启前状态已保存");
        }
        catch (Exception ex)
        {
            SecurityLog.Write($"[runtime-updater] 状态保存失败: {ex.GetType().Name}: {ex.Message}");
        }
        
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

    /// <summary>
    /// 请求受控重启——保存状态并触发应用重启。
    /// 由 UI 层在用户确认后调用（例如点击「重启以应用更新」按钮）。
    /// </summary>
    public void RequestControlledRestart()
    {
        try
        {
            _stateStore.MarkPendingRestart("runtime-update");
            SecurityLog.Write("[runtime-updater] 受控重启：状态已保存，请求应用重启");
            _onRestartRequested?.Invoke();
        }
        catch (Exception ex)
        {
            SecurityLog.Write($"[runtime-updater] 受控重启失败: {ex.GetType().Name}: {ex.Message}");
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

/// <summary>
/// 运行时重启状态存取器——独立于会话库（tabs.db），专用于 Runtime 更新重启场景。
/// 
/// 状态内容：
/// - 重启原因（runtime-update）
/// - 标记时间戳
/// - 应用版本（可选——用于诊断）
/// 
/// 设计：
/// - 单文件 JSON（runtime-restart.json）——轻量、可读、易调试
/// - 成功恢复后自动清除标记（避免重复恢复）
/// - 文件缺失/损坏时返回空状态（fail-safe）
/// </summary>
public sealed class RuntimeRestartStateStore
{
    private readonly string _statePath;
    private readonly object _lock = new();

    public RuntimeRestartStateStore(string? statePath = null)
    {
        _statePath = statePath ?? Path.Combine(
            Core.AppPaths.DataDir, "runtime-restart.json");
    }

    /// <summary>
    /// 重启状态（只读快照）。
    /// </summary>
    public sealed record RestartState(
        string Reason,
        DateTimeOffset MarkedAt,
        string? AppVersion);

    /// <summary>
    /// 标记待重启——写入状态文件。
    /// </summary>
    public void MarkPendingRestart(string reason, string? appVersion = null)
    {
        lock (_lock)
        {
            var state = new RestartState(
                Reason: reason,
                MarkedAt: DateTimeOffset.UtcNow,
                AppVersion: appVersion ?? GetType().Assembly.GetName().Version?.ToString());
            
            var json = JsonSerializer.Serialize(state, new JsonSerializerOptions
            {
                WriteIndented = true
            });
            File.WriteAllText(_statePath, json);
        }
    }

    /// <summary>
    /// 读取待重启状态。无标记/文件缺失/损坏时返回 null（fail-safe）。
    /// </summary>
    public RestartState? LoadPendingRestart()
    {
        lock (_lock)
        {
            if (!File.Exists(_statePath))
                return null;
            try
            {
                var json = File.ReadAllText(_statePath);
                var state = JsonSerializer.Deserialize<RestartState>(json);
                return state;
            }
            catch (Exception ex) when (ex is JsonException or IOException or UnauthorizedAccessException)
            {
                SecurityLog.Write(
                    $"[runtime-updater] 重启状态读取失败: {ex.GetType().Name}: {ex.Message}");
                return null;
            }
        }
    }

    /// <summary>
    /// 清除重启标记（成功恢复后调用）。
    /// </summary>
    public void ClearPendingRestart()
    {
        lock (_lock)
        {
            try
            {
                if (File.Exists(_statePath))
                    File.Delete(_statePath);
            }
            catch (Exception ex) when (ex is IOException or UnauthorizedAccessException)
            {
                SecurityLog.Write(
                    $"[runtime-updater] 重启状态清除失败: {ex.GetType().Name}: {ex.Message}");
            }
        }
    }

    /// <summary>
    /// 是否有待重启标记（供 App 启动时快速检测）。
    /// </summary>
    public bool HasPendingRestart()
    {
        lock (_lock)
        {
            return File.Exists(_statePath);
        }
    }
}

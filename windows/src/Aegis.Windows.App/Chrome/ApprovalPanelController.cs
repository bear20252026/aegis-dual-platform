namespace Aegis.Windows.Chrome;

using System;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Input;
using Aegis.Windows.WebView;

/// <summary>导航确认面板控制器（MainWindow 上帝对象拆分·第三批）：单面板无
/// 队列——第二个确认请求到达时先拒绝前一个标签的挂起请求（此前直接覆盖
/// pendingId，前一个标签永远卡在 pending）。面板状态（含 pending 标签 id）
/// 由本控制器唯一持有。</summary>
public sealed class ApprovalPanelController
{
    private const string StaleMessage = "确认请求已失效、被拒绝或无法安全恢复导航。";
    private const string DeniedMessage = "已拒绝该导航请求。";

    private readonly FrameworkElement _overlay;
    private readonly TextBlock _origin;
    private readonly TextBlock _path;
    private readonly TextBlock _scope;
    private readonly TextBlock _expiry;
    private readonly Button _denyButton;
    private readonly Action<bool> _setNavigationEnabled;
    private readonly Func<string, TabRuntime?> _resolveRuntime;
    private readonly Action<string> _showRejection;

    /// <summary>当前挂起确认的标签 id（无挂起为 null）。</summary>
    public string? PendingTabId { get; private set; }

    /// <summary>面板是否可见（Escape 拦截等前提判断）。</summary>
    public bool IsVisible => _overlay.Visibility == Visibility.Visible;

    public ApprovalPanelController(
        FrameworkElement overlay,
        TextBlock origin,
        TextBlock path,
        TextBlock scope,
        TextBlock expiry,
        Button denyButton,
        Action<bool> setNavigationEnabled,
        Func<string, TabRuntime?> resolveRuntime,
        Action<string> showRejection)
    {
        _overlay = overlay ?? throw new ArgumentNullException(nameof(overlay));
        _origin = origin ?? throw new ArgumentNullException(nameof(origin));
        _path = path ?? throw new ArgumentNullException(nameof(path));
        _scope = scope ?? throw new ArgumentNullException(nameof(scope));
        _expiry = expiry ?? throw new ArgumentNullException(nameof(expiry));
        _denyButton = denyButton ?? throw new ArgumentNullException(nameof(denyButton));
        _setNavigationEnabled = setNavigationEnabled ?? throw new ArgumentNullException(nameof(setNavigationEnabled));
        _resolveRuntime = resolveRuntime ?? throw new ArgumentNullException(nameof(resolveRuntime));
        _showRejection = showRejection ?? throw new ArgumentNullException(nameof(showRejection));
    }

    /// <summary>登记并展示来自指定标签的确认请求。单面板无队列：先拒绝
    /// 前一个不同标签的挂起请求（fail-closed 且不可恢复覆盖）。</summary>
    public void Request(string tabId, NavigationConfirmationRequestedEventArgs e)
    {
        if (PendingTabId is { } previous
            && previous != tabId
            && _resolveRuntime(previous) is { } previousRuntime)
        {
            previousRuntime.Host.RejectPendingNavigation();
        }
        PendingTabId = tabId;
        _origin.Text = e.Request.Origin;
        _path.Text = e.Request.Path;
        _scope.Text = e.Request.Scope;
        _expiry.Text = $"此请求将在 {e.Request.ExpiresAt.ToLocalTime():yyyy-MM-dd HH:mm:ss} 过期。";
        _setNavigationEnabled(false);
        _overlay.Visibility = Visibility.Visible;
        Keyboard.Focus(_denyButton);
    }

    /// <summary>宿主侧已解决（无论允许/拒绝/过期）——仅撤面板。</summary>
    public void Resolved() => Hide();

    /// <summary>允许：pending 丢失/标签已销毁时唯一正确动作是撤面板 + 告知
    ///（对应标签的 Host 在销毁时已自行 fail-closed）。</summary>
    public void Allow()
    {
        // 审计修复语义保留：orphan 恢复分支不存在（字典永无 "" 键）；pending
        // 丢失时不尝试恢复导航
        if (PendingTabId is not { } pendingId
            || _resolveRuntime(pendingId) is not { } runtime
            || runtime.Control.CoreWebView2 is null)
        {
            Hide();
            _showRejection(StaleMessage);
            return;
        }
        if (!runtime.Host.ApprovePendingNavigation(runtime.Control.CoreWebView2))
            _showRejection(StaleMessage);
    }

    /// <summary>拒绝（按钮或 Escape）：通知宿主拒绝并告知用户。</summary>
    public void Deny()
    {
        if (PendingTabId is not null && _resolveRuntime(PendingTabId) is { } runtime)
            runtime.Host.RejectPendingNavigation();
        _showRejection(DeniedMessage);
    }

    private void Hide()
    {
        _overlay.Visibility = Visibility.Collapsed;
        _setNavigationEnabled(true);
        _origin.Text = string.Empty;
        _path.Text = string.Empty;
        _scope.Text = string.Empty;
        _expiry.Text = string.Empty;
        PendingTabId = null;
    }
}

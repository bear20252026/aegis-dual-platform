namespace Aegis.Windows.Core.Tabs;

using System;
using System.ComponentModel;
using System.Runtime.CompilerServices;
using System.Windows.Media;

/// <summary>标签模型（ADR-009 D2 领域层——纯数据，无 UI/WebView 依赖）。
/// Title/Url 经 INotifyPropertyChanged 通知原生标签条刷新。
/// 新增：IsPinned（固定标签前置且隐藏关闭钮）、IsSleeping（睡眠标签——
/// WebView 已释放仅存状态，激活时复活）、Icon（站点 favicon，Tab 更换时通知）。</summary>
public sealed class Tab : INotifyPropertyChanged
{
    private string _title;
    private string _url;
    private bool _isPinned;
    private bool _isSleeping;
    private ImageSource? _icon;
    private DateTime _lastActivated = DateTime.Now;

    public Tab(string tabId, string url, string title = "新标签页")
    {
        TabId = tabId;
        _url = url;
        _title = title;
    }

    public event PropertyChangedEventHandler? PropertyChanged;

    /// <summary>标签唯一标识（broker tabId——会话/授权账本绑定此键）。</summary>
    public string TabId { get; }

    /// <summary>当前 URL（地址栏同步/会话保存数据源）。</summary>
    public string Url
    {
        get => _url;
        set => SetField(ref _url, value);
    }

    /// <summary>页面标题（标签条/窗口标题）。</summary>
    public string Title
    {
        get => _title;
        set => SetField(ref _title, value);
    }

    /// <summary>固定标签：置于标签条前端、隐藏关闭钮、不参与睡眠。</summary>
    public bool IsPinned
    {
        get => _isPinned;
        set => SetField(ref _isPinned, value);
    }

    /// <summary>睡眠标签：WebView 实例已释放，仅保留 Url/Title；激活时复活。</summary>
    public bool IsSleeping
    {
        get => _isSleeping;
        set => SetField(ref _isSleeping, value);
    }

    /// <summary>站点图标（favicon 缓存命中后回填；null → 占位圆点）。</summary>
    public ImageSource? Icon
    {
        get => _icon;
        set => SetField(ref _icon, value);
    }

    /// <summary>最近激活时刻（睡眠计时依据）。</summary>
    public DateTime LastActivated
    {
        get => _lastActivated;
        set => SetField(ref _lastActivated, value);
    }

    private void SetField<T>(ref T field, T value, [CallerMemberName] string? name = null)
    {
        if (Equals(field, value))
            return;
        field = value;
        PropertyChanged?.Invoke(this, new PropertyChangedEventArgs(name));
    }
}

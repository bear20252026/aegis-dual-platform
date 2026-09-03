namespace Aegis.Windows.Core.Tabs;

using System;
using System.ComponentModel;
using System.Runtime.CompilerServices;

/// <summary>标签模型（ADR-009 D2 领域层——纯数据，无 UI/WebView 依赖）。
/// Title/Url 经 INotifyPropertyChanged 通知原生标签条刷新（修复 Python 栈
/// 「标签标题永不更新」缺陷的架构性方案——原生绑定，非注入 JS）。
/// TabId 同时作为 broker 会话的 tabId（ADR-002 唯一副作用点的账本键）。</summary>
public sealed class Tab : INotifyPropertyChanged
{
    private string _title;
    private string _url;

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

    private void SetField<T>(ref T field, T value, [CallerMemberName] string? name = null)
    {
        if (Equals(field, value))
            return;
        field = value;
        PropertyChanged?.Invoke(this, new PropertyChangedEventArgs(name));
    }
}

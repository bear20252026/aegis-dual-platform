namespace Aegis.Windows.Chrome;

using System;
using System.Windows;

/// <summary>源码查看窗口（M3）：源码 100% 全转义纯文本展示（零脚本执行），
/// Python api_bridge.view_source「查看源码永不等于执行源码」语义的正典栈实现。
/// CS-359（2026-10-01 审计）：非虚拟化 TextBox 直接塞 5MB 会冻结 UI——
/// 改首屏 256KB 预览 + 「加载全部」按钮（全量仍受抓取层 5MB 上限约束）。</summary>
public partial class SourceViewerWindow : Window
{
    /// <summary>首屏预览上限（字符）——TextBox 非虚拟化，5MB 全量排版即冻结。</summary>
    internal const int PreviewChars = 256 * 1024;

    private readonly string _fullSource;

    public SourceViewerWindow(string url, string source)
    {
        InitializeComponent();
        SourceUrl.Text = url;
        _fullSource = source;
        if (source.Length > PreviewChars)
        {
            // 全转义（含属性边界）——WPF TextBox 天然纯文本，仅截断超大首屏
            SourceText.Text = source[..PreviewChars];
            PreviewHint.Text = $"已加载前 {PreviewChars / 1024} KB 预览（全文 {source.Length / 1024} KB）——避免 5MB 全量排版冻结界面";
        }
        else
        {
            SourceText.Text = source;
            PreviewHint.Text = string.Empty;
            LoadAllButton.Visibility = Visibility.Collapsed;
        }
    }

    /// <summary>加载全部源码（用户显式请求——接受大文本排版开销）。
    /// internal：CS-359 冒烟测试直驱（构造预览 → 加载全部 → 全量呈现）。</summary>
    internal void LoadAll_Click(object sender, RoutedEventArgs e)
    {
        SourceText.Text = _fullSource;
        PreviewHint.Text = $"已加载全文（{_fullSource.Length / 1024} KB）";
        LoadAllButton.Visibility = Visibility.Collapsed;
    }

    /// <summary>统一深浅主题接入（此前 XAML 硬编码深色——浅色模式下与主窗口割裂）。
    /// 画刷键经 DynamicResource 引用，此处仅需写入窗口资源。</summary>
    public void ApplyTheme(string? theme) => WindowTheme.Apply(this, theme);
}

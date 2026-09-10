namespace Aegis.Windows.Chrome;

using System.Windows;

/// <summary>源码查看窗口（M3）：源码 100% 全转义纯文本展示（零脚本执行），
/// Python api_bridge.view_source「查看源码永不等于执行源码」语义的正典栈实现。</summary>
public partial class SourceViewerWindow : Window
{
    public SourceViewerWindow(string url, string source)
    {
        InitializeComponent();
        SourceUrl.Text = url;
        // 全转义（含属性边界）——WPF TextBox 天然纯文本，无需 HTML 转义，
        // 仅截断超大首屏（5MB 上限已在抓取层保证）
        SourceText.Text = source;
    }

    /// <summary>统一深浅主题接入（此前 XAML 硬编码深色——浅色模式下与主窗口割裂）。
    /// 画刷键经 DynamicResource 引用，此处仅需写入窗口资源。</summary>
    public void ApplyTheme(string? theme) => WindowTheme.Apply(this, theme);
}

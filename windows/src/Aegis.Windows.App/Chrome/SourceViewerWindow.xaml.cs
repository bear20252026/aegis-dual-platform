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

    private void SourceText_TextChanged(object sender, System.Windows.Controls.TextChangedEventArgs e)
    {
        // 占位：行号/搜索随 M4 设置界面迭代
    }
}

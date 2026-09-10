namespace Aegis.Windows.Chrome;

using System;
using System.Threading.Tasks;
using System.Windows;
using System.Windows.Controls;
using Microsoft.Web.WebView2.Core;

/// <summary>页内查找控制器（MainWindow 上帝对象拆分·第一批）：查找条开关、
/// 命中计数与 window.find 脚本执行。JS 构造为纯静态方法——转义与方向参数
/// 可脱离 WebView 单测。</summary>
public sealed class FindBarController
{
    private const string ClearJs = "window.find('', false, false, false);";

    private readonly FrameworkElement _bar;
    private readonly TextBox _box;
    private readonly TextBlock _count;
    private readonly Func<TabRuntime?> _activeRuntime;

    public FindBarController(
        FrameworkElement bar,
        TextBox box,
        TextBlock count,
        Func<TabRuntime?> activeRuntime)
    {
        _bar = bar ?? throw new ArgumentNullException(nameof(bar));
        _box = box ?? throw new ArgumentNullException(nameof(box));
        _count = count ?? throw new ArgumentNullException(nameof(count));
        _activeRuntime = activeRuntime ?? throw new ArgumentNullException(nameof(activeRuntime));
    }

    /// <summary>打开查找条并全选既有词（Ctrl+F 入口）。</summary>
    public void Open()
    {
        _bar.Visibility = Visibility.Visible;
        _box.Focus();
        _box.SelectAll();
    }

    /// <summary>收起查找条并清除页面高亮。</summary>
    public void Close()
    {
        _bar.Visibility = Visibility.Collapsed;
        _count.Text = string.Empty;
        if (_activeRuntime()?.Control.CoreWebView2 is { } cw)
            _ = cw.ExecuteScriptAsync(ClearJs);
    }

    /// <summary>执行一次查找：计数 + window.find（页面侧高亮/跳转）。
    /// WebView 已释放/竞态时静默放弃。</summary>
    public async Task SearchAsync(string? query, bool backwards)
    {
        if (string.IsNullOrWhiteSpace(query) || _activeRuntime()?.Control.CoreWebView2 is not { } cw)
            return;
        try
        {
            var count = await CountMatchesAsync(cw, query);
            await cw.ExecuteScriptAsync(BuildFindJs(query, backwards));
            _count.Text = count > 0 ? $"{count} 处" : "无结果";
        }
        catch (Exception) { }
    }

    private static async Task<int> CountMatchesAsync(CoreWebView2 cw, string query)
    {
        var res = await cw.ExecuteScriptAsync(BuildCountJs(query));
        return int.TryParse(res, out var n) ? n : 0;
    }

    /// <summary>window.find 脚本（纯函数）：query 经 JSON 序列化转义（引号/
    /// 反斜杠/换行注入面），第三参为方向，第四参环绕查找。</summary>
    public static string BuildFindJs(string query, bool backwards) =>
        "window.find(" + System.Text.Json.JsonSerializer.Serialize(query) +
        ", false, " + (backwards ? "true" : "false") + ", true);";

    /// <summary>命中计数脚本（纯函数）：innerText 非重叠计数，异常回 0。</summary>
    public static string BuildCountJs(string query)
    {
        var q = System.Text.Json.JsonSerializer.Serialize(query);
        return "new Promise(r=>{try{var m=(document.body&&document.body.innerText)||'';" +
               "var n=0,i=0,Q=" + q + ";while((i=m.indexOf(Q,i))!==-1){n++;i+=Q.length;}r(n);}catch(e){r(0);}});";
    }
}

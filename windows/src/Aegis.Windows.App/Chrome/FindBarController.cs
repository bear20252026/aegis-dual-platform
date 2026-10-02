namespace Aegis.Windows.Chrome;

using System;
using System.Threading.Tasks;
using System.Windows;
using System.Windows.Controls;
using Aegis.Windows.Core.Security;
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
        if (_activeRuntime()?.Control is { } control)
        {
            // CS-227：显式把焦点还给页面 WebView——此前收起后焦点悬空在
            // 已隐藏的查找条上，需再点一次页面才能继续滚动/输入
            control.Focus();
            if (control.CoreWebView2 is { } cw)
                _ = cw.ExecuteScriptAsync(ClearJs);
        }
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
        catch (Exception ex)
        {
            // CS-147：不再全吞——WebView 已释放/脚本竞态留痕安全日志（失败
            // 本身不影响浏览，但零痕迹使「查找无响应」不可诊断）
            SecurityLog.Write($"[findbar] 查找脚本执行失败: {ex.GetType().Name}: {ex.Message}");
        }
    }

    private static async Task<int> CountMatchesAsync(CoreWebView2 cw, string query)
    {
        // CS-338（2026-10-01 审计）：脚本改同步表达式——此前返回 Promise，
        // ExecuteScriptAsync 不等待 Promise 解析，序列化结果恒 "null"，
        // int.TryParse 失败 → 命中计数恒 0（查找条永远显示"无结果"）。
        // 返回值容错解析：数字字符串直取，其余形态（"null"/对象）回 0。
        var res = await cw.ExecuteScriptAsync(BuildCountJs(query));
        return int.TryParse(res?.Trim('"', ' '), out var n) ? n : 0;
    }

    /// <summary>window.find 脚本（纯函数）：query 经 JSON 序列化转义（引号/
    /// 反斜杠/换行注入面），第三参为方向，第四参环绕查找。</summary>
    public static string BuildFindJs(string query, bool backwards) =>
        "window.find(" + System.Text.Json.JsonSerializer.Serialize(query) +
        ", false, " + (backwards ? "true" : "false") + ", true);";

    /// <summary>命中计数脚本（纯函数）：同步 IIFE 表达式——ExecuteScriptAsync
    /// 直接返回其值（数字），无 Promise 形态。innerText 非重叠计数，异常回 0。
    /// 空查询防护：indexOf('') 恒命中且步进为 0 会死循环，前置长度短路。</summary>
    public static string BuildCountJs(string query)
    {
        var q = System.Text.Json.JsonSerializer.Serialize(query);
        return "(function(){try{var m=(document.body&&document.body.innerText)||'';" +
               "var n=0,i=0,Q=" + q + ";if(Q.length){while((i=m.indexOf(Q,i))!==-1){n++;i+=Q.length;}}" +
               "return n;}catch(e){return 0;}})()";
    }
}

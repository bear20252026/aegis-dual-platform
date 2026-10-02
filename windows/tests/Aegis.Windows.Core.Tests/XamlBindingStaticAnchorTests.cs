namespace Aegis.Windows.Core.Tests;

using System.Collections.Generic;
using System.IO;
using System.Reflection;
using Aegis.Windows.Chrome;
using Aegis.Windows.Core.Downloads;
using Aegis.Windows.Core.Tabs;
using Xunit;

/// <summary>CS-412（2026-10-02 审计）：XAML {Binding} 零静态锚补测——
/// 解析 windows/src/Aegis.Windows.App/Chrome/*.xaml 的 {Binding X} 路径，
/// 映射到条目模型类型（DownloadItem/HistoryRow/BookmarkRow/Tab/SuggestionRow）
/// 反射断言公共属性存在。WPF 绑定引擎对不存在的属性静默失配（运行期零报错
/// ——StateKind 曾以 internal 形态混过，DataTrigger 恒不触发），本测试把
/// 「模型属性改名/降级 internal」变成编译后的第二道静态锚。
/// 跳过约定（登记于 AssertableBindings）：RelativeSource/ElementName 绑定的
/// 来源被覆写为可视树宿主（ContentPresenter/TemplatedParent/命名元素），
/// 不指向条目模型——跳过；自绑定 {Binding}（空路径）与子路径（含 `.`）
/// 不属单属性锚——跳过。新增 XAML 绑定若无法映射宿主类型，须在注释登记。</summary>
public sealed class XamlBindingStaticAnchorTests
{
    /// <summary>XAML → 条目模型类型（DataContext 宿主）。同一文件多宿主时
    /// 「至少一个类型存在同名公共属性」即通过（保守口径——同页多列表宿主）。</summary>
    private static readonly Dictionary<string, Type[]> HostModels = new()
    {
        [nameof(DownloadsWindow)] = new[] { typeof(DownloadItem) },
        [nameof(HistoryWindow)] = new[]
        {
            typeof(HistoryWindow.HistoryRow),
            typeof(HistoryWindow.DateHeader),
        },
        [nameof(BookmarkManagerWindow)] = new[] { typeof(BookmarkManagerWindow.BookmarkRow) },
        [nameof(MainWindow)] = new[] { typeof(Tab), typeof(SuggestionRow) },
        [nameof(InPrivateWindow)] = new[] { typeof(Tab) },
        // 无 {Binding} 或仅有来源覆写绑定的文件不入表（DateField/ChromeStyles/
        // SettingsWindow/SourceViewerWindow——见 AssertableBindings 跳过约定）
    };

    [Fact]
    public void AllChromeXamlBindingsResolveToPublicModelProperties()
    {
        var chromeDir = FindChromeXamlDir();
        foreach (var xamlPath in Directory.GetFiles(chromeDir, "*.xaml"))
        {
            var fileName = Path.GetFileNameWithoutExtension(xamlPath);
            var bindings = AssertableBindings(fileName, File.ReadAllText(xamlPath)).ToList();
            if (!HostModels.TryGetValue(fileName, out var hosts))
            {
                Assert.True(bindings.Count == 0,
                    $"{fileName}.xaml 存在未映射宿主的绑定 [{string.Join(", ", bindings)}]" +
                    "——请把 DataContext 模型类型登记进 HostModels（或在跳过约定登记）");
                continue;
            }
            foreach (var path in bindings)
            {
                Assert.True(
                    hosts.Any(host => host.GetProperty(
                        path, BindingFlags.Public | BindingFlags.Instance) is not null),
                    $"{fileName}.xaml 的 {{Binding {path}}} 在宿主模型 " +
                    $"[{string.Join(", ", hosts.Select(h => h.Name))}] 上无公共属性" +
                    "（WPF 对缺失属性静默失配——绑定恒不生效）");
            }
        }
    }

    /// <summary>提取可静态锚定的绑定路径（跳过约定见类注释）。</summary>
    private static IEnumerable<string> AssertableBindings(string fileName, string xaml)
    {
        foreach (var expression in ExtractBindingExpressions(xaml))
        {
            if (expression.Contains("RelativeSource") || expression.Contains("ElementName"))
                continue;  // 来源覆写为可视树宿主——不指向条目模型（跳过约定）
            var body = expression["{Binding".Length..].TrimEnd('}').Trim();
            if (body.StartsWith("Path=", StringComparison.Ordinal))
                body = body["Path=".Length..];
            var path = body.Split(',')[0].Trim();
            if (path.Length == 0 || path.Contains('.'))
                continue;  // 自绑定（空路径）/子路径不属单属性锚（跳过约定）
            yield return path;
        }
    }

    /// <summary>平衡大括号截取完整绑定表达式（RelativeSource={...} 含嵌套）。</summary>
    private static IEnumerable<string> ExtractBindingExpressions(string xaml)
    {
        var idx = xaml.IndexOf("{Binding", StringComparison.Ordinal);
        while (idx >= 0)
        {
            var depth = 0;
            var end = xaml.Length - 1;
            for (var i = idx; i < xaml.Length; i++)
            {
                if (xaml[i] == '{')
                    depth++;
                else if (xaml[i] == '}')
                {
                    depth--;
                    if (depth == 0)
                    {
                        end = i;
                        break;
                    }
                }
            }
            yield return xaml.Substring(idx, end - idx + 1);
            idx = xaml.IndexOf("{Binding", end, StringComparison.Ordinal);
        }
    }

    /// <summary>向上定位 Chrome XAML 目录（测试输出层级随 RID 变化——逐级
    /// 上溯按仓库布局标记定位，不依赖固定层数）。</summary>
    private static string FindChromeXamlDir()
    {
        var dir = new DirectoryInfo(AppContext.BaseDirectory);
        while (dir is not null)
        {
            var candidate = Path.Combine(
                dir.FullName, "windows", "src", "Aegis.Windows.App", "Chrome");
            if (Directory.Exists(candidate))
                return candidate;
            dir = dir.Parent!;
        }
        // 显式 throw（Assert.Fail 标注 DoesNotReturn——其后不可达代码在
        // TreatWarningsAsErrors 下即 CS0162 编译错误）
        throw new InvalidOperationException(
            "未定位到 windows/src/Aegis.Windows.App/Chrome（仓库布局契约）");
    }
}

using System.Reflection;
using Microsoft.Web.WebView2.Core;

// Q58（台账 §五 = R9-CS-18）第一步：把「钉版 SDK 的下载面到底有什么」变成每次都能重跑的
// 机器可读记录，而不是某一次反射脚本的口头结论。
//
// 为什么需要它：Q58 的修法取决于一件我们没有事实的事——`CoreWebView2DownloadOperation.Uri`
// 报的是**入队时请求的地址**还是**跟随重定向之后的落点**。钉版 SDK 自带的 XML 文档对这一句
// 只写了 “The URI of the download.”（现读 `~/.nuget/packages/microsoft.web.webview2/
// 1.0.2903.40/lib/net462/Microsoft.Web.WebView2.Core.xml`），官方文本没答；
// 而 R9-B43 在 Android 侧能复判，靠的是 DownloadProvider 会改写 `COLUMN_URI` 这条平台事实。
//
// 本探针能稳定回答的（也是它现在只做的）：
//   · Runtime 版本与 SDK 程序集版本（compat 工作流本职就是盯 Runtime 两周一次的更新）；
//   · 下载相关类型的**属性面与事件面**——R9-B37 记过「本 SDK 只有 BytesReceivedChanged /
//     EstimatedEndTimeChanged / StateChanged 三个事件、没有 Completed」，那是反射一次的结论，
//     这里让它每次重跑；
//   · 全量 `*Download*` 类型清单——上游哪天补上「完成后」那一族，这份报告会自己长出来，
//     不需要有人记得去读 changelog。
//
// 本探针**答不出**的，以及为什么（这条是它自己的实测边界，写在这儿而不是埋在讨论里）：
// 量「Uri 跟随不跟随重定向」要真起一次下载。本机试做过一次独立宿主（不可见窗口 +
// loopback 双端口 + 302→附件），卡在订阅事件这一步：
//     NotImplementedException: Unable to cast to ICoreWebView2_4
//         at CoreWebView2.add_DownloadStarting(...)
// 也就是说「一次性探针宿主」与「出货 App 的宿主」不是同一个环境，探针造不出可信的下载场景；
// 那一条只能在跑着的 App 里量（=装机/桌面实测面，见 Q58 的验收口径）。据此本探针**只做静态面**，
// 不留一份跑不起来的双分叉代码。
//
// 退出码纪律：0=三面都拿到；2=拿不到（SDK 程序集缺失 / Runtime 版本读不出），并打
// `PROBE_ERROR` 说明断在哪一步——绝不静默。语义结论不是断言：报告是给人读的事实表。

return Probe.Run(args);

internal static class Probe
{
    internal static int Run(string[] args)
    {
        if (args.Length > 0)
        {
            return Fail($"未知参数 {args[0]}（本探针只有默认的静态模式）");
        }
        try
        {
            return Surface();
        }
        catch (Exception e)
        {
            // 栈要一起打：第一次撞「Unable to cast to ICoreWebView2_4」时没有栈，
            // 就只能猜是哪一行在转型（起环境？加事件？导航？）——猜出来的修法会把自己带偏。
            Console.WriteLine("stack_begin");
            Console.WriteLine(e.StackTrace);
            return Fail(e.GetType().Name + ": " + e.Message.Split('\n')[0]);
        }
    }

    internal static int Fail(string why)
    {
        Console.WriteLine($"PROBE_ERROR {why}");
        return 2;
    }

    private static int Surface()
    {
        Assembly sdk;
        try
        {
            sdk = typeof(CoreWebView2Environment).Assembly;
        }
        catch (Exception e)
        {
            return Fail($"SDK 程序集加载失败：{e.GetType().Name} {e.Message}");
        }

        Console.WriteLine($"sdk_assembly={sdk.GetName().FullName}");
        try
        {
            Console.WriteLine($"runtime_version={CoreWebView2Environment.GetAvailableBrowserVersionString()}");
        }
        catch (Exception e)
        {
            return Fail($"WebView2 Runtime 不可用：{e.GetType().Name} {e.Message}");
        }

        foreach (var name in TypesOfInterest)
        {
            var type = sdk.GetType("Microsoft.Web.WebView2.Core." + name, throwOnError: false);
            if (type is null)
            {
                // 缺席本身就是答案（钉版里没有「下载完成」那一族事件参数）。
                Console.WriteLine($"TYPE_ABSENT {name}");
                continue;
            }

            Console.WriteLine($"TYPE {name}");
            foreach (var p in type.GetProperties(BindingFlags.Public | BindingFlags.Instance | BindingFlags.Static)
                         .OrderBy(p => p.Name, StringComparer.Ordinal))
            {
                Console.WriteLine($"  PROP {p.Name} : {p.PropertyType.Name}");
            }
            foreach (var e in type.GetEvents(BindingFlags.Public | BindingFlags.Instance)
                         .OrderBy(e => e.Name, StringComparer.Ordinal))
            {
                Console.WriteLine($"  EVENT {e.Name} : {e.EventHandlerType?.Name ?? "?"}");
            }
            if (type.IsEnum)
            {
                Console.WriteLine($"  ENUM_VALUES {string.Join(",", Enum.GetNames(type))}");
            }
        }

        Type[] all;
        try
        {
            all = sdk.GetTypes();
        }
        catch (ReflectionTypeLoadException e)
        {
            all = [.. e.Types.Where(t => t is not null).Select(t => t!)];
            Console.WriteLine($"PROBE_WARN partial_type_load {e.LoaderExceptions.Length}");
        }
        foreach (var t in all.Where(t => t.Name.Contains("Download", StringComparison.Ordinal))
                     .OrderBy(t => t.FullName, StringComparer.Ordinal))
        {
            Console.WriteLine($"SDK_DOWNLOAD_TYPE {t.FullName}");
        }
        return 0;
    }

    // 故意把钉版里**不存在**的两个名字列进来：期望输出是 TYPE_ABSENT。哪天 SDK 补上了，
    // 同一份报告里它自己从 ABSENT 变成 TYPE——判据不依赖任何人重读上游 changelog。
    private static readonly string[] TypesOfInterest =
    [
        "CoreWebView2DownloadOperation",
        "CoreWebView2DownloadStartingEventArgs",
        "CoreWebView2DownloadCompletedEventArgs",
        "CoreWebView2DownloadCompletedHandler",
        "CoreWebView2DownloadState",
    ];
}

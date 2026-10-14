using System.IO;
using System.Net;
using System.Net.Sockets;
using System.Text;
using System.Text.RegularExpressions;
using Microsoft.Web.WebView2.Core;
using Microsoft.Web.WebView2.WinForms;

// Q58 的动态测量（`--redirect`）。与静态面同一个工具，但**刻意不进 compat**：
// 它要有可用的浏览器宿主，属于「装机/桌面实测面」。
//
// 宿主用 **WinForms 的 WebView2 控件 + EnsureCoreWebView2Async**，与正典 App 同一条初始化路径
// （App 是 WPF 控件，两者走同一套 Environment/Controller 装配）。第一版用的是裸
// `CreateCoreWebView2ControllerAsync(hwnd)`，在订阅 `DownloadStarting` 时就抛
// `NotImplementedException: Unable to cast to ICoreWebView2_4`——当时记的结论是
// 「一次性宿主造不出可信场景」，现在看更准确的说法是「我用了一条 App 不走的路径」。
//
// 要答的问题只有一句：`CoreWebView2DownloadOperation.Uri` 报的是**入队时请求的地址**，
// 还是**跟随重定向之后的落点**？钉版 SDK 的 XML 文档只写 `The URI of the download.`（不答），
// 而 Windows 侧的下载闸门判的就是这个属性 ⇒ 结论决定 Q58 到底是缺口还是伪缺口。
//
// 三个场景一次跑完（不拿单点测量下 P2 判定）：
//   S1 一跳：origin /start → 302 → target /final.bin
//   S2 两跳：origin /start2 → 302 → /mid → 302 → target /final2.bin（报最后一跳还是第一跳）
//   S3 页面内触发：origin /page 返回 HTML，脚本 click() 一个 `href="/start3" download` 的链接
//      ——真实点击形态与「直接导航到下载地址」不是同一条路径
// 用不同端口而不是同端口不同路径，是为了让结论变成一次字符串比较，不需要解释。
//
// 卫生：窗口 off-screen + 透明；下载文件与用户数据目录都在 %TEMP% 的一次性目录里，跑完即删；
// 每个场景各自打印 `written=`（第一版只打了一个总数，出现「file_written=False」这种解释不了的黑话）。
//
// 本机实测结果（2026-10-14，Runtime 155.0.4283.45 + SDK 1.0.2903.40，三场景同一结论）：
//   S1 一跳 / S2 两跳 / S3 页面内 click —— 在 DownloadStarting 那一刻 `Uri` 就已经是**最后一跳的落点**，
//   到 Completed 也不变。⇒ 台账 Q58 原来那句「Windows 闸门判的是入队地址」在**这条属性上不成立**：
//   跟随重定向后的地址就是它判的那个。真正的缺口在别处（见 §3.57）：Windows 的下载判定只有
//   扩展名与确认，没有 Android 侧 R8-AD-03 那条「保留地址/云元数据硬拒」——
//   而 `Uri` 既然是落点，补那条就是纯策略活儿，不需要任何跳转解析改造。

internal static class RedirectProbe
{
    private static readonly byte[] Payload = "aegis-q58-probe-payload"u8.ToArray();

    internal static int Run()
    {
        var scratch = Path.Combine(Path.GetTempPath(), $"aegis_wv2_probe_{Guid.NewGuid():N}");
        Directory.CreateDirectory(scratch);
        using var origin = new LoopbackServer();
        using var target = new LoopbackServer();
        Route(origin, target);

        var scenarios = new (string Name, string Url, string ExpectedFinal)[]
        {
            ("S1", $"{origin.Base}{StartPath}", $"{target.Base}/final.bin"),
            ("S2", $"{origin.Base}/start2", $"{target.Base}/final2.bin"),
            ("S3", $"{origin.Base}/page", $"{target.Base}/final3.bin"),
        };
        foreach (var s in scenarios)
        {
            Console.WriteLine($"scenario {s.Name} entry={s.Url} redirect_target={s.ExpectedFinal}");
        }

        string? fatal = null;
        var thread = new Thread(() =>
        {
            try
            {
                Session.Run(scratch, scenarios);
            }
            catch (Exception e)
            {
                fatal = $"{e.GetType().Name}: {e.Message.Split('\n')[0]}";
                Console.WriteLine("stack_begin");
                Console.WriteLine(e.StackTrace);
            }
        });
        thread.SetApartmentState(ApartmentState.STA);
        thread.IsBackground = true;
        thread.Start();
        if (!thread.Join(TimeSpan.FromSeconds(180)))
        {
            Console.WriteLine("PROBE_ERROR 宿主线程 180s 未收工");
            return 2;
        }
        var written = Directory.GetFiles(scratch, "payload-*.bin").Length;
        Console.WriteLine($"payload_files={written}/{scenarios.Length}");
        try { Directory.Delete(scratch, true); } catch (IOException) { }
        return fatal is null ? 0 : Probe.Fail(fatal);
    }

    private const string StartPath = "/start";

    private static void Route(LoopbackServer origin, LoopbackServer target)
    {
        origin.OnGet = path =>
        {
            if (path.StartsWith("/start2", StringComparison.Ordinal)) return HttpReply.Redirect($"{origin.Base}/mid");
            if (path.StartsWith("/mid", StringComparison.Ordinal)) return HttpReply.Redirect($"{target.Base}/final2.bin");
            if (path.StartsWith("/start3", StringComparison.Ordinal)) return HttpReply.Redirect($"{target.Base}/final3.bin");
            if (path.StartsWith("/page", StringComparison.Ordinal))
            {
                return HttpReply.Html(
                    "<a id=\"d\" href=\"" + origin.Base + "/start3\" download=\"x\">go</a>" +
                    "<script>document.getElementById('d').click();</script>");
            }
            if (path.StartsWith(StartPath, StringComparison.Ordinal)) return HttpReply.Redirect($"{target.Base}/final.bin");
            return HttpReply.NotFound();
        };
        target.OnGet = path => path.Contains("final", StringComparison.Ordinal)
            ? HttpReply.Attachment(Payload)
            : HttpReply.NotFound();
    }

    private static string Snapshot(CoreWebView2DownloadOperation op)
    {
        string uri;
        try
        {
            uri = op.Uri ?? "NULL";
        }
        catch (Exception e)
        {
            uri = "READ_FAIL:" + e.GetType().Name;
        }
        return $"uri={uri} state={op.State} received={op.BytesReceived}";
    }

    private static string Classify(string snapshot, string entryUrl, string expectedFinal)
    {
        var m = Regex.Match(snapshot, @"uri=(\S+)");
        if (!m.Success) return "none";
        var uri = m.Groups[1].Value;
        if (uri == entryUrl) return "original";
        if (uri == expectedFinal) return "final";
        return uri.Contains("FAIL", StringComparison.Ordinal) ? "unreadable" : "other:" + uri;
    }

    /// <summary>一次会话里顺序跑完三个场景：每次 `Navigate` 后等这一单下到终态再走下一个。</summary>
    private static class Session
    {
        internal static void Run(string scratch, (string Name, string Url, string ExpectedFinal)[] scenarios)
        {
            using var form = new Form
            {
                StartPosition = FormStartPosition.Manual,
                Location = new Point(-32000, -32000),
                Opacity = 0d,
                ShowInTaskbar = false,
                FormBorderStyle = FormBorderStyle.FixedToolWindow,
                Size = new Size(320, 200),
            };
            var view = new WebView2 { Dock = DockStyle.Fill };
            form.Controls.Add(view);
            var env = CoreWebView2Environment.CreateAsync(null, Path.Combine(scratch, "wv2")).GetAwaiter().GetResult();

            var exit = new ManualResetEventSlim(false);
            form.Shown += async (_, _) =>
            {
                try
                {
                    await view.EnsureCoreWebView2Async(env);
                    var core = view.CoreWebView2;
                    for (var i = 0; i < scenarios.Length; i++)
                    {
                        var (name, url, expectedFinal) = scenarios[i];
                        var settled = new TaskCompletionSource<string>(TaskCreationOptions.RunContinuationsAsynchronously);
                        var startLine = string.Empty;

                        void OnStarting(object? _, CoreWebView2DownloadStartingEventArgs e)
                        {
                            var op = e.DownloadOperation;
                            if (op is null)
                            {
                                settled.TrySetResult("uri=OP_NULL");
                                return;
                            }
                            startLine = Snapshot(op);
                            e.ResultFilePath = Path.Combine(scratch, $"payload-{name}.bin");
                            op.StateChanged += (_, _) =>
                            {
                                if (op.State is CoreWebView2DownloadState.Completed or CoreWebView2DownloadState.Interrupted)
                                {
                                    settled.TrySetResult(startLine + " || " + Snapshot(op) +
                                                          " written=" + File.Exists(e.ResultFilePath));
                                }
                            };
                        }

                        core.DownloadStarting += OnStarting;
                        core.Navigate(url);
                        var winner = await Task.WhenAny(settled.Task, Task.Delay(TimeSpan.FromSeconds(60)));
                        core.DownloadStarting -= OnStarting;
                        var endLine = winner == settled.Task ? settled.Task.Result : "TIMEOUT";
                        Console.WriteLine($"RESULT {name} start[{startLine}] end[{endLine}]");
                        Console.WriteLine($"verdict {name} start={Classify(startLine, url, expectedFinal)} " +
                                          $"end={Classify(endLine, url, expectedFinal)}");
                    }
                }
                catch (Exception e)
                {
                    Console.WriteLine($"session_failure {e.GetType().Name}: {e.Message.Split('\n')[0]}");
                    throw;
                }
                finally
                {
                    exit.Set();
                    Application.ExitThread();
                }
            };
            Application.Run(form);
            exit.Wait(TimeSpan.FromSeconds(5));
        }
    }
}

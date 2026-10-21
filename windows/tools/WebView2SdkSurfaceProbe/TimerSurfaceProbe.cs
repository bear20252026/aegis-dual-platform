using System.IO;
using System.Text.Json;
using System.Windows.Forms;
using Microsoft.Web.WebView2.Core;
using Microsoft.Web.WebView2.WinForms;

// Q57/Q25（六条高解析通道）的一次可重跑测量：引擎默认给站点多细的时间。
//
// 为什么要量：Q57 剩下的那半句是「rAF／`getEntries*`／`Event.timeStamp`／`timeOrigin` 的圆整
// 是站点可观察的行为变更，只能由真机/桌面冒烟证明」——这句话要 owner 给话，而给话需要的
// 数字我们从来没有过。本批**不改任何判定面**，只把这六个数字量出来记进台账。
//
// 静态前提（同批现读，不是假设）：Windows `FingerprintShield.cs` 与 Android
// `WebViewHardeningStagesShield.kt` 对 `getEntriesByType`／`getEntriesByName`／`timeOrigin`／
// `requestAnimationFrame`／`timeStamp` 五个词**零命中**——两端对这六条通道一条都不裹。
// 所以「引擎默认」在这两端就等于「出货后可见面」，本探针不需要引用正点 App 的注入文本。
// 这条等价关系写在报告里，免得下一轮把它当理所当然。
//
// 宿主路径沿用 `--redirect` 那一套：WinForms 的 WebView2 控件 + `EnsureCoreWebView2Async`。
// 不用裸 `CreateCoreWebView2ControllerAsync(hwnd)`——§3.56 记过一次：那条路在
// `add_DownloadStarting` 上抛 `Unable to cast to ICoreWebView2_4`，当时据此得出的「量不到」
// 是假的（§3.57 自纠）。控件路径与正典 App 同一条初始化。
//
// 页面从 loopback http 起（不是 NavigateToString）：时间戳精度与 `crossOriginIsolated`
// 在 about:blank／data: 与真 http 源下不是一回事，量错上下文等于没量。
//
// 退出码纪律与 `--surface` 同：0=六项都拿到；2=任一项缺失并打 `PROBE_ERROR`，绝不静默。

internal static class TimerSurfaceProbe
{
    internal static int Run()
    {
        var scratch = Path.Combine(Path.GetTempPath(), "aegis_timer_probe");
        Directory.CreateDirectory(scratch);
        var payload = new string?[1];
        var failure = new string?[1];

        // COM 套间必须在建线程前定：WebView2 的 WinForms 宿主只能站 STA。
        // 本工程的入口是控制台 Main（MTA），直接在主线程 ShowDialog 会撞
        // `RPC_E_CHANGED_MODE`（本机实测）——`--redirect` 走的也是这条 STA 线程。
        var thread = new Thread(() =>
        {
            try
            {
                payload[0] = Session.Run(scratch);
            }
            catch (Exception exc)
            {
                failure[0] = $"未捕获异常：{exc.GetType().Name}: {exc.Message}";
            }
        });
        thread.SetApartmentState(ApartmentState.STA);
        thread.Start();
        if (!thread.Join(TimeSpan.FromSeconds(120)))
        {
            Console.WriteLine("PROBE_ERROR 计时面超时（120s）：宿主线程未回，绝不静等");
            return 2;
        }

        if (failure[0] is not null || payload[0] is null)
        {
            Console.WriteLine($"PROBE_ERROR 计时面未能全量取得::{failure[0] ?? "脚本返回空"}");
            return 2;
        }
        return Report(JsonDocument.Parse(Unwrap(payload[0]!)).RootElement);
    }

    /// <summary>一次会话：起 loopback 页 → 控件加载 → 采数 → 关消息循环，返回 JSON 文本。</summary>
    private static class Session
    {
        internal static string Run(string scratch)
        {
            using var server = new LoopbackServer { OnGet = _ => HttpReply.Html(Page()) };
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
            var json = new string[1];
            var failure = new string[1];

            form.Shown += async (_, _) =>
            {
                try
                {
                    var env = await CoreWebView2Environment.CreateAsync(null, Path.Combine(scratch, "wv2"));
                    await view.EnsureCoreWebView2Async(env);
                    view.CoreWebView2.Navigate($"{server.Base}/");
                }
                catch (Exception exc)
                {
                    failure[0] = $"初始化失败：{exc.GetType().Name}: {exc.Message}";
                    Application.ExitThread();
                }
            };
            view.NavigationCompleted += async (_, _) =>
            {
                try
                {
                    await view.ExecuteScriptAsync(StartRaf);
                    await Task.Delay(700);
                    json[0] = await view.ExecuteScriptAsync(ReadAll);
                }
                catch (Exception exc)
                {
                    failure[0] = $"取值失败：{exc.GetType().Name}: {exc.Message}";
                }
                finally
                {
                    Application.ExitThread();
                }
            };

            // 兜底：任何一步没回（导航失败、脚本不返回）都不许把进程挂住
            var watchdog = new System.Threading.Timer(
                _ =>
                {
                    try
                    {
                        form.Invoke(() => Application.ExitThread());
                    }
                    catch (Exception)
                    {
                        // 窗口已销毁：ExitThread 已经发生过，不必再报
                    }
                },
                null, TimeSpan.FromSeconds(60), Timeout.InfiniteTimeSpan);
            Application.Run(form);
            watchdog.Dispose();

            if (failure[0] is not null)
            {
                throw new InvalidOperationException(failure[0]!);
            }
            return json[0] ?? throw new InvalidOperationException("脚本返回空");
        }
    }

    /// <summary>`ExecuteScriptAsync` 把返回值编码成 JSON 字符串字面量，先剥一层。</summary>
    private static string Unwrap(string raw) =>
        JsonDocument.Parse(raw).RootElement.ValueKind == JsonValueKind.String
            ? raw[1..^1].Replace("\\\"", "\"").Replace("\\\\", "\\")
            : raw;

    private static int Report(JsonElement root)
    {
        var missing = new List<string>();
        string Get(string name)
        {
            if (!root.TryGetProperty(name, out var value) || value.ValueKind is JsonValueKind.Null)
            {
                missing.Add(name);
                return "?";
            }
            return value.ToString();
        }

        Console.WriteLine($"runtime={Get("rv")} ua={Get("ua")}");
        Console.WriteLine($"timers now_min_delta_us={Get("nowMin")}");
        Console.WriteLine($"timers prototype_bypass_min_delta_us={Get("protoMin")}");
        Console.WriteLine($"timers raf_min_delta_us={Get("rafMin")}");
        Console.WriteLine($"timers event_timestamp_frac={Get("evtFrac")} timeOrigin_frac={Get("originFrac")}");
        Console.WriteLine($"timers mark_startTime_frac={Get("markFrac")} entries_getEntriesByType={Get("markCount")}");
        Console.WriteLine($"timers crossOriginIsolated={Get("coi")} sharedArrayBuffer={Get("sab")}");
        Console.WriteLine("timers premise=两端对六条通道零包裹（现读 FingerprintShield.cs / WebViewHardeningStagesShield.kt 五个词 0 命中）⇒ 引擎默认即出货可见面");

        if (missing.Count > 0)
        {
            Console.WriteLine($"PROBE_ERROR 计时面缺项：{string.Join(",", missing)}");
            return 2;
        }
        return 0;
    }

    internal static string Page() =>
        """
        <!doctype html><meta charset=utf-8><title>timer-surface</title>
        <script>window.__raf=[];let __last=null;
        function __step(t){window.__raf.push(t);if(window.__raf.length<40)requestAnimationFrame(__step);}</script>
        """;

    // 六个通道各取「最小非零步进」或「小数尾数」——这是分辨率的直接读数，不是推断。
    internal const string StartRaf = "requestAnimationFrame(function s(t){window.__raf.push(t);" +
        "if(window.__raf.length<40)requestAnimationFrame(s);});void 0";

    internal const string ReadAll = """
        (function () {
          var min = function (arr) { var best = -1; arr.forEach(function (d) {
            if (d > 0 && (best < 0 || d < best)) best = d; }); return best; };
          var deltas = [], a = performance.now();
          for (var i = 0; i < 3000; i++) { var b = performance.now(); if (b > a) { deltas.push(b - a); a = b; } }
          var proto = [], c = Performance.prototype.now.call(performance);
          for (var j = 0; j < 3000; j++) { var d = Performance.prototype.now.call(performance);
            if (d > c) { proto.push(d - c); c = d; } }
          var raf = (window.__raf || []).slice(1).map(function (t, k) { return t - window.__raf[k]; });
          performance.mark('probe-mark');
          var marks = performance.getEntriesByType('mark');
          var frac = function (x) { var s = (x === undefined || x === null) ? '' : String(x);
            var dot = s.indexOf('.'); return dot < 0 ? 'no-fraction' : s.slice(dot + 1); };
          var ev = new Event('probe');
          var rv = (navigator.userAgent.match(/Chrome\/([\d.]+)/) || [])[1] || '?';
          return JSON.stringify({
            rv: rv, ua: navigator.userAgent.slice(0, 40),
            nowMin: min(deltas), protoMin: min(proto), rafMin: min(raf),
            evtFrac: frac(ev.timeStamp), originFrac: frac(performance.timeOrigin).slice(0, 12),
            markFrac: frac(marks.length ? marks[0].startTime : null), markCount: marks.length,
            coi: String(self.crossOriginIsolated), sab: typeof SharedArrayBuffer
          });
        })()
        """;
}

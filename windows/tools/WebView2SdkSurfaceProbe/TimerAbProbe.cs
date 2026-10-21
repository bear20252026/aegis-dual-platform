using System.IO;
using System.Text.Json;
using System.Windows.Forms;
using Microsoft.Web.WebView2.Core;
using Microsoft.Web.WebView2.WinForms;

// R9-B97：Q57 剩下的那半边要的不是推理，是「裹了之后站点看到什么」的两组数字。
//
// 为什么要 A/B 而不是再引一次 §3.74：§3.74 量的是**引擎默认**（两端对六条通道零包裹，
// 所以默认＝出货可见面）。它给出 100µs 网格，却没给出「按核心 Stage-8 那样圆整到 1ms + jitter
// 之后，页内动画与性能读数会变成什么」。那句话一直被写成「需真机/桌面冒烟」，而本机就跑得动
// WebView2——把「需要用户给话」的前提先用数字填掉，才是这一批的产出。
//
// 注入的文本是 `contracts/timer-stage8-script.js`，由 `TimerPrecision::new().inject_script()`
// 逐字节生成，并由 `core/rust-policy-core/tests/timer_parity.rs::stage8_golden_matches_the_generated_script_byte_for_byte`
// 钉住（本批写这条测试的过程中它当场判红两次：分隔换行剥多剥少都算漂移）。
// 探针**不重写**代表形态——自己手写一份裹法，量到的是自己的重写而不是核心。
//
// 宿主沿用 `--timers` 那一套：STA 线程 + WinForms 控件 + loopback http 源；
// 两个阶段在同一控件上两次导航（document-start 脚本只对之后的导航生效）。
// 退出码纪律同 `--surface`：任一阶段缺项 ⇒ 2，绝不静默出半份数字。

internal static class TimerAbProbe
{
    internal static int Run(string[] args)
    {
        var scriptPath = Locate(args.Length > 1 ? args[1] : null);
        if (scriptPath is null)
        {
            Console.WriteLine("PROBE_ERROR 找不到金样本 contracts/timer-stage8-script.js"
                + "（可用第二个参数给绝对路径）");
            return 2;
        }

        var script = File.ReadAllText(scriptPath);
        var payloads = new string?[2];
        var failure = new string?[1];

        var thread = new Thread(() =>
        {
            try
            {
                payloads = Session.Run(script);
            }
            catch (Exception exc)
            {
                failure[0] = $"未捕获异常：{exc.GetType().Name}: {exc.Message}";
            }
        });
        thread.SetApartmentState(ApartmentState.STA);
        thread.Start();
        if (!thread.Join(TimeSpan.FromSeconds(180)))
        {
            Console.WriteLine("PROBE_ERROR A/B 超时（180s）：宿主线程未回，绝不静等");
            return 2;
        }

        if (failure[0] is not null || payloads[0] is null || payloads[1] is null)
        {
            Console.WriteLine($"PROBE_ERROR A/B 未取得两组读数::{failure[0] ?? "阶段缺失"}");
            return 2;
        }

        return Report(
            JsonDocument.Parse(Unwrap(payloads[0]!)).RootElement,
            JsonDocument.Parse(Unwrap(payloads[1]!)).RootElement);
    }

    /// <summary>从可执行文件位置向上找仓库里的金样本；找不到返回 null（不猜路径）。</summary>
    private static string? Locate(string? explicitPath)
    {
        if (explicitPath is not null && File.Exists(explicitPath))
        {
            return explicitPath;
        }

        var dir = new DirectoryInfo(AppContext.BaseDirectory);
        for (var hop = 0; hop < 10 && dir is not null; hop++, dir = dir.Parent)
        {
            var candidate = Path.Combine(dir.FullName, "contracts", "timer-stage8-script.js");
            if (File.Exists(candidate))
            {
                return candidate;
            }
        }

        return null;
    }

    private static string Unwrap(string raw) =>
        JsonDocument.Parse(raw).RootElement.ValueKind == JsonValueKind.String
            ? raw[1..^1].Replace("\\\"", "\"").Replace("\\\\", "\\")
            : raw;

    private static class Session
    {
        internal static string?[] Run(string script)
        {
            using var server = new LoopbackServer { OnGet = _ => HttpReply.Html(TimerSurfaceProbe.Page()) };
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
            var payloads = new string?[2];
            var phase = new int[1];
            var failure = new string?[1];
            var done = new bool[1];

            form.Shown += async (_, _) =>
            {
                try
                {
                    var scratch = Path.Combine(Path.GetTempPath(), "aegis_timer_ab");
                    Directory.CreateDirectory(scratch);
                    var env = await CoreWebView2Environment.CreateAsync(null, scratch);
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
                if (done[0] || failure[0] is not null)
                {
                    return;                     // 一次导航只走一遍；失败后不重试
                }

                var slot = phase[0];
                if (slot >= 2)
                {
                    return;
                }

                try
                {
                    await view.ExecuteScriptAsync(TimerSurfaceProbe.StartRaf);
                    await Task.Delay(900);      // 40 帧在 60Hz 下约 670ms，留抖动余量
                    payloads[slot] = await view.ExecuteScriptAsync(Collect);
                }
                catch (Exception exc)
                {
                    failure[0] = $"阶段 {slot} 取值失败：{exc.GetType().Name}: {exc.Message}";
                    Application.ExitThread();
                    return;
                }

                phase[0]++;
                if (phase[0] == 1)
                {
                    // document-start 脚本只对**之后**的导航生效，所以 B 阶段必须重新导航。
                    await view.CoreWebView2.AddScriptToExecuteOnDocumentCreatedAsync(script);
                    view.CoreWebView2.Navigate($"{server.Base}/?wrapped=1");
                    return;
                }

                done[0] = true;
                Application.ExitThread();
            };

            var watchdog = new System.Threading.Timer(
                _ =>
                {
                    try
                    {
                        form.Invoke(() => Application.ExitThread());
                    }
                    catch (Exception)
                    {
                        // 窗口已销毁
                    }
                },
                null, TimeSpan.FromSeconds(120), Timeout.InfiniteTimeSpan);
            Application.Run(form);
            watchdog.Dispose();

            if (failure[0] is not null)
            {
                throw new InvalidOperationException(failure[0]!);
            }

            return payloads;
        }
    }

    /// <summary>
    /// 一组读数：分辨率（最小步进、小数尾数）、单调性（回退次数）、可检测性
    /// （是否 native、自有属性、描述符形态）。回退计数是 A/B 的关键——
    /// 核心给 `performance.now` 装了高水位钳位，却**没有**给 rAF 回调的时间戳装。
    /// </summary>
    private const string Collect = """
        (function () {
          var raf = window.__raf || [];
          var nowMin = -1, prev = performance.now(), regress = 0;
          for (var i = 0; i < 3000; i++) {
            var t = performance.now(), d = t - prev;
            if (t < prev) regress++;
            if (d > 0 && (nowMin < 0 || d < nowMin)) nowMin = d;
            prev = t;
          }
          var rafMin = -1, rafRegress = 0, intervals = [];
          for (var j = 1; j < raf.length; j++) {
            var q = raf[j] - raf[j - 1];
            if (q < 0) rafRegress++;
            if (q > 0) { intervals.push(q); if (rafMin < 0 || q < rafMin) rafMin = q; }
          }
          performance.mark('probe-mark');
          var mk = performance.getEntriesByType('mark');
          var frac = function (x) { var s = String(x), k = s.indexOf('.'); return k < 0 ? 'integer' : s.slice(k + 1); };
          var dp = Object.getOwnPropertyDescriptor(Performance.prototype, 'now');
          var ev = new Event('probe');
          return JSON.stringify({
            nowMin: nowMin, nowRegress: regress,
            rafMin: rafMin, rafRegress: rafRegress, rafFrames: raf.length,
            evtFrac: frac(ev.timeStamp), originFrac: frac(performance.timeOrigin).slice(0, 14),
            markFrac: mk.length ? frac(mk[0].startTime) : 'none',
            ownNow: String(Object.prototype.hasOwnProperty.call(performance, 'now')),
            nativeNow: String(String(Performance.prototype.now).indexOf('[native code]') >= 0),
            descW: dp ? String(dp.writable) : '?', descC: dp ? String(dp.configurable) : '?'
          });
        })()
        """;

    private static int Report(JsonElement a, JsonElement b)
    {
        var keys = new[]
        {
            "nowMin", "nowRegress", "rafMin", "rafRegress", "rafFrames",
            "evtFrac", "originFrac", "markFrac", "ownNow", "nativeNow", "descW", "descC",
        };
        var missing = new List<string>();
        foreach (var key in keys)
        {
            var okA = a.TryGetProperty(key, out var va);
            var okB = b.TryGetProperty(key, out var vb);
            if (!okA || !okB)
            {
                missing.Add(key);
                continue;
            }

            Console.WriteLine($"ab {key} A(unwrapped)={va.ToString()} B(core-stage8)={vb.ToString()}");
        }

        Console.WriteLine("ab premise=B 组注入的是 contracts/timer-stage8-script.js"
            + "（核心 TimerPrecision::new() 逐字节金样本，由 Rust 常驻测试钉住）");
        if (missing.Count > 0)
        {
            Console.WriteLine($"PROBE_ERROR A/B 缺项：{string.Join(",", missing)}");
            return 2;
        }

        return 0;
    }
}

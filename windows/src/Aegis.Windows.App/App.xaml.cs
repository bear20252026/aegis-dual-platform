namespace Aegis.Windows;

using System;
using System.Threading;
using System.Threading.Tasks;
using System.Windows;
using System.Windows.Threading;
using Aegis.Windows.Core.Security;
/// <summary>CS-196：弹窗频控器提纯——窗口内前 N 次放行、此后静默
///（此前逻辑内联在 App 静态数组上不可直测）。</summary>
internal sealed class PopupRateLimiter(int slots)
{
    /// <summary>「从未占用」哨兵（与 Core/NewTabGate.cs 的 SlotWindow 同形）。</summary>
    private const long NeverUsed = long.MinValue;

    private readonly long[] _ticks = CreateUnused(slots);
    private readonly object _lock = new();

    private static long[] CreateUnused(int slots)
    {
        var ticks = new long[slots];
        Array.Fill(ticks, NeverUsed);
        return ticks;
    }

    /// <summary>到期槽位被当前时刻占用并放行；全部槽位都在窗口期内则拒绝。
    /// R9-CS-5（第九轮 2026-10-10）：槽位此前以 **0** 起步，而判定是
    /// `nowTicks - _ticks[i] >= windowMs`，调用方传的是 `Environment.TickCount64`
    /// （自开机起毫秒）⇒ 开机后第一个 30 秒窗口里 `nowTicks` 本身就小于 windowMs，
    /// 三槽全判「未到期」⇒ 这段时间里所有崩溃弹窗被静默拒（只记日志）。它管的是
    /// 异常提示、方向保守所以从未被当成缺陷暴露，真正的风险是**形状被抄走**：同形状
    /// 用在「拒绝用户可达的功能」上就是打开即失效。哨兵改成「从未占用」后冷启动
    /// 放行满配额，由冷启动用例钉住（`nowTicks - NeverUsed` 会溢出，故先判哨兵——
    /// 与 NewTabGate 同一个次序，那边的 `ColdStart_AllowsFullQuotaInsideOneWindow` 已在绿）。</summary>
    public bool ShouldShow(long nowTicks, long windowMs)
    {
        lock (_lock)
        {
            for (var i = 0; i < _ticks.Length; i++)
            {
                if (_ticks[i] == NeverUsed || nowTicks - _ticks[i] >= windowMs)
                {
                    _ticks[i] = nowTicks;
                    return true;
                }
            }
            return false;
        }
    }
}

public partial class App : Application
{
    // 弹窗频控：持续性异常（如每帧渲染错误）此前会造成无限 MessageBox 循环，
    // 应用既无法操作也无法退出——30 秒窗口内最多弹 3 次，超出只记日志
    private static readonly PopupRateLimiter PopupLimiter = new(3);
    private const long PopupWindowMs = 30_000;
    // CS-230：单实例互斥——双开会割裂会话/书签库（SQLite busy 与配置互相覆盖）
    private const string SingleInstanceMutexName = "Local\\Aegis.WebView.SingleInstance";
    private static Mutex? _singleInstanceMutex;

    public App()
    {
        // 应用级未处理异常兜底：记录到安全日志 + 友好提示，阻止「闪退」。
        // 个别 UI 事件抛异常的根因由此可定位（日志含类型/消息），而非静默崩溃。
        DispatcherUnhandledException += OnDispatcherUnhandledException;
        // 后台线程/fire-and-forget 异常同样留痕（此前直接杀进程且无日志）
        AppDomain.CurrentDomain.UnhandledException += (_, e) =>
        {
            TryLog($"[fatal] 后台线程未处理异常: {e.ExceptionObject}");
        };
        TaskScheduler.UnobservedTaskException += (_, e) =>
        {
            TryLog($"[fatal] 未观察任务异常: {e.Exception}");
            e.SetObserved();  // 不因未观察任务异常终止进程
        };
    }

    private static void OnDispatcherUnhandledException(object? sender, DispatcherUnhandledExceptionEventArgs e)
    {
        TryLog(
            $"[fatal] 未处理异常（已拦截，应用继续运行）: {e.Exception?.GetType().Name}: {e.Exception?.Message}{Environment.NewLine}{e.Exception}");
        if (ShouldShowPopup())
        {
            MessageBox.Show(
                $"发生未处理的异常，应用已阻止崩溃并继续运行。\n\n" +
                $"{e.Exception?.GetType().Name}: {e.Exception?.Message}",
                "Aegis",
                MessageBoxButton.OK,
                MessageBoxImage.Error);
        }
        e.Handled = true;  // 已处理——应用不退出（频控超限时静默吞掉并持续记日志）
    }

    private static bool ShouldShowPopup() =>
        PopupLimiter.ShouldShow(Environment.TickCount64, PopupWindowMs);

    private static void TryLog(string message)
    {
        try
        {
            SecurityLog.Write(message);
        }
        catch
        {
            // 日志不可写时不阻断处理
        }
    }

    /// <summary>审计第六轮（2026-10-04）：裁决路径出厂留痕——"原生核心是否被
    /// 要求、探测是否成功、确认门是否开启"此前零痕迹，这正是"环境变量只在 CI
    /// 构建机赋值 → 出货制品运行时恒 Disabled()、Rust 核心从不被咨询"的断链
    /// 连续五轮审计未被发现的根因（决策路径差异不可观察）。只记布尔与门禁
    /// 拒绝码：不含 DLL 绝对路径（NativePolicyCoreGate 刻意使失败信息不带本机
    /// 路径——同一约束在此延续），也不记注册表值内容。</summary>
    private static void LogAdjudicationDecisionPath()
    {
        try
        {
            var required = Broker.NativePolicyCoreGate.IsRequired;
            var fromInstalledMarker = Broker.InstalledBuildMarker.IsSet(
                Broker.InstalledBuildMarker.NativePolicyCoreValueName);
            // 未要求时恒 Disabled()（探测即 TryLoad+Free，无副作用）
            var probe = Broker.NativePolicyCoreGate.ProbeFromEnvironment();
            var probeText = !required
                ? "未执行（Disabled）"
                : probe.AllowsPlatformBroker ? "通过" : $"失败:{probe.DenialCode}";
            var verdict = !required
                ? "导航由托管 C# broker 裁决"
                : probe.AllowsPlatformBroker
                    ? "导航由 Rust 策略核心裁决"
                    : "已要求原生核心但不可用：全部导航 fail-closed";
            TryLog(
                $"[adjudication] 原生策略核心要求={required}" +
                $"（安装期标记={fromInstalledMarker}，" +
                $"自定义库路径已配置={Broker.NativePolicyCoreGate.LibraryPath is not null}）；" +
                $"探测结果={probeText}；" +
                $"导航确认门要求={WebView.NavigationConfirmationGate.IsRequired}；{verdict}");
        }
        catch (Exception ex)
        {
            // 留痕本身绝不影响启动（门禁语义由 broker 侧独立强制）
            TryLog($"[adjudication] 裁决路径留痕失败: {ex.GetType().Name}: {ex.Message}");
        }
    }

    /// <summary>组合根：装配存储/策略/broker 后构造主窗口。MainWindow 不再自建
    /// 依赖（此前的字段初始器）——依赖显式可注入、可换内存实现、可构造测。</summary>
    protected override void OnStartup(StartupEventArgs e)
    {
        base.OnStartup(e);
        _singleInstanceMutex = new Mutex(true, SingleInstanceMutexName, out var createdNew);
        if (!createdNew)
        {
            MessageBox.Show("Aegis 已在运行（二次启动已退出）。", "Aegis",
                MessageBoxButton.OK, MessageBoxImage.Information);
            Shutdown();
            return;
        }
        try
        {
            // 审计第六轮（2026-10-04）：出厂裁决路径留痕——必须在主窗构造之前，
            // 使 fail-closed 启动（原生核心不可用）也留下判定依据
            LogAdjudicationDecisionPath();
            // CS-352（2026-10-01 审计）：启动清理崩溃残留的无痕临时目录
            //（%TEMP%\Aegis.InPrivate.*——正常退出经引用计数清理，崩溃后永久
            // 残留即隐私承诺失效）；失败留痕不打断启动
            _ = WebView.WebViewEnvironment.CleanupOrphanInPrivateDirs();
            var window = new Chrome.MainWindow(Chrome.MainWindowDependencies.Defaults());
            MainWindow = window;
            window.Show();
        }
        catch (Exception ex)
        {
            // CS-197：组合根/主窗构造失败留痕——此前直接进程退出且零痕迹
            TryLog($"[fatal] 主窗口构造失败: {ex.GetType().Name}: {ex.Message}{Environment.NewLine}{ex}");
            throw;
        }
    }
}

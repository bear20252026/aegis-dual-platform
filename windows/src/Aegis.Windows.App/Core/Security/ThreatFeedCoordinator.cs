namespace Aegis.Windows.Core.Security;

using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;

/// <summary>威胁黑名单刷新编排（上帝对象拆分·第六批——MainWindow.StartThreatFeedRefresh
/// 外移）：缓存快照替换 atomically apply 到策略 + 订阅源校验 + 后台异步刷新。
/// 副作用全部注入（applyHosts/log/网络抓取），可注入假实现做离线单测。
/// 刷新失败保持旧快照（fail-safe）；订阅源非法仅留痕。
///
/// Q52（外部第三轮审计 AEG-008，2026-10-11）：此前 `Start()` 只在启动链里取一次，
/// 长时间不关窗的用户会用一份越来越旧的名单（设置界面也确实写着「生效于下次启动」）。
/// 现在首次刷新后进入**周期重取**，失败按 2 的幂退避（只拉长间隔，绝不缩短），
/// 用户配置的源一旦合法就持续更新；未配置源时本类不产生任何网络活动（原判据不变）。</summary>
public sealed class ThreatFeedCoordinator
{
    /// <summary>默认节拍 6 小时；单次等待上限 24 小时（退避封顶，避免长时间断网后
    /// 间隔被推到「等于不再更新」）。要改节拍/上限在这里改一处——设置界面的过期判定
    /// 也按 [StaleAfterFactor] 倍这个值算，不另写一份数字。</summary>
    internal static readonly TimeSpan DefaultRefreshInterval = TimeSpan.FromHours(6);
    internal static readonly TimeSpan MaxRefreshDelay = TimeSpan.FromHours(24);

    /// <summary>「超过这么久而没有一次成功」才在 UI 上标为可能失效：3 倍节拍
    /// （= 默认 18 小时），留够一次退避重试的余量，不把正常空档说成故障。</summary>
    internal const int StaleAfterFactor = 3;

    private readonly Action<IBlockedHosts> _applyHosts;
    private readonly string _cachePath;
    private readonly Func<string?> _resolveFeedUrl;
    private readonly Action<string> _log;
    private readonly Func<string, string, IReadOnlyList<string>> _fetchAndStore;
    private readonly TimeSpan _refreshInterval;
    private readonly Func<TimeSpan, CancellationToken, Task> _delay;
    private readonly Func<DateTimeOffset> _clock;
    private readonly CancellationToken _cancel;

    /// <summary>同一时刻只放一次「抓取+落盘+应用」进去（Q52 带来的新竞态：周期循环与
    /// 设置界面的「保存即刷」现在都调用 [Refresh]）。两个并发抓取会各自 apply 一次，
    /// 而**后完成**的那次决定最终名单——它可能是先发出的那个请求的旧结果。串行化后
    /// 「发出顺序＝生效顺序」。这里不能改成「已在跑就跳过」：那会让用户保存后的
    /// 手动刷新静默失效，等于把新按钮接在半根线上。</summary>
    private readonly SemaphoreSlim _refreshGate = new(1, 1);

    /// <summary>最近一次「抓取+落盘+应用」成功的时刻（UTC）。UI 不读它——它显示的是
    /// 缓存文件的写入时间（同一件事的权威持久化形态，见 ThreatFeedCacheStatus），
    /// 这个属性是给测试与将来诊断用的。</summary>
    internal DateTimeOffset? LastSuccessUtc { get; private set; }

    /// <summary>当前进程唯一在跑的协调器（`KillSwitch.Shared`/`SharedBlockedHosts.Shared`
    /// 同款单点）。存在的唯一理由：设置界面改了订阅源要能**立刻**刷一次，而不是等下次启动——
    /// 「已保存；生效于下次启动」这句话本身就是 Q52 要消掉的东西。
    /// 由 [Start] 赋值，语义是「最后启动的那个」。Core.Tests 的
    /// `xunit.runner.json` 设了 `parallelizeTestCollections:false`，所以
    /// `Start_registers_the_active_coordinator_for_the_settings_window` 能确定地断言它；
    /// 若将来打开并行，这条用例必须与本装配里其它调用 [Start] 的用例归进同一
    /// `[Collection]`——单点状态 + 并行 = 抖动。</summary>
    internal static ThreatFeedCoordinator? Active { get; private set; }

    /// <summary>[resolveFeedUrl] 返回订阅源 URL（null/空白 → 跳过刷新）；
    /// [fetchAndStore] 默认走 ThreatFeedUpdater.FetchAndStore（真网络），
    /// 测试注入假实现绕过网络。[refreshInterval] 传 TimeSpan.Zero 关闭周期重取，
    /// [delay]/[clock]/[cancellation] 全部可注入——周期逻辑的唯一不可测面就是
    /// 「真的等 6 小时」，注入后它是可断言的。</summary>
    public ThreatFeedCoordinator(
        Action<IBlockedHosts> applyHosts,
        string cachePath,
        Func<string?> resolveFeedUrl,
        Action<string> log,
        Func<string, string, IReadOnlyList<string>>? fetchAndStore = null,
        TimeSpan? refreshInterval = null,
        Func<TimeSpan, CancellationToken, Task>? delay = null,
        Func<DateTimeOffset>? clock = null,
        CancellationToken cancellation = default)
    {
        _applyHosts = applyHosts;
        _cachePath = cachePath;
        _resolveFeedUrl = resolveFeedUrl;
        _log = log;
        _fetchAndStore = fetchAndStore
            ?? ((url, cache) => ThreatFeedUpdater.FetchAndStore(url, cache));
        _refreshInterval = refreshInterval ?? DefaultRefreshInterval;
        _delay = delay ?? Task.Delay;
        _clock = clock ?? (() => DateTimeOffset.UtcNow);
        _cancel = cancellation;
    }

    /// <summary>Start() 投递的那条后台任务（缓存快照应用 → 订阅源刷新 → 周期重取）。
    /// CS-350 把 LoadCached 移出 UI 线程时没留下任何句柄，调用方只能靠轮询副作用
    /// 观测——「用例断言完成」与「后台仍在写缓存文件」之间因此没有 happens-before，
    /// 第八轮实测把必需检查 windows-contract-build 打红（Dispose 删缓存撞
    /// IOException "used by another process"）。句柄交还调用方就能等待。
    /// 它**不**代表可取消（取消由构造时注入的 token 决定），那一条如实留在此处。</summary>
    internal Task? BackgroundTask { get; private set; }

    /// <summary>下一次等待时长：无失败 ⇒ 节拍本身；此后每次失败翻倍，封顶
    /// [MaxRefreshDelay]。退避只拉长——「失败就更快重试」在订阅源 429 时就是自伤。</summary>
    internal static TimeSpan NextDelay(TimeSpan interval, int consecutiveFailures)
    {
        if (consecutiveFailures <= 0 || interval <= TimeSpan.Zero)
            return interval;
        var shift = Math.Min(consecutiveFailures - 1, 10);   // 1<<10 之后必然触顶，防溢出
        var scaled = interval.Ticks << shift;
        var capped = scaled <= 0 || scaled > MaxRefreshDelay.Ticks
            ? MaxRefreshDelay.Ticks
            : scaled;
        return TimeSpan.FromTicks(capped);
    }

    /// <summary>启动：后台线程加载缓存快照并应用，再（源有效时）后台刷新并进入周期重取。
    /// CS-350（2026-10-01 审计）：LoadCached（≤5MB 读盘）此前在启动链 UI 线程
    /// 同步执行——改空快照启动（broker 保持默认空名单，fail-safe 放行）+
    /// 全量后台加载后回投应用；返回是否启动了后台刷新（语义不变，供测试
    /// 同步等待完成）。</summary>
    public bool Start()
    {
        Active = this;
        var validated = ResolveValidated();
        BackgroundTask = Task.Run(async () =>
        {
            try
            {
                var snapshot = ThreatFeedUpdater.LoadCached(_cachePath);
                _applyHosts(new BlockedHosts(snapshot));
                _log($"[threat] 黑名单快照 {snapshot.Count} 条");
            }
            catch (Exception ex)
            {
                _log($"[threat] 缓存快照加载失败（保持空名单）: {ex.Message}");
            }
            if (validated is null)
                return;
            await Refresh(validated);
            await RunPeriodicRefresh();
        });
        return validated is not null;
    }

    /// <summary>读取当前订阅源并校验（null ⇒ 未配置或非法）。**每轮重读**：
    /// 设置界面改源后不需要重启就能被采纳；未配置/改成非法值时这一轮直接跳过，
    /// 因此「未配置源 ⇒ 零网络活动」这条既有判据在周期化之后仍然成立。</summary>
    private string? ResolveValidated()
    {
        var feedUrl = (_resolveFeedUrl() ?? string.Empty).Trim();
        if (string.IsNullOrWhiteSpace(feedUrl))
            return null;
        var validated = ThreatFeedUpdater.ValidateFeedUrl(feedUrl);
        if (validated is null)
            _log("[threat] 订阅源非法（仅支持 https）——保持旧快照");
        return validated;
    }

    /// <summary>设置界面保存新订阅源后调用：立刻按当前值刷一次（不等下一个节拍）。
    /// fire-and-forget——UI 不阻塞在网络抓取上；失败仍走 [Refresh] 的留痕与
    /// 「保持旧快照」路径。返回是否发起了这次刷新。</summary>
    internal bool RefreshNow()
    {
        var validated = ResolveValidated();
        if (validated is null)
            return false;
        _ = Task.Run(() => Refresh(validated));
        return true;
    }

    /// <summary>Q52 周期重取（首轮由 Start 的后台任务做过，所以这里先等再取）。
    /// 节拍由 [NextDelay] 决定（含退避）；token 取消或节拍被关掉（TimeSpan.Zero）
    /// 即刻结束——不靠「抛异常退出」这种隐式约定。</summary>
    private async Task RunPeriodicRefresh()
    {
        if (_refreshInterval <= TimeSpan.Zero)
            return;
        var failures = 0;
        while (!_cancel.IsCancellationRequested)
        {
            try
            {
                await _delay(NextDelay(_refreshInterval, failures), _cancel);
            }
            catch (OperationCanceledException)
            {
                return;
            }
            var validated = ResolveValidated();
            if (validated is null)
                continue;   // 用户清空了订阅源：这一轮零网络活动，但节拍照走
            if (await Refresh(validated))
                failures = 0;
            else
            {
                failures++;
                _log($"[threat] 第 {failures} 次连续失败——下次等待 " +
                    $"{NextDelay(_refreshInterval, failures).TotalHours:0.#} 小时");
            }
        }
    }

    /// <summary>取一次订阅源；返回是否成功（失败保持旧快照，绝不清空）。
    /// 全程持 [_refreshGate]（见其注释：并发刷新会让旧结果后到后生效）。</summary>
    private async Task<bool> Refresh(string validated)
    {
        await _refreshGate.WaitAsync();
        try
        {
            // CS-134：直接用拉取返回值——此前写盘后再全量重读缓存文件（多一次
            // IO，且第三方进程若此刻改写缓存会应用非拉取内容）
            var fetched = await Task.Run(() => _fetchAndStore(validated, _cachePath));
            _applyHosts(new BlockedHosts(fetched));
            _log($"[threat] 订阅源刷新完成：{fetched.Count} 条域名入黑名单");
            LastSuccessUtc = _clock();
            return true;
        }
        catch (Exception ex)
        {
            _log($"[threat] 订阅源刷新失败（保持旧快照）: {ex.Message}");
            return false;
        }
        finally
        {
            _refreshGate.Release();
        }
    }
}

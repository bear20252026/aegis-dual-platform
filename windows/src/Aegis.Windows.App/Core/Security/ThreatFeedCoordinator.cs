namespace Aegis.Windows.Core.Security;

using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading.Tasks;

/// <summary>威胁黑名单刷新编排（上帝对象拆分·第六批——MainWindow.StartThreatFeedRefresh
/// 外移）：缓存快照替换 atomically apply 到策略 + 订阅源校验 + 后台异步刷新。
/// 副作用全部注入（applyHosts/log/网络抓取），可注入假实现做离线单测。
/// 刷新失败保持旧快照（fail-safe）；订阅源非法仅留痕。</summary>
public sealed class ThreatFeedCoordinator
{
    private readonly Action<IBlockedHosts> _applyHosts;
    private readonly string _cachePath;
    private readonly Func<string?> _resolveFeedUrl;
    private readonly Action<string> _log;
    private readonly Func<string, string, IReadOnlyList<string>> _fetchAndStore;

    /// <summary>[resolveFeedUrl] 返回订阅源 URL（null/空白 → 跳过刷新）；
    /// [fetchAndStore] 默认走 ThreatFeedUpdater.FetchAndStore（真网络），
    /// 测试注入假实现绕过网络。</summary>
    public ThreatFeedCoordinator(
        Action<IBlockedHosts> applyHosts,
        string cachePath,
        Func<string?> resolveFeedUrl,
        Action<string> log,
        Func<string, string, IReadOnlyList<string>>? fetchAndStore = null)
    {
        _applyHosts = applyHosts;
        _cachePath = cachePath;
        _resolveFeedUrl = resolveFeedUrl;
        _log = log;
        _fetchAndStore = fetchAndStore
            ?? ((url, cache) => ThreatFeedUpdater.FetchAndStore(url, cache));
    }

    /// <summary>Start() 投递的那条后台任务（缓存快照应用 → 订阅源刷新）。
    /// CS-350 把 LoadCached 移出 UI 线程时没留下任何句柄，调用方只能靠轮询副作用
    /// 观测——「用例断言完成」与「后台仍在写缓存文件」之间因此没有 happens-before，
    /// 第八轮实测把必需检查 windows-contract-build 打红（Dispose 删缓存撞
    /// IOException "used by another process"）。句柄交还调用方就能等待。
    /// 它**不**代表可取消（本类没有 CancellationToken），那一条如实留给后续面。</summary>
    internal Task? BackgroundTask { get; private set; }

    /// <summary>启动：后台线程加载缓存快照并应用，再（源有效时）后台刷新。
    /// CS-350（2026-10-01 审计）：LoadCached（≤5MB 读盘）此前在启动链 UI 线程
    /// 同步执行——改空快照启动（broker 保持默认空名单，fail-safe 放行）+
    /// 全量后台加载后回投应用；返回是否启动了后台刷新（语义不变，供测试
    /// 同步等待完成）。</summary>
    public bool Start()
    {
        var feedUrl = (_resolveFeedUrl() ?? string.Empty).Trim();
        string? validated = null;
        if (!string.IsNullOrWhiteSpace(feedUrl))
        {
            validated = ThreatFeedUpdater.ValidateFeedUrl(feedUrl);
            if (validated is null)
                _log("[threat] 订阅源非法（仅支持 https）——保持旧快照");
        }
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
        });
        return validated is not null;
    }

    private Task Refresh(string validated)
    {
        try
        {
            // CS-134：直接用拉取返回值——此前写盘后再全量重读缓存文件（多一次
            // IO，且第三方进程若此刻改写缓存会应用非拉取内容）
            var fetched = _fetchAndStore(validated, _cachePath);
            _applyHosts(new BlockedHosts(fetched));
            _log($"[threat] 订阅源刷新完成：{fetched.Count} 条域名入黑名单");
        }
        catch (Exception ex)
        {
            _log($"[threat] 订阅源刷新失败（保持旧快照）: {ex.Message}");
        }
        return Task.CompletedTask;
    }
}
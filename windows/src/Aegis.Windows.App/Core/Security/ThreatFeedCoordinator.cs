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

    /// <summary>启动同步：先应用缓存快照，再（源有效时）后台异步刷新。
    /// 返回是否启动了后台刷新（供测试同步等待完成）。</summary>
    public bool Start()
    {
        var snapshot = ThreatFeedUpdater.LoadCached(_cachePath);
        _applyHosts(new BlockedHosts(snapshot));
        _log($"[threat] 黑名单快照 {snapshot.Count} 条");

        var feedUrl = (_resolveFeedUrl() ?? string.Empty).Trim();
        if (string.IsNullOrWhiteSpace(feedUrl))
            return false;
        var validated = ThreatFeedUpdater.ValidateFeedUrl(feedUrl);
        if (validated is null)
        {
            _log("[threat] 订阅源非法（仅支持 https）——保持旧快照");
            return false;
        }

        Task.Run(() => Refresh(validated));
        return true;
    }

    private Task Refresh(string validated)
    {
        try
        {
            var fetched = _fetchAndStore(validated, _cachePath);
            _applyHosts(new BlockedHosts(ThreatFeedUpdater.LoadCached(_cachePath)));
            _log($"[threat] 订阅源刷新完成：{fetched.Count} 条域名入黑名单");
        }
        catch (Exception ex)
        {
            _log($"[threat] 订阅源刷新失败（保持旧快照）: {ex.Message}");
        }
        return Task.CompletedTask;
    }
}
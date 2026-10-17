namespace Aegis.Windows.Core.Security;

/// <summary>「清空威胁订阅源」这一步的判定与措辞单源（R9-B86 / 队列 Q54——用户定「清空即解除」）。
///
/// 为什么把这三件事从 WPF 事件处理器里抽出来：它们此前长在 UI 上，谁也测不到——
/// ① 要不要弹确认（只有「配过源 → 清空」才该弹，空 → 清空不该 nag）；
/// ② 清空之后给用户看的那句话必须按**缓存到底删没删**说真话；
/// ③ 旧口径「清空只停止重取、名单继续拦截到进程结束」不得回潮，而反向锚需要一个纯函数落点。
///
/// 判定本体（解除名单 + 删缓存 + 与在途抓取的先后）在
/// <see cref="ThreatFeedCoordinator.ClearAndDisableAsync"/>，本类不重复它，只管「该不该问」和「怎么说」。</summary>
internal static class ThreatFeedClear
{
    /// <summary>只有「原本配了源、现在要清空」才需要确认。这是**放松防护**的方向，
    /// 本仓对这类动作的既有口径是「让用户明确点一次」——误清一次的代价由这一次点击承担，
    /// 而不是由「清而不断」这种半成品行为承担（后者才是 Q54 登记时的原缺陷）。</summary>
    internal static bool RequiresConfirmation(string? previous, string next) =>
        !string.IsNullOrWhiteSpace(previous) && string.IsNullOrWhiteSpace(next);

    internal const string ConfirmationCaption = "清空威胁订阅源";

    internal const string ConfirmationText =
        "清空后：当前已生效的黑名单立即解除，缓存文件一并删除，下次启动也不会再加载它。确定继续？";

    /// <summary>取消确认后：什么都没发生，不能写成「已保存」。
    /// 用户点了「否」却看到保存成功的话术，比不弹这个框更糟。</summary>
    internal const string CancelledHint = "未清空：保留原有订阅源与当前名单。";

    /// <summary>清空后的措辞。`null` 这一支不是凑数：本进程没有活跃协调器时，
    /// 既没有在内存里生效的名单可解除，也没有后台在写缓存——把「无事发生」写成「已解除」
    /// 就是本仓反复修的那类「声明比行为多」。</summary>
    internal static string ClearedHint(bool? cacheCleared) => cacheCleared switch
    {
        true => "已清空订阅源：名单已解除，缓存已删除（下次启动不再加载旧名单）。",
        false => "已清空订阅源：名单已解除，但缓存文件没删掉（详见安全日志）——重启后它仍会被加载。",
        _ => "已清空订阅源：本进程没有在跑的刷新循环，下次启动按空源处理。",
    };
}

namespace Aegis.Windows.Broker;

using System;
using System.Collections.Generic;

/// <summary>阶段 C（蓝图 ADR-004）：原生终止开关（kill switch）——紧急时
/// 立即撤销已发出但尚未执行的授权/Agent 副作用。原生 UI 触发——
/// 不依赖网页/Agent 配合（Agent/MCP 默认无网络副作用——ADR-004）。
/// 单向 Engage（重启恢复）——触发即留痕（security.log）。</summary>
public sealed class KillSwitch
{
    private volatile bool _engaged;
    private readonly object _reactionLock = new();
    private readonly HashSet<Action> _processReactions = new();

    /// <summary>CS-291（2026-09-26 审计）：进程级共享实例。紧急终止必须冻结
    /// **全部**窗口的导航/下载/批准链——此前 KillSwitch 是每个 broker 的实例
    /// 属性：每个无痕窗口 new BrowserPolicyBroker() 自带独立开关，设置窗触发
    /// 主窗 broker 的开关后无痕窗口链完全不受冻结（fail-open）。组合根把本
    /// 实例注入全部 broker（主窗 + 各无痕窗）即恢复"全进程一把闸"语义；
    /// 测试可注入独立实例保持隔离。</summary>
    public static KillSwitch Shared { get; } = new();

    public bool IsEngaged => _engaged;

    /// <summary>CS-367（2026-10-01 审计）：触发通知——主窗据此显示常驻横幅
    ///（此前 Engage 后零可见指示，用户只见"导航无反应"无从知晓原因）。
    /// 仅首次触发时广播一次。</summary>
    public event Action? Engaged;

    /// <summary>审计第七轮（2026-10-03）：登记**进程级反应**回调（Engage 时逐个
    /// 执行）。此前 Engage 只在 broker 入口判定（导航/下载/批准链冻结），
    /// 已建立的 WebView2 内核继续流式拉取 XHR/子资源、进行中的下载照常完成
    /// ——与"进程级紧急冻结"的承诺不符（P2）。
    /// 依赖方向：Broker 层不引用 WebView2 类型（ADR-002），WebView 侧反应
    ///（Stop 内核 / Cancel 下载）由 App 层以回调形式注册于此。
    /// 已触发后注册的反应立即执行——紧急终止期间新建的标签同样被冻结。
    /// 返回 IDisposable 注销句柄：标签销毁时注销，避免开关持有已释放控件
    ///（注册表此前不存在，无历史注销面）。</summary>
    public IDisposable RegisterProcessReaction(Action reaction)
    {
        ArgumentNullException.ThrowIfNull(reaction);
        lock (_reactionLock)
            _processReactions.Add(reaction);
        if (_engaged)
            RunReaction(reaction);  // 注册即已触发——立即执行（fail-closed）
        return new Registration(this, reaction);
    }

    /// <summary>紧急终止（原生 UI 触发——立即撤销未执行授权；幂等）。</summary>
    public void Engage()
    {
        if (_engaged)
            return;
        _engaged = true;
        Core.Security.SecurityLog.Write("[security] KillSwitch 已触发——导航/下载/批准链全部冻结（重启恢复）");
        // 审计第七轮（2026-10-03）：入口冻结之外执行进程级反应（停内核/取消下载）
        // 快照后在锁外执行——反应回调可能注销自身（重入死锁面）
        Action[] reactions;
        lock (_reactionLock)
        {
            reactions = new Action[_processReactions.Count];
            _processReactions.CopyTo(reactions);
        }
        foreach (var reaction in reactions)
            RunReaction(reaction);
        Engaged?.Invoke();
    }

    private static void RunReaction(Action reaction)
    {
        try
        {
            reaction();
        }
        catch (Exception ex)
        {
            // 单个反应失败不得中断冻结链（其余内核/下载仍须处置）——如实留痕
            Core.Security.SecurityLog.Write(
                $"[security] KillSwitch 进程反应异常（已跳过该反应）: {ex.GetType().Name}: {ex.Message}");
        }
    }

    private void Unregister(Action reaction)
    {
        lock (_reactionLock)
            _processReactions.Remove(reaction);
    }

    private sealed class Registration(KillSwitch owner, Action reaction) : IDisposable
    {
        public void Dispose() => owner.Unregister(reaction);
    }
}

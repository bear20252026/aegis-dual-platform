namespace Aegis.Windows.Broker;

using System;

/// <summary>阶段 C（蓝图 ADR-004）：原生终止开关（kill switch）——紧急时
/// 立即撤销已发出但尚未执行的授权/Agent 副作用。原生 UI 触发——
/// 不依赖网页/Agent 配合（Agent/MCP 默认无网络副作用——ADR-004）。
/// 单向 Engage（重启恢复）——触发即留痕（security.log）。</summary>
public sealed class KillSwitch
{
    private volatile bool _engaged;

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

    /// <summary>紧急终止（原生 UI 触发——立即撤销未执行授权；幂等）。</summary>
    public void Engage()
    {
        if (_engaged)
            return;
        _engaged = true;
        Core.Security.SecurityLog.Write("[security] KillSwitch 已触发——导航/下载/批准链全部冻结（重启恢复）");
        Engaged?.Invoke();
    }
}

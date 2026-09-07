namespace Aegis.Windows.Broker;

using System;

/// <summary>阶段 C（蓝图 ADR-004）：原生终止开关（kill switch）——紧急时
/// 立即撤销已发出但尚未执行的授权/Agent 副作用。原生 UI 触发——
/// 不依赖网页/Agent 配合（Agent/MCP 默认无网络副作用——ADR-004）。
/// 单向 Engage（重启恢复）——触发即留痕（security.log）。</summary>
public sealed class KillSwitch
{
    private volatile bool _engaged;

    public bool IsEngaged => _engaged;

    /// <summary>紧急终止（原生 UI 触发——立即撤销未执行授权；幂等）。</summary>
    public void Engage()
    {
        if (_engaged)
            return;
        _engaged = true;
        Core.Security.SecurityLog.Write("[security] KillSwitch 已触发——导航/下载/批准链全部冻结（重启恢复）");
    }

    /// <summary>任何副作用服务执行前检查（Broker 唯一副作用点——ADR-002）。</summary>
    public void EnsureNotEngaged()
    {
        if (_engaged)
            throw new InvalidOperationException("紧急终止开关已触发——拒绝副作用");
    }
}

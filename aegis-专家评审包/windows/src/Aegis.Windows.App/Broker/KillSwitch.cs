namespace Aegis.Windows.Broker;

using System;

/// <summary>阶段 C（蓝图 ADR-004）：原生终止开关（kill switch）——紧急时
/// 立即撤销已发出但尚未执行的授权/Agent 副作用。原生 UI 触发——
/// 不依赖网页/Agent 配合（Agent/MCP 默认无网络副作用——ADR-004）。</summary>
public sealed class KillSwitch
{
    private volatile bool _engaged;

    public bool IsEngaged => _engaged;

    /// <summary>紧急终止（原生 UI 触发——立即撤销未执行授权）。</summary>
    public void Engage()
    {
        _engaged = true;
    }

    /// <summary>任何副作用服务执行前检查（Broker 唯一副作用点——ADR-002）。</summary>
    public void EnsureNotEngaged()
    {
        if (_engaged)
            throw new InvalidOperationException("紧急终止开关已触发——拒绝副作用");
    }
}

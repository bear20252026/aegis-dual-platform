// 由 contracts/codegen/generate_csharp.py 生成（蓝图阶段 B——契约事实来源——请勿手工编辑）
namespace Aegis.Windows.Contracts.Generated;

public sealed record AuditEvent.schema(
    string event_id,
    string timestamp,
    string decision,
    string scope,
    string origin,
    string reason,
    string tab_id,
);

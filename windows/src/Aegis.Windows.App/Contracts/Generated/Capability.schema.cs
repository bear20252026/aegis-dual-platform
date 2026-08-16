// 由 contracts/codegen/generate_csharp.py 生成（蓝图阶段 B——契约事实来源——请勿手工编辑）
namespace Aegis.Windows.Contracts.Generated;

public sealed record Capability.schema(
    string scope,
    List<string> actions,
    List<string> resources,
    bool requires_confirmation,
);

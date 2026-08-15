namespace Aegis.Windows.Contracts;

/// <summary>阶段 C（蓝图 windows/src/Aegis.Windows.Contracts）：
/// contracts 的生成/引用产物——唯一安全协议事实来源（蓝图 contracts/——
/// schemas 六类对象冻结 + vectors 测试向量——JSON 11/11 有效）。
/// 本目录引用 contracts/（不手工维护平行 Schema——蓝图禁止）。
/// 生成方式：contracts/codegen（generate_csharp.py——阶段 B 蓝图）——
/// 当前阶段最小：指向 contracts/ 的引用说明（完整 codegen 按蓝图阶段 C 迭代）。</summary>
public static class Contracts
{
    public const string ContractRoot = "../../../../contracts";
    public const string PolicyVersion = "1.0";  // 与 contracts/version.schema.json 语义一致
}

namespace Aegis.Windows.Core.Tests;

using System.Collections.Generic;
using System.IO;
using System.Text.Json;
using Aegis.Windows.Broker;
using Xunit;

/// <summary>CS-418（2026-10-02 审计）：contracts 向量 C# 消费——url-origin
/// valid/invalid 向量逐条断言 OriginPolicy.TryParseExternal 判定一致。
/// 与 Rust vectors.rs / Kotlin OriginPolicyTest 消费同一单一事实源
///（contracts/vectors/*.json）——向量/schema 变更时三端测试自动跟随。
/// 判定面选 OriginPolicy（导航解析层契约；UrlSafety.CanOpenHttpUrl 对
/// 本机/内网开发地址有放行豁免——它锁的是"新窗口打开面"而非本契约）。
/// csproj 以 CopyToOutputDirectory 把向量复制到输出 contracts/ 目录
///（csproj 路径相对性：../../.. 自测试工程根上溯到仓库根）。</summary>
public sealed class UrlOriginVectorTests
{
    private static string VectorsDir =>
        Path.Combine(AppContext.BaseDirectory, "contracts", "vectors");

    public static IEnumerable<object[]> ValidVectors => LoadVectors("url-origin-valid.json");

    public static IEnumerable<object[]> InvalidVectors => LoadVectors("url-origin-invalid.json");

    private static IEnumerable<object[]> LoadVectors(string fileName)
    {
        var path = Path.Combine(VectorsDir, fileName);
        var root = JsonSerializer.Deserialize<JsonElement>(File.ReadAllText(path));
        foreach (var vector in root.GetProperty("vectors").EnumerateArray())
        {
            var url = vector.GetProperty("url").GetString()!;
            // oversize 占位向量按 JSON note 物化为真实超长 URL（>8192 字符）
            //（JSON 保持可读，实际样本在消费端展开——与 Rust vectors.rs /
            // Kotlin OriginPolicyTest 同口径）
            if (url.Contains("oversize-url-limit-test"))
                url = "https://example.org/" + new string('a', 9000);
            yield return new[] { url, vector.GetProperty("expected").GetString()! };
        }
    }

    [Theory]
    [MemberData(nameof(ValidVectors))]
    public void ValidVectorsAllAllow(string url, string expected) =>
        AssertVector(url, expected);

    [Theory]
    [MemberData(nameof(InvalidVectors))]
    public void InvalidVectorsAllDeny(string url, string expected) =>
        AssertVector(url, expected);

    private static void AssertVector(string url, string expected)
    {
        // 已知差异跳过约定：向量 note 明确标注「消费端已知差异」的条目应在此
        // 按 note 关键词跳过并留注释（归属端/原因）——当前 url-origin 向量与
        // C# 判定零差异（OriginPolicy 已补 CS-418 端口 0/八位组越界校验），
        // 无跳过项；全部向量逐条硬断言。
        Assert.True(
            OriginPolicy.TryParseExternal(url, out _) == (expected == "allow"),
            $"向量结果不符: {(url.Length > 100 ? url[..100] + "…(截断)" : url)} (expected={expected})");
    }
}

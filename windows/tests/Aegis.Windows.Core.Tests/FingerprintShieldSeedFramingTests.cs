namespace Aegis.Windows.Core.Tests;

using System.Linq;
using Aegis.Windows.WebView;
using Xunit;

/// <summary>站点框定与公共后缀清单（R9-B67 从 FingerprintShieldTests 拆出——那份
/// 文件在零余量行数基线上，而「未命中回退整个 host」这条新口径必须有常驻用例）。
/// 主题本来就自成一格：种子按谁的 eTLD+1 派生、表体从哪来、表里没有怎么办。</summary>
public sealed class FingerprintShieldSeedFramingTests
{
    private const string SeedA = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef";

    // ===== CS-381（2026-10-02 审计）：getETLD1 公共后缀清单 =====

    [Fact]
    public void GetETLD1_PublicSuffixList_SplitsSameSuffixSites()
    {
        // bbc.co.uk 与 shop.co.uk 此前简单取后两标签同得 "co.uk" 种子
        //（跨站噪声可关联）——公共后缀命中取后 3 标签（真 eTLD+1），两站种子不同
        var script = FingerprintShield.BuildScript(SeedA);

        Assert.Contains("PUBLIC_SUFFIXES", script);
        Assert.Contains("'co.uk':1", script);
        Assert.Contains("slice(-3)", script);
        Assert.Contains("p.slice(-2).join('.')", script);
    }

    [Fact]
    public void GetETLD1_MissFallsBackToWholeHost_NotTailTwo()
    {
        // R9-B67（队列 Q16）：本表不含裸 TLD 条目，所以「后两段不在表里」既可能是
        // example.com 这种正常注册域、也可能是表还没收的托管域——登记时 a.web.app 与
        // b.web.app 共享一种子就是后者。判不出差别时按更细的一侧收：未命中回退整个
        // host。代价照实记：同站多子域不再共享种子（产品语义变更，已在第四节定稿）。
        var script = FingerprintShield.BuildScript(SeedA);

        Assert.Contains("return p.join('.');", script);
        Assert.DoesNotContain("return last2;", script);
    }

    [Fact]
    public void SeedFraming_UsesTopLevelHost_NotFrameHost()
    {
        // R7-CS1-05≡R7-CS2-01（第七轮）：种子必须按**顶层站** eTLD+1 框定。
        // 按本帧 host 派生时，同一第三方跟踪帧在该用户的所有宿主站点上产出同
        // 一种子——加噪后的画布哈希本身就成了跨站持久标识符（正是要消除的东西）。
        var script = FingerprintShield.BuildScript(SeedA);

        // 顶层通道存在且被种子消费
        Assert.Contains("function aegisTopLevelHostname()", script);
        Assert.Contains("location.ancestorOrigins", script);
        Assert.Contains("getETLD1(aegisTopLevelHostname())", script);
        // 缺陷形态不得回归：直接把本帧 hostname 当站点键
        Assert.DoesNotContain("getETLD1(location.hostname)", script);
        // 取不到祖先链时保守退回本帧（绝不因顶层失败而放弃噪声）
        Assert.Contains("return location.hostname;", script);
    }

    [Fact]
    public void PublicSuffixList_RenderedFromSingleSourceArray()
    {
        // R7-CS2-10：表体取自 FingerprintShield.PublicSuffixes（与
        // contracts/policy/public-suffix-list.txt 逐项对账的 CI 门禁由
        // contracts/codegen/verify_seed_framing_parity.py 负责——本用例只锁"C# 侧渲染的
        // 是这份数组"，防表退回 JS 里的手抄字面量）
        var script = FingerprintShield.BuildScript(SeedA);

        Assert.Contains(string.Join(",", FingerprintShield.PublicSuffixes.Select(s => $"'{s}':1")), script);
        Assert.Contains("'github.io':1", script);   // 托管域取到用户子域为止
        Assert.Contains("'co.il':1", script);       // 第七轮前只有 Android 有
        Assert.Contains("'edu.cn':1", script);      // 第七轮前只有 C# 有
    }
}

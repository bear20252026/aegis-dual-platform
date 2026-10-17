namespace Aegis.Windows.Core.Tests;

using System;
using System.Collections.Generic;
using System.IO;
using Aegis.Windows.Core.Security;
using Aegis.Windows.TestSupport;
using Xunit;

/// <summary>R9-B86（队列 Q54，用户定「清空即解除」）：「清空威胁订阅源」这一步的判定、
/// 措辞与 UI 接线锚。
///
/// 三件事各自为什么要钉：① <c>RequiresConfirmation</c> 只在「配过源 → 清空」时弹框——
/// 这条长在 UI 里就永远测不到，下一轮有人把它改成「每次都问」也不会有人判红；
/// ② <c>ClearedHint</c> 必须按「缓存到底删没删」说话——把一次 IO 失败写成「已删除」，
/// 用户就会带着旧名单重启一次而毫不知情；③ 旧口径「清空只停重取、名单继续拦截到进程结束」
/// 不得回潮，而反向锚需要一个纯函数落点（同款形状见 ThreatFeedCacheStatusTests 的
/// `生效于下次启动`、ThreadSafeRecorderTests 的 `Applied.Add(`）。</summary>
public sealed class ThreatFeedClearTests
{
    /// <summary>被禁的旧措辞（Q54 登记的原缺陷：清而不断）。</summary>
    private const string ObsoleteKeepBlockingWording = "当前名单仍会继续拦截";

    [Theory]
    [InlineData("https://feeds.example/list.txt", "", true)]      // 配过源 → 清空＝放松防护，必须问
    [InlineData("", "", false)]                                    // 本来就没配：无事可确认，别 nag
    [InlineData(null, "", false)]
    [InlineData("   ", "", false)]
    [InlineData("https://a.example/l.txt", "https://b.example/l.txt", false)] // 换源不是关闭
    [InlineData("https://a.example/l.txt", "https://b.example/l.txt ", false)]
    public void Confirmation_is_only_asked_when_a_configured_feed_is_being_cleared(
        string? previous,
        string next,
        bool expected) => Assert.Equal(expected, ThreatFeedClear.RequiresConfirmation(previous, next));

    [Fact]
    public void Cleared_hint_states_the_cache_outcome_truthfully()
    {
        var deleted = ThreatFeedClear.ClearedHint(true);
        Assert.Contains("缓存已删除", deleted, StringComparison.Ordinal);
        Assert.DoesNotContain("仍会被加载", deleted, StringComparison.Ordinal);

        var stuck = ThreatFeedClear.ClearedHint(false);
        // 删除失败时这句话必须把「重启还会加载旧名单」说出来——否则就是把失败说成关闭成功
        Assert.Contains("重启后它仍会被加载", stuck, StringComparison.Ordinal);
        Assert.Contains("名单已解除", stuck, StringComparison.Ordinal);

        // 没有活跃协调器：内存里没有名单可解除，说「已解除」就是把无事发生说成办好了
        Assert.DoesNotContain("名单已解除", ThreatFeedClear.ClearedHint(null), StringComparison.Ordinal);
    }

    [Fact]
    public void Cancelled_hint_does_not_claim_a_save()
        => Assert.DoesNotContain("已保存", ThreatFeedClear.CancelledHint, StringComparison.Ordinal);

    // ===== 接线锚：设置窗口必须真的走这条链 =====

    /// <summary>纯函数：给定 SettingsWindow 源码（已剔注释），返回接线问题。
    /// 判定与正向控制共用同一份，反向锚才落在真逻辑上（ThreadSafeRecorderTests 同口径）。</summary>
    private static List<string> WiringProblems(string code)
    {
        var problems = new List<string>();
        if (!code.Contains("ThreatFeedClear.RequiresConfirmation", StringComparison.Ordinal))
            problems.Add("清空订阅源不再经 RequiresConfirmation——「该不该问」退回不可测的 UI 文本");
        if (!code.Contains("ClearAndDisableAsync", StringComparison.Ordinal))
            problems.Add("清空不再调用 ClearAndDisableAsync——名单会留在内存里继续拦截（Q54 的原缺陷）");
        if (!code.Contains("ThreatFeedClear.ClearedHint", StringComparison.Ordinal))
            problems.Add("清空后的措辞不再按缓存结果取值——IO 失败会被写成「已删除」");
        if (code.Contains(ObsoleteKeepBlockingWording, StringComparison.Ordinal))
            problems.Add($"旧措辞「{ObsoleteKeepBlockingWording}」回潮：那是「清而不断」，正是 Q54 要消掉的");
        return problems;
    }

    [Fact]
    public void SettingsWindow_is_wired_through_the_clear_path()
    {
        var code = SourceTextAnchors.CodeOnly(ReadChromeFile("SettingsWindow.xaml.cs"));
        Assert.True(WiringProblems(code).Count == 0, string.Join(" | ", WiringProblems(code)));
    }

    [Fact]
    public void An_unwired_settings_window_is_red()
    {
        // 上一条那个断言的正面控制：同一份判定必须认得被禁形态，否则它恒真。
        var injected =
            "void ThreatFeedBox_LostFocus() {" +
            $" ThreatFeedHint.Text = \"已清空订阅源：此后不再自动重取，{ObsoleteKeepBlockingWording}。\";" +
            " Save(); }";
        var problems = WiringProblems(SourceTextAnchors.CodeOnly(injected));
        Assert.Equal(4, problems.Count);
        Assert.Contains(problems, p => p.Contains("RequiresConfirmation", StringComparison.Ordinal));
        Assert.Contains(problems, p => p.Contains(ObsoleteKeepBlockingWording, StringComparison.Ordinal));
    }

    [Fact]
    public void Comment_text_is_not_evidence_for_these_anchors()
    {
        // 本仓的传统是把被禁形态逐字抄进注释当防回归说明（R9-B45）。锚必须只判代码：
        // 同样那句话写在行注释里，不该让上一条判红。
        var commented = "// " + ObsoleteKeepBlockingWording + "\n" +
                        "class T { void M() { } }";
        Assert.DoesNotContain(
            ObsoleteKeepBlockingWording,
            SourceTextAnchors.CodeOnly(commented),
            StringComparison.Ordinal);
    }

    /// <summary>向上定位 Chrome 目录（测试输出层级随 RID 变化，逐级上溯——
    /// 同款口径见 ThreatFeedCacheStatusTests.ReadChromeFile）。</summary>
    private static string ReadChromeFile(string fileName)
    {
        var dir = new DirectoryInfo(AppContext.BaseDirectory);
        while (dir is not null)
        {
            var candidate = Path.Combine(
                dir.FullName, "windows", "src", "Aegis.Windows.App", "Chrome", fileName);
            if (File.Exists(candidate))
                return File.ReadAllText(candidate);
            dir = dir.Parent!;
        }
        // 显式 throw：Assert.Fail 的 DoesNotReturn 标注会让其后的代码在
        // TreatWarningsAsErrors 下变成 CS0162（同款坑见 ThreatFeedCacheStatusTests:124）
        throw new InvalidOperationException($"未定位到 Chrome/{fileName}（仓库布局契约）");
    }
}

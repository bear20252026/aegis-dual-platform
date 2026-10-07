namespace Aegis.Windows.Broker.Tests;

using System;
using System.IO;
using System.Linq;
using Xunit;

/// <summary>
/// R8-CS-SEC-11（第八轮审计 2026-10-06）的结构锚：`HostWebView.WireEvents` 里
/// `_wired` 的置位必须排在**所有**接线动作之后。
///
/// 原形态：`_wired = webView;` 紧跟在 `RegisterSession` 之后，而 7 个事件订阅、
/// `AddWebResourceRequestedFilter`、`WebView2Hardening.Apply`、KillSwitch 登记
/// 全在其后。任一步抛出（COM 拒绝、加固束里任何一处守卫失败、broker 状态异常）
/// 就留下一个「`IsWired == true` 的半接线控件」——而 R6-12 的 fail-closed 守卫
/// （<c>TabRuntime</c> 拿 <see cref="HostWebView.IsWired"/> 当「可以放行导航」的依据）
/// 会把这份坏接线当成好接线满足：这正是"守卫信的那个标志自己撒谎"的形态。
///
/// 为什么是结构锚而不是行为用例：<c>CoreWebView2</c> 是 COM 对象，无法在无 WebView2
/// Runtime 的作业里构造，所以「中途抛出 ⇒ IsWired 仍为 false」在必需检查里不可达
/// （R8-CI-18 的覆盖错觉不能拿来当证据）。这里钉的是**顺序本身**——它是该性质唯一
/// 的可静态判定形态，且必须带正面控制：三个锚点任一找不到就直接判失败，否则
/// 「重构把订阅改名了」会让本用例退化成恒绿。
/// </summary>
public sealed class HostWebViewWiringOrderTests
{
    private const string RelativeSource =
        "windows/src/Aegis.Windows.App/WebView/HostWebView.cs";

    private static string RepoRoot()
    {
        var dir = new DirectoryInfo(AppContext.BaseDirectory);
        while (dir is not null)
        {
            if (File.Exists(Path.Combine(dir.FullName, RelativeSource)))
                return dir.FullName;
            dir = dir.Parent;
        }

        throw new DirectoryNotFoundException($"未找到 {RelativeSource}（请在仓库内运行测试）");
    }

    /// <summary>只取代码行：注释行必须剔掉——本仓的注记里常常抄着被禁的旧形态原文，
    /// 不剔就会自我打红（第八轮两次实测的同型事故）。行尾按平台无关方式切分
    /// （`.gitattributes` 检出 LF、工作副本可能是 CRLF，按 Environment.NewLine 切会把
    /// 整份文件当成一行，注释过滤静默失效）。</summary>
    private static string CodeOnly() =>
        string.Join(
            "\n",
            File.ReadAllText(Path.Combine(RepoRoot(), RelativeSource))
                .Replace("\r\n", "\n")
                .Split('\n')
                .Where(line => !line.TrimStart().StartsWith("//", StringComparison.Ordinal)));

    private static int RequiredIndex(string code, string anchor)
    {
        var index = code.IndexOf(anchor, StringComparison.Ordinal);
        Assert.True(index >= 0, $"结构锚失配：代码里找不到「{anchor}」——接线形态已改，本用例需同步改写");
        return index;
    }

    [Fact]
    public void WiredFlagIsSetOnlyAfterEveryWiringStep()
    {
        var code = CodeOnly();
        var wired = RequiredIndex(code, "_wired = webView;");

        // 正面控制：这三处都是"接线动作"的末端锚，找不到就说明接线形态变了
        foreach (var anchor in new[]
                 {
                     "webView.AddWebResourceRequestedFilter(",
                     "WebView2Hardening.Apply(webView, _tabId);",
                     "RegisterProcessReaction(StopLiveTraffic)",
                 })
        {
            var step = RequiredIndex(code, anchor);
            Assert.True(
                wired > step,
                $"R8-CS-SEC-11 回退：`_wired` 置位（{wired}）排在了「{anchor}」（{step}）之前——"
                + "半接线控件会被 IsWired 的 fail-closed 守卫当成已接线满足");
        }
    }

    [Fact]
    public void WiredFlagIsAssignedExactlyOnceInsideWireEvents()
    {
        // 出现第二处 `_wired = webView;` 意味着有人把置位又提前了一次（幂等守卫读同一字段）
        var occurrences = CodeOnly().Split("_wired = webView;").Length - 1;
        Assert.Equal(1, occurrences);

        // 而 `_wired = null` 只应出现在解除接线处（Dispose），不得与置位混在一起
        Assert.Contains("_wired = null;", CodeOnly());
    }
}

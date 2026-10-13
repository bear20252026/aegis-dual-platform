namespace Aegis.Windows.Core.Tests;

using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using Aegis.Windows.WebView;
using Xunit;
using Aegis.Windows.TestSupport;

/// <summary>AX-01（外部第三轮审计 2026-10-11）：拒绝已经产生之后，「合成/交付这份拒绝响应」
/// 这一步自己失败，不能把请求退回默认路径。
///
/// 第八轮 ⑤ 修的是**求值期**异常（→ 单条 403 + subresource_policy_error），这部分判据留在
/// <c>SubresourceFailClosedTests</c>；本文件判的是**投递期**：⑤ 之后代码是
/// `try { e.Response = Create(...) } catch { 只写日志 }`——留痕不是拦截，原始请求照发。
/// 现改为两段收敛：交付失败（返回 false 或抛出）⇒ 升级 <c>CoreWebView2.Stop()</c>
/// 中止该 WebView 当前导航，并留重码 subresource_denial_undeliverable。</summary>
public sealed class SubresourceDenialDeliveryTests
{
    private const string RelativeSource =
        "windows/src/Aegis.Windows.App/WebView/HostWebView.WebResourceGuards.cs";

    private const string UndeliverableCode = "subresource_denial_undeliverable";

    private readonly List<string> _lines = [];

    private static HostWebView.WebResourceDenial Denial() =>
        new(403, "Blocked");

    private static readonly Action NoOp = () => { };

    private void Deliver(
        Func<HostWebView.WebResourceDenial, bool> tryDeliver,
        Action? escalateStop = null) =>
        HostWebView.DeliverDenial(
            Denial(), tryDeliver, escalateStop ?? NoOp, _lines.Add);

    private string Text() => string.Join("\n", _lines);

    // ===== 行为面 =====

    [Fact]
    public void DeliveredDenial_EscalatesNothingAndLeavesNoTrace()
    {
        // 反向控制：正常路径（拒绝交付成功）不得被顺手升级——否则每个黑名单命中
        // 都会连带中止整页导航，把「单条请求失败闭合」变成「整页 403 事故」。
        var stopped = 0;
        Deliver(_ => true, () => stopped++);
        Assert.Equal(0, stopped);
        Assert.Empty(_lines);
    }

    [Fact]
    public void DeliveryReturningFalse_StopsTheNavigationAndLogsTheCode()
    {
        var stopped = 0;
        Deliver(_ => false, () => stopped++);
        Assert.Equal(1, stopped);
        Assert.Contains(UndeliverableCode, Text());
        Assert.Contains("status=403", Text());
    }

    [Fact]
    public void DeliveryThrowing_StopsTheNavigationToo()
    {
        // 审计点名的就是这一形态：CreateWebResourceResponse 抛出（COM 对象已退休、
        // Environment 已释放）与返回 false 是同一个事实——拒绝没落地，必须升级。
        // 旧代码在这里只留一行日志，然后让原始请求照常发出。
        var stopped = 0;
        Deliver(_ => throw new ObjectDisposedException("CoreWebView2Environment"), () => stopped++);
        Assert.Equal(1, stopped);
        Assert.Contains(UndeliverableCode, Text());
        Assert.Contains("ObjectDisposedException", Text());
    }

    [Fact]
    public void EscalationAlsoFailing_IsSwallowedAndLogged()
    {
        // 升级面也可能失效（Stop 自己抛 COMException）。此时唯一还能做的是留痕：
        // 异常抛回 WebResourceRequested 的 shim 会当场炸进程，而「炸进程」并不比
        // 「放行一条请求」更安全。
        Deliver(_ => false, () => throw new InvalidOperationException("COM 已退休"));
        Assert.Contains("拒绝投递与升级均失败", Text());
        Assert.Contains(UndeliverableCode, Text());
    }

    [Fact]
    public void DeliverDenialNeverThrowsBackToTheEventShim()
    {
        // 三个注入面全部同时抛——判定核仍必须安静收敛（这一条是本文件的存在理由：
        // 「异常面自己再异常」是安全代码最常见的崩溃根因，见 SubresourceFailClosedTests 同型用例）。
        var threw = false;
        try
        {
            HostWebView.DeliverDenial(
                Denial(),
                _ => throw new NullReferenceException(),
                () => throw new ObjectDisposedException("webView"),
                _ => throw new InvalidOperationException("日志面也不可用"));
        }
        catch (Exception)
        {
            threw = true;
        }

        Assert.False(threw, "DeliverDenial 把异常上抛回事件 shim——进程会当场崩");
    }

    [Fact]
    public void DenialCodeIsNamedOnce_AndMatchesTheRuling()
    {
        // 改码不改文档＝运维看板静默失配（R8-CS-CORE-1 同型教训）。
        Assert.Equal(UndeliverableCode, HostWebView.DenialUndeliverableErrorCode);
    }

    // ===== 结构锚：handler 的投递失败出口必须接到真实 Stop =====

    [Fact]
    public void HandlerRoutesUndeliverableDenialsToAStopNotJustALog()
    {
        var body = HandlerBody();
        Assert.Contains("DeliverDenial(", body);
        Assert.Contains("TryStopWebView", body);
        // 旧形态：handler 自己包 try/catch 把投递异常吞成一行日志、原始请求路径保留。
        // 现在 handler 本体里不该再有 catch——收口全在 DeliverDenial 内（它同时负责升级）。
        Assert.DoesNotContain("catch", body);
        Assert.DoesNotContain("e.Response =", body);
    }

    [Fact]
    public void EscalationTargetIsAnActualStop()
    {
        // 「升级」不能是个空动词：TryStopWebView 必须真的调 CoreWebView2.Stop()。
        var code = CodeOnly();
        var start = RequiredIndex(code, "private static void TryStopWebView(");
        var body = code[start..];
        body = body[..RequiredIndex(body, "\n    }")];
        Assert.Contains("webView.Stop()", body);
    }

    [Fact]
    public void DeliveryAttemptIsSingleShot_WithTheFailureAccountedOnce()
    {
        // 不做「换一组参数再试一次」：会失败的原因是 COM 对象/环境已失效，换参数不改结局，
        // 只会把一次失败刷成两条互不相干的日志。因此响应合成本体不得自己写日志。
        var code = CodeOnly();
        var start = RequiredIndex(code, "private static bool TryCreateDenialResponse(");
        var body = code[start..];
        body = body[..RequiredIndex(body, "\n    }")];
        Assert.DoesNotContain("SecurityLog", body);
        Assert.Equal(1, Occurrences(body, "CreateWebResourceResponse("));
    }

    private string HandlerBody()
    {
        var code = CodeOnly();
        var start = RequiredIndex(code, "private void OnWebResourceRequested(");
        var end = RequiredIndex(code, "\n    internal static void DeliverDenial(");
        return code[start..end];
    }

    /// <summary>剔注释后再判结构：口径单源在 <c>SourceTextAnchors.CodeOnly</c>（R9-B45 / 台账 Q59）。</summary>
    private static string CodeOnly() => SourceTextAnchors.ReadCodeOnly(RepoRoot(), RelativeSource);

    private static int RequiredIndex(string code, string anchor)
    {
        var index = code.IndexOf(anchor, StringComparison.Ordinal);
        Assert.True(
            index >= 0,
            $"结构锚失配：代码里找不到「{anchor}」——子资源守卫形态已改，本用例需同步改写");
        return index;
    }

    private static int Occurrences(string text, string needle)
    {
        var count = 0;
        var at = text.IndexOf(needle, StringComparison.Ordinal);
        while (at >= 0)
        {
            count++;
            at = text.IndexOf(needle, at + needle.Length, StringComparison.Ordinal);
        }

        return count;
    }

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
}

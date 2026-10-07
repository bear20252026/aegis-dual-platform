namespace Aegis.Windows.Core.Tests;

using System;
using System.IO;
using System.Linq;
using System.Runtime.InteropServices;
using Aegis.Windows.WebView;
using Xunit;

/// <summary>⑤（第八轮，用户 2026-10-07 定稿）：子资源策略链的异常处置。
///
/// 改的是 CS-310 取舍的另一半——「单请求异常不影响其他请求」保留，
/// 「异常时保持原始响应路径」去掉：策略层自己出 bug 时，那**一条**子资源按失败
/// 闭合回绝（403 + 审计码 subresource_policy_error），而不是静默放行。
/// 不整页 403、不改导航语义（放行/阻断方向属第七节 1，本批不越界）。
///
/// handler 本体要 COM 对象（`CoreWebView2` 在无 WebView2 Runtime 的作业里构造不出），
/// 所以判定面抽成 <see cref="HostWebView.SubresourceDenialFailClosed"/> 直测，另加一条
/// 结构锚钉住 handler 不得回到「只写日志、不改响应」的旧形态——与 R8-CS-SEC-11 同法：
/// 行为不可达就钉顺序，且必须带正面控制、先剔注释（本仓注记里常抄旧形态原文）。</summary>
public sealed class SubresourceFailClosedTests : IDisposable
{
    private const string RelativeSource =
        "windows/src/Aegis.Windows.App/WebView/HostWebView.WebResourceGuards.cs";

    private readonly string _logDir =
        Path.Combine(Path.GetTempPath(), $"aegis_subresfail_{Guid.NewGuid():N}");

    public SubresourceFailClosedTests()
    {
        Directory.CreateDirectory(_logDir);
        Aegis.Windows.Core.Security.SecurityLog.SecurityLogDirOverride = _logDir;
    }

    public void Dispose()
    {
        Aegis.Windows.Core.Security.SecurityLog.SecurityLogDirOverride = null;
        try { Directory.Delete(_logDir, true); } catch (IOException) { }
    }

    private static HostWebView.WebResourceDenial? Run(
        Func<HostWebView.WebResourceDenial?> evaluate) =>
        HostWebView.SubresourceDenialFailClosed(evaluate, () => "https://img.example/a.png");

    private string LoggedText() =>
        string.Concat(Directory.GetFiles(_logDir).Select(File.ReadAllText));

    // ===== 判定核的行为面 =====

    [Fact]
    public void PassThroughIsPreservedWhenPolicySaysAllow()
    {
        // 反向控制：判定核不得把「策略说放行」擅自改成回绝——否则 ⑤ 除了异常面
        // 还多了一重副作用（整页缺图缺脚本那种事故）。
        HostWebView.WebResourceDenial? Evaluate() => null;

        Assert.Null(Run(Evaluate));
        Assert.Empty(Directory.GetFiles(_logDir));
    }

    [Fact]
    public void PolicyDenialPassesThroughUnchanged()
    {
        HostWebView.WebResourceDenial? Evaluate() =>
            new HostWebView.WebResourceDenial(403, "Blocked");

        Assert.Equal(403, Run(Evaluate)?.Status);
        Assert.Equal("Blocked", Run(Evaluate)?.ReasonPhrase);
    }

    /// <summary>本条就是这个修复的全部意义：策略链抛出不得等于「照常取原始响应」。
    /// 取子资源链真实出现过的四类抛出面（桥租约/COM/会话/dispose 竞态）。</summary>
    [Theory]
    [InlineData(nameof(InvalidOperationException))]
    [InlineData(nameof(NullReferenceException))]
    [InlineData(nameof(ObjectDisposedException))]
    [InlineData(nameof(ExternalException))]
    public void AnyExceptionDuringPolicyEvaluation_BecomesSingleRequestDenial(string kind)
    {
        HostWebView.WebResourceDenial? Evaluate()
        {
            switch (kind)
            {
                case nameof(NullReferenceException): throw new NullReferenceException();
                case nameof(ObjectDisposedException): throw new ObjectDisposedException("CoreWebView2");
                case nameof(ExternalException):
                    // COMException(string, int hr) 是公开构造；ExternalException 的
                    // (int, string) 形态不存在（会绑到 (string?, Exception?) 上 → CS1503）
                    throw new ExternalException("COM 拒绝", unchecked((int)0x80070005));
                default: throw new InvalidOperationException("桥租约已失效");
            }
        }

        Assert.Equal(403, Run(Evaluate)?.Status);
    }

    [Fact]
    public void PolicyException_IsRecordedWithTheAuditCode()
    {
        // 留痕面：异常必须带码可查，否则线上只有一行自由文本、无法按码聚合
        _ = Run(() => throw new InvalidOperationException("跟踪名单读取失败"));
        var text = LoggedText();
        Assert.Contains("subresource_policy_error", text);
        Assert.Contains("InvalidOperationException", text);
        Assert.Contains("img.example", text);   // 脱敏后 host 仍可读
    }

    [Fact]
    public void UnreadableUrlStillYieldsDenial()
    {
        // 取 URL 本身也可能抛（`e.Request` 已退休）。它不能成为「连回绝都做不到」
        // 的理由——所以判定核收 Func<string> 而不是字符串，这里直接钉这个设计。
        var denial = HostWebView.SubresourceDenialFailClosed(
            () => throw new InvalidOperationException("策略读取失败"),
            () => throw new NullReferenceException("e.Request 为 null"));

        Assert.Equal(403, denial?.Status);
        var text = LoggedText();
        Assert.Contains("URL 不可读", text);
        Assert.Contains("subresource_policy_error", text);
    }

    [Fact]
    public void PolicyExceptionDoesNotEscapeToTheCaller()
    {
        // 事件回调里上抛 = 未处理异常 = 进程崩。三层都可能抛（求值、取 URL、写日志），
        // 判定核必须全部吞住并换成一份回绝。
        var swallowed = true;
        try
        {
            _ = Run(() => throw new InvalidOperationException("策略链抛出"));
        }
        catch (Exception)
        {
            swallowed = false;
        }

        Assert.True(swallowed, "⑤ 回退：判定核把异常上抛回事件 shim——进程会当场崩");
    }

    [Fact]
    public void PolicyDenialsUseTheErrorCodeNamedByTheRuling()
    {
        // 码名本身也要钉住（R8-CS-CORE-1 那一类的「改码不红」教训）：改名而不改文档，
        // 运维侧按码聚合的看板会静默失配。
        Assert.Equal("subresource_policy_error", HostWebView.SubresourcePolicyErrorCode);
        _ = Run(() => throw new InvalidOperationException("异常面"));
        Assert.Contains(HostWebView.SubresourcePolicyErrorCode, LoggedText());
    }

    // ===== 结构锚：handler 不得回到「只写日志、不改响应」的旧形态 =====

    [Fact]
    public void HandlerDeniesTheRequestInsteadOfOnlyLogging()
    {
        var code = CodeOnly();
        var seam = RequiredIndex(code, "SubresourceDenialFailClosed(");
        var response = RequiredIndex(code, "e.Response =");
        Assert.True(
            seam < response,
            $"⑤ 回退：处置取得（{seam}）排在了响应赋值（{response}）之后——单请求失败闭合不成立");

        // 旧形态是「整个求值包在 try 里，catch 只写日志、不给响应」。现在判定核调用
        // 本身不在任何 try 之内（它自己吞异常），方法头到调用点之间不得出现 try。
        var head = code[..seam];
        Assert.True(
            head.IndexOf("try", StringComparison.Ordinal) < 0,
            "⑤ 回退：求值又被包回 try/catch——异常会走「保持原始响应路径」的旧出口");
    }

    [Fact]
    public void MoveDidNotNarrowTheExistingDenialSurface()
    {
        // 搬移只改异常出口，不许顺手把既有三类拦截弄窄（黑名单/保留地址边界/跟踪分级）
        var code = CodeOnly();
        foreach (var anchor in new[]
                 {
                     "ReservedAddressBoundary.DeniesRaw",
                     "RecordTrackerBlock(uri, level, e.ResourceContext);",
                     "NtpAssets.IsVirtualHostUrl",
                     "Core.Privacy.TrackerList.IsTracker(uri.Host)",
                     "_privacy.ProtectionLevel",
                 })
        {
            RequiredIndex(code, anchor);
        }

        // 三条拒绝出口（黑名单/边界、跟踪、异常）都仍回 403，且响应只在一处落地
        Assert.Equal(3, Occurrences(code, @"new WebResourceDenial(403, ""Blocked"")"));
        Assert.Equal(1, Occurrences(code, "CreateWebResourceResponse("));
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

    /// <summary>只取 handler 本体与拦截面所在段落：注释行剔掉——本仓注记里常抄旧形态
    /// 原文，不剔就会自我打红（第八轮两次实测的同型事故）。行尾按平台无关方式切分
    /// （检出 LF、工作副本可能 CRLF，按 Environment.NewLine 切会把整份文件当一行）。</summary>
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
        Assert.True(
            index >= 0,
            $"结构锚失配：代码里找不到「{anchor}」——子资源守卫形态已改，本用例需同步改写");
        return index;
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

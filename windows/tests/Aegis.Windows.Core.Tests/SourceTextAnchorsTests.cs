namespace Aegis.Windows.Core.Tests;

using Aegis.Windows.TestSupport;
using Xunit;

/// <summary>
/// 剔注释单源自身的语料用例（R9-B45 / 台账 Q59）——它同时是「C# / Kotlin / Python 三份口径
/// 同形」的锚：语料与期望与 `SourceTextAnchorSupportTest`（Kotlin 两副本）逐条对得上。
/// 每条都配「原文里确实含 token」的恒真防呆，否则「剔完不含」在语料没造出场景时会恒过。
/// </summary>
public class SourceTextAnchorsTests
{
    private const string Token = "trackConsumedNonce(nonceLedgerKey(";

    [Theory]
    [InlineData("        var ok = " + Token + " sessionId, nonce);")]
    [InlineData("    var list = new[] { " + Token + " a, " + Token + " b };")]
    public void CodeLinesSurviveTheStrip(string line)
    {
        Assert.Contains(Token, line);
        Assert.Contains(Token, SourceTextAnchors.CodeOnly(line));
    }

    [Theory]
    [InlineData("    // 旧写法是 " + Token + " ，本批已改")]
    [InlineData("    /* 注记：" + Token + " 只是历史提及 */")]
    [InlineData("/* 说明" + "\n" + " * 历史写法 " + Token + "\n" + " */")]
    public void CommentMentionsNeverCount(string block)
    {
        Assert.Contains(Token, block);
        Assert.DoesNotContain(Token, SourceTextAnchors.CodeOnly(block));
    }

    [Fact]
    public void LineCommentHoldingAFakeBlockOpenDoesNotEatFollowingCode()
    {
        // 顺序判据（R9-B45 收敛时实测撞出来的）：整行注释里的 "https://*" 含一个 `/`+`*`
        // 的假块起点；先做块匹配就会一路吃到下一个 */，把中间的真语句删掉。
        var corpus =
            "        // allowedOriginRules 不接受 \"https://*\" 这种全域通配" + "\n" +
            "        var allowedOrigins = new[] { \"*\" };" + "\n" +
            "        // 下一个块收尾 */ 只是文本";
        Assert.Contains("var allowedOrigins", corpus);
        Assert.Contains("var allowedOrigins", SourceTextAnchors.CodeOnly(corpus));
    }

    [Fact]
    public void PreprocessorAndAttributeLinesAreNotComments()
    {
        // `#` 在 C# 里是预处理指令、在 Rust 里是属性——都不是注释。三份口径里只有 Python
        // 那份按扩展名启用 `#` 形态（R9-B45 无差别剔 `#` 时，core_unwired 的注入用例当场变绿）。
        var withDirective = "#if DEBUG" + "\n" + "        var trace = 1;" + "\n" + "#endif";
        Assert.Contains("#if DEBUG", SourceTextAnchors.CodeOnly(withDirective));
        Assert.Contains("var trace", SourceTextAnchors.CodeOnly(withDirective));
    }

    [Fact]
    public void StrippingIsNotJustDeletingTheWholeText()
    {
        // 恒绿的第三种形态：若实现把整个输入清空，上面两组都会「通过」。
        var mixed = "    var a = " + Token + " s, n);" + "\n" + "    // " + Token + " 历史写法";
        var stripped = SourceTextAnchors.CodeOnly(mixed);
        Assert.False(string.IsNullOrWhiteSpace(stripped));
        Assert.Contains("var a", stripped);
    }

    [Fact]
    public void CarriageReturnsDoNotSilenceTheFilter()
    {
        // 检出是 LF、工作副本可能 CRLF：按平台换行切分会把整份文件当成一行，过滤静默失效
        // （第八轮 B6 由 CI 暴露）。这里用 CRLF 输入，注释必须照样被剔。
        var crlf = "        // " + Token + " 历史写法\r\n        var keep = 1;";
        var stripped = SourceTextAnchors.CodeOnly(crlf);
        Assert.DoesNotContain(Token, stripped);
        Assert.Contains("var keep", stripped);
    }
}

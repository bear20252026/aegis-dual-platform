namespace Aegis.Windows.Core.Tests;

using Aegis.Windows.Core.Security;
using Xunit;

/// <summary>C19b 批（审计 2026-09-26）：UrlRedactor 单源此前全仓零测试。
/// CS-296：孤立代理/256 边界用例（回退截断分支吸收进单源后锁定）。</summary>
public sealed class UrlRedactorTests
{
    [Theory]
    [InlineData(null, "")]
    [InlineData("", "")]
    public void EmptyInput_ReturnsEmpty(string? url, string expected) =>
        Assert.Equal(expected, UrlRedactor.Redact(url));

    [Fact]
    public void AbsoluteUrl_DropsQueryAndFragment()
    {
        // 可解析绝对地址：保留 authority+path，token/搜索词不落审计
        Assert.Equal(
            "https://example.com/path",
            UrlRedactor.Redact("https://example.com/path?token=secret#frag"));
    }

    // ===== CS-337（2026-10-01 审计）：userinfo 泄漏回归 =====

    [Theory]
    [InlineData("https://token@example.com/path", "https://example.com/path")]
    [InlineData("https://token@example.com/path?token=secret#f", "https://example.com/path")]
    [InlineData("https://user:secret@example.com:8443/p?q=1#f", "https://example.com:8443/p")]
    [InlineData("https://token@sub.example.com/", "https://sub.example.com/")]
    public void Userinfo_IsStripped_FromRedactedOutput(string raw, string expected)
    {
        // CS-337：GetLeftPart(Authority) 含 userinfo——https://token@host/ 被
        // 拒后凭据完整落 security.log；改 Scheme + Uri.Authority 组装（实验
        // 确认 .NET 10 的 Uri.Authority 不含 userinfo 且 IPv6 保留方括号）
        Assert.Equal(expected, UrlRedactor.Redact(raw));
    }

    [Fact]
    public void Ipv6Literal_KeepsBrackets_InRedactedOutput()
    {
        // Uri.Host/Authority 对 IPv6 保留方括号——脱敏产物仍是可读合法形态
        Assert.Equal(
            "https://[2001:db8::1]/x",
            UrlRedactor.Redact("https://[2001:db8::1]/x?q=1"));
    }

    [Fact]
    public void AtBoundary256_ReturnedWhole()
    {
        // 恰好 256：不截断不加省略号（>256 才触发回退分支）
        var raw = new string('x', 256);
        Assert.Equal(raw, UrlRedactor.Redact(raw));
    }

    [Fact]
    public void Over256_TruncatesWithEllipsis()
    {
        var raw = new string('x', 300);
        var redacted = UrlRedactor.Redact(raw);
        Assert.Equal(256 + 1, redacted.Length);  // 256 字符 + "…"
        Assert.EndsWith("…", redacted);
        Assert.StartsWith(raw[..256], redacted);
    }

    [Fact]
    public void Over256_SurrogatePairAtCut_NotSplit()
    {
        // CS-296：截断点恰落在高代理项上回退一位——不产生孤立代理
        //（构造：前 255 个 ASCII + emoji（占 2 个 UTF-16 单元）+ 尾巴；
        // 256 处正是该 emoji 的低代理项）
        var raw = new string('a', 255) + "\U0001F600" + new string('b', 50);
        var redacted = UrlRedactor.Redact(raw);
        Assert.EndsWith("…", redacted);
        var body = redacted[..^1];
        Assert.Equal(255, body.Length);                    // 高代理项被回退保护
        Assert.All(body, c => Assert.False(char.IsSurrogate(c)));  // 无孤立代理
    }

    [Fact]
    public void LongNonUrlText_TruncatesSurrogateSafe()
    {
        // 不可解析长文本（无 host）：走回退截断分支——emoji 密集串截断后
        // 仍为完整代理对（256 处是低代理项——无需回退；254/255 恰为一对）
        var raw = string.Concat(Enumerable.Repeat("\U0001F600", 200));  // 400 个 UTF-16 单元
        var redacted = UrlRedactor.Redact(raw);
        Assert.EndsWith("…", redacted);
        var body = redacted[..^1];
        Assert.Equal(256, body.Length);
        Assert.Equal(0, body.Length % 2);  // 全部为完整代理对（无孤立代理）
    }
}

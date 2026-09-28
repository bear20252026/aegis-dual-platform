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

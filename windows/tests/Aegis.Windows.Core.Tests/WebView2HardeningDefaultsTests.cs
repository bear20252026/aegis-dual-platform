namespace Aegis.Windows.Core.Tests;

using System;
using Aegis.Windows.TestSupport;
using Aegis.Windows.WebView;
using Xunit;

/// <summary>
/// WebView2 出货默认的锚（R9-B48 / 台账 R9-CS-3 定稿）。
///
/// 为什么要给它单独一个文件而不是塞进 WebViewPipelineTests：本批改的是**默认值**，
/// 而默认值最容易以「SDK 反正也是这个默认」为由被删掉——本机实测 SDK 1.0.2903.40 的文档
/// （lib_manual/netcoreapp3.0/Microsoft.Web.WebView2.Core.xml）写的是
/// `AreDevToolsEnabled` default true、`IsGeneralAutofillEnabled` default true、
/// `IsPasswordAutosaveEnabled` default **false**。第三条正是「靠默认」最危险的地方：
/// 同一份文档说明「关掉之前已保存的密码仍会被自动填充」，所以这台机器的历史能盖过意图。
/// 这些事实必须有显式赋值 + 能被证伪的锚，而不是笔记。
/// </summary>
public class WebView2HardeningDefaultsTests
{
    private const string HardeningSource =
        "windows/src/Aegis.Windows.App/WebView/WebView2Hardening.cs";

    private static string RepoRoot()
    {
        var dir = new System.IO.DirectoryInfo(AppContext.BaseDirectory);
        while (dir is not null && !System.IO.File.Exists(
                   System.IO.Path.Combine(dir.FullName, "CLAUDE.md")))
        {
            dir = dir.Parent;
        }

        return dir?.FullName ?? throw new InvalidOperationException("未找到仓库根");
    }

    [Theory]
    [InlineData(null, false)]
    [InlineData("", false)]
    [InlineData("0", false)]
    [InlineData("true", false)]
    [InlineData(" 1", false)]
    [InlineData("1", true)]
    public void DevToolsGateIsExactlyOneValue(string? value, bool expected)
    {
        // 「只有 1 开」这条口径必须能被证伪：把比较改成 IsNullOrWhiteSpace 或 startswith 都会红在这里。
        Assert.Equal(expected, WebView2Hardening.DevToolsAllowed(value));
    }

    [Fact]
    public void DevToolsGateVariableIsNamedAndDocumented()
    {
        Assert.Equal("AEGIS_ENABLE_DEVTOOLS", WebView2Hardening.DevToolsEnvironmentVariable);
    }

    [Fact]
    public void HardeningAppliesTheDefaultsInCodeNotComments()
    {
        var code = SourceTextAnchors.ReadCodeOnly(RepoRoot(), HardeningSource);
        Assert.Contains("WebView2Hardening", code); // 正面控制：语料读到了对的文件

        Assert.Equal(1, Occurrences(code, "settings.AreDevToolsEnabled = DevToolsAllowed("));
        Assert.Contains("hardeningProfile.IsGeneralAutofillEnabled = false;", code);
        Assert.Contains("hardeningProfile.IsPasswordAutosaveEnabled = false;", code);
        Assert.Contains(WebView2Hardening.DevToolsEnvironmentVariable, code);
    }

    [Fact]
    public void DevToolsIsNeverTurnedOnByLiteral()
    {
        // 反向锚：把默认改回 true（或写死 true）必须红——本仓的注记里就写着「默认 true」这句事实，
        // 所以判据要先剔注释（R9-B45 的那条纪律在这里被直接用上了）。
        var code = SourceTextAnchors.ReadCodeOnly(RepoRoot(), HardeningSource);
        Assert.DoesNotContain("AreDevToolsEnabled = true", code, StringComparison.Ordinal);
    }

    [Fact]
    public void MissingProfileIsLoggedNotPretended()
    {
        // 「Profile 不可得」的分支必须留痕：静默跳过会让日志声称收紧已应用，而实际没有。
        var code = SourceTextAnchors.ReadCodeOnly(RepoRoot(), HardeningSource);
        Assert.Contains("自动填充收紧未应用", code, StringComparison.Ordinal);
    }

    private static int Occurrences(string haystack, string needle)
    {
        var count = 0;
        var index = 0;
        while ((index = haystack.IndexOf(needle, index, StringComparison.Ordinal)) >= 0)
        {
            count++;
            index += needle.Length;
        }

        return count;
    }
}

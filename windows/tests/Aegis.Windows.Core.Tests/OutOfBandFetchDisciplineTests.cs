namespace Aegis.Windows.Core.Tests;

using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using Xunit;

/// <summary>R9-B33（第九轮队列 Q23）：带外抓取（out-of-band fetch）的读取口径必须单源。
///
/// 判的形态：`HttpClient` 默认 `ResponseContentRead` 会在 `GetAsync` 返回前把整个响应体
/// 缓冲进内存，于是「Content-Length 预检 + 有界读取」这套写法对**不声明长度**的响应
/// 根本不成立——先 OOM 再判定。审计点名的两处（订阅源、favicon）当年都以为自己有上限。
///
/// 判法按**扫描面现取**：从 `windows/src` 里找出所有出现 `GetAsync(` 的文件，逐个要求它
/// 走 `HttpFetchGuard.ReadBoundedAsync`。这样第四条抓取路径出现时不需要有人记得来加白名单
/// （白名单形状的门禁只会保护今天这三个文件，而缺陷恰恰长在新加的那条路上）。
/// 剔除 `//` 注释：本仓的注记会逐字抄着被禁写法（`ReadAsByteArrayAsync()` 就在
/// HttpFetchGuard 的类型注释里），判代码不判注释是同款口径。</summary>
public sealed class OutOfBandFetchDisciplineTests
{
    private const string GuardCall = "HttpFetchGuard.ReadBoundedAsync";

    private static string SourceRoot()
    {
        var dir = new DirectoryInfo(AppContext.BaseDirectory);
        while (dir is not null)
        {
            var candidate = Path.Combine(dir.FullName, "windows", "src");
            if (Directory.Exists(candidate))
                return candidate;
            dir = dir.Parent;
        }
        throw new InvalidOperationException("未从测试输出上溯到 windows/src");
    }

    private static string StripLineComments(string text) => string.Join("\n",
        text.Split('\n').Select(line =>
        {
            var trimmed = line.TrimStart();
            return trimmed.StartsWith("//", StringComparison.Ordinal) ? "" : line;
        }));

    /// <summary>纯函数：给定「一个抓取文件」的代码，返回它的读取口径问题。
    /// 内存态注入用同一份判定，反向锚才落在真逻辑上。</summary>
    private static List<string> FetchProblems(string code)
    {
        var problems = new List<string>();
        if (!code.Contains("GetAsync(", StringComparison.Ordinal))
            return problems;
        if (!code.Contains(GuardCall, StringComparison.Ordinal))
            problems.Add($"没有 {GuardCall}——上限判定又长回调用方了");
        if (code.Contains("ReadAsByteArrayAsync(", StringComparison.Ordinal))
            problems.Add("仍在整包读响应体（超限之后才量长度）");
        if (!code.Contains("ResponseHeadersRead", StringComparison.Ordinal))
            problems.Add("缺 HttpCompletionOption.ResponseHeadersRead——默认缓冲已把整包读进内存");
        return problems;
    }

    /// <summary>扫描面：windows/src 下的手写 C# 源。排除 obj/bin——CI 在跑测试前会
    /// build，生成的 .cs 落进 obj 就被 AllDirectories 一起吸进来，那时本门禁判的
    /// 就不是「我们的代码」了（同款排除口径见 check_file_sizes.py）。</summary>
    private static List<string> SourceFiles() =>
        Directory.GetFiles(SourceRoot(), "*.cs", SearchOption.AllDirectories)
            .Where(path =>
            {
                var rel = Path.GetRelativePath(SourceRoot(), path).Replace('\\', '/');
                return !rel.Split('/').Any(seg => seg == "obj" || seg == "bin");
            })
            .ToList();

    private static List<string> Offenders()
    {
        var offenders = new List<string>();
        foreach (var path in SourceFiles())
        {
            var code = StripLineComments(File.ReadAllText(path));
            var problems = FetchProblems(code);
            if (problems.Count > 0)
                offenders.Add(Path.GetFileName(path) + "：" + string.Join("；", problems));
        }
        return offenders;
    }

    [Fact]
    public void EveryOutOfBandFetchSiteReadsThroughTheSharedGuard()
    {
        Assert.Empty(Offenders());
    }

    [Fact]
    public void ScanSurfaceActuallyFindsTheThreeGuardedPaths()
    {
        // 判据不恒真的另一半证明：扫描面必须真的认得出这三条路（某次重命名把
        // GetAsync 换成 SendAsync 时，本条会红，而不是让上一条静静变成「零个文件」）。
        var names = SourceFiles()
            .Where(path => StripLineComments(File.ReadAllText(path))
                .Contains("GetAsync(", StringComparison.Ordinal))
            .Select(Path.GetFileName)
            .ToList();
        Assert.Equal(
            new[] { "FaviconService.cs", "SourceFetcher.cs", "ThreatFeed.cs" }.OrderBy(n => n),
            names.OrderBy(n => n));
    }

    [Fact]
    public void AnUnguardedFetchSiteIsReported()
    {
        // 反向锚：照旧写法造一个抓取点，判定必须归因到它的三处缺失。
        var legacy = StripLineComments("""
            using var response = await Http.GetAsync(url).ConfigureAwait(false);
            var bytes = await response.Content.ReadAsByteArrayAsync();
            """);
        var problems = FetchProblems(legacy);
        Assert.Contains(problems, p => p.Contains(GuardCall, StringComparison.Ordinal));
        Assert.Contains(problems, p => p.Contains("整包读", StringComparison.Ordinal));
        Assert.Contains(problems, p => p.Contains("ResponseHeadersRead", StringComparison.Ordinal));
        // 纯函数对「没有抓取的普通文件」返回空——否则上面的扫描面会把全仓拖进来判红
        Assert.Empty(FetchProblems("public sealed class Foo { }"));
    }
}

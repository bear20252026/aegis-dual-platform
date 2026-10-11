namespace Aegis.Windows.Broker.Tests;

using System;
using System.IO;
using System.Linq;
using System.Reflection;
using Xunit;

/// <summary>AX-05/AX-06（外部第三轮审计 2026-10-11，第九轮 §四）：
/// 「本构建要求原生策略核心」必须是**编译进产物**的事实，而不是一个普通用户可清除的
/// HKCU 值、或一个只存在于 CI 那一步 shell 里的环境变量。
///
/// 三个判定源合一在 <see cref="NativePolicyCoreGate.ResolveRequirement"/>：
/// 构建常量 ⇒ 环境变量 ⇒ 安装期标记。顺序有语义：前两者不可被终端用户改动，
/// 标记仍是第三来源（升级前装好的旧版本产物里没有构建常量）。
///
/// 本文件同时钉住「验证手段本身成立」这条依赖：字符串常量若没有任何引用点，
/// 不会进入程序集元数据（本机实测 grep 命中 0），发布链那条「在已发布 dll 上找姿态串」
/// 就永远是假绿——所以 App.xaml.cs 的那处引用必须由锚钉住。</summary>
public sealed class NativePolicyCoreBuildRequirementTests
{
    private static readonly string RepoRoot = FindRepoRoot();

    private const string RequiredMarker = "aegis.build.require-native-policy-core=1";
    private const string NotRequiredMarker = "aegis.build.require-native-policy-core=0";

    // ===== 纯判定面：三源合一 =====

    [Theory]
    [InlineData(true, null, false, true)]    // 构建要求 ⇒ 其它两源全缺也必须要求
    [InlineData(true, "0", false, true)]
    [InlineData(true, "1", true, true)]
    [InlineData(false, "1", false, true)]    // 环境变量单独成立（开发/CI 显式打开）
    [InlineData(false, "0", false, false)]   // 只认精确 "1"
    [InlineData(false, "true", false, false)]
    [InlineData(false, null, false, false)]
    [InlineData(false, null, true, true)]    // 安装期标记单独成立（旧版本升级路径）
    public void ResolveRequirement_ThreeSourceOrWithExactEnvValue(
        bool requiredByBuild, string? environmentValue, bool installedMarkerSet, bool expected) =>
        Assert.Equal(expected, NativePolicyCoreGate.ResolveRequirement(
            requiredByBuild, environmentValue, installedMarkerSet));

    [Fact]
    public void BuildConstantIsTheFirstOperand_NotTheLastResort()
    {
        // 反向控制：构建常量若排在「环境变量已清」之后才起作用，用户删掉注册表 +
        // 清掉环境变量就能把要求关掉——那正是审计点名的形态。
        Assert.True(NativePolicyCoreGate.ResolveRequirement(true, null, false));
        Assert.True(NativePolicyCoreGate.ResolveRequirement(true, "0", false));
    }

    [Fact]
    public static void TestBuildDoesNotCarryTheReleaseRequirement()
    {
        // 正向控制：测试/开发构建里常量必须是 false——否则「发布构建才有 true」
        // 这句话无从被验证，而开发机也会在没有 DLL 时全导航 fail-closed。
        Assert.False(NativePolicyCoreBuildMarker.RequiredByThisBuild);
        Assert.Equal(NotRequiredMarker, NativePolicyCoreBuildMarker.BuildPostureMarker);
    }

    // ===== 接线锚：判定源真的被读、常量真的可达 =====

    [Fact]
    public void GateIsRequiredActuallyReadsTheBuildConstant()
    {
        var body = MethodBody("NativePolicyCoreGate.cs", "public static bool IsRequired");
        Assert.Contains("ResolveRequirement(", body);
        Assert.Contains("NativePolicyCoreBuildMarker.RequiredByThisBuild", body);
        // 顺序判据：构建常量必须是第一个实参（与 ResolveRequirement 的语义一致）
        var firstArg = body[(body.IndexOf("ResolveRequirement(", StringComparison.Ordinal)
                           + "ResolveRequirement(".Length)..];
        Assert.True(firstArg.TrimStart().StartsWith("NativePolicyCoreBuildMarker.RequiredByThisBuild"),
            $"构建常量不再是第一操作数：{firstArg.TrimStart()[..Math.Min(60, firstArg.TrimStart().Length)]}");
    }

    [Fact]
    public void PostureStringIsReferencedAtRuntime_OtherwiseNoArtifactCanProveIt()
    {
        // 未被引用的 const 不进元数据（本机实测：加入引用前 grep 命中 0）。
        // 发布链那条「在已发布 dll 上验证姿态串」因此依赖这个引用点存在。
        var app = SourceOf("windows/src/Aegis.Windows.App/App.xaml.cs");
        Assert.Contains("NativePolicyCoreBuildMarker.BuildPostureMarker", app);
    }

    [Fact]
    public void CsprojGeneratesBothBranchesAndCompilesTheFile()
    {
        var csproj = SourceOf("windows/src/Aegis.Windows.App/Aegis.Windows.App.csproj");
        Assert.Contains("GenerateNativePolicyCoreBuildMarker", csproj);
        Assert.Contains("BeforeTargets=\"CoreCompile\"", csproj);
        Assert.Contains("<Compile Include=\"$(IntermediateOutputPath)generated/NativePolicyCoreBuildMarker.g.cs\"",
            csproj);
        // 两条分支都必须能产出：缺 else 分支 ⇒ 开发构建直接编译不起来
        Assert.Contains("'$(RequireNativePolicyCore)' == 'true'", csproj);
        Assert.Contains("'$(_NativeCoreRequired)' == ''", csproj);
        Assert.Contains("RequiredByThisBuild = $(_NativeCoreRequired)", csproj);
        // MSBuild 把裸分号当项分隔符：生成行里的 `;` 必须写 %3B（首版栽过一次，
        // 产物里留下 `RequiredByThisBuild = ;` 即 CS1525）
        Assert.DoesNotContain("RequiredByThisBuild = $(_NativeCoreRequired);", csproj);
    }

    [Fact]
    public void ReleaseWorkflowsMustAssertTheArtifact_NotJustTheCommandLine()
    {
        var release = SourceOf(".github/workflows/release-windows.yml");
        Assert.Contains("RequireNativePolicyCore=true", release);
        // 验终物：在已发布 dll 上找姿态串。注意 workflow 里写的是**正则**形态
        // （点被转义成 \.），所以这里只断言不含前缀转义歧义的那一段——断整串
        // 会因为 `aegis\.` 与 `aegis.` 的差别而恒假，那是「锚看着严、实则永不成立」。
        Assert.Contains(@"require-native-policy-core=1", release);
        Assert.Contains("Encoding]::Unicode", release);
        Assert.Contains(@"require-native-policy-core=0", release);   // 反向：产物里不许出现 require=0
        // ZIP 内容也要验（此前只 Test-Path 发布目录里的 DLL，压缩包从没打开过）
        Assert.Contains("require-native-policy-core-artifact", release);
        Assert.Contains("aegis_policy_core.dll", release);
    }

    [Fact]
    public void AndroidReleaseMustVerifyTheGeneratedBuildConfig()
    {
        var release = SourceOf(".github/workflows/release-android.yml");
        Assert.Contains("-PrequireNativePolicyCore=true", release);
        // 验命令行的参数不等于验编译结果：AGP 生成的 BuildConfig 才是打进 APK 的那个值
        Assert.Contains("REQUIRE_NATIVE_POLICY_CORE", release);
        Assert.Contains("app/build/generated", release);
        // 找不到生成物必须是失败而不是跳过（find 空结果 ⇒ 后面的 grep 恒真）
        Assert.Contains("找不到 release 变体的生成 BuildConfig", release);
    }

    private static string MethodBody(string fileName, string anchor)
    {
        var text = SourceOf($"windows/src/Aegis.Windows.App/Broker/{fileName}");
        var start = text.IndexOf(anchor, StringComparison.Ordinal);
        Assert.True(start >= 0, $"{fileName} 里找不到「{anchor}」——判定源改名了，本锚需同步改写");
        var rest = text[start..];
        var end = rest.IndexOf("\n    }", StringComparison.Ordinal);
        Assert.True(end > 0, $"{fileName}:{anchor} 的定位没有收口——切片会一路读到文件末尾");
        // 剔注释：本仓注记里常抄旧形态原文，不剔会自我打红
        return string.Join("\n", rest[..end].Split('\n')
            .Where(line => !line.TrimStart().StartsWith("//", StringComparison.Ordinal)));
    }

    private static string SourceOf(string relative) =>
        File.ReadAllText(Path.Combine(RepoRoot, relative.Replace('/', Path.DirectorySeparatorChar)))
            .Replace("\r\n", "\n");

    private static string FindRepoRoot()
    {
        var dir = new DirectoryInfo(AppContext.BaseDirectory);
        while (dir is not null && !File.Exists(Path.Combine(dir.FullName, "CLAUDE.md")))
            dir = dir.Parent!;
        Assert.NotNull(dir);
        return dir!.FullName;
    }
}

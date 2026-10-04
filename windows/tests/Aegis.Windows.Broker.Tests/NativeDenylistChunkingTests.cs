namespace Aegis.Windows.Broker.Tests;

using Aegis.Windows.Broker;
using Xunit;

/// <summary>审计第七轮（2026-10-04·R7-RS-02）：威胁名单**分块推送**的纯函数侧。
///
/// 为什么要单独钉：核心 C ABI 的 <c>FFI_INPUT_MAX_BYTES</c> 是 64KiB，而托管侧订阅源
/// 允许 5 MiB（<c>ThreatFeed.MaxBytes</c>）。在只有"整批替换"的版本里，真实规模的名单
/// 必然整批注入失败（<c>ffi_input_too_long</c> → NotPublished），核心侧
/// <c>threat_blocklist</c> 分支因此从不执行——而它在日志里每轮只是"记一次降级"，
/// 看起来像正常工作。分批后新增了两个可失效面：**切批不得丢条目**、**不得有批次撞上限**。
///
/// 本文件的用例都不需要真实 DLL（纯函数 + 应答解析），因此在托管 job 与原生 job 里
/// 都真实执行——不像 R6-13 记过的那批「环境变量缺失即 return」的原生用例。</summary>
public sealed class NativeDenylistChunkingTests
{
    /// <summary>核心侧硬上限：core/rust-policy-core/src/c_abi/mod.rs 的
    /// FFI_INPUT_MAX_BYTES（read_utf8 在 len ≥ 该值时拒批）。</summary>
    private const int CorePayloadCapBytes = 64 * 1024;

    /// <summary>宿主切批预算：NativePolicyCoreBridge.MaxChunkPayloadBytes。
    /// 比核心上限小，留余量给数组括号与序列化误差。</summary>
    private const int ChunkBudgetBytes = 60 * 1024;

    private static int PayloadBytes(IEnumerable<string> batch) =>
        System.Text.Encoding.UTF8.GetByteCount(System.Text.Json.JsonSerializer.Serialize(batch));

    [Fact]
    public void EmptySnapshotStillYieldsOneClearingBatch()
    {
        // "清空核心名单"正是靠 clear=true 的**空批**表达的：不推空批，已撤销的条目
        // 就会在核心侧永久残留（黑名单只增不减 = 越用越严的静默故障）。
        var batches = NativePolicyCoreBridge.EnumerateBatches(Array.Empty<string>());

        Assert.Single(batches);
        Assert.Empty(batches[0]);
    }

    [Fact]
    public void SmallSnapshotTravelsInASingleBatch()
    {
        // 单批时必须仍是 clear=1 的整批替换语义——分批改造不得让常见规模
        // （几十条）变成"追加"，否则旧条目永远抹不掉。
        var hosts = new[] { "bad.example", "evil.example.com", "ads.example" };
        var batches = NativePolicyCoreBridge.EnumerateBatches(hosts);

        Assert.Single(batches);
        Assert.Equal(hosts, batches[0]);
    }

    [Fact]
    public void OversizedSnapshotIsSplitAndDeliveredInFull()
    {
        var hosts = Enumerable.Range(0, 8_000)
            .Select(i => $"host-{i:D5}.deny.example")
            .ToList();

        var batches = NativePolicyCoreBridge.EnumerateBatches(hosts);

        // 真实规模必然跨批——这正是修复前"整批必拒"的那个量级
        Assert.True(batches.Count > 1, $"8000 条应切成多批，实得 {batches.Count}");
        // 且一条不丢、顺序不变（首批 clear=1 建立快照，其余追加）
        Assert.Equal(hosts, batches.SelectMany(b => b).ToList());
    }

    [Fact]
    public void NoBatchExceedsTheCorePayloadCap()
    {
        var hosts = Enumerable.Range(0, 3_000)
            .Select(i => $"sub{i}.malware.example.org")
            .ToList();

        var batches = NativePolicyCoreBridge.EnumerateBatches(hosts);

        Assert.NotEmpty(batches);
        foreach (var batch in batches)
        {
            var bytes = PayloadBytes(batch);
            Assert.True(bytes <= ChunkBudgetBytes,
                $"批次序列化后 {bytes} 字节，超过切批预算 {ChunkBudgetBytes}");
            // 外部真约束：任何一批都不得撞上核心 read_utf8 的硬上限——
            // 撞上的那一批是**被整批拒**，不是被截断，会静默少一段名单
            Assert.True(bytes < CorePayloadCapBytes,
                $"批次 {bytes} 字节将撞核心 FFI_INPUT_MAX_BYTES={CorePayloadCapBytes}");
        }
    }

    [Fact]
    public void MultiByteHostsAreChargedByUtf8BytesNotChars()
    {
        // 计费按 UTF-8 字节：若按字符数切批，非 ASCII 条目（punycode 之外的
        // 国际化域名形态）会让真实载荷超预算、整批被核心拒收。
        var hosts = Enumerable.Range(0, 2_000)
            .Select(i => $"xn--roca{i:D5}-.example")
            .Concat(Enumerable.Range(0, 2_000).Select(i => $"日本語{i:D5}.example"))
            .ToList();

        var batches = NativePolicyCoreBridge.EnumerateBatches(hosts);

        Assert.True(batches.Count > 1);
        Assert.Equal(hosts, batches.SelectMany(b => b).ToList());
        Assert.All(batches, batch => Assert.True(PayloadBytes(batch) < CorePayloadCapBytes));
    }

    [Fact]
    public void CoreEchoOfClearParameterIsDetectedInResponseEnvelope()
    {
        // 符号名区分不了"2 参旧核心"与"3 参新核心"（ABI 版本仍 v3、就地加参），
        // 应答里的 clear 回显是唯一探针。多批推送时缺回显必须中止：否则每批各自
        // 整批替换，最终快照只剩最后一批——又一个"看起来在工作"的残缺名单。
        var withoutEcho = NativePolicyCoreBridge.ParseUpdateResponse(
            """{"decision":"ok","accepted":3,"input":3}""", 3);
        var withEcho = NativePolicyCoreBridge.ParseUpdateResponse(
            """{"decision":"ok","accepted":3,"input":3,"clear":true}""", 3);

        Assert.True(withoutEcho.Published);
        Assert.False(withoutEcho.CoreEchoesClear);
        Assert.True(withEcho.CoreEchoesClear);
    }

    [Fact]
    public void RejectedEntriesRemainVisibleInsteadOfSilentDeadEntries()
    {
        // accepted < input 必须原样带出：被核心形态校验拒收的条目在核心侧是
        // "登记了但永不命中"的死条目，静默吞掉正是这个缺口藏了五轮的原因。
        var partial = NativePolicyCoreBridge.ParseUpdateResponse(
            """{"decision":"ok","accepted":7,"input":10,"clear":true}""", 10);

        Assert.Equal(CoreDenylistOutcome.PartiallyPublished, partial.Outcome);
        Assert.Equal(3, partial.RejectedEntryCount);
        Assert.True(partial.Published);   // 核心确实收了这批（只是部分条目）
        Assert.True(partial.CoreEchoesClear);
    }

    [Fact]
    public void DenyAndUnparsableResponsesAreReportedAsNotPublished()
    {
        var denied = NativePolicyCoreBridge.ParseUpdateResponse(
            """{"decision":"deny","reason":{"code":"ffi_input_too_long"}}""", 5_000);
        var broken = NativePolicyCoreBridge.ParseUpdateResponse("not json", 5_000);
        var missingInput = NativePolicyCoreBridge.ParseUpdateResponse(
            """{"decision":"ok","accepted":4}""", 9);

        Assert.Equal(CoreDenylistOutcome.NotPublished, denied.Outcome);
        Assert.Equal("ffi_input_too_long", denied.Detail);   // 修复前的真实故障码
        Assert.Equal(CoreDenylistOutcome.NotPublished, broken.Outcome);
        Assert.Equal("native_denylist_response_unparsable", broken.Detail);
        // 应答缺 input 时退回本地 offered 数（9），据差异额算出被拒条目数——
        // 绝不因缺字段把 5 条未确认条目报成"全收"
        Assert.Equal(9, missingInput.Input);
        Assert.Equal(5, missingInput.RejectedEntryCount);
    }
}

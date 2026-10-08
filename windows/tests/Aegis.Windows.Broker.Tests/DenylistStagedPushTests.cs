namespace Aegis.Windows.Broker.Tests;

using Aegis.Windows.Broker;
using Xunit;

/// <summary>⑨（第八轮 R8-RS-14）：黑名单分批注入的**暂存 + 提交**协议与混版三态。
///
/// 修掉的形态：首批 <c>clear=1</c> 立即清空活动快照、只装入第一批 ⇒ 5 MiB 名单
/// 约 85 批的推送窗口内，导航判定读的是不完整名单（未推到的恶意 host 一律
/// Allow）；任一批失败则核心永久保留前缀，判定侧无从分辨。现在提交前
/// 判定始终读上一份完整快照，半途失败只是"没提交"。
///
/// 走的是纯逻辑接缝 <see cref="NativePolicyCoreBridge.DriveDenylistPush"/> +
/// 假核心（不依赖原生 DLL）——R8-CI-18 的教训：真桥用例在 PR 必需检查里集体早退，
/// 协议判据必须在任何机器上都真跑。</summary>
public sealed class DenylistStagedPushTests
{
    /// <summary>假核心：按 Rust 侧 <c>HostDenylist::apply</c> 的档位语义演化状态，
    /// 并把每次调用的档位记下来（协议顺序是本类的主要判据）。</summary>
    private sealed class FakeCore
    {
        // 提交是整体换（与核心侧一致），所以这里可以重新赋值而不是原地增删
        private HashSet<string> _active = [];
        private HashSet<string>? _staging;

        public List<int> Modes { get; } = [];
        public List<int> BatchSizes { get; } = [];
        public bool SupportsModes { get; set; } = true;
        public bool SupportsClear { get; set; } = true;
        public int? FailOnCallIndex { get; set; }
        public int? RefuseCommit { get; set; }
        /// <summary>模拟核心形态校验拒收：该次调用少报一条 accepted。</summary>
        public int? ShapeRejectAtCall { get; set; }

        /// <summary>提交前判定读到的这一份（测试用来断言"推送窗口内不残缺"）。</summary>
        public IReadOnlyCollection<string> ServedNow => _active;

        public bool SessionOpen => _staging is not null;

        public NativePolicyCoreBridge.DenylistAck Send(List<string> batch, int mode)
        {
            Modes.Add(mode);
            BatchSizes.Add(batch.Count);
            if (FailOnCallIndex == Modes.Count - 1)
                return Refused("native_denylist_denied");

            var accepted = 0;
            var payload = batch;
            var reject = ShapeRejectAtCall == Modes.Count - 1 && batch.Count > 0;
            if (reject)
                payload = batch[..^1];  // 形态拒收：那一条不落地（核心侧真会丢它）

            // SupportsModes=false 就是 3 参旧核心：非 0 一律当"清空并整批替换"，
            // 不认识暂存/提交档位，也不回显 mode——宿主必须能带着它走完既往链。
            var staged = false;
            if (!SupportsModes)
            {
                _staging = null;
                if (mode == NativePolicyCoreBridge.DenylistModeAppend)
                    _active.UnionWith(payload);
                else
                {
                    _active.Clear();
                    _active.UnionWith(payload);
                }
            }
            else
            {
                switch (mode)
                {
                    case NativePolicyCoreBridge.DenylistModeBegin:
                        _staging = new HashSet<string>(payload);
                        staged = true;
                        break;
                    case NativePolicyCoreBridge.DenylistModeAppend when _staging is not null:
                        _staging.UnionWith(payload);
                        staged = true;
                        break;
                    case NativePolicyCoreBridge.DenylistModeAppend:
                        _active.UnionWith(payload);
                        break;
                    case NativePolicyCoreBridge.DenylistModeReplace:
                        _staging = null;
                        _active.Clear();
                        _active.UnionWith(payload);
                        break;
                    default:
                        // 提交：无会话可提交时什么都不换（与核心侧逐字同语义）。
                        // accepted 报的是「这次换没换快照」——Rust 侧 commit 分支同理，
                        // 宿主靠它区分「提交成功」与「无会话可提交」，两者 payload 都是空。
                        if (RefuseCommit != Modes.Count - 1 && _staging is not null)
                        {
                            _active = _staging;
                            _staging = null;
                            accepted = 1;
                        }

                        break;
                }
            }

            if (SupportsModes && mode != NativePolicyCoreBridge.DenylistModeCommit)
                accepted = payload.Count;
            return new NativePolicyCoreBridge.DenylistAck(
                true, accepted, batch.Count, SupportsClear, SupportsModes, staged,
                _active.Count, "ok");
        }
        private static NativePolicyCoreBridge.DenylistAck Refused(string detail) =>
            new(false, 0, 0, false, false, false, -1, detail);
    }

    private static List<List<string>> Batches(int count, int perBatch = 2) =>
        Enumerable.Range(0, count)
            .Select(index => Enumerable.Range(0, perBatch)
                .Select(slot => $"host{index}-{slot}.example")
                .ToList())
            .ToList();

    [Fact]
    public void StagedPushCommitsOnlyAfterEveryBatchLands()
    {
        var core = new FakeCore();
        core.Send(["stale.example"], NativePolicyCoreBridge.DenylistModeReplace);
        core.Modes.Clear();
        var batches = Batches(3);

        var result = NativePolicyCoreBridge.DriveDenylistPush(
            batches, core.Send, batches.Sum(batch => batch.Count));

        Assert.Equal(CoreDenylistOutcome.Published, result.Outcome);
        Assert.Equal(
            [
                NativePolicyCoreBridge.DenylistModeBegin,
                NativePolicyCoreBridge.DenylistModeAppend,
                NativePolicyCoreBridge.DenylistModeAppend,
                NativePolicyCoreBridge.DenylistModeCommit,
            ],
            core.Modes);
        Assert.Equal(6, core.ServedNow.Count);
        Assert.False(core.SessionOpen);
    }

    [Fact]
    public void MidChainFailureNeverCommits_AndPreviousSnapshotKeepsServing()
    {
        // 这是 ⑨ 的全部意义：半途断掉时，判定侧读到的仍是上一份**完整**名单，
        // 而不是"清空后已推前缀"的残缺快照。
        var core = new FakeCore { FailOnCallIndex = 2 }; // 第 3 次调用（第二批追加）断掉
        core.Send(["keeper-a.example", "keeper-b.example"],
            NativePolicyCoreBridge.DenylistModeReplace);
        var before = core.ServedNow.ToList();
        core.Modes.Clear();

        var batches = Batches(4);
        var result = NativePolicyCoreBridge.DriveDenylistPush(
            batches, core.Send, batches.Sum(batch => batch.Count));

        Assert.Equal(CoreDenylistOutcome.NotPublished, result.Outcome);
        Assert.DoesNotContain(NativePolicyCoreBridge.DenylistModeCommit, core.Modes);
        Assert.Equal(2, core.ServedNow.Count);
        Assert.Equal(before.OrderBy(host => host), core.ServedNow.OrderBy(host => host));
        Assert.Contains("未提交", result.Detail);
        Assert.Contains("上一份完整", result.Detail);
        // 旧措辞不得复活：它把"清空 + 半截前缀"写成了无害的"保留前缀"
        Assert.DoesNotContain("保留已推送前缀", result.Detail);
    }

    [Fact]
    public void CoreWithoutModeEchoFallsBackToTheLegacyReplaceThenAppendChain()
    {
        // 混版：新宿主 + 3 参旧核心。不假装拿到原子性——走既往链，
        // 且保留"缺 clear 回显即中止"的旧判据。
        var core = new FakeCore { SupportsModes = false };
        var batches = Batches(3);

        NativePolicyCoreBridge.DriveDenylistPush(batches, core.Send, 6);

        // 旧核心把 Begin(2) 当成既往的"清空 + 整批替换"，链照旧推完 ⇒
        // 最终名单完整，且宿主没有对旧核心发提交（发了会被当成又一次清空）。
        Assert.DoesNotContain(NativePolicyCoreBridge.DenylistModeCommit, core.Modes);
        Assert.Equal(6, core.ServedNow.Count);

        var blind = new FakeCore { SupportsModes = false, SupportsClear = false };
        var lost = NativePolicyCoreBridge.DriveDenylistPush(batches, blind.Send, 6);
        Assert.Equal(CoreDenylistOutcome.NotPublished, lost.Outcome);
        Assert.Contains("core_lacks_clear_parameter", lost.Detail);
    }

    [Fact]
    public void SingleBatchStaysAPlainReplace()
    {
        // 一批即完整：整批替换本就原子，开会话只是多两次 FFI 往返。
        var core = new FakeCore();
        var batches = Batches(1);

        var result = NativePolicyCoreBridge.DriveDenylistPush(batches, core.Send, 2);

        Assert.Equal(CoreDenylistOutcome.Published, result.Outcome);
        Assert.Equal([NativePolicyCoreBridge.DenylistModeReplace], core.Modes);
    }

    [Fact]
    public void RefusedCommitIsReportedNotSilentlyTreatedAsPublished()
    {
        // 核心若拒绝提交（无会话可提交=协议被写坏），宿主必须看见失败，
        // 否则日志会写"已发布"而判定侧读的还是旧名单。
        var core = new FakeCore { RefuseCommit = 3 };
        var batches = Batches(3);

        var result = NativePolicyCoreBridge.DriveDenylistPush(
            batches, core.Send, batches.Sum(batch => batch.Count));

        Assert.Equal(CoreDenylistOutcome.NotPublished, result.Outcome);
        Assert.Contains("denylist_commit_refused", result.Detail);
    }

    [Fact]
    public void PartialAcceptStillCommitsAndKeepsTheRejectedCountVisible()
    {
        // 形态拒收不中止（托管侧仍在拦那些条目），但差额必须原样留给日志——
        // 静默吞掉正是这个缺口藏了五轮的原因。
        var core = new FakeCore { ShapeRejectAtCall = 0 };
        var batches = new List<List<string>>
        {
            new() { "a.example", "bad..entry" },
            new() { "b.example" },
        };

        var result = NativePolicyCoreBridge.DriveDenylistPush(batches, core.Send, 3);

        Assert.Equal(CoreDenylistOutcome.PartiallyPublished, result.Outcome);
        Assert.Contains(NativePolicyCoreBridge.DenylistModeCommit, core.Modes);
        Assert.Equal(1, result.RejectedEntryCount);
        Assert.Equal(2, core.ServedNow.Count);
    }

    [Fact]
    public void ModeValuesMatchTheCoreContractExactly()
    {
        // 跨语言常量的数值契约：核心 denylist::MODE_* 与这里是同一组字面量。
        // 任何一侧改值都会让另一侧把"整批替换"当成"追加"（静默失配，无异常）。
        Assert.Equal(0, NativePolicyCoreBridge.DenylistModeAppend);
        Assert.Equal(1, NativePolicyCoreBridge.DenylistModeReplace);
        Assert.Equal(2, NativePolicyCoreBridge.DenylistModeBegin);
        Assert.Equal(3, NativePolicyCoreBridge.DenylistModeCommit);
    }

    [Fact]
    public void AckParsingReadsTheCapabilityFields()
    {
        var staged = NativePolicyCoreBridge.ParseDenylistAck(
            """{"decision":"ok","accepted":3,"input":3,"clear":false,"mode":2,"staged":true,"served":1}""",
            3);
        Assert.True(staged.Published);
        Assert.True(staged.EchoesMode);
        Assert.True(staged.Staged);
        Assert.Equal(1, staged.Served);

        var legacy = NativePolicyCoreBridge.ParseDenylistAck(
            """{"decision":"ok","accepted":3,"input":3,"clear":true}""", 3);
        Assert.True(legacy.EchoesClear);
        Assert.False(legacy.EchoesMode);
        Assert.False(legacy.Staged);
        Assert.Equal(-1, legacy.Served);

        // 信封缺失字段/坏 JSON 一律不猜：Published=false 且 reason 可读
        Assert.False(NativePolicyCoreBridge.ParseDenylistAck("{", 3).Published);
        var denied = NativePolicyCoreBridge.ParseDenylistAck(
            """{"decision":"deny","reason":{"code":"denylist_mode_invalid"}}""", 3);
        Assert.False(denied.Published);
        Assert.Equal("denylist_mode_invalid", denied.Detail);
    }
}

namespace Aegis.Windows.Broker;

using System;
using System.Collections.Generic;
using System.Text.Json;

/// <summary>原生黑名单注入的**分批协议**（第八轮 ⑨，R8-RS-14）。
///
/// 从 <c>NativePolicyCoreBridge.Denylist.cs</c> 拆出：那个分片停在 300 行红线上，
/// 而本协议是纯逻辑（不碰句柄/租约），拆出来才可在无原生 DLL 的常跑门禁里直测
///（R8-CI-18 的教训：原生用例在 PR 门禁集体早退，等于没有覆盖）。
///
/// 协议：核心侧 <c>clear</c> 参数已从布尔扩成档位——0 追加 / 1 整批替换 /
/// 2 开一次暂存会话 / 3 提交会话。**提交前，判定读的始终是上一份完整快照**，
/// 这就是 ⑨ 要修的东西：既往「首批 clear=1 立即清空 + 只装入第一批」意味着
/// 5 MiB 名单的约 85 批推送窗口内，未推到的恶意 host 一律 Allow；任一批失败则
/// 核心永久保留前缀。现在半途失败只是"没提交"，活动快照纹丝不动。
///
/// 混版三态（缺一不可有明确行为）：
/// • 新宿主 + 新核心：应答回显 <c>mode</c> ⇒ 走暂存 + 提交。
/// • 新宿主 + 旧核心（只回显 <c>clear</c>）：退回既往的分批替换链（并保留原有的
///   <c>core_lacks_clear_parameter</c> 判据）——不假装拿到了原子性。
/// • 旧宿主 + 新核心：只发 0/1，走的仍是既往路径，逐字不变（⑨ 的核心兼容性要求）。</summary>
public sealed partial class NativePolicyCoreBridge
{
    /// <summary>与核心 <c>denylist::MODE_*</c> 逐值对应（跨语言常量，改一边必须改另一边；
    /// 值语义由 <c>DenylistProtocolTests</c> 与核心侧测试各自钉住）。</summary>
    internal const int DenylistModeAppend = 0;

    internal const int DenylistModeReplace = 1;
    internal const int DenylistModeBegin = 2;
    internal const int DenylistModeCommit = 3;

    /// <summary>核心对单批调用的应答（含协议字段）。与
    /// <see cref="CoreDenylistUpdateResult"/> 的分工：本类型是"这一批怎么样"，
    /// 后者是"这一轮整体怎么样"。</summary>
    internal readonly record struct DenylistAck(
        bool Published,
        int Accepted,
        int Input,
        bool EchoesClear,
        bool EchoesMode,
        bool Staged,
        int Served,
        string Detail);

    /// <summary>解析注入应答。信封刻意不含 abi_version（与决策信封不同），所以
    /// 能力探测只能靠字段自身：<c>mode</c> 在场 = 该核心支持暂存协议；只有
    /// <c>clear</c> = 3 参旧核心；两者皆无 = 2 参旧核心（会忽略多余实参）。</summary>
    internal static DenylistAck ParseDenylistAck(string payload, int input)
    {
        try
        {
            using var document = JsonDocument.Parse(payload);
            var root = document.RootElement;
            var decision = root.TryGetProperty("decision", out var node) ? node.GetString() : null;
            if (decision != "ok")
            {
                var code = root.TryGetProperty("reason", out var reason)
                    && reason.TryGetProperty("code", out var value)
                    ? value.GetString() ?? "native_denylist_denied"
                    : "native_denylist_response_not_ok";
                return new DenylistAck(false, 0, input, false, false, false, -1, code);
            }

            var accepted = ReadNonNegative(root, "accepted");
            // 核心如实回报 input；应答缺失时退回本地 offered 数（不虚报成功）
            var offered = root.TryGetProperty("input", out _) ? ReadNonNegative(root, "input") : input;
            var echoesClear = root.TryGetProperty("clear", out _);
            var echoesMode = root.TryGetProperty("mode", out _);
            var staged = echoesMode
                && root.TryGetProperty("staged", out var flag) && flag.ValueKind == JsonValueKind.True;
            var served = echoesMode && root.TryGetProperty("served", out var count)
                ? ReadNonNegative(root, "served")
                : -1;
            return new DenylistAck(
                true, accepted, offered, echoesClear, echoesMode, staged, served,
                accepted < offered ? "partial_accept" : "ok");
        }
        catch (Exception)
        {
            return new DenylistAck(false, 0, input, false, false, false, -1,
                "native_denylist_response_unparsable");
        }
    }

    private static int ReadNonNegative(JsonElement root, string name) =>
        root.TryGetProperty(name, out var value) && value.TryGetInt32(out var number) && number >= 0
            ? number
            : 0;

    /// <summary>推送一条完整快照：优先走「暂存 + 提交」，核心不认档位时退回既往链。
    ///
    /// <paramref name="send"/> 是唯一的对外接缝（批次 + 档位 → 应答），单测因此能
    /// 扮演"支持暂存的核心""只回显 clear 的核心""第 N 批断掉的核心"三种混版态。
    ///
    /// 暂存路径的中止条件只有一个：某一批整批被拒。<b>不</b>在部分接受（形态拒收）
    /// 时中止——被拒条目在托管侧仍被拦，与既往口径一致，最终以 PartiallyPublished 呈现。
    /// 中止时不发提交，核心继续服务上一份完整名单（Detail 如实写明"未提交"，
    /// 不再写"保留已推送前缀"那种半截话）。
    /// 单批快照不发会话：一批即完整，mode=1 的整批替换本就原子（少一次 FFI 往返）。</summary>
    internal static CoreDenylistUpdateResult DriveDenylistPush(
        List<List<string>> batches,
        Func<List<string>, int, DenylistAck> send,
        int input)
    {
        if (batches.Count == 0)
            return CoreDenylistUpdateResult.NotPublished(input, "denylist_no_batch");

        var first = send(batches[0], batches.Count == 1 ? DenylistModeReplace : DenylistModeBegin);
        if (!first.Published)
            return Fail(first, input, 0);
        if (batches.Count == 1)
            return CoreDenylistUpdateResult.Apply(first.Accepted, input, first.EchoesClear);
        if (!first.EchoesMode)
            return LegacyPush(first, batches, send, input);

        var accepted = first.Accepted;
        for (var index = 1; index < batches.Count; index++)
        {
            var ack = send(batches[index], DenylistModeAppend);
            if (!ack.Published)
                return Fail(ack, input, index);
            accepted += ack.Accepted;
        }

        var commit = send([], DenylistModeCommit);
        if (!commit.Published)
            return Fail(commit, input, batches.Count);
        if (!commit.Staged && commit.Accepted == 0)
            return CoreDenylistUpdateResult.NotPublished(input, "denylist_commit_refused");
        return CoreDenylistUpdateResult.Apply(accepted, input, first.EchoesClear);
    }

    /// <summary>既往协议（R7-RS-02）：首批 <c>clear=1</c> 立即生效 + 其余追加。
    /// 只在核心不回显 <c>mode</c> 时走这里。中止时核心侧留下的确实是**已推送前缀**
    /// （首批即带清空），所以 Detail 必须那样写——这条措辞本身就是缺陷记录。</summary>
    private static CoreDenylistUpdateResult LegacyPush(
        DenylistAck first,
        List<List<string>> batches,
        Func<List<string>, int, DenylistAck> send,
        int input)
    {
        var accepted = first.Accepted;
        if (batches.Count > 1 && !first.EchoesClear)
            return new CoreDenylistUpdateResult(
                CoreDenylistOutcome.NotPublished, accepted, input,
                $"core_lacks_clear_parameter@0（核心侧保留已推送前缀 {accepted} 条）");
        for (var index = 1; index < batches.Count; index++)
        {
            var ack = send(batches[index], DenylistModeAppend);
            if (!ack.Published)
                return new CoreDenylistUpdateResult(
                    CoreDenylistOutcome.NotPublished, accepted, input,
                    $"denylist_chunk_failed@{index}（核心侧保留已推送前缀 {accepted} 条）");
            accepted += ack.Accepted;
        }

        return CoreDenylistUpdateResult.Apply(accepted, input, first.EchoesClear);
    }

    private static CoreDenylistUpdateResult Fail(DenylistAck ack, int input, int batchIndex) =>
        new(
            CoreDenylistOutcome.NotPublished,
            ack.Accepted,
            input,
            $"denylist_staged_push_aborted@{batchIndex}（{ack.Detail}）——未提交，"
            + "核心侧仍服务上一份完整黑名单快照");
}

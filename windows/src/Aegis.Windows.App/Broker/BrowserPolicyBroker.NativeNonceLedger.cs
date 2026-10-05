namespace Aegis.Windows.Broker;

/// <summary>原生 nonce 的账本键推导（<see cref="BrowserPolicyBroker"/> 的
/// partial 分片——单独成文件是为了让它能在**无原生库**的常跑门禁里被断言）。</summary>
public sealed partial class BrowserPolicyBroker
{
    /// <summary>把原生核心返回的裸 nonce 折算成本仓账本键（<c>sessionId:nonce</c>）。</summary>
    /// <remarks>
    /// R8-CS-REG-01（第八轮 2026-10-05，**本轮 B4 修复自身引入的回归**）：这一句原本写成
    /// <c>"${sessionId}:${action.Nonce}"</c>——C# 里没有前导 <c>$</c> 的字符串不是内插串，
    /// 于是每一次原生导航消费都往账本里记同一个**常量**：第一次放行，第二次起
    /// <c>TryRecordConsumedNonce</c> 恒 false ⇒ 全部后续导航以 <c>nonce_replay</c> 被拒。
    /// 装机的注册表标记使原生模式正是**出货配置**，等于第一次导航后浏览器即锁死。
    ///
    /// 为什么 CI 全绿却看不见：原生分支的行为用例都要 <c>AEGIS_NATIVE_POLICY_CORE_TEST_PATH</c>
    /// 才不早退，而该变量只在 <c>native-policy-artifacts.yml</c>（master push + paths 过滤）
    /// 与 <c>release-windows.yml</c>（发布）里赋值——两者都不是 PR 的必需检查。
    /// 必需检查 <c>contract-source-of-truth/windows-contract-build</c> 跑
    /// <c>dotnet test</c> 时该分支**零行为覆盖**（R8-CS-CORE-2 的根因）。
    ///
    /// 因此把键推导抽成纯函数：格式与「不同 nonce 必须得到不同键」这两条不依赖原生库，
    /// 在常跑门禁里就红（<c>NativeNonceLedgerKeyTests</c>）。端到端的双次消费仍另有一条
    /// 真桥用例（<c>BrowserPolicyBrokerNativeGateTests</c>，env 门控）——它证明调用点
    /// 确实走的是这个函数；文本锚只能证明「源码长这样」，证明不了数学。
    /// </remarks>
    internal static string NativeNonceLedgerKey(string sessionId, string nonce) =>
        $"{sessionId}:{nonce}";
}

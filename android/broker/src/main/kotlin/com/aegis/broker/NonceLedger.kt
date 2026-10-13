// 已消费 nonce 的账本键与回收判据（R9-AD-5 / 第九轮 2026-10-13）。
//
// 两条写入形态不同源：托管路径的 nonce 由 `AndroidBroker.newNonce` 生成，本身就是
// `sessionId:token`；原生路径的 nonce 是 Rust 核心发的 64 位裸 hex，**没有前缀**
// （`NativePolicyCoreBridge` 原样取 `nonce` 字段）。而回收侧
// （`AndroidBroker.destroySession`）按 `sessionId:` 前缀摘条目 ⇒ 原生形态写进去的
// 条目一条也摘不掉：那句 KDoc 承诺的「移除其已消费 nonce」在**启用原生核心的出货
// 配置**里是空话，残留条目还会长期挤占 `MAX_CONSUMED_NONCES` 的 FIFO 名额。
//
// 口径：写入前统一折算成会话作用域键（幂等——托管形态保持不变，不叠第二层前缀），
// 回收判据与键共用 nonceLedgerPrefix 这一个约定，两侧不可能再各抄一份。
//
// 与 Windows 侧 `BrowserPolicyBroker.NativeNonceLedgerKey`（R8-CS-REG-01，那条
// 「账本满后全站导航永久锁死」的自 DoS）同一职责：把键推导抽成**纯函数**，不需要
// 原生库或真桥就能在常跑门禁里断言——文本锚只能证明「源码长这样」，证明不了数学。
package com.aegis.broker

/** 账本键的会话前缀——写入与回收共用的唯一约定。 */
internal fun nonceLedgerPrefix(sessionId: String): String = "$sessionId:"

/** 把两种形态的 nonce 折算成会话作用域的账本键（幂等）。 */
internal fun nonceLedgerKey(
    sessionId: String,
    nonce: String,
): String {
    val prefix = nonceLedgerPrefix(sessionId)
    return if (nonce.startsWith(prefix)) nonce else "$prefix$nonce"
}

/** 账本条目是否属于该会话（回收判据）。 */
internal fun String.belongsToNonceLedger(sessionId: String): Boolean = startsWith(nonceLedgerPrefix(sessionId))

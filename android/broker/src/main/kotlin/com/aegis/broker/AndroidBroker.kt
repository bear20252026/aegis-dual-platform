package com.aegis.broker

import kotlin.time.Duration.Companion.seconds

/**
 * 阶段 D（蓝图 android/broker）：Android 侧 capability broker adapter——唯一允许
 * 产生本地副作用的边界（ADR-002）。验证来源/会话/标签代际/scope/参数/预算/批准/
 * nonce——没有 AuthorizedAction 不能导航/下载/导出/改策略。默认拒绝（fail-closed）。
 * 与 Windows BrowserPolicyBroker 同语义——同一 contracts（url-origin 向量）。
 */
class AndroidBroker(
    private val policyVersion: String = "1.0",
    private val nativePolicyCoreGate: NativePolicyCoreGate = DefaultNativePolicyCoreGate,
    // AD-020（2026-09-24 审计）：时钟可注入——SESSION_TTL 过期/滑动语义可 JVM
    // 单测（此前 Clock.System 硬编码，过期行为不可测）。
    private val clock: kotlinx.datetime.Clock = kotlinx.datetime.Clock.System,
) {
    private val consumedNonces =
        java.util.LinkedHashSet<String>()
    private val sessions = java.util.concurrent.ConcurrentHashMap<String, SessionContext>()
    private val authorizationLock = Any()
    private val nativePolicyCoreBridge =
        if (BuildConfig.REQUIRE_NATIVE_POLICY_CORE) {
            NativePolicyCoreBridge.tryCreate(policyVersion)
        } else {
            null
        }

    companion object {
        /**
         * 原生核心会话 TTL（秒）。P0 修复（全量复审 2026-09-01）：此前硬编码
         * 在 registerSession 调用点且无续期——应用启动 2 分钟后所有导航被
         * session_expired 拒绝（真机复现）。常量单源 + renewSession 滑动续期。
         */
        const val SESSION_TTL_SECONDS = 120L

        /**
         * P2 修复（全量复审 2026-09-01）：已消费 nonce 有界（FIFO 逐出最旧）。
         * 逐出的 nonce 对应授权对象 SESSION_TTL_SECONDS 内即过期（isValid
         * 校验 expiresAt），重放窗口远小于逐出周期——有界性不以安全性换取。
         */
        const val MAX_CONSUMED_NONCES = 50_000

        /**
         * AD-180（审计 2026-09-23 清单·A7 批）：scheme → 默认端口查表——
         * 原 `if (https) 443 else 80` 把一切非 https scheme 都折叠成 80
         * （脆弱：新增 scheme 时默认端口静默错误）。改为显式查表，未知
         * scheme 无默认端口（始终按显式端口展示处理——端口折叠只对
         * 表内 scheme 生效）。
         */
        private val DEFAULT_PORTS = mapOf("http" to 80, "https" to 443)

        /**
         * AD-142（审计 2026-09-23 清单·A6 批）：nonce 组装抽函数——原内联于
         * evaluateNavigation 的 AuthorizedAction 构造（UUID 去连字符 + 会话
         * 前缀拼接单行表达式），抽具名函数后 nonce 语义可测试可追读。
         */
        internal fun newNonce(sessionId: String): String {
            val token =
                java.util.UUID
                    .randomUUID()
                    .toString()
                    .replace("-", "")
            return "$sessionId:$token"
        }
    }

    /**
     * AD-199（审计 2026-09-23 清单·A7 批）：原生核心桥的判空/开关判定收口
     * ——原 registerSession/renewSession/updateDocumentGeneration 三处
     * `REQUIRE_NATIVE_POLICY_CORE && bridge?.op(...) != true` 重复样板
     * （第四处 destroySession 亦各自判空）。抽本收口：未要求原生核心 →
     * 放行（true）；要求但桥接缺失/操作失败 → fail-closed（false）。
     */
    private fun nativeCoreGate(op: (NativePolicyCoreBridge) -> Boolean): Boolean =
        when {
            !BuildConfig.REQUIRE_NATIVE_POLICY_CORE -> true

            // 桥接缺失（null）或 op 失败（false）一律 fail-closed
            else -> nativePolicyCoreBridge?.let(op) == true
        }

    /** 注册由受控 WebView 创建的会话；未知会话上的所有副作用均应被拒绝。 */
    fun registerSession(
        sessionId: String,
        tabId: String,
        generation: Long = 0,
    ): Boolean {
        if (sessionId.isBlank() || tabId.isBlank() || generation < 0) return false
        return synchronized(authorizationLock) {
            if (sessions.containsKey(sessionId)) return@synchronized false
            // AD-199：原生核心会话操作经 nativeCoreGate 收口
            if (!nativeCoreGate { it.createSession(sessionId, tabId, generation, SESSION_TTL_SECONDS) }) {
                return@synchronized false
            }
            sessions[sessionId] = SessionContext(tabId, generation)
            true
        }
    }

    /**
     * 会话滑动续期（P0 修复——全量复审 2026-09-01）：导航前重调原生核心
     * createSession 对同 session_id 覆盖式重注册（重置 created_at，generation
     * 传当前值保持双端一致），消除「启动 2 分钟后所有导航被 session_expired
     * 拒绝」。仅在会话存在且标签匹配时续期；待审批确认期间不续期（由调用方
     * 保证），避免孤儿化 pending nonce。非原生模式会话本无时效——恒真。
     */
    fun renewSession(
        sessionId: String,
        tabId: String,
    ): Boolean {
        return synchronized(authorizationLock) {
            val session = sessions[sessionId] ?: return@synchronized false
            if (session.tabId != tabId) return@synchronized false
            // AD-199：与 registerSession 共用 nativeCoreGate 收口
            nativeCoreGate { it.createSession(sessionId, tabId, session.documentGeneration, SESSION_TTL_SECONDS) }
        }
    }

    /** 文档代际推进后立即同步；仅同标签严格单步推进，拒绝跳跃、回退和已销毁会话。 */
    fun updateDocumentGeneration(
        sessionId: String,
        tabId: String,
        generation: Long,
    ): Boolean {
        return synchronized(authorizationLock) {
            val session = sessions[sessionId] ?: return@synchronized false
            if (session.tabId != tabId || session.documentGeneration == Long.MAX_VALUE ||
                generation != session.documentGeneration + 1
            ) {
                return@synchronized false
            }
            // AD-199：与 registerSession 共用 nativeCoreGate 收口
            if (!nativeCoreGate { it.advanceDocumentGeneration(sessionId, tabId, generation) }) {
                return@synchronized false
            }
            session.documentGeneration = generation
            true
        }
    }

    /** 关闭标签时销毁会话并移除其已消费 nonce，避免状态残留。 */
    fun destroySession(sessionId: String) {
        synchronized(authorizationLock) {
            // AD-199：判空/开关判定经同一收口语义（要求原生核心才销毁；
            // 桥接缺失时无会话可销毁——不视为失败）。
            if (BuildConfig.REQUIRE_NATIVE_POLICY_CORE) {
                nativePolicyCoreBridge?.destroySession(sessionId)
            }
            sessions.remove(sessionId)
            consumedNonces.removeIf { nonce -> nonce.startsWith("$sessionId:") }
        }
    }

    /** 评估导航意图（ProposedAction → Decision——默认拒绝——fail-closed）。 */
    fun evaluateNavigation(
        sessionId: String,
        tabId: String,
        generation: Long,
        rawUrl: String,
        scope: String,
    ): Decision {
        val nativeGate = nativePolicyCoreGate.probe()
        if (!nativeGate.allowsPlatformBroker) {
            return deny(
                nativeGate.denialCode ?: "native_policy_core_unavailable",
                "已启用的原生策略核心不可用或不兼容",
            )
        }
        if (BuildConfig.REQUIRE_NATIVE_POLICY_CORE) {
            val bridge =
                nativePolicyCoreBridge ?: return deny(
                    "native_policy_core_bridge_unavailable",
                    "原生策略核心桥接不可用",
                )
            return bridge.evaluateNavigation(sessionId, tabId, generation, rawUrl, scope)
                ?: deny("native_policy_core_protocol", "原生策略核心响应无效或不可读取")
        }
        val session =
            sessions[sessionId]
                ?: return deny("session_not_found", "会话不存在或已销毁")
        if (session.tabId != tabId) return deny("tab_mismatch", "标签与会话不匹配")
        if (session.documentGeneration != generation) {
            return deny("generation_mismatch", "文档代际与会话状态不匹配")
        }
        val uri =
            OriginPolicy.tryParseExternal(rawUrl)
                ?: return deny("url_policy", "拒绝 URL: $rawUrl")
        val origin = canonicalOrigin(uri)
        val action =
            AuthorizedAction(
                sessionId = sessionId,
                tabId = tabId,
                documentGeneration = generation,
                origin = origin,
                method = "GET",
                canonicalParameters = canonicalPathAndQuery(uri),
                scope = scope,
                // AD-143（审计 2026-09-23 清单·A6 批）：Duration.parse("${N}s")
                // 字符串拼接换 Duration.seconds(N)——类型化构造免解析，
                // 值域由类型保证（parse 对异常输入的失败面不存在）。
                expiresAt = clock.now().plus(SESSION_TTL_SECONDS.seconds),
                nonce = newNonce(sessionId),
                policyVersion = policyVersion,
                explanation =
                    "allowed origin $origin — scheme ${uri.scheme}, host ${uri.host} — policy version $policyVersion",
            )
        return Decision.Allow(action)
    }

    /**
     * 登记待审批导航。原生核心模式由 Rust 维护 confirmation nonce；默认构建
     * 使用同一托管策略的直接评估路径，避免没有 native core 时所有导航都被
     * 误判为 native_confirmation_core_required。
     */
    fun requestNavigationConfirmation(
        sessionId: String,
        tabId: String,
        generation: Long,
        rawUrl: String,
        scope: String,
    ): Decision {
        val nativeGate = nativePolicyCoreGate.probe()
        return when {
            // 原生核心模式下所有 confirmation 统一由 Rust 托管（禁止反向顺延）。
            BuildConfig.REQUIRE_NATIVE_POLICY_CORE -> {
                if (!nativeGate.allowsPlatformBroker) {
                    deny(
                        nativeGate.denialCode ?: "native_policy_core_unavailable",
                        "已启用的原生策略核心不可用或不兼容",
                    )
                } else {
                    val bridge =
                        nativePolicyCoreBridge ?: return deny(
                            "native_policy_core_bridge_unavailable",
                            "原生策略核心桥接不可用",
                        )
                    bridge.requestNavigationConfirmation(sessionId, tabId, generation, rawUrl, scope)
                        ?: deny("native_policy_core_protocol", "原生策略核心确认请求无效或不可读取")
                }
            }

            // 默认构建无 native core：走托管 evaluate 的直接 Allow/Deny——
            // 此前无条件 Deny，导致默认产物每次导航都被拒绝（仅 CI 传
            // requireNativePolicyCore=true 掩盖了该问题）。
            else -> {
                evaluateNavigation(sessionId, tabId, generation, rawUrl, scope)
            }
        }
    }

    /** 仅按 Rust 核心登记的 nonce 显式批准，并由核心返回原始绑定授权。 */
    fun approveNavigationConfirmation(
        request: ApprovalRequest,
        rawUrl: String,
        scope: String,
    ): Decision {
        val nativeGate = nativePolicyCoreGate.probe()
        if (!nativeGate.allowsPlatformBroker) {
            return deny(
                nativeGate.denialCode ?: "native_policy_core_unavailable",
                "已启用的原生策略核心不可用或不兼容",
            )
        }
        if (!BuildConfig.REQUIRE_NATIVE_POLICY_CORE) {
            return deny("native_confirmation_core_required", "确认型导航必须由原生策略核心托管")
        }
        val bridge =
            nativePolicyCoreBridge ?: return deny(
                "native_policy_core_bridge_unavailable",
                "原生策略核心桥接不可用",
            )
        return bridge.approveNavigationConfirmation(request, rawUrl, scope)
            ?: deny("native_policy_core_protocol", "原生策略核心确认批准响应无效或不可读取")
    }

    /** 显式拒绝待审批导航；任何模式、门禁、桥接或 nonce 错误都返回 false。 */
    fun rejectNavigationConfirmation(request: ApprovalRequest): Boolean {
        if (!nativePolicyCoreGate.probe().allowsPlatformBroker ||
            !BuildConfig.REQUIRE_NATIVE_POLICY_CORE
        ) {
            return false
        }
        return nativePolicyCoreBridge?.rejectNavigationConfirmation(request) == true
    }

    /** 校验 AuthorizedAction 是否仍有效（会话/标签/代际/过期/策略版本——fail-closed）。 */
    fun isValid(
        action: AuthorizedAction?,
        currentGeneration: Long,
    ): Boolean {
        return synchronized(authorizationLock) {
            val presentAction = action ?: return@synchronized false
            val session = sessions[presentAction.sessionId] ?: return@synchronized false
            presentAction.policyVersion == policyVersion &&
                presentAction.tabId == session.tabId &&
                presentAction.documentGeneration == currentGeneration &&
                presentAction.documentGeneration == session.documentGeneration &&
                presentAction.expiresAt >
                clock.now()
        }
    }

    /** 在实际导航前校验上下文并消费 nonce，避免授权对象被跨标签或跨请求重放。 */
    fun consumeNavigation(
        action: AuthorizedAction?,
        sessionId: String,
        tabId: String,
        currentGeneration: Long,
        rawUrl: String,
        scope: String,
    ): Boolean {
        if (!nativePolicyCoreGate.probe().allowsPlatformBroker) return false
        if (BuildConfig.REQUIRE_NATIVE_POLICY_CORE) {
            val bridge = nativePolicyCoreBridge ?: return false
            val nonNullAction = action ?: return false
            // AD-200（审计 2026-09-23 清单·A7 批）：JNI 跨界调用移出锁外——
            // 原实现 authorizationLock 持锁期间跨 JNI 调 Rust 核心消费 nonce
            // （native 侧阻塞会拖住全部会话的授权校验，锁竞争面不可控）。
            // 现顺序：先跨 JNI 征询核心（无锁），再入锁做完整校验 + nonce
            // 登记。核心先消费的窗口里若 Kotlin 侧校验失败，整体仍拒绝
            // （fail-closed 方向不变；代价仅是极小概率多烧一个 nonce——
            // 烧 nonce 只收窄能力面，不放大）。
            val nativeAccepted = bridge.consumeNavigation(nonNullAction, rawUrl, scope)
            return synchronized(authorizationLock) {
                nativeAccepted &&
                    isValid(nonNullAction, currentGeneration) &&
                    nonNullAction.sessionId == sessionId &&
                    nonNullAction.tabId == tabId &&
                    trackConsumedNonce(nonNullAction.nonce)
            }
        }
        val uri = OriginPolicy.tryParseExternal(rawUrl) ?: return false
        return synchronized(authorizationLock) {
            if (!isValid(action, currentGeneration) || action == null) return@synchronized false
            if (action.sessionId != sessionId || action.tabId != tabId || action.scope != scope ||
                action.method != "GET" || action.origin != canonicalOrigin(uri) ||
                action.canonicalParameters != canonicalPathAndQuery(uri)
            ) {
                return@synchronized false
            }
            trackConsumedNonce(action.nonce)
        }
    }

    /**
     * 登记已消费 nonce（调用方须持 authorizationLock）；超上限 FIFO 逐出最旧。
     *
     * AD-179（审计 2026-09-23 清单·A7 批）：批量移除——原 while 循环每轮
     * 经迭代器只移除一个最旧条目（超限 N 条时 N 轮 full-pass 语义重复）；
     * 现一次计算超额数并单次迭代成批移除。
     */
    private fun trackConsumedNonce(nonce: String): Boolean {
        val added = consumedNonces.add(nonce)
        val excess = consumedNonces.size - MAX_CONSUMED_NONCES
        if (excess > 0) {
            val iterator = consumedNonces.iterator()
            repeat(excess) {
                if (!iterator.hasNext()) return@repeat
                iterator.next()
                iterator.remove()
            }
        }
        return added
    }

    private fun deny(
        code: String,
        detail: String,
    ): Decision.Deny =
        Decision.Deny(
            DenyReason(
                code,
                detail,
                explanation = "denied — $detail — policy version $policyVersion",
            ),
        )

    /**
     * AD-249（2026-09-26 审计）：internal 化供 JVM 单测直接断言——IPv6 host、
     * 非默认端口拼接与默认端口折叠此前仅经 evaluateNavigation 间接覆盖。
     */
    internal fun canonicalOrigin(uri: java.net.URI): String {
        // T2 配套（全面审计批次2 2026-09-04）：about:blank 为 opaque URI
        // （host=null）——直接归一会 NPE；固定返回原字面量。
        if (uri.scheme.equals("about", ignoreCase = true)) return "about:blank"
        val scheme = uri.scheme.lowercase()
        val port = uri.port
        // AD-180：默认端口查表（未知 scheme 无默认端口 → 端口一律显式展示）
        val defaultPort = DEFAULT_PORTS[scheme]
        val authority =
            if (port == -1 || defaultPort == port) {
                uri.host.lowercase()
            } else {
                "${uri.host.lowercase()}:$port"
            }
        return "$scheme://$authority"
    }

    private fun canonicalPathAndQuery(uri: java.net.URI): String {
        val path = uri.rawPath?.ifEmpty { "/" } ?: "/"
        return uri.rawQuery?.let { "$path?$it" } ?: path
    }

    private data class SessionContext(
        val tabId: String,
        @Volatile var documentGeneration: Long,
    )
}

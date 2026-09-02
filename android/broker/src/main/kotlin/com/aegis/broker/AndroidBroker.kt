package com.aegis.broker

/**
 * 阶段 D（蓝图 android/broker）：Android 侧 capability broker adapter——唯一允许
 * 产生本地副作用的边界（ADR-002）。验证来源/会话/标签代际/scope/参数/预算/批准/
 * nonce——没有 AuthorizedAction 不能导航/下载/导出/改策略。默认拒绝（fail-closed）。
 * 与 Windows BrowserPolicyBroker 同语义——同一 contracts（url-origin 向量）。
 */
class AndroidBroker(
    private val policyVersion: String = "1.0",
    private val nativePolicyCoreGate: NativePolicyCoreGate = DefaultNativePolicyCoreGate,
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
            if (BuildConfig.REQUIRE_NATIVE_POLICY_CORE && nativePolicyCoreBridge?.createSession(
                    sessionId,
                    tabId,
                    generation,
                    SESSION_TTL_SECONDS,
                ) != true
            ) {
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
            if (BuildConfig.REQUIRE_NATIVE_POLICY_CORE && nativePolicyCoreBridge?.createSession(
                    sessionId,
                    tabId,
                    session.documentGeneration,
                    SESSION_TTL_SECONDS,
                ) != true
            ) {
                return@synchronized false
            }
            true
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
            if (BuildConfig.REQUIRE_NATIVE_POLICY_CORE && nativePolicyCoreBridge?.advanceDocumentGeneration(
                    sessionId,
                    tabId,
                    generation,
                ) != true
            ) {
                return@synchronized false
            }
            session.documentGeneration = generation
            true
        }
    }

    /** 关闭标签时销毁会话并移除其已消费 nonce，避免状态残留。 */
    fun destroySession(sessionId: String) {
        synchronized(authorizationLock) {
            if (BuildConfig.REQUIRE_NATIVE_POLICY_CORE && nativePolicyCoreBridge != null) {
                nativePolicyCoreBridge.destroySession(sessionId)
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
                expiresAt =
                    kotlinx.datetime.Clock.System
                        .now()
                        .plus(kotlin.time.Duration.parse("${SESSION_TTL_SECONDS}s")),
                nonce = "$sessionId:${java.util.UUID.randomUUID().toString().replace("-", "")}",
                policyVersion = policyVersion,
                explanation = "allowed origin $origin — scheme ${uri.scheme}, host ${uri.host} — policy version $policyVersion",
            )
        return Decision.Allow(action)
    }

    /**
     * 登记由 Rust 核心托管的待审批导航。默认托管路径不得自行重建确认授权，
     * 因此非原生模式、门禁失败或桥接故障均返回拒绝。
     */
    fun requestNavigationConfirmation(
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
        if (!BuildConfig.REQUIRE_NATIVE_POLICY_CORE) {
            return deny("native_confirmation_core_required", "确认型导航必须由原生策略核心托管")
        }
        val bridge =
            nativePolicyCoreBridge ?: return deny(
                "native_policy_core_bridge_unavailable",
                "原生策略核心桥接不可用",
            )
        return bridge.requestNavigationConfirmation(sessionId, tabId, generation, rawUrl, scope)
            ?: deny("native_policy_core_protocol", "原生策略核心确认请求无效或不可读取")
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
                kotlinx.datetime.Clock.System
                    .now()
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
            return synchronized(authorizationLock) {
                if (!isValid(action, currentGeneration) || action == null ||
                    action.sessionId != sessionId || action.tabId != tabId
                ) {
                    return@synchronized false
                }
                bridge.consumeNavigation(action, rawUrl, scope) && trackConsumedNonce(action.nonce)
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

    /** 登记已消费 nonce（调用方须持 authorizationLock）；超上限 FIFO 逐出最旧。 */
    private fun trackConsumedNonce(nonce: String): Boolean {
        val added = consumedNonces.add(nonce)
        while (consumedNonces.size > MAX_CONSUMED_NONCES) {
            val iterator = consumedNonces.iterator()
            if (!iterator.hasNext()) break
            iterator.next()
            iterator.remove()
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

    private fun canonicalOrigin(uri: java.net.URI): String {
        val scheme = uri.scheme.lowercase()
        val port = uri.port
        val defaultPort = if (scheme == "https") 443 else 80
        val authority = if (port == -1 || port == defaultPort) uri.host.lowercase() else "${uri.host.lowercase()}:$port"
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

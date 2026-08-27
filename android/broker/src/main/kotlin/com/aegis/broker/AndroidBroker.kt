package com.aegis.broker

/**
 * 阶段 D（蓝图 android/broker）：Android 侧 capability broker adapter——唯一允许
 * 产生本地副作用的边界（ADR-002）。验证来源/会话/标签代际/scope/参数/预算/批准/
 * nonce——没有 AuthorizedAction 不能导航/下载/导出/改策略。默认拒绝（fail-closed）。
 * 与 Windows BrowserPolicyBroker 同语义——同一 contracts（url-origin 向量）。
 *
 * Mode（照搬 warden evaluate 模式）：
 * - FirstMatch：顺序遍历规则，第一个匹配生效（默认）
 * - DenyOverrides：收集所有匹配规则，deny > ask > allow 最严格优先（XACML/Cedar 语义）
 */
class AndroidBroker(
    private val policyVersion: String = "1.0",
    private val mode: BrokerMode = BrokerMode.FirstMatch,
) {
    private val consumedNonces = java.util.concurrent.ConcurrentHashMap.newKeySet<String>()
    private val sessions = java.util.concurrent.ConcurrentHashMap<String, SessionContext>()
    private val authorizationLock = Any()

    /** 注册由受控 WebView 创建的会话；未知会话上的所有副作用均应被拒绝。 */
    fun registerSession(sessionId: String, tabId: String, generation: Long = 0): Boolean {
        if (sessionId.isBlank() || tabId.isBlank() || generation < 0) return false
        return synchronized(authorizationLock) {
            sessions.putIfAbsent(sessionId, SessionContext(tabId, generation)) == null
        }
    }

    /** 文档代际推进后立即同步；仅同标签严格单步推进，拒绝跳跃、回退和已销毁会话。 */
    fun updateDocumentGeneration(sessionId: String, tabId: String, generation: Long): Boolean {
        return synchronized(authorizationLock) {
            val session = sessions[sessionId] ?: return@synchronized false
            if (session.tabId != tabId || session.documentGeneration == Long.MAX_VALUE ||
                generation != session.documentGeneration + 1) return@synchronized false
            session.documentGeneration = generation
            true
        }
    }

    /** 关闭标签时销毁会话并移除其已消费 nonce，避免状态残留。 */
    fun destroySession(sessionId: String) {
        synchronized(authorizationLock) {
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
        val session = sessions[sessionId]
            ?: return deny("session_not_found", "会话不存在或已销毁")
        if (session.tabId != tabId) return deny("tab_mismatch", "标签与会话不匹配")
        if (session.documentGeneration != generation) {
            return deny("generation_mismatch", "文档代际与会话状态不匹配")
        }
        val uri = OriginPolicy.tryParseExternal(rawUrl)
            ?: return deny("url_policy", "拒绝 URL: $rawUrl")
        val origin = canonicalOrigin(uri)
        val action = AuthorizedAction(
            sessionId = sessionId, tabId = tabId, documentGeneration = generation,
            origin = origin, method = "GET", canonicalParameters = canonicalPathAndQuery(uri),
            scope = scope, expiresAt = kotlinx.datetime.Clock.System.now()
                .plus(kotlin.time.Duration.parse("120s")),
            nonce = "$sessionId:${java.util.UUID.randomUUID().toString().replace("-", "")}",
            policyVersion = policyVersion,
            explanation = "allowed origin $origin — scheme ${uri.scheme}, host ${uri.host} — policy version $policyVersion",
        )
        return Decision.Allow(action)
    }

    /** 校验 AuthorizedAction 是否仍有效（会话/标签/代际/过期/策略版本——fail-closed）。 */
    fun isValid(action: AuthorizedAction?, currentGeneration: Long): Boolean {
        return synchronized(authorizationLock) {
            val presentAction = action ?: return@synchronized false
            val session = sessions[presentAction.sessionId] ?: return@synchronized false
            presentAction.policyVersion == policyVersion &&
                presentAction.tabId == session.tabId &&
                presentAction.documentGeneration == currentGeneration &&
                presentAction.documentGeneration == session.documentGeneration &&
                presentAction.expiresAt > kotlinx.datetime.Clock.System.now()
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
        val uri = OriginPolicy.tryParseExternal(rawUrl) ?: return false
        return synchronized(authorizationLock) {
            if (!isValid(action, currentGeneration) || action == null) return@synchronized false
            if (action.sessionId != sessionId || action.tabId != tabId || action.scope != scope ||
                action.method != "GET" || action.origin != canonicalOrigin(uri) ||
                action.canonicalParameters != canonicalPathAndQuery(uri)) {
                return@synchronized false
            }
            consumedNonces.add(action.nonce)
        }
    }

    private fun deny(code: String, detail: String): Decision.Deny =
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

/** 评估模式（照搬 warden Mode——FirstMatch/DenyOverrides）。 */
enum class BrokerMode {
    /** 顺序遍历规则，第一个匹配生效（默认）。 */
    FirstMatch,
    /** 收集所有匹配规则，deny > ask > allow 最严格优先（XACML/Cedar 语义）。 */
    DenyOverrides,
}

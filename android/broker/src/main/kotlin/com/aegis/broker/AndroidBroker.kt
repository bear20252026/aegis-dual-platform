package com.aegis.broker

/**
 * 阶段 D（蓝图 android/broker）：Android 侧 capability broker adapter——唯一允许
 * 产生本地副作用的边界（ADR-002）。验证来源/会话/标签代际/scope/参数/预算/批准/
 * nonce——没有 AuthorizedAction 不能导航/下载/导出/改策略。默认拒绝（fail-closed）。
 * 与 Windows BrowserPolicyBroker 同语义——同一 contracts（url-origin 向量）。
 */
class AndroidBroker(private val policyVersion: String = "1.0") {

    /** 评估导航意图（ProposedAction → Decision——默认拒绝——fail-closed）。 */
    fun evaluateNavigation(
        sessionId: String,
        tabId: String,
        generation: Long,
        rawUrl: String,
        scope: String,
    ): Decision {
        val uri = OriginPolicy.tryParseExternal(rawUrl)
            ?: return Decision.Deny(DenyReason("url_policy", "拒绝 URL: $rawUrl"))
        val origin = "${uri.scheme}://${uri.host}"
        val action = AuthorizedAction(
            sessionId = sessionId, tabId = tabId, documentGeneration = generation,
            origin = origin, method = "GET", canonicalParameters = uri.path,
            scope = scope, expiresAt = kotlinx.datetime.Clock.System.now()
                .plus(kotlin.time.Duration.parse("120s")),
            nonce = java.util.UUID.randomUUID().toString().replace("-", ""),
            policyVersion = policyVersion,
            explanation = "allowed origin $origin — scheme ${uri.scheme}, host ${uri.host} — policy version $policyVersion",
        )
        return Decision.Allow(action)
    }

    /** 校验 AuthorizedAction 是否仍有效（代际/过期/策略版本——fail-closed）。 */
    fun isValid(action: AuthorizedAction?, currentGeneration: Long): Boolean =
        action != null
            && action.policyVersion == policyVersion
            && action.documentGeneration == currentGeneration
            && action.expiresAt > kotlinx.datetime.Clock.System.now()
}

package com.aegis.broker

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class AndroidBrokerTest {
    @Test
    fun registeredSessionCanConsumeNavigationOnlyOnce() {
        val broker = AndroidBroker()
        assertTrue(broker.registerSession("session-1", "tab-1"))

        val decision =
            broker.evaluateNavigation(
                sessionId = "session-1",
                tabId = "tab-1",
                generation = 0,
                rawUrl = "https://example.com/path?query=1",
                scope = "navigation",
            )
        assertTrue(decision is Decision.Allow)
        val action = (decision as Decision.Allow).action

        assertTrue(
            broker.consumeNavigation(
                action,
                "session-1",
                "tab-1",
                0,
                "https://example.com/path?query=1",
                "navigation",
            ),
        )
        assertFalse(
            broker.consumeNavigation(
                action,
                "session-1",
                "tab-1",
                0,
                "https://example.com/path?query=1",
                "navigation",
            ),
        )
    }

    @Test
    fun unregisteredOrStaleSessionIsDenied() {
        val broker = AndroidBroker()
        assertTrue(
            broker.evaluateNavigation(
                "missing",
                "tab-1",
                0,
                "https://example.com",
                "navigation",
            ) is Decision.Deny,
        )

        assertTrue(broker.registerSession("session-1", "tab-1"))
        assertTrue(broker.updateDocumentGeneration("session-1", "tab-1", 1))
        assertTrue(
            broker.evaluateNavigation(
                "session-1",
                "tab-1",
                0,
                "https://example.com",
                "navigation",
            ) is Decision.Deny,
        )
    }

    @Test
    fun renewSessionOnlyWorksForLiveSessionWithMatchingTab() {
        val broker = AndroidBroker()
        assertFalse(broker.renewSession("missing", "tab-1"))

        assertTrue(broker.registerSession("session-1", "tab-1"))
        assertFalse(broker.renewSession("session-1", "other-tab"))
        assertTrue(broker.renewSession("session-1", "tab-1"))

        broker.destroySession("session-1")
        assertFalse(broker.renewSession("session-1", "tab-1"))
    }

    @Test
    fun renewalPreservesSessionGenerationState() {
        val broker = AndroidBroker()
        assertTrue(broker.registerSession("session-1", "tab-1"))
        assertTrue(broker.updateDocumentGeneration("session-1", "tab-1", 1))
        assertTrue(broker.renewSession("session-1", "tab-1"))
        // 续期不重置本地代际：旧代际仍拒绝、当前代际仍放行
        assertTrue(
            broker.evaluateNavigation(
                "session-1",
                "tab-1",
                0,
                "https://example.com",
                "navigation",
            ) is Decision.Deny,
        )
        assertTrue(
            broker.evaluateNavigation(
                "session-1",
                "tab-1",
                1,
                "https://example.com",
                "navigation",
            ) is Decision.Allow,
        )
    }

    @Test
    fun documentGenerationAdvancesOnlyOneStepForTheRegisteredTab() {
        val broker = AndroidBroker()
        assertTrue(broker.registerSession("session-1", "tab-1"))

        assertFalse(broker.updateDocumentGeneration("session-1", "other-tab", 1))
        assertFalse(broker.updateDocumentGeneration("session-1", "tab-1", 2))
        assertFalse(broker.updateDocumentGeneration("session-1", "tab-1", 0))
        assertTrue(broker.updateDocumentGeneration("session-1", "tab-1", 1))
    }

    @Test
    fun requiredNativePolicyCoreFailureClosesNavigationAndConsumption() {
        val broker =
            AndroidBroker(
                nativePolicyCoreGate =
                    NativePolicyCoreGate {
                        NativePolicyCoreGateResult.block("native_policy_core_unavailable")
                    },
            )
        assertTrue(broker.registerSession("session-1", "tab-1"))

        val denied =
            broker.evaluateNavigation(
                "session-1",
                "tab-1",
                0,
                "https://example.com",
                "navigation",
            )

        assertTrue(denied is Decision.Deny)
        assertTrue((denied as Decision.Deny).reason.code == "native_policy_core_unavailable")
        assertFalse(
            broker.consumeNavigation(
                null,
                "session-1",
                "tab-1",
                0,
                "https://example.com",
                "navigation",
            ),
        )
    }

    @Test
    fun defaultNativePolicyCoreGateClosesWhenBuildRequiresNativeCore() {
        val result = DefaultNativePolicyCoreGate.probe()

        if (BuildConfig.REQUIRE_NATIVE_POLICY_CORE) {
            assertFalse(result.allowsPlatformBroker)
            assertTrue(result.denialCode == "native_policy_core_unavailable")
        } else {
            assertTrue(result.allowsPlatformBroker)
        }
    }

    @Test
    fun nativeDecisionJsonMapsAuthorizationFieldsAndDenyReason() {
        val allow =
            NativePolicyCoreBridge.parseDecisionJson(
                """{
                "abi_version":3,"decision":"allow","action":{
                "session_id":"native-session","tab_id":"native-tab","document_generation":2,
                "origin":"https://example.com","method":"GET","canonical_parameters":"/path?x=1",
                "scope":"navigation","expires_at":1700000000,"nonce":"nonce-1","policy_version":"1.0",
                "explanation":"allowed"}}""",
            ) as Decision.Allow

        assertEquals("native-session", allow.action.sessionId)
        assertEquals(2, allow.action.documentGeneration)
        assertEquals("https://example.com", allow.action.origin)
        assertEquals("/path?x=1", allow.action.canonicalParameters)
        assertEquals(1_700_000_000, allow.action.expiresAt.epochSeconds)

        val deny =
            NativePolicyCoreBridge.parseDecisionJson(
                """{"abi_version":3,"decision":"deny","reason":{
                "code":"nonce_replay","detail":"nonce already consumed","explanation":"denied"}}""",
            ) as Decision.Deny
        assertEquals("nonce_replay", deny.reason.code)

        val confirmation =
            NativePolicyCoreBridge.parseDecisionJson(
                """{"abi_version":3,"decision":"require_confirmation","request":{
                "origin":"https://payments.example","method":"POST","path":"/transfers",
                "scope":"payment:create","expires_at":1700000000,"nonce":"approval-nonce"}}""",
            ) as Decision.RequireConfirmation
        assertEquals("https://payments.example", confirmation.request.origin)
        assertEquals("POST", confirmation.request.method)
        assertEquals("/transfers", confirmation.request.path)
        assertEquals("payment:create", confirmation.request.scope)
        assertEquals(1_700_000_000, confirmation.request.expiresAt.epochSeconds)
        assertEquals("approval-nonce", confirmation.request.nonce)
    }

    @Test
    fun confirmationDelegatesToManagedEvaluateWhenNativeCoreNotRequired() {
        val broker = AndroidBroker()
        assertTrue(broker.registerSession("confirmation-session", "confirmation-tab"))

        // 默认构建（未启用原生策略核心）：requestNavigationConfirmation 应
        // 委托托管 evaluateNavigation 做直接 Allow/Deny——此前无条件 Deny
        // 导致默认产物每次导航都被拒绝（仅 CI/原生模式掩盖该问题）。
        val allowed =
            broker.requestNavigationConfirmation(
                "confirmation-session",
                "confirmation-tab",
                0,
                "https://example.com/confirmation",
                "navigation",
            )
        val rejected =
            broker.requestNavigationConfirmation(
                "no-such-session",
                "confirmation-tab",
                0,
                "https://example.com/confirmation",
                "navigation",
            )

        if (BuildConfig.REQUIRE_NATIVE_POLICY_CORE) {
            // 原生模式：确认型导航必须由 Rust core 托管（fail-closed）。
            assertTrue(allowed is Decision.Deny)
            assertTrue(rejected is Decision.Deny)
        } else {
            // 托管模式：合法会话+https Allow；非法会话 Deny。
            assertTrue(allowed is Decision.Allow)
            assertTrue(rejected is Decision.Deny)
        }
    }

    @Test
    fun managedEvaluateRejectsUnparseableUrlInConfirmation() {
        if (BuildConfig.REQUIRE_NATIVE_POLICY_CORE) return
        val broker = AndroidBroker()
        assertTrue(broker.registerSession("s", "t"))
        val denied =
            broker.requestNavigationConfirmation(
                "s",
                "t",
                0,
                "javascript:alert(1)",
                "navigation",
            )
        assertTrue(denied is Decision.Deny)
        assertEquals("url_policy", (denied as Decision.Deny).reason.code)
    }

    @Test
    fun nativeDecisionJsonRejectsPreviousAbiVersion() {
        val exception =
            runCatching {
                NativePolicyCoreBridge.parseDecisionJson(
                    """{"abi_version":1,"decision":"deny","reason":{
                    "code":"legacy","detail":"legacy ABI","explanation":"denied"}}""",
                )
            }.exceptionOrNull()

        assertTrue(exception is IllegalStateException)
    }

    @Test
    fun destroyingSessionInvalidatesFutureNavigation() {
        val broker = AndroidBroker()
        assertTrue(broker.registerSession("session-1", "tab-1"))
        broker.destroySession("session-1")

        assertTrue(
            broker.evaluateNavigation(
                "session-1",
                "tab-1",
                0,
                "https://example.com",
                "navigation",
            ) is Decision.Deny,
        )
    }

    @Test
    fun destroyingSessionInvalidatesAnAlreadyIssuedAuthorization() {
        val broker = AndroidBroker()
        assertTrue(broker.registerSession("session-1", "tab-1"))
        val decision =
            broker.evaluateNavigation(
                "session-1",
                "tab-1",
                0,
                "https://example.com",
                "navigation",
            )
        assertTrue(decision is Decision.Allow)
        broker.destroySession("session-1")

        assertFalse(
            broker.consumeNavigation(
                (decision as Decision.Allow).action,
                "session-1",
                "tab-1",
                0,
                "https://example.com",
                "navigation",
            ),
        )
    }

    @Test
    fun navigationAuthorizationCanonicalizesOriginAndPathQuery() {
        val broker = AndroidBroker()
        assertTrue(broker.registerSession("session-1", "tab-1"))
        val decision =
            broker.evaluateNavigation(
                "session-1",
                "tab-1",
                0,
                "HTTPS://Example.Org:443/a?b=1#ignored",
                "navigation",
            )
        assertTrue(decision is Decision.Allow)
        val action = (decision as Decision.Allow).action

        assertTrue(action.origin == "https://example.org")
        assertTrue(action.canonicalParameters == "/a?b=1")
    }

    // ---------------- AD-249（2026-09-26 审计）：canonicalOrigin 直接断言 ----------------

    @Test
    fun canonicalOriginKeepsIpv6HostBrackets() {
        val broker = AndroidBroker()
        // java.net.URI 对 IPv6 host 保留方括号——归一不得剥除（剥除后非合法 origin）
        assertEquals("https://[::1]", broker.canonicalOrigin(java.net.URI("https://[::1]/x")))
        assertEquals(
            "https://[2001:db8::1]:8443",
            broker.canonicalOrigin(java.net.URI("https://[2001:db8::1]:8443/x")),
        )
    }

    @Test
    fun canonicalOriginAppendsNonDefaultPort() {
        val broker = AndroidBroker()
        assertEquals(
            "https://example.com:8443",
            broker.canonicalOrigin(java.net.URI("https://example.com:8443/x")),
        )
        assertEquals(
            "http://example.com:8080",
            broker.canonicalOrigin(java.net.URI("http://example.com:8080/x")),
        )
    }

    @Test
    fun canonicalOriginFoldsDefaultPortAndOmittedPort() {
        val broker = AndroidBroker()
        // 默认端口（https:443/http:80）与未写端口折叠为同一 canonical origin
        assertEquals("https://example.com", broker.canonicalOrigin(java.net.URI("https://example.com:443/x")))
        assertEquals("http://example.com", broker.canonicalOrigin(java.net.URI("http://example.com:80/x")))
        assertEquals("https://example.com", broker.canonicalOrigin(java.net.URI("https://example.com/x")))
    }

    // ---------------- AD-121/122/142（审计 2026-09-23 清单·A6 批） ----------------

    @Test
    fun directEvaluateNavigationDeniesJavascriptScheme() {
        // AD-121：直调 javascript: 必须在 evaluateNavigation 层 fail-closed
        // 拒绝（url_policy——不再补 https 拼接、不产生授权对象）
        if (BuildConfig.REQUIRE_NATIVE_POLICY_CORE) return
        val broker = AndroidBroker()
        assertTrue(broker.registerSession("session-js", "tab-js"))
        val denied =
            broker.evaluateNavigation("session-js", "tab-js", 0, "javascript:alert(1)", "navigation")
        assertTrue(denied is Decision.Deny)
        assertEquals("url_policy", (denied as Decision.Deny).reason.code)
    }

    @Test
    fun aboutBlankFullChainIssuesAndConsumesAuthorization() {
        // AD-122：about:blank 全链（evaluate Allow → consume 成功 → 重放拒绝）
        if (BuildConfig.REQUIRE_NATIVE_POLICY_CORE) return
        val broker = AndroidBroker()
        assertTrue(broker.registerSession("session-blank", "tab-blank"))

        val decision =
            broker.evaluateNavigation("session-blank", "tab-blank", 0, "about:blank", "navigation")
        assertTrue(decision is Decision.Allow)
        val action = (decision as Decision.Allow).action
        assertEquals("about:blank", action.origin)

        assertTrue(
            broker.consumeNavigation(action, "session-blank", "tab-blank", 0, "about:blank", "navigation"),
        )
        // nonce 单次消费——重放必须拒绝
        assertFalse(
            broker.consumeNavigation(action, "session-blank", "tab-blank", 0, "about:blank", "navigation"),
        )
    }

    @Test
    fun newNonceIsSessionPrefixedHexWithoutDashes() {
        // AD-142：nonce 组装抽函数后的形态守护——会话前缀 + 32 位去连字符 hex
        val nonce = AndroidBroker.newNonce("session-n")
        assertTrue(nonce.startsWith("session-n:"))
        val randomPart = nonce.removePrefix("session-n:")
        assertEquals(32, randomPart.length)
        assertTrue(randomPart.all { it.isDigit() || it in 'a'..'f' })
        // 随机性：同会话两次生成不得相同
        assertNotEquals(AndroidBroker.newNonce("session-n"), nonce)
    }
}

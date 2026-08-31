package com.aegis.broker

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
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
    fun confirmationCoordinationFailsClosedWithoutNativeCore() {
        val broker = AndroidBroker()
        assertTrue(broker.registerSession("confirmation-session", "confirmation-tab"))

        val pending =
            broker.requestNavigationConfirmation(
                "confirmation-session",
                "confirmation-tab",
                0,
                "https://example.com/confirmation",
                "navigation",
            )

        assertTrue(pending is Decision.Deny)
        assertEquals("native_confirmation_core_required", (pending as Decision.Deny).reason.code)
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
}

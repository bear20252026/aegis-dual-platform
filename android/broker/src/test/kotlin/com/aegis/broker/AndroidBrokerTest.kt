package com.aegis.broker

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class AndroidBrokerTest {
    @Test
    fun registeredSessionCanConsumeNavigationOnlyOnce() {
        val broker = AndroidBroker()
        assertTrue(broker.registerSession("session-1", "tab-1"))

        val decision = broker.evaluateNavigation(
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
        val broker = AndroidBroker(
            nativePolicyCoreGate = NativePolicyCoreGate {
                NativePolicyCoreGateResult.block("native_policy_core_unavailable")
            },
        )
        assertTrue(broker.registerSession("session-1", "tab-1"))

        val denied = broker.evaluateNavigation(
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
        val decision = broker.evaluateNavigation(
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
        val decision = broker.evaluateNavigation(
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

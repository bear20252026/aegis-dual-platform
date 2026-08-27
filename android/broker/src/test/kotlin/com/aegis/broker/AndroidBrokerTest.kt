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
}

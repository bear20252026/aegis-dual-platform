package com.aegis.broker

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * A-2 对齐守卫（架构审计 2026-08-31）：手写模型 AuthorizedAction 与
 * 契约生成物 ActionContract 的字段面必须 1:1 对应（camelCase ↔ snake_case），
 * 漂移即失败——杜绝「schema 变更只靠注释维持一致性」的平行双轨。
 *
 * 语义约定（允许的有意差异，逐条豁免）：
 * - expiresAt（Instant）↔ expires_at（String）——生成物保持 JSON 原始形态；
 * - explanation——审计扩展字段，仅存在于手写模型（生成器尚未覆盖）。
 */
class ContractAlignmentTest {
    private val exemptions = setOf("explanation")

    /** Java 反射取字段名（broker 不引 kotlin-reflect——保持依赖最小）。 */
    private fun fieldNames(c: Class<*>): Set<String> = c.declaredFields.map { it.name }.toSet()

    private fun String.toSnakeCase(): String =
        replace(Regex("([a-z0-9])([A-Z])")) { m ->
            m.groupValues[1] + "_" + m.groupValues[2].lowercase()
        }.lowercase()

    private fun String.toCamelCase(): String =
        split('_')
            .mapIndexed { i, part ->
                if (i == 0) part else part.replaceFirstChar { it.uppercase() }
            }.joinToString("")

    @Test
    fun `authorized action mirrors action contract field-for-field`() {
        val actionNames = fieldNames(AuthorizedAction::class.java) - exemptions
        val contractNames = fieldNames(com.aegis.contracts.generated.ActionContract::class.java)
        assertEquals(
            "AuthorizedAction 与 ActionContract 字段集漂移——同步 contracts/action.schema.json 与生成器",
            contractNames,
            actionNames.map { it.toSnakeCase() }.toSet(),
        )
    }

    @Test
    fun `explanation is the only documented extra field`() {
        val extras =
            fieldNames(AuthorizedAction::class.java) -
                fieldNames(com.aegis.contracts.generated.ActionContract::class.java)
                    .map { it.toCamelCase() }
                    .toSet()
        assertEquals(setOf("explanation"), extras)
    }

    @Test
    fun `contract module is on the compile classpath of broker tests`() {
        // 防退化：本测试本身依赖 :contracts——若依赖被移除，编译即失败；
        // 此断言显式声明该意图，使对齐守卫的存在可被发现。
        assertTrue(
            com.aegis.contracts.generated.ActionContract::class
                .qualifiedName!!
                .startsWith("com.aegis.contracts.generated"),
        )
    }

    // ---------------- AD-210（审计 2026-09-23 清单·A7 批）：双形态转换单源 ----------------

    /** 样本契约生成物（字段面取 ActionContract 生成器现状）。 */
    private fun originalSampleContract(): com.aegis.contracts.generated.ActionContract =
        com.aegis.contracts.generated.ActionContract(
            session_id = "s",
            tab_id = "t",
            document_generation = 0L,
            origin = "https://example.com",
            method = "GET",
            canonical_parameters = "/",
            scope = "navigation",
            expires_at = "2026-09-27T00:00:00Z",
            nonce = "n",
            policy_version = "1.0",
        )

    @Test
    fun `authorized action converts to contract and back losslessly`() {
        // 转换扩展（ActionContractConversions.kt 单源）必须无损往返：
        // expires_at 经 ISO-8601 字符串对偶（Instant.toString/parse），
        // explanation 为契约外扩展字段——正向丢弃、反向以参数补回
        val original =
            AuthorizedAction(
                sessionId = "session-x",
                tabId = "tab-x",
                documentGeneration = 7L,
                origin = "https://example.com",
                method = "GET",
                canonicalParameters = "/p?x=1",
                scope = "navigation",
                expiresAt = kotlinx.datetime.Instant.fromEpochSeconds(1_700_000_123),
                nonce = "session-x:abc123",
                policyVersion = "1.0",
                explanation = "audit trail",
            )
        val contract = original.toActionContract()
        assertEquals(original.expiresAt.toString(), contract.expires_at)
        val roundTrip = contract.toAuthorizedAction(explanation = original.explanation)
        assertEquals(original, roundTrip)
    }

    @Test
    fun `contract to authorized action rejects non iso instant strings`() {
        // 转换单源承担编码契约守护：非 ISO-8601 的 expires_at 必须显式失败
        // （fail-fast 优于静默产生畸形 Instant 的下游语义漂移）
        val broken = originalSampleContract().copy(expires_at = "not-a-timestamp")
        val exception = runCatching { broken.toAuthorizedAction() }.exceptionOrNull()
        assertTrue(exception is IllegalArgumentException)
    }
}

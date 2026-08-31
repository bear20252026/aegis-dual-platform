package com.aegis.broker

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import kotlin.reflect.KClass
import kotlin.reflect.full.memberProperties

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

    private fun KClass<*>.propertyNames() = memberProperties.map { it.name }.toSet()

    private fun String.toSnakeCase(): String =
        replace(Regex("([a-z0-9])([A-Z])")) { m ->
            m.groupValues[1] + "_" + m.groupValues[2].lowercase()
        }.lowercase()

    @Test
    fun `authorized action mirrors action contract field-for-field`() {
        val actionNames = AuthorizedAction::class.propertyNames()
        val contractNames = com.aegis.contracts.generated.ActionContract::class.propertyNames()

        val actionInSnake = actionNames - exemptions
        assertEquals(
            "AuthorizedAction 与 ActionContract 字段集漂移——同步 contracts/action.schema.json 与生成器",
            contractNames,
            actionInSnake.map { it.toSnakeCase() }.toSet(),
        )
    }

    @Test
    fun `explanation is the only documented extra field`() {
        val extras =
            AuthorizedAction::class.propertyNames() -
                com.aegis.contracts.generated.ActionContract::class
                    .propertyNames()
                    .map { it.toCamelCase() }
                    .toSet()
        assertEquals(setOf("explanation"), extras)
    }

    private fun String.toCamelCase(): String =
        split('_')
            .mapIndexed { i, part ->
                if (i == 0) part else part.replaceFirstChar { it.uppercase() }
            }.joinToString("")

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
}

package com.aegis.broker

import com.aegis.contracts.generated.ActionContract
import kotlinx.datetime.Instant

// AD-210（审计 2026-09-23 清单·A7 批）：契约生成物与手写模型的双形态转换
// 扩展单源——ActionContract.expires_at 为 String（JSON 原始形态——生成器
// 不引时间类型），AuthorizedAction.expiresAt 为 Instant：此前两形态的字段
// 互转靠 ContractAlignmentTest 的字段名反射对齐 + 人工注释维持，无统一
// 转换点。收敛为本文件的两个扩展（broker 测试源集——ActionContract 仅在
// 测试类路径可用，主源集引入 :contracts 会造成发布耦合），ContractAlignmentTest
// 消费；若未来生产链路需要互转（如契约回放），随消费点一并上移主源集。
//
// Instant 编码契约：ISO-8601 扩展格式（Instant.toString/parse 对偶）——
// 与 contracts action.schema.json 的 date-time 语义一致。

/** 手写模型 → 契约生成物（explanation 为手写模型独有字段——契约侧无槽位）。 */
internal fun AuthorizedAction.toActionContract(): ActionContract =
    ActionContract(
        session_id = sessionId,
        tab_id = tabId,
        document_generation = documentGeneration,
        origin = origin,
        method = method,
        canonical_parameters = canonicalParameters,
        scope = scope,
        expires_at = expiresAt.toString(),
        nonce = nonce,
        policy_version = policyVersion,
    )

/** 契约生成物 → 手写模型（[explanation] 为契约外审计扩展，缺省空串）。 */
internal fun ActionContract.toAuthorizedAction(explanation: String = ""): AuthorizedAction =
    AuthorizedAction(
        sessionId = session_id,
        tabId = tab_id,
        documentGeneration = document_generation,
        origin = origin,
        method = method,
        canonicalParameters = canonical_parameters,
        scope = scope,
        expiresAt = Instant.parse(expires_at),
        nonce = nonce,
        policyVersion = policy_version,
        explanation = explanation,
    )

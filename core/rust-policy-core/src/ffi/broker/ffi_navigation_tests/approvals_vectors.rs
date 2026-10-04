use super::super::*;

use super::common::*;

// —— RS-308（2026-10-02 审计）：approvals-replay-and-expiry 向量消费 ——

/// 向量 expires_at（ISO8601 Z 形态）→ UNIX epoch 秒。手工解析
/// （civil 天数算法——Howard Hinnant days_from_civil），不引 chrono。
fn iso8601_to_epoch(s: &str) -> Option<u64> {
    let b = s.as_bytes();
    if b.len() != 20 || b[4] != b'-' || b[7] != b'-' || b[10] != b'T' || b[19] != b'Z' {
        return None;
    }
    let num = |r: std::ops::Range<usize>| s.get(r)?.parse::<i64>().ok();
    let (y, m, d) = (num(0..4)?, num(5..7)?, num(8..10)?);
    let (hh, mm, ss) = (num(11..13)?, num(14..16)?, num(17..19)?);
    if !(1..=12).contains(&m) || !(1..=31).contains(&d) {
        return None;
    }
    let y = if m <= 2 { y - 1 } else { y };
    let era = if y >= 0 { y } else { y - 399 } / 400;
    let yoe = y - era * 400;
    let mp = (m + 9) % 12;
    let doy = (153 * mp + 2) / 5 + d - 1;
    let doe = yoe * 365 + yoe / 4 - yoe / 100 + doy;
    let days = era * 146_097 + doe - 719_468;
    Some((days * 86_400 + hh * 3_600 + mm * 60 + ss) as u64)
}

#[test]
fn approvals_replay_and_expiry_vectors_consumed() {
    // RS-308：approvals-replay-and-expiry.json 五条向量此前零 Rust 消费
    // ——逐条经 FFI 消费语义断言（nonce 重放 deny / 过期 deny / 换 scope
    // deny / 有效放行）。向量 expires_at 是 ISO8601（epoch 转换在
    // iso8601_to_epoch）；重放向量（n1/n3）的时间戳语义与过期正交，
    // 首次消费用新鲜窗口建立已消费状态后再重放（向量的 2026-08-16
    // 时间戳在重放分支之前就会触发 action_expired，触达不了重放本身）
    let root: serde_json::Value = serde_json::from_str(include_str!(
        "../../../../../../contracts/vectors/approvals-replay-and-expiry.json"
    ))
    .expect("向量 JSON 必须合法");
    let vectors = root["vectors"]
        .as_array()
        .expect("approvals 向量缺 vectors 数组");
    assert!(vectors.len() >= 5, "向量覆盖面收缩（{}）", vectors.len());
    let url = "https://example.com/";
    let mut semantic = 0usize;
    for v in vectors {
        let expected = v["expected"].as_str().unwrap_or("valid");
        let note = v["note"].as_str().unwrap_or("unnamed");
        let nonce = v["nonce"].as_str().unwrap_or_default().to_string();
        let scope = v["scope"].as_str().unwrap_or("navigation").to_string();
        // 重放向量：首次消费需要未过期窗口（见函数注释）——非重放
        // 向量按向量原值
        let vector_expiry = iso8601_to_epoch(v["expires_at"].as_str().unwrap_or_default())
            .unwrap_or_else(|| panic!("向量 {note}: expires_at 不可解析"));
        let fresh = crate::broker::now_unix_secs().unwrap_or(0) + 3_600;
        let expires_at = if expected == "deny_replay" {
            fresh
        } else {
            vector_expiry
        };
        let broker = FfiBroker::new(POLICY_VERSION.into());
        assert!(broker.create_session("s1".into(), "t1".into(), 1, 120));
        let action = AuthorizedAction {
            session_id: "s1".into(),
            tab_id: "t1".into(),
            document_generation: 1,
            origin: "https://example.com".into(),
            method: "GET".into(),
            canonical_parameters: "/".into(),
            scope: scope.clone(),
            expires_at,
            nonce: nonce.clone(),
            policy_version: POLICY_VERSION.into(),
            explanation: String::new(),
        };
        // 模拟 evaluate 签发后的账本状态（公共 evaluate 无法注入向量
        // 的 expires_at，经账本登记后走公共 consume 入口）
        broker.issued_actions.lock().unwrap().insert(
            action.nonce.clone(),
            IssuedAuthorization::Pending(Box::new(action.clone())),
        );
        let consume = |broker: &FfiBroker, scope: &str| {
            broker.consume_navigation(
                FfiAuthorizedAction::from(action.clone()),
                url.into(),
                scope.into(),
            )
        };
        match expected {
            "valid" => {
                // 未重放 + 远期过期：单次消费放行
                assert!(
                    matches!(consume(&broker, &scope), FfiDecision::Allow { .. }),
                    "向量 {note}: 有效授权必须放行"
                );
                semantic += 1;
            }
            "deny_replay" => {
                // 先原 scope 单次消费成功（入账），再按向量形态重放
                assert!(
                    matches!(consume(&broker, &scope), FfiDecision::Allow { .. }),
                    "向量 {note}: 重放前首次消费必须放行"
                );
                let replay_scope = v["replay_scope"].as_str().unwrap_or(&scope);
                let expected_code = if replay_scope != scope {
                    // PY-089：换 scope 重放——scope 参与授权绑定
                    "action_binding_mismatch"
                } else {
                    "nonce_replay"
                };
                match consume(&broker, replay_scope) {
                    FfiDecision::Deny { reason } => assert_eq!(
                        reason.code, expected_code,
                        "向量 {note}: 重放必须按 {expected_code} 拒绝"
                    ),
                    other => panic!("向量 {note}: 重放必须拒绝，实际 {other:?}"),
                }
                semantic += 1;
            }
            "deny_expired" => {
                // PY-090：expires_at 到点即拒（<=now 口径）
                match consume(&broker, &scope) {
                    FfiDecision::Deny { reason } => assert_eq!(
                        reason.code, "action_expired",
                        "向量 {note}: 过期必须 action_expired 拒绝"
                    ),
                    other => panic!("向量 {note}: 过期必须拒绝，实际 {other:?}"),
                }
                semantic += 1;
            }
            "deny_schema" => {
                // 缺 nonce（空串）：schema 层 minLength 是 Python 职责；
                // Rust 侧消费机制 = consume_nonce 对空 nonce 拒绝
                //（RS-034 nonce_invalid——长度非法不认账本键）
                match consume(&broker, &scope) {
                    FfiDecision::Deny { reason } => assert_eq!(
                        reason.code, "nonce_invalid",
                        "向量 {note}: 缺 nonce 的 Rust 侧消费语义（空 nonce 拒绝入账）"
                    ),
                    other => panic!("向量 {note}: 缺 nonce 必须拒绝，实际 {other:?}"),
                }
                semantic += 1;
            }
            other => panic!("向量 {note}: 未知 expected {other}"),
        }
    }
    assert!(semantic >= 5, "语义级向量覆盖面收缩（{semantic}）");
}

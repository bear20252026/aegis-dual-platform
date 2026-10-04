use super::super::*;

use super::common::*;

// —— RS-136（审计 2026-09-25）：ledger_can_admit 白盒直测 ——

fn craft_action(expires_in: i64) -> AuthorizedAction {
    // RS-220：测试辅助同样经 broker::now_unix_secs 单源取时
    let now = crate::broker::now_unix_secs().unwrap_or(0);
    AuthorizedAction {
        session_id: "s".into(),
        tab_id: "t".into(),
        document_generation: 0,
        origin: "https://example.com".into(),
        method: "GET".into(),
        canonical_parameters: "/".into(),
        scope: "navigation".into(),
        expires_at: (now as i64 + expires_in) as u64,
        nonce: format!("nonce-{expires_in}-{}", std::process::id()),
        policy_version: "test".into(),
        explanation: String::new(),
    }
}

#[test]
fn ledger_can_admit_direct_capacity_semantics() {
    let mut ledger: HashMap<String, IssuedAuthorization> = HashMap::new();
    // 未满：直接放行
    ledger.insert(
        "n1".into(),
        IssuedAuthorization::Pending(Box::new(craft_action(3600))),
    );
    assert!(ledger_can_admit(&mut ledger, MAX_ISSUED_ACTIONS));
    // 满 + 全部未过期 Pending：拒绝（fail-closed，不淘汰）
    let mut full: HashMap<String, IssuedAuthorization> = HashMap::new();
    for i in 0..MAX_ISSUED_ACTIONS {
        full.insert(
            format!("k{i}"),
            IssuedAuthorization::Pending(Box::new(craft_action(3600))),
        );
    }
    assert!(!ledger_can_admit(&mut full, MAX_ISSUED_ACTIONS));
    // 满 + 存在过期 Pending：惰性清理后放行（清理不触及 Consumed）
    let key0 = "k0".to_string();
    full.insert(
        key0.clone(),
        IssuedAuthorization::Pending(Box::new(craft_action(-1))),
    );
    assert!(ledger_can_admit(&mut full, MAX_ISSUED_ACTIONS));
    assert!(!full.contains_key(&key0), "过期 Pending 被清理");
    assert_eq!(
        full.len(),
        MAX_ISSUED_ACTIONS - 1,
        "清理仅腾位不扩容（insert 由调用方随后完成）"
    );
    // 拒绝路径：已满且全部为 Consumed（清理不触及）→ 拒绝
    let mut consumed_full: HashMap<String, IssuedAuthorization> = HashMap::new();
    for i in 0..MAX_ISSUED_ACTIONS {
        consumed_full.insert(
            format!("c{i}"),
            IssuedAuthorization::Consumed {
                session_id: "s".into(),
            },
        );
    }
    assert!(!ledger_can_admit(&mut consumed_full, MAX_ISSUED_ACTIONS));
}

// —— RS-287/300/301 回归（2026-10-02 审计） ——

#[test]
fn lazy_cleanup_treats_boundary_expiry_as_expired() {
    // RS-287：== now 即过期（RS-156 口径）——此前 `>= now` 保留 == 边界
    // 条目（已过期却驻留）。构造 expires_at == now 的 Pending 注入满
    // 账本，惰性清理必须移除（时间只前进，无翻转方向竞态）
    let mut full: HashMap<String, IssuedAuthorization> = HashMap::new();
    let now = crate::broker::now_unix_secs().unwrap_or(0);
    for i in 0..8 {
        full.insert(
            format!("k{i}"),
            IssuedAuthorization::Pending(Box::new(craft_action(3600))),
        );
    }
    full.insert(
        "boundary".into(),
        IssuedAuthorization::Pending(Box::new(AuthorizedAction {
            expires_at: now,
            ..craft_action(3600)
        })),
    );
    assert_eq!(full.len(), 9);
    // 容量 9：满 → 惰性清理 → boundary（== now）被移除 → 腾位放行
    assert!(ledger_can_admit(&mut full, 9));
    assert!(
        !full.contains_key("boundary"),
        "== now 的 Pending 必须按过期清理（RS-156 口径）"
    );
    // 判定单源直测：== now 过期、now+1 未过期
    assert!(pending_expired_at(now, now));
    assert!(pending_expired_at(now - 1, now));
    assert!(!pending_expired_at(now + 1, now));
}

#[test]
fn authorization_ledger_full_via_public_path() {
    // RS-300：账本容量 fail-closed 公共路径覆盖——生产容量 50K 全量
    // evaluate 在单测内是负担（每次 getrandom + URL 解析），测试构造器
    // 注入小容量（4）走同一公共路径（evaluate → validate →
    // ledger_can_admit → insert），第 5 次 evaluate 必须
    // authorization_ledger_full 拒绝
    let broker = FfiBroker::with_ledger_capacity(POLICY_VERSION.into(), ACTION_EXPIRY_SECONDS, 4);
    assert!(broker.create_session("s".into(), "t".into(), 1, 60));
    for i in 0..4 {
        let url = format!("https://example.com/ledger/{i}");
        assert!(
            matches!(
                broker.evaluate_navigation("s".into(), "t".into(), 1, url, "navigation".into()),
                FfiDecision::Allow { .. }
            ),
            "第 {i} 次（容量内）必须放行"
        );
    }
    // 第 5 次：满账本 + 全部未过期 → fail-closed 拒绝
    match broker.evaluate_navigation(
        "s".into(),
        "t".into(),
        1,
        "https://example.com/overflow".into(),
        "navigation".into(),
    ) {
        FfiDecision::Deny { reason } => {
            assert_eq!(reason.code, "authorization_ledger_full")
        }
        other => panic!("满账本必须 fail-closed，实际 {other:?}"),
    }
}

#[test]
fn consume_on_full_ledger_denies_then_replays() {
    // RS-301：consume 成功 + 满账本的收口语义——validate_and_consume
    // 已在核心层消费 nonce，但 Consumed 记录因满账本无法登记 → 本次
    // 导航 deny（authorization_ledger_full）；二次 consume 同 nonce →
    // nonce_replay（核心层已消费，收口闭合）
    let broker = FfiBroker::with_ledger_capacity(POLICY_VERSION.into(), ACTION_EXPIRY_SECONDS, 4);
    assert!(broker.create_session("s".into(), "t".into(), 1, 60));
    let FfiDecision::Allow { action } = broker.evaluate_navigation(
        "s".into(),
        "t".into(),
        1,
        "https://example.com/once".into(),
        "navigation".into(),
    ) else {
        panic!("容量内必须放行")
    };
    // 填满账本（3 个其它 Pending + 目标 = 4）
    for i in 0..3 {
        let url = format!("https://example.com/filler/{i}");
        assert!(matches!(
            broker.evaluate_navigation("s".into(), "t".into(), 1, url, "navigation".into()),
            FfiDecision::Allow { .. }
        ));
    }
    // consume：核心层消费成功，Consumed 登记被满账本拒 → deny
    match broker.consume_navigation(
        action.clone(),
        "https://example.com/once".into(),
        "navigation".into(),
    ) {
        FfiDecision::Deny { reason } => {
            assert_eq!(reason.code, "authorization_ledger_full")
        }
        other => panic!("满账本 consume 必须 deny，实际 {other:?}"),
    }
    // 二次 consume：核心层 nonce 已消费 → nonce_replay（收口闭合）
    match broker.consume_navigation(
        action,
        "https://example.com/once".into(),
        "navigation".into(),
    ) {
        FfiDecision::Deny { reason } => assert_eq!(reason.code, "nonce_replay"),
        other => panic!("二次 consume 必须重放拒绝，实际 {other:?}"),
    }
}

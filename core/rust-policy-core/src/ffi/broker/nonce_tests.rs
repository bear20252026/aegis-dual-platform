use super::*;

#[test]
fn generate_nonce_is_64_lowercase_hex_chars() {
    for _ in 0..8 {
        let nonce = generate_nonce().expect("OS entropy available in tests");
        assert_eq!(nonce.len(), 64, "32 字节 hex 编码必须 64 字符");
        assert!(
            nonce
                .bytes()
                .all(|b| b.is_ascii_hexdigit() && !b.is_ascii_uppercase()),
            "nonce 必须全小写 hex（与 MAX_NONCE_LENGTH 校验、账本键序一致）"
        );
    }
    // 两次生成不重复（随机性抽查）
    let a = generate_nonce().unwrap();
    let b = generate_nonce().unwrap();
    assert_ne!(a, b);
}

// —— RS-185/199（审计 2026-09-25）——

#[test]
fn entropy_error_maps_to_typed_deny() {
    // RS-199：熵不足路径参数化后可测——映射构造的拒绝码/文案单源锁定
    //（真实 getrandom 失败在测试进程不可注入，映射函数即为注入面）
    let reason = entropy_error(getrandom::Error::UNSUPPORTED);
    assert_eq!(reason.code, "entropy_unavailable");
    assert!(reason.explanation.contains("entropy unavailable"));
    // 编码契约：确定性输入 → 确定性输出（64 字符小写 hex）
    let nonce = nonce_from_entropy(&[0u8; 32]);
    assert_eq!(nonce, "0".repeat(64));
    let nonce = nonce_from_entropy(&[0xff; 32]);
    assert_eq!(nonce, "f".repeat(64));
    assert_eq!(nonce_from_entropy(&[0xab; 32]).len(), 64);
}

#[test]
fn approve_navigation_rejects_unparseable_url() {
    // RS-185：approve 的 URL 解析失败分支此前零测试——pending 审批
    // 对畸形 URL 必须拒绝（url_policy），且不消费 pending 记录？
    // 口径核实：canonicalize 在 remove(&nonce) 之后执行——失败时
    // nonce 已被移除（一次性语义：畸形重试后 approval_not_pending）
    let broker = FfiBroker::new("1.0".into());
    assert!(broker.create_session("s".into(), "t".into(), 1, 120));
    let decision = broker.request_navigation_confirmation(
        "s".into(),
        "t".into(),
        1,
        "https://127.0.0.1/confirm".into(),
        "navigation".into(),
    );
    let FfiDecision::RequireConfirmation { request } = decision else {
        panic!("active session should produce confirmation request");
    };
    // 畸形 URL approve → deny（url_policy）
    let denied = broker.approve_navigation_confirmation(
        request.nonce.clone(),
        "https://[::1]/bad".into(),
        "navigation".into(),
    );
    match denied {
        FfiDecision::Deny { reason } => {
            assert_eq!(reason.code, "url_policy", "畸形 URL 必须走 url_policy 拒绝");
        }
        other => panic!("期望 Deny，实际 {other:?}"),
    }
    // pending 已被移除（一次性语义）：同 nonce 重试 → approval_not_pending
    let retry = broker.approve_navigation_confirmation(
        request.nonce,
        "https://127.0.0.1/confirm".into(),
        "navigation".into(),
    );
    match retry {
        FfiDecision::Deny { reason } => {
            assert_eq!(reason.code, "approval_not_pending");
        }
        other => panic!("期望 approval_not_pending，实际 {other:?}"),
    }
}

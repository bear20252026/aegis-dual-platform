use super::super::*;

use super::common::*;

/// P1-11 回归（全量复审 2026-09-01）：ttl=0 必须钳到下限——
/// 原实现会签发"成功、即刻过期"的静默失效会话。
#[test]
fn create_session_clamps_zero_ttl_to_minimum() {
    let broker = FfiBroker::new(POLICY_VERSION.into());
    assert!(broker.create_session("s-min".into(), "tab-1".into(), 1, 0));
    let decision = broker.evaluate_navigation(
        "s-min".into(),
        "tab-1".into(),
        1,
        "https://example.com/".into(),
        "navigation".into(),
    );
    assert!(
        matches!(
            decision,
            FfiDecision::Allow { .. } | FfiDecision::RequireConfirmation { .. }
        ),
        "ttl=0 钳到 MIN_SESSION_TTL_SECONDS 后会话应在窗口内有效"
    );
}

// —— RS-158（审计 2026-09-25）：TTL 上限钳制 ——

#[test]
fn create_session_clamps_huge_ttl_to_maximum() {
    // u64::MAX 会话近乎永生——必须钳到 MAX_SESSION_TTL_SECONDS（24h）。
    // 实际生效 TTL 经 core session_ttl 可观测性 API 读取（测试不可
    // 反射宿主传参，只认签发结果）。
    // 注意：锁作用域最小化——持有 inner 锁期间不得再调
    // broker.create_session（内部二次 lock 同一 Mutex = 自死锁）
    let broker = FfiBroker::new(POLICY_VERSION.into());
    assert!(broker.create_session("s-max".into(), "tab-1".into(), 1, u64::MAX));
    {
        let inner = broker.inner.lock().expect("broker 锁必须可用");
        assert_eq!(
            inner.session_ttl("s-max"),
            Some(std::time::Duration::from_secs(MAX_SESSION_TTL_SECONDS)),
            "超长 TTL 必须钳到 24h 上限"
        );
    }
    // 边界内侧：86400 恰好等于上限——原样接受（锁已释放，安全再入）
    assert!(broker.create_session("s-cap".into(), "tab-1".into(), 1, 86_400));
    let inner = broker.inner.lock().expect("broker 锁必须可用");
    assert_eq!(
        inner.session_ttl("s-cap"),
        Some(std::time::Duration::from_secs(86_400)),
        "恰等于上限的 TTL 原样生效"
    );
}

// —— RS-159（审计 2026-09-25）：session_id 直测 ——

#[test]
fn create_session_rejects_empty_session_id() {
    // 空 session_id 拒绝（fail-closed，对齐 Action schema minLength 1）——
    // 空 id 会话即匿名共享会话，破坏 persona 隔离语义
    let broker = FfiBroker::new(POLICY_VERSION.into());
    assert!(!broker.create_session(String::new(), "tab-1".into(), 1, 60));
    // 创建失败即无会话——后续导航必须拒绝（fail-closed 闭环）
    let decision = broker.evaluate_navigation(
        String::new(),
        "tab-1".into(),
        1,
        "https://example.com/".into(),
        "navigation".into(),
    );
    assert!(
        matches!(decision, FfiDecision::Deny { .. }),
        "空 id 会话不存在——导航必须拒绝"
    );
}

// —— RS-223（审计 2026-09-26）：会话键长度上限 ——

#[test]
fn create_session_rejects_oversized_keys() {
    // 键长度上限 256 字节（与 core 层 MAX_TAB_ID_LEN 对齐）——此前仅查
    // 空串，1024 会话 × 64KB 双键 ≈128MB 键驻留面
    let broker = FfiBroker::new(POLICY_VERSION.into());
    let oversized = "x".repeat(MAX_SESSION_KEY_BYTES + 1);
    assert!(
        !broker.create_session(oversized.clone(), "t".into(), 1, 60),
        "超长 session_id 拒绝"
    );
    assert!(
        !broker.create_session("s".into(), oversized.clone(), 1, 60),
        "超长 tab_id 拒绝"
    );
    // 边界内（256 字节）放行
    let at_cap = "y".repeat(MAX_SESSION_KEY_BYTES);
    assert!(broker.create_session(at_cap.clone(), "t".into(), 1, 60));
    // 创建失败即无会话——超长 id 导航必须拒绝（fail-closed 闭环）
    assert!(matches!(
        broker.evaluate_navigation(
            oversized,
            "t".into(),
            1,
            "https://example.com/".into(),
            "navigation".into(),
        ),
        FfiDecision::Deny { .. }
    ));
}

#[test]
fn create_session_session_id_uniqueness_and_isolation() {
    // session_id 隔离语义直测：同 id replace（RS-033 续期契约）+
    // 异 id 各自独立（不同 id 不串会话）
    let broker = FfiBroker::new(POLICY_VERSION.into());
    assert!(broker.create_session("sa".into(), "tab-a".into(), 1, 60));
    assert!(broker.create_session("sb".into(), "tab-b".into(), 1, 60));
    // sa 的会话不能在 tab-b 上用（会话 ↔ 标签绑定）
    let cross = broker.evaluate_navigation(
        "sa".into(),
        "tab-b".into(),
        1,
        "https://example.com/".into(),
        "navigation".into(),
    );
    assert!(
        matches!(cross, FfiDecision::Deny { .. }),
        "跨标签复用会话必须拒绝"
    );
    // 同 id replace 语义（续期）——与 RS-033 契约一致
    assert!(broker.create_session("sa".into(), "tab-a".into(), 1, 120));
}

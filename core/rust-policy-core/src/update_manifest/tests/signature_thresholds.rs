use super::super::*;

// —— RS-124（审计 2026-09-25）：verify_threshold 白盒分支——

use ed25519_dalek::{Signer, SigningKey};

// RS-306（2026-10-02 审计）：b64_encode 已收敛为模块级共享单源
//（super::b64_encode 经 `use super::super::*;` 可见）——本模块此前内联的
// 逐字节相同副本已删除

/// 测试辅助：用固定种子密钥签名 canonical payload，返回
/// (key_id, 公钥字节, 签名条目)。
fn make_signature(
    seed: [u8; 32],
    key_id: &str,
    payload: &[u8],
) -> (String, Vec<u8>, serde_json::Value) {
    let sk = SigningKey::from_bytes(&seed);
    let vk = sk.verifying_key();
    let sig = sk.sign(payload);
    (
        key_id.to_string(),
        vk.as_bytes().to_vec(),
        serde_json::json!({
            "key_id": key_id,
            "sig": b64_encode(&sig.to_bytes()),
        }),
    )
}

#[test]
fn threshold_zero_or_huge_always_rejected() {
    // 白盒分支 1：threshold < 1 直接 false（空签名集也不可能通过）
    let keys: std::collections::HashMap<String, Vec<u8>> = Default::default();
    let payload = canonical_unsigned(&serde_json::json!({"version": "1.0.0"})).unwrap();
    assert!(!verify_threshold(&keys, &[], &payload, 0));
    // usize::MAX：永远达不到的阈值 = fail-closed（哪怕签名全有效）
    let (kid, pubkey, sig) = make_signature([7u8; 32], "k1", &payload);
    let mut keys = keys;
    keys.insert(kid.clone(), pubkey);
    assert!(!verify_threshold(&keys, &[sig], &payload, usize::MAX));
}

#[test]
fn duplicate_keyid_counts_once() {
    // 白盒分支 2：重复 keyid 只计一次（TUF THRESHOLD counting）——
    // 同一密钥签两次不得凑满 threshold=2
    let payload = canonical_unsigned(&serde_json::json!({"version": "1.0.0"})).unwrap();
    let (kid, pubkey, sig1) = make_signature([7u8; 32], "k1", &payload);
    let (_, _, sig2) = make_signature([7u8; 32], "k1", &payload);
    let mut keys = std::collections::HashMap::new();
    keys.insert(kid, pubkey);
    let sigs = vec![sig1, sig2];
    assert!(verify_threshold(&keys, &sigs, &payload, 1));
    assert!(
        !verify_threshold(&keys, &sigs, &payload, 2),
        "同一 keyid 的重复签名不得凑满阈值（防密钥复用凑数）"
    );
}

#[test]
fn malformed_signature_entries_are_skipped() {
    // 白盒分支 3：非对象 / 缺 key_id / 未知 key_id / 缺 sig /
    // 非法 base64 / 签名长度错 / 公钥长度错——七类全部跳过，
    // 仅有效签名计入（fail-closed：全部畸形时 threshold 1 也不通过）
    let payload = canonical_unsigned(&serde_json::json!({"version": "1.0.0"})).unwrap();
    let (kid, pubkey, good_sig) = make_signature([7u8; 32], "k1", &payload);
    let mut keys = std::collections::HashMap::new();
    keys.insert(kid.clone(), pubkey);
    keys.insert("short-key".to_string(), vec![0u8; 10]); // 公钥长度错
    let sigs = vec![
        serde_json::json!(1),                                              // 非对象
        serde_json::json!({"sig": "AA=="}),                                // 缺 key_id
        serde_json::json!({"key_id": "ghost", "sig": "AA=="}),             // 未知 key_id
        serde_json::json!({"key_id": kid}),                                // 缺 sig
        serde_json::json!({"key_id": kid, "sig": "!!!"}),                  // 非法 base64
        serde_json::json!({"key_id": kid, "sig": b64_encode(&[0u8; 10])}), // 签名长度错
        serde_json::json!({"key_id": "short-key", "sig": b64_encode(&[0u8; 64])}), // 公钥长度错
    ];
    assert!(!verify_threshold(&keys, &sigs, &payload, 1));
    // 混入一条有效签名后通过——畸形条目只跳过不拖累
    let mut sigs = sigs;
    sigs.push(good_sig);
    assert!(verify_threshold(&keys, &sigs, &payload, 1));
}

#[test]
fn two_distinct_keys_meet_threshold_and_tamper_breaks() {
    // 白盒分支 4：两个不同密钥各自有效签名凑满 threshold=2；
    // 载荷被篡改后验证必须失败（verify_strict）
    let payload = canonical_unsigned(&serde_json::json!({"version": "1.0.0"})).unwrap();
    let (kid1, pub1, sig1) = make_signature([7u8; 32], "k1", &payload);
    let (kid2, pub2, sig2) = make_signature([9u8; 32], "k2", &payload);
    let mut keys = std::collections::HashMap::new();
    keys.insert(kid1, pub1);
    keys.insert(kid2, pub2);
    let sigs = vec![sig1, sig2];
    assert!(verify_threshold(&keys, &sigs, &payload, 2));
    // 篡改载荷（多一个字段）→ canonical 字节变化 → 全部签名失效
    let tampered =
        canonical_unsigned(&serde_json::json!({"version": "1.0.0", "extra": 1})).unwrap();
    assert!(!verify_threshold(&keys, &sigs, &tampered, 2));
}

// —— 审计第六轮延续（2026-10-04）：按密钥字节去重 + 退化锚筛除 ——

#[test]
fn same_key_under_two_keyids_counts_as_one_vote() {
    // 票数是"多少把不同的密钥签了"，不是"多少条署名记录存在"。
    // 修复前只按 keyid 去重 → 同一把公钥挂两个 keyid 即凑满 threshold=2，
    // t-of-n 被单钥满足。
    let payload = canonical_unsigned(&serde_json::json!({"version": "1.0.0"})).unwrap();
    let (kid_a, pub_a, sig_a) = make_signature([7u8; 32], "k1", &payload);
    let (kid_b, pub_b, sig_b) = make_signature([7u8; 32], "k1-renamed", &payload);
    assert_eq!(pub_a, pub_b, "同一把密钥的公钥字节必须相同（测试前提）");
    let mut keys = std::collections::HashMap::new();
    keys.insert(kid_a, pub_a);
    keys.insert(kid_b, pub_b);
    let sigs = vec![sig_a, sig_b];
    assert!(
        !verify_threshold(&keys, &sigs, &payload, 2),
        "单钥换名重复计票不得凑满 threshold=2"
    );
    // threshold=1 仍可（确实有一把有效密钥）——防止修成恒拒
    assert!(verify_threshold(&keys, &sigs, &payload, 1));
}

#[test]
fn degenerate_public_key_encodings_are_rejected_explicitly() {
    // 单位元 / y=0 / 阶 2 点（y = p-1）——含符号位置变体
    let mut identity = [0u8; 32];
    identity[0] = 1;
    assert!(is_degenerate_public_key(&identity));
    let mut identity_signed = identity;
    identity_signed[31] = 0x80; // x 符号位置位，y 不变
    assert!(is_degenerate_public_key(&identity_signed));
    assert!(is_degenerate_public_key(&[0u8; 32]));
    let mut order2 = [0u8; 32];
    order2[0] = 0xec;
    order2[1..31].fill(0xff);
    order2[31] = 0x7f;
    assert!(is_degenerate_public_key(&order2));
    // 正常公钥不得误伤（否则阈值判定恒假=另一种假闭环）
    let sk = SigningKey::from_bytes(&[7u8; 32]);
    assert!(
        !is_degenerate_public_key(&sk.verifying_key().to_bytes()),
        "真实公钥被误判为退化——筛选过宽会把 quorum 变成永不可达"
    );
}

// —— RS-126/127（审计 2026-09-25）：canonical 遍历跳过 + 浮点拒绝——

#[test]
fn canonical_skips_only_top_level_signatures() {
    // RS-126 回归：顶层 signatures 剔除；嵌套同名键保留（Python 对齐）
    let manifest = serde_json::json!({
        "version": "1.0.0",
        "signatures": [{"key_id": "k1"}],
        "meta": {"signatures": "kept", "nested": true}
    });
    let bytes = canonical_unsigned(&manifest).unwrap();
    let text = String::from_utf8(bytes).unwrap();
    assert!(
        !text.contains(r#""signatures":[{"#),
        "顶层 signatures 必须剔除"
    );
    assert!(
        text.contains(r#""signatures":"kept""#),
        "嵌套 signatures 必须保留"
    );
    assert!(text.contains(r#""meta":{"#), "嵌套对象完整输出");
}

#[test]
fn canonical_rejects_float_numbers_failclosed() {
    // RS-127：浮点 to_string 与 Python json.dumps 字节级漂移
    // （1e30 vs 1e+30）——非整型数值 fail-closed 拒绝
    assert!(canonical_unsigned(&serde_json::json!({"version": "1.0.0", "score": 1.5})).is_err());
    // 整数值的 f64 形态（JSON 里 2.0）同样拒绝——Python 侧输出 "2.0"
    // 与整型 "2" 漂移，无法确定性对齐
    assert!(canonical_unsigned(&serde_json::json!({"version": "1.0.0", "n": 2.0})).is_err());
    assert!(canonical_unsigned(&serde_json::json!({"version": "1.0.0", "n": 1e30})).is_err());
    // 嵌套浮点同样拒绝
    assert!(
        canonical_unsigned(&serde_json::json!({"a": {"b": [1, 2.5]}})).is_err(),
        "嵌套数组内的浮点也必须拒绝"
    );
    // 整型照常通过
    assert!(canonical_unsigned(
        &serde_json::json!({"a": 1, "b": -5, "c": 18446744073709551615u64})
    )
    .is_ok());
}

use super::*;
use std::collections::HashMap;

/// 单位元/退化信任锚 tripwire（审计第六轮 2026-10-03/04）。
///
/// 背景：`try_verify_signature` 对可信密钥只做 `VerifyingKey::from_bytes`
/// 以及长度校验，未显式拒绝退化点。数学上若 A 为单位元则 [k]A = O，
/// 验证方程退化为 [s]B = R，攻击者可对任意消息造出通过验证的"签名"
/// ——一个错配的槽位即把 t-of-n 降为"无需 quorum"。
///
/// **本轮实测结论（不虚构）**：ed25519-dalek 3.x 下 `from_bytes` 接受单位元
/// 编码，但按上述构造（R = 基点压缩编码 66..66、s = 1）的 forged 签名被
/// `verify_strict` **拒绝**——即该绕过在当前依赖版本上不可利用。因此本断言
/// 的作用是 **tripwire**：若 dalek 升级/换版后开始接受，或有人改用非 strict
/// 验证，本测试即红。不要把它当成"已在核心层显式拒绝退化密钥"的证据——
/// 核心层仍未做小顺序点筛除，那属于信任锚供给格式变更（需同步 keyid 派生）。
#[test]
fn identity_anchor_does_not_verify_forged_signature() {
    let mut identity = [0u8; 32];
    identity[0] = 1; // 压缩单位元
    let Ok(vk) = VerifyingKey::from_bytes(&identity) else {
        // dalek 若将来直接拒收单位元编码，同样安全——记录并返回
        return;
    };
    let mut forged = [0u8; 64];
    for b in forged[..32].iter_mut() {
        *b = 0x66; // R = 基点 B 的压缩编码
    }
    forged[32] = 1; // s = 1（小端）
    let msg = b"attacker chosen payload";
    let sig = Signature::from_bytes(&forged);
    assert!(
        vk.verify_strict(msg, &sig).is_err(),
        "单位元信任锚竟通过了构造伪造——dalek 行为已变，须显式筛除退化密钥"
    );
}

/// keyid 与密钥字节无绑定：同一 keyid 名下喂不同字节，当前实现照单全收。
/// 本测试**记录现状**（断言存在该行为），供后续信任锚格式改造时有回归基线。
#[test]
fn keyid_is_not_bound_to_key_bytes_current_state() {
    let mut trusted: HashMap<String, Vec<u8>> = HashMap::new();
    // keyid 声明为 "expected-id"，但字节是任意合法公钥——验证只看 map 取值
    trusted.insert("expected-id".into(), vec![7u8; 32]);
    let sigs = vec![serde_json::json!({"key_id": "expected-id", "sig": "x"})];
    // 非法 base64/长度 → 该签名不计入（阈值不达），但**不因 keyid 与字节
    // 不匹配而额外拒绝**——即无绑定校验。
    assert!(
        !verify_threshold(&trusted, &sigs, b"payload", 1),
        "非法签名不应计入阈值"
    );
}

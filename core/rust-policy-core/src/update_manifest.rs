//! Update Manifest canonicalization + Ed25519 阈值验证（蓝图阶段 F 第一推荐项）。
//!
//! 依据（全球调研交叉）：TUF Specification 1.0.36 官方（canonical JSON——
//! 签名验证前提；THRESHOLD counting——keyid 唯一——重复 keyid 只计一次——
//! 与 update_verifier P0-04 一致）+ Houseme Ed25519 生产实践（verify_strict
//! 防 malleability——严格验证）。
//! 纯函数——manifest/trusted keys/签名参数注入（无 I/O）。

use ed25519_dalek::{Signature, VerifyingKey};

/// TUF canonical JSON（排序键 + 紧凑分隔——与 Python canonical_unsigned 一致）。
/// canonicalization 是签名验证前提（TUF 官方）。
pub fn canonical_unsigned(manifest: &serde_json::Value) -> Vec<u8> {
    let mut bytes = Vec::new();
    canonical_write(manifest, &mut bytes);
    bytes
}

fn canonical_write(value: &serde_json::Value, out: &mut Vec<u8>) {
    match value {
        serde_json::Value::Object(map) => {
            out.push(b'{');
            let mut keys: Vec<&String> = map.keys().collect();
            keys.sort();
            for (i, key) in keys.iter().enumerate() {
                if i > 0 {
                    out.push(b',');
                }
                canonical_write(&serde_json::Value::String((*key).clone()), out);
                out.push(b':');
                canonical_write(&map[*key], out);
            }
            out.push(b'}');
        }
        serde_json::Value::Array(arr) => {
            out.push(b'[');
            for (i, item) in arr.iter().enumerate() {
                if i > 0 {
                    out.push(b',');
                }
                canonical_write(item, out);
            }
            out.push(b']');
        }
        serde_json::Value::String(s) => {
            out.push(b'"');
            out.extend_from_slice(s.as_bytes());
            out.push(b'"');
        }
        other => out.extend_from_slice(other.to_string().as_bytes()),
    }
}

/// 解析 SemVer 字符串（与 contracts/version.schema.json 一致——拒绝无效格式）。
pub fn version_tuple(value: &str) -> Option<(u64, u64, u64)> {
    let mut parts = value.split('.');
    let major = parts.next()?.parse().ok()?;
    let minor = parts.next()?.parse().ok()?;
    let patch = parts.next()?.parse().ok()?;
    if parts.next().is_some() {
        return None;
    }
    Some((major, minor, patch))
}

/// Ed25519 阈值验证（TUF THRESHOLD counting——keyid 唯一——重复 keyid 只计一次；
/// verify_strict 防 malleability——生产实践）。
/// 纯函数：trusted keys（keyid -> 公钥字节）+ manifest（已 canonical）参数注入。
pub fn verify_threshold(
    trusted_keys: &std::collections::HashMap<String, Vec<u8>>,
    signatures: &[serde_json::Value],
    canonical_payload: &[u8],
    threshold: usize,
) -> bool {
    if threshold < 1 {
        return false;
    }
    let mut valid_key_ids: std::collections::HashSet<String> = Default::default();
    for sig in signatures {
        let obj = match sig.as_object() {
            Some(o) => o,
            None => continue,
        };
        let key_id = match obj.get("key_id").and_then(|v| v.as_str()) {
            Some(k) => k.to_string(),
            None => continue,
        };
        if valid_key_ids.contains(&key_id) {
            continue; // 重复 keyid 只计一次（TUF THRESHOLD counting——与 P0-04 一致）
        }
        let key_bytes = match trusted_keys.get(&key_id) {
            Some(k) => k,
            None => continue,
        };
        let sig_bytes = match obj.get("sig").and_then(|v| v.as_str()) {
            Some(s) => s,
            None => continue,
        };
        let Ok(sig_bytes) = base64_decode(sig_bytes) else {
            continue;
        };
        // ed25519-dalek 2.x：from_bytes 期望固定长度数组（[u8; 32]/[u8; 64]——
        // E0308 修复——公钥/签名长度校验——try_into）
        let Ok(key_arr) = <[u8; 32]>::try_from(key_bytes.as_slice()) else {
            continue;
        };
        let Ok(sig_arr) = <[u8; 64]>::try_from(sig_bytes.as_slice()) else {
            continue;
        };
        // ed25519-dalek 2.x：VerifyingKey::from_bytes 返回 Result（let-else 处理
        // Err）；Signature::from_bytes 直接返回 Signature（非 Result——2.x API）
        let Ok(verifying_key) = VerifyingKey::from_bytes(&key_arr) else {
            continue;
        };
        let signature = Signature::from_bytes(&sig_arr);
        // verify_strict：严格验证——防 malleability（Houseme 生产实践）
        if verifying_key
            .verify_strict(canonical_payload, &signature)
            .is_ok()
        {
            valid_key_ids.insert(key_id);
        }
    }
    valid_key_ids.len() >= threshold
}

/// 基础 base64 解码（纯函数——无外部 crate 依赖的简版；生产用 base64 crate——
/// 蓝图最小依赖取舍：此实现仅试点，后续迁移 base64 crate）。
fn base64_decode(input: &str) -> Result<Vec<u8>, ()> {
    const TABLE: &[u8] = b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
    let mut out = Vec::new();
    let mut buf = 0u32;
    let mut bits = 0u32;
    for &ch in input.as_bytes() {
        if ch == b'=' {
            break;
        }
        let val = TABLE.iter().position(|&t| t == ch).ok_or(())? as u32;
        buf = (buf << 6) | val;
        bits += 6;
        if bits >= 8 {
            bits -= 8;
            out.push((buf >> bits) as u8);
        }
    }
    Ok(out)
}

//! Update Manifest canonicalization + Ed25519 阈值验证（蓝图阶段 F 第一推荐项）。
//!
//! 依据（全球调研交叉）：TUF Specification 1.0.36 官方（canonical JSON——
//! 签名验证前提；THRESHOLD counting——keyid 唯一——重复 keyid 只计一次——
//! 与 update_verifier P0-04 一致）+ Houseme Ed25519 生产实践（verify_strict
//! 防 malleability——严格验证）。
//! 纯函数——manifest/trusted keys/签名参数注入（无 I/O）。

use ed25519_dalek::{Signature, VerifyingKey};

/// TUF canonical JSON（排序键 + 紧凑分隔——与 Python canonical_unsigned 字节级一致）。
/// canonicalization 是签名验证前提（TUF 官方）。
///
/// 批次4-3 修复（全面审计 2026-09-04）：与发布链权威实现
/// `release/update_verifier.py::canonical_unsigned` 对齐——
/// ① 剔除**顶层** `signatures` 键（签名不参与被签载荷）；
/// ② 字符串按 JSON 标准转义（此前直出原始字节——值含 `"`/`\`/控制字符时
///    产生非法或歧义 canonical 字节，签名两端校验不一致 = 验证旁路面）。
/// 字节级一致性由 `contracts/vectors/update-manifest-canonical.json`
/// golden 向量锁定（Python 侧生成、Rust 断言——tests/vectors.rs 消费）。
pub fn canonical_unsigned(manifest: &serde_json::Value) -> Vec<u8> {
    let mut bytes = Vec::new();
    match manifest.as_object() {
        // 仅剔除顶层 signatures（Python 字典推导同语义——嵌套对象不动）
        Some(map) => {
            let mut filtered = map.clone();
            filtered.remove("signatures");
            canonical_write(&serde_json::Value::Object(filtered), &mut bytes);
        }
        None => canonical_write(manifest, &mut bytes),
    }
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
                write_json_string(key, out);
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
        serde_json::Value::String(s) => write_json_string(s, out),
        other => out.extend_from_slice(other.to_string().as_bytes()),
    }
}

/// JSON 字符串序列化（与 Python `json.dumps(ensure_ascii=False)` 转义语义
/// 一致）：`"`/`\`/控制字符转义，短转义优先（\b\f\n\r\t），其余 <0x20 用
/// `\u00xx`（4 位小写 hex）；非 ASCII 原样 UTF-8 输出（ensure_ascii=False）。
fn write_json_string(s: &str, out: &mut Vec<u8>) {
    out.push(b'"');
    for ch in s.chars() {
        match ch {
            '"' => out.extend_from_slice(b"\\\""),
            '\\' => out.extend_from_slice(b"\\\\"),
            '\u{08}' => out.extend_from_slice(b"\\b"),
            '\u{0C}' => out.extend_from_slice(b"\\f"),
            '\n' => out.extend_from_slice(b"\\n"),
            '\r' => out.extend_from_slice(b"\\r"),
            '\t' => out.extend_from_slice(b"\\t"),
            c if (c as u32) < 0x20 => {
                out.extend_from_slice(format!("\\u{:04x}", c as u32).as_bytes());
            }
            c => {
                let mut buf = [0u8; 4];
                out.extend_from_slice(c.encode_utf8(&mut buf).as_bytes());
            }
        }
    }
    out.push(b'"');
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
/// 审计整改（2026-09-07）：严格校验——padding 只能在末尾、`=` 之后不得再有
/// 数据、数据长度模 4 不得为 1、尾部残留非零 bit 拒绝。
fn base64_decode(input: &str) -> Result<Vec<u8>, ()> {
    const TABLE: &[u8] = b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
    let bytes = input.as_bytes();
    let mut out = Vec::new();
    let mut buf = 0u32;
    let mut bits = 0u32;
    let mut index = 0usize; // 非 padding 字符数
    let mut saw_padding = false;
    for &ch in bytes {
        match ch {
            b'=' => {
                // 首个 '=' 之前的数据量必须是 2/3（模 4）；重复 '=' 允许，
                // 但总量由输入长度与末尾规则共同约束
                if !saw_padding && index % 4 != 2 && index % 4 != 3 {
                    return Err(());
                }
                saw_padding = true;
            }
            _ if saw_padding => return Err(()), // '=' 之后出现数据
            _ => {
                let val = TABLE.iter().position(|&t| t == ch).ok_or(())? as u32;
                buf = (buf << 6) | val;
                bits += 6;
                index += 1;
                if bits >= 8 {
                    bits -= 8;
                    out.push((buf >> bits) as u8);
                }
            }
        }
    }
    // 数据长度模 4 == 1 是非法编码（单字符剩余 6bit 无意义）
    if index % 4 == 1 {
        return Err(());
    }
    // 剩余未消费 bits 必须为 0（拒绝尾部非零 bit 的非规范编码）
    if bits > 0 && (buf & ((1u32 << bits) - 1)) != 0 {
        return Err(());
    }
    Ok(out)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn base64_decodes_canonical() {
        assert_eq!(base64_decode("Zg==").unwrap(), vec![0x66]); // 'f'
        assert_eq!(base64_decode("aGVsbG8=").unwrap(), b"hello".to_vec());
        assert_eq!(base64_decode("YWI=").unwrap(), b"ab".to_vec());
    }

    #[test]
    fn base64_rejects_noncanonical_trailing_bits() {
        // "AB==" -> A=0,B=1 => 字节 0、尾部残留 0b0001 非零 → 拒绝
        assert!(base64_decode("AB==").is_err());
        // "AA==" -> 字节 0、尾部残留 0 → 接受
        assert!(base64_decode("AA==").is_ok());
    }

    #[test]
    fn base64_rejects_bad_padding_placement() {
        assert!(base64_decode("A=AA").is_err()); // '=' 在中间
        assert!(base64_decode("AA=A").is_err()); // '=' 后有数据
        assert!(base64_decode("A====").is_err()); // 过多 '='
    }

    #[test]
    fn base64_rejects_length_one_mod_four() {
        assert!(base64_decode("A").is_err()); // index%4==1
        assert!(base64_decode("Zg").is_ok()); // 2 数据字符合法
    }
}

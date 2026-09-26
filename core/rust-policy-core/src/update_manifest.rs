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
///
/// RS-127（审计 2026-09-25）：返回 `Result`——manifest 含**非整型数值**
/// （浮点）时 fail-closed 拒绝：`f64::to_string` 与 Python `json.dumps`
/// 存在字节级漂移（如 serde `1e30` vs Python `1e+30`），漂移即签名两端
/// canonical 字节不一致 = 验证失败面。manifest schema（version.schema.json）
/// 不含浮点字段——含浮点即非法载荷，拒绝而非静默产出漂移字节。
/// RS-127（审计 2026-09-25）：canonical 失败（manifest 含非整型数值）的
/// 错误标记类型——fail-closed 拒绝不可确定性序列化的载荷。
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct CanonicalError;

pub fn canonical_unsigned(manifest: &serde_json::Value) -> Result<Vec<u8>, CanonicalError> {
    let mut bytes = Vec::new();
    match manifest.as_object() {
        // 仅剔除顶层 signatures（Python 字典推导同语义——嵌套对象不动）。
        // RS-126（审计 2026-09-25）：键过滤遍历替代整 map clone——
        // 此前 clone 整个顶层对象再 remove，O(map) 堆分配纯属浪费
        Some(map) => canonical_write_object(map, &mut bytes, Some("signatures"))?,
        None => canonical_write(manifest, &mut bytes)?,
    }
    Ok(bytes)
}

/// 顶层对象写入（RS-126：skip_key 过滤替代 clone+remove）。
fn canonical_write_object(
    map: &serde_json::Map<String, serde_json::Value>,
    out: &mut Vec<u8>,
    skip_key: Option<&str>,
) -> Result<(), CanonicalError> {
    out.push(b'{');
    let mut keys: Vec<&String> = map
        .keys()
        .filter(|k| Some(k.as_str()) != skip_key)
        .collect();
    keys.sort();
    for (i, key) in keys.iter().enumerate() {
        if i > 0 {
            out.push(b',');
        }
        write_json_string(key, out);
        out.push(b':');
        canonical_write(&map[*key], out)?;
    }
    out.push(b'}');
    Ok(())
}

fn canonical_write(value: &serde_json::Value, out: &mut Vec<u8>) -> Result<(), CanonicalError> {
    match value {
        serde_json::Value::Object(map) => canonical_write_object(map, out, None),
        serde_json::Value::Array(arr) => {
            out.push(b'[');
            for (i, item) in arr.iter().enumerate() {
                if i > 0 {
                    out.push(b',');
                }
                canonical_write(item, out)?;
            }
            out.push(b']');
            Ok(())
        }
        serde_json::Value::String(s) => {
            write_json_string(s, out);
            Ok(())
        }
        serde_json::Value::Number(n) => {
            // RS-127：仅整型（i64/u64）可确定性序列化——浮点 to_string
            // 与 Python json.dumps 字节级漂移（1e30 vs 1e+30 等）即
            // 签名验证失败面——fail-closed 拒绝
            if n.is_i64() || n.is_u64() {
                out.extend_from_slice(n.to_string().as_bytes());
                Ok(())
            } else {
                Err(CanonicalError)
            }
        }
        other => {
            out.extend_from_slice(other.to_string().as_bytes());
            Ok(())
        }
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

/// 解析 SemVer 严格核心版字符串（与 contracts/version.schema.json 的
/// `(0|[1-9][0-9]*)` 数字段口径一致——拒绝无效格式）。
///
/// RS-148（审计 2026-09-25）：数字段收紧——此前直接 `u64::parse`，会
/// 接受 `"+1.2.3"`（Rust parse 接受前导 `+`）与 `"01.2.3"`（前导零），
/// 而 schema pattern 拒绝两者——跨语言漂移面：`"+1.2.3"` 与 `"1.2.3"`
/// 解析出同一元组，污染版本比较语义（回滚判定可被 `+` 前缀混淆）。
/// 收紧后：每段必须为 `0` 或无前导零的 ASCII 数字串。
///
/// 预发布（`-rc.1`）与构建元数据（`+build.5`）后缀仍拒绝（RS-125 口径
/// 不变——本函数是版本比较键，只认严格核心版）。
pub fn version_tuple(value: &str) -> Option<(u64, u64, u64)> {
    fn strict_segment(seg: &str) -> Option<u64> {
        let bytes = seg.as_bytes();
        match bytes.first()? {
            // "0" 单独合法；前导零（"01"）拒绝——与 schema (0|[1-9][0-9]*) 一致
            b'0' if bytes.len() == 1 => return Some(0),
            b'0' => return None,
            b'1'..=b'9' => {}
            // "+"/"-"前缀、空白、Unicode 数字（多字节首字节不在 ASCII 区）等
            _ => return None,
        }
        if !bytes.iter().all(|b| b.is_ascii_digit()) {
            return None;
        }
        seg.parse().ok()
    }
    let mut parts = value.split('.');
    let major = strict_segment(parts.next()?)?;
    let minor = strict_segment(parts.next()?)?;
    let patch = strict_segment(parts.next()?)?;
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

    // —— RS-125（审计 2026-09-25）：version_tuple 预发布/溢出——

    #[test]
    fn version_tuple_rejects_prerelease_suffix() {
        // 预发布段参与 patch 解析即失败（fail-closed 拒绝）——
        // 回滚到预发布清单不得通过 (major,minor,patch) 数值比较
        assert_eq!(version_tuple("1.2.3-rc.1"), None);
        assert_eq!(version_tuple("1.2.3-beta"), None);
        assert_eq!(version_tuple("1.2.3+build.5"), None); // 构建元数据同样拒绝
    }

    #[test]
    fn version_tuple_rejects_u64_overflow() {
        // u64 溢出（> 18446744073709551615）必须拒绝——不得饱和或截断
        assert_eq!(version_tuple("99999999999999999999.0.0"), None);
        assert_eq!(version_tuple("1.99999999999999999999.0"), None);
        assert_eq!(version_tuple("1.2.99999999999999999999"), None);
    }

    #[test]
    fn version_tuple_rejects_extra_and_missing_segments() {
        assert_eq!(version_tuple("1.2.3.4"), None); // 四段
        assert_eq!(version_tuple("1.2"), None); // 两段
        assert_eq!(version_tuple("1"), None); // 单段
        assert_eq!(version_tuple(""), None); // 空串
        assert_eq!(version_tuple("a.b.c"), None); // 非数字
    }

    #[test]
    fn version_tuple_rejects_leading_plus_and_leading_zeros() {
        // RS-148：数字段口径与 schema (0|[1-9][0-9]*) 对齐——Rust
        // u64::parse 会接受前导 "+" 与前导零，此前 version_tuple 同样
        // 放行 → "+1.2.3" 与 "1.2.3" 解析出同一元组（版本比较可被
        // 混淆），"01.2.3" 跨语言漂移。收紧后一律拒绝
        assert_eq!(version_tuple("+1.2.3"), None, "前导 + 拒绝");
        assert_eq!(version_tuple("1.+2.3"), None, "段内 + 拒绝");
        assert_eq!(version_tuple("01.2.3"), None, "前导零拒绝");
        assert_eq!(version_tuple("1.02.3"), None);
        assert_eq!(version_tuple("1.2.03"), None);
        assert_eq!(version_tuple("00.0.0"), None);
        // 空白与负数（parse 本就拒绝——锁定不回退）
        assert_eq!(version_tuple(" 1.2.3"), None);
        assert_eq!(version_tuple("1.2.3 "), None);
        assert_eq!(version_tuple("-1.2.3"), None);
        // 全角数字（Unicode 多字节——非 ASCII 数字段）
        assert_eq!(version_tuple("１.2.3"), None);
        // 对照：单个 "0" 段合法，多位无前导零合法
        assert_eq!(version_tuple("0.0.0"), Some((0, 0, 0)));
        assert_eq!(version_tuple("10.20.30"), Some((10, 20, 30)));
    }

    #[test]
    fn version_tuple_accepts_canonical_forms() {
        assert_eq!(version_tuple("0.0.0"), Some((0, 0, 0)));
        assert_eq!(version_tuple("1.2.3"), Some((1, 2, 3)));
        // u64 上边界（不溢出）
        assert_eq!(
            version_tuple("18446744073709551615.0.0"),
            Some((u64::MAX, 0, 0))
        );
    }

    // —— RS-128（审计 2026-09-25）：base64 空串/URL-safe/空白——

    #[test]
    fn base64_empty_string_is_empty_output() {
        // 空串合法输出空 Vec——verify_threshold 侧由 [u8;64] 长度检查兜底
        assert_eq!(base64_decode("").unwrap(), Vec::<u8>::new());
    }

    #[test]
    fn base64_rejects_urlsafe_alphabet() {
        // 标准 base64 表（+ /）——URL-safe 变体字符（- _）不在表内，
        // 必须拒绝（签名仅接受发布链标准编码）
        assert!(base64_decode("a-G_").is_err());
        assert!(base64_decode("-abc").is_err());
    }

    #[test]
    fn base64_rejects_whitespace_contamination() {
        // 空白字符（空格/换行/制表）不得容忍——防止签名载荷被注入截断
        assert!(base64_decode("Zg==\n").is_err());
        assert!(base64_decode(" Zg==").is_err());
        assert!(base64_decode("Zg ==").is_err());
    }

    // —— RS-124（审计 2026-09-25）：verify_threshold 白盒分支——

    use ed25519_dalek::{Signer, SigningKey};

    /// 测试辅助：base64 标准编码（与 base64_decode 对偶）。
    fn b64_encode(data: &[u8]) -> String {
        const TABLE: &[u8] = b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
        let mut out = String::new();
        for chunk in data.chunks(3) {
            let b = [
                chunk[0],
                chunk.get(1).copied().unwrap_or(0),
                chunk.get(2).copied().unwrap_or(0),
            ];
            let n = ((b[0] as u32) << 16) | ((b[1] as u32) << 8) | b[2] as u32;
            out.push(TABLE[(n >> 18) as usize & 63] as char);
            out.push(TABLE[(n >> 12) as usize & 63] as char);
            out.push(if chunk.len() > 1 {
                TABLE[(n >> 6) as usize & 63] as char
            } else {
                '='
            });
            out.push(if chunk.len() > 2 {
                TABLE[n as usize & 63] as char
            } else {
                '='
            });
        }
        out
    }

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
        assert!(
            canonical_unsigned(&serde_json::json!({"version": "1.0.0", "score": 1.5})).is_err()
        );
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
        assert!(
            canonical_unsigned(&serde_json::json!({"a": 1, "b": -5, "c": 18446744073709551615u64}))
                .is_ok()
        );
    }
}

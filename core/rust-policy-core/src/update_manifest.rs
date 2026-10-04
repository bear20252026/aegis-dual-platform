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
    // 审计第六轮延续（2026-10-04）：**按密钥字节去重**。此前只按 keyid 去重
    // （TUF THRESHOLD counting 的字面口径），于是同一把公钥以两个 keyid 登记
    // 即计两票——t-of-n 门槛可被单一密钥凑满。票数是"多少把不同的密钥签了"，
    // 不是"多少条署名记录存在"，故必须按字节去重。
    let mut valid_key_bytes: std::collections::HashSet<[u8; 32]> = Default::default();
    for sig in signatures {
        // RS-197（审计 2026-09-25）：逐签名验证链抽辅助——此前 8 层
        // continue 嵌套内联在循环体（结构/去重/密钥/形态/严格验证逐层
        // 跳过），控制流与验证序不可读。提取后主循环单一职责：
        // 验证成功 → 计入，失败 → 跳过
        if let Some((key_id, key_arr)) =
            try_verify_signature(sig, trusted_keys, canonical_payload, &valid_key_ids)
        {
            if !valid_key_bytes.insert(key_arr) {
                continue; // 同一把密钥换名重复计票——只算一票
            }
            valid_key_ids.insert(key_id);
        }
    }
    valid_key_ids.len() >= threshold
}

/// RS-197：单签名验证链——结构 → 重复 keyid → 密钥存在 → 签名字段 →
/// base64 → 密钥/签名长度 → 公钥解析 → 严格验证；任一环节失败返回 None。
/// 重复 keyid 提前短路（TUF THRESHOLD counting——与 P0-04 一致，只计一次）；
/// 返回 (keyid, 公钥字节) 以便调用方**另按字节去重**（审计第六轮延续）。
fn try_verify_signature(
    sig: &serde_json::Value,
    trusted_keys: &std::collections::HashMap<String, Vec<u8>>,
    canonical_payload: &[u8],
    already_valid: &std::collections::HashSet<String>,
) -> Option<(String, [u8; 32])> {
    let obj = sig.as_object()?;
    let key_id = obj.get("key_id").and_then(|v| v.as_str())?.to_string();
    if already_valid.contains(&key_id) {
        return None; // 重复 keyid 只计一次（TUF THRESHOLD counting——与 P0-04 一致）
    }
    let key_bytes = trusted_keys.get(&key_id)?;
    let sig_str = obj.get("sig").and_then(|v| v.as_str())?;
    let sig_bytes = base64_decode(sig_str).ok()?;
    // ed25519-dalek 2.x：from_bytes 期望固定长度数组（[u8; 32]/[u8; 64]——
    // E0308 修复——公钥/签名长度校验——try_into）
    let key_arr = <[u8; 32]>::try_from(key_bytes.as_slice()).ok()?;
    let sig_arr = <[u8; 64]>::try_from(sig_bytes.as_slice()).ok()?;
    // 审计第六轮延续（2026-10-04）：显式拒退化信任锚（见 is_degenerate_public_key）
    if is_degenerate_public_key(&key_arr) {
        return None;
    }
    // ed25519-dalek 2.x：VerifyingKey::from_bytes 返回 Result；Signature::
    // from_bytes 直接返回 Signature（非 Result——2.x API）
    let verifying_key = VerifyingKey::from_bytes(&key_arr).ok()?;
    let signature = Signature::from_bytes(&sig_arr);
    // verify_strict：严格验证——防 malleability（Houseme 生产实践）
    verifying_key
        .verify_strict(canonical_payload, &signature)
        .ok()?;
    Some((key_id, key_arr))
}

/// 退化公钥筛除（审计第六轮延续 2026-10-04）——**限定口径，不假装全覆盖**。
///
/// 若 A 为单位元则验证方程 [s]B = R + [k]A 退化为 [s]B = R，攻击者可对任意
/// 消息造出通过验证的"签名"；阶 2 点（y = p-1）同理使 [k]A 落在低阶子群里。
/// 一个错配的信任锚槽位即可把 t-of-n 降为"无需 quorum"。
///
/// 实测：在本仓钉住的 ed25519-dalek 3.x 上，按上述构造的 forged 签名已被
/// `verify_strict` 拒绝（见 degenerate_anchor_tests 的 tripwire），因此**这不是
/// 在修一个已可利用的漏洞**，而是把"不依赖第三方内部行为"的判定显式落到核心：
/// 换版/换 provider 时不该悄悄退化。
///
/// 只做无需曲线运算即可判定的三种编码（压缩格式 = 小端 y，byte31 高位为 x 符号）：
///   · y = 1  → 01 00 … 00            （单位元）
///   · y = 0  → 00 00 … 00            （不在曲线上，from_bytes 亦会拒，双保险）
///   · y = p-1→ ec FF … FF 7F          （阶 2 点）
/// 完整的 8 阶挠子筛除需要 cofactor 乘法（curve25519 点运算），而把
/// curve25519-dalek 提为直接依赖会改动 Cargo.lock 供给面——不在本轮范围，
/// 已作为残留登记（keyid 与密钥字节的绑定同理，需信任锚供给格式变更）。
fn is_degenerate_public_key(key: &[u8; 32]) -> bool {
    // 符号位（byte31 bit7）不影响 y 值，比较时一律掩掉
    let y_top = key[31] & 0x7f;
    // y = 1
    if key[0] == 1 && key[1..31].iter().all(|&b| b == 0) && y_top == 0 {
        return true;
    }
    // y = 0
    if key[..31].iter().all(|&b| b == 0) && y_top == 0 {
        return true;
    }
    // y = p - 1 = 2^255 - 20 → LE: EC 后接 29 个 FF，末字节 7F
    if key[0] == 0xec && key[1..31].iter().all(|&b| b == 0xff) && y_top == 0x7f {
        return true;
    }
    false
}

/// 更新清单版本守卫（审计第六轮 2026-10-03/04）。
///
/// 存在理由：`verify_threshold` 只回答"签名是否够数"，完全不看版本；全仓唯一
/// 的降级判定在 `release/update_verifier.py`（离线发布链验证器），设备侧运行时
/// 不校验更新——于是一份**签名有效但版本更旧**的清单可被重放用于降级到已知
/// 有缺陷的策略。本入口把"版本单调"折进验证路径，与阈值判定同等 fail-closed：
///   ① 必须严格高于 `highest_accepted`（相等即拒——同版本重放）；
///   ② 若清单自带 `min_version` 下限，必须 ≥ 该下限；
///   ③ 任一版本串不可解析 → 拒（解析失败不等于放行）。
/// 调用方须传入**已持久化**的最高接受版本；传 "0.0.0" 表示冷启动无历史。
pub fn accept_update_version(
    manifest_version: &str,
    highest_accepted: &str,
    min_version: Option<&str>,
) -> bool {
    let Some(current) = version_tuple(manifest_version) else {
        return false;
    };
    let Some(accepted) = version_tuple(highest_accepted) else {
        return false;
    };
    if current <= accepted {
        return false;
    }
    if let Some(floor) = min_version {
        // 下限不可解析：按 fail-closed 拒绝（不可解析的清单不得被接受）
        let Some(floor_tuple) = version_tuple(floor) else {
            return false;
        };
        if current < floor_tuple {
            return false;
        }
    }
    true
}

/// 基础 base64 解码（纯函数——无外部 crate 依赖的简版；生产用 base64 crate——
/// 蓝图最小依赖取舍：此实现仅试点，后续迁移 base64 crate）。
/// 审计整改（2026-09-07）：严格校验——padding 只能在末尾、`=` 之后不得再有
/// 数据、数据长度模 4 不得为 1、尾部残留非零 bit 拒绝。
/// RS-224（2026-09-26 审计）：规范长度对齐 Python b64decode——
/// len % 4 != 0 一律拒绝（"Zg" 无 padding 与 "Zg=" len 3 此前均放行，
/// 签名编码严格性两端不一致 = 跨语言漂移面）；padding 仅允许尾部
/// "=" / "=="（由首个 '=' 的 index%4 ∈ {2,3} 前置约束共同保证）。
fn base64_decode(input: &str) -> Result<Vec<u8>, ()> {
    const TABLE: &[u8] = b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
    let bytes = input.as_bytes();
    // RS-224：非规范长度（无 padding 短串 / 残缺 padding）整体拒绝
    if !bytes.len().is_multiple_of(4) {
        return Err(());
    }
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

/// 基础 base64 标准编码（与 [`base64_decode`] 对偶——纯函数简版）。
///
/// RS-306（2026-10-02 审计）：共享单源——此前本实现以两份逐字节相同的
/// 副本分别内联在 update_manifest 单元测试模块与 tests/vectors.rs 集成
/// 测试（同一编码格式两处维护，漂移面）。集成测试（tests/ 目录）按外部
/// 消费者编译，无法访问 crate 私有/`#[cfg(test)]` 项，故以 pub 导出为
/// 单一事实源（生产解码器 base64_decode 的逆函数，pub 是测试共享的
/// 必要取舍）。
pub fn b64_encode(data: &[u8]) -> String {
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
                                              // RS-224：规范长度——"Zg"（无 padding）此前放行，现对齐 Python
                                              // b64decode 一律拒绝（签名仅接受规范编码）
        assert!(base64_decode("Zg").is_err());
        assert!(base64_decode("Zg=").is_err()); // 残缺 padding（len 3）
        assert!(base64_decode("Zg==").is_ok()); // 规范形态
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

    // RS-306（2026-10-02 审计）：b64_encode 已收敛为模块级共享单源
    //（super::b64_encode 经 use super::* 可见）——本模块此前内联的
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
        assert!(canonical_unsigned(
            &serde_json::json!({"a": 1, "b": -5, "c": 18446744073709551615u64})
        )
        .is_ok());
    }
}

#[cfg(test)]
mod degenerate_anchor_tests {
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
}

#[cfg(test)]
mod version_gate_tests {
    use super::accept_update_version;

    #[test]
    fn strictly_higher_version_is_accepted() {
        assert!(accept_update_version("1.0.1", "1.0.0", None));
        assert!(accept_update_version("2.0.0", "1.9.9", None));
        // 语义化数值比较而非字符串比较："10.0.0" > "9.0.0"
        assert!(accept_update_version("10.0.0", "9.0.0", None));
    }

    #[test]
    fn equal_and_older_are_rejected() {
        // 相等即拒——同版本重放不得被当作一次有效更新
        assert!(!accept_update_version("1.0.0", "1.0.0", None));
        assert!(!accept_update_version("0.9.0", "1.0.0", None));
        assert!(!accept_update_version("1.0.0", "1.0.1", None));
    }

    #[test]
    fn min_version_floor_is_enforced() {
        assert!(accept_update_version("1.5.0", "1.0.0", Some("1.2.0")));
        assert!(!accept_update_version("1.1.0", "1.0.0", Some("1.2.0")));
    }

    #[test]
    fn unparseable_version_fails_closed() {
        // 解析失败 ≠ 放行（与全核 fail-closed 口径一致）
        for bad in [
            "",
            "1",
            "1.",
            "v1.2.3",
            "1.2.3.4",
            "abc",
            "1.2.x",
            "0x1.0.0",
            "1.2.3-beta",
        ] {
            assert!(
                !accept_update_version(bad, "0.0.0", None),
                "不可解析版本 {bad} 必须拒绝"
            );
        }
        assert!(!accept_update_version("9.9.9", "not-a-version", None));
        assert!(!accept_update_version("9.9.9", "0.0.0", Some("???")));
    }

    #[test]
    fn u64_sized_component_does_not_overflow_reject_incorrectly() {
        // version_tuple 对越界分量的处置即 fail-closed（RS 既有测试覆盖），
        // 此处锁定门不 panic
        assert!(!accept_update_version(
            "99999999999999999999999.0.0",
            "1.0.0",
            None
        ));
    }
}

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
mod tests;

#[cfg(test)]
mod degenerate_anchor_tests;

#[cfg(test)]
mod version_gate_tests;

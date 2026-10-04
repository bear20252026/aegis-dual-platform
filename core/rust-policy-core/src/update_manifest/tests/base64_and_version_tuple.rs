use super::super::*;

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

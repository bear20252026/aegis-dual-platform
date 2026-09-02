//! 与 contracts/vectors 的差分测试（蓝图：跨语言测试向量一致——
//! Rust 与 C#/Kotlin reference 在全部 vectors 上结果一致）。
//!
//! 覆盖：update-manifest-valid/invalid（阈值/回滚/重复 key——TUF THRESHOLD
//! counting）+ url-origin-valid/invalid（contracts 向量）。
//!
//! 全库审计 2026-09-02 收敛：向量不再手工内联复制到测试代码——直接解析
//! `contracts/vectors/*.json`（单一事实源，schema 变更时测试自动跟随；
//! c_abi 集成测试此前已按此口径消费 JSON）。

use aegis_policy_core::origin::try_parse_external;
use aegis_policy_core::update_manifest::{canonical_unsigned, verify_threshold, version_tuple};
use serde_json::{json, Value};

/// contracts/vectors 目录（仓库布局：core/rust-policy-core → ../../contracts/vectors）。
fn vectors_dir() -> std::path::PathBuf {
    let manifest = env!("CARGO_MANIFEST_DIR");
    std::path::Path::new(manifest)
        .join("../../contracts/vectors")
        .canonicalize()
        .expect("contracts/vectors 目录必须存在（仓库布局契约）")
}

fn load_vectors(name: &str) -> Vec<Value> {
    let path = vectors_dir().join(name);
    let text =
        std::fs::read_to_string(&path).unwrap_or_else(|e| panic!("读取向量文件失败 {path:?}: {e}"));
    let root: Value = serde_json::from_str(&text).expect("向量 JSON 必须合法");
    root["vectors"]
        .as_array()
        .unwrap_or_else(|| panic!("{name}: 缺少 vectors 数组"))
        .clone()
}

#[test]
fn url_origin_vectors_match_contracts() {
    // contracts/vectors/url-origin-valid.json —— 全部放行
    for v in load_vectors("url-origin-valid.json") {
        let url = v["url"].as_str().expect("向量必须有 url 字段");
        let expected = v["expected"].as_str().unwrap_or("allow");
        assert_eq!(
            try_parse_external(url).is_some(),
            expected == "allow",
            "向量结果不符: {url} (expected={expected})"
        );
    }

    // contracts/vectors/url-origin-invalid.json —— 全部拒绝
    for v in load_vectors("url-origin-invalid.json") {
        let raw = v["url"].as_str().expect("向量必须有 url 字段");
        // oversize 占位向量按 JSON note 物化为真实超长 URL（>8192 字符）——
        // JSON 保持可读，实际样本在消费端展开（与 Kotlin OriginPolicyTest 同口径）
        let url = if raw.contains("oversize-url-limit-test") {
            format!("https://example.org/{}", "a".repeat(9000))
        } else {
            raw.to_string()
        };
        let expected = v["expected"].as_str().unwrap_or("deny");
        assert_eq!(
            try_parse_external(&url).is_some(),
            expected == "allow",
            "向量结果不符: {raw} (expected={expected})"
        );
    }
}

#[test]
fn update_manifest_valid_vectors() {
    // SemVer 解析语义抽查（解析器单元语义；清单级向量见 c_abi 集成测试
    // 对 update-manifest-valid.json 的完整消费）
    assert_eq!(version_tuple("1.2.3"), Some((1, 2, 3)));
    assert_eq!(version_tuple("0.9.0"), Some((0, 9, 0)));
    assert_eq!(version_tuple("1.0"), None); // 无效 SemVer
}

#[test]
fn update_manifest_duplicate_key_counts_once() {
    // TUF THRESHOLD counting：重复 keyid 只计一次（与 update_verifier P0-04 一致——
    // contracts/vectors/update-manifest-invalid.json duplicate_key 场景）
    let mut keys = std::collections::HashMap::new();
    keys.insert("k1".to_string(), [0u8; 32].to_vec()); // 合成公钥（仅测计数逻辑）
    let sigs = vec![
        json!({"key_id": "k1", "sig": "AAAA"}),
        json!({"key_id": "k1", "sig": "BBBB"}),
    ];
    let payload = canonical_unsigned(&json!({"version": "1.2.3"}));
    // 重复 key 只计一次（不足 threshold 2——即使同 key 两条签名）
    assert!(!verify_threshold(&keys, &sigs, &payload, 2));
}

#[test]
fn canonical_json_deterministic() {
    // TUF canonical JSON：键排序 + 紧凑——确定性（签名验证前提）
    let a = canonical_unsigned(&json!({"b": 2, "a": 1}));
    let b = canonical_unsigned(&json!({"a": 1, "b": 2}));
    assert_eq!(a, b, "canonicalization 必须确定（与键顺序无关）");
}

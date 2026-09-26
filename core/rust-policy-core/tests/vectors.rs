//! 与 contracts/vectors 的差分测试（蓝图：跨语言测试向量一致——
//! Rust 与 C#/Kotlin reference 在全部 vectors 上结果一致）。
//!
//! 覆盖：update-manifest-valid/invalid（阈值/回滚/重复 key——TUF THRESHOLD
//! counting）+ url-origin-valid/invalid（contracts 向量）。
//!
//! 全库审计 2026-09-02 收敛：向量不再手工内联复制到测试代码——直接解析
//! `contracts/vectors/*.json`（单一事实源，schema 变更时测试自动跟随；
//! c_abi 集成测试此前已按此口径消费 JSON）。

use aegis_policy_core::decision::AuthorizedAction;
use aegis_policy_core::matcher::{glob_match, glob_subsumes};
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

// ===== RS-147（审计 2026-09-25）：action / glob 跨语言向量接入 =====
// （此前 action-valid/invalid.json 仅由 Python validate_vector_schemas.py
// 消费，Rust 侧零覆盖——契约数据面与 Rust 结构面之间的字段映射无锁定）

/// Action schema 词表（contracts/schemas/action.schema.json enum——Rust
/// 侧同款词表锁定；漂移即本测试失败）。
const ACTION_METHODS: &[&str] = &["GET", "POST", "PUT", "DELETE", "NAVIGATE", "DOWNLOAD"];

#[test]
fn action_valid_vectors_map_to_authorized_action_fields() {
    // valid 向量：10 必填字段与 AuthorizedAction 字段面一一对应——
    // 字段名/词表/origin 口径漂移即失败。expires_at 表示差异（向量
    // ISO8601 ↔ Rust u64 epoch）由 schema 锁定格式、此处锁定字段存在性，
    // 映射构造取固定远期值
    for v in load_vectors("action-valid.json") {
        let a = &v["action"];
        let note = v["note"].as_str().unwrap_or("unnamed");
        let session_id = a["session_id"].as_str().expect("缺 session_id");
        let tab_id = a["tab_id"].as_str().expect("缺 tab_id");
        let document_generation = a["document_generation"].as_u64().expect("缺代际");
        let origin = a["origin"].as_str().expect("缺 origin");
        let method = a["method"].as_str().expect("缺 method");
        let canonical_parameters = a["canonical_parameters"].as_str().expect("缺参数");
        let scope = a["scope"].as_str().expect("缺 scope");
        assert!(a.get("expires_at").is_some(), "向量 {note}: 缺 expires_at");
        let nonce = a["nonce"].as_str().expect("缺 nonce");
        let policy_version = a["policy_version"].as_str().expect("缺版本");

        // method 词表（schema enum 同款）
        assert!(
            ACTION_METHODS.contains(&method),
            "向量 {note}: method {method} 不在 Action 词表"
        );
        // origin 归一层放行（schema pattern ^https?:// 对应 Rust 归一口径）
        assert!(
            try_parse_external(origin).is_some(),
            "向量 {note}: origin {origin} 必须过归一层"
        );
        // 字段面映射：构造 AuthorizedAction 成功且逐字段一致
        let action = AuthorizedAction {
            session_id: session_id.into(),
            tab_id: tab_id.into(),
            document_generation,
            origin: origin.into(),
            method: method.into(),
            canonical_parameters: canonical_parameters.into(),
            scope: scope.into(),
            expires_at: 4_102_444_800, // 2100-01-01T00:00:00Z（远期占位）
            nonce: nonce.into(),
            policy_version: policy_version.into(),
            explanation: String::new(), // 审计扩展字段——schema 数据面不含
        };
        assert_eq!(action.session_id, session_id);
        assert_eq!(action.tab_id, tab_id);
        assert_eq!(action.document_generation, document_generation);
        assert_eq!(action.origin, origin);
        assert_eq!(action.method, method);
        assert_eq!(action.nonce, nonce);
    }
}

#[test]
fn action_invalid_vectors_match_rust_side_rules() {
    // invalid 向量：schema 拒绝的形态中，Rust 侧存在同款机制的条目逐一
    // 对齐；纯 schema 专属规则（additionalProperties / minLength）显式
    // 登记为「Rust 侧透传」——数据结构无构造校验，拒绝发生在消费层
    // （空 nonce → consume_nonce RS-034；空 session_id → FFI create_session
    // RS-159），此处锁定机制性规则不回退
    for v in load_vectors("action-invalid.json") {
        let a = &v["action"];
        let note = v["note"].as_str().unwrap_or("unnamed");
        // 1) origin 非 http(s)（file: 注入）——origin 归一层同款拒绝
        if let Some(origin) = a["origin"].as_str() {
            if !origin.starts_with("http://") && !origin.starts_with("https://") {
                assert!(
                    try_parse_external(origin).is_none(),
                    "向量 {note}: origin 归一层必须拒绝 {origin}"
                );
            }
        }
        // 2) document_generation 负数——Rust u64 同样不可表示（serde 面
        //    对齐：u64 反序列化拒绝负值）。仅对负值形态断言（合法 0 值
        //    反序列化应成功——不误伤）；edition 2024 下 gen 是保留字，
        //    绑定名取 generation
        if let Some(generation) = a["document_generation"].as_i64() {
            if generation < 0 {
                assert!(
                    serde_json::from_value::<u64>(json!(generation)).is_err(),
                    "向量 {note}: 负代际必须被 u64 反序列化拒绝"
                );
            }
        }
        // 3) method 词表越界/小写——按向量形态分派：越界方法不在词表；
        //    小写变体不等于词表项（大小写敏感）但可 ASCII 归一匹配
        if let Some(method) = a["method"].as_str() {
            let in_list = ACTION_METHODS.contains(&method);
            match method {
                "PATCH" => assert!(!in_list, "向量 {note}: PATCH 必须在词表外"),
                "get" => {
                    assert!(!in_list, "向量 {note}: 词表大小写敏感");
                    assert!(
                        ACTION_METHODS
                            .iter()
                            .any(|m| m.eq_ignore_ascii_case(method)),
                        "get 应是词表项的大小写变体"
                    );
                }
                _ => {} // 其余向量因非 method 规则失效——method 本身在词表内
            }
        }
        // 4) 缺 nonce / 空 session_id / 额外字段——纯 schema 规则
        //    （required / minLength / additionalProperties），Rust 数据结构
        //   无构造校验（透传），拒绝发生在消费层：空 nonce →
        //    consume_nonce 拒绝（RS-034，broker 单元测试锁定）；空
        //    session_id → FFI create_session 拒绝（RS-159，ffi 测试锁定）
    }
}

#[test]
fn glob_vectors_match_contracts() {
    // RS-147：glob-match.json——glob_match / glob_subsumes 跨语言向量。
    // 断言字段遵循 contracts 向量协议（verify_vectors.py PY-064）：顶层
    // expected ∈ {allow, deny}——allow = 期望匹配/覆盖成立，deny = 不成立。
    // 匹配向量（pattern/text）与覆盖向量（a/b）共用 vectors 数组，按字段
    // 形态分派
    let vectors = load_vectors("glob-match.json");
    assert!(!vectors.is_empty(), "glob 向量不得为空");
    let mut matched_count = 0usize;
    let mut subsumed_count = 0usize;
    for v in &vectors {
        let note = v["note"].as_str().unwrap_or("unnamed");
        let expected = match v["expected"].as_str() {
            Some("allow") => true,
            Some("deny") => false,
            other => panic!("向量 {note}: expected 非法（{other:?}）——协议值域 allow/deny"),
        };
        if let (Some(pattern), Some(text)) = (v["pattern"].as_str(), v["text"].as_str()) {
            let flat = v["flat"].as_bool().unwrap_or(false);
            assert_eq!(
                glob_match(pattern, text, flat),
                expected,
                "glob_match 向量不符: {note} ({pattern:?} vs {text:?}, flat={flat})"
            );
            matched_count += 1;
        }
        if let (Some(a), Some(b)) = (v["a"].as_str(), v["b"].as_str()) {
            let flat = v["flat"].as_bool().unwrap_or(false);
            assert_eq!(
                glob_subsumes(a, b, flat),
                expected,
                "glob_subsumes 向量不符: {note} ({a:?} ⊇ {b:?}, flat={flat})"
            );
            subsumed_count += 1;
        }
    }
    assert!(
        matched_count >= 20 && subsumed_count >= 7,
        "向量覆盖面收缩（match={matched_count}, subsume={subsumed_count}）"
    );
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
    let payload = canonical_unsigned(&json!({"version": "1.2.3"})).unwrap();
    // 重复 key 只计一次（不足 threshold 2——即使同 key 两条签名）
    assert!(!verify_threshold(&keys, &sigs, &payload, 2));
}

#[test]
fn canonical_json_deterministic() {
    // TUF canonical JSON：键排序 + 紧凑——确定性（签名验证前提）
    let a = canonical_unsigned(&json!({"b": 2, "a": 1})).unwrap();
    let b = canonical_unsigned(&json!({"a": 1, "b": 2})).unwrap();
    assert_eq!(a, b, "canonicalization 必须确定（与键顺序无关）");
}

#[test]
fn canonical_json_matches_python_golden_vectors() {
    // 批次4-3（全面审计 2026-09-04）：与发布链权威实现
    // release/update_verifier.py::canonical_unsigned 的字节级一致性——
    // golden 向量（contracts/vectors/update-manifest-canonical.json）由
    // Python 侧生成、此处断言 Rust 输出逐字节相同。覆盖：常规清单 /
    // 特殊字符（引号/反斜杠/换行/控制字符/中文）/ 顶层 signatures 剔除
    // （嵌套 signatures 保留）。
    let vectors = load_vectors("update-manifest-canonical.json");
    assert!(
        !vectors.is_empty(),
        "update-manifest-canonical 向量不得为空"
    );
    for v in &vectors {
        let name = v["name"].as_str().unwrap_or("unnamed");
        let expected_hex = v["expected_canonical_hex"].as_str().unwrap_or_else(|| {
            panic!("向量 {name} 缺少 expected_canonical_hex");
        });
        let actual = canonical_unsigned(&v["manifest"]).unwrap_or_else(|_| {
            panic!("golden 向量 {name} canonical 失败（含浮点？RS-127 fail-closed）");
        });
        let actual_hex: String = actual.iter().map(|b| format!("{b:02x}")).collect();
        assert_eq!(
            actual_hex, expected_hex,
            "canonical 字节与 Python 权威实现不一致: {name}"
        );
    }
}

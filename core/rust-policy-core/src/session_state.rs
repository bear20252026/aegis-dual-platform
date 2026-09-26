/*
 * session_state.rs — 会话状态序列化（照搬 Omni Browser OmniSessionState.kt 本地化适配）。
 *
 * 原始版权：Omni Browser - Copyright (C) 2026 RebelRoot Ltd
 * 原始许可：GNU General Public License v3.0
 * 来源：https://github.com/REBEL-ROOT/omni-browser
 * 改动：将 Kotlin data class 序列化模式翻译为 Rust，适配 Aegis 架构（零外部依赖）。
 *
 * 设计意图（照搬 Omni Browser 原注释）：
 * 此类与平台内部序列化格式（WebView2/GeckoView）解耦，仅存储原始状态字节
 * 加浏览器级元数据，确保恢复不依赖特定内核实现。
 */

use std::collections::HashMap;

/// 当前 schema 版本（向前/向后兼容）。
pub const CURRENT_SCHEMA_VERSION: u32 = 1;

/// 单个标签页的可恢复状态（照搬 Omni Browser OmniSessionState）。
#[derive(Debug, Clone, PartialEq)]
pub struct SessionState {
    /// Schema 版本（向前/向后兼容）。
    pub schema_version: u32,
    /// 标签页标识符（匹配 TabState.id）。
    pub tab_id: String,
    /// 序列化的平台内核会话状态字节（对 Aegis 透明）。
    pub session_state_bytes: Vec<u8>,
    /// 浏览器级元数据（不依赖内核实现）。
    pub metadata: TabMetadata,
    /// 写入时间戳（Unix 毫秒）。
    pub timestamp: u64,
}

/// 标签页元数据（照搬 Omni Browser TabMetadata）。
#[derive(Debug, Clone, PartialEq)]
pub struct TabMetadata {
    pub title: String,
    pub url: String,
    pub is_incognito: bool,
    pub last_active_time: u64,
    pub can_go_back: bool,
    pub can_go_forward: bool,
}

impl SessionState {
    /// 从 JSON 字符串反序列化（照搬 Omni Browser fromJson）。
    /// 审计整改（2026-09-07）：对字段长度做上限、拒绝未知 schema 版本——
    /// 此前反序列化不校验字段长度/schema，超长输入可驱动无界分配（内存 DoS）。
    pub fn from_json(json: &str) -> Option<Self> {
        const MAX_TAB_ID_LEN: usize = 256;
        const MAX_TITLE_LEN: usize = 4096;
        const MAX_URL_LEN: usize = 8192;
        const MAX_STATE_BYTES: usize = 512 * 1024;
        // 解析前总长上限——此前 serde_json 先全量解析任意大小输入再逐字段
        // 限长，超长 JSON 可先驱动无界内存分配（内存 DoS）。字段上限之和
        // 远小于 1MB，超限输入不可能合法。
        const MAX_JSON_BYTES: usize = 1024 * 1024;
        if json.len() > MAX_JSON_BYTES {
            return None;
        }

        let map: HashMap<String, serde_json::Value> = serde_json::from_str(json).ok()?;
        let schema_version = map.get("schemaVersion")?.as_u64()? as u32;
        // 仅接受当前 schema（拒绝未来/未知版本，避免向后兼容盲区）
        if schema_version != CURRENT_SCHEMA_VERSION {
            return None;
        }
        let tab_id = map.get("tabId")?.as_str()?.to_string();
        if tab_id.len() > MAX_TAB_ID_LEN {
            return None;
        }
        let b64 = map.get("sessionStateBytes")?.as_str()?;
        let session_state_bytes = hex_decode(b64)?;
        if session_state_bytes.len() > MAX_STATE_BYTES {
            return None;
        }
        let meta = map.get("metadata")?;
        let title = meta.get("title")?.as_str()?;
        let url = meta.get("url")?.as_str()?;
        if title.len() > MAX_TITLE_LEN || url.len() > MAX_URL_LEN {
            return None;
        }
        let metadata = TabMetadata {
            title: title.to_string(),
            url: url.to_string(),
            // RS-110（审计 2026-09-25）：isIncognito 必填且必须为 bool——
            // 此前缺失/类型损坏静默降级 false（普通标签），无痕标签恢复成
            // 普通标签 = 隐私语义静默丢失。fail-closed：缺即拒恢复。
            is_incognito: meta.get("isIncognito")?.as_bool()?,
            last_active_time: meta.get("lastActiveTime")?.as_u64().unwrap_or(0),
            can_go_back: meta.get("canGoBack")?.as_bool().unwrap_or(false),
            can_go_forward: meta.get("canGoForward")?.as_bool().unwrap_or(false),
        };
        let timestamp = map.get("timestamp")?.as_u64().unwrap_or(0);
        Some(Self {
            schema_version,
            tab_id,
            session_state_bytes,
            metadata,
            timestamp,
        })
    }

    /// 序列化为 JSON 字符串（照搬 Omni Browser toJson）。
    /// 经 serde_json 构造——此前 format! 手拼零转义，页面标题（攻击者可控）
    /// 含 `"`/`\`/控制字符即产生非法 JSON 或字段注入，破坏会话恢复链路。
    pub fn to_json(&self) -> String {
        let metadata = serde_json::json!({
            "title": self.metadata.title,
            "url": self.metadata.url,
            "isIncognito": self.metadata.is_incognito,
            "lastActiveTime": self.metadata.last_active_time,
            "canGoBack": self.metadata.can_go_back,
            "canGoForward": self.metadata.can_go_forward,
        });
        serde_json::json!({
            "schemaVersion": self.schema_version,
            "tabId": self.tab_id,
            "sessionStateBytes": hex_encode(&self.session_state_bytes),
            "metadata": metadata,
            "timestamp": self.timestamp,
        })
        .to_string()
    }
}

/// hex 编解码（RS-186：收敛至 util 单源——此前本文件私有一份，与
/// util::hex_digit 形成"同格式多实现"漂移面）。
use crate::util::{hex_decode, hex_encode};

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn round_trip_json() {
        let state = SessionState {
            schema_version: CURRENT_SCHEMA_VERSION,
            tab_id: "tab-42".into(),
            session_state_bytes: vec![0x01, 0x02, 0xFF],
            metadata: TabMetadata {
                title: "Test Page".into(),
                url: "https://example.com".into(),
                is_incognito: false,
                last_active_time: 1700000000000,
                can_go_back: true,
                can_go_forward: false,
            },
            timestamp: 1700000000000,
        };
        let json = state.to_json();
        let restored = SessionState::from_json(&json).unwrap();
        assert_eq!(restored.tab_id, "tab-42");
        assert_eq!(restored.session_state_bytes, vec![0x01, 0x02, 0xFF]);
        assert_eq!(restored.metadata.title, "Test Page");
    }

    #[test]
    fn hex_round_trip() {
        let data = b"hello world 1234567890!@#$%";
        let encoded = hex_encode(data);
        let decoded = hex_decode(&encoded).unwrap();
        assert_eq!(decoded, data);
    }

    #[test]
    fn schema_version_default() {
        let state = SessionState {
            schema_version: CURRENT_SCHEMA_VERSION,
            tab_id: "t1".into(),
            session_state_bytes: vec![],
            metadata: TabMetadata {
                title: String::new(),
                url: String::new(),
                is_incognito: false,
                last_active_time: 0,
                can_go_back: false,
                can_go_forward: false,
            },
            timestamp: 0,
        };
        assert_eq!(state.schema_version, 1);
    }

    #[test]
    fn malicious_title_round_trips_without_injection() {
        // RS-044 回归：页面标题（攻击者可控）含引号/反斜杠/换行/控制字符/
        // 字段注入载荷——serde_json 构造保证逐字节往返，不产生非法 JSON
        // 或额外字段；format! 手拼时代这些输入会破坏会话恢复链路
        let payload = r#"He said "hi" \ </script>{"admin":true}"#;
        let with_control = format!("{payload}\u{0007}\u{001B}[31m\n\t");
        let state = SessionState {
            schema_version: CURRENT_SCHEMA_VERSION,
            tab_id: "t".into(),
            session_state_bytes: vec![0xDE, 0xAD],
            metadata: TabMetadata {
                title: with_control,
                url: "https://evil.example/\"?x=1".into(),
                is_incognito: false,
                last_active_time: 0,
                can_go_back: false,
                can_go_forward: false,
            },
            timestamp: 42,
        };
        let json = state.to_json();
        // 输出必须是合法 JSON——手拼零转义时代这里直接解析失败
        let parsed: serde_json::Value =
            serde_json::from_str(&json).expect("恶意标题经 serde_json 构造后必须是合法 JSON");
        // 注入载荷不得逃出 title 字段成为顶层字段
        assert!(parsed.get("admin").is_none(), "字段注入不得产生顶层字段");
        // 逐字段往返一致
        assert_eq!(SessionState::from_json(&json), Some(state));
    }

    #[test]
    fn malicious_title_json_with_escaped_quotes_rejects_injected_fields() {
        // RS-044 补充：构造已含 \" 转义的 JSON 输入（模拟攻击者直接喂历史
        // 恢复文件）——转义后的引号只作用于 title 字符串内部，不得拆包
        let json = r#"{"schemaVersion":1,"tabId":"t","sessionStateBytes":"00","metadata":{"title":"a\",\"admin\":true,\"b":"url":"","isIncognito":false},"timestamp":0}"#;
        if let Some(state) = SessionState::from_json(json) {
            // 即便解析成功，title 也只能是原始字符串字面量——不得变成新字段
            assert!(state.metadata.title.contains("admin"));
            assert!(!state.metadata.title.is_empty());
        }
    }

    fn state_json(tab_id: &str, title: &str, url: &str, hex_bytes: &str) -> String {
        format!(
            r#"{{"schemaVersion":{},"tabId":"{}","sessionStateBytes":"{}","metadata":{{"title":"{}","url":"{}","isIncognito":false,"lastActiveTime":0,"canGoBack":false,"canGoForward":false}},"timestamp":0}}"#,
            CURRENT_SCHEMA_VERSION, tab_id, hex_bytes, title, url
        )
    }

    #[test]
    fn rejects_unknown_schema_version() {
        let json = r#"{"schemaVersion":999,"tabId":"t","sessionStateBytes":"00","metadata":{"title":"","url":"","isIncognito":false,"lastActiveTime":0,"canGoBack":false,"canGoForward":false},"timestamp":0}"#;
        assert!(SessionState::from_json(json).is_none());
    }

    #[test]
    fn schema_version_zero_and_two_rejected() {
        // RS-172：前向兼容策略此前只有 999 一个用例——版本边界 0（历史
        // 过去版本）与 2（紧邻未来版本）必须同样拒绝。策略口径：仅接受
        // CURRENT_SCHEMA_VERSION=1，未来版本在实现其迁移语义前一律
        // fail-closed（盲区恢复比静默丢字段安全）
        let base = |version: u32| {
            format!(
                r#"{{"schemaVersion":{version},"tabId":"t","sessionStateBytes":"00","metadata":{{"title":"","url":"","isIncognito":false,"lastActiveTime":0,"canGoBack":false,"canGoForward":false}},"timestamp":0}}"#
            )
        };
        assert!(
            SessionState::from_json(&base(0)).is_none(),
            "schemaVersion=0（过去版本）必须拒绝"
        );
        assert!(
            SessionState::from_json(&base(2)).is_none(),
            "schemaVersion=2（未来版本）必须拒绝"
        );
        assert!(
            SessionState::from_json(&base(1)).is_some(),
            "当前版本 1 必须接受"
        );
    }

    #[test]
    fn rejects_oversized_state_bytes() {
        let big = "ff".repeat(600 * 1024); // > 512KB 上限
        assert!(SessionState::from_json(&state_json("t", "t", "u", &big)).is_none());
    }

    #[test]
    fn rejects_oversized_json_before_parse() {
        // RS-009 回归：解析前总长上限——1MB 垃圾输入直接拒绝（不进 serde）
        let junk = "x".repeat(1024 * 1024 + 1);
        assert!(SessionState::from_json(&junk).is_none());
    }

    #[test]
    fn accepts_json_within_total_cap() {
        // 正常尺寸输入不受上限影响（往返可用）
        let state = SessionState {
            schema_version: CURRENT_SCHEMA_VERSION,
            tab_id: "t".into(),
            session_state_bytes: vec![0xAB; 4096],
            metadata: TabMetadata {
                title: "t".into(),
                url: "https://e.com".into(),
                is_incognito: false,
                last_active_time: 0,
                can_go_back: false,
                can_go_forward: false,
            },
            timestamp: 1,
        };
        let json = state.to_json();
        assert_eq!(SessionState::from_json(&json), Some(state));
    }

    #[test]
    fn rejects_oversized_url_and_tab_id() {
        let long_url = format!("https://x/{}", "a".repeat(9000)); // > 8192 上限
        assert!(SessionState::from_json(&state_json("t", "t", &long_url, "00")).is_none());
        let long_tab = "x".repeat(300); // > 256 上限
        assert!(SessionState::from_json(&state_json(&long_tab, "t", "u", "00")).is_none());
    }

    // —— RS-109/110 回归（审计 2026-09-25） ——

    #[test]
    fn rejects_odd_length_and_non_hex_bytes() {
        // RS-109：hex 解码畸形输入 fail-closed——奇数长度/非 hex 字符
        assert!(SessionState::from_json(&state_json("t", "t", "u", "0")).is_none());
        assert!(SessionState::from_json(&state_json("t", "t", "u", "0g")).is_none());
        assert!(SessionState::from_json(&state_json("t", "t", "u", "zz")).is_none());
        // 合法 hex 不受影响
        assert!(SessionState::from_json(&state_json("t", "t", "u", "0a1f")).is_some());
    }

    #[test]
    fn rejects_missing_required_fields() {
        // RS-109：缺必填字段逐项拒绝——此前 unwrap_or 默认值可能掩盖损坏
        let base = |body: &str| {
            format!(
                r#"{{"schemaVersion":{},"tabId":"t","sessionStateBytes":"00","metadata":{{{body}}},"timestamp":0}}"#,
                CURRENT_SCHEMA_VERSION
            )
        };
        // metadata 内缺 title / url
        assert!(
            SessionState::from_json(&base(r#""url":"https://e.com","isIncognito":false"#))
                .is_none()
        );
        assert!(SessionState::from_json(&base(r#""title":"t","isIncognito":false"#)).is_none());
        // 顶层缺 sessionStateBytes / tabId
        let no_bytes = format!(
            r#"{{"schemaVersion":{},"tabId":"t","metadata":{{"title":"t","url":"u","isIncognito":false}},"timestamp":0}}"#,
            CURRENT_SCHEMA_VERSION
        );
        assert!(SessionState::from_json(&no_bytes).is_none());
        let no_tab = format!(
            r#"{{"schemaVersion":{},"sessionStateBytes":"00","metadata":{{"title":"t","url":"u","isIncognito":false}},"timestamp":0}}"#,
            CURRENT_SCHEMA_VERSION
        );
        assert!(SessionState::from_json(&no_tab).is_none());
    }

    #[test]
    fn incognito_flag_never_silently_degrades() {
        // RS-110：isIncognito 缺失/类型损坏必须拒绝恢复（此前 unwrap_or(false)
        // 把无痕标签静默降级为普通标签——隐私语义丢失）
        let without_flag = format!(
            r#"{{"schemaVersion":{},"tabId":"t","sessionStateBytes":"00","metadata":{{"title":"t","url":"u"}},"timestamp":0}}"#,
            CURRENT_SCHEMA_VERSION
        );
        assert!(
            SessionState::from_json(&without_flag).is_none(),
            "缺 isIncognito 必须拒绝"
        );
        let wrong_type = format!(
            r#"{{"schemaVersion":{},"tabId":"t","sessionStateBytes":"00","metadata":{{"title":"t","url":"u","isIncognito":"yes"}},"timestamp":0}}"#,
            CURRENT_SCHEMA_VERSION
        );
        assert!(
            SessionState::from_json(&wrong_type).is_none(),
            "isIncognito 非 bool 必须拒绝"
        );
        // 显式 true 正常恢复
        let explicit = format!(
            r#"{{"schemaVersion":{},"tabId":"t","sessionStateBytes":"00","metadata":{{"title":"t","url":"u","isIncognito":true,"lastActiveTime":0,"canGoBack":false,"canGoForward":false}},"timestamp":0}}"#,
            CURRENT_SCHEMA_VERSION
        );
        let state = SessionState::from_json(&explicit).expect("显式 true 必须恢复");
        assert!(state.metadata.is_incognito);
    }

    #[test]
    fn hex_encode_large_block_single_pass() {
        // RS-111：write! 单缓冲语义回归——大块数据编码逐字节一致
        let data: Vec<u8> = (0..=255u8).cycle().take(4096).collect();
        let encoded = hex_encode(&data);
        assert_eq!(encoded.len(), 8192);
        assert_eq!(hex_decode(&encoded).unwrap(), data);
    }
}

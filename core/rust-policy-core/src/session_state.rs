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
#[derive(Debug, Clone)]
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
#[derive(Debug, Clone)]
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
            is_incognito: meta.get("isIncognito")?.as_bool().unwrap_or(false),
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

/// hex 编码（零依赖——简单可靠——无 padding 问题——每个字节→2 字符）。
fn hex_encode(data: &[u8]) -> String {
    data.iter().map(|b| format!("{b:02x}")).collect()
}

/// hex 解码（零依赖——每 2 字符→1 字节）。
fn hex_decode(s: &str) -> Option<Vec<u8>> {
    let bytes = s.as_bytes();
    if !bytes.len().is_multiple_of(2) {
        return None;
    }
    let mut out = Vec::with_capacity(bytes.len() / 2);
    for pair in bytes.chunks(2) {
        let hi = hex_digit(pair[0])?;
        let lo = hex_digit(pair[1])?;
        out.push((hi << 4) | lo);
    }
    Some(out)
}

use crate::util::hex_digit;

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

    fn state_json(tab_id: &str, title: &str, url: &str, hex_bytes: &str) -> String {
        format!(
            r#"{{"schemaVersion":{},"tabId":"{}","sessionStateBytes":"{}","metadata":{{"title":"{}","url":"{}","isIncognito":false,"lastActiveTime":0,"canGoBack":false,"canGoForward":false}},"timestamp":0}}"#,
            CURRENT_SCHEMA_VERSION, tab_id, hex_bytes, title, url
        )
    }

    #[test]
    fn rejects_unknown_schema_version() {
        let json = format!(
            r#"{{"schemaVersion":999,"tabId":"t","sessionStateBytes":"00","metadata":{{"title":"","url":"","isIncognito":false,"lastActiveTime":0,"canGoBack":false,"canGoForward":false}},"timestamp":0}}"#
        );
        assert!(SessionState::from_json(&json).is_none());
    }

    #[test]
    fn rejects_oversized_state_bytes() {
        let big = "ff".repeat(600 * 1024); // > 512KB 上限
        assert!(SessionState::from_json(&state_json("t", "t", "u", &big)).is_none());
    }

    #[test]
    fn rejects_oversized_url_and_tab_id() {
        let long_url = format!("https://x/{}", "a".repeat(9000)); // > 8192 上限
        assert!(SessionState::from_json(&state_json("t", "t", &long_url, "00")).is_none());
        let long_tab = "x".repeat(300); // > 256 上限
        assert!(SessionState::from_json(&state_json(&long_tab, "t", "u", "00")).is_none());
    }
}

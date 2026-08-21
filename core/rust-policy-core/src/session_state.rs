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
    pub fn from_json(json: &str) -> Option<Self> {
        let map: HashMap<String, serde_json::Value> = serde_json::from_str(json).ok()?;
        let schema_version = map.get("schemaVersion")?.as_u64()? as u32;
        let tab_id = map.get("tabId")?.as_str()?.to_string();
        let b64 = map.get("sessionStateBytes")?.as_str()?;
        let session_state_bytes = hex_decode(b64)?;
        let meta = map.get("metadata")?;
        let metadata = TabMetadata {
            title: meta.get("title")?.as_str()?.to_string(),
            url: meta.get("url")?.as_str()?.to_string(),
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
    pub fn to_json(&self) -> String {
        let b64 = hex_encode(&self.session_state_bytes);
        format!(
            r#"{{"schemaVersion":{},"tabId":"{}","sessionStateBytes":"{}","metadata":{{"title":"{}","url":"{}","isIncognito":{},"lastActiveTime":{},"canGoBack":{},"canGoForward":{}}},"timestamp":{}}}"#,
            self.schema_version,
            self.tab_id,
            b64,
            self.metadata.title,
            self.metadata.url,
            self.metadata.is_incognito,
            self.metadata.last_active_time,
            self.metadata.can_go_back,
            self.metadata.can_go_forward,
            self.timestamp,
        )
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

fn hex_digit(b: u8) -> Option<u8> {
    match b {
        b'0'..=b'9' => Some(b - b'0'),
        b'a'..=b'f' => Some(b - b'a' + 10),
        b'A'..=b'F' => Some(b - b'A' + 10),
        _ => None,
    }
}

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
}

//! Decision 类型化模型（蓝图——与 contracts/Windows Broker/Android Broker 一致）。
//!
//! Decision = Allow(AuthorizedAction) | RequireConfirmation(ApprovalRequest) | Deny(DenyReason)
//! ——不再用 bool/空字符串作为安全模型——默认拒绝（fail-closed）。

/// 类型化安全决策（纯数据——无 I/O）。
#[derive(Debug, Clone, PartialEq)]
pub enum Decision {
    Allow(AuthorizedAction),
    RequireConfirmation(ApprovalRequest),
    Deny(DenyReason),
}

/// AuthorizedAction——唯一允许进入副作用服务的凭据（ADR-002）。
/// 绑定字段任一变化使批准失效。
/// explanation：人类可读的审计说明（照搬 warden Verdict.explanation 模式）。
///
/// RS-191（审计 2026-09-25）：字段级文档——绑定字段（参与批准失效判定）
/// 与描述字段（仅审计）的边界由此锁定。**explanation 不参与绑定比较**
/// （ffi/broker.rs consume 的 M-15 修正口径：托管端序列化不携带该字段）。
#[derive(Debug, Clone, PartialEq)]
pub struct AuthorizedAction {
    /// 会话标识——broker 会话池寻址键（不存在即 session_not_found）。
    pub session_id: String,
    /// 绑定标签页——跨标签使用该凭据被拒（tab_mismatch）。
    pub tab_id: String,
    /// 绑定顶层文档代际——页面切换推进后旧代际凭据失效（generation_mismatch）。
    pub document_generation: u64,
    /// 绑定 origin（scheme://host[:port]）——授权与来源强绑定。
    pub origin: String,
    /// 绑定 HTTP 方法（当前导航通路恒为 "GET"——其余方法走副作用审批）。
    pub method: String,
    /// 绑定规范化 path+query（fragment 不参与绑定）。
    pub canonical_parameters: String,
    /// 动作 scope（策略/能力层评估键，如 "navigation"）。
    pub scope: String,
    /// 授权失效时刻（UNIX 秒）——`<= now` 即过期（RS-156 边界口径）。
    pub expires_at: u64,
    /// 一次性 nonce——消费即失效（重放拒绝），由 broker 账本原子推进。
    pub nonce: String,
    /// 签发时策略版本——与 broker 当前版本不一致即拒（policy_version_mismatch）。
    pub policy_version: String,
    /// 人类可读审计说明——**不参与绑定比较**（M-15：托管端序列化不携带）。
    pub explanation: String,
}

/// 审批请求（高风险副作用——原生确认——nonce 一次性/过期——重放拒绝）。
#[derive(Debug, Clone, PartialEq)]
pub struct ApprovalRequest {
    pub origin: String,
    pub method: String,
    pub path: String,
    pub scope: String,
    pub expires_at: u64,
    pub nonce: String,
}

/// 拒绝原因（类型化——fail-closed——审计可追溯）。
#[derive(Debug, Clone, PartialEq)]
pub struct DenyReason {
    pub code: String,
    pub detail: String,
    /// 人类可读的审计说明（照搬 warden Verdict.explanation 模式）。
    pub explanation: String,
}

impl Decision {
    /// 是否为放行决策（仅 Allow——RequireConfirmation 不算放行）。
    ///
    /// RS-090（审计 2026-09-25）：判定 helper 单源——调用方不得各自
    /// `matches!` 重复展开（口径漂移风险）。
    pub fn is_allow(&self) -> bool {
        matches!(self, Decision::Allow(_))
    }

    /// 拒绝码（仅 Deny 决策有值——审计通道直接消费）。
    pub fn deny_code(&self) -> Option<&str> {
        match self {
            Decision::Deny(reason) => Some(&reason.code),
            _ => None,
        }
    }

    /// 是否需要用户确认。
    pub fn requires_confirmation(&self) -> bool {
        matches!(self, Decision::RequireConfirmation(_))
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn deny(code: &str) -> Decision {
        Decision::Deny(DenyReason {
            code: code.into(),
            detail: "detail".into(),
            explanation: "explanation".into(),
        })
    }

    #[test]
    fn decision_helpers_classify_correctly() {
        // RS-090：三分支判定 helper 单源语义
        let allow = Decision::Allow(AuthorizedAction {
            session_id: "s".into(),
            tab_id: "t".into(),
            document_generation: 1,
            origin: "https://example.com".into(),
            method: "GET".into(),
            canonical_parameters: "/".into(),
            scope: "nav".into(),
            expires_at: 1,
            nonce: "n".into(),
            policy_version: "1".into(),
            explanation: "ok".into(),
        });
        assert!(allow.is_allow());
        assert!(!allow.requires_confirmation());
        assert_eq!(allow.deny_code(), None);
        let d = deny("policy_denied");
        assert!(!d.is_allow());
        assert_eq!(d.deny_code(), Some("policy_denied"));
        let ask = Decision::RequireConfirmation(ApprovalRequest {
            origin: "https://example.com".into(),
            method: "POST".into(),
            path: "/".into(),
            scope: "nav".into(),
            expires_at: 0,
            nonce: "pending".into(),
        });
        assert!(ask.requires_confirmation());
        assert!(!ask.is_allow(), "RequireConfirmation 不算放行");
        assert_eq!(ask.deny_code(), None);
    }

    #[test]
    fn decisions_equality_binds_all_fields() {
        // RS-089：PartialEq 绑定全部字段——nonce 任一变化即不等（重放
        // 防护依赖凭据逐字段比对）
        let a = deny("denied");
        let b = deny("denied");
        assert_eq!(a, b);
        let c = deny("other_code");
        assert_ne!(a, c);
        // 默认拒绝语义：Deny 是独立构造，与 Allow/RequireConfirmation 恒不等
        assert_ne!(
            a,
            Decision::RequireConfirmation(ApprovalRequest {
                origin: String::new(),
                method: String::new(),
                path: String::new(),
                scope: String::new(),
                expires_at: 0,
                nonce: String::new(),
            })
        );
    }

    #[test]
    fn debug_shows_variant_structure() {
        // RS-089：Debug 可诊断（不泄敏断言——decision 本身非秘密）
        let debug = format!("{:?}", deny("fail_safe"));
        assert!(debug.contains("Deny"));
        assert!(debug.contains("fail_safe"));
    }
}

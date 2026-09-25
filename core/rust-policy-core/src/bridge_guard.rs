//! Bridge 硬化（照搬 AdarshK11/SecureWebViewContainer NativeBridge.kt 本地化适配）。
//!
//! 两端各司其职：
//! - 原生 [`BridgeGuard::validate`]：对 bridge **目标**做 HTTPS + 域名白名单校验（fail-closed）。
//! - 注入页面脚本 [`BridgeGuard::inject_script`]：拦截 fetch / XMLHttpRequest / sendBeacon /
//!   WebSocket，只有**调用方自身属于受信内页**（hostname ∈ 白名单）才放行 bridge 调用。
//!
//! 可拆卸：不依赖 UI/网络/策略引擎。
//! 可拼接：WebView 创建时注入为 JS bridge 的安全门。

use std::collections::HashSet;

/// 注入脚本中的占位符：用 `.replace()` 组装，避免与 JS 花括号冲突，也无需 `format!` 转义。
/// 模板因此保持人类可读、可单测断言。
const SCRIPT_PLACEHOLDER_HOSTS: &str = "__AEGIS_HOSTS__";
const SCRIPT_PLACEHOLDER_HTTPS: &str = "__AEGIS_REQUIRE_HTTPS__";

/// JS 桥安全配置。
#[derive(Debug)]
pub struct BridgeGuard {
    /// 允许调用 bridge 的域名白名单。
    allowed_hosts: HashSet<String>,
    /// 是否强制 HTTPS（true=仅 HTTPS 允许调用 bridge）。
    require_https: bool,
}

impl BridgeGuard {
    pub fn new(allowed_hosts: Vec<String>, require_https: bool) -> Self {
        Self {
            // RS-129（审计 2026-09-25）：构造时小写归一——host 语义
            // 大小写不敏感（RFC 4343），字面差异不得造成误杀
            allowed_hosts: allowed_hosts
                .into_iter()
                .map(|h| h.to_ascii_lowercase())
                .collect(),
            require_https,
        }
    }

    /// 验证 bridge 调用是否允许（对 bridge **目标**做校验）。
    /// 返回 Ok(()) 允许，Err(reason) 拒绝。
    ///
    /// RS-129（审计 2026-09-25）：scheme/host 比较大小写不敏感——
    /// 此前 `scheme != "https"` 字面比较：`HTTPS://` 目标被误杀；
    /// host 白名单 `contains` 字面比较：`Example.COM` 目标被误杀。
    /// RS-130（审计 2026-09-25）：host 含端口时按**字面**匹配
    /// （"example.com:8080" ≠ "example.com"）——端口归一由调用方
    /// extract_host 层负责，此处不剥离（fail-closed：归一缺失只会
    /// 拒绝，不会放行）。
    pub fn validate(&self, scheme: &str, host: &str) -> Result<(), String> {
        if self.require_https && !scheme.eq_ignore_ascii_case("https") {
            return Err(format!("bridge 调用拒绝：非 HTTPS（scheme={scheme}）"));
        }
        let host_lc = host.to_ascii_lowercase();
        if !self.allowed_hosts.is_empty() && !self.allowed_hosts.contains(&host_lc) {
            return Err(format!("bridge 调用拒绝：host {host} 不在白名单中"));
        }
        Ok(())
    }

    /// 生成 JS 注入脚本（拦截未授权的 bridge 调用，覆盖 4 种网络出口）。
    ///
    /// 安全模型：只有「调用方自身 hostname ∈ 白名单」的受信内页才能调用 bridge，
    /// 普通站点的非 bridge 流量一律放行（不影响正常浏览）。
    ///
    /// 模板单一事实源（ADR-007）：脚本本体在
    /// `contracts/schemas/bridge_guard.template.js`（contracts 唯一事实源原则），
    /// 经 `include_str!` 编译期嵌入——杜绝 Rust/Kotlin 手工拷贝漂移
    /// （漂移由 `contracts/codegen/verify_bridge_guard.py` 门禁兜底）。
    pub fn inject_script(&self) -> String {
        let mut hosts: Vec<&str> = self.allowed_hosts.iter().map(|s| s.as_str()).collect();
        hosts.sort_unstable(); // 稳定输出，便于测试断言
        let hosts_json = serde_json::to_string(&hosts).unwrap_or_else(|_| "[]".to_string());
        let require_https = if self.require_https { "true" } else { "false" };

        const SCRIPT: &str = include_str!("../../../contracts/schemas/bridge_guard.template.js");

        SCRIPT
            .replace(SCRIPT_PLACEHOLDER_HOSTS, &hosts_json)
            .replace(SCRIPT_PLACEHOLDER_HTTPS, require_https)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn https_allowed_host_passes() {
        let guard = BridgeGuard::new(vec!["example.com".into()], true);
        assert!(guard.validate("https", "example.com").is_ok());
    }

    #[test]
    fn http_rejected_when_require_https() {
        let guard = BridgeGuard::new(vec!["example.com".into()], true);
        assert!(guard.validate("http", "example.com").is_err());
    }

    #[test]
    fn unknown_host_rejected() {
        let guard = BridgeGuard::new(vec!["example.com".into()], true);
        assert!(guard.validate("https", "evil.com").is_err());
    }

    #[test]
    fn empty_allowlist_permits_all() {
        let guard = BridgeGuard::new(vec![], false);
        assert!(guard.validate("http", "any.com").is_ok());
    }

    // —— RS-129/130（审计 2026-09-25）——

    #[test]
    fn scheme_and_host_case_insensitive() {
        // RS-129：HTTPS:// 目标与 Example.COM 白名单/请求大小写变体
        // 不得被字面比较误杀
        let guard = BridgeGuard::new(vec!["Example.COM".into()], true);
        assert!(guard.validate("HTTPS", "example.com").is_ok());
        assert!(guard.validate("https", "EXAMPLE.com").is_ok());
        assert!(guard.validate("HttpS", "Example.Com").is_ok());
        // 大小写不敏感 ≠ 全放行：scheme 非 https 仍拒绝
        assert!(guard.validate("HTTPS-KEEP-ALIVE", "example.com").is_err());
        assert!(guard.validate("http", "EXAMPLE.COM").is_err());
    }

    #[test]
    fn host_with_port_is_literal_fail_closed() {
        // RS-130：host 含端口按字面匹配——白名单 "example.com:8080"
        // 不放行裸 "example.com"，反之亦然（端口归一属调用方职责；
        // 字面差异只会拒绝不会放行 = fail-closed）
        let guard = BridgeGuard::new(vec!["example.com:8080".into()], false);
        assert!(guard.validate("https", "example.com:8080").is_ok());
        assert!(
            guard.validate("https", "example.com").is_err(),
            "裸 host 不得命中带端口白名单条目"
        );
        let guard_bare = BridgeGuard::new(vec!["example.com".into()], false);
        assert!(guard_bare.validate("https", "example.com").is_ok());
        assert!(
            guard_bare.validate("https", "example.com:8080").is_err(),
            "带端口 host 不得命中裸白名单条目"
        );
    }

    #[test]
    fn require_https_gates_even_with_empty_allowlist() {
        // RS-130：组合语义——HTTPS 门禁独立于白名单：
        // 空白名单 + require_https 时 http 目标必须拒绝（此前仅测
        // 「空白名单+非 https」与「非空白名单+https」两半边）
        let guard = BridgeGuard::new(vec![], true);
        assert!(guard.validate("http", "any.com").is_err());
        assert!(guard.validate("https", "any.com").is_ok());
        // 组合面：白名单命中 + scheme 违规 → 仍拒绝（scheme 先判）
        let strict = BridgeGuard::new(vec!["example.com".into()], true);
        assert!(strict.validate("http", "example.com").is_err());
        assert!(strict.validate("https", "not-allowed.com").is_err());
        assert!(strict.validate("https", "example.com").is_ok());
    }

    // —— 注入脚本质量断言（防回归：注释与实现保持一致，且覆盖所有网络出口）——
    #[test]
    fn inject_script_covers_all_sinks() {
        let guard = BridgeGuard::new(vec!["aegis.local".into()], true);
        let s = guard.inject_script();
        for needle in [
            "window.fetch = function",
            "XMLHttpRequest.prototype.open",
            "navigator.sendBeacon = function",
            "window.WebSocket = function",
        ] {
            assert!(s.contains(needle), "注入脚本缺少拦截点：{needle}");
        }
        // 核心安全属性：受信调用方（自身 hostname ∈ 白名单）校验
        assert!(s.contains("trustedCaller"));
        assert!(s.contains("location.hostname"));
    }

    #[test]
    fn inject_script_substitutes_allowlist_and_https() {
        let guard = BridgeGuard::new(vec!["aegis.local".into(), "localhost".into()], true);
        let s = guard.inject_script();
        // 模板占位符必须被替换，不得残留
        assert!(!s.contains(SCRIPT_PLACEHOLDER_HOSTS));
        assert!(!s.contains(SCRIPT_PLACEHOLDER_HTTPS));
        assert!(s.contains("\"aegis.local\""));
        assert!(s.contains("REQUIRE_HTTPS = true"));

        // HTTPS 未开启时输出 false
        let guard_no_https = BridgeGuard::new(vec!["aegis.local".into()], false);
        let s2 = guard_no_https.inject_script();
        assert!(s2.contains("REQUIRE_HTTPS = false"));
    }
}

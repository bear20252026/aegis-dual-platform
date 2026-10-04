use super::super::*;

use super::common::*;

#[test]
fn c_abi_matches_native_navigation_confirmation_vectors() {
    let _serial = broker_test_guard();
    let vectors: serde_json::Value = serde_json::from_str(include_str!(
        "../../../../../contracts/vectors/native-navigation-confirmation.json"
    ))
    .expect("native navigation confirmation vectors must be valid JSON");

    for vector in vectors["vectors"].as_array().expect("vectors array") {
        let name = vector["name"].as_str().expect("vector name");
        let version = c_string("1.0");
        let broker = aegis_policy_core_broker_new(version.as_ptr());
        assert!(!broker.is_null(), "{name}: broker creation");
        let session = c_string("confirmation-vector-session");
        let tab = c_string("confirmation-vector-tab");
        let generation = vector["generation"].as_u64().expect("generation");
        if vector["register_session"].as_bool().expect("registration") {
            assert_eq!(
                aegis_policy_core_broker_create_session(
                    broker,
                    session.as_ptr(),
                    tab.as_ptr(),
                    generation,
                    120,
                ),
                1,
                "{name}: session registration"
            );
        }
        // 审计第六轮（2026-10-03/04）：可选威胁 host 黑名单注入。
        // deny-by-content 此前在向量里没有表达形式（native-navigation-decision
        // 只覆盖 url_policy / session_not_found 两类拒绝），"黑名单匹配"这类
        // 最像安全特性的代码从未被跨端锁定。accepted 必须等于条目数——不等即
        // 说明有条目被形态校验拒收，将成为永不命中的死条目。
        if let Some(hosts) = vector.get("deny_hosts") {
            let payload = c_string(&hosts.to_string());
            let applied = read_response(aegis_policy_core_broker_update_host_denylist_json(
                broker,
                payload.as_ptr(),
            ));
            assert_eq!(applied["decision"], "ok", "{name}: 黑名单注入失败");
            assert_eq!(
                applied["accepted"].as_u64(),
                Some(hosts.as_array().expect("deny_hosts 必须是数组").len() as u64),
                "{name}: 黑名单有条目被形态校验拒收（静默死条目）"
            );
        }
        let url = c_string(vector["url"].as_str().expect("url"));
        let scope = c_string(vector["scope"].as_str().expect("scope"));
        let requested = read_response(
            aegis_policy_core_broker_request_navigation_confirmation_json(
                broker,
                session.as_ptr(),
                tab.as_ptr(),
                generation,
                url.as_ptr(),
                scope.as_ptr(),
            ),
        );
        assert_eq!(
            requested["decision"], vector["expected_request"],
            "{name}: request decision"
        );
        if requested["decision"] == "deny" {
            assert_eq!(
                requested["reason"]["code"], vector["expected_request_code"],
                "{name}: request denial"
            );
            // SAFETY: broker 由本测试创建，且在此后不再使用或释放。
            unsafe { aegis_policy_core_broker_free(broker) };
            continue;
        }
        let nonce = c_string(
            requested["request"]["nonce"]
                .as_str()
                .expect("approval nonce"),
        );
        if let Some(next_generation) = vector.get("advance_generation") {
            assert_eq!(
                aegis_policy_core_broker_advance_document_generation(
                    broker,
                    session.as_ptr(),
                    tab.as_ptr(),
                    next_generation.as_u64().expect("next generation"),
                ),
                1,
                "{name}: generation advance"
            );
        }
        if vector
            .get("reject")
            .and_then(serde_json::Value::as_bool)
            .unwrap_or(false)
        {
            assert_eq!(
                aegis_policy_core_broker_reject_navigation_confirmation(broker, nonce.as_ptr(),),
                1,
                "{name}: explicit rejection"
            );
        }
        let approve_url = c_string(vector["approve_url"].as_str().expect("approve URL"));
        let approve_scope = c_string(vector["approve_scope"].as_str().expect("approve scope"));
        let approved = read_response(
            aegis_policy_core_broker_approve_navigation_confirmation_json(
                broker,
                nonce.as_ptr(),
                approve_url.as_ptr(),
                approve_scope.as_ptr(),
            ),
        );
        assert_eq!(
            approved["decision"], vector["expected_approve"],
            "{name}: approve decision"
        );
        if let Some(expected_code) = vector.get("expected_approve_code") {
            assert_eq!(
                approved["reason"]["code"], *expected_code,
                "{name}: approve denial"
            );
        }
        if let Some(expected_code) = vector.get("expected_second_approve_code") {
            let second = read_response(
                aegis_policy_core_broker_approve_navigation_confirmation_json(
                    broker,
                    nonce.as_ptr(),
                    approve_url.as_ptr(),
                    approve_scope.as_ptr(),
                ),
            );
            assert_eq!(
                second["reason"]["code"], *expected_code,
                "{name}: second approval"
            );
        }
        if approved["decision"] == "allow" {
            let action = c_string(&approved["action"].to_string());
            let consumed = read_response(aegis_policy_core_broker_consume_navigation_json(
                broker,
                action.as_ptr(),
                approve_url.as_ptr(),
                approve_scope.as_ptr(),
            ));
            assert_eq!(
                consumed["decision"], vector["expected_consume"],
                "{name}: consume decision"
            );
            if let Some(expected_code) = vector.get("expected_replay_code") {
                let replay = read_response(aegis_policy_core_broker_consume_navigation_json(
                    broker,
                    action.as_ptr(),
                    approve_url.as_ptr(),
                    approve_scope.as_ptr(),
                ));
                assert_eq!(
                    replay["reason"]["code"], *expected_code,
                    "{name}: replay denial"
                );
            }
        }
        // SAFETY: broker 由本测试创建，且在此后不再使用或释放。
        unsafe { aegis_policy_core_broker_free(broker) };
    }
}

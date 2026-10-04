use super::super::*;

use super::common::*;

#[test]
fn c_abi_matches_native_navigation_decision_vectors() {
    let _serial = broker_test_guard();
    let vectors: serde_json::Value = serde_json::from_str(include_str!(
        "../../../../../contracts/vectors/native-navigation-decision.json"
    ))
    .expect("native navigation decision vectors must be valid JSON");

    for vector in vectors["vectors"].as_array().expect("vectors array") {
        let name = vector["name"].as_str().expect("vector name");
        let version = c_string("1.0");
        let broker = aegis_policy_core_broker_new(version.as_ptr());
        assert!(!broker.is_null(), "{name}: broker creation");
        let session = c_string("vector-session");
        let tab = c_string("vector-tab");
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
        let evaluated = read_response(aegis_policy_core_broker_evaluate_navigation_json(
            broker,
            session.as_ptr(),
            tab.as_ptr(),
            generation,
            url.as_ptr(),
            scope.as_ptr(),
        ));
        assert_eq!(
            evaluated["decision"], vector["expected_evaluate"],
            "{name}: evaluate decision"
        );
        if evaluated["decision"] == "deny" {
            assert_eq!(
                evaluated["reason"]["code"], vector["expected_deny_code"],
                "{name}: evaluate denial code"
            );
            // SAFETY: broker 由本测试创建，且在此后不再使用或释放。
            unsafe { aegis_policy_core_broker_free(broker) };
            continue;
        }
        // 审计第六轮（2026-10-03/04）：高危目标（本机/私网）走待审批分支——
        // 核心不得发放可消费授权，只回 request；这条分支此前不存在，因为
        // evaluate_navigation 从不做内容判定。
        if evaluated["decision"] == "require_confirmation" {
            if let Some(expected_origin) = vector.get("expected_origin") {
                assert_eq!(
                    evaluated["request"]["origin"], *expected_origin,
                    "{name}: 待审批请求 origin"
                );
            }
            assert!(
                evaluated.get("action").is_none(),
                "{name}: 高危目标不得同时发放可消费授权"
            );
            // SAFETY: broker 由本测试创建，且在此后不再使用或释放。
            unsafe { aegis_policy_core_broker_free(broker) };
            continue;
        }
        assert_eq!(
            evaluated["action"]["origin"], vector["expected_origin"],
            "{name}: canonical origin"
        );
        assert_eq!(
            evaluated["action"]["canonical_parameters"], vector["expected_parameters"],
            "{name}: canonical parameters"
        );
        let action = c_string(&evaluated["action"].to_string());
        let consume_url = c_string(vector["consume_url"].as_str().expect("consume URL"));
        let consume_scope = c_string(vector["consume_scope"].as_str().expect("consume scope"));
        let consumed = read_response(aegis_policy_core_broker_consume_navigation_json(
            broker,
            action.as_ptr(),
            consume_url.as_ptr(),
            consume_scope.as_ptr(),
        ));
        assert_eq!(
            consumed["decision"], vector["expected_consume"],
            "{name}: consume decision"
        );
        if let Some(expected_code) = vector.get("expected_consume_code") {
            assert_eq!(
                consumed["reason"]["code"], *expected_code,
                "{name}: consume denial"
            );
        }
        if let Some(expected_replay_code) = vector.get("expected_replay_code") {
            let replay = read_response(aegis_policy_core_broker_consume_navigation_json(
                broker,
                action.as_ptr(),
                consume_url.as_ptr(),
                consume_scope.as_ptr(),
            ));
            assert_eq!(
                replay["reason"]["code"], *expected_replay_code,
                "{name}: replay denial"
            );
        }
        // PY-091/092（审计 2026-09-25）：向量协议扩展——销毁会话/推进代际
        // 后再次消费同一 action，断言 fail-closed 拒绝码
        if vector
            .get("destroy_session")
            .and_then(|v| v.as_bool())
            .unwrap_or(false)
        {
            assert_eq!(
                aegis_policy_core_broker_destroy_session(broker, session.as_ptr()),
                1,
                "{name}: destroy session"
            );
        }
        if vector
            .get("advance_generation")
            .and_then(|v| v.as_bool())
            .unwrap_or(false)
        {
            assert_eq!(
                aegis_policy_core_broker_advance_document_generation(
                    broker,
                    session.as_ptr(),
                    tab.as_ptr(),
                    generation + 1,
                ),
                1,
                "{name}: advance generation"
            );
        }
        if let Some(expected_reconsume_code) = vector.get("expected_reconsume_code") {
            let reconsume = read_response(aegis_policy_core_broker_consume_navigation_json(
                broker,
                action.as_ptr(),
                consume_url.as_ptr(),
                consume_scope.as_ptr(),
            ));
            assert_eq!(reconsume["decision"], "deny", "{name}: reconsume must deny");
            assert_eq!(
                reconsume["reason"]["code"], *expected_reconsume_code,
                "{name}: reconsume denial code"
            );
        }
        // SAFETY: broker 由本测试创建，且在此后不再使用或释放。
        unsafe { aegis_policy_core_broker_free(broker) };
    }
}

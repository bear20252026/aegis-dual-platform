#![no_main]

use libfuzzer_sys::fuzz_target;

// RS-050：SessionState::from_json 必须是 total 的——任意 UTF-8 输入不 panic、
// 不无界分配（解析前总长上限先行）、字段限长只返回 None。往返一致性：
// 解析成功则 to_json 再解析须得到相同结果。
fuzz_target!(|data: &[u8]| {
    if let Ok(json) = std::str::from_utf8(data) {
        if let Some(state) = aegis_policy_core::session_state::SessionState::from_json(json) {
            let re = aegis_policy_core::session_state::SessionState::from_json(&state.to_json());
            assert_eq!(re.as_ref(), Some(&state), "session_state 往返必须一致");
        }
    }
});

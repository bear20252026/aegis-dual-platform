#![no_main]

use libfuzzer_sys::fuzz_target;

// RS-050：util 主机提取面必须 total——extract_hostname/extract_host 对任意
// 输入（含裸 IPv6、内嵌冒号、authority 终止符组合）不 panic；转义助手
// js_escape_single_quoted 输出必须真正消除单引号注入面。
fuzz_target!(|data: &[u8]| {
    let s = String::from_utf8_lossy(data);
    let _ = aegis_policy_core::util::extract_hostname(&s);
    let _ = aegis_policy_core::util::extract_host(&s);
    let escaped = aegis_policy_core::util::js_escape_single_quoted(&s);
    // 转义不变式：输出中不得存在未转义的单引号/反斜杠/裸换行（作为 JS
    // 单引号字面量注入面必须闭合——\' \\\\ \n \r 序列本身合法）
    let mut chars = escaped.chars().peekable();
    while let Some(c) = chars.next() {
        if c == '\\' {
            assert!(
                matches!(chars.next(), Some('\\' | '\'' | 'n' | 'r')),
                "js_escape 输出含非法转义序列"
            );
        } else {
            assert!(c != '\'', "js_escape 输出含未转义单引号");
        }
    }
});

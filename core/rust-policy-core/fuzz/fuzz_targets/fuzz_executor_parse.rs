#![no_main]

use libfuzzer_sys::fuzz_target;

// RS-271（2026-10-01 审计）：Executor 命令解析（阶段 1）必须是 total 的——
// 任意输入（畸形 JSON/超长/深嵌套/类型错位）经 execute_pipeline 不 panic，
// 结果只能是 Ok 三态或类型化错误；解析层有 64KB 输入上限先行。
fuzz_target!(|data: &[u8]| {
    let s = String::from_utf8_lossy(data);
    let executor = aegis_policy_core::executor::Executor::new();
    let _ = executor.execute_pipeline(&s);
});

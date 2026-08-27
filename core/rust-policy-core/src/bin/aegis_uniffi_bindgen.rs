//! 受 Cargo.lock 约束的 UniFFI 绑定生成器。
//!
//! 将生成工具作为本 crate 的显式二进制目标，避免依赖开发机全局安装的
//! `uniffi-bindgen` 版本。CI 必须从已构建的 cdylib 生成绑定并检查漂移。

fn main() {
    uniffi::uniffi_bindgen_main();
}

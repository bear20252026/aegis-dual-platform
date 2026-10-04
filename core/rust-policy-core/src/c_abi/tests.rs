// 测试按主题拆到同名子目录；子模块经 `use super::super::*;` 看到父模块
// 私有项（Rust 子模块可见祖先私有项），故外迁未放宽任何生产可见性。
mod buffer_boundaries;
mod common;
mod consume_and_approval;
mod envelope_and_input_errors;
mod export_surface;
mod malformed_and_retired;
mod vectors_confirmation;
mod vectors_decision;

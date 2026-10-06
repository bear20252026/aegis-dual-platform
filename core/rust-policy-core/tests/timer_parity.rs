//! R8-RS-04（第八轮审计 2026-10-06）：`performance.now()` 单调钳位的**三端齐平**门禁。
//!
//! 形态：圆整到精度网格后叠加**无状态**随机抖动 ⇒ 相邻两次读数可回退（t2 < t1），
//! 违反规范保证的「单调非递减」。回退既是一行即检的防护存在信号
//! （`for (var i = 0; i < 1000; i++) if (performance.now() < prev) bad++`），
//! 也会打乱页内动画与性能统计。C# 孪生（`FingerprintShield.cs` 的 Stage 8）早有
//! 高水位钳位，而 **Rust 核心与 Android 注入脚本都没有** ⇒ 台账里「三端同一防护」
//! 在这一出口上是假的（本文件因此先对未修形态报红，再长期防回退与防单端漂移）。
//!
//! 为什么放 `tests/` 而不是 `src/timer_prec.rs` 的内联 `mod tests`：后者是
//! `scripts/file_size_baseline.json` 的零余量 ratchet 条目，新增判定面按本仓既有
//! 口径外迁成独立文件；跨端对账也需要能同时看到三份源码的位置。
//!
//! 断言取**计数/三件套**而不是「标识符在场」：只声明高水位而不在读回路径上比较与
//! 回填，等于没有钳位——那是恒绿的另一种形态。

use aegis_policy_core::timer_prec::{TimerPrecision, TimerPrecisionConfig};
use std::path::Path;

/// 高水位声明。
const DECL: &str = "var lastPerf = -Infinity;";
/// 回退钳位（读回路径上的比较）。
const CLAMP: &str = "if (v < lastPerf) v = lastPerf;";
/// 高水位回填。
const FILL: &str = "lastPerf = v;";

fn repo_file(rel: &str) -> String {
    let manifest = env!("CARGO_MANIFEST_DIR");
    let path = Path::new(manifest).join(rel);
    std::fs::read_to_string(&path)
        .unwrap_or_else(|e| panic!("读取 {path:?} 失败：{e}（仓库布局契约）"))
}

fn script_with(jitter: bool) -> String {
    TimerPrecision::with_config(TimerPrecisionConfig {
        microseconds: 100,
        jitter,
    })
    .inject_script()
}

#[test]
fn rust_generated_script_clamps_performance_now() {
    let script = TimerPrecision::new().inject_script();
    assert!(script.contains(DECL), "Rust 生成脚本缺单调高水位声明");
    assert!(script.contains(CLAMP), "Rust 生成脚本缺回退比较式");
    assert!(script.contains(FILL), "Rust 生成脚本缺高水位回填");
    // 4 = 声明 1 + 比较行 2（读写各一）+ 回填 1；注释里刻意不出现该标识符
    assert_eq!(
        script.matches("lastPerf").count(),
        4,
        "钳位形态不完整（多一处少一处都算）：{script}"
    );
}

#[test]
fn clamp_is_not_gated_on_jitter_enabled() {
    // 关掉随机抖动后钳位必须仍在：圆整本身仍可能因时钟回跳而递减，且
    // 「钳位挂在 JITTER_ENABLED 分支里」会让 jitter=false 配置整面失守。
    let no_jitter = script_with(false);
    assert!(no_jitter.contains("JITTER_ENABLED = false;"), "配置未透传");
    assert!(
        no_jitter.contains(CLAMP) && no_jitter.contains(FILL),
        "jitter 关闭即丢钳位"
    );
}

#[test]
fn all_three_ends_share_the_same_clamp_form() {
    let ends: [(&str, String); 3] = [
        (
            "Rust 核心（生成脚本）",
            TimerPrecision::new().inject_script(),
        ),
        (
            "C# FingerprintShield",
            repo_file("../../windows/src/Aegis.Windows.App/WebView/FingerprintShield.cs"),
        ),
        (
            "Android WebViewHardening Stage 8",
            repo_file(
                "../../android/app/src/main/java/com/aegis/browser/WebViewHardeningStagesShield.kt",
            ),
        ),
    ];
    for (name, text) in ends {
        for fragment in [DECL, CLAMP, FILL] {
            assert!(
                text.contains(fragment),
                "{name} 缺计时器单调钳位的这一段：{fragment}"
            );
        }
    }
}

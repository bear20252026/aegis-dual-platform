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

/// R9-B38（第九轮 Q25）：三端共用的**挂载形态**片段（缩进不比对，只比对文本）。
/// 核心按 RS-216/RS-250 早就是这个形状，两端此前是「实例 value 遮蔽 + 写死双 false」——
/// 那一形态有两个后果：`Performance.prototype.now.call(performance)` 直取无降噪原实现，
/// 而 `hasOwnProperty.call(performance,'now')` / `getOwnPropertyDescriptor` 一查即检出防护。
const MOUNT_PROTO: &str =
    "var oPN = Object.getOwnPropertyDescriptor(Performance.prototype, 'now');";
const MOUNT_TARGET: &str = "var tgtPN = Performance.prototype;";
const MOUNT_FALLBACK: &str = "oPN = Object.getOwnPropertyDescriptor(performance, 'now');";
const MOUNT_PRESERVE: &str = "writable: oPN.writable,";
const MOUNT_ENUMERABLE: &str = "enumerable: oPN.enumerable,";
const MOUNT_CONFIGURABLE: &str = "configurable: oPN.configurable";
/// 被禁止的旧形状（冻结的实例遮蔽）——出现即说明某一端漂移回去。
const FROZEN_INSTANCE: &str = "writable: false, configurable: false";

fn three_end_sources() -> [(&'static str, String); 3] {
    [
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
    ]
}

#[test]
fn all_three_ends_mount_performance_now_on_the_prototype_preserving_the_native_descriptor() {
    for (name, text) in three_end_sources() {
        for fragment in [
            MOUNT_PROTO,
            MOUNT_TARGET,
            MOUNT_FALLBACK,
            MOUNT_PRESERVE,
            MOUNT_ENUMERABLE,
            MOUNT_CONFIGURABLE,
        ] {
            assert!(
                text.contains(fragment),
                "{name} 的 performance.now 挂载形态与核心不同形：缺 {fragment}"
            );
        }
        assert!(
            !text.contains(FROZEN_INSTANCE),
            "{name} 又出现「实例 value 遮蔽 + 冻结描述符」形态——那是可绕过也可检出的旧形状"
        );
    }
}

#[test]
fn mounting_shape_is_not_satisfied_by_mere_identifier_presence() {
    // 反向锚（内存态注入）：把「原型」这个来源整体换成实例，两个原型片段必须同时消失——
    // 不写这条，上面那组断言会退化成「文件里有 oPN 三个字」。
    let real = TimerPrecision::new().inject_script();
    let mutated = real.replace("Performance.prototype", "performance");
    assert_ne!(
        mutated, real,
        "注入锚点失配（核心脚本形态变了，本条会恒绿）"
    );
    let missing: Vec<&str> = [MOUNT_PROTO, MOUNT_TARGET]
        .into_iter()
        .filter(|f| !mutated.contains(f))
        .collect();
    assert_eq!(
        missing.len(),
        2,
        "注入没生效：改过的脚本仍含原型挂载片段 ⇒ 判据恒真"
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

/// R9-B97：桌面 A/B 冒烟注入的就是这份金样本——`TimerPrecision::new()` 的默认配置
/// （1000µs + jitter）必须与 `contracts/timer-stage8-script.js` **逐字节相同**。
///
/// 为什么要有这条：Q57 剩下的半边要的是「裹了之后站点观察到什么」的数字，而数字只有
/// 注入**真**脚本才有意义——在探针里手写一份「代表形态」量的是我的重写，不是核心。
/// 金样本因此既是测量输入也是契约：核心脚本一改（精度、jitter、单调钳位、描述符形态），
/// 这条先红，逼着同批重跑冒烟并重记数字，而不是让台账里的结论继续引用旧字节。
#[test]
fn stage8_golden_matches_the_generated_script_byte_for_byte() {
    let golden = repo_file("../../contracts/timer-stage8-script.js");
    let generated = TimerPrecision::new().inject_script();
    assert_eq!(
        golden,
        format!(
            "{generated}
"
        )
        .as_str(),
        "核心 Stage-8 脚本与金样本漂移——桌面 A/B 冒烟的数字不再代表这份字节，须同批重跑并重记台账"
    );
}

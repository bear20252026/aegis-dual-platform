//! R8-RS-09（第八轮审计 2026-10-06）：ToStringGuard 的**注册窗口**必须在本 blob
//! 末尾同步关闭，且注册接口不得只防 original 一侧。
//!
//! 缺陷形态（RS-252 原设计留下的两面）：
//! 1. 撤销排在 `setTimeout(0)` 宏任务里，而 document-start 注入与后续 HTML 解析
//!    在**同一个任务**内完成 ⇒ 头部内联脚本在撤销之前就能调用注册接口，把
//!    「自己的钩子 → 某个尚未登记的原生函数」写进映射表，于是它的钩子
//!    `toString()` 报 `[native code]`——我方为反检测而建的通道被反向用来藏攻击者的钩子。
//! 2. 只校验 `proxyMap.has(original)`，不校验 proxy 侧 ⇒ 可以把**我方包装函数**
//!    重新登记到另一个原生上，同一函数在不同读取通道给出不同 `toString()`，
//!    不一致本身即检测信号。
//!
//! 现设计：注册资格由**闭包内的 `open` 标志**决定（替换 window 上的属性挡不住
//! 已捕获的引用，而替换本身又要求 `configurable: true`——那才是留门）；撤销行由
//! 管线在所有阶段之后发射（`ToStringGuard::close_script()`）。撤销键幂等且
//! 不可替换：页面唯一能用它做的事是**提前**关窗，那只缩小攻击面。
//!
//! 本文件放 `tests/` 而不是各模块内联用例：判定面横跨「守卫脚本」与「管线装配」
//! 两处，而 `protection_mode.rs`/`tostring_guard.rs` 都是零余量行数基线条目。

use aegis_policy_core::protection_mode::{fingerprint_pipeline_with_mode, ProtectionMode};
use aegis_policy_core::shield::FingerprintShield;
use aegis_policy_core::tostring_guard::ToStringGuard;

fn pipeline(mode: ProtectionMode) -> String {
    let shield = FingerprintShield::from_seed([7u8; 32]);
    fingerprint_pipeline_with_mode(&shield, mode, "example.com")
}

const REGISTER: &str = "proxy.register.v1";
const CLOSE: &str = "proxy.register.close.v1";

/// Android 侧注入脚本。R8-CS-SEC-14 把 9 阶段文本按 Stage 边界拆成两个文件：
/// 注册接口在 Seed 段（Stage 1），撤销行在 Shield 段（blob 末尾）——**分处两段**
/// 正是 R8-RS-09 的语义，所以对账必须读两段之和，否则「撤销行没跟着搬」这种
/// 漂移正好落在盲区里。
const KOTLIN_SEED: &str =
    "../../android/app/src/main/java/com/aegis/browser/WebViewHardeningStagesSeed.kt";
const KOTLIN_TAIL: &str =
    "../../android/app/src/main/java/com/aegis/browser/WebViewHardeningStagesShield.kt";

fn repo_file(rel: &str) -> String {
    let manifest = env!("CARGO_MANIFEST_DIR");
    let path = std::path::Path::new(manifest).join(rel);
    std::fs::read_to_string(&path)
        .unwrap_or_else(|e| panic!("读取 {path:?} 失败：{e}（仓库布局契约）"))
}

#[test]
fn maximum_pipeline_closes_the_register_window_last() {
    let script = pipeline(ProtectionMode::Maximum);
    let close_at = script.rfind(CLOSE).expect("管线必须发射撤销键（R8-RS-09）");
    let last_register_use = script
        .rfind(REGISTER)
        .expect("各阶段必须经注册键登记包装函数");
    assert!(
        close_at > last_register_use,
        "撤销必须排在**最后一次**注册使用之后：close={close_at} last_register={last_register_use}"
    );
}

#[test]
fn guard_mode_off_emits_no_closer() {
    // 未启用注册接口时不该发射撤销行——虽然 closer 对缺失的键是 no-op，
    // 但给页面留一个「看得见的空函数」本身就是可枚举的探测面。
    for mode in [
        ProtectionMode::Compatible,
        ProtectionMode::Balanced,
        ProtectionMode::Maximum,
    ] {
        let script = pipeline(mode);
        assert_eq!(
            script.contains(CLOSE),
            mode.enable_tostring_guard(),
            "{mode:?} 的撤销行必须与注册接口同进退"
        );
    }
}

#[test]
fn register_interface_is_flag_gated_and_immutable() {
    let script = ToStringGuard::new().inject_script();
    assert!(script.contains("var open = true;"), "窗口标志必须在闭包内");
    assert!(
        script.contains("if (!open) return;"),
        "注册函数必须先看窗口标志（捕获的引用也不例外）"
    );
    assert!(
        script.contains("if (proxyMap.has(original) || proxyMap.has(proxy)) return;"),
        "original 与 proxy 两侧都要拒重复登记"
    );
    assert_eq!(
        script.matches("configurable: false").count(),
        2,
        "注册键与撤销键都必须不可替换"
    );
    assert!(
        !script.contains("configurable: true"),
        "撤销不得依赖「替换属性」这条需要 configurable: true 的路"
    );
    assert!(
        !script.contains("setTimeout("),
        "撤销不得再排进宏任务（那之前页面脚本已可注册）"
    );
}

#[test]
fn close_script_is_idempotent_and_symbol_keyed() {
    let close = ToStringGuard::close_script();
    assert!(close.contains(&format!("Symbol.for('{CLOSE}')")), "{close}");
    assert!(
        !close.contains(&format!("Symbol.for('{REGISTER}'")),
        "两个 Symbol 串必须互不为子串，否则计数类用例互相污染"
    );
    assert_eq!(
        close.matches("c()").count(),
        1,
        "撤销必须只调一次（幂等靠闭包标志，不靠重复赋值）"
    );
}

#[test]
fn android_shield_shares_the_same_register_discipline() {
    // R8-RS-09 的 Android 面：AD-297 版注册接口是
    // `function(proxy, original) { proxyMap.set(proxy, original); }` +
    // `configurable: false`——零校验、且因为不可替换而**永不撤销** ⇒ 任意页面脚本
    // 在任意时刻都能登记伪造映射（比我方 Rust 侧的 RS-252 校验更弱）。
    // 三端不一致本身就是缺陷，故在此对账而不是只在 Kotlin 用例里自说自话。
    let kt = repo_file(KOTLIN_SEED) + &repo_file(KOTLIN_TAIL);
    assert!(kt.contains("var open = true;"), "Android 缺闭包内窗口标志");
    assert!(
        kt.contains("if (!open) return;"),
        "Android 注册函数未检查窗口标志"
    );
    assert!(
        kt.contains("if (proxyMap.has(original) || proxyMap.has(proxy)) return;"),
        "Android 未做双函数/双侧重复校验"
    );
    assert!(
        kt.contains(CLOSE) && kt.contains("if (c) c();"),
        "Android 缺 blob 末尾的同步撤销调用"
    );
}

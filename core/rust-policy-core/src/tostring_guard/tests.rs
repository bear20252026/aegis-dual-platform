// 测试自 tostring_guard.rs 拆出（第八轮 R8-RS-09·行数红线让位，与 shield/tests.rs、
// PR #76 同法）——子模块经 `use super::*;` 看到父模块私有项，生产可见性零放宽。

use super::*;

#[test]
fn script_contains_proxy_map() {
    let guard = ToStringGuard::new();
    let script = guard.inject_script();
    assert!(script.contains("WeakMap"));
    assert!(script.contains("Symbol.for"));
    assert!(script.contains("Function.prototype.toString"));
}

#[test]
fn script_exposes_register_interface() {
    let guard = ToStringGuard::new();
    let script = guard.inject_script();
    assert!(script.contains("proxyMap.set(proxy, original)"));
}

#[test]
fn script_self_registers_own_overrides() {
    // RS-007 回归：guard 覆盖的 toString/toLocaleString 必须自注册进
    // proxyMap——否则映射恒空、欺骗防护为零
    let script = guard_script();
    assert!(script.contains("proxyMap.set(Function.prototype.toString, origToString)"));
    assert!(script.contains("proxyMap.set(Function.prototype.toLocaleString, origToLocale)"));
}

#[test]
fn register_interface_symbol_keyed_not_named_global() {
    // RS-027 回归：注册接口收敛到 Symbol 键——不再有具名全局常量
    let script = guard_script();
    assert!(script.contains(&format!("Symbol.for('{}')", ToStringGuard::REGISTER_SYMBOL)));
    assert!(
        !script.contains("__AEGIS_REGISTER_PROXY"),
        "具名全局注册接口必须移除"
    );
}

fn guard_script() -> String {
    ToStringGuard::new().inject_script()
}

// —— RS-080 回归（审计 2026-09-25） ——

#[test]
fn to_locale_string_coverage_independent() {
    // RS-080：toLocaleString 与 toString 是两条独立欺骗通道——检测
    // 方可走任一路径，二者必须都进 proxyMap
    let script = guard_script();
    assert!(
        script.contains("Function.prototype.toLocaleString = function()"),
        "toLocaleString 独立覆盖"
    );
    assert!(
        script.contains("origToLocale.call(proxyMap.get(this))"),
        "toLocaleString 代理欺骗路径"
    );
    assert!(script.contains("proxyMap.set(Function.prototype.toLocaleString, origToLocale)"));
}

// —— RS-252 回归（审计 2026-10-01）：注册接口参数防御 + 注入窗口撤销 ——

#[test]
fn register_interface_validates_arguments() {
    // RS-252 + R8-RS-09：注册函数必须校验双函数入参，且 original 与 proxy 两侧
    // 都不得已登记——页面拿到注册接口后不得注入伪造映射（非函数对、链式
    // proxy→proxy、以及把我方包装函数改登记到别的原生上）
    let script = guard_script();
    assert!(
        script.contains("typeof proxy !== 'function' || typeof original !== 'function'"),
        "双函数类型校验"
    );
    assert!(
        script.contains("if (proxyMap.has(original) || proxyMap.has(proxy)) return;"),
        "original 与 proxy 两侧都要拒重复登记"
    );
    // 校验先于登记
    let check = script
        .find("if (proxyMap.has(original) || proxyMap.has(proxy)) return;")
        .expect("校验存在");
    let set = script
        .find("proxyMap.set(proxy, original);")
        .expect("登记存在");
    assert!(check < set, "校验必须先于登记");
}

#[test]
fn register_interface_tamper_proofed() {
    // RS-080/RS-252 + R8-RS-09：注册键与撤销键一律 writable:false +
    // configurable:false。撤销不再靠替换 window 上的属性——替换前已捕获的引用
    // 照样可用，而替换本身要求 configurable:true（那才是留门）；现由闭包标志
    // 让函数体自己失效，因此没有任何一处需要可改写。
    let script = guard_script();
    assert_eq!(
        script.matches("configurable: false").count(),
        2,
        "注册键与撤销键都必须 configurable: false"
    );
    assert_eq!(
        script.matches("writable: false").count(),
        2,
        "两个键都必须 writable: false"
    );
    assert!(
        !script.contains("configurable: true"),
        "撤销通道不得依赖 configurable: true"
    );
    assert!(
        !script.contains("enumerable: true"),
        "注册接口不得可枚举（泄漏进 Object.keys）"
    );
}

#[test]
fn register_window_closes_synchronously_at_blob_end() {
    // R8-RS-09：撤销必须是同步的。RS-252 的 setTimeout(0) 宏任务排在解析任务
    // 之后，头部内联脚本在撤销前仍可注册；现在窗口由闭包标志控制，撤销行由管线
    // 在所有阶段发射完后追加（见 protection_mode 的同名用例）。
    let script = guard_script();
    assert!(!script.contains("setTimeout("), "撤销不得再靠宏任务");
    assert!(script.contains("var open = true;"), "缺闭包内窗口标志");
    assert!(
        script.contains("if (!open) return;"),
        "注册函数未检查窗口标志"
    );
    assert!(
        script.contains(ToStringGuard::CLOSE_SYMBOL),
        "撤销键必须与注册键同为 Symbol.for 通道"
    );
    let close = ToStringGuard::close_script();
    assert!(
        close.contains(ToStringGuard::CLOSE_SYMBOL),
        "closer 必须调用撤销键"
    );
    assert!(
        !close.contains(ToStringGuard::REGISTER_SYMBOL),
        "两个 Symbol 串必须互不为子串（否则计数类用例互相污染）"
    );
}

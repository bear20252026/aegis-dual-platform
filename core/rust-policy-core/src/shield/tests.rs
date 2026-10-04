// 测试自 shield.rs 拆出（第七轮 B4·行数红线让位，与 PR #76 同法）——子模块经
// `use super::*;` 看到父模块私有项，生产可见性零放宽。

use super::*;

#[test]
fn seed_is_32_bytes_hex() {
    let s = FingerprintShield::new();
    assert_eq!(s.seed_hex().len(), 64); // 32 bytes = 64 hex chars
}

#[test]
fn script_contains_seed_marker() {
    let s = FingerprintShield::new();
    let script = s.inject_script();
    assert!(script.contains("__AEGIS_SESSION_SEED"));
    assert!(script.contains("toDataURL"));
    assert!(script.contains("hardwareConcurrency"));
}

#[test]
fn two_instances_have_different_seeds() {
    let a = FingerprintShield::new();
    let b = FingerprintShield::new();
    assert_ne!(a.seed_hex(), b.seed_hex());
}

#[test]
fn from_seed_deterministic() {
    let seed = [42u8; 32];
    let a = FingerprintShield::from_seed(seed);
    let b = FingerprintShield::from_seed(seed);
    assert_eq!(a.seed_hex(), b.seed_hex());
}

// —— RS-081 回归（审计 2026-09-25） ——

#[test]
fn debug_does_not_leak_seed() {
    // RS-081：Debug 输出绝不泄种子（日志/崩溃报告面泄漏 = 会话级
    // 指纹标识符外泄）
    let s = FingerprintShield::from_seed([0xabu8; 32]);
    let debug = format!("{s:?}");
    assert!(debug.contains("***hidden***"), "Debug 遮蔽语义");
    assert!(!debug.contains("ababab"), "Debug 不得含种子 hex 片段");
    // inject_script 确定性：同种子两次生成逐字节一致
    assert_eq!(s.inject_script(), s.inject_script());
}

#[test]
fn seed_bytes_roundtrip_matches_hex() {
    // RS-081：seed_bytes 与 seed_hex 同源一致（管线阶段消费契约）；
    // RS-262：seed_hex 已收敛 util::hex_encode 单源——期望值同源构造
    let seed = [7u8; 32];
    let s = FingerprintShield::from_seed(seed);
    assert_eq!(s.seed_bytes(), seed);
    let hex_from_bytes = crate::util::hex_encode(&s.seed_bytes());
    assert_eq!(hex_from_bytes, s.seed_hex());
}

// —— RS-082 回归（审计 2026-09-25） ——

#[test]
fn canvas_read_channels_all_covered() {
    // RS-082：canvas 读取三通道全覆盖——toDataURL/toBlob/
    // OffscreenCanvas.convertToBlob（漏任一通道 = 噪声绕过）
    let script = FingerprintShield::from_seed([9u8; 32]).inject_script();
    assert!(script.contains("HTMLCanvasElement.prototype.toDataURL"));
    assert!(
        script.contains("HTMLCanvasElement.prototype.toBlob"),
        "toBlob 第二通道必须覆盖"
    );
    assert!(
        script.contains("OffscreenCanvas.prototype.convertToBlob"),
        "convertToBlob 第三通道必须覆盖"
    );
    assert!(
        script.contains("音频指纹噪声由 PerSiteSeed"),
        "Audio 归属文档化（PerSiteSeed 单一负责）"
    );
}

// —— RS-206/207/215 回归（审计 2026-09-26） ——

#[test]
fn canvas_noise_not_gated_on_source_2d_context() {
    // RS-206：噪声包装不得对源画布调用 this.getContext('2d')——
    // WebGL 画布（主流指纹向量）取 2d 上下文得 null 会整体绕过噪声；
    // 无上下文画布则被永久锁定 2d（页面后续 webgl 渲染被破坏）。
    // 离屏副本自身的 off.getContext('2d') 不受影响（副本自建 2d 上下文）
    let script = FingerprintShield::from_seed([9u8; 32]).inject_script();
    assert!(
        !script.contains("this.getContext"),
        "噪声包装不得探测源画布上下文（WebGL 画布噪声绕过 + 2d 锁定）"
    );
    assert!(
        script.contains("off.getContext('2d')"),
        "离屏副本自取 2d 上下文（drawImage 通道）"
    );
}

#[test]
fn canvas_noise_seed_is_per_site() {
    // RS-207：canvas 噪声种子必须按站点派生——会话级常量种子对同会话
    // 的 A/B 两站产生相同噪声图案（跨站 canvas 哈希比对即关联用户）
    let script = FingerprintShield::from_seed([9u8; 32]).inject_script();
    assert!(
        script.contains("aegisEtldPlus1(aegisTopLevelHostname() || '')"),
        "站点键必须取**顶层** eTLD+1（R7-CS1-05：本帧口径让同一跟踪帧在全部宿主站点同种子）"
    );
    assert!(
        script.contains("location.ancestorOrigins"),
        "顶层通道存在（Chromium/WebView 祖先 origin 链）"
    );
    assert!(
        !script.contains("aegisEtldPlus1(location.hostname"),
        "缺陷形态不得回归：直接把本帧 hostname 当站点键"
    );
    // 取不到祖先链时保守退回本帧——不得因顶层链失败而放弃噪声
    assert!(script.contains("return location.hostname;"));
    assert!(
        script.matches("const seed = aegisCanvasSeed();").count() >= 3,
        "三通道噪声必须全部消费站点键"
    );
    // 旧的会话级直取形态必须消失
    assert!(
        !script.contains("__AEGIS_SESSION_SEED.slice(0, 8)"),
        "canvas 不得再直接消费会话级种子切片（跨站关联面）"
    );
    // hardwareConcurrency 随机化仍由会话种子驱动（低熵值非关联向量，保留）
    assert!(script.contains("__AEGIS_SESSION_SEED.slice(8, 16)"));
}

#[test]
fn canvas_noise_perturbs_multiple_channels() {
    // RS-215：R/G/B 三通道扰动——单 R 通道噪声形态与 Android 孪生
    //（AD-175 多通道口径）不一致，跨端噪声形态差异本身即指纹差异面
    let script = FingerprintShield::from_seed([9u8; 32]).inject_script();
    assert!(
        script.contains("imageData.data[i + 1]"),
        "G 通道必须参与扰动"
    );
    assert!(
        script.contains("imageData.data[i + 2]"),
        "B 通道必须参与扰动"
    );
    // alpha（i + 3）不动——透明度变化视觉可察
    assert!(!script.contains("imageData.data[i + 3]"));
}

// —— RS-249/250/257 回归（审计 2026-10-01） ——

#[test]
fn canvas_noise_is_per_pixel_not_constant_offset() {
    // RS-249：噪声必须逐像素混合——(seed+i)%N 在 i+=4 步进下每通道
    // 全图只取常量偏置（减法即还原）。三通道不同常数 Math.imul 混合
    let script = FingerprintShield::from_seed([9u8; 32]).inject_script();
    for (channel, k) in [(0usize, "0x9E3779B1"), (1, "0x85EBCA6B"), (2, "0x27D4EB2F")] {
        let form = if channel == 0 {
            "imageData.data[i]".to_string()
        } else {
            format!("imageData.data[i + {channel}]")
        };
        let expected = format!("Math.imul(i, {k})");
        let line = script
            .lines()
            .find(|l| l.contains(&form) && l.contains("seed ^"))
            .unwrap_or_else(|| panic!("通道 {channel} 缺少逐像素混合形态"));
        assert!(
            line.contains(&expected),
            "通道 {channel} 必须用常数 {k} 混合：{line}"
        );
    }
    // 旧的常量偏置形态必须消失
    assert!(
        !script.contains("(seed + i) % 2"),
        "(seed+i)%N 常量偏置形态必须移除"
    );
    // 三通道噪声形态在全部三个读取通道（toDataURL/toBlob/convertToBlob）一致
    assert_eq!(script.matches("Math.imul(i, 0x9E3779B1)").count(), 3);
}

#[test]
fn hardware_concurrency_replaced_at_prototype_level() {
    // RS-250：hardwareConcurrency 必须原型级 getter 替换——实例遮蔽可经
    // 原型 descriptor 的原 getter 直取原值
    let script = FingerprintShield::from_seed([9u8; 32]).inject_script();
    assert!(
        script.contains(
            "Object.getOwnPropertyDescriptor(Navigator.prototype, 'hardwareConcurrency')"
        ),
        "原型 descriptor 探测"
    );
    assert!(
        script.contains("Object.defineProperty(Navigator.prototype, 'hardwareConcurrency'"),
        "原型级替换"
    );
    assert!(
        !script.contains("defineProperty(navigator, 'hardwareConcurrency'"),
        "实例遮蔽形态必须移除"
    );
    // 保留原 descriptor 属性
    assert!(script.contains("enumerable: oHC.enumerable"));
    assert!(script.contains("configurable: oHC.configurable"));
    // 种子切片消费保留（低熵值非关联向量）
    assert!(script.contains("__AEGIS_SESSION_SEED.slice(8, 16)"));
}

#[test]
fn canvas_seed_uses_public_suffix_aware_etld1() {
    // RS-257：eTLD+1 提取带公共后缀表——a.co.uk 与 b.co.uk 此前共享
    // 站点键（最后两标签同为 co.uk，跨站关联面）
    let script = FingerprintShield::from_seed([9u8; 32]).inject_script();
    assert!(
        script.contains("AEGIS_PUBLIC_SUFFIXES"),
        "最小公共后缀表必须存在"
    );
    assert!(script.contains("'co.uk': 1"), "co.uk 在表中");
    assert!(script.contains("'github.io': 1"), "github.io 在表中");
    // R7-CS2-10：表体由 include_str! 的 contracts 清单生成——第七轮前两端
    // 各自手抄且集合不同（Android 独有的 co.il、C# 独有的 edu.cn 现同表）
    assert!(
        script.contains("'co.il': 1"),
        "co.il 在表中（第七轮前仅 Android 有）"
    );
    assert!(
        script.contains("'edu.cn': 1"),
        "edu.cn 在表中（第七轮前仅 C# 有）"
    );
    assert_eq!(
        script.matches("': 1").count(),
        PUBLIC_SUFFIX_SOURCE
            .lines()
            .filter(|l| !l.trim().is_empty() && !l.trim().starts_with('#'))
            .count(),
        "JS 表条目数必须等于单源清单条目数（不再有手抄副本）"
    );
    assert!(
        script.contains("return parts.slice(-3).join('.');"),
        "公共后缀命中时升级到三标签"
    );
    assert!(
        script.contains("function aegisEtldPlus1("),
        "eTLD+1 提取单源函数"
    );
}

// —— RS-292 回归（2026-10-02）：worker 作用域守卫 ——

#[test]
fn worker_scope_guards_on_all_blocks() {
    // RS-292：worker 注入守卫——HTMLCanvasElement/Navigator 在 worker
    // 作用域未定义，裸引用抛未捕获 ReferenceError（脚本整体中断，
    // 后续阶段全部失效）。各块入口 typeof 守卫 + 注册行 try 包
    //（对齐 per_site_seed 全 try 口径；worker 无 window）
    let script = FingerprintShield::from_seed([9u8; 32]).inject_script();
    assert_eq!(
        script
            .matches("if (typeof HTMLCanvasElement === 'undefined') return;")
            .count(),
        2,
        "toDataURL/toBlob 两块 canvas 入口守卫"
    );
    assert!(
        script.contains("if (typeof OffscreenCanvas === 'undefined') return;"),
        "convertToBlob 块守卫（既有）"
    );
    assert!(
        script.contains("if (typeof Navigator === 'undefined') return;"),
        "hardwareConcurrency 块守卫"
    );
    // 注册行必须 try 包裹（worker 无 window——裸 window 引用同样
    // ReferenceError）。生成态脚本为单大括号形态（format! 的 {{ 已展开）
    assert_eq!(script.matches("try {{ if (window[Symbol.for(").count(), 0);
    let reg_count = script
        .lines()
        .filter(|l| l.contains("try { if (window[Symbol.for("))
        .count();
    assert_eq!(reg_count, 3, "三处注册行全部 try 包裹");
}

#[test]
fn injected_script_is_paren_brace_balanced() {
    // 常驻锚点：第七轮实测 `{psl}` 在 format! 里吞掉花括号→产出 `'co.uk': 1, …`（SyntaxError）
    let script = FingerprintShield::from_seed([7u8; 32]).inject_script();
    assert_eq!(
        script.matches('{').count(),
        script.matches('}').count(),
        "花括号不配平"
    );
    assert_eq!(
        script.matches('(').count(),
        script.matches(')').count(),
        "圆括号不配平"
    );
    assert!(
        script.contains("AEGIS_PUBLIC_SUFFIXES = { '"),
        "后缀表必须是对象字面量"
    );
}

// canvas 噪声公式的回归与性质断言（第八轮 R8-RS-01/02）——自 tests.rs 外迁，
// 与第七轮 B4「测试模块外迁为子模块」同法：父模块的私有项经 `use super::*;` 对本
// 子模块可见，生产可见性零放宽。

use super::*;

#[test]
fn canvas_noise_is_per_pixel_not_constant_offset() {
    // R8-RS-01（第八轮审计 2026-10-04）取代 RS-249 口径：RS-249 用 `Math.imul(i, K)`
    // 把「常量偏置」改成了「看起来逐像素」的形态，但 0x9E3779B1/0x85EBCA6B/
    // 0x27D4EB2F 三枚常数全为奇数，乘积的最低位＝操作数最低位，而 i += 4 使字节
    // 偏移恒为偶 ⇒ `(seed ^ imul(i, K)) & 1` 对每个像素、每个通道都等于 `seed & 1`。
    // 全图同一 ±1 偏移，有效熵 1 bit，试 2 个候选即还原真画布。现统一为 murmur3
    // fmix32 终混 + R/G/B 取互不相交位段（三端同公式）。
    let script = FingerprintShield::from_seed([9u8; 32]).inject_script();
    // 单源噪声函数被三个读取出口各调一次
    assert_eq!(
        script
            .matches("aegisApplyCanvasNoise(imageData, aegisCanvasSeed());")
            .count(),
        3,
        "toDataURL/toBlob/convertToBlob 三出口必须共用单源噪声函数"
    );
    // 退化形态（最低位由偶数步进决定）必须整体消失
    assert!(!script.contains("Math.imul(i, "), "退化混合形态必须移除");
    assert!(
        !script.contains("(seed + i) % 2"),
        "(seed+i)%N 常量偏置形态必须移除"
    );
    // 边界不外溢 + 像素上限：nudge 定义一处、上限声明 1 次 + 三出口各判 1 次
    assert_eq!(
        script.matches("if (current === 255) return 254;").count(),
        1
    );
    // 上限判据：1 处声明 + 三处编码出口 + ⑦ 的两处直读出口
    assert_eq!(script.matches("AEGIS_MAX_NOISE_PIXELS").count(), 6);
    // 噪声函数只有一处定义（防再被逐出口复制成三份各自漂移）
    assert_eq!(script.matches("function aegisApplyCanvasNoise").count(), 1);
}

#[test]
fn canvas_noise_formula_is_actually_non_degenerate() {
    // 本用例不复读脚本字符串，而是复刻同一公式做**性质断言**——第七轮批评的
    // 「token 断言把文本钉死、数学上却恒退化」正是字符串层面永远发现不了的形态。
    // 与上一条互补：这条锁设计，那条锁产出形态。
    fn js_fmix(seed: u32, px: u32) -> u32 {
        let mut m = seed ^ px;
        m = (m ^ (m >> 16)).wrapping_mul(0x85ebca6b);
        m = (m ^ (m >> 13)).wrapping_mul(0xc2b2ae35);
        m ^ (m >> 16)
    }
    let seed = 0x1234_5678u32;

    // 旧公式必为全等序列——这就是「只有 1 bit 熵」的可复现证明
    let old_bit = |i: u32| (seed ^ i.wrapping_mul(0x9E37_79B1)) & 1;
    let old_bits: Vec<u32> = (0..64u32).map(|px| old_bit(px * 4)).collect();
    assert!(
        old_bits.iter().all(|b| *b == old_bits[0]),
        "旧公式在 4 步进下必须恒为同一位（回归证据）"
    );

    // 新公式：同种子 64 个像素的三通道位组必须出现足够多的组合
    let triples: Vec<(u32, u32, u32)> = (0..64u32)
        .map(|px| {
            let m = js_fmix(seed, px);
            (m & 1, (m >> 8) & 1, (m >> 16) & 1)
        })
        .collect();
    let distinct: std::collections::HashSet<(u32, u32, u32)> = triples.iter().copied().collect();
    assert!(
        distinct.len() >= 4,
        "噪声位组合过少（{}）——扰动宽度不足，跨站仍可能归一",
        distinct.len()
    );
    // 三通道不得恒等（恒等＝单通道扰动，可被通道差分抵消）
    let same = triples.iter().filter(|t| t.0 == t.1 && t.1 == t.2).count();
    assert!(same < 40, "三通道恒等的像素过多（{same}/64）");

    // 不同种子必须给出不同序列（per-site 隔离的有效性）
    let a: Vec<u32> = (0..32u32).map(|px| js_fmix(0xAAAA_AAAA, px) & 1).collect();
    let b: Vec<u32> = (0..32u32).map(|px| js_fmix(0x5555_5555, px) & 1).collect();
    assert_ne!(a, b, "跨站点种子必须给出不同噪声序列");

    // 站点键为空时仍须随会话种子变化（R8-RS-02 的退化出口）
    let empty_a: Vec<u32> = (0..64u32).map(|s| js_fmix(0, s) & 1).collect();
    let empty_b: Vec<u32> = (0..64u32).map(|s| js_fmix(0xFFFF_FFFF, s) & 1).collect();
    assert_ne!(empty_a, empty_b, "站点键为空时噪声仍须随会话种子变化");
}

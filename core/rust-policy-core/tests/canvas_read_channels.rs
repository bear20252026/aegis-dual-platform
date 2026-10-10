//! ⑦（第八轮，用户 2026-10-07 定稿）：canvas **像素直读出口**的三端齐平门禁。
//!
//! 被消除的形态：噪声只加在编码三出口（`toDataURL`/`toBlob`/
//! `OffscreenCanvas.convertToBlob`）上，而 `ctx.getImageData(...)` 与
//! `gl.readPixels(...)` 直读到**无噪原文**——页面把两条出口逐像素比对，
//! 差异本身就是「防护存在」的一行判据（R8-RS-03，第七轮把这条记成
//! 「注释与用例名声称全覆盖」的声明失实）。
//!
//! 本文件钉的是两件容易被写坏的事：
//! 1. **两条出口必须用同一个绝对像素序号**（`px = (sy+row)*stride + (sx+col)`）。
//!    子矩形读回若按缓冲区局部序号取噪，同一点在两条出口拿到不同扰动，
//!    等于把旧缺陷换了个位置。
//! 2. **编码路径必须走未包裹的原实现**。先包裹 `getImageData` 再让离屏副本调它，
//!    副本就会被加噪两次——编码出口与直读出口不再一致（node 探针对此做过
//!    双向验证：陷阱版与正确版差 2553 字节）。
//!
//! 为什么放 `tests/`：三端的 canvas 段在第八轮都各自外迁成了独立文件
//! （`src/shield/canvas.rs` / `FingerprintShield.Canvas.cs` / `WebViewHardeningCanvas.kt`），
//! 跨端对账要同时读到这三份；`shield/tests.rs` 又在零余量基线面上。

use aegis_policy_core::shield::FingerprintShield;
use std::path::Path;

const RECT_FN: &str = "function aegisNoiseRectangle(data, seed, sx, sy, sw, sh, stride)";
const PX_FORMULA: &str = "(sy + row) * stride + (sx + col)";
const RAW_CAPTURE: &str = "var AEGIS_RAW_GET_IMAGE_DATA = null;";
const RECT_WRAPPER: &str = "aegisWrapRectRead";
const READ_PIXELS_WRAPPER: &str = "aegisWrapReadPixels";
const BYTE_RGBA_GUARD: &str = "pixels.length === width * height * 4";
const READ_NOISE_CALL: &str =
    "aegisNoiseRectangle(imageData.data, aegisCanvasSeed(), sx, sy, sw, sh, canvas.width)";
const WEBGL_NOISE_CALL: &str =
    "aegisNoiseRectangle(pixels, aegisCanvasSeed(), x, y, width, height, stride)";
const INTERNAL_RAW_CALL: &str = "AEGIS_RAW_GET_IMAGE_DATA.call(octx, 0, 0, off.width, off.height)";
/// 两条直读出口的**调用**（只钉「确实调了噪声函数」这件事）。为什么不像上面两个常量
/// 那样写整行：种子访问器名三端本就不同——Rust/C# 用 `aegisCanvasSeed()`、Kotlin 用
/// `noiseSeed()`，那是 R9-RS-8 逐 token 门禁里显式登记的分歧面（DIVERGENT_REGISTERED），
/// 在本文件里按整行钉会把一条已登记的口径差异误判成缺失。
const READ_NOISE_CALL_HEAD: &str = "aegisNoiseRectangle(imageData.data,";
const WEBGL_NOISE_CALL_HEAD: &str = "aegisNoiseRectangle(pixels,";
/// 编码路径里残留的「已包裹」读法——出现即双重加噪。
const INTERNAL_WRAPPED_CALL: &str = "octx.getImageData(0, 0, off.width, off.height)";

fn repo_file(rel: &str) -> String {
    let manifest = env!("CARGO_MANIFEST_DIR");
    let path = Path::new(manifest).join(rel);
    std::fs::read_to_string(&path)
        .unwrap_or_else(|e| panic!("读取 {path:?} 失败：{e}（仓库布局契约）"))
}

#[test]
fn rust_generated_script_noise_pixel_readback_channels() {
    let script = FingerprintShield::new().inject_script();
    for fragment in [
        RECT_FN,
        PX_FORMULA,
        RAW_CAPTURE,
        RECT_WRAPPER,
        READ_PIXELS_WRAPPER,
        BYTE_RGBA_GUARD,
        READ_NOISE_CALL,
        WEBGL_NOISE_CALL,
    ] {
        assert!(
            script.contains(fragment),
            "Rust 生成脚本缺直读段判据：{fragment}"
        );
    }
    // 单源：矩形噪声循环只有一处定义，两条出口都调它
    assert_eq!(script.matches("function aegisNoiseRectangle").count(), 1);
    // alpha（i + 3）不动
    assert!(!script.contains("data[i + 3]"), "透明度通道不得被扰动");
}

#[test]
fn encoding_paths_read_through_the_unwrapped_original() {
    let script = FingerprintShield::new().inject_script();
    assert!(
        !script.contains(INTERNAL_WRAPPED_CALL),
        "编码路径又走了被包裹的 getImageData ⇒ 副本双重加噪，两条出口不再逐像素一致"
    );
    // 两个 HTMLCanvasElement 出口用 2D 的原实现，OffscreenCanvas 出口用自己那份
    assert_eq!(script.matches(INTERNAL_RAW_CALL).count(), 2);
    assert_eq!(
        script
            .matches("AEGIS_RAW_OFFSCREEN_GET_IMAGE_DATA || AEGIS_RAW_GET_IMAGE_DATA")
            .count(),
        1,
        "convertToBlob 的副本必须走 OffscreenCanvas 自己的未包裹原实现"
    );
}

#[test]
fn three_ends_share_the_pixel_readback_shape() {
    // C# 与 Android 是手抄孪生（核心生成导出接口缺位，B9 的正题）；
    // 只改一端就会让「三端同一防护」再次变成台账假账——本轮已多次实测到该形态。
    let ends = [
        (
            "C#",
            "../../windows/src/Aegis.Windows.App/WebView/FingerprintShield.Canvas.cs",
        ),
        (
            "Android",
            "../../android/app/src/main/java/com/aegis/browser/WebViewHardeningCanvas.kt",
        ),
    ];
    for (label, rel) in ends {
        let source = repo_file(rel);
        for fragment in [
            RECT_FN,
            PX_FORMULA,
            RAW_CAPTURE,
            RECT_WRAPPER,
            READ_PIXELS_WRAPPER,
            // R9-RS-7 的余量：上面 5 段只钉住「函数存在 + 序号同形」，钉不到
            // 「8 位 RGBA 守卫还在」和「两条出口真的调了噪声」——端上删掉
            // `pixels.length === width*height*4` 或删掉整条调用，此前都不会红。
            BYTE_RGBA_GUARD,
            READ_NOISE_CALL_HEAD,
            WEBGL_NOISE_CALL_HEAD,
        ] {
            assert!(
                source.contains(fragment),
                "{label} 端缺直读段判据：{fragment}（三端不齐平即为本项要消除的漂移）"
            );
        }
        assert!(
            !source.contains(INTERNAL_WRAPPED_CALL),
            "{label} 端编码路径不得调用已包裹的 getImageData（双重加噪）"
        );
    }
}

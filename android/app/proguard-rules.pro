# Keep WebView bridge and Activity entry points stable.
-keepclassmembers class * {
    @android.webkit.JavascriptInterface <methods>;
}
-keep public class com.aegis.browser.MainActivity { *; }

# ---- Rust 策略核心桥（JNA）----
# JNA 按「方法名」映射 native 符号（aegis_policy_core_broker_*）——
# R8 混淆 Abi 接口后 System.load 可过但符号查找全部失败 → 静默 null →
# registerSession fail-closed 崩溃（release minified 专属，debug 不复现）。
-keep class com.sun.jna.** { *; }
-keep class com.sun.jna.ptr.** { *; }
-dontwarn com.sun.jna.**
-keep interface com.aegis.broker.NativePolicyCoreBridge$NativePolicyCoreAbi { *; }
-keep class com.aegis.broker.NativePolicyCoreBridge { *; }
# AD-219（2026-09-26 审计）：probe 门禁的 JNA 接口（NativePolicyCoreGate 持有）
# 与 Bridge 的 Abi 同为按名映射接口——漏 keep 时方法名被混淆，
# Native.load 符号查找失败 → 门禁 block → 全部导航 fail-closed 拒绝。
-keep interface com.aegis.broker.NativePolicyCoreGate$NativePolicyCoreAbi { *; }
-keep class com.sun.jna.internal.** { *; }

# ---- androidx.webkit：document-start 注入用 View.setTag(key=R$id) ——
# R8 优化掉未引用的 R$id 字段后 key=0 → IllegalArgumentException 启动崩
-keep class androidx.webkit.R$id { *; }
-keep class androidx.webkit.** { *; }
-dontwarn androidx.webkit.**

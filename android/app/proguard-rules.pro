# Keep WebView bridge and Activity entry points stable.
# AD-098（审计 2026-09-23 清单·A6 批）：MainActivity 全成员 keep 收窄为仅
# 类级——Manifest 实例化只需类名与默认构造器存活；成员级 keep 使全部字段/
# 方法（含后续新增）永远不可混淆/内联，属过度保留。Activity 由 AGP 的
# aapt keep 规则双重兜底，此条为显式声明。
-keepclassmembers class * {
    @android.webkit.JavascriptInterface <methods>;
}
-keep public class com.aegis.browser.MainActivity

# ---- lateinit isInitialized × R8（AD-003 真机回归 2026-09-29 实锤）----
# minified release 启动即崩 "Required value was null"（AddressAndContent:248）：
# R8 full mode 按 @NotNull 声明折叠 `::tabManager.isInitialized` 的空比较为
# true——init() 的幂等检查被折叠成无条件 return，tabManager 永不初始化。
# 实验证据：整类 keep BrowserViewModel 不缓解（优化作用于字段空检查语义，
# 非类名/合并）。修复取代码级：BrowserViewModel.tabManager lateinit → 可空
# 字段（类型系统承载未初始化语义，对优化器免疫）——不设 keep 规则。

# ---- Rust 策略核心桥（JNA）----
# JNA 按「方法名」映射 native 符号（aegis_policy_core_broker_*）——
# R8 混淆 Abi 接口后 System.load 可过但符号查找全部失败 → 静默 null →
# registerSession fail-closed 崩溃（release minified 专属，debug 不复现）。
# AD-279（2026-10-01 审计）：JNA 全量 keep（`com.sun.jna.** { *; }` 含全部
# 内部实现与私有成员）抵消混淆——收窄为「公开类 + 公开成员」（JNA 对外
# API 面：Native/Library/Pointer/Memory 等经反射触达的公开构造与方法）。
# com.sun.jna.internal.**（Cleaner 等按类名反射探测的实现类）保持全量：
# JNA 静态初始化按名字符串加载，成员被剥即运行期 NoSuchMethod。
-keep public class com.sun.jna.** { public *; }
-keep public interface com.sun.jna.** { *; }
-keep class com.sun.jna.internal.** { *; }
-dontwarn com.sun.jna.**
-keep interface com.aegis.broker.NativePolicyCoreBridge$NativePolicyCoreAbi { *; }
-keep class com.aegis.broker.NativePolicyCoreBridge { *; }
# AD-219（2026-09-26 审计）：probe 门禁的 JNA 接口（NativePolicyCoreGate 持有）
# 与 Bridge 的 Abi 同为按名映射接口——漏 keep 时方法名被混淆，
# Native.load 符号查找失败 → 门禁 block → 全部导航 fail-closed 拒绝。
-keep interface com.aegis.broker.NativePolicyCoreGate$NativePolicyCoreAbi { *; }

# ---- androidx.webkit：document-start 注入用 View.setTag(key=R$id) ——
# R8 优化掉未引用的 R$id 字段后 key=0 → IllegalArgumentException 启动崩
# AD-097（审计 2026-09-23 清单·A6 批）：全量 keep 收窄——WebViewCompat 等
# 均为直接调用（R8 按引用自动保留），无需成员级 keep；真正按名敏感的只有
# R$id 常量字段（setTag 的 key 反射面）。保留 R$id + dontwarn 即可。
-keep class androidx.webkit.R$id { *; }
-dontwarn androidx.webkit.**

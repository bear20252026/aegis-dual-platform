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
# AD-294（2026-10-02 发布实证，v2.2.0-beta.51 真机闪退）：AD-279 的「公开类 +
# 公开成员」收窄不成立——JNA 原生库还按名字段访问非公开成员（首个即
# com.sun.jna.Pointer 的 protected peer 字段：原生侧 GetFieldID("peer","J")），
# 收窄后 R8 改名 peer → UnsatisfiedLinkError "Can't obtain peer field ID"
# → 原生核心加载失败 → 必需模式注册会话失败 → 启动即崩（模拟器 x86_64
# minified release 复现，栈见 AegisBroker/AegisCrash）。JNA 对外 API 与
# 内部实现均被 JNI 双向按名触达——成员级全量 keep 是该库的正确粒度，
# 混淆收益（库内部名）不抵运行期风险，恢复 AD-279 前的全量口径。
-keep class com.sun.jna.** { *; }
-dontwarn com.sun.jna.**
-keep interface com.aegis.broker.NativePolicyCoreBridge$NativePolicyCoreAbi { *; }
-keep class com.aegis.broker.NativePolicyCoreBridge { *; }
# AD-219（2026-09-26 审计）：probe 门禁的 JNA 接口（NativePolicyCoreGate 持有）
# 与 Bridge 的 Abi 同为按名映射接口——漏 keep 时方法名被混淆，
# Native.load 符号查找失败 → 门禁 block → 全部导航 fail-closed 拒绝。
#
# R8-AD-02（第八轮审计 2026-10-04）：AD-219 把规则写成 `NativePolicyCoreGate$…`
# （嵌套形态），但该接口在源文件里是**顶层 private interface**——NativePolicyCoreGate.kt
# 的 object 在 :105 已闭合，:117 的 `private interface NativePolicyCoreAbi : Library`
# 缩进为 0，其二进制名是 com.aegis.broker.NativePolicyCoreAbi（无 `$`）。带 `$` 的
# 规则命中 0 个类 ⇒ 方法名照旧被 R8 改名 ⇒ JNA 按名查符号失败 ⇒ LinkageError 折叠为
# Unavailable ⇒ 门禁 block ⇒ 出货 APK 每次远程导航都拒 native_policy_core_unavailable
# （首页是 file:// 不经 broker，故表现为「进程存活、首页正常、所有网站打不开」——
# 恰与 beta.51/beta.52 的「进程存活 + UI 完整渲染」验证口径互补，那类冒烟抓不到）。
# 同仓自证：broker/detekt-baseline.xml 对 Bridge 记作 `NativePolicyCoreBridge.NativePolicyCoreAbi`
# （嵌套，带点号），对 Gate 记作裸名 `NativePolicyCoreAbi`。
# 常驻门禁：ProguardKeepCoverageTest 逐个断言「源码里所有 `: Library` 接口的真实二进制名
# 都出现在本文件的 keep 规则里」——AD-219/AD-294 这一族缺陷从此不靠人工记忆。
-keep interface com.aegis.broker.NativePolicyCoreAbi { *; }

# ---- androidx.webkit：document-start 注入用 View.setTag(key=R$id) ——
# R8 优化掉未引用的 R$id 字段后 key=0 → IllegalArgumentException 启动崩
# AD-097（审计 2026-09-23 清单·A6 批）：全量 keep 收窄——WebViewCompat 等
# 均为直接调用（R8 按引用自动保留），无需成员级 keep；真正按名敏感的只有
# R$id 常量字段（setTag 的 key 反射面）。保留 R$id + dontwarn 即可。
-keep class androidx.webkit.R$id { *; }
-dontwarn androidx.webkit.**

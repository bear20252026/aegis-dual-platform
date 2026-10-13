# Aegis Android

这是 Aegis Android 的第一阶段原生工程骨架，采用 Kotlin + Jetpack Compose + Android WebView。浏览器内核通过 `BrowserEngine` 适配层隔离，后续可以替换为 GeckoView，而不重写页面和业务层。

当前已包含地址栏、HTTP/HTTPS URL 校验、后退、前进、刷新、JavaScript/DOM Storage 基础能力，以及关闭 file/content 访问和多窗口支持等安全默认值。

A-06 整改（国防级审查）：本节的判据是**写在这里的每一项都要能指出实现**
（R9-DOC-12，第九轮 2026-10-13 按实树把原来那句混排的清单拆成两栏——旧写法把未落地项
与已落地项并列在「发布前强制控制」里，正是本节自己明令禁止的「用清单代替实现」）：

- **已落地（可指出实现）**：下载策略与文件名净化 / 危险扩展拦截（`DownloadPolicy`——A-02）、
  权限请求默认拒绝（`BrowserEngine.kt:97` 无条件 `request.deny()`——注意它是**拒绝而非授权 UI**）、
  崩溃诊断（`AegisApplication` 的 `setDefaultUncaughtExceptionHandler`）、
  签名发布流程（`release-android.yml`——B0-S，SHA-256/SBOM/provenance 独立验证）。
- **未落地（不作为已存在的控制）**：Room 历史/书签存储（全树零 `androidx.room`、零 `bookmark`
  引用；`HistoryAction` 只是 WebView 的前进/后退/重载，不是持久化历史）、
  Android Keystore 密钥存储（全树零 `KeyStore`/`KeyGenParameterSpec`）、同步协议
  （`docs/product/supported-features.md` 的「明确不做」已列「云端同步密码」）、
  无痕 profile 清理（**A-03**：全树零 `clearPrivateData` 引用——第八轮 B8 实测；
  主 README 与 `supported-features.md` 的「无痕窗口」条已标为仅 Windows）。
Google Play 发布使用 AAB；自由传播使用同一签名身份生成的 universal APK，并为每个发布文件生成 SHA-256 校验值。

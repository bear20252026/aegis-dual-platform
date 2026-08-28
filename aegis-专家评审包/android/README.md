# Aegis Android

这是 Aegis Android 的第一阶段原生工程骨架，采用 Kotlin + Jetpack Compose + Android WebView。浏览器内核通过 `BrowserEngine` 适配层隔离，后续可以替换为 GeckoView，而不重写页面和业务层。

当前已包含地址栏、HTTP/HTTPS URL 校验、后退、前进、刷新、JavaScript/DOM Storage 基础能力，以及关闭 file/content 访问和多窗口支持等安全默认值。

A-06 整改（国防级审查）：以下为发布前强制控制（不可绕过门禁——不以路线图代替实现）：
- Room 历史/书签存储、Android Keystore 密钥存储、下载管理器（DownloadPolicy 已接入——A-02）、
  权限请求 UI（默认拒绝——A-02）、无痕 profile 清理（clearPrivateData——A-03）、
  崩溃诊断、同步协议、签名发布流程（B0-S——SHA-256/SBOM/provenance 独立验证）
Google Play 发布使用 AAB；自由传播使用同一签名身份生成的 universal APK，并为每个发布文件生成 SHA-256 校验值。

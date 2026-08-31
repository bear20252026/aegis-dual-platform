# Aegis 双平台代码审计报告（2026-08-31）

> 审计方法：4 个专项并行深审（Python 桌面壳 / Android Kotlin / Rust 策略核心 / 前端+CI 供应链），逐行阅读真实代码，全部高危项经独立抽查验证行号属实。
> 分级：高危（可被利用/承诺失守）· 中危（实质缺陷）· 低危（局部问题）· 建议（改进项）。

---

## 一、高危（8 项）

### H-1【桌面壳】新窗口请求完全绕过导航白名单
- 位置：`legacy/windows-pywebview/main_webview.py:554-557`
- 问题：`_on_new_window_requested` 直接 `window.load_url(uri)`，未经 `safe_url`/`_is_navigation_safe` 校验；且 `except: pass` 静默降级、在 WebView2 事件线程直接调 load_url（绕过 NavQueue）。
- 影响：恶意页面 `window.open("file:///C:/...")` 或 `javascript:` URI 可绕过全部白名单（CWE-602）；并发下可复现 Invoke 死锁。
- 修复：`url = safe_url(uri, allow_internal=False)`，校验通过后经 NavQueue 投递导航；拒绝时 `args.put_Handled(True)` 后加载 about:blank。

### H-2【桌面壳】地址栏 URL 单引号断串 → 页面上下文任意 JS 注入
- 位置：`legacy/windows-pywebview/app/shell_toolbar.py:396`（注入点）、`:115`（`inp.value = '...'` 模板）
- 问题：`json.dumps(current_url)[1:-1]` 剥引号后拼入单引号 JS 字符串——json.dumps 不转义单引号，URL 由远程页面自控（`https://evil.com/?x=';payload;//`）即成 XSS。
- 影响：工具栏 JS 上下文中执行任意脚本，可操纵全部桥接 API。
- 修复：不剥引号，模板改 `var AEGIS_URL_JSON = __AEGIS_URL_JSON__; inp.value = AEGIS_URL_JSON;`；同链路 `__TABS_JSON__` 替换顺序（见 M-19）一并修。

### H-3【桌面壳】Agent 白名单校验 fail-open 且会话永不过期
- 位置：`legacy/windows-pywebview/app/tab_ops.py:191-204`
- 问题：整段 allowlist 校验包在 `except Exception: pass` 中——日志故障即跳过拒绝逻辑放行；`getattr(self,"_agent_session",None) or 0.0` 只判真值、无 60s 过期（对比 main_webview.py:206-210 有过期）。
- 影响：Agent 沙箱导航拦截可被一次日志异常击穿；会话一旦激活永久生效。
- 修复：校验移出 try（异常默认 return False）；补 `time.time() - self._agent_session < 60` 判断。

### H-4【Android】WeakHashMap 值强引用键，导航器注册表永不回收
- 位置：`android/.../SecureWebViewFactory.kt:32`（WeakHashMap）、`:368-370`（SecureNavigator 持 webView 强引用）
- 问题：值→键强引用使 WeakHashMap 键永不可达；每次 newTab 泄漏一个 WebView 及全部 Chromium 资源。
- 修复：改普通 Map + `close()/onDestroy` 显式 remove；或 SecureNavigator 改 `WeakReference<WebView>`。

### H-5【Android】openGeogebra 绕过 Broker 直接 loadUrl
- 位置：`android/.../AegisHomeBridge.kt:83-89`
- 问题：任意第三方页面可调 `AegisBridge.openGeogebra()` → `wv.loadUrl("file:///android_asset/...")`，绕过 SecureNavigator→Broker 授权链（`allowFileAccess=false` 不影响 android_asset）。
- 修复：改走 navigatorFor(wv) 受控导航路径，或将 HOME_URL 纳入 Broker 本地白名单统一决策。

### H-6【Android】下载防线是死代码，WebView 下载完全未接线
- 位置：`android/.../DownloadPolicy.kt` 全文件（全仓无 `setDownloadListener`）；README.md 宣称"A-02 已接入"与实态不符。
- 影响：危险扩展确认机制不存在，点击下载链接静默失败（用户侧表现为"下载坏了"）。
- 修复：工厂接线 `setDownloadListener`，经 DownloadPolicy 判定 + Broker 决策后交 DownloadManager；同步修正 README。

### H-7【Rust】策略/能力两层校验从未接入导航决策链
- 位置：`core/rust-policy-core/src/ffi/broker.rs:257,432`（只走 validate_action）；`broker.rs:143-168`（`ContextBroker::evaluate` 无生产调用点）
- 问题：文档承诺的三层管线 `policy.evaluate → capability.validate → session` 在 FFI 通路不执行，deny-all 默认策略引擎形同虚设——有效会话内任意 URL 直接 Allow（c_abi/mod.rs:232 测试佐证）。
- 修复：`FfiBroker::evaluate_navigation` 接入 `ContextBroker::evaluate`；或显式修改文档声明导航策略由外部承担并删除误导注释；补"deny-all 引擎下导航必拒"集成测试。

### H-8【Rust】adblock 父域检查逐单段匹配，语义错误
- 位置：`core/rust-policy-core/src/adblock.rs:114-121`
- 问题：注释称"父域匹配"，实现为 `host.split('.')` 逐段精确匹配——`ads.example.com` 会拿 `ads`/`example`/`com` 三个单词比对；两段父域（`ads.com`）永远无法命中。
- 影响：黑名单含常见单词域（`m`/`app`）即大面积误拦；含 `com` 则全网拦截。
- 修复：`while let Some((_, rest)) = host.split_once('.') { check(rest) }`，黑名单入口做注册域归一。

---

## 二、中危（20 项）

### 桌面壳（6）
| # | 位置 | 问题 | 修复 |
|---|---|---|---|
| M-1 | main_webview.py:531-532 | `_create_window` 失败 `return 1` 而非 None，`if window is None` 永不触发 → 启动后 AttributeError | 改 `return None` |
| M-2 | app/session_store.py:76-81 | session.json（完整浏览 URL）明文落盘未调 `harden_perms`（database.py:61-69 有先例） | `os.replace` 后补 `harden_perms` |
| M-3 | app/navigation.py:71-79 | 受信来源仅凭 `host == ""` 判定——data:/blob: 页全放行 | 显式白名单：shell 目录内 file:// 或 about:blank |
| M-4 | main_webview.py:226 | 每个网络请求回调内读盘解析 sitemap JSON | 启动加载 + mtime 失效缓存 |
| M-5 | app/mcp.py:276 | params 类型未校验，list/int 时 `.get` 抛 AttributeError 逃逸 handle_request | `isinstance(params, dict)` 否则 -32600 |
| M-6 | app/history_store.py:143 | 每次搜索全量重建 FTS 索引 O(N) | meta 表记 schema 版本，仅首次 rebuild |

### Android（6）
| # | 位置 | 问题 | 修复 |
|---|---|---|---|
| M-7 | AegisHomeBridge.kt:44-47 | logError 允许任意页面写任意字符串进 logcat；bridge-guard JS 拦不住 @JavascriptInterface 直调 | 限长 + origin 门禁，或仅注入受信首页 |
| M-8 | AegisWebViewClient.kt:147,196；BrowserEngine.kt:87,94 | release 无门控打印完整 URL/标题/搜索词（浏览历史带 token URL 进 logcat） | 统一日志门面，release 裁剪为 scheme+host |
| M-9 | AegisWebViewClient.kt:158-163；SecureWebViewFactory.kt:71 | 渲染进程崩溃后 onRendererGone 为空回调——白屏无恢复 | 回调中重建标签或提示重载 |
| M-10 | MainActivity.kt:251-264 | onDestroy 不调 navigatorFor(it)?.close() → 静态 broker 跨 Activity 累积 session | onDestroy 遍历 close() |
| M-11 | BrowserViewModel.kt:90；BrowserEngine.kt:90-95 | 地址栏/标题永不随导航更新（Tab.url 创建时写死）——用户无法核验当前 URL，钓鱼观感风险 | onPageStarted 上抛 ViewModel 更新 |
| M-12 | AndroidManifest.xml:23-29 | VIEW/BROWSABLE intent-filter 声明但 onCreate 不消费 intent、无 onNewIntent | 补 onNewIntent→navigateExternal 或删 filter |

### Rust（5）
| # | 位置 | 问题 | 修复 |
|---|---|---|---|
| M-13 | https_only.rs:52,43-44 | `starts_with("http://")` 大小写敏感——`HTTP://` 绕过强制升级；allow_http 不归一 | scheme/host 全部 `eq_ignore_ascii_case`，host 经 origin::canonicalize |
| M-14 | update_manifest.rs:45-49 | canonical JSON 字符串不转义引号/控制字符，与 Python json.dumps 字节流不一致 | 复用 `serde_json::to_string`，补跨语言 golden-vector 测试 |
| M-15 | ffi/broker.rs:16,123,441-448 | issued_actions 授权账本无上限无淘汰（对比 consumed_nonces 有 50k 上限）；锁 poisoned 时静默跳过清理 | 设上限 fail-closed + 惰性清理；poisoned 返回 deny |
| M-16 | broker.rs:57-97,127 | 会话池无上限（C ABI 直暴露），evict_expired 全库无调用——内存耗尽 DoS 面 | validate 时顺带删过期；入口周期 evict；软上限 |
| M-17 | origin.rs:53 | IDN 不转 punycode、尾部点不剥离——与内核 origin 语义分裂 | 拒绝非 ASCII host 或接入 idna crate；剥尾点 |

### 前端 + CI（3）
| # | 位置 | 问题 | 修复 |
|---|---|---|---|
| M-18 | shared/shell/start.html:648-652 | openGeo 回调引用未定义变量 `ok`（Host.openGeo 调 onFail() 不传参）——ReferenceError，画板缺失时按钮永不置灰 | `function (ok){...}` 或 openGeo 内传参 |
| M-19 | shell_toolbar.py:394-399 | `__TABS_JSON__` 先替换，`__AEGIS_URL__` 全文替换会命中远程页标题中的字面量占位符，可破坏注入 JS 结构 | URL 先替换，或正则单次参数化替换 |
| M-20 | .github/actions/prepare-geogebra/action.yml:23 | GeoGebra zip 外部下载无 SHA256 校验，直接进 APK/安装包制品 | 仓内登记 sha256，下载后 `sha256sum -c` |
| M-21 | .github/workflows/release-windows.yml:148-182 | installer-pywebview 作业（最终分发 EXE）无 needs:pin-check、无 SHA256SUMS、无 SLSA attestation | 补门禁并复用 write_checksum_json + attest |

---

## 三、低危（15 项，摘要）

| # | 位置 | 问题 |
|---|---|---|
| L-1 | api_bridge.py:47-57 | 死代码 `_row_to_tuple`（HistoryMixin 已有同名）——删 |
| L-2 | bridge/history.py:34,57,78 | `limit or 100` 把合法 0 吞成 100——改 `is not None` |
| L-3 | bridge/*.py 6 处 | 手写 log_event 导入+try/except，未用 event_log 统一入口 |
| L-4 | shell_toolbar.py:142,231 | 注入 JS 调不存在的 show_menu/view_source——死功能 |
| L-5 | tab_ops.py:242-245 | 限流状态跨线程无锁——纳入 self._lock |
| L-6 | history_store.py:55-57 | 注释称"无痕用内存库"与实际行为不符 |
| L-7 | TabManager.kt:107 | suspendAll 空表 `tabs.first()` 抛异常——改 firstOrNull |
| L-8 | MainActivity.kt:266-270 | onPause 未挂起后台 JS；resumeCurrent 是死代码 |
| L-9 | MainActivity.kt:239-249 | onKeyDown 返回逻辑在 targetSdk36 手势导航下不可达——死代码 |
| L-10 | MainActivity.kt:167,187；BrowserViewModel.kt:143 | `!!` 与缺 isInitialized 守卫不统一 |
| L-11 | build.gradle.kts:107 | release 关 R8（已知止血项，记录在案） |
| L-12 | AegisWebViewClient.kt:28,154 | allowedHttpDomains 无调用方且与 HTTPS-only 语义冲突——删 |
| L-13 | ffi/mod.rs:164-170 | hex_seed_to_bytes 非法字符静默置 0，种子熵无声削弱——fail-closed |
| L-14 | util.rs:36-62 vs origin.rs | 两套 host 提取语义分裂（userinfo/IPv6 处理不同）——adblock 改用 try_parse_external |
| L-15 | security_policy.rs:11 | scheme 白名单含 file/content，与 origin.rs fail-closed 双轨矛盾——收敛单一入口 |

## 四、建议（8 项）

1. credential_guard.py:20-23 脱敏键补 `authorization/cookie/session_id`。
2. database.py:61-69 harden_perms 移到首次创建执行一次（当前每连接执行）。
3. matcher.rs:142-176 glob_subsumes 无记忆化，入运行时前补 memo。
4. ffi/broker.rs:474-482 generate_nonce 64 次 String 分配/次导航——查表 hex 写固定缓冲。
5. ffi/broker.rs:398,432,441 三锁串行——合并 ledger 进 inner 一把锁。
6. broker.rs:143,127 等 `ContextBroker::evaluate`/`evict_expired`/security_policy 全模块：接入或删除（死代码清单）。
7. 准备-geogebra action 的 `${{ inputs.* }}` 与 workflows 的 `${{ github.ref_name }}` 内插改 env: 传递。
8. supply-chain.yml cargo-audit 未固定版本（对比 cargo-ndk 已 pin）——pin 版本；全部 workflow 补 concurrency + timeout-minutes。

## 五、正面确认（审计中验证合格项）

- Rust FFI 边界：全部 extern "C" 有 catch_unwind、null 拒绝、统一 string_free、错误返回 deny JSON；unsafe 仅 3 处均有 SAFETY 注释。
- Android 基线：allowBackup=false、cleartext=false、仅 INTERNET 权限、文件/内容访问全关、第三方 Cookie 禁、@JavascriptInterface 白名单齐全。
- 前端：无 innerHTML/insertAdjacentHTML、无 URL 参数拼接；标题经 textContent 渲染；asset_scheme 白名单+NFKC+穿越校验规范。
- CI：action 全部 40 位 SHA pin、无 pull_request_target、keystore 不落日志、Python 脚本无 shell=True、update_verifier 有 Ed25519+回滚拒绝。

## 六、健康度评分（1-10）

| 模块 | 安全 | 质量 | 性能 | 可靠 | 可维护 | 综合 |
|---|---|---|---|---|---|---|
| Python 桌面壳 | 6 | 7.5 | 6 | 6 | 8 | **6.7** |
| Android | 6 | 7 | 5 | 6 | 8 | **6.4** |
| Rust 策略核心 | 6.5 | 6 | 6 | 7 | 7 | **6.5** |
| 前端 | 8 | 8 | 8 | 7 | 8 | **7.8** |
| CI/供应链 | 7 | 8 | 8 | 8 | 7 | **7.6** |

**总体：6.8/10**。安全基线（SHA pin、SLSA、fail-closed 骨架、DOM 安全 API）显著高于同类项目；失分集中在「承诺与实现脱节」：策略层未接线（H-7）、下载防线死代码（H-6）、README 与实态漂移、三处白名单旁路。

## 七、优先级改进路线图

**P0（本周，安全承诺失守）**
1. H-1 新窗口白名单旁路（桌面壳）
2. H-2 地址栏单引号 XSS（桌面壳，连带 M-19）
3. H-3 Agent fail-open（桌面壳）
4. H-5 openGeogebra 旁路（Android）
5. H-7 Rust 策略层接线或显式摘除承诺

**P1（两周内，实质缺陷）**
6. H-4 WeakHashMap 泄漏 + H-6 下载接线（Android，同批）
7. H-8 adblock 父域 + M-13 HTTPS 大小写（Rust）
8. M-15/M-16 集合无界（Rust）
9. M-2 session.json 权限 + M-1 启动返回值（桌面壳）
10. M-20/M-21 供应链补链（CI）

**P2（一个月内，体验与可靠性）**
11. M-8 日志脱敏、M-9 崩溃恢复、M-11 地址栏同步、M-12 intent 消费（Android）
12. M-18 openGeo 回调 bug、M-4 sitemap 缓存、M-6 FTS 增量（前端/桌面壳）

**P3（随迭代，清理与还债）**
13. 全部低危死代码清单（L-1/4/8/9/12 + 建议 6）一次性清理
14. 性能项（建议 4/5）与防御加固（建议 1/2/3/7/8）

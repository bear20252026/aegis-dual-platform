# Aegis 全仓第三轮审计——241 项新发现(2026-10-01)

**范围**:接续 docs/audit/full-audit-2026-09-26-229-items.md(229 项全闭环)之后的**新一轮全仓新鲜扫描**——六区并行审计代理逐文件核对当前代码状态(含 D1 真机批之后),凡与已登记条目相同或高度相似的一律剔除;另由正典门禁实测(0 警告基线/ruff 根口径/gradle 弃用告警)补充 7 项实证条目。
**方式**:6 路并行审计(Windows C# / Android / Rust 核心 / Python·契约·发布链 / Web 资产·文档 / CI·根配置·盲区),每项带 file:line 证据与具体修复方案;关键 P1/P2 声明由主审计代理二次抽查复核(NtpAssets Allow、sync_versions 断裂、CS0168 均实证)。
**总量**:**245 行登记,去重合并 4 行(WB-146≡CS-334、WB-153≡SP-188、WB-154≡SP-185、WB-155≡SP-190)后 241 项;发布链批(tag/真机实证)追加 10 项 → 251 项**:问题 140+8 / 提升 101+2;P1×4 / P2×27 / P3×220。

> 编号体系:延续既往(CS=C# 正典栈,AD=Android,RS=Rust 策略核心,PY=Python/CI/契约/发布链,WB=Web 资产+文档,SP=补充盲区)。
> 优先级:P1=必须(缺陷/安全/门禁失效),P2=应该(正确性/一致性/重要测试),P3=可以(打磨/补测/归置)。
> 每行格式:`ID | 优先级 | 类型 | 位置 | 问题 → 方案`。「问题」=缺陷/安全/正确性/门禁失效;「提升」=补测试/重构/可观测性/文档失实修正/治理。

---

## 0. P1/P2 汇总

| ID | 优先级 | 类型 | 位置 | 问题 → 方案 |
|---|---|---|---|---|
| CS-334 | P1 | 安全/指纹暴露 | windows/.../Chrome/Ntp/NtpAssets.cs:107-119 | 虚拟主机映射用 `Allow`(等效 ACAO:* 全放行)——任意远程站点 fetch ntp/geo 资产可读,一行探测识别 Aegis 用户,指纹防护被单点旁路;GeoGebra 整包也被任意外站热链 → 两处改 `Deny`(同源自加载不受影响),补"远程页探测必失败"回归说明 |
| CS-335 | P1 | 安全/指纹防护失效 | windows/.../WebView/FingerprintShield.cs:103-116 | canvas 噪声前置 `getContext('2d')` 门禁:WebGL 画布取 2d 上下文得 null→无噪声回退,且无上下文画布被永久锁 2d——RS-206 已修 Rust 侧,C# 孪生未修 → 删门禁,离屏副本 drawImage 取像素加噪;补 WebGL 画布回归 |
| CS-336 | P2 | 安全/跨站关联 | windows/.../WebView/FingerprintShield.cs:96,106 | siteSeed 计算后零引用(死代码),canvas 噪声用会话级种子——同用户跨站噪声相同,可跨站关联(RS-207 孪生) → canvasProxy 改用 per-site 种子(加载时缓存),补跨域差异断言 |
| CS-337 | P2 | 安全/凭据落盘 | windows/.../Core/Security/UrlRedactor.cs:19 | `GetLeftPart(Authority)` 含 userinfo——`https://token@host/` 被拒后凭据完整落 security.log → 改 Scheme+HostAndPort 组装(剥 userinfo),补用例 |
| CS-338 | P2 | 功能缺陷 | windows/.../Chrome/FindBarController.cs:79-94 | 计数脚本返回 Promise,ExecuteScriptAsync 不等待→恒 "null"→命中计数恒 0,查找条永远"无结果" → 改同步表达式计数,返回串容错反序列化 |
| CS-339 | P2 | UI 冻结面 | windows/.../WebView/HostWebView.cs:78-90 + Core/UrlSafety.cs:242 | 帧导航在 UI 线程同步 DNS 解析,恶意页嵌多个不可解析 http iframe 逐帧冻结 UI → 帧路径只读缓存,未命中 fail-closed 取消+后台预热 |
| CS-374 | P2 | 门禁回归 | windows/.../Chrome/WindowTheme.cs:76 | `catch (Exception _)` 触发 CS0168×2——正典「0 警告」基线已破(本轮门禁实测) → 改 `catch (Exception)`,重跑 build 验证 0 警告 |
| AD-252 | P1 | 安全/URL 混淆 | android/broker/.../OriginPolicy.kt:60-75 | 尾点 host(`localhost.`/`aegis.local.`)绕过:java.net.URI 保留尾点放行,Chromium 归一剥尾点命中白名单成 trustedCaller;canonicalOrigin 产出幻影 origin 绑进 AuthorizedAction → 备用编码判定前 `endsWith(".")` 即拒(或整链拒尾点),补 `https://localhost./` 等向量 |
| AD-253 | P2 | 指纹防护缺陷 | android/.../WebViewHardening.kt:296-299 | canvas 噪声 `(seed+i)%2` 在 i+=4 步进下退化为每通道全图常量偏移(共 8 种组合),减法即可还原 → 改逐像素 PRNG(mulberry32 类),断言相邻像素噪声不一致 |
| AD-254 | P2 | 正确性/生命周期 | android/.../TabManager.kt:97 | closeTab 对后台标签也把激活位切到被关位置——关后台标签激活跳变+双活跃 WebView → 按 index 与 activeIndex 关系分支保持激活,原激活标签 pause;补用例 |
| AD-255 | P2 | 正确性/决策面 | android/webview-adapter/.../AegisWebViewClient.kt:73-113 | 主框架判定只看 `isHttp && isForMainFrame`:https 主框架链接落入子框架轻量分支——确认对话框永不出现、Deny 不上抛(静默死链) → 以 isForMainFrame 为主分支,scheme 仅决定升级;补测试 |
| AD-256 | P2 | 安全/策略旁路 | android/webview-adapter/.../AegisWebViewClient.kt:54-115 | 30x 重定向/POST/reload 不经 shouldOverrideUrlLoading——放行后 302 跳 userinfo 形态/确认策略 URL 整链绕过 → onPageStarted 对主框架 URL 轻量复核,Deny 即 stopLoading+上抛 |
| AD-257 | P2 | 日志泄敏 | android/.../AegisHomeBridge.kt:109 | 拒绝路径明文记录完整 URL(含 query token)——脱敏口径第三处漏接 → 改 LogRedact.redact |
| PY-216 | P1 | 发布链工具断裂 | scripts/sync_versions.py:75-76 + android/app/build.gradle.kts:104,108 | gradle 版本已改构建期消费 properties(`versionCodeFromProperties`),sync_versions 仍按字面量正则替换——实测必抛 RuntimeError,自 09-23 起不可用;KNOWLEDGE_BASE 仍宣称可用 → 删两行 gradle 写入(已单源接线),补真实仓库 main() 集成测试,同步更正文档 |
| PY-217 | P2 | 门禁缺口+lint 回归 | tests/python/ 六文件 + legacy-python-guard.yml:77,86 | ruff 实测 40 错(F401/F811×7/I001×14/RUF100×18/RUF012/PLW1510);CI 两处 ruff 均不扫 tests/python、根 validate_release.py、core/bindings——per-file-ignores 声称在门禁面实际零覆盖 → 清 40 错+门禁面接线 |
| PY-218 | P2 | 工具永久失效 | release/tools/verify_manifest/verify_manifest.py:67-75 | trusted_keys.json 的 str 值直接传 Ed25519PublicKey.from_public_bytes 必抛 TypeError 被吞——CLI 对任何真实密钥恒拒;单测用 monkeypatch shim 掩盖 → main() 按 base64/hex 解码为 32 字节,测试改走真实路径 |
| PY-219 | P2 | 去重残留撞名 | scripts/dedup_release_assets.py:57-69 | 改名产物不写 seen——跨目录原生同名资产再冲突,防的正是该 404 场景 → rename 后 seen[target.name]=target,冲突退出 1;补三目录撞名用例 |
| PY-220 | P2 | 工具链双源漂移 | legacy/windows-pywebview/requirements-dev.txt vs requirements-ci.in | 两把锁 ruff 0.16.3/0.16.9、mypy 2.3.0/2.3.1、pytest 9.0.3/9.1.1——guard 装 dev 锁却跑活跃树门禁,规则口径漂移 → dev 锁与 requirements-ci.in 同版本(guard 或改装 requirements-ci) |
| PY-221 | P2 | 依赖声明缺口 | release/update_verifier.py:22-23 + requirements-ci.in | cryptography 顶层导入不在活动工具链锁——只装 requirements-ci.txt 的环境 import 即失败(现仅靠 legacy 锁传递依赖侥幸) → cryptography 入 requirements-ci.in 并 pip-compile --generate-hashes 重锁 |
| PY-222 | P2 | 发布窗口测试盲区 | tests/python/ + release.yml | 发布链验证器 207 单测只在周 cron 跑——tag 发布窗口零 pytest,工具回归不可见 → contracts.yml(或 release verify-gate)接线 `pip install --require-hashes -r requirements-ci.txt && python -m pytest tests/python -q` |
| SP-177 | P2 | 配置失实/供应链 | CONTRIBUTING.md:27 + SECURITY.md:43 + contracts.yml:102 + release-windows.yml:49 | 三处声称 packages.lock.json 锁定 NuGet,实际全仓无锁文件(缓存 glob 恒空)——NuGet 传递依赖未锁 → 三个 csproj 启用锁文件+提交,CI restore/publish 加 --locked-mode;或三处口径如实改写 |
| SP-178 | P2 | 供应链/pin 可审计性 | release.yml 等 15 处 action pin | 经 git ls-remote 核对:8 个 SHA 不被上游任何 release tag 引用(6 个=上游 main HEAD 未发布提交;setup-java 与 gh-release 为孤儿提交,后者持发布写权限)——pin 无法归属已发布版本、不可审计 → 全部重 pin 到现行 release tag+#vX.Y.Z 注记 |
| SP-179 | P2 | 门禁缺口 | .github/workflows/release.yml:226-268 | publish 去重改名后重生成的 SHA 清单发布前零对账——verify-gate 验的是改名前清单,坏清单可直接上 Release → 重生成后、re-attest 前复跑 verify_checksum_json/sha256sum -c |
| WB-133 | P2 | 前端缺陷/数据丢失 | shared/shell/start.snake.js:435-447 + start.css:245 | 键盘守卫判内联 display,浮层初始由 CSS 类隐藏——加载后首开前按 Escape 即 close()→persistBest 把未 loadBest 的 best=0 写入 localStorage,已存最高分被清零 → 模块级 isOpen 标志;补回归 |
| WB-152 | P2 | 文档失实 | docs/product/supported-features.md:24 | Android 清单列「书签宫格」——android 全树零 bookmark 引用,功能不存在 → 移除或改述 Windows 专属 |
| RS-239 | P2 | FFI 健壮性 | core/rust-policy-core/src/c_abi/mod.rs:37 | read_utf8 的 `'a` 不在输入位置是自由生命周期——签名层 unsound 依旧(RS-211 无效修复) → 返回 String(调用点全部立即 to_owned)或 unsafe fn+契约 |
| RS-240 | P2 | 控制失效 | core/rust-policy-core/src/broker.rs:234-243 | 三层管线只 validate 不 consume——max_uses 永不推进,一次性能力可无限次通过,耗尽控制形同虚设 → evaluate 成功后追加 consume(或原子 try_consume),补管线级耗尽用例 |
| RS-241 | P2 | 防护缺陷 | core/rust-policy-core/src/per_site_seed.rs:108-118 | getChannelData 对底层数组写噪声——二次读同 buffer 再叠加,双读比对即检出(canvas 双读漂移的 Audio 孪生) → WeakSet 按 buffer+channel 首次标记;补双读一致断言 |
| RS-242 | P2 | 伪装可检测 | core/.../query_strip.rs:193-210、ext_proxy.rs:148-176、font_norm.rs:104-162、contracts/schemas/bridge_guard.template.js | 四处覆盖未注册 ToStringGuard——`fetch.toString()` 一行暴露包装源码(内含品牌特征) → 各覆盖点补 proxy.register.v1 注册(bridge 模板四出口同) |
| RS-243 | P2 | fail-open | core/rust-policy-core/src/action_policy.rs:148-158 | context_contains_token 前边界缺 `.`——deny 条件 "example.com" 对子域 context 不命中,Deny 在子域静默失效 → 边界补 b'.' 或先 canonicalize;补子域用例 |
| RS-244 | P2 | 覆盖缺口 | core/rust-policy-core/src/timer_prec.rs:110-196 | Event.prototype.timeStamp 与 performance.timeOrigin 未圆整(RS-074 半面) → 注入二者 getter 圆整包装或文档登记缺口 |

## 1. Windows C# 正典栈(CS-334..375,42 行)

| ID | 优先级 | 类型 | 位置 | 问题 → 方案 |
|---|---|---|---|---|
| CS-334 | P1 | 问题/安全 | NtpAssets.cs:107-119 | (见 P1 汇总) |
| CS-335 | P1 | 问题/安全 | FingerprintShield.cs:103-116 | (见 P1 汇总) |
| CS-336 | P2 | 问题/安全 | FingerprintShield.cs:96,106 | (见 P1/P2 汇总) |
| CS-337 | P2 | 问题/安全 | UrlRedactor.cs:19 | (见汇总) |
| CS-338 | P2 | 问题/功能 | FindBarController.cs:79-94 | (见汇总) |
| CS-339 | P2 | 问题/UI 冻结 | HostWebView.cs:78-90 | (见汇总) |
| CS-340 | P3 | 问题/校验缺口 | BookmarkStore.cs:21-34,87-97 | Add/Rename/Import 无长度钳制(CS-319 只落 HistoryStore)——页面可控任意长 title/URL 落库回读渲染 → 复用 ClampText 语义钳制,补用例 |
| CS-341 | P3 | 问题/校验缺口 | TabSessionStore.cs:41-56 | 会话 Save 对 url/title 无钳制——单页可撑大 tabs.db → INSERT 前 2048/256 钳制(代理对安全) |
| CS-342 | P3 | 问题/可观测 | HistoryWindow.xaml.cs:107-115 | Task.Run 内 SQLite 异常成为未观察任务异常,UI 停旧页无提示 → 体内 try/catch+EmptyHint 失败态+SecurityLog |
| CS-343 | P3 | 问题/XAML | HistoryWindow.xaml:100-105,209-213 | 行分隔线永不显示:DataTrigger 绑 AlternationIndex==0 但列表未设 AlternationCount → HistoryList 补 AlternationCount="100000" |
| CS-344 | P3 | 问题/死数据面 | DownloadRecordStore.cs:8-10,59 | 注释承诺"重启后仍可查看"但 All() 零调用——带 token 的 URL 无收益常驻磁盘 → DownloadsWindow 合并展示或删写入并改注释 |
| CS-345 | P3 | 问题/半修 | Broker.Tests.csproj:21 | xunit.runner.json 引用的文件不存在——CS-256 只落 Core.Tests → 复制配置文件进项目目录 |
| CS-346 | P3 | 问题/测试副作用 | BrowserPolicyBrokerTests.cs:270-307 | 测试写真实用户目录 security.log → fixture 设 SecurityLogDirOverride 临时目录并还原 |
| CS-347 | P3 | 问题/韧性 | WebViewEnvironment.cs:22-33 | Lazy 永久缓存失败——首建失败后所有标签不可用到重启 → 失败可重置门闩(SemaphoreSlim),成功结果保留单次创建语义 |
| CS-348 | P3 | 问题/注释互斥 | OriginPolicy.cs:40-44 vs UrlSafety.cs:67-71 | 两文件对 .NET 八进制解析留相反注释——必有一处失实 → 确定性实验统一,注明两防线分工 |
| CS-349 | P3 | 问题/一致性 | InPrivateWindow.xaml + .cs:115 | 无痕窗口零加载指示(主窗有 LoadingBar) → 补 2px 不定态 ProgressBar+事件接线 |
| CS-350 | P3 | 问题/性能 | MainWindow.xaml.cs:291-300 + ThreatFeed.cs:197-214 | 启动链 UI 线程同步 LoadCached(≤5MB) → 空快照启动+Task.Run 回投 |
| CS-351 | P3 | 问题/安全 | DownloadPolicy.cs:21-27 | 危险扩展缺 .url/.website/.appref-ms/.application/.settingcontent-ms/.jnlp → 集合补齐+确认用例 |
| CS-352 | P3 | 问题/隐私 | WebViewEnvironment.cs:37-89 | 无痕临时目录崩溃后永久残留 → 启动扫描 %TEMP%\Aegis.InPrivate.* 清未持有残留 |
| CS-353 | P3 | 问题/fail-safe | TabSessionStore.cs:116 + BookmarkStore.cs:119-129 | 库损坏 BLOB 抛 InvalidCastException 逃逸(Load 启动失败/管理器裸抛) → Load 扩捕归并空+日志;Reload 包 try/catch |
| CS-354 | P3 | 问题/边界 | DownloadPolicy.cs:91-104 | 超长扩展名打破 200 上限(1+ext 可达 500+) → 截断后二次校验总长,超限弃 ext 回退名 |
| CS-355 | P3 | 问题/UX | MainWindow.xaml.cs:582-586 | 策略拒绝导航被 OperationCanceled 过滤——零可见反馈 → deny reason 经 ShowRejection 呈现 |
| CS-356 | P3 | 问题/边界 | FaviconService.cs:175 | IPv6 host 无方括号拼非法 URL→永远失败入负缓存 → host 含 ':' 加括号,补用例 |
| CS-357 | P3 | 问题/健壮性 | DownloadsWindow.xaml.cs:98 vs 124-131 | OpenFile_Click 在 try 外读 FilePath——RCW 释放后 COM 异常弹窗 → 移入 try 与 ShowInFolder 对齐 |
| CS-358 | P3 | 问题/可观测 | InPrivateWindow.xaml.cs:93-99 | 无痕 init 失败静默(主窗同分支有 SecurityLog) → 补同款留痕 |
| CS-359 | P3 | 问题/性能 | SourceViewerWindow.xaml.cs:15 | 5MB 源码塞非虚拟化 TextBox——Ctrl+U UI 冻结 → 首屏 256KB+加载全部按钮 |
| CS-360 | P3 | 提升/补测试 | SecurityLog.cs:35-52 | 1MB 轮转(保留 .1/失败截断重写)零测试 → 注入缝+断言轮转行为 |
| CS-361 | P3 | 提升/补测试 | BrowserPolicyBroker.cs:397-411 | CS-323 门禁探测缓存(成功恒缓存/失败 30s TTL)零测试 → 假 gate 注入断言语义 |
| CS-362 | P3 | 提升/补测试 | HostWebView.cs:143-153 | HTTPS-only 升级 URL 构造零逻辑级测试 → 提取 internal static BuildHttpsUpgradeUrl 直测 |
| CS-363 | P3 | 提升/补测试 | HostWebView.cs:274-299 | CS-308 拦截聚合零测试 → 提纯 internal 小类单测聚合/阈值/尾部 flush |
| CS-364 | P3 | 提升/补测试 | WindowSmokeTests.cs | InPrivateWindow 唯一无 STA 冒烟 → 提环境注入缝补构造+关闭冒烟 |
| CS-365 | P3 | 提升/文档 | windows/README.md:24 | "packaging/ 打包脚本"目录不存在(实为 docs/release/AegisSetup-CSharp.iss) → 改指真实位置 |
| CS-366 | P3 | 提升/重构 | TabRuntimeCoordinator.cs:192-203 | Dispose 只清 _lifetimes,两调用方各自 Clear _runtimes——约定分散 → Dispose 内单点清空,调用方删各自 Clear |
| CS-367 | P3 | 提升/可观测 | KillSwitch.cs:24-30 | Engage 后主窗无常驻指示——只见"导航无反应" → 顶部红色横幅(轮询/事件) |
| CS-368 | P3 | 提升/性能 | SettingsService.cs:80-89 | 启动无条件整文件重写 settings.json → Apply 先比对快照,无变更跳过写盘 |
| CS-369 | P3 | 提升/单源 | BookmarkImporter.cs:17-18 + HistoryStore.cs:28-29 + BookmarkManagerWindow.xaml.cs:14 | 标题/URL 上限常量三处独立 → 提共享 internal static class 单源 |
| CS-370 | P3 | 提升/双源 | MainWindow.xaml.cs:442-452 vs InPrivateWindow.xaml.cs:135-145 | 危险下载确认 MessageBox 两份同形 → 提取单源 ConfirmDangerousDownload |
| CS-371 | P3 | 提升/双源 | MainWindow.xaml.cs:541-550 vs InPrivateWindow.xaml.cs:213-220 | 标签切换四属性翻转两窗各一份 → 提取 ApplyTabVisibility 共享 |
| CS-372 | P3 | 提升/补测试 | BrowserPolicyBroker.cs:170-185 | native 必需模式黑名单门禁零测试(ctor 不可注入) → 增 internal 测试缝+两用例 |
| CS-373 | P3 | 提升/降噪 | NtpAssets.cs:99-119 | BindVirtualHosts 每标签写 3-4 行日志,3N 行冲刷 1MB 取证日志 → 进程级只记一次(失败仍每次) |
| CS-374 | P2 | 问题/门禁回归 | WindowTheme.cs:76 | (见汇总;本轮门禁实测 CS0168×2) |
| CS-375 | P3 | 提升/测试警告 | ThreatFeedCoordinatorTests.cs:154 + WindowLogicTests.cs:79,91 + BrowserPolicyBrokerTests.cs:400 | 4 处分析器警告(xUnit1013/xUnit2031×2/CS8625) → 逐处修复至测试构建 0 警告 |
| CS-376 | P2 | 问题/发布链实证 | NativePolicyCoreBridge.cs:378 + 两 Broker 测试文件 | v2.2.0-beta.51 tag 首跑实证:①原生 ABI 进程级单例(RS-140)×未 Dispose broker 靠 GC 终结退休——CS-372 NativeGateTests 与既有 probe 测试创建时序竞争,发布链原生 job 随机挂;②CS-207 NativeLibraryHandle 终结波 FreeLibrary 失败(loader 关停竞态)抛异常杀死测试宿主(运行总数截断 62→9 实证);③生产隐患登记:required 模式下主窗+无痕窗两 broker 抢单例,第二者拿不到桥即全拒(现网不设 env,登记待评估) → 逻辑测试改 CS-372 测试缝、真 DLL probe 保留独占;ReleaseHandle 兜底吞异常(终结器不允许外逃);连跑 3× 62/62 全绿 |

## 2. Android(AD-252..292,41 行)

| ID | 优先级 | 类型 | 位置 | 问题 → 方案 |
|---|---|---|---|---|
| AD-252 | P1 | 问题/安全 | OriginPolicy.kt:60-75 | (见汇总) |
| AD-253 | P2 | 问题/指纹 | WebViewHardening.kt:296-299 | (见汇总) |
| AD-254 | P2 | 问题/生命周期 | TabManager.kt:97 | (见汇总) |
| AD-255 | P2 | 问题/决策面 | AegisWebViewClient.kt:73-113 | (见汇总) |
| AD-256 | P2 | 问题/策略旁路 | AegisWebViewClient.kt:54-115 | (见汇总) |
| AD-257 | P2 | 问题/日志泄敏 | AegisHomeBridge.kt:109 | (见汇总) |
| AD-258 | P3 | 问题/死代码 | WebViewHardening.kt:308-315 | Stage 3 getParameter 伪装被 Stage 7 先行返回——永不可达;'Aegis Privacy' 字符串是现成指纹标记 → 删 Stage 3 包装保留单源 |
| AD-259 | P3 | 问题/兼容 | WebViewHardening.kt:343-348 | innerWidth 等冻结为常量——旋转/键盘弹出后读旧值,响应式错乱 → 改 getter 包装动态量化 |
| AD-260 | P3 | 问题/UX | MainDialogs.kt:75-91 | 安全提示共用版本检查对话框——按钮恒"去更新/稍后" → 提示分型(瞬时 Snackbar/单按钮) |
| AD-261 | P3 | 问题/文本边界 | MainDialogs.kt:148 | chunked 按 UTF-16 char 切段可劈开代理对 → 分段处复用码点边界回退 |
| AD-262 | P3 | 问题/下载落盘 | WebViewDownloadHandler.kt:26,179-194 | 200 字符截断≠字节上限——中文名 600 字节超 FS 255 上限落盘失败 → 按字节度量截断保扩展名 |
| AD-263 | P3 | 问题/解析 | WebViewDownloadHandler.kt:203-232 | RFC5987 解码用 URLDecoder(+→空格错);filename= 无 token 边界误匹配 xfilename → 逐 %XX 解码+锚定 |
| AD-264 | P3 | 问题/日志泄敏 | LogRedact.kt:14-19 | redact 不剥 userinfo——token@host 脱敏后仍入 logcat → 先剥 userinfo 再截 query,补断言 |
| AD-265 | P3 | 问题/状态污染 | AegisWebViewClient.kt:310-320 | 代际推进失败已 stopLoading 仍上抛 URL——地址栏被阻断 URL 覆盖 → 推进成功才上抛 |
| AD-266 | P3 | 问题/状态残留 | BrowserViewModel.kt:342-352 | navigateHistory 不清地址草稿——页面已变地址栏停留草稿 → 同提交路径清草稿 |
| AD-267 | P3 | 问题/竞态 | ReaderController.kt:34-42 | evaluateJavascript 回填无归属校验——切标签后旧正文入新语境 → 闭包比对 currentWebView 一致才写 |
| AD-268 | P3 | 问题/文本边界 | BrowserEngine.kt:118 | title take 按 char 截断可劈代理对 → takeAtCharBoundary 同口径 |
| AD-269 | P3 | 问题/可检测 | WebViewHardening.kt:164 | __AEGIS_PROTECTION_VERSION 裸赋值可枚举可删除 → defineProperty 不可枚举不可配置 |
| AD-270 | P3 | 问题/资源放大 | WebViewHardening.kt:284-301 | toDataURL 包装无尺寸上限——16K×16K 画布峰值 ~1GB OOM → 超阈值直接走原实现降级 |
| AD-271 | P3 | 问题/错误面过宽 | AegisWebViewClient.kt:328-342 | onReceivedSslError 无主框架过滤——子资源证书错即整页遮罩 → 按 error.url 归属判定,子资源仅 cancel+log |
| AD-272 | P3 | 提升/补测试 | WebViewHardeningScriptTest.kt:25-35 | 9 阶段脚本仅 Stage 2 三条断言 → 逐阶段补关键标记断言 |
| AD-273 | P3 | 提升/补测试 | AegisWebViewClient.kt:328-342,404-415 | onReceivedSslError/onSafeBrowsingHit 零覆盖——cancel 改 proceed 无测试失败 → 补两用例 |
| AD-274 | P3 | 提升/补测试 | OriginPolicyTest.kt:78-105 | 备用编码向量缺尾点/混合形态(AD-252 回归锚点) → 同批补入 |
| AD-275 | P3 | 提升/补测试 | TabManagerTest.kt:76-110 | 后台关闭 activeIndex 保持语义(AD-254)无回归 → 补两分支用例 |
| AD-276 | P3 | 提升/补测试 | BrowserEngine.kt:63 | safeBrowsingEnabled=true 零自动化断言(注释称真机覆盖实际不存在) → androidTest/API26+ getter 断言 |
| AD-277 | P3 | 提升/供应链 | gradle-wrapper.properties:3 | distributionUrl 未钉 distributionSha256Sum——发行包无完整性校验 → 补官方 sha256 |
| AD-278 | P3 | 提升/构建 | app/build.gradle.kts:175-179 | release minify 未开 shrinkResources → 补开启+lintRelease 验证 |
| AD-279 | P3 | 提升/混淆 | proguard-rules.pro:23-32 | JNA 全量 keep 抵消混淆 → 收窄到 public/实际触达类 |
| AD-280 | P3 | 提升/隐私 | TranslateEntry.kt:34-35 | 翻译 URL 外发整 pageUrl 含 fragment(OAuth token 载体) → substringBefore('#') 后编码+断言 |
| AD-281 | P3 | 提升/噪声 | SecureWebViewFactory.kt:157-160 | 销毁路径 loadUrl(about:blank) 必夭折且竞态噪声 → 删该步+同步测试次序断言 |
| AD-282 | P3 | 提升/冷启动 | AegisApplication.kt:18 | broker lazy 首消费在主线程同步 JNA dlopen → 后台线程预热 |
| AD-283 | P3 | 提升/安全UX | MainActivity.kt:276-285 | onNewIntent 无条件 bypassDebounce 消费 VIEW intent——第三方应用可高频打断 → 频控/前台判定 |
| AD-284 | P3 | 提升/UX | AegisWebViewClient.kt:94-113 | mailto:/tel: 与恶意 scheme 同走静默 Deny → 显式 Toast 不支持该类链接 |
| AD-285 | P3 | 提升/隐私覆盖 | WebViewHardening.kt:352-371 | QueryStripper 只包 fetch/XHR——sendBeacon/WebSocket 不 strip,追踪参数畅通 → 同口径包装 |
| AD-286 | P3 | 提升/日志净化 | LogSanitize.kt:14 | flatten 仅压 \r\n\t,其余 C0(含 ESC)仍入 logcat → 扩为 \p{Cntrl}+向量 |
| AD-287 | P3 | 提升/构建性能 | gradle.properties:1-4 | 未开 parallel/caching/configuration-cache → 逐项启用回归 |
| AD-288 | P3 | 提升/开发流程 | app/build.gradle.kts:163-181 | debug 无 applicationIdSuffix——真机回归须先卸 debug → 加 .debug 后缀 |
| AD-289 | P3 | 提升/硬化 | BrowserEngine.kt:52-70 | 缺 setGeolocationEnabled(false)/setSaveFormData(false) 显式立场 → 显式置 false+断言矩阵 |
| AD-290 | P3 | 提升/测试基建 | app/build.gradle.kts:214-216 | unitTests.isReturnDefaultValues 全局开——掩盖真实框架依赖 → 收窄/注释固化豁免范围 |
| AD-291 | P3 | 提升/SafeBrowsing | AegisWebViewClient.kt:404-415 | onSafeBrowsingHit 恒 backToSafety——无历史时无处可退白屏 → showInterstitial 或回 HOME_URL |
| AD-292 | P3 | 提升/构建卫生 | android/(gradle 输出) | Gradle 9.8 报 Deprecated features + 提示 configuration cache(本轮门禁实测) → --warning-mode all 定位逐项清(与 AD-287 分列) |
| AD-293 | P2 | 问题/发布链实证 | android/broker/build.gradle.kts:74-87 | AD-287 启用的 configuration-cache 与 broker preBuild doFirst 捕获脚本对象引用冲突——仅 -PrequireNativePolicyCore=true(发布链独有)触发,本地门禁无此 flag 故未暴露;云端 Android 原生打包 job 实证 BUILD FAILED(cannot serialize Gradle script object references) → 脚本态值拷入局部 val 后闭包只引局部量;preBuild CC stored/reused 双跑验证 |

## 3. Rust 策略核心(RS-239..274,36 行)

| ID | 优先级 | 类型 | 位置 | 问题 → 方案 |
|---|---|---|---|---|
| RS-239 | P2 | 问题/FFI | c_abi/mod.rs:37 | (见汇总) |
| RS-240 | P2 | 问题/控制失效 | broker.rs:234-243 | (见汇总) |
| RS-241 | P2 | 问题/防护 | per_site_seed.rs:108-118 | (见汇总) |
| RS-242 | P2 | 问题/伪装 | query_strip.rs/ext_proxy.rs/font_norm.rs/bridge 模板 | (见汇总) |
| RS-243 | P2 | 问题/fail-open | action_policy.rs:148-158 | (见汇总) |
| RS-244 | P2 | 问题/覆盖缺口 | timer_prec.rs:110-196 | (见汇总) |
| RS-245 | P3 | 问题/兼容 | font_norm.rs:106-114 | check 包装不 coerce 非字符串参数(原生 coerce "123")——TypeError 泄漏兼探测点 → 入口 String(font) |
| RS-246 | P3 | 问题/校验 | session_state.rs:63 | schemaVersion u64→u32 截断:2³²+1 回绕为 1 被接受 → 先判 ≤u32::MAX 再转,补回绕用例 |
| RS-247 | P3 | 问题/重放窗口 | broker.rs:173-177 | destroy_session 清 nonce 账本——同 id 重建后旧 nonce 可重放 → 按 (session_id,纪元) 联合记账,补用例 |
| RS-248 | P3 | 问题/剥离绕过 | query_strip.rs:174-190 | JS stripParams 用 new URL 无 base——相对 URL 抛异常原样放行(Rust 侧字符串语义无双源漂移) → 带 location.href base 或手工解析 |
| RS-249 | P3 | 问题/噪声退化 | shield.rs:132-138 | 噪声 (seed+i)%2 在 i+=4 下退化为通道常量偏置(与 AD-253 跨端同病) → 像素索引混合取模,三通道不同常数 |
| RS-250 | P3 | 问题/绕过 | letterbox.rs:130-147 等 | 实例遮蔽可经原型 getter 直取原值 → 改原型级替换与 font_norm 口径统一 |
| RS-251 | P3 | 问题/探测面 | protection_mode.rs:43,123-141 | MODE_SYMBOL 带品牌前缀且 Symbol.for 可反查 → 去品牌化/per-page Symbol |
| RS-252 | P3 | 问题/防篡改 | tostring_guard.rs:99-106 | 注册接口页面可调用注入伪造映射 → 校验 original 未注册/注入窗口后撤销 |
| RS-253 | P3 | 问题/口径不一 | ffi/broker.rs:69-80 | C ABI 拒空 policy_version,UniFFI 不拒——行为分叉 → UniFFI 同拒或默认版本,补一致性测试 |
| RS-254 | P3 | 问题/输入无界 | ffi/broker.rs:87-94 + ffi/mod.rs:250-263 | evaluate_navigation scope 与 pipeline domain 无长度上限(RS-223 只限会话键) → 对齐 256 上限 |
| RS-255 | P3 | 问题/校验绕过 | ext_proxy.rs:79-110 | scheme 归一只在 with_endpoint——with_config/直构绕过 → inject_script 防御性再校验,非法退化空 |
| RS-256 | P3 | 问题/伪装 | protection_mode.rs:73-87 | Compatible 模式关 ToStringGuard 但仍注入 canvas 覆盖——最易检出 → Compatible 也启用 Stage 1 或文档登记 |
| RS-257 | P3 | 问题/跨站关联 | shield.rs:96-108 | eTLD+1 取最后两标签——公共后缀下不同站点共享种子(co.uk/github.io) → 最小公共后缀表或宿主传入真实 eTLD+1 |
| RS-258 | P3 | 问题/日志泄敏 | ffi/broker.rs:96-106,610-618 | url_policy deny 的 detail/explanation 双份内嵌完整明文 URL(AD-211 认识已立,Rust 未同步) → 脱敏/去 query 后组装 |
| RS-259 | P3 | 问题/口径漂移 | util.rs:95 | extract_host 用全量 to_lowercase,origin.rs 用 to_ascii_lowercase——非 ASCII host 双链路分叉 → 统一 ascii,补用例 |
| RS-260 | P3 | 问题/上限往返 | session_state.rs:53-57 | 512KB 状态 hex 膨胀恰超 1MB JSON 上限——上限状态往返失败恢复静默失效 → MAX_JSON_BYTES 提至 ~1.125MB 或状态降半,补恰上限往返测试 |
| RS-261 | P3 | 提升/热路径 | command_bar.rs:124-206 | search 每条目重复 to_lowercase 同一查询 → 一次折叠传入内部方法 |
| RS-262 | P3 | 提升/单源 | shield.rs:56-58 | seed_hex 逐字节 format!(第三份 hex 实现) → 改调 util::hex_encode;测试同型一并收敛 |
| RS-263 | P3 | 提升/死泛型 | matcher.rs:55-62 | run_match 的 Option 参数两调用点恒 Some——死分支 → 改直传 |
| RS-264 | P3 | 提升/死字段 | oracle.rs:22,200 | Snapshot.captured_at 只写不读 → verify 校验账龄或删字段 |
| RS-265 | P3 | 提升/死数据 | adblock.rs:20-22,109-120 | rule_count/last_updated 恒 0——UI 展示面失真 → load 回写或删字段声明宿主职责 |
| RS-266 | P3 | 提升/热路径 | space_routing.rs:100,170-177 | N 条规则逐条重复 extract_hostname → route 单次提取传 host |
| RS-267 | P3 | 提升/冗余折叠 | https_only.rs:44-46,96-101 | upgrade 与 is_http_allowed 双重 to_ascii_lowercase → 增 _lc 内核 |
| RS-268 | P3 | 提升/热路径 | c_abi/mod.rs:89-161 | FFI 响应先建整棵 Value 树再序列化(双倍分配) → Serialize 结构体直写 |
| RS-269 | P3 | 提升/补测试 | capability.rs:93-115 | is_origin_allowed 边界缺 userinfo/@ 与 :port 用例 → 补三类边界 |
| RS-270 | P3 | 提升/可测性 | ffi/broker.rs:36-37,310-326 | ACTION_EXPIRY_SECONDS 硬编码,FFI 层过期分支零测试 → 构造参数化+过期 approve 拒绝用例 |
| RS-271 | P3 | 提升/fuzz | fuzz/Cargo.toml:33-62 | 缺 https_only::upgrade / capability::is_origin_allowed / executor::parse 三个 fuzz target → 照现有模式新增 |
| RS-272 | P3 | 提升/口径 | session_state.rs:94-95 | canGoBack/canGoForward 仍宽松 unwrap_or(false)——与 RS-230 缺即拒口径不一 → 同步收紧或注明理由 |
| RS-273 | P3 | 提升/死接口 | js_inject.rs:18-28 | JsInjectable::name() 生产零消费 → build 输出阶段名注释或删 |
| RS-274 | P3 | 提升/兼容 | font_norm.rs:143-149 | measureText 无条件替换 family——等宽字体测量系统性偏差;SAFE_SET 内也强制替换 → 命中 SAFE_SET 原样,替换表补等宽/serif |

## 4. Python·契约·发布链(PY-216..257,42 行)

| ID | 优先级 | 类型 | 位置 | 问题 → 方案 |
|---|---|---|---|---|
| PY-216 | P1 | 问题/工具断裂 | scripts/sync_versions.py:75-76 | (见汇总) |
| PY-217 | P2 | 问题/门禁+lint | tests/python/ + guard yml | (见汇总) |
| PY-218 | P2 | 问题/工具失效 | verify_manifest.py:67-75 | (见汇总) |
| PY-219 | P2 | 问题/去重残留 | dedup_release_assets.py:57-69 | (见汇总) |
| PY-220 | P2 | 问题/双源漂移 | requirements-dev.txt vs requirements-ci.in | (见汇总) |
| PY-221 | P2 | 问题/依赖缺口 | update_verifier.py:22-23 | (见汇总) |
| PY-222 | P2 | 问题/测试盲区 | release.yml / contracts.yml | (见汇总;workflow 改动归 SP 批) |
| PY-223 | P3 | 问题/误报 | verify_versions.py:15-17 | XML 取值不反转义——DISPLAY_NAME 含 & 必报漂移 → unescape,补往返用例 |
| PY-224 | P3 | 问题/正则注入 | sync_versions.py:29-30 | re.subn 替换串反向引用——值含 \ 错位 → 函数式替换(lambda),补用例 |
| PY-225 | P3 | 问题/校验弱 | verify_release.py:66-73 | core .txt 回退只数非空行不验内容——伪造清单 1 行即过 → 逐行解析+文件集对账,改 deadbeef 弱测试(PY-250) |
| PY-226 | P3 | 问题/口径单侧 | generate_sbom.py:21 | 工件名未 unquote——percent-encoded 名 SBOM 对账必失败 → 同款 unquote 取尾段 |
| PY-227 | P3 | 问题/契约矛盾 | update-manifest.schema.json:50-56 | artifacts.platform 枚举仍含 windows-arm64(无该构建产物) → 与 PY-101 口径移除 |
| PY-228 | P3 | 问题/宽松解析 | update_verifier.py:97 | fromisoformat 接受非 RFC3339 形态——与 schema 口径不一 → 正则锚定或 rfc3339_validator |
| PY-229 | P3 | 问题/文档矛盾 | security-release.md:11-45 | runbook 仍把 cosign 轨道写为现役(SP-147 已改口) → 标注 planned/预备步骤 |
| PY-230 | P3 | 问题/死声明 | shared/version.properties:7 | ANDROID_APPLICATION_ID 零消费者,真实值三处平行硬编码 → 删死键或加三方对账 |
| PY-231 | P3 | 问题/测试泄漏 | codegen_and_catalog_test.py:261-264 | 直接改模块全局不经 monkeypatch 不还原 → 三处换 monkeypatch.setattr |
| PY-232 | P3 | 问题/平台差异 | generate_csharp.py:179 等 | write_text 未锁 newline="\n"——Windows 重生成 CRLF 漂移,git diff 门禁假红 → 补 newline="\n",补零 diff 断言 |
| PY-233 | P3 | 问题/检查错位 | bootstrap-dev-environment/run.py:51-55 | dotnet/node 只验存在不验版本下限 → 参照 _check_python 补断言 |
| PY-234 | P3 | 问题/第三源 | build_review_package.py:126-135 | version_props 是第三份 properties 解析(宽松吞坏行) → 复用 sync_versions.load_properties |
| PY-235 | P3 | 问题/守卫不齐 | verify_release.py:45 | build-metadata.json 损坏裸 traceback → 包 try/except 干净退出 |
| PY-236 | P3 | 问题/门禁恒真 | verify_bridge_guard.py:79-83 | required_sinks 从锚点行解析又查同文本——body 删光也过 → 对剔除锚点后的 body 检查 |
| PY-237 | P3 | 提升/边界一致 | update_verifier.py:98 vs e2e:174 | 过期边界两套(<= vs <) → e2e 对齐 <=,补 expires==now 用例 |
| PY-238 | P3 | 提升/配置 | pyproject.toml:18-25 | ruff 无显式 select——规则面随版本漂移 → 显式 select 固定 |
| PY-239 | P3 | 提升/死配置 | pyproject.toml:34 | selftest_*.py 豁免永无匹配文件 → 删或注释留痕 |
| PY-240 | P3 | 提升/环境漂移 | requirements-ci.in:6-10 + bootstrap | 本地 ruff 0.16.3 vs 活动锁 0.16.9;bootstrap 不装 lint 工具链;规程缺 POSIX 路径 → bootstrap 补 venv 指引;规程补 bin/ |
| PY-241 | P3 | 提升/弱化检测 | validate_vector_schemas.py:76-83 | invalid 向量只打 info 零断言——schema 削弱门禁仍绿 → schema 级子集必须全拒 |
| PY-242 | P3 | 提升/双源 | generate_csharp.py:53-122 | describe_value_domain 两份逐字重复;cs_nullable 死结构 → 抽共享模块+化简 |
| PY-243 | P3 | 提升/锚点 | generate_csharp.py:36-39 | artifacts 嵌套对象降级 List<object>——五字段零编译期锚点 → 生成嵌套子模型+compat 对账 |
| PY-244 | P3 | 提升/向量消费 | update-manifest-canonical.json | canonical 字节金标仅 Rust 消费——Python 侧改序列化不红 → 逐条 canonical_unsigned(manifest).hex()==expected |
| PY-245 | P3 | 提升/SAST 缺口 | legacy-python-guard.yml:95 | bandit/mypy 只扫 legacy app——现役 scripts/release/contracts/agent 零 SAST → guard 增面(依赖 PY-221) |
| PY-246 | P3 | 提升/补测试 | bootstrap/migrate/verify_agent_catalog | 三脚本零单测;migrate 的 assert 在 -O 下剥离 → 补 tmp_path/monkeypatch 用例 |
| PY-247 | P3 | 提升/shell 门禁 | scripts/e2e-android-search.sh | 零 shellcheck;$PKG 正则点号未转义 → CI 接线 shellcheck+修脚本(含 SP-212 严格模式) |
| PY-248 | P3 | 提升/生成噪声 | generate_csharp.py:140 | 无条件 using Collections.Generic——4/6 份生成文件未用 → 条件输出,快照同步 |
| PY-249 | P3 | 提升/死表达式 | bridge_guard.template.js:33 | `sendBeacon && sendBeacon` 恒等自身——缺 .bind(navigator) 笔误,sendBeacon 缺失时守卫自炸 → 明确 bind+存在性短路(修复归 RS 批同步) |
| PY-250 | P3 | 提升/锁定弱行为 | release_chain_test.py:243-254 | deadbeef 假哈希把弱行为锁死 → 随 PY-225 改真实哈希 |
| PY-251 | P3 | 提升/类型守卫 | redteam_test.py:52-53 | isinstance(int) 对 bool 放行(max_actions: true 过门禁) → 排除 bool,补向量 |
| PY-252 | P3 | 提升/语义模拟 | redteam_e2e_test.py:161-225 | session.md 声称 tab_id 绑定,e2e 只比代际——模拟面窄于文档 → 补 per-session tab 绑定或修文档 |
| PY-253 | P3 | 提升/零消费策略 | signing-policy.yaml:20-36 | 除 threshold 外全部零机器消费,纯文档型 YAML 必漂移 → signer_workflow 接消费或文件头注明 |
| PY-254 | P3 | 提升/门禁弱于测试 | verify_agent_catalog.py:18-35 | CI 脚本只断言两项,pytest 侧四项 → check() 补 policy_version 非空+预算断言同源 |
| PY-255 | P3 | 提升/静默首胜 | gen_jsapi_schema.py:51-62 | setdefault 静默取首个同名类——方法悄然从 schema 消失 → 冲突清单 stderr 告警或 fail |
| PY-256 | P3 | 提升/lint 治理 | core/rust-policy-core/bindings/ | 43 处 ruff 违规(F401 等,33 可自动修)且不在任何门禁面(本轮根口径实测) → --fix 清零+接线 |
| PY-257 | P3 | 提升/跳过口径 | tests/python/release_tools_test.py:244 | 1 例 skip(Windows 符号链接非特权)长期跳过且口径未登记 → 注明口径/开发者模式启用说明 |
| PY-258 | P2 | 问题/供应链 | requirements-ci.in:26 + requirements-ci.txt | cryptography==48.0.1 命中 PYSEC-2026-3552/3553/3554(supply-chain pip-audit 门禁实证 6 条,修复版本 49.0.0/50.0.0)——PY-221 入锁时未过漏洞扫描 → 升级 50.0.0 + pip-compile --generate-hashes 真实重锁(989 hash),--require-hashes dry-run 通过 |
| PY-259 | P3 | 问题/测试环境泄漏 | tests/python/release_tools_test.py:355-364 | test_complete_properties_write_metadata 断言 source_revision=local-unverified,但 build_metadata 写侧优先消费 GITHUB_SHA/GITHUB_REF/GITHUB_RUN_ID——CI runner 恒有值,断言的是 runner 环境(本地绿/contracts job 红的环境泄漏) → monkeypatch.delenv 三变量 |

## 5. Web 资产·文档(WB-133..175,43 行)

| ID | 优先级 | 类型 | 位置 | 问题 → 方案 |
|---|---|---|---|---|
| WB-133 | P2 | 问题/数据丢失 | start.snake.js:435-447 | (见汇总) |
| WB-134 | P3 | 问题/UI | start.import.js:130-132 | hint 每次 append 堆叠不消散 → 提示节点单例化 |
| WB-135 | P3 | 问题/功能 | start.import.js:136-157 | 导入阶段无超时兜底——桥挂起向导永停 → 布导入总超时渲染失败态 |
| WB-136 | P3 | 问题/误导反馈 | start.import.js:109-116 | csCall TTL null 被计入成功 0 条 → null 计 failures 或单列无响应 |
| WB-137 | P3 | 问题/语义 | start.main.js:288 | restoreBox display 压过 hidden 但不移除属性 → removeAttribute('hidden') 统一配对 |
| WB-138 | P3 | 问题/误导反馈 | start.main.js:303-317 | 书签 null 与空数组同路径渲染空库文案 → 分流显示加载失败 |
| WB-139 | P3 | 问题/日志注入 | NtpBridge.cs:196-201 | jsError 页面可控字符串未净化直入 SecurityLog(AD-235 孪生) → 折叠 \r\n(修复归 CS 批) |
| WB-140 | P3 | 提升/可观测 | start.main.js:7-20 | error 监听注册于最末脚本——前三文件顶层异常零上报 → 移入首文件 start.js |
| WB-141 | P3 | 提升/可访问性 | start.css | 0 处 forced-colors 规则——高对比模式系统色未恢复 → 补规则 |
| WB-142 | P3 | 提升/移动端 | start.css:228-230 | coarse pointer 清单缺 .link-btn/.snake-sound/.snake-close(<44px) → 补齐 |
| WB-143 | P3 | 提升/对比度 | start.css:53 | placeholder 2.9:1<AA → 加深至 ≥4.5:1 |
| WB-144 | P3 | 提升/移动端 | start.css:216 | 15px<16px 聚焦自动放大跳变 → 提至 16px |
| WB-145 | P3 | 提升/可访问性 | start.import.js:92-106 | 历史条数下拉无可编程名称 → aria-label |
| WB-146 | P3 | 提升/安全收紧 | NtpAssets.cs:107-118 | ≡CS-334,合并处理(虚拟主机 Allow→Deny) |
| WB-147 | P3 | 提升/补测试 | start.main.js:263-274 | geoBtn 降级零行为测试 → 补 onFail 断言 |
| WB-148 | P3 | 提升/补测试 | start.main.js:136-147 | selectEngine 行为零测试 → 补三断言 |
| WB-149 | P3 | 提升/补测试 | start_page.test.mjs:229-231 | CSP img-src data: 未锁 → 补断言 |
| WB-150 | P3 | 提升/补测试 | start.js:111-114 | Host.goBack 仅静态断言 → 补 cs 桩 postMessage 行为断言 |
| WB-151 | P3 | 提升/攻击面 | start.snake.js:518-536 | __test 受控钩子随生产脚本入成品 → 条件注入或只读冻结 |
| WB-152 | P2 | 问题/文档失实 | supported-features.md:24 | (见汇总) |
| WB-153 | P3 | 问题/台账漏项 | CLAUDE.md:108 | ≡SP-188,合并处理 |
| WB-154 | P3 | 问题/命令漂移 | CLAUDE.md:53-54 | ≡SP-185/186,合并处理 |
| WB-155 | P3 | 问题/口径矛盾 | CONTRIBUTING.md:95 | ≡SP-190,合并处理 |
| WB-156 | P3 | 问题/命令失效 | CONTRIBUTING.md:57-83 | 质量门槛命令块缺全部 cd 前缀 → 补 cd 行 |
| WB-157 | P3 | 问题/台账失实 | tests/KNOWN_DEFECTS.md:24 | BUG-012 回归断言描述与现行断言相反 → 改述 |
| WB-158 | P3 | 问题/触发点失实 | tests/KNOWN_DEFECTS.md:35,37 | 测试分层表挂错 workflow(ci.yml 已只剩 UI 回归) → 逐行改挂 |
| WB-159 | P3 | 问题/文档过期 | architecture-overview.md:111 | 回归流仍以 selftest 为正典 → 改述四栈回归 |
| WB-160 | P3 | 问题/枚举失实 | architecture-overview.md:56,75-76 | 五门禁漏 ci/legacy-guard;树列 reader/ translate/ 目录(实为平文件) → 对齐 13 workflow 与实树 |
| WB-161 | P3 | 问题/索引失实 | docs/README.md:15 | release/ 行内容与实物不符 → 对齐并给正确路径 |
| WB-162 | P3 | 问题/索引失实 | docs/README.md:14,18 | runbooks 漏列;quality-reports 称有三工具报告实无;09-04 审计仍称现役栈 → 逐行修正+横幅 |
| WB-163 | P3 | 问题/文档过期 | inv05-delivery-chain-design.md:14,37,63 | 无横幅且现状节过期 → 补横幅+快照标注 |
| WB-164 | P3 | 问题/文档过期 | release-workflow-design.md | 孪生文件已加横幅本文件漏 → 同口径补 |
| WB-165 | P3 | 问题/文档过期 | code-signing-design.md | 仍称 sigstore 待实施(现役 apksigner+attestation) → 补横幅注明现役面 |
| WB-166 | P3 | 问题/横幅双标 | KNOWLEDGE_BASE.md:27-38,432-477 | 部分节有横幅部分无 → 范围扩齐或逐节注记 |
| WB-167 | P3 | 问题/引用过期 | KNOWLEDGE_BASE.md:78,89 | 「ktlint 待 Gradle 环境」「CI 已在 ci.yml」过期 → 更新 13 workflow 分层口径 |
| WB-168 | P3 | 问题/引用过期 | device-validation.md:18 | 预期引归档栈 INTERNAL_SCHEMES → 改述正典机制 |
| WB-169 | P3 | 问题/孪生漏改 | refactor-final-route.md:27,88 | 仍称 bundled origin(WB-121 已改 trust-boundaries) → 同步分列 |
| WB-170 | P3 | 问题/孪生漏改 | android/app/build.gradle.kts:197 | 注释仍称 PyInstaller datas(SP-169 同批漏) → 改 csproj 口径(修复归 AD 批) |
| WB-171 | P3 | 提升/横幅补齐 | 6 份调研期文档 | webview2-extensions-research 等 6 份无时代横幅(README 承诺未兑现) → 逐份补 |
| WB-172 | P3 | 提升/台账衔接 | 229-items.md:315 | 结注「余量池 332 项」与 09-23 台账终态全闭环矛盾 → 补后记指向终态 |
| WB-173 | P3 | 提升/安全文档 | SECURITY.md:21-33 | 危险 API 审查表缺 JS(单源首页)行 → 补行(修复归 SP 批) |
| WB-174 | P3 | 问题/归档表述 | quality-reports/full-audit-2026-09-04.md:3 | 仍称 pywebview 现役栈且无横幅 → 移 docs/audit 或加横幅 |
| WB-175 | P3 | 提升/索引 | docs/README.md:24-25 | 审计索引缺 2026-10-01 本轮条目 → 补行 |

## 6. CI·根配置·盲区(SP-177..217,41 行)

| ID | 优先级 | 类型 | 位置 | 问题 → 方案 |
|---|---|---|---|---|
| SP-177 | P2 | 问题/供应链 | CONTRIBUTING.md:27 + SECURITY.md:43 + contracts.yml:102 + release-windows.yml:49 | (见汇总;csproj 部分归 CS 批) |
| SP-178 | P2 | 问题/pin 可审计性 | 15 处 action pin | (见汇总) |
| SP-179 | P2 | 问题/门禁缺口 | release.yml:226-268 | (见汇总) |
| SP-180 | P3 | 问题/注记漂移 | agent-redteam/compat/supply-chain/legacy-guard vs android-quality | 同一 setup-python SHA 四处注 v6.0.0 一处注 v7.0.0(实为 v7.0.0),contracts 无注 → 统一注记 |
| SP-181 | P3 | 问题/配置失实 | compat.yml:40-44 | 步骤名"安装 Python 3.14"实装 3.12;注释引 ci.yml(无 Python) → 改名改注释 |
| SP-182 | P3 | 问题/副本漂移 | release-windows/android/core.yml pin-check 副本 | 存在性断言只落编排器——四副本已漂移 → 抽 composite action 单源 |
| SP-183 | P3 | 问题/口径不一 | README/CLAUDE vs core-rust.yml/release-core.yml | clippy 三口径:--all-targets 承诺 vs PR 门禁无 --all-targets vs 发布链仅 --locked → 统一 --all-features --all-targets -D warnings |
| SP-184 | P3 | 问题/缓存键 | release-android.yml:97 | Gradle 缓存 key 漏 libs.versions.toml(AD-243 只修 android-quality) → key 追加 |
| SP-185 | P3 | 问题/文档双源 | CLAUDE.md:53 | 行内 bandit --skip 与 bandit.yaml 单源并存(WB-154 合并) → 改 bandit -c bandit.yaml |
| SP-186 | P3 | 问题/文档过时 | CLAUDE.md:54 | mypy 手写清单漏 crash_reporter.py(mypy.ini 已全量) → 改裸 mypy |
| SP-187 | P3 | 问题/文档过时 | CLAUDE.md:87 + PR 模板:7 | "显式文件清单"已改目录 glob(SP-163) → 两处删措辞 |
| SP-188 | P3 | 问题/台账漏项 | CLAUDE.md:108 | audit 行漏 2026-09-26 轮(WB-153 合并;顺带补本轮) → 补引用 |
| SP-189 | P3 | 问题/配置失实 | CONTRIBUTING.md:25 | "requirements.txt 声明"——根无该文件(活跃源为 requirements-ci.in) → 改写 |
| SP-190 | P3 | 问题/自相矛盾 | CONTRIBUTING.md:95 | 评审清单仍要求新增 selftest(WB-155 合并) → 改按端测试口径 |
| SP-191 | P3 | 问题/门禁缺口 | CLAUDE.md + PR 模板 | 缺 agent 红队与 supply-chain 自检项 → 各补两行 |
| SP-192 | P3 | 问题/文档过时 | SECURITY.md:37-39 | hash 锁表述未提 requirements-ci.txt 活跃锁 → 双锁源更新 |
| SP-193 | P3 | 问题/死忽略 | .gitignore:70 | installer_output 规则无写入方(OutputDir 已改 dist) → 删 |
| SP-194 | P3 | 问题/忽略缺口 | .gitignore:5-9 | 凭据组缺 *.pfx(Authenticode 签名落盘面) → 补 |
| SP-195 | P3 | 问题/脚本健壮性 | android/build-android.ps1:19-23 | 不检查 $LASTEXITCODE——Gradle 失败仍报完成(修复归 AD 批) → 补检查 |
| SP-196 | P3 | 问题/同型未修完 | release-windows/native-policy-artifacts/release.yml 5 处 | verify_versions 等仍依赖镜像预装 python(PY-065 只修一处) → 各 job 补 setup-python |
| SP-197 | P3 | 问题/门禁覆盖 | native-policy-artifacts.yml:6-17 | paths 不含 windows/android 但 job 消费之——组合冒烟永不触发 → 补 paths 或注明取舍 |
| SP-198 | P3 | 问题/口径不一 | README.md:78-79 vs CHANGELOG | "pytest 230+"与 30 并存无口径说明 → 注明分列口径 |
| SP-199 | P3 | 问题/口径失实 | README.md:86 | "13 workflow 分层常跑"——常跑实为 8 → 如实分层口径 |
| SP-200 | P3 | 提升/CI 触发面 | supply-chain.yml + agent-redteam.yml | push 无 paths——docs 改动全量跑审计 → 补 paths |
| SP-201 | P3 | 提升/缓存口径 | contracts/supply-chain/agent-redteam | pip 缓存三口径(静态键/无缓存) → 统一 cache-dependency-path |
| SP-202 | P3 | 提升/CI 性能 | cargo-audit/cargo-ndk 安装 | 每次 CI 从源码编译数分钟 → 缓存或预编译安装 |
| SP-203 | P3 | 提升/依赖更新 | dependabot.yml | 缺 cargo/nuget 生态——Rust 依赖无例行 bump → 补两组 |
| SP-204 | P3 | 提升/CI 性能 | native-policy-artifacts.yml:83-167 | build-android 三次 gradle 无缓存 → 补同款 |
| SP-205 | P3 | 提升/最小权限 | release.yml:65,78,87 | secrets: inherit 全量透传 → 显式逐 secret |
| SP-206 | P3 | 提升/并发 | release.yml:14-17 | 无 concurrency 组——双 tag 并发争抢 Release 资产 → 补 group |
| SP-207 | P3 | 提升/协作基建 | .github/(无 CODEOWNERS) | 安全敏感路径无强制评审 → 补 CODEOWNERS |
| SP-208 | P3 | 提升/lint 覆盖 | legacy-python-guard.yml:72-86 | ruff 面缺 validate_release.py/tests/bindings(与 PY-217/256 配套) → 面补齐 |
| SP-209 | P3 | 提升/供应链 | prepare-geogebra/action.yml:42 | extractall 无 zip-slip 校验 → 成员路径断言 |
| SP-210 | P3 | 提升/协作基建 | ISSUE_TEMPLATE/ | 无 config.yml 引导入口 → 补 contact_links |
| SP-211 | P3 | 提升/本地口径 | build-android.ps1 + gradle | 本地 -Release 无原生策略核心(与 CI 发布物配置不同)无感知(修复归 AD 批) → 对齐参数或醒目告警 |
| SP-212 | P3 | 提升/e2e 可空转 | e2e-android-search.sh:74-80 | 标题日志缺失仅 WARN 仍判 PASS(修复归 PY 批) → 空标题计 FAIL/严格模式 |
| SP-213 | P3 | 提升/注入一致性 | release-android.yml:64,168 | ref_type 直插脚本(同步骤 ref_name 已 env 中转) → 统一 env |
| SP-214 | P3 | 提升/锁口径 | legacy-python-guard.yml:63-67 | dev 工具链无 hash 未注明边界 → hash 锁或注明取舍 |
| SP-215 | P3 | 提升/缓存双源 | contracts vs android-quality/release-android | Gradle 缓存两套机制并存 → 统一 |
| SP-216 | P3 | 提升/归档门禁 | supply-chain.yml:32 | pip-audit 对归档栈硬门禁——新 CVE 永久阻断 push 逼人改只读归档 → 降告警或移周守护 |
| SP-217 | P3 | 提升/记账 | CHANGELOG.md | 本轮 241 项整改变更未入账 → 补 Unreleased 条目 |
| SP-218 | P2 | 问题/门禁失效 | release-windows.yml:12 + release-android.yml:11 | SP-205 把 secrets:inherit 改显式逐 secret 传参,但两被调子流 workflow_call 未声明 secrets 面——Actions 语义校验直接 startup_failure(「Invalid workflow file」),release.yml 对 v2.2.0-beta.51 tag 完全无法启动;本地 yaml.safe_load/actionlint 双绿仍漏(校验发生在 Actions 侧被调方声明层) → 两子流补 secrets 声明(required:false 保留 dispatch 无凭据调试路径);actionlint 复验 0 告警 |
| SP-219 | P3 | 外部观察/依赖提交 | (GitHub 内置 Automatic Dependency Submission) | submit-nuget 内置工作流在 ubuntu restore net10.0-windows 工程失败(EnableWindowsTargeting)——仓库侧无 workflow 文件可修,仅影响依赖图提交面,不阻塞发布链 → 处置:仓库设置关闭自动依赖提交,或自管 workflow 加 -p:EnableWindowsTargeting=true 承接 |
| AD-294 | P2 | 问题/发布链实证 | android/app/proguard-rules.pro:28-31 | v2.2.0-beta.51 真机闪退第一层:AD-279 JNA keep 收窄为「公开类+公开成员」,但 com.sun.jna.Pointer 的 protected peer 字段被原生侧 GetFieldID 按名访问——R8 改名 → UnsatisfiedLinkError「Can't obtain peer field ID」→ 原生核心加载失败 → REQUIRE_NATIVE_POLICY_CORE=true 注册会话失败 → MainActivity.onCreate 启动即崩(模拟器复现,AegisBroker/AegisCrash 留痕) → 恢复 JNA 全量成员 keep(-keep class com.sun.jna.** {*;}),AD-279 收窄作废并注记原因 |
| AD-295 | P2 | 问题/发布链实证 | android/gradle.properties + BrowserViewModel.kt:155,197 | 修复 ① 后露出第二层:R8 full mode 折叠 BrowserViewModel.tabManager 可空字段(AD-003 同族第二例)——init 的字段写入与组合期读取错位,AddressAndContent:261 requireNotNull 首帧即崩(R8 retrace 精确定位;init 于 onCreate:93 先行,非时序问题) → android.enableR8.fullMode=false(模拟器同代码存活+UI 完整渲染实证);被折叠 store/load 对的代码级精修登记后续批 |
| AD-296 | P3 | 提升/门禁缺口 | .github/workflows/release-android.yml | 发布链无运行时冒烟:zipalign/签名/条目校验均为静态,启动崩溃(beta.51)零拦截——arm64 制品与 CI 模拟器(x86_64 无转译)ABI 错配无法直测 → 登记结构缺口;后续批以「同 commit x86_64 minified 构建+模拟器启动存活」代偿冒烟(本次人工执行) | 第三次 tag 跑实证:三平台 build/sbom/verify 首次全绿,verify-gate 的 core .txt 对账误拒全部条目——①release-core 清单重生成命令(find -print0|xargs sha256sum)产出 "./" 前缀条目,与实际文件名集合判不一致;②自排除比较拿相对 rglob 路径对 resolve() 绝对路径恒不等,清单自身落入 unlisted——PY-225 加强校验暴露生成/校验两侧形态漂移(此前弱校验"只数行"看不见) → 条目归一化(反斜杠→正斜杠+剥 ./ 前缀)+自排除改 p.resolve() 同侧比较;补 "./" 前缀+相对 dist 路径双形态回归用例 | 第二次 tag 跑实证:publish 带 --runtime win-x64 而 CS-SP-177 批本地生成的锁无 RID——locked-mode NU1004「runtime identifiers have changed」,restore 失败连带发布目录缺 DLL;build/test(无 RID)恰好与无 RID 锁一致故绿(假象) → 三锁以 -r win-x64 重生成(+38 行 RID 专属依赖);CI 全部 dotnet 命令统一 -r win-x64(contracts 3 处/release-windows test 2 处/native-policy test 1 处,publish 本就带 --runtime);csproj 属性处注记「无 -r 裸 restore 会把锁改写回无 RID」;CLAUDE/CONTRIBUTING 本地命令同步;locked build/test 本地复验 0 警告+695 全绿 |

---

## 执行批次日志(随执行更新)

| 批次 | 范围 | 项数 | 验证 |
|---|---|---|---|
| CS 批 | CS-334..375 全 42 项 + WB-146(合并)+ SP-177 csproj 部分 + WB-139(核验)。要点:Ntp 虚拟主机 Allow→Deny(334)/canvas WebGL 门禁删除+per-site 种子(335/336)/UrlRedactor 剥 userinfo(337)/查找计数 Promise 恒 0(338)/帧 DNS UI 冻结 fail-closed(339)/CS-374 0 警告基线恢复/测试分析器警告清零(375)/NuGet 锁文件三 csproj 入库/DownloadRecordStore 死数据面删除(344)/TextLimits·WindowSharedChrome·TrackerBlockAggregator 三个单源收敛(369/370/371/363)/KillSwitch 常驻横幅(367)/无痕崩溃残留清扫(352);顺带修出 HTTPS 升级 HostAndPort 补默认端口的隐性缺陷(362);windows/dist 陈旧暂存 122MB 清除。CS-345 无效(xunit.runner.json 已存在);WB-139 无效(SecurityLog 落盘点 CS-247 已统一折叠,补回归锚) | 42+3 | dotnet build 0 警告 0 错误(RestoreLockedMode)、Core.Tests 633/633、Broker.Tests 62/62 |
| AD 批 | AD-252..292 全 41 项 + WB-170 + SP-195 + SP-211。要点:尾点 host 整链拒绝+向量(252)/canvas 逐像素 PRNG(253)/closeTab 激活保持三分支(254)/主框架决策分支重构+重定向复核(255/256)/第三处日志泄敏(257)/9 阶段逐阶段断言(272)/SSL·SafeBrowsing 零覆盖补齐(273)/wrapper sha256 钉(277)/shrinkResources(278)/JNA keep 收窄(279)/Gradle 弃用清理+parallel/caching/CC(287/292)/debug 后缀(288)/geolocation+saveFormData 显式关(289)。AD-289 geolocation 无公开 getter(注释+真机链路)、AD-279 运行时冒烟留 CI/真机批、AD-292 第三方插件弃用登记 | 41+3 | 四模块 ktlint+detekt 0 违规、单测 339 全绿(app 246/broker 56/adapter 37)、lintDebug 0 error、assembleRelease 通过 |
| RS 批 | RS-239..274 全 36 项 + PY-249。要点:read_utf8 返回 String 消除 unsound 签名(239)/三层管线 consume 接线 max_uses 生效(240)/AudioBuffer 双读漂移 WeakSet(241)/五处覆盖 ToStringGuard 注册(242)/子域边界补点(243)/timeStamp+timeOrigin 圆整(244)/nonce 账本跨会话保留堵重放窗(247)/JS 相对 URL 剥离(248)/canvas 噪声去退化(249)/原型级 getter 替换(250)/公共后缀表(257)/deny detail 脱敏(258)/FFI 强类型序列化(268)/3 fuzz target(271)/JSON 上限往返修复(260)。RS-251/256 按登记的文档化取舍收口 | 36+1 | cargo fmt/clippy -D warnings/cargo test 509 全过(495+10+4)、fuzz 9 target 编译过 |
| PY 批 | PY-216..257(除归属 SP/RS 项)。要点:sync_versions 修复+集成测试(216)/tests+bindings 83 处 ruff 清零(217/256)/verify_manifest 密钥解码修复+shim 拆除(218)/cryptography 真实重锁(221)/XML 反转义(223)/正则注入(224)/.txt 清单强校验+弱测试改真实哈希(225/250)/arm64 枚举(227)/RFC3339 锚定(228)/canonical 金标双端消费(244)/ruff 显式 select(238)/tab 绑定模拟(252)/bool 类型守卫(251)/catalog 门禁对齐(254)等;PY-243/248 于收尾批 2 同批闭环(生成镜像落并行禁区,须与产物同批) | 38 | ruff 全绿、pytest 275(207→275)、validate/versions/compat/vectors/catalog 全过 |
| WB 批 | WB-133..175(除归属他区项)+ PY-216 文档配套。要点:snake Escape 清零修复+isOpen 标志(133)/导入超时+null 统计(135/136)/hidden 语义(137)/书签失败分流(138)/错误监听前置(140)/forced-colors+44px+对比度+16px(141-144)/__test 条件注入(151)/19 处文档失实修正(152-172/174/175,横幅 7 份/索引对齐/台账衔接后记) | 34+1 | node 100/100、snake 27/27、validate 0 失败 |
| SP 批 | SP-177..217(除归属 AD/PY 项)+ PY-222/245 + WB-173/153/154/155(合并)。要点:8 个 action 重 pin 到 release tag+注记(178,网络实测)/publish 重生成清单后复验(179)/pin-check 抽 composite 单源(182)/clippy 口径统一 -D warnings(183)/13 job setup-python 固化(196)/secrets 显式映射(205)/concurrency 组(206)/CODEOWNERS+config.yml(207/210)/bandit 活跃树接线+根配置(245 部分:mypy 因 scripts 同名模块阻塞,登记)/归档 pip-audit 降告警(216)/pip·gradle·cargo 缓存统一(201/202/204/215) | 41 | YAML 17 解析 0 坏、bandit exit 0、clippy 统一口径 0 警告、verify_versions/validate 过 |
| 主审计收尾 | Kotlin BRIDGE_GUARD_JS 镜像同步新模板(RS-242/PY-249 三端一致)/WB-156 CONTRIBUTING cd 前缀/SP-177 全闭环(锁文件入库+三 workflow RestoreLockedMode+CONTRIBUTING/SECURITY 如实口径)/SP-217 按 WB-102 记账规则随下个正式版本合并记账(事实源=本台账) | 4 | verify_bridge_guard 三端过、dotnet build -p:RestoreLockedMode 0 警告 |
| 收尾批 2 | PY-243/248 生成镜像同批落地:codegen 新增 ident.py 单源(pascal/singular_pascal),两生成器对 array-of-object+properties 生成嵌套子模型(UpdateManifestContractArtifact/Signature + 值域常量类,六字段组全部获得编译期锚点)、自由 object 保持原降级、using 条件输出(4 份去未用 using);pytest 补 5 用例 | 2 | pytest 280(275→280)、compat 对账过、validate 87 文件、ruff 绿、dotnet build 0 警告、:contracts ktlint+compile 过 |
| 中央总验 | 全部正典门禁在六批+收尾合并后整体重跑 | — | ruff 全过、pytest 275、validate/versions/bridge_guard/cross_end/compat/vectors/catalog 全过、node 100/100+snake 27/27、YAML 17/17;cargo/dotnet/gradle 三端重跑结果见下 | 
| 发布链批(2026-10-02) | SP-218/PY-258/PY-259/AD-293/CS-376:v2.2.0-beta.51 tag 触发云端发布链首跑,5 个 workflow 实证失败(Release startup_failure/supply-chain pip-audit/contracts 测试/native-policy 双 job)+ submit-nuget 外部观察(SP-219) | 5+1 | actionlint 0 告警、YAML 全解、Broker.Tests 全 env 双口径 3×62/62、dotnet 0 警告+Core 633、pytest 280、gradle preBuild CC stored/reused、--require-hashes dry-run 过 |
| 发布链批 2(2026-10-02) | SP-220:第二次 tag 跑——android/core 两平台全链路绿,release-windows build NU1004(锁无 RID vs publish --runtime) → 三锁 -r win-x64 重生成 + CI 6 处命令统一 RID + 文档口径 | 1 | locked build 0 警告、Core 633/Broker 62 locked 全绿、锁幂等、YAML/actionlint 过 |
| 发布链批 3(2026-10-02) | SP-221:第三次 tag 跑——三平台 build/sbom/verify 全链路首次全绿,verify-gate core .txt 对账误拒(./ 前缀条目+自排除恒不等) → verify_release 归一化+同侧比较 | 1 | release_chain 44/44(新增双形态回归)、pytest 281、ruff/validate 过 |
| 发布链批 4(2026-10-02) | AD-294/295/296:beta.51 真机闪退——模拟器 x86_64 minified release 复现(AegisCrash 留痕+R8 retrace)双层根因(JNA peer 字段 keep 收窄/R8 full mode 折叠可空字段) → 恢复全量 keep+关闭 full mode;同通道复验进程存活+UI 完整渲染 | 3 | 模拟器冒烟(启动存活+截图)、beta.52 版本推进 verify_versions 过 |

> 完成度:**251 项中 248 项闭环**(含发布链批 10 项);AD-296 以人工模拟器冒烟代偿为部分闭环;CS-345/WB-139 两项经证据推翻登记为无效;PY-245 mypy 半面、AD-289 geolocation 断言半面、AD-279 R8 运行时冒烟留真机批为部分闭环;SP-219 为外部观察不占闭环。跨 9 批全部经区级门禁全绿后落盘。


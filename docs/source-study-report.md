# 8 项目源码研读报告（核心亮点提取）

> 研读日期：2026-08-15 ｜ 范围：D:\abrowser\research 下 8 个克隆项目（浅克隆）
> 目标：提取各项目对 Aegis（pywebview+WebView2 壳 / Kotlin+System WebView 壳）可借鉴的核心实现

---

## 一、研读结论总览

| 项目 | 类型 | 研读收获（核心亮点） | 对 Aegis 的价值 |
|---|---|---|---|
| **min** | Electron 壳 | 99 个 JS 模块、Dexie 全文搜索(tf-idf/stemmer)、模块化搜索栏 | 🟢 最高（同构壳） |
| **falkon** | QtWebEngine 壳 | 317 cpp+318 h、lib 模块化、插件体系、VerticalTabs 2635 行 | 🟢 高（架构参照） |
| **floorp** | Firefox 定制层 | browser-features 特性分层(chrome/modules/pages-*)、工作区 i18n | 🟢 高（特性组织） |
| **zen-browser** | Firefox 定制层 | src/zen/spaces 工作区(同步/样式/测试)、sidebar 组件 | 🟢 高（垂直标签蓝本） |
| **librewolf** | Firefox 构建层 | 三件套配置机制(local-settings.js/policies.json/librewolf.cfg) | 🟡 中（隐私配置） |
| **ungoogled** | Chromium 补丁层 | 108 个去 Google 补丁(禁 update/rlz/扩展/安全浏览上报) | 🟡 中（去后台化） |
| **brave** | Chromium 定制层 | 隐私组件矩阵(shields/ai_chat/ephemeral_storage/global_privacy_control) | 🟡 中（隐私组件） |
| **firefox** | Gecko 本体 | 引擎分层(js/dom/layout/netwerk/gfx/xpcom)、browser/components | 🟢 高（架构全景） |

## 二、各项目核心亮点详解

### 1. min（9.1k★，Electron）—— 同构壳的最高参照

**模块组织**（99 个 JS 文件，单文件单职责典范）：
- `js/` 顶层：browserUI / keybindings / downloadManager / findinpage / focusMode / pdfViewer / pageTranslations / sessionRestore / tabAudio / userscripts / webviewGestures / webviews
- `js/places/`：历史/书签存储（fullTextSearch.js / places.js / tagIndex.js）
- `js/searchbar/`：插件式搜索栏（bangsPlugin / calculatorPlugin / instantAnswerPlugin / placeSuggestionsPlugin / searchSuggestionsPlugin）
- `js/tabState/`：标签状态分层（tab/task/windowSync）
- `js/preload/` + `js/navbar/`：页面预加载与导航栏

**全文搜索历史实现**（Aegis 可移植蓝本）：
- Dexie(IndexedDB) 存 `searchIndex` 字段 + `where('searchIndex').equals(prefix)` 并行查所有 token
- 分词：NFD 归一化去音标 → 空白切分 → 过滤停用词（stopWords）→ stemmer → 截断 20000 token
- 匹配规则：token 命中 searchIndex **或** 命中 title/url/tags（子串匹配）
- 排序：tf-idf（tokenMatchCounts）+ recency/visit 评分（calculateHistoryScore），仅取前 100 文档全文排名（性能取舍）

### 2. falkon（QtWebEngine）—— 壳架构的模块化范式

**lib 模块**（src/lib，自包含模块化）：adblock / autofill / bookmarks / cookies / downloads / history / navigation / network / notifications / session / sidebar / tabwidget / webengine / webtab
**插件体系**（src/plugins）：AutoScroll / GreaseMonkey / MouseGestures / **VerticalTabs(2635 行)** / PyFalkon(Python 插件!) / TabManager / SiteSettingsView
**adblock 实现**：adblockmanager / adblockmatcher / adblocknetworkrequest 分离（管理/匹配/网络请求拦截三职责）

### 3. floorp（8.3k★）—— Firefox 特性层组织

**browser-features 结构**（特性分层范例）：chrome/(UI 注入) / modules/(功能模块) / pages-*(独立页面：settings/newtab/notes/profile-manager)
工作区(workspaces)与垂直标签相关逻辑在 browser-features（i18n 已定位 en-US.json 等 30+ 语言）

### 4. zen-browser（43.9k★）—— 垂直标签/工作区蓝本

- **sidebar 组件**：`src/browser/components/sidebar/`（browser-sidebar-js.patch + 图标体系）
- **workspaces 实现**：`src/zen/spaces/`（create-workspace-form.css / zen-workspaces.css / ZenWorkspacesSync.sys.mjs 同步 + 测试 browser_workspace_*.js）
- **极简 UI**：`src/zen/common/styles/zen-sidebar.css` 等

### 5. librewolf —— 隐私配置三件套

**配置机制**：`content/toggle-settings.sh` 通过启用/禁用三件套控制隐私默认值：
- `local-settings.js`（本地 JS 设置）→ `policies.json`（企业策略）→ `librewolf.cfg`（核心隐私默认配置）
- launch_librewolf.sh 启动脚本组合加载

### 6. ungoogled-chromium（27.4k★）—— 去后台化补丁清单

**108 个补丁**（patches/core 分 bromite/inox-patchset/iridium-browser 多源）：
- 代表性去 Google 补丁：disable-fetching-field-trials / disable-autofill-download-manager / disable-default-extensions / **disable-update-pings** / **disable-rlz** / safe-browsing-disable-incident-reporting

### 7. brave（22k★）—— 隐私组件矩阵

**components 隐私组件**：brave_shields（拦截引擎）/ ai_chat（本地 AI，对应 Aegis 翻译问答）/ **ephemeral_storage**（临时存储隔离）/ **global_privacy_control**（GPC 信号）/ brave_rewards / brave_ads / brave_vpn

### 8. firefox —— Gecko 引擎全景

**引擎分层**：js/(SpiderMonkey) / dom / layout / netwerk / gfx / xpcom(组件模型) / ipc(跨进程) / mfbt(内存基础)
**浏览器层**：browser/components（BrowserGlue.sys.mjs 启动胶水、accounts、aboutlogins 等，ESM 模块化）

## 三、对 Aegis 的可借鉴点汇总

| Aegis 方向 | 借鉴来源 | 具体可移植点 |
|---|---|---|
| 标签增强（垂直/工作区） | zen/floorp/falkon | 垂直标签树 + 工作区同步（建议①） |
| 隐私默认配置 | librewolf | 三件套配置机制 + 默认禁遥测清单（建议②） |
| 全文搜索历史 | min | Dexie searchIndex + tf-idf + stemmer（建议③） |
| 去后台化 | ungoogled | 禁 update-pings/rlz 思路（Aegis 无遥测，对照自查） |
| 隐私组件隔离 | brave | ephemeral_storage/global_privacy_control 思路 |
| 插件体系 | falkon | 插件化架构（Aegis 未来扩展方向） |

## 四、结论

> 8 项目研读完成：min 与 falkon 提供"壳浏览器"的完整实现参照，zen/floorp 提供
> 垂直标签与工作区蓝本，librewolf/ungoogled/brave 提供隐私与去后台化清单，
> firefox 提供引擎全景。下一阶段按建议①（垂直标签+工作区）、②（隐私默认值）、
> ③（全文搜索历史）逐项落地到 Aegis。

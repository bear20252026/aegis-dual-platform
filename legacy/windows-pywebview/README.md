# Aegis —— 加固版套壳浏览器（旧栈归档说明）

> **ARCHIVED（ADR-009 M4，2026-09-05）**：本 Python 功能栈已**整体归档（只读）**。
> Windows 唯一正典栈为 `windows/src/Aegis.Windows.App`（C#/.NET 10 + 原生
> WebView2）——全功能迁移已完成（parity 清单见
> `docs/product/feature-parity-checklist.md`），发布链已单轨（PyInstaller 包
> 移除）。本目录**不再接受任何功能 PR**；P0 安全缺陷仅经安全披露通道评估修复
> （ADR-009 D4 冻结纪律的归档终态）。

> **R-20 整改（体验/功能审查）**：本文档描述的是已归档的 QtWebEngine
> 旧栈（legacy——`windows/aegis_source/legacy/`，不再维护——仅供历史
> 参照）。**当前 Windows 新栈以 `main_webview.py`（pywebview + WebView2）
> 为唯一正式入口**——产品能力以功能注册表（app/features.py）为准，
> 不再宣称两套产品功能（双栈收敛——实施手册 R-20）。

Aegis 是对一款基于 PySide6 + QtWebEngine 的套壳浏览器（原 MyBrowser）
进行**严格安全审计后**的加固重生版。审计发现的每一项缺陷都已修复，
并在其基础上增加了若干"超越商业级"的安全能力。

> 数据完全隔离在独立目录 `AegisData/`，不读取、不共享 Edge/Chrome 数据。

---

## 一、诚实声明（先讲清楚边界）

- **引擎版本不臆造**：具体 Chromium 版本由 QtWebEngine 在运行时如实报告
  （`关于` 对话框与`安全仪表盘`中可见），代码里**不硬编码**任何大版本号。
- **内核版本锁定在 2026 水平**：依赖锁定 `PySide6==6.11.1`，其随附的
  QtWebEngine 捆绑 Chromium 接近 140（2026 年主流水平）。早期误锁
  `6.7.3`（仅捆绑 Chromium 118）是一次**倒退**，已从源码树纠正。
- **内核架构限制**：QtWebEngine 不开放 Chrome 扩展 API，也不开放浏览器级
  "热补丁"通道。部分能力（扩展生态、站点隔离粒度、密码自动填充深度集成）
  受内核架构约束，无法仅靠壳层代码消除——下文"已知局限"如实列出。
- **未做不可验证的性能/测试承诺**：本文档只陈述已落地、可复现的内容；
  安全关键逻辑由 `tools/selftest_security.py` 实测覆盖（见第六节）。

---

## 二、安全加固清单（对照审计发现）

| 等级 | 审计发现 | Aegis 修复 |
|------|----------|------------|
| **C-1 严重** | 更新器下载未验签，可被中间人替换安装包（RCE） | 离线 **Ed25519 签名验签** + 强制 HTTPS + 可选证书锁定（cert pinning）+ 下载后 SHA-256 复核；公钥写死在客户端，私钥离线保管（`tools/sign_release.py`） |
| **H-1 高危** | 安全浏览为空壳（仅 `.example` 占位域名） | 真实 typosquat 种子名单 + 可插拔情报源（本地黑名单 / Google Safe Browsing API v4）；覆盖度**如实告知**用户 |
| **H-2 高危** | 同步传输允许明文 http | WebDAV 强制 HTTPS，Bearer Token 优先于 Basic，依赖系统 CA 校验 |
| **H-3 中危** | 依赖可静默降级导致安全能力丧失 | `requirements.txt` 版本锁定；缺加密库时密码保存**整体禁用**而非降级明文 |
| **M/L** | 单实例 IPC 无认证、配置注入、可执行文件静默下载、UA 伪装等 | IPC 随机令牌认证、配置逐字段类型+scheme 校验、危险下载二次确认、如实 UA |
| **残留** | `.ruff_cache/` 误提交 | 已加入 `.gitignore` |

### 超越项（审计之外的增强）

- **HSTS 预加载 + 强升级**：名单内主机 `http://` 自动升级 `https://`，证书错误不可绕过（SSL stripping 防护）。
- **WebRTC IP 防泄漏**：默认限制 WebRTC 仅暴露公网接口，降低真实内网 IP 暴露。
- **安全态势仪表盘**：菜单内可查看每一项防护的真实状态与覆盖度局限（不夸大、不隐瞒）。
- **统一内联 SVG 图标**：全项目零 emoji 功能图标，统一描边、可矢量缩放（P0 规则）。
- **诚实版本报告**：`engine_version()` 运行时读取 QtWebEngine 真实版本。
- **查看源代码（View Source）**：对标商业浏览器，Ctrl+U / 右键菜单 / 工具菜单
  均可调出；展示渲染后 DOM 的序列化 HTML，带行号、轻量语法高亮、查找与复制。
- **命令面板（Command Palette）**：`Ctrl+Shift+P` 唤起，键盘直达二十余项高频操作
  ——**多数商业浏览器缺失此能力**（超标对标）。
- **强制深色模式**：类 Dark Reader 的全局反色样式，一键切换、新页面即时生效（超标）。
- **站点信息 / 证书透明**：锁形详情展示证书链与 SHA-256 指纹，连接安全性一目了然（对标）。
- **细粒度清除浏览数据**：可分别勾选历史 / Cookie / 缓存 / 密码，对标商业浏览器隐私清理。
- **网页截图（PNG）**：一键截取当前视口为 PNG，对标商业浏览器截图能力。
- **书签导入/导出**：标准 Netscape 书签 HTML，与 Chrome / Firefox / Edge 互导（对标）。
- **密码主密钥接入系统密钥环**：Windows 上即「Windows 凭据管理器」（系统浏览器
  同款 DPAPI 体系），再加 `dpapi.py` 把密钥绑死本机本账户——比 Edge/Chrome 直接把
  密码 blob 丢进 Login Data 更稳（已落地，非本轮新增）。
- **原生翻译（对标沉浸式翻译类插件）**：内核不支持 Chrome 扩展（见已知局限），
  故原生实现翻译面板，直接调用**本地 AI App**（Ollama / LM Studio）的 OpenAI 兼容
  端点——免费、本地运行、无需 API Key，侧栏体验不打断浏览（超标）。
- **页面内双语对照（对标沉浸式翻译正文对照）**：一键在当前页面把原文逐段注入
  本地 AI 生成的译文（叠加在原文下方），再次点击即清除。同样走本地 AI，免费离线（超标）。
- **AI 总结 / 网页问答**：针对当前打开的网页，一键总结要点，或就页面内容提问，
  全程本地 AI、不上传云端（超标对标商业浏览器的侧边 AI）。
- **密码工具（生成 + 本地泄露检测）**：用 `secrets` 生成高强度密码并显示熵估算；
  泄露检测采用 HaveIBeenPwned **k-匿名**模型——仅发送 SHA-1 前 5 位，明文/完整哈希
  不出本机，无需 API Key（对标商业浏览器的密码健康）。
- **本地千问 / Kimi 一键唤起**：在 AI 助手面板内一键打开你本地安装的千问 / Kimi
  桌面 App（免费对话）；并内置「供应商预设」把端点快速切到对应服务（如本地 Qwen
  经 Ollama、Kimi 经 Moonshot 云端兼容端点）。
- **云端 AI 供应商（DeepSeek 等）**：AI 助手面板支持「供应商预设」直接切到
  **DeepSeek** 等 OpenAI 兼容云端服务——填入 API Key 即可让翻译 / 双语对照 / 总结 /
  问答**走云端大模型**，无需本机 GPU、不依赖本地 AI。凭证优先读环境变量、其次存
  `~/.config/aegis/<provider>.key`（与 IMA 凭证同风格，绝不明文写进配置）。默认模型
  用 `deepseek-chat`（DeepSeek 最便宜的型号，对标你说的"flash"档）。**这解决了低配
  笔记本跑不动本地大模型的现实问题**（超标对标商业浏览器的云侧 AI）。
- **浏览并阅读 IMA 知识库**：在 AI 助手面板之外，新增独立入口「IMA 知识库」，可列出
  你 IMA 里的全部知识库（如「昆仑山知识库」）、逐层展开文件夹与文档，文件类条目在
  新标签页渲染原文、笔记类条目直接显示纯文本——边看网页边查阅私有知识库（超标对标
  「企业知识库内嵌」）。同样调用经审计的 IMA OpenAPI 脚本，凭证仅发往 `ima.qq.com`。
- **边看网页边存笔记（IMA 知识库）**：把当前网页的标题 + 网址，连同你写的备注、
  以及页面中选中的原文，整理成一篇 Markdown 笔记，一键存进你的 **IMA（腾讯云知识库）**。
  支持新建，也支持追加到最近的一篇笔记；调用经安全审计的 IMA OpenAPI 脚本，
  凭证仅发往 `ima.qq.com`，本地图片引用自动过滤（超标对标「边读边存」）。
  注：此能力与翻译/总结是**两路独立依赖**——笔记走 IMA 云端（需 API Key），
  翻译/总结走本地 AI（需 Ollama 等），互不影响。

---

## 三、架构

```
Aegis/
├── main.py               # 入口：单实例锁、QtWebEngine 引导、协议集成
├── app/                  # 数据层（与 UI 解耦）
│   ├── browser.py        # BrowserContext 运行时上下文（服务聚合）
│   ├── config.py         # AppConfig 类型化配置（JSON 持久化 + 字段校验）
│   ├── updater.py        # 签名更新框架（Ed25519 + HTTPS + cert pinning）
│   ├── safe_browsing.py  # 恶意/钓鱼站点防护（真实情报源 + 诚实覆盖度）
│   ├── hsts.py           # HSTS 预加载与强升级
│   ├── sync.py           # 端到端加密同步备份（PBKDF2 + Fernet）
│   ├── security.py       # 统一安全关口（scheme 白名单 / 危险下载 / 文件权限）
│   ├── password_store.py # 密码加密存储（keyring / DPAPI / Fernet）
│   ├── ai_client.py      # 本地/云端 AI 调用客户端（翻译/批量/总结/问答，OpenAI 兼容，支持 Bearer Key）
│   ├── password_tools.py # 密码生成 + HIBP k-匿名泄露检测（纯逻辑）
│   ├── ima_client.py     # IMA 知识库 OpenAPI 封装（新建/追加/列表笔记 + 知识库浏览，复用审计脚本）
│   ├── permissions.py    # 站点权限决策（摄像头/麦克风/位置/通知）
│   ├── adblock.py        # 请求级广告/追踪拦截
│   └── ...               # 历史/书签/下载/会话/搜索 等
└── ui/                   # 界面层
    ├── main_window.py    # 主窗口编排
    ├── security_dashboard.py # 安全态势仪表盘
    ├── view_source.py    # 查看源代码对话框（View Source）
    ├── ai_assistant.py   # 本地/云端 AI 助手（翻译/双语对照/总结/提问/唤起千问·Kimi/DeepSeek 预设+Key）
    ├── password_tools.py # 密码工具（生成 + 本地泄露检测）
    ├── ima_notes.py      # 边看网页存笔记到 IMA 知识库（新建/追加）
    ├── ima_knowledge.py  # 浏览并阅读 IMA 知识库（列表/文件夹展开/文档查看，如昆仑山知识库）
    ├── icons.py          # 统一内联 SVG 图标
    └── ...               # 标签栏/地址栏/书签栏/阅读模式/设置 等
```

---

## 四、功能

多标签 · 地址栏联想 · 历史/书签（SQLite）· 广告拦截 · 安全浏览 ·
密码加密管理 · 无痕模式 · 会话崩溃恢复 · 阅读模式 · 查找/下载管理 ·
任务管理器 · 用户脚本 · 加密同步备份（WebDAV 云端推送/拉取）· 跟随系统主题 · Apple 玻璃态视觉 ·
查看源代码（Ctrl+U）· 内置开发者工具（Ctrl+Shift+I / F12，QtWebEngine 原生 DevTools）·
安全态势仪表盘 · 命令面板（Ctrl+Shift+P）· 站点信息/证书查看 · 站点权限管理 · 强制深色模式 ·
细粒度清除浏览数据 · 网页截图（PNG）· 书签导入/导出（HTML）· 书签管理器（多选删除）·
历史按日分组 + 多选删除 · 标签悬停缩略图 · 下载历史（跨会话保留）· i18n 国际化框架 ·
AI 视觉问答（截图 → 视觉模型看图回答，本地 Ollama / 云端 OpenAI 兼容）·
AI 上网代理（截图→决策→执行闭环：自动点击/输入/滚动/后退/搜索/加书签/切换引擎；
权限分级 L0~L3、L3 密码库直填、扫码/短信人工介入）·
AI 助手（翻译/双语对照/总结/问答）· 密码工具（生成 + 本地泄露检测）·
保存到 IMA 笔记（边看网页存笔记到 IMA 知识库，需 IMA API Key）·
浏览 IMA 知识库（列出你的知识库、展开文件夹与文档，需 IMA API Key）。

### AI 视觉能力与云同步配置（设置页 → AI / 同步）

- **AI 视觉**（设置 → AI）：启用后可用「视觉问答（AI）」与「AI 上网代理」。来源二选一：
  - 本地 Ollama：`ollama pull qwen2.5-vl:7b` 后填端点（默认
    `http://localhost:11434/v1/chat/completions`）；
  - 云端 OpenAI 兼容（GPT-4o / Qwen-VL 等）：填端点与模型名，密钥走环境变量
    `VISION_API_KEY` 或 `~/.config/aegis/vision.key`。
  权限分级：L0 只读 / L1 浏览（默认）/ L2 表单输入 / L3 凭据访问（密码库直填，
  需会话前确认，凭据明文不进 AI 上下文）。
- **云同步**（设置 → 同步）：填 WebDAV 地址（强制 HTTPS）与用户名；凭证走环境变量
  `AEGIS_WEBDAV_TOKEN` / `AEGIS_WEBDAV_PASSWORD` 或 `~/.config/aegis/sync.key`
  （`token:xxx` / `password:xxx`）。工具菜单可推送/拉取加密同步包。
- **开发者工具**：Ctrl+Shift+I / F12 打开当前页的 QtWebEngine 原生 DevTools
  （本地 UI，不暴露端口，比远程调试安全）。
- **自测**：`python tools/selftest_security.py`（安全）与
  `python tools/selftest_vision.py`（AI 视觉逻辑）可离线运行。

> 项目 `docs/DESIGN.md` 是界面设计的事实来源（Apple 设计系统）。其第 10 节「Application Chrome — Liquid Glass（液态玻璃）」记录了浏览器外框采用 Windows DWM 原生毛玻璃的实现要点与合规约束（不硬编码颜色、不使用 emoji 图标、禁止紫色渐变）。

---

## 五、运行与打包

```bash
# 依赖（Python 3.10+）
pip install -r requirements.txt
# 推荐补装加密库（无则密码保存自动禁用）
pip install cryptography keyring

# 运行
python main.py
python main.py --incognito              # 无痕
python main.py --profile work           # 独立配置文件
python main.py https://github.com       # 启动即打开

# 发布签名（更新器信任链）
python tools/sign_release.py gen        # 生成 Ed25519 密钥对（私钥勿提交）
# 将打印出的公钥粘贴进 app/updater.py 的 UPDATE_PUBLIC_KEY_B64
python tools/sign_release.py make --version 2.1.0 \
    --url https://update.example.com/Aegis-2.1.0.exe --notes "..."

# 打包（Windows）
pyinstaller --noconfirm --clean --windowed --name Aegis \
    --icon assets/icon.ico --collect-data PySide6 main.py
```

---

## 六、安全自测（可复现）

`tools/selftest_security.py` 覆盖安全关键逻辑，**无需 GUI 即可运行**：

```bash
python tools/selftest_security.py
```

当前覆盖（实测通过）：

- 安全浏览：种子拦截、正常站点不误拦、仅种子时诚实声明有限、关闭态、google 源 gating
- HSTS：`http://`→`https://` 强升级、非名单主机不升级、预加载计数
- 配置：`javascript:` 主页被拒（回退默认）、save/load 往返
- 同步加密：往返一致、错口令拒绝、篡改拒绝、WebDAV 明文拒绝
- 签名更新信任链：真实 Ed25519 验签——正确签名通过、篡改拒绝、错误密钥拒绝、未配置公钥宁可错过更新

GUI/集成层面的端到端测试需真实 Windows + PySide6 运行环境，未随本仓库捆绑；
在具备显示与 PySide6 的环境中应补充窗口/导航/拦截页等手动与集成验证。

---

## 七、已知局限（如实列出）

1. **内核版本节奏**：安全补丁跟随上游 QtWebEngine 发版，无浏览器级热补丁通道。
2. **威胁情报覆盖**：内置种子仅作基线；生产环境应接入 Google Safe Browsing API
   或自托管黑名单源（`threat_feed_url`）并定期更新。
3. **扩展生态**：QtWebEngine 不开放 Chrome 扩展 API（架构硬限制）。
4. **站点隔离/沙箱粒度**：`--site-per-process` 可经 `chromium_flags` 注入，
   但内存代价高，默认未开。
5. **密码密钥强度**：系统密钥环（DPAPI/Keychain）优先；无密钥环时回退本地
   Fernet 文件（已收紧权限），弱于系统级密钥保护。
6. **代码签名/SmartScreen**：Windows 实机需自行完成代码签名与信誉建立。

---

## 八、数据安全

- 所有数据位于 `AegisData/`，删除该目录即可完全清除。
- 密码加密优先系统密钥环；无密钥环时使用 AES 加密文件（仅当前用户权限）。
- 广告拦截仅在请求层生效，不采集任何浏览行为。

## 九、打包与安装（生成 Windows 安装包）

本项目可打包成**标准 NSIS Modern UI 向导**安装程序 `Aegis-Setup.exe`：双击后依次经过
欢迎页 → 许可协议 → 选择安装位置 → 安装进度 → 完成页（可勾选“立即启动”），
并自动创建开始菜单与桌面快捷方式、可正常卸载。外观与常见 Windows 安装包一致，
无需用户预装 Python / Node。

**构建产物（已生成）：**
- `Aegis-Setup.exe` —— 最终安装包（约 288MB，LZMA 压缩）。
- `dist/Aegis/` —— PyInstaller 冻结后的可运行目录（onedir）。
- `aegis.spec` —— PyInstaller 打包配置。
- `installer.nsi` —— NSIS 安装脚本。
- `app/ima/` —— 随包分发的 IMA 资源（含 `ima_api.cjs`、`node.exe`、
  `meta.json`），版本检查已关闭，装到任意电脑都不会被卡。

**重新构建步骤（如需在自己机器上改后重打）：**
1. 安装依赖：`pip install PySide6 cryptography keyring pyinstaller`
2. 冻结：`pyinstaller --noconfirm --clean aegis.spec`
   （产物在 `dist/Aegis/`，含 Qt6 + QtWebEngine 运行数据，约 745MB）
3. 编译安装包：`"%ProgramFiles(x86)%\NSIS\makensis.exe" installer.nsi`
   （注：安装脚本须为 ASCII 编码；源路径避免中文，已统一用 `C:\aegis_build\Aegis`）

**安装到本机：**
- 双击 `Aegis-Setup.exe` → 安装到
  `%LOCALAPPDATA%\Programs\Aegis`（当前用户，无需管理员权限），
  自动创建开始菜单与桌面快捷方式。
- 卸载：开始菜单「Aegis → 卸载 Aegis」，或系统「应用」里卸载。

**关于 IMA 功能可用的前提：**
- IMA 笔记 / 知识库需要凭证文件：`%USERPROFILE%\.config\ima\client_id`
  与 `api_key`（从 https://ima.qq.com/agent-interface 获取）。
- AI 助手（翻译 / 双语对照 / 总结 / 问答）使用 DeepSeek 云端，Key 存于
  `%USERPROFILE%\.config\aegis\deepseek.key`，无需本地大模型。

## 十、版本变更记录

### v2.1.6（标签文字对比度修复：深底白字 / 浅底黑字）

- **问题**：此前非活动标签文字被压到 ~56% 透明度，在深色标签条上几乎不可读，
  多个网页时难以识别/切换标签。
- **修复**：非活动标签文字改为**纯白（深色主题）/ 近黑（浅色主题）全不透明**；
  每个非活动标签给予**可见底色**（不再"隐身"），悬停进一步提亮；
  活动标签靠"更亮底色 + 强调色指示条 + 加粗"区分，**不靠压暗文字**。
- 上方标签栏与左侧垂直标签栏（`_paint_tab` / `_paint_tab_v`）同步生效；
  `_CHROME` 令牌统一调整（theme.py），QPainter 自绘与 QSS 同源。

### v2.1.5（随包壁纸 + 首页图标自定义 + 垂直标签栏）

- **随包壁纸（assets/wallpapers/）**：内置 4 张极光风壁纸（洋红/青柠/暮蓝/紫青）。
  新增 `app/asset_scheme.py`：只读自定义 scheme `aegisasset://`，**白名单 +
  防路径穿越**，仅放行登记的壁纸文件；NTP 的 CSP `img-src` 只放行该 scheme
  （不放 data:/http:）。设置 `ntp_wallpaper` 指定壁纸名，空则回退渐变。
- **首页图标自定义**：`app/dial_store.py` 持久化自定义拨号（dials.json），
  工具菜单「自定义首页拨号…」可增删/排序/恢复默认；自定义后 NTP 只显示该列表。
  URL 仅 http/https，点击仍过 safe_url 关口。
- **垂直标签栏（Edge 风）**：设置/视图菜单/Ctrl+Shift+Y 在「上方标签栏」与
  「左侧垂直标签」间切换；垂直模式行式自绘（图标+标题+关闭键、活动行强调色
  指示条），`BrowserTabBar.set_vertical()` + `QTabBar.RoundedWest` 实现。

### v2.1.4（新标签页图标系统：Apple 级 squircle 拨号图标）

- **拨号图标重做**：`ui/icons_dial.py` 用代码自动生成 iOS 风格
  squircle 图标（品牌渐变 + 顶部镜面高光 + 发丝边），替代原来"标题第一个字"
  的简陋圆形。内置 20+ 常见站点的品牌化图形（Bilibili 电视、GitHub 分支、
  Baidu 爪印、微信双气泡等）；未知站点按域名哈希取六色和谐渐变 + 精致字母徽标。
- **安全不变**：图标为**内联 SVG**（DOM 节点，非图片资源），CSP
  `img-src 'none'` 无需放宽；唯一动态片段（标题首字母）经 html.escape，
  无脚本、无事件处理器。
- **去重修复**：HTML 版拨号按 URL 去重，与 Qt 版 `_collect_dials` 行为对齐
  （同站点同时在历史与书签时不再重复出现）。
- **Qt/HTML 双版一致**：`new_tab_page.py` DialCard 同步改用品牌渐变 squircle。

### v2.1.3（UI 重设计：Microsoft Edge Fluent × Apple Liquid Glass）

- **设计语言融合**：窗口外框改为 Fluent 云母（Mica）层级——活动标签与
  工具栏渐变同色「融合」（Edge 标志语言），标签为顶部大圆角玻璃卡片、
  相邻非活动标签间发丝分隔线；地址栏/搜索框/CTA 统一液态玻璃胶囊。
- **新标签页**：极光 mesh 渐变背景（蓝/青/白，无紫）+ 玻璃速拨卡
  （顶部镜面高光、悬停上浮、软投影），深浅两套完整调校。
- **令牌纪律**：新增 `_CHROME` 云母令牌与 `chrome()` 导出函数，
  QPainter 自绘与 QSS 共用同源；修复 NTP 内 CSS 硬编码强调色
  （改为跟随配置强调色 + `#RRGGBB` 白名单校验，杜绝样式注入）。
- **Qt 渲染修正**：实测 Qt QSS `border-radius` 超过控件半高会退化为
  小圆角，新增 `RADIUS_CAPSULE` 并全面替换 QSS 中的 980px 胶囊值。
- **安全不变式保持**：v2.1.2 全部安全修复原样保留；新标签页 CSP
  （script-src 'none' / form-action https:）、html.escape、safe_url
  白名单、35 项安全自测全绿不变。

### v2.1.2（安全复审修复）

对 v2.1.1 做全量复审（静态分析 + 逻辑走查 + 离线自测）后修复，
并在 `tools/selftest_security.py` 中补齐 10 项回归自测（35 项全绿）：

1. **AI 助手面板整体失效（P0）**：`QWidget` 未导入导致面板打开即崩溃；
   API Key 被误填入 `timeout` 参数位，翻译/双语对照/总结/问答四类功能
   在任意供应商下全部失效、云端鉴权头从未发出。已修复并接线 `api_key`。
2. **更新器下载完整性缺口（高危）**：manifest 中 `sha256` 为空时下载
   跳过哈希复核；下载请求默认跟随 https→http 降级重定向；证书锁定只
   作用于 manifest 阶段。现：SHA-256 缺失/非法直接拒下、重定向策略降为
   NoLessSafe、锁定覆盖下载阶段、SSL 失败清理临时文件。
3. **WebDAV 同步凭据降级泄露（高危）**：urllib 默认跟随重定向并转发
   `Authorization` 头，https→http 跳转即明文泄密；现拒绝非 HTTPS 跳转、
   跨主机跳转剥离鉴权头。
4. **L3 密码库直填命中链断裂（高危功能缺陷）**：按 `scheme+host` 精确
   匹配存储 URL 几乎必然失配，且 R9 eTLD+1 归一化从未接入。现由
   `PasswordStore.find_for_host()` 按归一化可注册域匹配；
   `vision_l3_confirm` 设置项开始真正生效。
5. **密钥/凭证面收敛**：AI 供应商 Key 落盘后收紧为 0600；密码主密钥
   解析失败（DPAPI 换机等）不再让整个浏览器启动崩溃，改为禁用密码保存
   并保留原因；IPC 令牌改为恒定时序比较并支持分片缓冲读取。
6. **跨线程回调静默丢失**：威胁情报刷新与 WebDAV 推/拉在工作线程里
   调 `QTimer.singleShot`（无事件循环即丢失），统一改走 `MainBridge`。
7. **其他**：AI 动作 JS 模板占位符串扰、Google Safe Browsing 版本号/
   平台硬编码、同步恢复 URL 未过 scheme 白名单、无痕模式 UA 不一致、
   审计日志无滚动、设置页主页即时校验、重复定义的死代码移除；
   依赖 `cryptography` 提级 43.0.3→50.0.0；`selftest_security` 纳入 CI
   （此前发布管线漏跑安全自测，且 v2.1.1 无法通过自身 ruff 门禁）。


# Aegis 部分重构技术路线文档（pytauri-migration-technical-plan）

> 编制日期：2026-08-15 ｜ 级别：国家项目 / 专家级
> 路线：部分重构（保留全部 Python 业务，目标换 Tauri 壳）
> 依据：官方全文文档（pytauri/Tauri Sidecar，中英双语）+ examples 源码 + Tune 源码 + 技术网站

---

## 〇、结论速览

**推荐路线：pytauri-wheel（全 Python）为主，standalone 备选，sidecar 不推荐。**
- **pytauri-wheel**：免 Rust 编译器、Pyo3 直连（无 IPC 开销）、Windows Tier 1 平台支持、wheel 预编译 + sdist 全 Python——**Aegis 零 Rust 成本路径**
- **standalone**：需 Rust 编译器 + python-build-standalone 捆绑（体积上升 + rpath/install_name 补丁），但产出独立可执行（政府内网免 Python 运行时）
- **sidecar**：进程间 JSON-RPC 通信改造成本高于 B（NavQueue 语义需重构），仅 B 遇 wheel 平台覆盖问题才回退

## 一、三条路线对比（官方文档 + 源码核实）

| 维度 | A. pytauri standalone | B. pytauri-wheel（全 Python） | C. Tauri sidecar |
|---|---|---|---|
| Rust 门槛 | 需 Rust 编译器（几乎不写业务 Rust） | **免 Rust 编译器**（`pip install "pytauri-wheel == 0.8.*"`） | 需 Rust（壳层） |
| 通信 | Pyo3 直连（无 IPC 开销） | Pyo3 直连（无 IPC 开销） | JSON-RPC stdin/stdout（序列化开销） |
| 打包 | tauri-cli 独立可执行（签名/安装器/更新器全收益）；捆绑 python-build-standalone | wheel 分发（PyPI）+ build-sdist 全 Python；可再 tauri-cli 打包 | PyInstaller → externalBin（target-triple 后缀） |
| Python 业务 | ✅ 全保留 | ✅ 全保留 | ✅ 全保留 |
| 源码保护 | Cython（private.py 示例） | Cython | PyInstaller |
| 成熟度 | examples/tauri-app 完整；Windows Tier 1 | examples/tauri-app-wheel 完整；pip 即装 | Tune PR #7 生产案例 |
| 关键坑 | python-build-standalone rpath/install_name 补丁、PYO3_PYTHON、RUSTFLAGS | wheel 平台覆盖（windows-2022 x64/windows-11 arm64 等） | PyInstaller --clean、NSIS hooks 杀进程、CSP |

## 二、Aegis 落地方案（推荐组合）

### 主路线：B（pytauri-wheel）
1. **零 Rust 成本**：Python 业务全保留（30 提交安全纵深零回归）
2. **无 IPC 开销**：Pyo3 直连 ≈ 现 NavQueue 同进程语义（无需 JSON-RPC 进程通信改造）
3. **Windows Tier 1**：作者主环境 Windows 10 = Aegis 目标平台
4. 分发：wheel 预编译 + build-sdist（hatchling 打包，`[tool.hatch.build] artifacts` 含 frontend）

### 备选：A（standalone）
- 触发条件：政府内网需独立可执行（免 Python 运行时）
- 工程：python-build-standalone 捆绑（`src-tauri/pyembed`）+ `PYTAURI_STANDALONE=1` + `uv pip install --python=pyembed` + `tauri.bundle.json` resources + `PYO3_PYTHON`/`RUSTFLAGS rpath`/macOS `install_name` 补丁 + `tauri build --profile bundle-release`

### 不推荐：C（sidecar）
- JSON-RPC 进程通信改造成本高于 B；仅 wheel 平台覆盖问题时回退（Tune 案例为参考）

## 三、Aegis 分步落地

```
第 1 步：ACL deny 复核（零风险，本周）
第 2 步：预研跑通 examples/tauri-app-wheel（pip install pytauri-wheel + uv 打包）✅ 已确认可跑
第 3 步：PoC——Aegis 最小壳（窗口+导航）用 pytauri-wheel 搭起
        ├─ Tauri.toml：frontendDist=start.html + [[app.windows]]（标题/尺寸）
        ├─ capabilities：ipc 权限白名单（≈ 现 js_api 白名单映射）
        └─ main.py：webview.create_window → pytauri 窗口 API（仅改桥层）
第 4 步：分模块迁移（壳→桥→安全模块），每模块回归（smoodit 经验：Aegis 分层清晰已具备）
第 5 步：PoC 三关实测（体积/内存/启动 vs pywebview 基线）达标才正式迁移
```

## 四、关键技术细节（官方文档核实）

### 4.1 pytauri-wheel（B 路线核心）
- 安装：`pip install "pytauri-wheel == 0.8.*"`（预编译 wheel：windows-2022 x64/windows-11 arm64/manylinux/macOS）
- 配置：`Tauri.toml`（productName/identifier/frontendDist/withGlobalTauri/[[app.windows]]）+ capabilities（ipc 权限）
- 入口：`__main__.py` → `from tauri_app_wheel import main; sys.exit(main())`
- 打包：hatchling（`[tool.hatch.build] artifacts = ["src/tauri_app_wheel/frontend/"]`）
- 依赖：`pytauri == 0.3.*` + `pytauri-wheel == 0.3.*`（examples 版本；主仓库最新 v0.8.0 以 PyPI 为准）

### 4.2 standalone（A 路线备选）
- 便携 Python：python-build-standalone → `src-tauri/pyembed`（tauri-cli 忽略）
- 环境变量：`PYTAURI_STANDALONE=1`、`PYO3_PYTHON=pyembed 的 python`、`RUSTFLAGS=-C link-arg=-Wl,-rpath,...`
- macOS：`install_name_tool -id '@rpath/libpython3.x.dylib'`（上游 python-build-standalone 未修）
- 构建：`tauri build --config="src-tauri/tauri.bundle.json" -- --profile bundle-release`（勿在 tauri.conf.json 直接设 bundle.resources）

### 4.3 sidecar（C 路线参考，Tune 案例）
- `externalBin` + `-$TARGET_TRIPLE` 后缀（`rustc --print host-tuple`）
- capabilities：`shell:allow-execute`（spawn 用 allow-spawn）+ args validator
- Rust：`app.shell().sidecar(name).spawn()`（只传文件名）；JS：`Command.sidecar('binaries/x')`
- 生命周期：PyInstaller `--clean`、NSIS `installerHooks` 杀进程删旧二进制、CSP 配置、版本 bump

## 五、信源清单（本轮部分重构调研）

- 官方文档：pytauri.github.io（tutorial/pytauri-wheel/build-standalone/build-sdist）、v2.tauri.app/develop/sidecar + capabilities
- 开源源码：github.com/pytauri/pytauri（examples/tauri-app + tauri-app-wheel + nicegui-app，已克隆 D:/abrowser/research/pytauri）、github.com/mauriceboe/Tune（src-tauri/src/sidecar.rs，已克隆）
- 技术网站：pytauri README（几乎不写 Rust/pytauri-wheel/无 IPC 开销/Cython）、HN pytauri 讨论（异步勿跨 FFI 边界）
- 前轮结论：tauri-migration-report(-2).md、rust-desktop-landscape-2026.md、KNOWLEDGE_BASE 第 9/10 节

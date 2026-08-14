"""config.py —— 应用配置（类型化、带默认值、JSON 持久化）。

商业级要求配置项"真正生效"，因此这里集中管理所有可配置项，
并显式提供默认值。改配置后由各模块读取最新值。
"""

import json
import os
from dataclasses import asdict, dataclass, field


@dataclass
class AppConfig:
    """全局配置。新增配置项时只需在此增加字段与默认值。"""

    # ---- 外观 ----
    theme: str = "auto"             # auto(跟随系统) | dark | light
    accent_color: str = "#0071e3"     # Apple Blue（唯一强调色，DESIGN.md）
    font_size: int = 13
    language: str = "zh-CN"           # 界面语言（R11：zh-CN | en，重启生效）
    show_bookmark_bar: bool = True
    # R1 用户快捷键覆盖（JSON 字符串，如 '{"new_tab":"n","close_tab":"x"}'；
    # 空串=使用默认表 DEFAULT_KEYBINDINGS）。值须为单字符按键。
    keybindings_json: str = ""

    # ---- 搜索与主页 ----
    engine: str = "baidu"             # baidu | bing | google | sogou
    homepage: str = "https://www.baidu.com"
    use_speed_dial_newtab: bool = True

    # ---- 启动行为 ----
    resume_session: bool = False      # 启动恢复上次会话
    startup_pages: str = "homepage"   # homepage | speeddial | blank | resume

    # ---- 新标签页与标签布局（v2.1.5）----
    # tabs_position: top=顶部标签栏（经典），left=左侧垂直标签栏（Edge 风）
    tabs_position: str = "top"        # top | left
    # ntp_wallpaper: NTP 背景壁纸；空串=默认 mesh 渐变，
    # 否则必须命中随包壁纸白名单（见 app/asset_scheme.WALLPAPERS）。
    # 默认启用「暮蓝」随包壁纸（可在 设置→外观 切换或清空）。
    ntp_wallpaper: str = "aurora-twilight.jpg"

    # ---- 隐私 ----
    adblock: bool = True              # 广告拦截
    do_not_track: bool = True
    save_passwords: bool = True
    use_system_proxy: bool = True     # 使用系统代理
    safe_browsing: bool = True        # 恶意/钓鱼网站防护
    safe_browsing_provider: str = "local"   # local | google
    safe_browsing_api_key: str = ""        # Google Safe Browsing API 密钥
    webrtc_ip_leak_protection: bool = True  # 防 WebRTC 泄露真实 IP

    # ---- 性能 ----
    hibernate_background_mins: int = 10   # 后台标签休眠阈值，0=关闭（标准 #6）
    http_cache_mb: int = 400              # HTTP 磁盘缓存上限
    chromium_flags: str = ""              # 附加 Chromium 启动参数（高级）

    # ---- 网络/隐私补充 ----
    search_suggestions: bool = True   # 地址栏远程搜索建议（关闭则只用本地）
    # 恶意站点情报订阅源（纯文本域名列表）。强制 https://；
    # file:// 仅在环境变量 AEGIS_THREAT_FEED_ALLOW_FILE=1 时允许（离线自测）。
    threat_feed_url: str = ""

    # ---- 更新 ----
    update_url: str = ""              # 更新清单(manifest.json)地址，空=关闭
    update_auto_check: bool = True    # 启动后自动检查一次
    update_pinned_cert_sha256: str = ""  # 可选：更新服务器叶子证书 SHA-256 锁定

    # ---- 下载 ----
    download_dir: str = ""            # 空 = 系统下载目录
    ask_download_location: bool = True

    # ---- 无痕 ----
    incognito: bool = False

    # ---- 开发 ----
    devtools_port: int = 0   # 0=关闭；>0 开启远程调试端口
    force_dark: bool = False  # 强制深色模式（注入反色样式表，类 Dark Reader）
    translate_endpoint: str = "http://localhost:11434/v1/chat/completions"  # 本地 AI 端点（Ollama/LM Studio/兼容 OpenAI）
    translate_model: str = ""   # 模型名（Ollama 必填，如 qwen2.5:7b）
    translate_target: str = "中文"  # 目标语言
    ai_provider: str = "ollama"  # ollama | qwen | kimi | custom（供应商预设）
    qwen_app_path: str = ""      # 本地千问桌面 App 的 exe 路径（一键唤起）
    kimi_app_path: str = ""      # 本地 Kimi 桌面 App 的 exe 路径（一键唤起）
    ima_default_folder_id: str = ""  # 保存笔记到的默认 IMA 笔记本（空=默认位置）

    # ---- AI 视觉能力（vision_*，设计文档 §3）----
    vision_enabled: bool = False      # 总开关（默认关，诚实原则）
    vision_provider: str = "ollama"   # ollama | cloud | custom
    vision_endpoint: str = "http://localhost:11434/v1/chat/completions"
    vision_model: str = ""            # 空=按 provider 取默认（ollama 用 qwen2.5-vl:7b）
    vision_max_image_width: int = 1280   # 截图最长边（发送前缩放）
    vision_jpeg_quality: int = 80        # JPEG 压缩质量
    vision_step_limit: int = 50          # 模式 B 单会话最大步数
    vision_step_timeout: float = 30.0    # 单步（截图→决策→执行）超时秒数
    vision_interval_ms: int = 2500       # 相邻两次截图最小间隔
    vision_cloud_key_provider: str = "vision"  # 云端密钥文件名（~/.config/aegis/<值>.key）
    vision_permission_level: int = 1     # 权限等级 0~3（L3=可访问密码库）
    vision_l3_confirm: bool = True       # L3 会话开始前确认弹窗
    vision_l3_max_sites: int = 3         # L3 会话允许访问的凭据域名上限
    vision_qr_wait_sec: int = 180        # 扫码等待上限

    # ---- HTTPS-First（R4）：off | balanced | strict ----
    # balanced：裸域名 https 失败自动回退 http（现状）；strict：不回退，
    # 仅展示警示；off：不启用升级回退策略。
    https_first_mode: str = "balanced"

    # ---- 云同步（WebDAV；token/密码不入配置，见 sync.load_webdav_auth）----
    sync_webdav_url: str = ""            # 强制 https://
    sync_webdav_user: str = ""           # WebDAV 用户名（可空，凭证走文件/环境变量）

    # ---- DoH 加密 DNS（R3：off | auto | secure）----
    doh_mode: str = "off"                # 默认关（参数需在目标 Chromium 验证）
    doh_provider: str = "cloudflare"     # cloudflare | google | alidns | dnspod

    # ---- 其他 ----
    enable_plugins: bool = False      # Qt5 无 NPAPI，保持关闭（最小攻击面）
    enable_javascript: bool = True
    default_zoom: float = 1.0
    zoom_map: dict = field(default_factory=dict)  # 站点 -> 缩放倍率

    def save(self, data_dir: str):
        """持久化到 config.json（POSIX 下收紧为 0600）。"""
        os.makedirs(data_dir, exist_ok=True)
        path = os.path.join(data_dir, "config.json")
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(asdict(self), f, ensure_ascii=False, indent=2)
            from .security import harden_perms
            harden_perms(path)
        except OSError:
            pass

    @classmethod
    def load(cls, data_dir: str) -> "AppConfig":
        """从磁盘加载。v1.4 M5 修复：逐字段类型校验，
        非法值一律回退默认（杜绝把 homepage 改成 javascript: 之类的注入）。"""
        cfg = cls()
        defaults = cls()
        path = os.path.join(data_dir, "config.json")
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    for k, v in data.items():
                        if not hasattr(defaults, k):
                            continue
                        dft = getattr(defaults, k)
                        if isinstance(dft, bool):
                            if isinstance(v, bool):
                                setattr(cfg, k, v)
                        elif isinstance(dft, int):
                            if isinstance(v, int) and not isinstance(v, bool):
                                setattr(cfg, k, v)
                        elif isinstance(dft, float):
                            if isinstance(v, (int, float)) and not isinstance(v, bool):
                                setattr(cfg, k, float(v))
                        elif isinstance(dft, str):
                            if isinstance(v, str):
                                setattr(cfg, k, v)
                        elif isinstance(dft, dict) and isinstance(v, dict):
                            setattr(cfg, k, {
                                str(a): b for a, b in v.items()
                                if isinstance(b, (int, float))})
            except (json.JSONDecodeError, OSError):
                pass
        # ---- 字段级约束（类型通过后再做语义校验）----
        if cfg.theme not in ("auto", "dark", "light"):
            cfg.theme = defaults.theme
        if cfg.language not in ("zh-CN", "en"):
            cfg.language = defaults.language
        cfg.font_size = max(11, min(20, cfg.font_size))
        cfg.devtools_port = max(0, min(65535, cfg.devtools_port))
        cfg.http_cache_mb = max(0, min(4096, cfg.http_cache_mb))
        cfg.hibernate_background_mins = max(0, min(1440, cfg.hibernate_background_mins))
        # URL 字段 scheme 白名单：拒绝 javascript:/file: 等
        from .security import safe_url
        if not safe_url(cfg.homepage):
            cfg.homepage = defaults.homepage
        # 更新源与情报订阅源强制 HTTPS（明文 http 可被投毒/中间人篡改）
        if cfg.update_url and not cfg.update_url.lower().startswith("https://"):
            cfg.update_url = defaults.update_url
        # threat_feed_url：仅 https；file:// 需显式开启离线测试开关
        from .threat_feed import validate_feed_url
        cfg.threat_feed_url = validate_feed_url(cfg.threat_feed_url)
        # ---- AI 视觉能力校验（设计文档 §3.2）----
        if cfg.vision_provider not in ("ollama", "cloud", "custom"):
            cfg.vision_provider = defaults.vision_provider
        cfg.vision_max_image_width = max(320, min(2560, cfg.vision_max_image_width))
        cfg.vision_jpeg_quality = max(40, min(95, cfg.vision_jpeg_quality))
        cfg.vision_step_limit = max(1, min(500, cfg.vision_step_limit))
        cfg.vision_step_timeout = max(5.0, min(120.0, cfg.vision_step_timeout))
        cfg.vision_interval_ms = max(500, min(10000, cfg.vision_interval_ms))
        cfg.vision_permission_level = max(0, min(3, cfg.vision_permission_level))
        cfg.vision_l3_max_sites = max(1, min(20, cfg.vision_l3_max_sites))
        cfg.vision_qr_wait_sec = max(30, min(600, cfg.vision_qr_wait_sec))
        # 云同步 WebDAV 地址强制 HTTPS（明文传输凭据会被窃听）
        if cfg.sync_webdav_url and not cfg.sync_webdav_url.lower().startswith("https://"):
            cfg.sync_webdav_url = defaults.sync_webdav_url
        # HTTPS-First（R4）：非法档位回退 balanced
        if cfg.https_first_mode not in ("off", "balanced", "strict"):
            cfg.https_first_mode = defaults.https_first_mode
        # DoH（R3）：非法档位回退 off
        if cfg.doh_mode not in ("off", "auto", "secure"):
            cfg.doh_mode = defaults.doh_mode
        # ---- v2.1.5：标签布局 / NTP 壁纸白名单校验 ----
        if cfg.tabs_position not in ("top", "left"):
            cfg.tabs_position = defaults.tabs_position
        # 壁纸白名单：只允许随包登记的文件名或空（回退渐变），杜绝
        # 把任意路径/URL 写进背景值（样式注入 + 本地文件探测面）。
        try:
            from .asset_scheme import WALLPAPERS
            if cfg.ntp_wallpaper and cfg.ntp_wallpaper not in WALLPAPERS:
                cfg.ntp_wallpaper = defaults.ntp_wallpaper
        except Exception:
            if cfg.ntp_wallpaper:
                cfg.ntp_wallpaper = defaults.ntp_wallpaper
        return cfg

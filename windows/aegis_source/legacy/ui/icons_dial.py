# -*- coding: utf-8 -*-
"""icons_dial.py —— 新标签页拨号图标系统（v2.1.4：Apple 级 squircle 图标）。

设计目标：替代"标题第一个字"的简陋圆形，用**代码自动生成**的
iOS 风格 squircle 图标（圆角方块 + 品牌渐变 + 顶部镜面高光 + 发丝边）：

- 已知站点：品牌化渐变底色 + 简化的品牌图形（内联 SVG 路径）；
- 未知站点：按域名哈希取一套和谐渐变色 + 精致字母徽标（回退也体面）。

安全（P0）：
- 输出为**内联 SVG**（DOM 节点，非图片资源），NTP 的 CSP
  `img-src 'none'` 不需要放宽，也不引入任何外部加载；
- 全部图形模板为模块内常量；唯一动态片段是站点标题首字母，
  统一经 html.escape 转义；无 <script>、无事件处理器属性；
- 遵守项目配色约束：品牌渐变不含紫色（Figma 例外用蓝替代紫）。

API：
- dial_icon_svg(url, title, uid) -> str：返回 56x56 内联 SVG 片段
- brand_palette(host) -> (top, bottom) | None：品牌渐变色（Qt 侧复用）
"""

import html as _html
from urllib.parse import urlparse

_SVG_FONT = ("-apple-system,BlinkMacSystemFont,'SF Pro Display',"
             "'Segoe UI','Microsoft YaHei',sans-serif")


# ---------------------------------------------------------------------- #
# 品牌图形库：key 为可注册域后缀；val = (渐变上, 渐变下, 图形 SVG, 图形色)
# 图形在 56x56 坐标系内手工绘制，白色为默认图形色。
# ---------------------------------------------------------------------- #
def _t(ch, size=26, weight=600, fg="#ffffff", family=None):
    """居中文字徽标（首字母/汉字徽标通用构建器）。"""
    fam = family or _SVG_FONT
    return (f'<text x="28" y="29" text-anchor="middle" '
            f'dominant-baseline="central" font-family="{fam}" '
            f'font-size="{size}" font-weight="{weight}" fill="{fg}">'
            f'{ch}</text>')


_BRANDS = {}


def _brand(domain: str, top: str, bottom: str, glyph: str,
           fallback_char: str = ""):
    _BRANDS[domain] = {"top": top, "bottom": bottom, "glyph": glyph,
                       "char": fallback_char}


# ---- 搜索/工具 ----
_brand("baidu.com", "#4e86ff", "#2456e6",
       '<g fill="#fff"><circle cx="20" cy="17.5" r="4.4"/>'
       '<circle cx="28" cy="14" r="4.4"/><circle cx="36" cy="17.5" r="4.4"/>'
       '<path d="M28 23.5c-6.8 0-12.3 4.8-12.3 10.7 0 4.6 3.7 7.8 8.2 7.8 '
       '1.7 0 2.7-.8 4.1-.8s2.4.8 4.1.8c4.5 0 8.2-3.2 8.2-7.8 '
       '0-5.9-5.5-10.7-12.3-10.7z"/></g>', "百")
_brand("bing.com", "#0fb9b1", "#067d78",
       '<path fill="#fff" d="M20 8.5l9 3.2v25.6l15.5-6.5-7-3.3-8.5 3.5V8.5z"/>',
       "B")
_brand("google.com", "#4285f4", "#2b6cd4", _t("G", 30, 700), "G")
_brand("sogou.com", "#fd6336", "#d84315", _t("S", 28, 700), "搜")

# ---- 社区/内容 ----
_brand("zhihu.com", "#3aa2ff", "#1672e0", _t("知", 27, 700), "知")
_brand("bilibili.com", "#fb7299", "#e14d78",
       '<g><rect x="13" y="21.5" width="30" height="20" rx="6" fill="none" '
       'stroke="#fff" stroke-width="3.4"/><path d="M20.5 21l-5.5-7.5M35.5 21l5.5-7.5" '
       'stroke="#fff" stroke-width="3.4" stroke-linecap="round"/>'
       '<circle cx="23" cy="31.5" r="2.2" fill="#fff"/>'
       '<circle cx="33" cy="31.5" r="2.2" fill="#fff"/></g>', "哔")
_brand("weibo.com", "#f7a23c", "#e5701f",
       '<g><path fill="#fff" d="M24.5 41c-7.5 0-13.5-3.9-13.5-9.3 0-6.9 8-14.7 '
       '15.4-14.7 2.9 0 5.2 1 6.4 2.8.5.8.8 1.7.9 2.7 2.6.3 4.5 1.7 4.5 4.3 '
       '0 6.5-6.2 14.2-13.7 14.2z"/><circle cx="23" cy="31" r="2" '
       'fill="#e5701f"/><path d="M35 10c4 .5 7.5 3.9 8 8" fill="none" '
       'stroke="#fff" stroke-width="2.6" stroke-linecap="round"/></g>', "微")
_brand("douyin.com", "#1c1e26", "#0a0b10",
       '<g fill="#fff"><circle cx="22.5" cy="37.5" r="5.5"/>'
       '<rect x="25.8" y="12.5" width="3.6" height="25" rx="1.8"/>'
       '<path d="M29.4 12.5c2.8 4.4 7.2 5 9.6 3.6v6.2c-3.6 1.2-7-.6-9.6-3.4z"/>'
       '</g>', "抖")
_brand("wikipedia.org", "#ffffff", "#ececf0",
       _t("W", 30, 700, "#37373c", "Georgia,'Times New Roman',serif"), "W")
_brand("news.qq.com", "#3d8bff", "#1f63dd", _t("Q", 30, 700), "Q")
_brand("iqiyi.com", "#1cc749", "#0f9b32", _t("奇", 27, 700), "奇")

# ---- 开发者/工具 ----
_brand("github.com", "#475365", "#232a35",
       '<g fill="none" stroke="#fff" stroke-width="3.2" stroke-linecap="round">'
       '<circle cx="19" cy="15.5" r="4.6"/><circle cx="19" cy="40.5" r="4.6"/>'
       '<circle cx="37" cy="15.5" r="4.6"/><path d="M19 20.2v15.6"/>'
       '<path d="M37 20.2c.4 8-6 9.8-13.4 11"/></g>', "G")
_brand("csdn.net", "#f0553d", "#c93521",
       '<g fill="none" stroke="#fff" stroke-width="3.4" stroke-linecap="round" '
       'stroke-linejoin="round"><path d="M21 20l-8.5 8L21 36"/>'
       '<path d="M35 20l8.5 8L35 36"/><path d="M30.5 17l-5 22"/></g>', "C")
_brand("juejin.cn", "#2f86f6", "#1460cf",
       '<g><path d="M28 11.5L42.5 26 28 44.5 13.5 26z" fill="none" '
       'stroke="#fff" stroke-width="3.2" stroke-linejoin="round"/>'
       '<path d="M21.5 26l6.5 8 6.5-8" fill="none" stroke="#fff" '
       'stroke-width="3.2" stroke-linecap="round" stroke-linejoin="round"/></g>',
       "掘")
_brand("figma.com", "#ffffff", "#f3f3f6",
       '<g><rect x="15.5" y="10.5" width="12" height="11" rx="5.5" '
       'fill="#f24e1e"/><rect x="15.5" y="22.5" width="12" height="11" rx="5.5" '
       'fill="#0acf83"/><circle cx="34.5" cy="16" r="5.5" fill="#1abcfe"/>'
       '<rect x="28.5" y="34" width="12" height="11" rx="5.5" '
       'fill="#ff7262"/></g>', "F", )
_brand("linear.app", "#31363f", "#181b21",
       '<g fill="none" stroke="#fff" stroke-width="3" stroke-linecap="round">'
       '<circle cx="28" cy="28" r="14.5"/><path d="M16.5 28.5l11 11"/>'
       '<path d="M20 21.5l16 16"/><path d="M25.5 15.5l16 16"/></g>', "L")
_brand("deepseek.com", "#4d6bfe", "#2c47d6",
       '<g fill="none" stroke="#fff" stroke-width="3.4" stroke-linecap="round">'
       '<path d="M12 25c4.2-5.4 8.2-5.4 12.4 0s8.2 5.4 12.4 0"/>'
       '<path d="M12 34c4.2-5.4 8.2-5.4 12.4 0s8.2 5.4 12.4 0"/></g>', "深")
_brand("openai.com", "#12b981", "#088a5f",
       '<g stroke="#fff" stroke-width="4" stroke-linecap="round">'
       '<path d="M28 13.5v29"/><path d="M15.4 20.8l25.2 14.4"/>'
       '<path d="M40.6 20.8L15.4 35.2"/></g>', "A")
_brand("moonshot.cn", "#20232f", "#0d0f16",
       '<path fill="#fff" d="M33.5 11.5a17 17 0 1 0 10.8 26A14.6 14.6 0 0 1 '
       '33.5 11.5z"/><circle cx="39" cy="17" r="1.8" fill="#fff"/>'
       '<circle cx="43.5" cy="22" r="1.1" fill="#fff"/>', "K")

# ---- 电商 ----
_brand("taobao.com", "#ff8f2b", "#f45a00", _t("淘", 27, 700), "淘")
_brand("jd.com", "#e8434a", "#c41c26", _t("京", 27, 700), "京")

# ---- 社交/通讯 ----
_brand("qq.com", "#3d8bff", "#1f63dd", _t("Q", 30, 700), "Q")
_brand("wechat.com", "#12c45f", "#0a9a47",
       '<g><path fill="#fff" d="M23.5 38.5c-6.6 0-12-4.2-12-9.5 0-5.4 5.4-9.6 '
       '12-9.6s12 4.2 12 9.6c0 5.3-5.4 9.5-12 9.5z" transform="translate(-2,-8)" '
       'opacity=".95"/><circle cx="16.8" cy="23" r="1.7" fill="#0a9a47"/>'
       '<circle cx="24.2" cy="23" r="1.7" fill="#0a9a47"/><path fill="#fff" '
       'd="M35 46c-5.6 0-10.2-3.5-10.2-8s4.6-8 10.2-8 10.2 3.5 10.2 8-4.6 8-10.2 8z"/>'
       '<circle cx="31.6" cy="37.6" r="1.5" fill="#0a9a47"/>'
       '<circle cx="38.4" cy="37.6" r="1.5" fill="#0a9a47"/></g>', "微")
_brand("x.com", "#16181d", "#000000", _t("X", 28, 800), "X")
_brand("twitter.com", "#1d9bf0", "#0c7fd6",
       '<path fill="#fff" d="M43 15.5c-1.2.6-2.5 1-3.9 1.2a6.7 6.7 0 0 0 3-3.7 '
       '13.4 13.4 0 0 1-4.3 1.6 6.7 6.7 0 0 0-11.6 4.6A19 19 0 0 1 12.4 12a6.7 '
       '6.7 0 0 0 2.1 9 6.6 6.6 0 0 1-3-.9v.1a6.7 6.7 0 0 0 5.4 6.6 6.7 6.7 0 0 1 '
       '-3 .1 6.7 6.7 0 0 0 6.3 4.7A13.5 13.5 0 0 1 10 34.6a19 19 0 0 0 29-16.8c1.3-1 '
       '2.4-2.1 4-3.3z"/>', "T")
_brand("apple.com", "#5b616e", "#24262e",
       '<path fill="#fff" d="M35.2 30.7c0-5 4.1-7.4 4.3-7.6-2.3-3.5-6-4-7.3-4'
       '-3.1-.3-6.1 1.9-7.7 1.9-1.6 0-4-1.8-6.6-1.8-3.4.1-6.5 2-8.2 5'
       '-3.5 6.1-.9 15.1 2.5 20 1.7 2.4 3.6 5.1 6.2 5 2.5-.1 3.5-1.6 6.5-1.6'
       's3.9 1.6 6.6 1.6c2.7 0 4.3-2.4 6-4.9 1.9-2.8 2.7-5.5 2.7-5.6'
       '-.1 0-5.2-2-5-8zM30.2 16.3c1.4-1.7 2.3-4 2-6.3-2 .1-4.4 1.3-5.8 3'
       '-1.3 1.5-2.4 3.9-2.1 6.2 2.2.2 4.5-1.1 5.9-2.9z"/>', "")


# ---------------------------------------------------------------------- #
# 未知站点回退：按域名哈希取和谐渐变（六色体系，无紫），字母徽标居中
# ---------------------------------------------------------------------- #
_FALLBACK_PALETTES = (
    ("#4f8ef7", "#2e6bdb"),   # 蓝
    ("#38c2a0", "#1f9a7e"),   # 青绿
    ("#f2994a", "#d17524"),   # 橙
    ("#e5636f", "#c23b4e"),   # 珊瑚红
    ("#62b96c", "#3f9150"),   # 绿
    ("#7a8699", "#556072"),   # 石墨
)


def _match_brand(host: str):
    """按可注册域后缀匹配品牌表；命中返回 (key, spec)，否则 None。"""
    if not host:
        return None
    for key, spec in _BRANDS.items():
        if host == key or host.endswith("." + key):
            return key, spec
    return None


def brand_palette(host: str):
    """返回站点图标的渐变 (top, bottom)；未知站点按哈希取回退色。

    Qt 侧（new_tab_page.py DialCard）复用此函数保持两版新标签页一致。
    """
    hit = _match_brand((host or "").lower())
    if hit:
        _, spec = hit
        return spec["top"], spec["bottom"]
    h = (host or "").lower()
    idx = sum(ord(c) for c in h) % len(_FALLBACK_PALETTES)
    return _FALLBACK_PALETTES[idx]


def brand_char(host: str, title: str) -> str:
    """图标中央字符：品牌指定字符优先，否则标题首字。"""
    hit = _match_brand((host or "").lower())
    if hit:
        _, spec = hit
        if spec["char"]:
            return spec["char"]
    t = (title or "").strip()
    return (t[0].upper() if t and t[0].isalpha() else (t[:1] or "?"))


def _squircle_body(uid: int, top: str, bottom: str) -> str:
    """squircle 底：品牌渐变 + 顶部镜面高光 + 发丝边（iOS 质感）。"""
    g = f"dg{uid}"
    return (
        f'<defs>'
        f'<linearGradient id="{g}a" x1="0" y1="0" x2="0" y2="1">'
        f'<stop offset="0" stop-color="{top}"/>'
        f'<stop offset="1" stop-color="{bottom}"/></linearGradient>'
        f'<linearGradient id="{g}s" x1="0" y1="0" x2="0" y2="1">'
        f'<stop offset="0" stop-color="rgba(255,255,255,0.30)"/>'
        f'<stop offset="1" stop-color="rgba(255,255,255,0)"/></linearGradient>'
        f'</defs>'
        f'<rect width="56" height="56" rx="14" fill="url(#{g}a)"/>'
        # 顶部镜面高光（上半圆角区）
        f'<path d="M0 14A14 14 0 0 1 14 0h28a14 14 0 0 1 14 14v12H0Z" '
        f'fill="url(#{g}s)"/>'
        # 发丝边
        f'<rect x="0.5" y="0.5" width="55" height="55" rx="13.5" '
        f'fill="none" stroke="rgba(255,255,255,0.18)"/>'
    )


def dial_icon_svg(url: str, title: str, uid: int) -> str:
    """返回拨号图标的内联 SVG 片段（56x56，CSP 安全：纯 DOM，无脚本）。

    - 已知站点：品牌渐变 + 品牌图形（模块常量模板）；
    - 未知站点：哈希渐变 + 字母徽标（首字母经 html.escape）。
    """
    try:
        host = (urlparse(url).hostname or "").lower()
    except Exception:
        host = ""
    hit = _match_brand(host)
    if hit:
        _, spec = hit
        body = _squircle_body(uid, spec["top"], spec["bottom"]) + spec["glyph"]
    else:
        top, bottom = brand_palette(host)
        ch = _html.escape(brand_char(host, title))
        # CJK 与拉丁字母分别定字号，视觉重量一致
        size = 26 if ch and ord(ch[0]) > 0x2E00 else 28
        body = (_squircle_body(uid, top, bottom)
                + _t(ch, size, 600, "#ffffff"))
    return (f'<svg width="56" height="56" viewBox="0 0 56 56" '
            f'xmlns="http://www.w3.org/2000/svg" aria-hidden="true">{body}</svg>')

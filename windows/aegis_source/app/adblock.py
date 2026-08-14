# -*- coding: utf-8 -*-
"""adblock.py —— 广告拦截。

基于 QWebEngineUrlRequestInterceptor 的请求级拦截：
- 域名黑名单（常见广告/追踪域名）
- 通用规则：拦截第三方脚本/iframe/图片中明显的广告路径
默认附带一份精简内置规则表；启用时不向广告域名发起请求。
"""

from PySide6.QtWebEngineCore import (
    QWebEngineUrlRequestInterceptor, QWebEngineUrlRequestInfo,
)

# 常见广告/追踪「主机名段」（v1.4 L3 修复：按主机名段精确匹配，
# 不再用整 URL 子串匹配，避免误伤 github.com/trackers 这类路径）
AD_HOST_FRAGMENTS = (
    "ads", "adserver", "adservice", "doubleclick", "googlesyndication",
    "googletagservices", "googletagmanager", "google-analytics",
    "adnxs", "taboola", "outbrain", "scorecardresearch",
    "amazon-adsystem", "zedo", "quantserve", "media.net", "adform",
    "criteo", "moatads", "pubmatic", "openx", "2mdn.net", "admob",
    "yieldmo", "smaato", "sharethrough",
)

# 通用广告资源路径特征（v1.4：仅对非主文档资源应用，防止整站白屏）
AD_PATH_FRAGMENTS = (
    "/ad/", "/ads/", "/banner/", "/banners/", "advert", "adclick",
    "adframe", "adfox", "popunder", "sponsored",
)


def _host_matches(host: str, frag: str) -> bool:
    """主机名段匹配：多段域名要求后缀匹配，单段要求标签完全相等。"""
    if "." in frag:
        return host == frag or host.endswith("." + frag)
    return any(label == frag for label in host.split("."))


class AdBlocker(QWebEngineUrlRequestInterceptor):
    """拦截匹配广告规则的网络请求；同时可附加 Do-Not-Track 请求头。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.enabled = True
        self.dnt_enabled = True
        self.blocked_count = 0

    def set_enabled(self, enabled: bool):
        self.enabled = enabled

    def set_dnt(self, enabled: bool):
        """设置是否附加 DNT: 1 请求头（QtWebEngine 无内置 API，
        通过请求拦截器实现；保存设置后立即生效）。"""
        self.dnt_enabled = enabled

    def _is_blocked(self, url_str: str, resource_type) -> bool:
        url = url_str.lower()
        # 白名单：自身协议与空
        if url.startswith(("data:", "blob:", "about:", "javascript:")):
            return False
        from urllib.parse import urlparse
        try:
            parsed = urlparse(url)
            host = (parsed.hostname or "").lower()
            path = (parsed.path or "").lower()
        except Exception:
            return False
        if not host:
            return False
        # 域名段匹配（仅看主机名，不看路径 —— 消除误伤）
        if any(_host_matches(host, frag) for frag in AD_HOST_FRAGMENTS):
            return True
        # 路径级规则：仅对脚本/图片/子资源的非主文档请求应用
        RT = QWebEngineUrlRequestInfo.ResourceType
        if resource_type in (RT.ResourceTypeScript,
                             RT.ResourceTypeImage,
                             RT.ResourceTypeSubResource):
            return any(frag in path for frag in AD_PATH_FRAGMENTS)
        return False

    def interceptRequest(self, info):
        if not self.enabled:
            if self.dnt_enabled:
                self._attach_dnt(info)
            return
        url = info.requestUrl().toString()
        rtype = info.resourceType()
        if self._is_blocked(url, rtype):
            self.blocked_count += 1
            info.block(True)  # 阻止该请求
            return
        if self.dnt_enabled:
            self._attach_dnt(info)

    @staticmethod
    def _attach_dnt(info):
        """附加 Do-Not-Track 头。部分 Qt 版本未暴露 setHttpHeader，做兼容处理。"""
        try:
            info.setHttpHeader(b"DNT", b"1")
        except (AttributeError, TypeError):
            pass


class AdBlockStats:
    """拦截统计（供设置界面展示）。"""

    def __init__(self, blocker: AdBlocker):
        self._blocker = blocker

    def blocked(self) -> int:
        return self._blocker.blocked_count

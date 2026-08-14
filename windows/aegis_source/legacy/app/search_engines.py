# -*- coding: utf-8 -*-
"""search_engines.py —— 搜索引擎注册表与搜索建议。

支持切换多个国内可用的搜索引擎，并提供基于 GET 接口的搜索建议
（无建议接口的引擎使用本地历史补全兜底）。
"""

import urllib.parse

ENGINES = {
    "baidu": {
        "name": "百度",
        "search_url": "https://www.baidu.com/s?wd={query}",
        "suggest_url": "https://suggestion.baidu.com/su?wd={query}&cb=window.q",
    },
    "bing": {
        "name": "必应",
        "search_url": "https://www.bing.com/search?q={query}",
        "suggest_url": "https://api.bing.com/osjson.aspx?query={query}",
    },
    "sogou": {
        "name": "搜狗",
        "search_url": "https://www.sogou.com/web?query={query}",
        "suggest_url": None,
    },
    "google": {
        "name": "谷歌（国内可能不可用）",
        "search_url": "https://www.google.com/search?q={query}",
        "suggest_url": None,
    },
    "github": {
        "name": "GitHub 搜索",
        "search_url": "https://github.com/search?q={query}",
        "suggest_url": None,
    },
    "zhihu": {
        "name": "知乎",
        "search_url": "https://www.zhihu.com/search?type=content&q={query}",
        "suggest_url": None,
    },
}

DEFAULT_ENGINE = "baidu"

# S-6：地址栏输入裸域名时默认补 https://。为了不把用户手输的 https://
# 也一起降级，这里只记录**由本模块自动升级**的地址；仅这些地址在加载
# 失败时才允许回退一次 http://（HSTS 名单主机任何情况下都不降级）。
_AUTO_HTTPS_MAX = 32
_auto_https_urls = []


def _mark_auto_https(url: str):
    if url in _auto_https_urls:
        return
    _auto_https_urls.append(url)
    if len(_auto_https_urls) > _AUTO_HTTPS_MAX:
        del _auto_https_urls[0]


def http_fallback(url: str) -> str:
    """返回 https 失败后可尝试的 http 地址；不允许降级时返回空串。"""
    if not url or not url.startswith("https://"):
        return ""
    if url not in _auto_https_urls:
        return ""      # 不是我们自动升级的地址，绝不降级
    host = urllib.parse.urlparse(url).hostname or ""
    if not host:
        return ""
    try:
        from .hsts import is_hsts
        if is_hsts(host):
            return ""
    except Exception:
        return ""
    return "http://" + url[len("https://"):]


class SearchEngines:
    """搜索引擎配置与建议获取。"""

    def __init__(self, config):
        self.config = config
        # 建议接口（异步 JSONP）。None 表示无建议接口。
        self._suggest_urls = {
            "baidu": "https://suggestion.baidu.com/su?wd={query}&cb=window.q",
            "bing": "https://api.bing.com/osjson.aspx?query={query}",
        }

    def current(self) -> str:
        """当前引擎 key。"""
        eng = self.config.engine
        return eng if eng in ENGINES else DEFAULT_ENGINE

    def engine_names(self):
        return [(k, v["name"]) for k, v in ENGINES.items()]

    def search_url(self, query: str) -> str:
        """将关键词转换为搜索引擎 URL。"""
        eng = ENGINES[self.current()]
        q = urllib.parse.quote(query)
        return eng["search_url"].format(query=q)

    def search_template(self) -> str:
        """返回未 URL 编码的搜索 URL 模板（以 `{query}` 结尾形式展开），
        供前端 JS 使用：`template + encodeURIComponent(keyword)`。"""
        eng = ENGINES[self.current()]
        return eng["search_url"].format(query="")

    def form_fields(self):
        """返回 (action, query_param)，供纯 HTML 表单提交使用。

        v1.4 H2 修复：新标签页不再内联 JS 处理器，改用原生表单，
        从而可以启用 script-src 'none' 的 CSP 彻底封死 XSS。
        """
        eng = ENGINES[self.current()]
        su = eng["search_url"]
        base, _, query = su.partition("?")
        param = "q"
        for pair in query.split("&"):
            if "{query}" in pair:
                param = pair.split("=", 1)[0]
                break
        return base, param

    def search_direct(self, query: str) -> bool:
        """判断输入是否直接是完整 URL（则不走搜索）。"""
        return "://" in query or " " not in query.strip() and "." in query

    def parse_input(self, text: str) -> str:
        """将地址栏输入规整为可加载的 URL。"""
        text = text.strip()
        if not text:
            return "about:blank"
        if "://" in text:
            return text
        # 域名或带点路径 -> 补协议（S-6：默认 https，失败时由标签页回退 http）
        if (" " not in text and "." in text) or text.startswith("localhost"):
            url = "https://" + text
            _mark_auto_https(url)
            return url
        # 其余走搜索引擎
        return self.search_url(text)

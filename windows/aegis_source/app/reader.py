"""reader.py —— 阅读模式（单文件单职责，决策/视图分离）。

借鉴 min 的 readerView.js / readerDecision.js 分离设计：
- ReaderDecision（决策层）：判断页面正文是否适合阅读模式 —— 只回答
  "可读 / 不可读"，不含任何渲染逻辑；
- ReaderView（视图层）：把正文渲染为干净的阅读 HTML —— 只负责
  输出，不参与判断。

设计原则（与项目 P0 一致）：
- **纯函数 + 标准库**：不引入第三方解析器（BeautifulSoup/lxml），
  用 html.parser 提取文本，保证零额外依赖、可离线单测；
- **防御式**：输入为空 / 结构异常一律返回"不可读"或空视图，
  绝不抛异常；
- **安全**：渲染输出使用白名单转义（html.escape），杜绝注入。
"""

import html
import re
from html.parser import HTMLParser
from typing import ClassVar

# 阅读模式判定的正文最小字符数
_MIN_TEXT_LEN = 200
# 判定的"正文密度"阈值（文本字符 / 总字符，≥ 则视为文章页）
_MIN_TEXT_RATIO = 0.20


# --------------------------------------------------------------------------- #
# 决策层：ReaderDecision —— 只判断"能否进入阅读模式"
# --------------------------------------------------------------------------- #
class ReaderDecision:
    """判断页面正文是否适合阅读模式。"""

    @staticmethod
    def is_readable(html_text: str) -> bool:
        """返回 True 表示页面正文适合阅读模式。

        依据（启发式，无第三方依赖）：
        1. 存在 <article>/<main> 语义标签，或
        2. 正文文本量 ≥ _MIN_TEXT_LEN 且文本占比 ≥ _MIN_TEXT_RATIO。
        """
        if not html_text or not isinstance(html_text, str):
            return False
        lowered = html_text.lower()
        has_article = "<article" in lowered or "<main" in lowered
        text = _extract_text(html_text)
        total = len(html_text)
        if total <= 0:
            return False
        ratio = len(text) / total
        return has_article or (len(text) >= _MIN_TEXT_LEN
                               and ratio >= _MIN_TEXT_RATIO)


# --------------------------------------------------------------------------- #
# 视图层：ReaderView —— 把正文渲染为干净的阅读 HTML
# --------------------------------------------------------------------------- #
class ReaderView:
    """生成阅读模式视图 HTML（标题 + 正文段落，内联样式）。"""

    # 内联 CSS：无外部依赖，离线可渲染；克制配色（政府项目风格）
    _CSS = (
        "body{max-width:720px;margin:0 auto;padding:24px 20px;"
        "font-family:system-ui,'Segoe UI',sans-serif;line-height:1.75;"
        "color:#1a1a1a;background:#fafafa;}"
        "h1{font-size:24px;margin-bottom:8px;}"
        ".reader-meta{color:#888;font-size:13px;margin-bottom:20px;}"
        "p{margin:12px 0;}"
        "a{color:#0071e3;}"
    )

    @staticmethod
    def render(title: str, body_text: str, source_url: str = "") -> str:
        """把标题与正文渲染为完整阅读 HTML（含 <style>）。"""
        title_esc = html.escape(title or "阅读模式")
        body_esc = html.escape(body_text or "")
        meta = ""
        if source_url:
            url_esc = html.escape(source_url)
            meta = (f'<p class="reader-meta">原文：'
                    f'<a href="{url_esc}">{url_esc}</a></p>')
        return (
            "<!DOCTYPE html><html><head><meta charset=\"utf-8\">"
            f"<title>{title_esc}</title><style>{ReaderView._CSS}</style>"
            f"</head><body><h1>{title_esc}</h1>{meta}"
            f"<div class=\"reader-body\">{body_esc}</div></body></html>"
        )


# --------------------------------------------------------------------------- #
# 内部工具（模块私有）
# --------------------------------------------------------------------------- #
class _TextExtractor(HTMLParser):
    """提取可见文本：跳过 script/style，忽略标签，折叠空白。"""

    _SKIP_TAGS: ClassVar[set[str]] = {
        "script", "style", "noscript", "template", "svg",
    }

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self._parts: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag, attrs):
        if tag in self._SKIP_TAGS:
            self._skip_depth += 1

    def handle_endtag(self, tag):
        if tag in self._SKIP_TAGS and self._skip_depth > 0:
            self._skip_depth -= 1

    def handle_data(self, data):
        if self._skip_depth == 0:
            self._parts.append(data)

    def text(self) -> str:
        raw = " ".join(self._parts)
        return re.sub(r"\s+", " ", raw).strip()


def _extract_text(html_text: str) -> str:
    """抽取页面可见文本（折叠空白）。异常时返回空串。"""
    try:
        parser = _TextExtractor()
        parser.feed(html_text)
        parser.close()
        return parser.text()
    except Exception:
        return ""

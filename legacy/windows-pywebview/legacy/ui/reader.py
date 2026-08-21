"""reader.py —— 阅读模式。

通过注入 JS 提取页面正文，再以清爽的阅读排版重新渲染，
去除广告与侧栏干扰。作用于当前标签页的副本（新标签）。

v1.4 H3 修复：标题/作者/URL 全部 html.escape；正文经白名单净化
（剥离 script、事件属性、javascript: 链接、iframe/object/form 等）；
页面启用严格 CSP（script-src 'none'），双保险封死 HTML 注入。
"""

import html as html_mod
import re

# 提取正文的 JS：优先 article，其次 main，最后取文本密度最大的 div 块
EXTRACT_JS = r"""
(function(){
  function score(el){
    var t = el.innerText||'';
    return t.length;
  }
  var cand = [];
  var article = document.querySelector('article');
  if(article) cand.push(article);
  var main = document.querySelector('main');
  if(main) cand.push(main);
  var ps = document.querySelectorAll('p');
  var bestP = null, bestLen = 0;
  ps.forEach(function(p){
    if(p.innerText.length > bestLen){ bestLen = p.innerText.length; bestP = p; }
  });
  if(bestP) cand.push(bestP.parentElement);
  var pick = null;
  cand.forEach(function(el){
    if(el && (!pick || score(el) > score(pick))) pick = el;
  });
  var title = document.title || '';
  var url = location.href;
  var author = '';
  var meta = document.querySelector('meta[name="author"]');
  if(meta) author = meta.content;
  if(!pick){ return JSON.stringify({title:title,url:url,author:author,body:''}); }
  // 清理干扰节点
  pick.querySelectorAll('script,style,iframe,nav,aside,form,button,svg').forEach(
    function(n){ n.remove(); });
  var body = pick.innerHTML;
  return JSON.stringify({title:title,url:url,author:author,body:body});
})();
"""


def sanitize_html(body: str) -> str:
    """阅读正文白名单净化：保留排版标签，剥离一切可执行内容。"""
    if not body:
        return ""
    # 1) 成对危险标签（script/style/iframe/object/embed/form/button/link/meta）
    body = re.sub(
        r"<\s*(script|style|iframe|object|embed|form|button|link|meta|svg|canvas)"
        r"[^>]*>.*?<\s*/\s*\1\s*>",
        "", body, flags=re.IGNORECASE | re.DOTALL)
    # 2) 单独出现（含自闭合）的危险标签
    body = re.sub(
        r"<\s*(script|style|iframe|object|embed|form|button|link|meta|svg|canvas)"
        r"[^>]*/?\s*>", "", body, flags=re.IGNORECASE)
    # 3) 事件属性 on*=
    body = re.sub(r"\son\w+\s*=\s*\"[^\"]*\"", "", body, flags=re.IGNORECASE)
    body = re.sub(r"\son\w+\s*=\s*'[^']*'", "", body, flags=re.IGNORECASE)
    body = re.sub(r"\son\w+\s*=\s*[^\s>]+", "", body, flags=re.IGNORECASE)
    # 4) javascript:/vbscript:/data: 伪协议链接 Neutralization
    body = re.sub(
        r"(href|src|action)\s*=\s*([\"'])\s*(?:javascript|vbscript|data)\s*:[^\"']*\2",
        r'\1=\2#\2', body, flags=re.IGNORECASE)
    return body


def build_reader_html(data: dict, accent="#0071e3") -> str:
    """把提取到的 {title,url,author,body} 渲染成阅读排版。"""
    title = html_mod.escape(data.get("title") or "阅读模式")
    url = html_mod.escape(data.get("url") or "")
    author = html_mod.escape(data.get("author") or "")
    body = sanitize_html(data.get("body") or "")
    if not body:
        body = "<p>未能提取到正文内容。</p>"
    return f"""<!DOCTYPE html><html><head><meta charset="utf-8">
<meta http-equiv="Content-Security-Policy"
      content="default-src 'none'; script-src 'none'; style-src 'unsafe-inline'; img-src https: data:; media-src https:; font-src data:; form-action 'none';">
<style>
/* Apple 阅读模式：浅灰底 + SF Pro 标题 + 舒适正文行距（DESIGN.md） */
body{{margin:0;background:#f5f5f7;color:#1d1d1f;line-height:1.47;
  font-family:'SF Pro Text','Helvetica Neue','Segoe UI','Microsoft YaHei',
  sans-serif;font-size:17px;letter-spacing:-0.374px;
  -webkit-font-smoothing:antialiased;}}
.wrap{{max-width:760px;margin:0 auto;padding:56px 32px 96px;}}
h1{{font-family:'SF Pro Display','SF Pro Text','Helvetica Neue','Segoe UI',
  'Microsoft YaHei',sans-serif;
  font-size:40px;line-height:1.1;font-weight:600;letter-spacing:0;
  margin:0 0 12px;}}
.meta{{color:rgba(0,0,0,0.48);font-size:14px;letter-spacing:-0.224px;
  margin-bottom:30px;padding-bottom:20px;border-bottom:1px solid rgba(0,0,0,0.08);}}
.article{{font-size:19px;line-height:1.7;color:#1d1d1f;}}
.article p{{margin:0 0 22px;}}
.article img{{max-width:100%;border-radius:12px;}}
.article a{{color:#0066cc;text-decoration:none;}}
.article a:hover{{text-decoration:underline;}}
blockquote{{border-left:3px solid #d2d2d7;margin:0 0 22px;padding:6px 0 6px 20px;
  color:rgba(0,0,0,0.62);}}
h2,h3,h4{{font-family:'SF Pro Display','Helvetica Neue','Segoe UI',sans-serif;
  font-weight:600;letter-spacing:0;line-height:1.2;margin:32px 0 12px;}}
</style></head><body><div class="wrap">
<h1>{title}</h1>
<div class="meta">{author}{' · ' if author else ''}<a href="{url}" style="color:#0066cc">{url}</a></div>
<div class="article">{body}</div>
</div></body></html>"""


def extract_reader_js() -> str:
    """返回用于页面执行的提取脚本。"""
    return EXTRACT_JS

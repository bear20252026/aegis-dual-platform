# -*- coding: utf-8 -*-
"""error_pages.py —— Apple 风格友好错误页与安全提示页（依据 DESIGN.md）。

页面加载失败（离线/DNS/拒绝连接等）时展示极简错误页，
提供"重试 / 返回主页"操作。设计原则：
- 实色背景（深 #000000 / 浅 #f5f5f7），不使用渐变
- SF Pro 字体栈 + 全尺寸负字距
- 唯一强调色 Apple Blue #0071e3 用于主按钮
- 次级操作为 980px 药丸链接样式
"""

import html as html_mod
from urllib.parse import urlparse

APPLE_BLUE = "#0071e3"

# 常见失败场景的文案
_ERROR_HINTS = {
    "dns": "找不到服务器地址，请检查网络或网址是否拼写正确。",
    "refused": "网站拒绝了连接请求，可能服务器繁忙或已停止服务。",
    "offline": "设备已离线，请检查网络连接后重试。",
    "timeout": "连接超时，网站响应时间过长。",
    "ssl": "该网站的证书不受信任，连接存在安全风险。",
}

_FONT = ("'SF Pro Display','SF Pro Text','Helvetica Neue',"
         "'Segoe UI','Microsoft YaHei',sans-serif")


def _palette(dark: bool) -> dict:
    """深/浅两套 Apple token（摘自 DESIGN.md）。"""
    if dark:
        return dict(bg="#000000", fg="#ffffff", sub="rgba(255,255,255,0.6)",
                    host="rgba(255,255,255,0.42)", ico="rgba(255,255,255,0.08)",
                    pill_border="rgba(255,255,255,0.4)", pill_fg="#ffffff")
    return dict(bg="#f5f5f7", fg="#1d1d1f", sub="rgba(0,0,0,0.8)",
                host="rgba(0,0,0,0.48)", ico="rgba(0,0,0,0.05)",
                pill_border="#1d1d1f", pill_fg="#1d1d1f")


def build_error_html(failed_url: str, reason: str = "generic",
                     accent=APPLE_BLUE, dark: bool = True) -> str:
    """生成友好的错误页 HTML（Apple 极简风）。"""
    host = urlparse(failed_url).netloc or failed_url
    hint = _ERROR_HINTS.get(reason, "无法加载此页面，请检查网络后重试。")
    safe_host = html_mod.escape(host)
    c = _palette(dark)
    return f"""<!DOCTYPE html><html><head><meta charset="utf-8">
<style>
body{{margin:0;height:100vh;font-family:{_FONT};
  display:flex;align-items:center;justify-content:center;
  background:{c['bg']};color:{c['fg']};-webkit-font-smoothing:antialiased;}}
.card{{max-width:520px;padding:48px;text-align:center;}}
.ico{{width:88px;height:88px;margin:0 auto 26px;border-radius:50%;
  background:{c['ico']};display:flex;align-items:center;justify-content:center;}}
.ico svg{{width:40px;height:40px;opacity:.85;}}
h1{{font-size:28px;font-weight:600;line-height:1.14;letter-spacing:0.196px;
  margin:0 0 12px;}}
p{{color:{c['sub']};font-size:17px;line-height:1.47;letter-spacing:-0.374px;
  margin:0 0 8px;}}
.host{{color:{c['host']};word-break:break-all;font-size:14px;
  letter-spacing:-0.224px;}}
.btns{{margin-top:28px;display:flex;gap:14px;justify-content:center;}}
.btn{{display:inline-block;padding:10px 22px;border-radius:8px;border:none;
  cursor:pointer;font-size:17px;letter-spacing:-0.374px;text-decoration:none;
  background:{accent};color:#fff;font-family:inherit;
  transition:filter .2s cubic-bezier(.32,.72,0,1);}}
.btn:hover{{filter:brightness(1.12);}}
.btn.ghost{{background:transparent;color:{c['pill_fg']};border-radius:980px;
  border:1px solid {c['pill_border']};}}
.btn.ghost:hover{{filter:none;text-decoration:underline;}}
</style></head><body><div class="card">
<div class="ico">
  <svg viewBox="0 0 24 24" fill="none" stroke="{c['fg']}" stroke-width="1.6"
       stroke-linecap="round" stroke-linejoin="round">
    <path d="M12 9v4M12 16.5v.5M10.3 3.6 2.7 17a2 2 0 0 0 1.7 3h15.2a2 2 0 0 0 1.7-3L13.7 3.6a2 2 0 0 0-3.4 0Z"/>
  </svg>
</div>
<h1>无法访问此页面</h1>
<p>{hint}</p>
<p class="host">{safe_host}</p>
<div class="btns">
  <a class="btn" href="#" onclick="window.retry();return false;">重试</a>
  <a class="btn ghost" href="#" onclick="window.gohome();return false;">返回主页</a>
</div>
</div>
<script>
window.retry=function(){{ location.reload(); }};
window.gohome=function(){{ location.href='about:blank'; }};
</script></body></html>"""


def build_ssl_warning_html(failed_url: str, accent=APPLE_BLUE,
                           dark: bool = True) -> str:
    """SSL 证书风险提示页（用户可选择仍要继续或返回）。"""
    safe_host = html_mod.escape(urlparse(failed_url).netloc or failed_url)
    c = _palette(dark)
    return f"""<!DOCTYPE html><html><head><meta charset="utf-8">
<style>
body{{margin:0;height:100vh;font-family:{_FONT};
  display:flex;align-items:center;justify-content:center;
  background:{c['bg']};color:{c['fg']};-webkit-font-smoothing:antialiased;}}
.card{{max-width:560px;padding:48px;text-align:center;}}
.ico{{width:88px;height:88px;margin:0 auto 26px;border-radius:50%;
  background:{c['ico']};display:flex;align-items:center;justify-content:center;}}
.ico svg{{width:40px;height:40px;opacity:.85;}}
h1{{font-size:28px;font-weight:600;line-height:1.14;letter-spacing:0.196px;
  margin:0 0 12px;}}
p{{color:{c['sub']};font-size:17px;line-height:1.47;letter-spacing:-0.374px;}}
.host{{color:{c['fg']};font-weight:600;word-break:break-all;}}
.note{{font-size:14px;color:{c['host']};letter-spacing:-0.224px;}}
.btns{{margin-top:28px;display:flex;gap:14px;justify-content:center;}}
.btn{{display:inline-block;padding:10px 22px;border-radius:980px;cursor:pointer;
  font-size:17px;letter-spacing:-0.374px;text-decoration:none;font-family:inherit;
  background:transparent;color:{c['pill_fg']};border:1px solid {c['pill_border']};}}
.btn:hover{{text-decoration:underline;}}
.btn.warn{{background:#b25000;border-color:transparent;color:#fff;border-radius:8px;}}
.btn.warn:hover{{filter:brightness(1.12);text-decoration:none;}}
</style></head><body><div class="card">
<div class="ico">
  <svg viewBox="0 0 24 24" fill="none" stroke="{c['fg']}" stroke-width="1.6"
       stroke-linecap="round" stroke-linejoin="round">
    <rect x="5" y="10.5" width="14" height="9.5" rx="2"/>
    <path d="M8 10.5V8a4 4 0 0 1 8 0v2.5"/>
  </svg>
</div>
<h1>该网站的安全证书不受信任</h1>
<p>连接 <span class="host">{safe_host}</span> 时发现证书问题。
攻击者可能正在尝试窃取你的信息。</p>
<p class="note">继续访问将承担安全风险。</p>
<div class="btns">
  <a class="btn warn" href="#" onclick="window.continue_();return false;">仍然继续</a>
  <a class="btn" href="#" onclick="window.back_();return false;">返回安全</a>
</div>
</div>
<script>
window.continue_=function(){{ document.title='__ALLOW_SSL__'; }};
window.back_=function(){{ history.back(); }};
</script></body></html>"""


# 分类错误（根据 URL 特征或状态粗略判断，供文案使用）
def classify_reason(failed_url: str) -> str:
    return "generic"

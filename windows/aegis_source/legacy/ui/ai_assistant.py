# -*- coding: utf-8 -*-
"""ai_assistant.py —— 本地 AI 助手面板（对标/超标商业浏览器的 AI 能力）。

能力：
- 文本翻译（单条）
- 页面内双语对照（对标「沉浸式翻译」类插件，纯注入实现）
- 总结当前网页
- 针对当前网页提问（QA）
- 一键唤起本地 千问 / Kimi 桌面 App（免费、本地对话）

全部走本地 AI（Ollama / LM Studio 等 OpenAI 兼容端点），免费、无需 Key。
也兼容云端 OpenAI 兼容端点（如 Kimi/Moonshot）。

设计约束（项目 P0 绝对规则）：
- 不使用 emoji 图标；不硬编码颜色（沿用系统主题与项目强调色 #0071e3）。
"""

import os
import json
import subprocess

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLineEdit, QPushButton,
    QPlainTextEdit, QLabel, QComboBox, QTabWidget, QInputDialog,
    QApplication, QWidget,
)

import app.ai_client as ai_client

# 供应商预设（仅作默认值，用户可改；端点均为 OpenAI 兼容 /v1/chat/completions）
PROVIDER_PRESETS = {
    "ollama": ("http://localhost:11434/v1/chat/completions", "", "中文"),
    "qwen":   ("http://localhost:11434/v1/chat/completions", "qwen2.5:7b", "中文"),
    "kimi":   ("https://api.moonshot.cn/v1/chat/completions", "moonshot-v1-8k", "中文"),
    "deepseek": ("https://api.deepseek.com/v1/chat/completions", "deepseek-chat", "中文"),
    "custom": (None, None, None),
}


# --------------------------------------------------------------------- #
# 页面内双语对照的 JS
# --------------------------------------------------------------------- #
_COLLECT_JS = r"""(function(){
  var TAGS=['P','H1','H2','H3','H4','H5','H6','LI','BLOCKQUOTE','TD','TH',
           'FIGCAPTION','BUTTON','A','LABEL','OPTION','SUMMARY','CAPTION'];
  function hasTagParent(el){while(el){if(TAGS.indexOf(el.tagName)>=0)return true;el=el.parentElement;}return false;}
  var sel='p,h1,h2,h3,h4,h5,h6,li,blockquote,td,th,figcaption,button,a,label,option,summary,caption';
  var all=document.querySelectorAll(sel);
  var out=[];var k=0;
  for(var i=0;i<all.length;i++){
    var el=all[i];
    if(hasTagParent(el.parentElement))continue;
    if(el.getAttribute('data-aegis-id'))continue;
    var txt=(el.innerText||'').replace(/\s+/g,' ').trim();
    if(txt.length<2)continue;
    if(/^[\s\d\W]+$/.test(txt))continue;
    el.setAttribute('data-aegis-id','a'+k);
    out.push({id:'a'+k,text:txt});
    k++; if(k>=180)break;
  }
  return JSON.stringify(out);
})();"""

_INJECT_JS_PREFIX = r"""(function(items){
  if(!document.getElementById('aegis-bi-style')){
    var s=document.createElement('style');s.id='aegis-bi-style';
    s.textContent='.aegis-bi{margin:.2em 0 .5em;padding:.4em .7em;border-left:3px solid #0071e3;background:rgba(127,127,127,.12);color:inherit;font-size:90%;line-height:1.55;border-radius:8px;opacity:.96;}';
    (document.head||document.documentElement).appendChild(s);
  }
  for(var i=0;i<items.length;i++){
    var it=items[i];
    var el=document.querySelector('[data-aegis-id="'+it.id+'"]');
    if(!el)continue;
    if(el.nextElementSibling && el.nextElementSibling.classList && el.nextElementSibling.classList.contains('aegis-bi'))continue;
    var d=document.createElement('div');d.className='aegis-bi';d.textContent=it.trans;
    el.after(d);
  }
})("""
_INJECT_JS_SUFFIX = r""")"""

_STOP_JS = r"""(function(){
  var els=document.querySelectorAll('.aegis-bi');
  for(var i=0;i<els.length;i++){els[i].parentNode.removeChild(els[i]);}
  var m=document.querySelectorAll('[data-aegis-id]');
  for(var i=0;i<m.length;i++){m[i].removeAttribute('data-aegis-id');}
})();"""


# --------------------------------------------------------------------- #
# 后台工作线程
# --------------------------------------------------------------------- #
class _AIWorker(QThread):
    """通用后台调用：在子线程执行 fn(*args)，结果通过信号回传。

    done 用 object 类型以兼容「翻译/总结/问答返回 str」与
    「双语对照返回 list」两种情况。
    """

    done = Signal(object)
    failed = Signal(str)

    def __init__(self, fn, args, kwargs=None):
        super().__init__()
        self._fn = fn
        self._args = args
        self._kwargs = kwargs or {}

    def run(self):
        try:
            out = self._fn(*self._args, **self._kwargs)
            self.done.emit(out or "")
        except Exception as e:  # noqa: BLE001
            self.failed.emit(str(e))


class AegisAIPanel(QDialog):
    """本地 AI 助手面板（非模态对话框）。"""

    def __init__(self, win, parent=None):
        super().__init__(parent)
        self._win = win
        self._bi_active = False
        self._bi_blocks = []
        self._worker = None
        self.setWindowTitle("AI 助手（本地）")
        self.resize(560, 560)

        # ---------- 配置区 ----------
        cfg = QVBoxLayout()
        row1 = QHBoxLayout()
        self._provider = QComboBox(self)
        self._provider.addItems(["ollama", "qwen", "kimi", "deepseek", "custom"])
        self._provider.setToolTip("供应商预设（端点可改）")
        self._endpoint = QLineEdit(self)
        self._endpoint.setPlaceholderText(
            "端点，如 http://localhost:11434/v1/chat/completions")
        self._model = QLineEdit(self)
        self._model.setPlaceholderText("模型名（Ollama 必填，如 qwen2.5:7b）")
        self._target = QComboBox(self)
        self._target.addItems(["中文", "English", "日本語", "한국어"])
        row1.addWidget(QLabel("供应商"))
        row1.addWidget(self._provider, 1)
        row1.addWidget(QLabel("端点"))
        row1.addWidget(self._endpoint, 3)
        row1.addWidget(QLabel("模型"))
        row1.addWidget(self._model, 2)
        row1.addWidget(QLabel("目标"))
        row1.addWidget(self._target)
        cfg.addLayout(row1)

        # 云端供应商的 API Key（本地 Ollama 无需）
        row1b = QHBoxLayout()
        self._key = QLineEdit(self)
        self._key.setEchoMode(QLineEdit.Password)
        self._key.setPlaceholderText(
            "云端服务填 API Key（DeepSeek/Kimi），本地 Ollama 留空")
        row1b.addWidget(QLabel("密钥"))
        row1b.addWidget(self._key, 1)
        cfg.addLayout(row1b)

        self._provider.currentTextChanged.connect(self._on_provider)

        # ---------- 功能 Tab ----------
        tabs = QTabWidget(self)

        # 1) 翻译
        w_trans = QWidget(self)
        lt = QVBoxLayout(w_trans)
        self._t_input = QPlainTextEdit(self)
        self._t_input.setPlaceholderText(
            "在此输入，或点下方按钮取「选中文本 / 整页文本」…")
        self._t_input.setMaximumHeight(150)
        lt.addWidget(self._t_input)
        r1 = QHBoxLayout()
        self._t_sel = QPushButton("取选中文本")
        self._t_page = QPushButton("取整页文本")
        self._t_go = QPushButton("翻译")
        self._t_go.setDefault(True)
        r1.addWidget(self._t_sel)
        r1.addWidget(self._t_page)
        r1.addStretch(1)
        r1.addWidget(self._t_go)
        lt.addLayout(r1)
        self._t_out = QPlainTextEdit(self)
        self._t_out.setReadOnly(True)
        lt.addWidget(self._t_out, 1)
        self._t_sel.clicked.connect(self._t_grab_sel)
        self._t_page.clicked.connect(self._t_grab_page)
        self._t_go.clicked.connect(self._t_translate)
        tabs.addTab(w_trans, "翻译")

        # 2) 双语对照
        w_bi = QWidget(self)
        lb = QVBoxLayout(w_bi)
        info = QLabel(
            "在当前已打开的页面上直接显示译文（对标沉浸式翻译的对照模式）。\n"
            "译文通过本地 AI 生成，逐段注入到原文下方；再次点击可清除。", self)
        info.setWordWrap(True)
        lb.addWidget(info)
        self._bi_btn = QPushButton("在此页开启双语对照")
        self._bi_btn.clicked.connect(self._run_bilingual)
        lb.addWidget(self._bi_btn)
        self._bi_status = QLabel("", self)
        self._bi_status.setWordWrap(True)
        lb.addWidget(self._bi_status)
        lb.addStretch(1)
        tabs.addTab(w_bi, "双语对照")

        # 3) 总结本页
        w_sum = QWidget(self)
        ls = QVBoxLayout(w_sum)
        self._sum_btn = QPushButton("总结当前网页")
        self._sum_btn.clicked.connect(self._summarize)
        ls.addWidget(self._sum_btn)
        self._sum_out = QPlainTextEdit(self)
        self._sum_out.setReadOnly(True)
        self._sum_out.setPlaceholderText("摘要将显示在这里…")
        ls.addWidget(self._sum_out, 1)
        tabs.addTab(w_sum, "总结本页")

        # 4) 提问本页
        w_qa = QWidget(self)
        lq = QVBoxLayout(w_qa)
        self._qa_input = QLineEdit(self)
        self._qa_input.setPlaceholderText("针对当前网页提问，如：这篇文章讲了什么？")
        lq.addWidget(self._qa_input)
        self._qa_btn = QPushButton("提问")
        self._qa_btn.clicked.connect(self._ask)
        lq.addWidget(self._qa_btn)
        self._qa_out = QPlainTextEdit(self)
        self._qa_out.setReadOnly(True)
        self._qa_out.setPlaceholderText("回答将显示在这里…")
        lq.addWidget(self._qa_out, 1)
        tabs.addTab(w_qa, "提问")

        cfg.addWidget(tabs)

        # ---------- 本地 AI App 唤起 ----------
        foot = QHBoxLayout()
        self._btn_qwen = QPushButton("打开千问")
        self._btn_kimi = QPushButton("打开 Kimi")
        self._btn_path = QPushButton("设置应用路径")
        self._btn_qwen.clicked.connect(lambda: self._launch_app("qwen"))
        self._btn_kimi.clicked.connect(lambda: self._launch_app("kimi"))
        self._btn_path.clicked.connect(self._set_app_paths)
        foot.addWidget(self._btn_qwen)
        foot.addWidget(self._btn_kimi)
        foot.addStretch(1)
        foot.addWidget(self._btn_path)
        cfg.addLayout(foot)
        self._app_status = QLabel("", self)
        self._app_status.setWordWrap(True)
        cfg.addWidget(self._app_status)

        self.setLayout(cfg)
        self._load_cfg()

    # ------------------------------------------------------------------ #
    # 配置
    # ------------------------------------------------------------------ #
    def _load_cfg(self):
        c = self._win.config
        provider = getattr(c, "ai_provider", "ollama") or "ollama"
        # 若用户尚未显式选择、但已配好 DeepSeek 密钥，则默认切到 DeepSeek
        if provider == "ollama" and ai_client.load_api_key("deepseek"):
            provider = "deepseek"
        idx = self._provider.findText(provider)
        if idx >= 0:
            self._provider.setCurrentIndex(idx)
        self._endpoint.setText(
            getattr(c, "translate_endpoint", "")
            or "http://localhost:11434/v1/chat/completions")
        self._model.setText(getattr(c, "translate_model", "") or "")
        t = getattr(c, "translate_target", "中文") or "中文"
        idx = self._target.findText(t)
        if idx >= 0:
            self._target.setCurrentIndex(idx)
        self._key.setText(ai_client.load_api_key(provider))

    def _save_cfg(self):
        c = self._win.config
        c.ai_provider = self._provider.currentText()
        c.translate_endpoint = self._endpoint.text().strip()
        c.translate_model = self._model.text().strip()
        c.translate_target = self._target.currentText()
        ai_client.save_api_key(self._provider.currentText(),
                               self._key.text().strip())
        self._win.ctx.save_config()

    def _on_provider(self, name):
        preset = PROVIDER_PRESETS.get(name)
        if not preset:
            return
        ep, model, target = preset
        if ep:
            self._endpoint.setText(ep)
        if model is not None:
            self._model.setText(model)
        if target:
            idx = self._target.findText(target)
            if idx >= 0:
                self._target.setCurrentIndex(idx)
        self._key.setText(ai_client.load_api_key(name))

    # ------------------------------------------------------------------ #
    # 翻译
    # ------------------------------------------------------------------ #
    def _t_grab_sel(self):
        t = self._win.current_tab()
        if not t:
            return
        t.run_js("window.getSelection().toString()",
                 lambda s: self._t_input.setPlainText(s or ""))

    def _t_grab_page(self):
        t = self._win.current_tab()
        if not t:
            return
        t.run_js("document.body ? document.body.innerText : ''",
                 lambda s: self._t_input.setPlainText(s or ""))

    def _t_translate(self):
        text = self._t_input.toPlainText().strip()
        if not text:
            return
        self._save_cfg()
        self._t_out.setPlainText("翻译中…")
        self._run_ai(ai_client.translate,
                     (text, self._endpoint.text().strip(),
                      self._model.text().strip(), self._target.currentText()),
                     self._t_out,
                     kwargs={"api_key": self._key.text().strip()})

    # ------------------------------------------------------------------ #
    # 双语对照
    # ------------------------------------------------------------------ #
    def _run_bilingual(self):
        t = self._win.current_tab()
        if not t:
            return
        if self._bi_active:
            t.run_js(_STOP_JS)
            self._bi_active = False
            self._bi_btn.setText("在此页开启双语对照")
            self._bi_status.setText("已关闭双语对照。")
            return
        self._save_cfg()
        self._bi_status.setText("正在提取页面文本…")
        self._bi_btn.setEnabled(False)
        t.run_js(_COLLECT_JS, self._on_collected)

    def _on_collected(self, raw):
        try:
            blocks = json.loads(raw) if raw else []
        except Exception:
            blocks = []
        self._bi_btn.setEnabled(True)
        if not blocks:
            self._bi_status.setText(
                "本页无可翻译文本，或页面尚未加载完成。请先打开网页。")
            return
        self._bi_blocks = blocks
        self._bi_status.setText(f"已提取 {len(blocks)} 段，正在翻译…")
        texts = [b["text"] for b in blocks]
        self._run_ai(ai_client.translate_many,
                     (texts, self._endpoint.text().strip(),
                      self._model.text().strip(), self._target.currentText()),
                     None, on_done=self._on_bi_done,
                     kwargs={"api_key": self._key.text().strip()})

    def _on_bi_done(self, translations):
        t = self._win.current_tab()
        if not t:
            self._bi_btn.setEnabled(True)
            return
        items = [{"id": b["id"], "trans": tr}
                 for b, tr in zip(self._bi_blocks, translations)]
        js = _INJECT_JS_PREFIX + json.dumps(items, ensure_ascii=False) \
            + _INJECT_JS_SUFFIX
        t.run_js(js)
        self._bi_active = True
        self._bi_btn.setText("关闭双语对照")
        self._bi_status.setText(
            f"双语对照已开启：{len(items)} 段。再次点击可关闭。")
        self._bi_btn.setEnabled(True)

    # ------------------------------------------------------------------ #
    # 总结 / 提问
    # ------------------------------------------------------------------ #
    def _summarize(self):
        t = self._win.current_tab()
        if not t:
            return
        self._save_cfg()
        self._sum_out.setPlainText("正在提取页面并总结…")
        t.run_js("document.body ? document.body.innerText : ''",
                 self._on_page_for_summary)

    def _on_page_for_summary(self, text):
        self._run_ai(ai_client.summarize,
                     (text, self._endpoint.text().strip(),
                      self._model.text().strip(), "中文"),
                     self._sum_out,
                     kwargs={"api_key": self._key.text().strip()})

    def _ask(self):
        q = self._qa_input.text().strip()
        if not q:
            return
        t = self._win.current_tab()
        if not t:
            return
        self._save_cfg()
        self._qa_out.setPlainText("正在阅读页面并回答…")
        self._qa_ctx = q

        def _on_ctx(ctx):
            self._run_ai(ai_client.ask,
                         (self._qa_ctx, ctx, self._endpoint.text().strip(),
                          self._model.text().strip()),
                         self._qa_out,
                         kwargs={"api_key": self._key.text().strip()})
        t.run_js("document.body ? document.body.innerText : ''", _on_ctx)

    # ------------------------------------------------------------------ #
    # 本地 AI App 唤起
    # ------------------------------------------------------------------ #
    def _launch_app(self, name):
        attr = "qwen_app_path" if name == "qwen" else "kimi_app_path"
        path = getattr(self._win.config, attr, "")
        if not path or not os.path.exists(path):
            path = self._autodetect(name)
        if path and os.path.exists(path):
            try:
                if os.name == "nt":
                    os.startfile(path)
                else:
                    subprocess.Popen([path])
                self._app_status.setText(f"已唤起 {name} 应用，可在其中免费对话。")
                return
            except Exception as e:  # noqa: BLE001
                self._app_status.setText(f"唤起失败：{e}")
                return
        self._app_status.setText(
            f"未找到 {name} 应用，请点「设置应用路径」指定其 exe 位置。")

    def _autodetect(self, name):
        """在常见安装目录中查找已知 exe 名。"""
        import glob
        names = (["Qwen.exe", "通义千问.exe", "qwen.exe"] if name == "qwen"
                 else ["Kimi.exe", "kimi.exe"])
        roots = []
        for base in ("C:/Program Files", "C:/Program Files (x86)",
                     os.path.expanduser("~/AppData/Local"),
                     os.path.expanduser("~/AppData/Roaming"),
                     os.path.expanduser("~/Desktop")):
            if os.path.isdir(base):
                roots.append(base)
        for root in roots:
            for nm in names:
                hits = glob.glob(os.path.join(root, "**", nm), recursive=True)
                if hits:
                    return hits[0]
        return ""

    def _set_app_paths(self):
        c = self._win.config
        for name, attr in (("千问", "qwen_app_path"), ("Kimi", "kimi_app_path")):
            cur = getattr(c, attr, "")
            path, _ = QInputDialog.getText(
                self, f"设置{name}应用路径",
                f"{name} 桌面 App 的 exe 完整路径：", text=cur)
            if path.strip():
                setattr(c, attr, path.strip())
        self._win.ctx.save_config()
        self._app_status.setText("应用路径已保存。")

    # ------------------------------------------------------------------ #
    # 通用后台调用
    # ------------------------------------------------------------------ #
    def _run_ai(self, fn, args, out_widget, on_done=None, kwargs=None):
        # v2.1.2 修复：API Key 必须以关键字参数 api_key 传入。此前误放进
        # 第 5 个位置参数（即 timeout），导致 TypeError / 云端鉴权头缺失，
        # 翻译/双语/总结/问答四类功能实际全部失效。
        self._worker = _AIWorker(fn, args, kwargs)
        if out_widget is not None:
            out_widget.setPlainText("处理中…")

        def _done(out):
            if out_widget is not None:
                out_widget.setPlainText(out or "（无返回：本地 AI 未响应，"
                                         "请确认服务已启动、端点与模型正确。）")
            if on_done is not None:
                on_done([] if out is None else _safe_list(out))

        def _failed(msg):
            if out_widget is not None:
                out_widget.setPlainText(f"出错：{msg}")
            if on_done is not None:
                on_done([])

        self._worker.done.connect(_done)
        self._worker.failed.connect(_failed)
        self._worker.start()


def _safe_list(out):
    """translate_many 返回 list；其他函数返回 str。统一转 list 供注入。"""
    if isinstance(out, list):
        return out
    return []

"""computer_use.py —— 模式 B：计算机使用闭环（设计文档 §7）。

截图 → 视觉模型决策（JSON 动作）→ 页面内执行（runJavaScript）→ 再截图……
本模块提供：
- 可离线单测的纯逻辑：GATE 等级门控（check_level）、JS 模板生成（build_js）、
  截图感知哈希（screen_fingerprint）
- 依赖 Qt 的执行器：PageActor（坐标按 DPR 换算、runJavaScript 执行）

安全边界（§8）：
- 动作白名单 × 权限等级（L0~L3）交叉校验，越级动作一律拒绝；
- 密码框输入由 JS 模板检测并拒绝（password-field）；密码库直填（login_fill）
  仅 L3 且由面板层从 PasswordStore 解密注入，**明文不进模型上下文**；
- 动作代码全部来自固定模板，text/坐标经 JSON 注入，不接受任意 JS 输入。

注意：JS 模板使用 .replace() 占位符替换（非 str.format），
模板保持纯 JS 写法，无需转义花括号。
"""

import base64
import json

from .vision_client import ACTION_WHITELIST

# 等级 → 允许动作（§13.2）；L0 只读观察（无任何动作）。
# 浏览器原生动作（§7.7）：set_engine/add_bookmark/new_tab/open_history 属 L1；
# open_settings 涉及配置修改，归 L2；qrcode/sms_input（§14）为人工介入请求。
LEVEL_ACTIONS = {
    0: frozenset(),
    1: frozenset({"click", "scroll", "back", "wait", "done", "fail",
                  "set_engine", "add_bookmark", "new_tab", "open_history",
                  "qrcode", "sms_input"}),
    2: frozenset({"click", "type", "scroll", "back", "wait", "done", "fail",
                  "set_engine", "add_bookmark", "new_tab", "open_history",
                  "open_settings", "qrcode", "sms_input"}),
    3: frozenset({"click", "type", "scroll", "back", "wait", "done", "fail",
                  "set_engine", "add_bookmark", "new_tab", "open_history",
                  "open_settings", "qrcode", "sms_input"}),
}

# 凭据类动作：仅 L3（密码库直填，由面板层构造，模型不可输出该动作）
CREDENTIAL_ACTIONS = frozenset({"login_fill"})


class GateError(Exception):
    """动作被权限等级拦截。"""


def check_level(action: dict, level: int) -> None:
    """GATE：动作是否在等级允许集合内。不通过抛 GateError。

    level 为 0~3；非法值按 L1 处理（默认保守）。
    """
    name = action.get("action")
    if name in CREDENTIAL_ACTIONS:
        if int(level) < 3:
            raise GateError("密码库访问需 L3 权限，已拦截")
        return
    if name not in ACTION_WHITELIST:
        raise GateError(f"动作 {name!r} 不在白名单内")
    try:
        level = int(level)
    except (TypeError, ValueError):
        level = 1
    if level < 0 or level > 3:
        level = 1
    allowed = LEVEL_ACTIONS.get(level, LEVEL_ACTIONS[1])
    if name not in allowed:
        raise GateError(f"当前等级 L{level}，不允许动作 {name!r}")


# --------------------------------------------------------------------------- #
# JS 模板（§7.3 / §7.4 / §14.3）——纯 JS 写法，占位符用 .replace() 注入
# --------------------------------------------------------------------------- #
CLICK_JS = (
    "(function(){var el=document.elementFromPoint({x},{y});"
    "if(!el)return {ok:false,why:'no-element'};"
    "el.click();return {ok:true};})()"
)

TYPE_JS = (
    "(function(){var el=document.elementFromPoint({x},{y});"
    "if(!el)return {ok:false,why:'no-element'};"
    "if(el.tagName!=='INPUT'&&el.tagName!=='TEXTAREA'&&!el.isContentEditable){"
    "var inner=el.querySelector('input,textarea,[contenteditable]');"
    "if(inner)el=inner;else return {ok:false,why:'not-input'};}"
    "if(el.type==='password')return {ok:false,why:'password-field'};"
    "el.focus();"
    "var proto=el.tagName==='TEXTAREA'"
    "?HTMLTextAreaElement.prototype:HTMLInputElement.prototype;"
    "var setter=Object.getOwnPropertyDescriptor(proto,'value').set;"
    "setter.call(el,{text});"
    "el.dispatchEvent(new Event('input',{bubbles:true}));"
    "el.dispatchEvent(new Event('change',{bubbles:true}));"
    "if({submit}){"
    "var form=el.closest('form');"
    "if(form)form.requestSubmit();"
    "else el.dispatchEvent(new KeyboardEvent('keydown',"
    "{key:'Enter',bubbles:true}));}"
    "return {ok:true};})()"
)

SCROLL_JS = "window.scrollBy({dx},{dy}); 'ok';"

# 短信验证码填入（§14.3）：验证码由用户输入，面板构造 sms_fill 动作
SMS_FILL_JS = (
    "(function(){var el=document.querySelector('input[type=tel],"
    "input[name*=code i],input[autocomplete=one-time-code]');"
    "if(!el)return {ok:false,why:'no-sms-field'};"
    "el.focus();"
    "var setter=Object.getOwnPropertyDescriptor("
    "HTMLInputElement.prototype,'value').set;"
    "setter.call(el,{code});"
    "el.dispatchEvent(new Event('input',{bubbles:true}));"
    "el.dispatchEvent(new Event('change',{bubbles:true}));"
    "var form=el.closest('form');"
    "if(form)form.requestSubmit();"
    "return {ok:true};})()"
)

# 密码库直填（§13.4）：AI 不见明文，由面板从 PasswordStore 取密后注入
FILL_JS = (
    "(function(){var pwd=document.querySelector('input[type=password]');"
    "if(!pwd)return {ok:false,why:'no-password-field'};"
    "pwd.focus();"
    "var setter=Object.getOwnPropertyDescriptor("
    "HTMLInputElement.prototype,'value').set;"
    "setter.call(pwd,{pwd});"
    "pwd.dispatchEvent(new Event('input',{bubbles:true}));"
    "var form=pwd.closest('form');"
    "var user=null;"
    "if(form){"
    "user=form.querySelector('input[type=text],input[type=email],"
    "input[type=tel],input:not([type]),input[name*=user i],"
    "input[name*=account i]');}"
    "if(user){"
    "setter.call(user,{user});"
    "user.dispatchEvent(new Event('input',{bubbles:true}));}"
    "return {ok:true,why:'filled'};})()"
)


def build_js(action: dict) -> str:
    """把白名单动作翻译为页面 JS（坐标/文本经 JSON 注入，防注入）。

    使用 .replace() 占位符替换（非 str.format），模板保持纯 JS 写法。
    """
    name = action.get("action")
    if name == "click":
        return (CLICK_JS.replace("{x}", str(int(action["x"])))
                        .replace("{y}", str(int(action["y"]))))
    if name == "type":
        js = TYPE_JS.replace("{x}", str(int(action["x"])))
        js = js.replace("{y}", str(int(action["y"])))
        # v2.1.2 修复：先替换 {submit} 再注入 {text}——旧顺序下，
        # 用户输入文本里若含字面量 "{submit}" 会被后续替换击穿，
        # 造成注入内容被篡改。{text} 永远最后注入。
        js = js.replace("{submit}",
                        "true" if action.get("submit") else "false")
        js = js.replace("{text}", json.dumps(str(action.get("text", ""))))
        return js
    if name == "scroll":
        return (SCROLL_JS.replace("{dx}", str(int(action.get("dx", 0))))
                         .replace("{dy}", str(int(action.get("dy", 0)))))
    if name == "login_fill":
        return (FILL_JS
                .replace("{user}", json.dumps(str(action.get("username", ""))))
                .replace("{pwd}", json.dumps(str(action.get("password", "")))))
    if name == "sms_fill":
        # 面板专用动作（§14.3）：验证码由用户输入，不来自模型输出
        return SMS_FILL_JS.replace("{code}",
                                   json.dumps(str(action.get("code", ""))))
    raise GateError(f"动作 {name!r} 无 JS 模板")


# --------------------------------------------------------------------------- #
# 执行器（§7.3 坐标换算 / §7.4 打字）
# --------------------------------------------------------------------------- #
class PageActor:
    """把动作指令执行到目标页面（runJavaScript 主世界）。"""

    def __init__(self, page):
        self._page = page
        self._dpr = 1.0

    def sync_dpr(self):
        """读取 devicePixelRatio：截图像素 ÷ DPR = CSS 坐标（§7.3）。"""
        try:
            self._page.runJavaScript(
                "window.devicePixelRatio",
                lambda v: setattr(self, "_dpr", float(v or 1.0)))
        except Exception:
            pass

    def act(self, action: dict, on_done=None) -> None:
        """执行一个动作。on_done(ok: bool, message: str)。"""
        name = action.get("action")
        if name == "back":
            try:
                self._page.triggerAction(self._page.Back)
            except Exception as e:
                self._finish(on_done, False, f"后退失败：{e}")
                return
            self._finish(on_done, True, "后退")
            return
        if name == "wait":
            # wait 由面板定时器处理（QTimer），此处仅确认
            self._finish(on_done, True,
                         f"等待 {action.get('ms', 500)}ms")
            return
        try:
            js = build_js(action)
        except (GateError, KeyError, TypeError, ValueError) as e:
            self._finish(on_done, False, f"动作无效：{e}")
            return

        def _cb(raw):
            ok, why = False, ""
            try:
                data = json.loads(raw or "{}")
                ok = bool(data.get("ok"))
                why = data.get("why", "")
            except Exception:
                ok = bool(raw)
            self._finish(on_done, ok, why or name)

        try:
            self._page.runJavaScript(js, _cb)
        except Exception as e:
            self._finish(on_done, False, f"执行失败：{e}")

    @staticmethod
    def _finish(on_done, ok, msg):
        if on_done:
            on_done(ok, msg)


# --------------------------------------------------------------------------- #
# 无进展检测（§7.5）：截图感知哈希
# --------------------------------------------------------------------------- #
def screen_fingerprint(data_uri: str) -> str:
    """截图感知哈希（简化版）：缩放 8×8 灰度，按均值转位串。

    用于"连续 N 步画面无变化"判定，避免 AI 陷入循环。
    """
    if not data_uri:
        return ""
    try:
        raw = base64.b64decode(data_uri.split(",", 1)[1])
        from PySide6.QtGui import QImage
        img = QImage.fromData(raw).scaled(8, 8).convertToFormat(
            QImage.Format_Grayscale8)
        vals = [img.pixelColor(x, y).lightness()
                for y in range(img.height()) for x in range(img.width())]
        if not vals:
            return ""
        avg = sum(vals) / len(vals)
        return "".join("1" if v >= avg else "0" for v in vals)
    except Exception:
        return ""

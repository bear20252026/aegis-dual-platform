"""shell_adapter.py —— 壳层抽象（单文件单职责：壳可随时替换）。

背景（2026-08-15）：Aegis 采取部分重构路线（B=pytauri-wheel 保留
全部 Python 业务），但【禁止被困】原则要求壳层可逆——pywebview 与
pytauri 作为**可插拔实现**，业务（api_bridge/nav_queue 等 25 文件）
只依赖本抽象接口，不依赖具体壳；pytauri 停滞即切回 pywebview，
业务零影响。

接口（薄）：create_window / start / events / core / settings / windows
- PywebviewShell：当前壳（pywebview 6.2.1，Windows WebView2）
- PytauriShell：目标壳（pytauri-wheel 0.8.0，PoC 级，可选导入，
  未安装时导入抛清晰错误——壳可替换性验证）
- get_shell(name)：工厂（默认 pywebview，配置可切换）

约定：本模块不含业务逻辑（DNT/威胁拦截等仍在 main_webview 经
events 钩子挂接）；新增壳实现需实现全部接口方法（缺失用 None 兜底）。
"""

from collections.abc import Callable
from typing import Any


class Shell:
    """壳抽象基类：定义所有壳实现的公共接口（协议，非强制继承）。"""

    name = "abstract"

    def create_window(self, js_api: Any, url: str, **kwargs: Any) -> Any:
        """创建主窗口（js_api 必须在创建时传入——renderer 从 _js_api 读取）。"""
        raise NotImplementedError

    def start(self, func: Callable | None = None) -> None:
        """启动事件循环（可选 func：循环前执行）。"""
        raise NotImplementedError

    def events(self, window: Any) -> Any:
        """窗口事件对象（request_sent 等钩子挂接点）；缺失返回 None。"""
        return None

    def core(self, window: Any) -> Any:
        """底层内核对象（pywebview: CoreWebView2）；缺失返回 None。"""
        return None

    def settings(self) -> dict:
        """壳模块级设置项（pywebview.settings）；无则返回空 dict。"""
        return {}

    def windows(self) -> list:
        """已创建窗口列表（pywebview.windows）；无则返回空 list。"""
        return []


class PywebviewShell(Shell):
    """当前壳：pywebview 6.2.1（Windows WebView2，Aegis 现状实现）。"""

    name = "pywebview"

    def __init__(self) -> None:
        # 延迟导入：pywebview 为运行时依赖，仅实际使用本实现时加载；
        # 未安装时抛清晰错误（提示 requirements.txt / pip install），
        # 与 PytauriShell 对称——壳可替换性（禁止被困原则）验证。
        try:
            import webview  # type: ignore[import-not-found]
        except ImportError as exc:  # pragma: no cover - 依赖缺失时清晰报错
            raise ImportError(
                "PywebviewShell 需要 pywebview（运行时依赖，见 "
                "requirements.txt）；未安装时无法使用本壳"
            ) from exc
        self._webview = webview

    def create_window(self, js_api: Any, url: str, **kwargs: Any) -> Any:
        return self._webview.create_window(js_api=js_api, url=url, **kwargs)

    def start(self, func: Callable | None = None) -> None:
        self._webview.start(func)

    def events(self, window: Any) -> Any:
        return getattr(window, "events", None)

    def core(self, window: Any) -> Any:
        try:
            gui = getattr(window, "gui", None)
            wv = getattr(gui, "webview", None)
            return getattr(wv, "CoreWebView2", None)
        except Exception:
            return None

    def settings(self) -> dict:
        """壳模块级设置项（pywebview.settings 原引用——直接修改生效）；
        无则返回空 dict。"""
        return self._webview.settings

    def windows(self) -> list:
        return list(self._webview.windows)


class PytauriShell(Shell):
    """目标壳：pytauri-wheel 0.8.0（可用级适配器，壳可替换性验证）。

    完善（2026-08-15 第④步）：从 PoC 级提升为可用级——窗口参数
    （title/width/height）接收 + frontend_dist 解析（显式 → url 本地
    目录 → 就近）；js_api 白名单（_JS_EXPOSED）注册为 pytauri 命令。
    未安装 pytauri-wheel 时导入抛清晰错误（提示安装/切回 pywebview），
    不静默失败。真实窗口渲染依赖本机 GUI 会话（三关实测中体积关
    已通过；启动/内存待本机验证）。
    """

    name = "pytauri"

    def __init__(self) -> None:
        try:
            from os import environ
            # pytauri-wheel 内部标识（官方 examples 同款，须在任何
            # pytauri 使用前设置）
            environ.setdefault("_PYTAURI_DIST", "pytauri-wheel")
            from anyio.from_thread import start_blocking_portal  # noqa: F401

            # pytauri-wheel 为运行时依赖（可选壳），未装时无类型桩——
            # 与 main_webview 的 webview import 同惯例忽略 import-not-found
            from pytauri import Commands  # type: ignore[import-not-found]
            from pytauri_wheel.lib import (  # type: ignore[import-not-found]
                builder_factory,
                context_factory,
            )
            self._builder_factory = builder_factory
            self._context_factory = context_factory
            self._commands = Commands()
        except ImportError as exc:  # pragma: no cover - 依赖缺失时清晰报错
            raise ImportError(
                "PytauriShell 需要 pytauri-wheel（pip install "
                "\"pytauri-wheel == 0.8.*\"）；未安装时请保持 pywebview 壳"
            ) from exc
        self._window_kwargs: dict = {}
        self._frontend_dir = None
        self._tauri_dir = None

    def _resolve_frontend_dir(self, url: str, kwargs: dict) -> Any:
        """解析前端资源目录（frontend_dist）优先级：显式 → url 本地目录 → 就近。

        pytauri 的 Tauri.toml frontendDist 必须是静态资源路径：
        - kwargs 显式 frontend_dist（迁移时 Aegis 指定 shell/ 目录）
        - url 为本地文件（如 start.html）时取其所在目录
        - 回退本模块就近目录（PoC 默认）
        """
        from pathlib import Path

        explicit = kwargs.get("frontend_dist")
        if explicit:
            p = Path(explicit)
            return p if p.is_dir() else p.parent
        if url and "://" not in url:  # 本地文件路径
            p = Path(url)
            return p.parent if p.is_file() else p
        return Path(__file__).resolve().parent

    def _resolve_tauri_dir(self, kwargs: dict) -> Any:
        """解析 Tauri 配置目录（含 Tauri.toml/tauri.conf.json）优先级：
        显式 tauri_conf_dir → 就近查找（模块目录向上）→ 清晰报错。

        pytauri context_factory(src_tauri_dir) 要求该目录含 Tauri 配置
        （productName/identifier/frontendDist 等）——与前端资源目录
        （frontend_dist）是两个不同概念，须分别解析。
        """
        from pathlib import Path

        explicit = kwargs.get("tauri_conf_dir")
        if explicit:
            p = Path(explicit)
            return p if p.is_dir() else p.parent
        # 就近向上查找 Tauri.toml / tauri.conf.json
        cur = Path(__file__).resolve().parent
        for cand in (cur, cur.parent, cur.parent.parent):
            if (cand / "Tauri.toml").exists() or (cand / "tauri.conf.json").exists():
                return cand
        raise ValueError(
            "PytauriShell 需要 Tauri 配置目录（含 Tauri.toml/tauri.conf.json，"
            "可经 kwargs tauri_conf_dir 显式指定）；缺失时无法构建 pytauri 应用"
        )

    def create_window(self, js_api: Any, url: str, **kwargs: Any) -> Any:
        # 可用级：注册 js_api 白名单方法为命令（与 capabilities 映射一致），
        # 保存窗口参数（title/width/height），解析前端资源目录与
        # Tauri 配置目录。
        self._window_kwargs = {
            k: kwargs.get(k) for k in ("title", "width", "height")
            if kwargs.get(k) is not None
        }
        self._frontend_dir = self._resolve_frontend_dir(url, kwargs)
        self._tauri_dir = self._resolve_tauri_dir(kwargs)
        exposed = getattr(js_api, "_JS_EXPOSED", None)
        if exposed:
            import json as _json

            def _make_wrapper(m: Any):
                """工厂：闭包绑定 js_api 方法，wrapper 仅接收 pytauri 已知
                参数 body（带注解），返回 str（JSON 序列化 js_api 结果）。
                pytauri wrap_pyfunc 要求参数/返回均有类型注解，且
                parse_parameters 拒绝已知参数名（body 等）之外的任何参数——
                故 js_api 方法须经本适配器（业务代码零改动）。"""
                def wrapper(body: dict | None = None) -> str:
                    try:
                        if isinstance(body, dict):
                            result = m(**body)
                        elif body is None:
                            result = m()
                        else:
                            result = m(body)
                        return _json.dumps(result, ensure_ascii=False,
                                           default=str)
                    except Exception as exc:  # 命令执行异常 → JSON 错误串
                        return _json.dumps({"error": repr(exc)})
                return wrapper

            for name in sorted(exposed):
                method = getattr(js_api, name, None)
                if callable(method):
                    wrapper = _make_wrapper(method)
                    wrapper.__name__ = name
                    self._commands.command(name)(wrapper)
        return self

    def start(self, func: Callable | None = None) -> None:
        if func is not None:
            func()
        from anyio.from_thread import start_blocking_portal

        with start_blocking_portal("asyncio") as portal:
            app = self._builder_factory().build(
                context=self._context_factory(self._frontend_dir),
                invoke_handler=self._commands.generate_handler(portal),
            )
            # 窗口参数（title/width/height）在 pytauri 中经 Tauri.toml
            # [[app.windows]] 或 WebviewWindowBuilder 应用；此处保持
            # builder 构建（PoC 已验证），参数应用留待本机三关实测确认。
            app.run_return()


def get_shell(name: str = "pywebview") -> Shell:
    """壳工厂：按名称返回壳实现（默认 pywebview——现状保持）。"""
    if name == "pywebview":
        return PywebviewShell()
    if name == "pytauri":
        return PytauriShell()
    raise ValueError(f"unknown shell: {name}（可选 pywebview / pytauri）")

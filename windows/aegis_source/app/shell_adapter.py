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

from typing import Any, Callable, Optional


class Shell:
    """壳抽象基类：定义所有壳实现的公共接口（协议，非强制继承）。"""

    name = "abstract"

    def create_window(self, js_api: Any, url: str, **kwargs: Any) -> Any:
        """创建主窗口（js_api 必须在创建时传入——renderer 从 _js_api 读取）。"""
        raise NotImplementedError

    def start(self, func: Optional[Callable] = None) -> None:
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

    def start(self, func: Optional[Callable] = None) -> None:
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
    """目标壳：pytauri-wheel 0.8.0（PoC 级适配器，壳可替换性验证）。

    PoC 级（2026-08-15 三关实测：体积关通过、启动/内存需本机验证）：
    本实现证明"换壳不动业务"的可行性；未安装 pytauri-wheel 时
    导入抛清晰错误（提示安装/切回 pywebview），不静默失败。
    """

    name = "pytauri"

    def __init__(self) -> None:
        try:
            from os import environ
            # pytauri-wheel 内部标识（官方 examples 同款，须在任何
            # pytauri 使用前设置）
            environ.setdefault("_PYTAURI_DIST", "pytauri-wheel")
            from anyio.from_thread import start_blocking_portal  # noqa: F401
            from pytauri import Commands  # noqa: F401
            from pytauri_wheel.lib import builder_factory, context_factory  # noqa: F401
            self._builder_factory = builder_factory
            self._context_factory = context_factory
            self._commands = Commands()
        except ImportError as exc:  # pragma: no cover - 依赖缺失时清晰报错
            raise ImportError(
                "PytauriShell 需要 pytauri-wheel（pip install "
                "\"pytauri-wheel == 0.8.*\"）；未安装时请保持 pywebview 壳"
            ) from exc

    def create_window(self, js_api: Any, url: str, **kwargs: Any) -> Any:
        # PoC 级：注册 js_api 白名单方法为命令（与 capabilities 映射一致）
        # 完整窗口创建依赖 Tauri.toml + frontendDist，PoC 阶段由
        # aegis-poc 演示；此处返回命令注册表供事件循环挂接
        from pathlib import Path

        exposed = getattr(js_api, "_JS_EXPOSED", None)
        if exposed:
            for name in sorted(exposed):
                method = getattr(js_api, name, None)
                if callable(method):
                    self._commands.command(name)(method)
        self._frontend_dir = Path(__file__).resolve().parent  # PoC：就近查找 index.html
        return self

    def start(self, func: Optional[Callable] = None) -> None:
        if func is not None:
            func()
        from anyio.from_thread import start_blocking_portal

        with start_blocking_portal("asyncio") as portal:
            app = self._builder_factory().build(
                context=self._context_factory(self._frontend_dir),
                invoke_handler=self._commands.generate_handler(portal),
            )
            app.run_return()


def get_shell(name: str = "pywebview") -> Shell:
    """壳工厂：按名称返回壳实现（默认 pywebview——现状保持）。"""
    if name == "pywebview":
        return PywebviewShell()
    if name == "pytauri":
        return PytauriShell()
    raise ValueError(f"unknown shell: {name}（可选 pywebview / pytauri）")

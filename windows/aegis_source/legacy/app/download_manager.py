# -*- coding: utf-8 -*-
"""download_manager.py —— 下载管理器。

监听 QtWebEngine 的下载事件，维护下载列表（进度/速度/状态），
并通过 Qt 信号通知 UI（下载栏 / 下载面板）刷新。
"""

import json
import os
import time
from PySide6.QtCore import QObject, Signal


def _dl_path(download) -> str:
    """Qt6 下载对象的完整目标路径（目录 + 文件名）。"""
    try:
        return os.path.join(download.downloadDirectory(),
                            download.downloadFileName())
    except Exception:
        return ""


def _dl_suggested(download) -> str:
    """建议文件名（Qt6），回退到 URL 末段。"""
    try:
        name = download.suggestedFileName()
        if name:
            return name
    except Exception:
        pass
    return ""


def _dl_set_path(download, full_path: str):
    """Qt6：拆成目录 + 文件名分别设置。"""
    download.setDownloadDirectory(os.path.dirname(full_path) or ".")
    download.setDownloadFileName(os.path.basename(full_path))


class DownloadItem:
    """单个下载任务的状态对象（非 QObject，由 DownloadManager 转发信号）。"""

    def __init__(self, download, download_dir: str, explicit_path: str = ""):
        self.download = download
        self.id = id(download)
        self.url = download.url().toString()
        suggested = _dl_suggested(download)
        self.filename = suggested or (self.url.split("/")[-1] or "download")
        self.total = download.totalBytes()
        self.received = 0
        self.speed = 0.0          # 字节/秒
        self.state = "downloading"  # downloading | paused | completed | failed | cancelled
        self.error = ""
        self.path = ""
        self._last_time = time.time()
        self._last_bytes = 0

        # Qt6：receivedBytesChanged 无参，进度从 getter 读取
        download.receivedBytesChanged.connect(self._on_progress)
        download.stateChanged.connect(self._on_state)
        # 设置保存路径（用户显式选择优先，否则默认目录 + 去重）
        if explicit_path:
            self.path = explicit_path
            _dl_set_path(download, explicit_path)
        elif download_dir:
            os.makedirs(download_dir, exist_ok=True)
            final_path = os.path.join(
                download_dir, _unique_name(download_dir, self.filename))
            _dl_set_path(download, final_path)
            self.path = final_path
        # Qt6：必须 accept() 才正式开始下载
        try:
            download.accept()
        except Exception:
            pass

    def _on_progress(self):
        received = self.download.receivedBytes()
        total = self.download.totalBytes()
        now = time.time()
        dt = now - self._last_time
        if dt > 0.4:
            self.speed = (received - self._last_bytes) / dt
            self._last_time = now
            self._last_bytes = received
        self.received = received
        self.total = total

    def _on_state(self, state):
        # Qt6 DownloadState，按枚举成员名映射（避免跨版本整型差异）
        name = getattr(state, "name", None) or str(state)
        if name in ("DownloadRequested", "DownloadInProgress"):
            self.state = "downloading"
        elif name == "DownloadCompleted":
            self.state = "completed"
        elif name == "DownloadCancelled":
            self.state = "cancelled"
        elif name == "DownloadInterrupted":
            self.state = "failed"

    def pause(self):
        try:
            self.download.pause()
        except Exception:
            pass

    def resume(self):
        try:
            self.download.resume()
        except Exception:
            pass

    def cancel(self):
        try:
            self.download.cancel()
        except Exception:
            pass

    def percent(self) -> float:
        if self.total > 0:
            return min(100, self.received * 100.0 / self.total)
        return 0.0


def _unique_name(directory: str, name: str) -> str:
    """避免覆盖同名文件。"""
    base, ext = os.path.splitext(name)
    candidate = name
    i = 1
    while os.path.exists(os.path.join(directory, candidate)):
        candidate = f"{base} ({i}){ext}"
        i += 1
    return candidate


class DownloadManager(QObject):
    """管理全部下载任务，并向 UI 发信号。

    下载进入终态（完成/失败/取消）后持久化到 downloads.json，
    重启浏览器后仍可在下载面板中查看历史（不可续传，仅展示）。
    """

    # 信号参数：DownloadItem
    item_added = Signal(object)
    item_updated = Signal(object)

    # 终态：进入即写入历史；其余状态（下载中/暂停）只存在于会话内
    _TERMINAL_STATES = {"completed", "failed", "cancelled"}
    _HISTORY_MAX = 200

    def __init__(self, config, data_dir: str = "", parent=None):
        super().__init__(parent)
        self.config = config
        self._items = {}     # id -> DownloadItem
        self._attached = set()
        # 下载历史持久化（data_dir 为空 = 无痕/纯内存会话，不落盘）
        self._data_dir = data_dir or ""
        self._history_file = ""
        if self._data_dir:
            self._history_file = os.path.join(self._data_dir, "downloads.json")
        self._history = {}    # str(item_id) -> record dict（仅终态记录）
        self._load_history()

    @property
    def download_dir(self) -> str:
        return (self.config.download_dir
                or os.path.join(os.path.expanduser("~"), "Downloads"))

    def items(self):
        return list(self._items.values())

    def active_count(self) -> int:
        return sum(1 for it in self._items.values()
                   if it.state == "downloading")

    def on_download(self, download, explicit_path: str = ""):
        """由主窗口的 downloadRequested 信号调用。

        explicit_path 非空表示用户已手动选择保存位置（ask 模式）。
        """
        item = DownloadItem(download, self.download_dir, explicit_path)
        self._items[item.id] = item
        download.receivedBytesChanged.connect(
            lambda it=item: self.item_updated.emit(it))
        download.stateChanged.connect(
            lambda s, it=item: self.item_updated.emit(it))
        download.stateChanged.connect(
            lambda s, it=item: self._on_item_state(it))
        self.item_added.emit(item)

    def _on_item_state(self, item):
        """进入终态时把记录写入下载历史（跨会话保留）。"""
        if item.state in self._TERMINAL_STATES:
            self._persist(item)

    # ------------------------------------------------------------------ #
    # 下载历史（downloads.json 持久化）
    # ------------------------------------------------------------------ #
    def _load_history(self):
        if not self._history_file:
            return
        try:
            if os.path.exists(self._history_file):
                with open(self._history_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    self._history = {
                        str(k): v for k, v in data.items()
                        if isinstance(v, dict)}
        except (OSError, json.JSONDecodeError):
            self._history = {}

    def _save_history(self):
        if not self._history_file:
            return
        try:
            os.makedirs(os.path.dirname(self._history_file),
                        exist_ok=True)
            with open(self._history_file, "w", encoding="utf-8") as f:
                json.dump(self._history, f, ensure_ascii=False, indent=2)
            from .security import harden_perms
            harden_perms(self._history_file)
        except OSError:
            pass

    def _persist(self, item):
        rec = {
            "url": item.url,
            "filename": item.filename,
            "path": item.path,
            "total": item.total,
            "received": item.received,
            "state": item.state,
            "time": time.time(),
        }
        self._history[str(item.id)] = rec
        if len(self._history) > self._HISTORY_MAX:
            for k in list(self._history)[:-self._HISTORY_MAX]:
                self._history.pop(k, None)
        self._save_history()

    def history(self) -> list:
        """历史下载记录（最新在前；仅终态）。"""
        recs = sorted(self._history.values(),
                      key=lambda r: r.get("time", 0), reverse=True)
        return recs

    def clear_history(self):
        self._history = {}
        if self._history_file:
            try:
                os.remove(self._history_file)
            except OSError:
                pass

    def remove(self, item):
        self._items.pop(item.id, None)

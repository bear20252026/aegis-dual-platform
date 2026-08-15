"""database.py —— SQLite 基础设施。

使用 WAL 模式提升并发读性能，开启外键，提供统一连接管理。
商用浏览器（Chrome/Firefox）的历史与书签均为 SQLite，这里对齐该方案。

连接策略（工程优化）：线程级连接复用——同一线程对同一 db 复用连接，
避免每次操作重复 connect + PRAGMA 初始化开销；同时修复 :memory: 库
每次新建连接导致数据丢失的问题（复用连接 = 同一内存库）。
close() 统一收尾所有连接（含线程池中的）；异常路径自动 rollback，
避免复用连接残留未提交事务。
"""

import os
import sqlite3
import threading

from .paths import ensure_dir

# 线程级连接池：{db_path -> connection}
_local = threading.local()


class _TrackedConnection(sqlite3.Connection):
    """连接子类：关闭时自动从所属 Database 的登记表中注销。"""

    owner: "Database | None" = None

    def close(self):
        owner = self.owner
        if owner is not None:
            self.owner = None
            owner._untrack(self)
        super().close()


class Database:
    """单个 SQLite 数据库的薄封装（线程级连接复用）。"""

    def __init__(self, db_path: str, schema_sql: str | None = None):
        self.db_path = db_path
        # 已打开且尚未关闭的连接登记表（close() 时统一收尾）
        self._conns: set[sqlite3.Connection] = set()
        self._conn_lock = threading.Lock()
        if db_path != ":memory:":
            ensure_dir(os.path.dirname(db_path))
        if schema_sql:
            self.executescript(schema_sql)

    def _new_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, check_same_thread=False,
                               factory=_TrackedConnection)
        conn.owner = self
        with self._conn_lock:
            self._conns.add(conn)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA synchronous=NORMAL")
        # W-08 整改（国防级审查）：数据库文件 + WAL/SHM sidecar 平台权限
        # 收紧（POSIX 0600 / Windows DACL 当前用户——security.harden_perms）
        try:
            from .security import harden_perms
            harden_perms(self.db_path)
            import os as _os
            for _side in (self.db_path + "-wal", self.db_path + "-shm"):
                if _os.path.exists(_side):
                    harden_perms(_side)
        except Exception:
            pass
        return conn

    def connect(self) -> sqlite3.Connection:
        """返回线程级复用连接（首次创建时初始化 PRAGMA）。"""
        pool = getattr(_local, "pool", None)
        if pool is None:
            pool = _local.pool = {}
        conn = pool.get(self.db_path)
        if conn is None or conn.owner is None:
            # 新连接，或该连接已被 close()（owner 置 None）后重建
            conn = self._new_conn()
            pool[self.db_path] = conn
        return conn

    def execute(self, sql: str, params=()):
        conn = self.connect()
        try:
            cur = conn.execute(sql, params)
            conn.commit()
            return cur
        except Exception:
            try:
                conn.rollback()
            except sqlite3.Error:
                pass
            raise

    def executescript(self, sql: str):
        conn = self.connect()
        try:
            conn.executescript(sql)
            conn.commit()
        except Exception:
            try:
                conn.rollback()
            except sqlite3.Error:
                pass
            raise

    def query(self, sql: str, params=()) -> list:
        conn = self.connect()
        try:
            return [dict(r) for r in conn.execute(sql, params)]
        except Exception:
            try:
                conn.rollback()
            except sqlite3.Error:
                pass
            raise

    def query_one(self, sql: str, params=()):
        conn = self.connect()
        try:
            row = conn.execute(sql, params).fetchone()
            return dict(row) if row else None
        except Exception:
            try:
                conn.rollback()
            except sqlite3.Error:
                pass
            raise

    def vacuum(self):
        self.execute("VACUUM")

    def _untrack(self, conn):
        with self._conn_lock:
            self._conns.discard(conn)

    def close(self):
        """关闭所有仍处于打开状态的连接（可重复调用）。

        包括线程池中的复用连接；关闭后 owner 置 None，
        下次 connect() 自动重建。
        """
        with self._conn_lock:
            conns = list(self._conns)
            self._conns.clear()
        for conn in conns:
            try:
                conn.close()
            except sqlite3.Error:
                pass
        # 清除本线程池中指向本库的连接引用
        try:
            pool = getattr(_local, "pool", None)
            if pool:
                pool.pop(self.db_path, None)
        except Exception:
            pass

"""logging_setup.py —— 最小文件日志（排障与审计痕迹）。

写到数据目录 logs/aegis.log；单文件 1MB，保留 3 份滚动。
安全相关事件（IPC 拒绝 / 站点拦截 / 证书决策）统一走 logger.info，
便于事后审计。
"""

import logging
import os

_CONFIGURED = False


def setup_logging(data_dir: str) -> logging.Logger:
    global _CONFIGURED
    logger = logging.getLogger("Aegis")
    if _CONFIGURED:
        return logger
    logger.setLevel(logging.INFO)
    try:
        log_dir = os.path.join(data_dir, "logs")
        os.makedirs(log_dir, exist_ok=True)
        from logging.handlers import RotatingFileHandler
        handler = RotatingFileHandler(
            os.path.join(log_dir, "aegis.log"),
            maxBytes=1024 * 1024, backupCount=3, encoding="utf-8")
        handler.setFormatter(logging.Formatter(
            "%(asctime)s %(levelname)s %(message)s"))
        logger.addHandler(handler)
    except OSError:
        # 日志失败绝不影响浏览器运行
        pass
    _CONFIGURED = True
    return logger


def get_logger() -> logging.Logger:
    return logging.getLogger("Aegis")

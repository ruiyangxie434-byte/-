"""
日志模块
提供统一的日志记录，支持控制台输出和文件滚动日志。
用法：
    from logger import get_logger
    log = get_logger(__name__)
    log.info("操作成功")
"""
from __future__ import annotations

import logging
import logging.handlers
from pathlib import Path

from config import LOG_BACKUP, LOG_DIR, LOG_LEVEL, LOG_MAX_BYTES


def get_logger(name: str = "sport_system") -> logging.Logger:
    """
    返回指定名称的 Logger，已配置文件滚动 + 控制台双输出。
    多次调用同一 name 返回同一实例（Python logging 保证）。
    """
    logger = logging.getLogger(name)
    if logger.handlers:           # 避免重复添加 handler
        return logger

    logger.setLevel(getattr(logging, LOG_LEVEL, logging.INFO))

    fmt = logging.Formatter(
        fmt="%(asctime)s  %(levelname)-8s  [%(name)s]  %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # ── 滚动文件 handler ──
    log_file = LOG_DIR / "sport_system.log"
    fh = logging.handlers.RotatingFileHandler(
        log_file,
        maxBytes=LOG_MAX_BYTES,
        backupCount=LOG_BACKUP,
        encoding="utf-8",
    )
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    # ── 控制台 handler ──
    ch = logging.StreamHandler()
    ch.setFormatter(fmt)
    ch.setLevel(logging.WARNING)   # 控制台只显示 WARNING 及以上
    logger.addHandler(ch)

    return logger

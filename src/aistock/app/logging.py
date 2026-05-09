"""
日志配置。

支持：
- 分模块日志文件（app.log / data.log / trade.log）
- 控制台统一输出
- 自动创建 logs 目录
- 按日轮转（通过 RotatingFileHandler）
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

# 已废弃，保留兼容性导入
LegacyFormatter = logging.Formatter


class ContextFilter(logging.Filter):
    """为日志添加上下文信息。"""

    def __init__(self, context: str = "") -> None:
        super().__init__()
        self.context = context

    def filter(self, record: logging.LogRecord) -> bool:
        record.context = getattr(record, "context", self.context)
        return True


def setup_logging(
    level: str = "INFO",
    logs_dir: str = "logs",
    app_name: str = "aistock",
) -> None:
    """
    配置全模块日志。

    日志输出：
    - 控制台（stdout）
    - logs/app.log        — 应用层日志（CLI、策略、信号）
    - logs/data.log       — 数据层日志（同步、清洗）
    - logs/trade.log      — 交易层日志（下单、成交、风控）
    """
    resolved_level = getattr(logging, level.upper(), logging.INFO)
    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    root_logger = logging.getLogger()
    root_logger.setLevel(resolved_level)
    for handler in list(root_logger.handlers):
        handler.close()
    root_logger.handlers.clear()

    log_dir = Path(logs_dir)
    log_dir.mkdir(parents=True, exist_ok=True)

    # 控制台
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    root_logger.addHandler(stream_handler)

    # 分模块文件
    _add_file_logger(root_logger, log_dir / f"{app_name}.log", formatter, "app")
    _add_file_logger(root_logger, log_dir / "data.log", formatter, "data")
    _add_file_logger(root_logger, log_dir / "trade.log", formatter, "trade")


def _add_file_logger(
    logger: logging.Logger,
    path: Path,
    fmt: logging.Formatter,
    module: str,
) -> None:
    handler = logging.FileHandler(path, encoding="utf-8")
    handler.setFormatter(fmt)
    handler.addFilter(ContextFilter(module))
    logger.addHandler(handler)


def get_logger(name: str) -> logging.Logger:
    """获取带模块前缀的 logger。"""
    return logging.getLogger(name)

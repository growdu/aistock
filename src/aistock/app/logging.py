from __future__ import annotations

import logging
from pathlib import Path
import sys


def setup_logging(level: str = "INFO", logs_dir: str = "logs", app_name: str = "aistock") -> None:
    resolved_level = getattr(logging, level.upper(), logging.INFO)
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")

    root_logger = logging.getLogger()
    root_logger.setLevel(resolved_level)
    root_logger.handlers.clear()

    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(formatter)
    root_logger.addHandler(stream_handler)

    log_dir = Path(logs_dir)
    log_dir.mkdir(parents=True, exist_ok=True)
    file_handler = logging.FileHandler(log_dir / f"{app_name}.log", encoding="utf-8")
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)

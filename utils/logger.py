import logging
import os
from datetime import datetime
from logging.handlers import RotatingFileHandler
from typing import Optional

DEFAULT_LOG_DIR = "logs"
DEFAULT_LOG_LEVEL = logging.INFO
LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

logger = logging.getLogger("SpaceshipSim")


def _build_default_log_path(log_dir: str) -> str:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return os.path.join(log_dir, f"session_{timestamp}.log")


def setup_logging(log_file: Optional[str] = None, level: int = DEFAULT_LOG_LEVEL) -> str:
    root_logger = logging.getLogger()

    if log_file:
        if os.path.isdir(log_file):
            log_dir = log_file
            log_file = _build_default_log_path(log_dir)
        else:
            log_dir = os.path.dirname(log_file) or "."
    else:
        log_dir = DEFAULT_LOG_DIR
        log_file = _build_default_log_path(log_dir)

    os.makedirs(log_dir, exist_ok=True)

    formatter = logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT)

    has_stream = any(isinstance(handler, logging.StreamHandler) for handler in root_logger.handlers)
    if not has_stream:
        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(formatter)
        root_logger.addHandler(stream_handler)

    normalized_target = os.path.abspath(log_file)
    has_file = False
    for handler in root_logger.handlers:
        if isinstance(handler, RotatingFileHandler) and os.path.abspath(handler.baseFilename) == normalized_target:
            has_file = True
            break
    if not has_file:
        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=10 * 1024 * 1024,
            backupCount=10,
            encoding="utf-8",
        )
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)

    root_logger.setLevel(level)

    logger.debug("Logging initialized", extra={"log_file": log_file})
    return log_file

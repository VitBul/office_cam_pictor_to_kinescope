"""Structured logging setup for the CamKinescope project.

Provides a single setup function that configures console and rotating file
handlers with a unified format.
"""

import logging
import os
from logging.handlers import RotatingFileHandler

LOG_FORMAT = "[%(asctime)s] %(levelname)s %(name)s: %(message)s"
DATE_FORMAT = "%d.%m.%Y %H:%M:%S"

MAX_LOG_BYTES = 10 * 1024 * 1024  # 10 MB
BACKUP_COUNT = 5


def setup_logger(name: str, log_dir: str = "./logs") -> logging.Logger:
    """Create and return a logger with console and rotating-file handlers.

    Args:
        name: Logger name, typically ``__name__`` of the calling module.
        log_dir: Directory where log files are stored. Created if missing.

    Returns:
        Configured :class:`logging.Logger` instance.
    """
    os.makedirs(log_dir, exist_ok=True)

    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)

    # Avoid adding duplicate handlers when called more than once for the
    # same logger name (e.g. during tests or module reloads).
    if logger.handlers:
        return logger

    formatter = logging.Formatter(fmt=LOG_FORMAT, datefmt=DATE_FORMAT)

    # --- Console handler ---
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)

    # --- Rotating file handler ---
    log_file = os.path.join(log_dir, "camkinescope.log")
    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=MAX_LOG_BYTES,
        backupCount=BACKUP_COUNT,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(formatter)

    logger.addHandler(console_handler)
    logger.addHandler(file_handler)

    return logger

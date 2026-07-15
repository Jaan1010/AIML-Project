"""
logger_setup.py
---------------
Configures a single, reusable logger for the whole project: console output
plus a rotating log file so runs are auditable after the fact.
"""

import logging
from logging.handlers import RotatingFileHandler

import config


def get_logger(name: str = "job_tracker") -> logging.Logger:
    logger = logging.getLogger(name)

    # Avoid adding duplicate handlers if get_logger() is called more than once.
    if logger.handlers:
        return logger

    logger.setLevel(getattr(logging, config.LOG_LEVEL.upper(), logging.INFO))

    fmt = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(fmt)
    logger.addHandler(console_handler)

    # Rotating file handler (5 MB per file, keep 5 backups)
    try:
        config.LOG_DIR.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(
            config.LOG_DIR / "job_tracker.log",
            maxBytes=5 * 1024 * 1024,
            backupCount=5,
            encoding="utf-8",
        )
        file_handler.setFormatter(fmt)
        logger.addHandler(file_handler)
    except OSError:
        # If the filesystem is read-only or unavailable, fall back to
        # console-only logging rather than crashing the whole app.
        logger.warning("Could not create log directory; continuing with console logging only.")

    return logger

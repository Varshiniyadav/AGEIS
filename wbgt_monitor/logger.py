"""
logger.py

Central logging setup for the WBGT Monitor project.

Log folder : ./logs/
Log file   : wbgt_monitor_YYYYMMDD.log  (one file per day)
Format     : [TIMESTAMP] [LEVEL] [MODULE] message

Usage (in any module):
    from logger import get_logger
    log = get_logger(__name__)
    log.info("Something happened")
    log.warning("Something suspicious")
    log.error("Something failed")
"""

import logging
import os
from datetime import datetime
from logging.handlers import TimedRotatingFileHandler

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
LOG_DIR      = os.getenv("LOG_DIR", "./logs")
LOG_LEVEL    = os.getenv("LOG_LEVEL", "DEBUG")
_LOG_FORMAT  = "[%(asctime)s] [%(levelname)-8s] [%(name)s] %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# ---------------------------------------------------------------------------
# Internal setup (runs once at import)
# ---------------------------------------------------------------------------
_initialized = False

def _setup_root_logger() -> None:
    global _initialized
    if _initialized:
        return
    _initialized = True

    os.makedirs(LOG_DIR, exist_ok=True)

    today    = datetime.now().strftime("%Y%m%d")
    log_file = os.path.join(LOG_DIR, f"wbgt_monitor_{today}.log")

    formatter = logging.Formatter(_LOG_FORMAT, datefmt=_DATE_FORMAT)

    # ── File handler (daily rotating, keep 30 days) ──────────────────────────
    file_handler = TimedRotatingFileHandler(
        filename    = log_file,
        when        = "midnight",
        interval    = 1,
        backupCount = 30,
        encoding    = "utf-8",
        utc         = False,
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(logging.DEBUG)
    file_handler.suffix = "%Y%m%d"

    # ── Console handler (INFO and above) ─────────────────────────────────────
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    console_handler.setLevel(logging.INFO)

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)

    # Avoid adding duplicate handlers if re-imported
    if not root.handlers:
        root.addHandler(file_handler)
        root.addHandler(console_handler)

    root.info("=" * 60)
    root.info("WBGT Monitor logging started")
    root.info(f"Log file : {os.path.abspath(log_file)}")
    root.info("=" * 60)


def get_logger(name: str) -> logging.Logger:
    """
    Return a named logger. Call this at the top of every module:
        log = get_logger(__name__)
    """
    _setup_root_logger()
    return logging.getLogger(name)

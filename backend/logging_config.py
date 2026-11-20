"""Application logging configuration."""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

LOG_DIR = Path(__file__).resolve().parent.parent / "logs"


def setup_logging() -> logging.Logger:
    level_name = os.getenv("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)

    log_file = LOG_DIR / "erp-viewer.log"

    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    root = logging.getLogger("erp_viewer")
    root.setLevel(level)
    root.handlers.clear()

    # Windows consoles default to cp1252; never crash on non-ASCII log text.
    try:
        sys.stdout.reconfigure(errors="replace")
    except (AttributeError, ValueError):
        pass
    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(fmt)
    root.addHandler(console)

    # File logs are optional (read-only / ephemeral hosting filesystems).
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setFormatter(fmt)
        root.addHandler(file_handler)
        root.info("Logging initialized -> %s", log_file)
    except OSError:
        root.info("Logging to console only (log directory not writable)")
    return root


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(f"erp_viewer.{name}")

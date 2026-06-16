"""Logging: rotating file log at DEBUG-or-config level under <home>/logs plus a
quieter console. Call ``setup_logging(cfg)`` once at every entry point (CLI,
tests opt out by simply not calling it)."""

from __future__ import annotations

import logging
import logging.handlers
from pathlib import Path

from .config import Config

_CONFIGURED = False


def setup_logging(cfg: Config, *, console_level: int = logging.WARNING) -> logging.Logger:
    global _CONFIGURED
    root = logging.getLogger("director")
    if _CONFIGURED:
        return root
    root.setLevel(logging.DEBUG)

    cfg.logs_dir.mkdir(parents=True, exist_ok=True)
    file_handler = logging.handlers.RotatingFileHandler(
        Path(cfg.logs_dir) / "director.log",
        maxBytes=2_000_000, backupCount=3, encoding="utf-8",
    )
    file_handler.setLevel(getattr(logging, cfg.log_level, logging.INFO))
    file_handler.setFormatter(logging.Formatter(
        "%(asctime)s %(levelname)-7s %(name)s :: %(message)s"))

    console = logging.StreamHandler()
    console.setLevel(console_level)
    console.setFormatter(logging.Formatter("%(levelname)s %(name)s: %(message)s"))

    root.addHandler(file_handler)
    root.addHandler(console)
    root.propagate = False
    _CONFIGURED = True
    return root


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(f"director.{name}")

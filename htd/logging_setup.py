"""
Diagnostics without a console: a rotating log file plus a handler for any
unhandled exception (main thread, worker threads, and the asyncio loop if any).
The log lives next to the app's settings (config.log_dir()), so the Help window
can open its folder and the user can attach it to a bug report.
"""

from __future__ import annotations

import logging
import logging.handlers
import sys
import threading
import traceback
from pathlib import Path

from . import config

LOG_NAME = "heinstruediyae.log"
_installed = False


def log_file() -> Path:
    return config.log_dir() / LOG_NAME


def install() -> Path:
    """Set up the rotating file log and catch unhandled exceptions. Safe to call once."""
    global _installed
    path = log_file()
    if _installed:
        return path
    _installed = True
    handler = logging.handlers.RotatingFileHandler(path, maxBytes=512 * 1024, backupCount=3, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s  %(levelname)s  %(name)s: %(message)s"))
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(handler)
    logging.getLogger("htd").info("%s v%s starting on %s", config.APP_NAME, config.APP_VERSION, sys.platform)

    def _hook(exc_type, exc_value, exc_tb):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_tb)
            return
        logging.getLogger("htd").critical("Unhandled exception:\n%s",
                                          "".join(traceback.format_exception(exc_type, exc_value, exc_tb)))

    sys.excepthook = _hook

    def _thread_hook(args):
        logging.getLogger("htd").critical("Unhandled exception in thread %s:\n%s", args.thread.name if args.thread else "?",
                                          "".join(traceback.format_exception(args.exc_type, args.exc_value, args.exc_traceback)))

    if hasattr(threading, "excepthook"):
        threading.excepthook = _thread_hook
    return path

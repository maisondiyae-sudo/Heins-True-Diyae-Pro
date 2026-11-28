"""
Application identity and paths (no Qt imports).

Paths work both from source and from a PyInstaller build (.exe / .app):
bundled resources live in ``sys._MEIPASS`` once frozen.
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

APP_NAME = "Heins True Diyae Pro"
ORG_NAME = "Heins True Diyae"
APP_ID = "HeinsTrueDiyae.Pro"          # Windows taskbar grouping / future installer id
APP_VERSION = "2.2.3"
APP_EDITION = "Free & Open Edition"      # free for everyone, every feature unlocked
APP_TAGLINE = "Anti-Parasite Filter, mastering and conversion"
APP_AUTHOR = "mo7amed illumyn diyae"     # author signature (header, About, README, LICENSE)
APP_COPYRIGHT = "© 2026 mo7amed illumyn diyae"


def resource_dir() -> Path:
    """Folder that contains ``assets/`` (and ``bin/`` in a packaged build)."""
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))
    return Path(__file__).resolve().parent.parent


def asset(name: str) -> Path:
    return resource_dir() / "assets" / name


def app_data_dir() -> Path:
    """Per-user folder for application files (settings live in QSettings)."""
    if os.name == "nt":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    folder = base / APP_NAME
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def default_output_dir() -> Path:
    music = Path.home() / "Music"
    return (music if music.is_dir() else Path.home()) / APP_NAME


def log_dir() -> Path:
    """Folder for the rotating error log (shown by the Help window)."""
    folder = app_data_dir() / "logs"
    folder.mkdir(parents=True, exist_ok=True)
    return folder


_SESSION_DIR: Path | None = None


def session_work_dir() -> Path:
    """Temporary folder for this run (master caches, previews); removed on exit."""
    global _SESSION_DIR
    if _SESSION_DIR is None:
        root = Path(tempfile.gettempdir()) / "HeinsTrueDiyaePro"
        root.mkdir(parents=True, exist_ok=True)
        _purge_old_sessions(root)
        _SESSION_DIR = root / f"session-{os.getpid()}-{int(time.time())}"
        _SESSION_DIR.mkdir(parents=True, exist_ok=True)
    return _SESSION_DIR


def cleanup_session() -> None:
    if _SESSION_DIR is not None:
        shutil.rmtree(_SESSION_DIR, ignore_errors=True)


def _purge_old_sessions(root: Path, max_age_s: float = 24 * 3600) -> None:
    """Remove leftovers of sessions that crashed more than a day ago, and of sessions
    whose process is gone (a force-killed instance leaves its render cache behind)."""
    now = time.time()
    for child in root.glob("session-*"):
        try:
            stale = now - child.stat().st_mtime > max_age_s
            if stale or not _session_owner_alive(child.name):
                shutil.rmtree(child, ignore_errors=True)
        except OSError:
            pass


def _session_owner_alive(name: str) -> bool:
    """Whether the PID in ``session-<pid>-<time>`` is still running."""
    if os.name == "nt":  # Signal 0 is CTRL_C_EVENT on Windows, not an existence probe.
        return True
    try:
        pid = int(name.split("-")[1])
    except (IndexError, ValueError):
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:                 # exists, owned by someone else
        return True
    return True

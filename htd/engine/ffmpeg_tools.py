"""
Cross-platform FFmpeg discovery.

A desktop app cannot rely on PATH alone: on macOS, apps launched from the Finder
do not see Homebrew's /opt/homebrew/bin, and on Windows FFmpeg is often
installed by winget, Chocolatey or Scoop in folders that are not on PATH for
GUI programs. Search order:

1. the ``HTD_FFMPEG`` environment variable (explicit override);
2. a binary bundled with the app: ``<resources>/bin/ffmpeg(.exe)`` (for the
   future .exe / .app builds);
3. PATH;
4. the usual install locations for Windows and macOS;
5. the ``imageio-ffmpeg`` package (``pip install imageio-ffmpeg``), which ships
   a ready-made FFmpeg binary for Windows, macOS and Linux.

Each candidate is checked by actually running ``ffmpeg -version``.
"""

from __future__ import annotations

import glob
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import FrozenSet, Iterator, Optional, Tuple

from .core import SUBPROCESS_FLAGS, set_ffmpeg_resolver

EXE_NAME = "ffmpeg.exe" if os.name == "nt" else "ffmpeg"


@dataclass(frozen=True)
class FfmpegInfo:
    path: str
    version: str
    source: str                                   # where it was found (for the status pill)
    encoders: FrozenSet[str] = field(default_factory=frozenset)

    @property
    def has_mp3(self) -> bool:
        return "libmp3lame" in self.encoders

    @property
    def has_aac(self) -> bool:
        return "aac" in self.encoders or "aac_at" in self.encoders

    @property
    def video_encoder(self) -> Optional[str]:
        """Best available H.264 encoder for the vertical social-media video (or None)."""
        for name in ("libx264", "h264_videotoolbox", "h264_mf", "mpeg4"):
            if name in self.encoders:
                return name
        return None

    @property
    def short_version(self) -> str:
        match = re.match(r"n?(\d+(?:\.\d+)*)", self.version)
        return match.group(1) if match else self.version[:12]


def _resource_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))
    return Path(__file__).resolve().parents[2]


def _platform_candidates() -> Iterator[Tuple[str, Path]]:
    home = Path.home()
    if os.name == "nt":
        local = Path(os.environ.get("LOCALAPPDATA", home / "AppData" / "Local"))
        program_files = [Path(os.environ.get(name, "")) for name in
                         ("ProgramFiles", "ProgramFiles(x86)", "ProgramW6432") if os.environ.get(name)]
        yield "winget", local / "Microsoft" / "WinGet" / "Links" / EXE_NAME
        for match in sorted(glob.glob(str(local / "Microsoft" / "WinGet" / "Packages" / "*FFmpeg*"
                                          / "**" / "bin" / EXE_NAME), recursive=True)):
            yield "winget", Path(match)
        yield "Chocolatey", Path(os.environ.get("ChocolateyInstall", r"C:\ProgramData\chocolatey")) / "bin" / EXE_NAME
        yield "Scoop", home / "scoop" / "shims" / EXE_NAME
        yield "C:\\ffmpeg", Path(r"C:\ffmpeg\bin") / EXE_NAME
        for base in program_files:
            yield "Program Files", base / "ffmpeg" / "bin" / EXE_NAME
    elif sys.platform == "darwin":
        yield "Homebrew", Path("/opt/homebrew/bin/ffmpeg")       # Apple Silicon
        yield "Homebrew", Path("/usr/local/bin/ffmpeg")          # Intel
        yield "MacPorts", Path("/opt/local/bin/ffmpeg")
        yield "~/bin", home / "bin" / "ffmpeg"
    else:
        yield "/usr/bin", Path("/usr/bin/ffmpeg")
        yield "/usr/local/bin", Path("/usr/local/bin/ffmpeg")
        yield "snap", Path("/snap/bin/ffmpeg")


def candidate_paths() -> Iterator[Tuple[str, Path]]:
    """Every place FFmpeg might be, in priority order, as ``(source label, path)``."""
    override = os.environ.get("HTD_FFMPEG")
    if override:
        yield "HTD_FFMPEG", Path(override)
    yield "bundled", _resource_dir() / "bin" / EXE_NAME
    on_path = shutil.which("ffmpeg")
    if on_path:
        yield "PATH", Path(on_path)
    yield from _platform_candidates()
    try:
        import imageio_ffmpeg  # type: ignore

        yield "imageio-ffmpeg", Path(imageio_ffmpeg.get_ffmpeg_exe())
    except Exception:  # noqa: BLE001 - optional dependency
        pass


def _run(args, timeout: float = 15.0) -> subprocess.CompletedProcess:
    return subprocess.run(args, capture_output=True, timeout=timeout, check=False,
                          creationflags=SUBPROCESS_FLAGS)


def probe(path: Path, source: str) -> Optional[FfmpegInfo]:
    """Run the binary to confirm it is a working FFmpeg; collect its version and encoders."""
    try:
        if not path.is_file():
            return None
        result = _run([str(path), "-hide_banner", "-version"])
        if result.returncode != 0:
            return None
        first = result.stdout.decode("utf-8", "replace").splitlines()[0] if result.stdout else ""
        match = re.search(r"ffmpeg version (\S+)", first)
        version = match.group(1) if match else "unknown"
        listing = _run([str(path), "-hide_banner", "-encoders"])
        encoders = set()
        for line in listing.stdout.decode("utf-8", "replace").splitlines():
            parts = line.split()
            if len(parts) >= 2 and len(parts[0]) == 6 and parts[0][0] in "AV":
                encoders.add(parts[1])
        return FfmpegInfo(str(path), version, source, frozenset(encoders))
    except (OSError, subprocess.SubprocessError, IndexError):
        return None


_cached: Optional[FfmpegInfo] = None
_searched = False


def locate_ffmpeg(refresh: bool = False) -> Optional[FfmpegInfo]:
    """The first working FFmpeg found (cached), or None."""
    global _cached, _searched
    if _searched and not refresh:
        return _cached
    _cached = None
    seen = set()
    for source, path in candidate_paths():
        key = str(path).lower() if os.name == "nt" else str(path)
        if key in seen:
            continue
        seen.add(key)
        info = probe(path, source)
        if info is not None:
            _cached = info
            break
    _searched = True
    return _cached


def install_resolver() -> Optional[FfmpegInfo]:
    """Locate FFmpeg and make the engine's M4A decoder use it."""
    info = locate_ffmpeg()
    set_ffmpeg_resolver(lambda: _cached.path if _cached else None)
    return info


def require_ffmpeg() -> FfmpegInfo:
    info = locate_ffmpeg()
    if info is None:
        raise RuntimeError(
            "FFmpeg was not found. Install it (macOS: 'brew install ffmpeg', "
            "Windows: 'winget install Gyan.FFmpeg') or run 'pip install imageio-ffmpeg', "
            "then restart the app."
        )
    return info

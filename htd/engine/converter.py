"""
Batch audio converter: FFmpeg only, no mastering.

Each file is converted by one FFmpeg process. Progress comes from FFmpeg's
``-progress`` output; the duration is read beforehand from FFmpeg's own
header dump (so it works with builds that have no ffprobe, like imageio-ffmpeg).
"""

from __future__ import annotations

import os
import re
import subprocess
import tempfile
import threading
from pathlib import Path
from typing import Callable, Dict, List, Optional

from .core import SUBPROCESS_FLAGS
from .export import FORMATS, clean_stem, unique_path
from .tags import CLEAN_CONTAINER_ARGS

SAMPLE_RATES: Dict[str, Optional[int]] = {
    "Keep original": None,
    "44.1 kHz": 44_100,
    "48 kHz": 48_000,
    "96 kHz": 96_000,
}

# Anything FFmpeg can read; video containers are accepted and only their audio is kept.
INPUT_EXTENSIONS = ("wav", "mp3", "m4a", "flac", "ogg", "oga", "opus", "aiff", "aif", "aac",
                    "wma", "alac", "mp4", "mov", "m4v", "webm", "mkv")

_DURATION = re.compile(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)")


class ConversionError(Exception):
    """A file could not be converted (message is user-facing)."""


class ConversionCancelled(Exception):
    """The user stopped the batch."""


def codec_args(fmt_key: str, sample_rate: Optional[int]) -> List[str]:
    """FFmpeg output options for each format."""
    rate = ["-ar", str(sample_rate)] if sample_rate else []
    if fmt_key == "wav24":
        return ["-c:a", "pcm_s24le", *rate]
    if fmt_key == "wav16":
        resample = f"aresample={sample_rate}:" if sample_rate else "aresample="
        return ["-af", resample + "dither_method=triangular", "-c:a", "pcm_s16le"]
    if fmt_key == "mp3":
        return ["-c:a", "libmp3lame", "-b:a", "320k", *rate]
    if fmt_key == "flac":
        return ["-c:a", "flac", "-compression_level", "8", *rate]
    if fmt_key == "m4a":
        return ["-c:a", "aac", "-b:a", "256k", "-movflags", "+faststart", *rate]
    raise ConversionError(f"Unknown format '{fmt_key}'.")


def output_path(source: Path, fmt_key: str, out_dir: Optional[Path]) -> Path:
    folder = out_dir if out_dir is not None else source.parent
    target = folder / f"{clean_stem(source.name)}.{FORMATS[fmt_key].ext}"
    if target.resolve() == source.resolve() or target.exists():
        target = folder / f"{clean_stem(source.name)} (converted).{FORMATS[fmt_key].ext}"
    return unique_path(target)


def probe_duration(ffmpeg: str, source: Path) -> Optional[float]:
    """Duration in seconds, read from ``ffmpeg -i`` (no ffprobe needed)."""
    try:
        result = subprocess.run([ffmpeg, "-hide_banner", "-nostdin", "-i", str(source)],
                                capture_output=True, timeout=60, check=False,
                                creationflags=SUBPROCESS_FLAGS)
    except (OSError, subprocess.SubprocessError):
        return None
    match = _DURATION.search(result.stderr.decode("utf-8", "replace"))
    if not match:
        return None
    hours, minutes, seconds = match.groups()
    total = int(hours) * 3600 + int(minutes) * 60 + float(seconds)
    return total if total > 0 else None


def convert_file(ffmpeg: str, source: Path, fmt_key: str, sample_rate: Optional[int],
                 out_dir: Optional[Path],
                 progress: Optional[Callable[[float], None]] = None,
                 cancel: Optional[threading.Event] = None) -> Path:
    """Convert one file; returns the written path. Raises ConversionError / ConversionCancelled."""
    if not source.is_file():
        raise ConversionError("The file no longer exists.")
    destination = output_path(source, fmt_key, out_dir)
    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = destination.with_name(f".{destination.stem}.partial{destination.suffix}")
    duration = probe_duration(ffmpeg, source)

    args = [ffmpeg, "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
            "-i", str(source), "-map", "0:a:0", "-vn", *CLEAN_CONTAINER_ARGS,
            *codec_args(fmt_key, sample_rate),
            "-progress", "pipe:1", "-nostats", str(partial)]
    with tempfile.TemporaryFile() as errors:
        process = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=errors,
                                   stdin=subprocess.DEVNULL, creationflags=SUBPROCESS_FLAGS)
        try:
            for raw in process.stdout:
                if cancel is not None and cancel.is_set():
                    process.kill()
                    process.wait()
                    raise ConversionCancelled()
                line = raw.decode("utf-8", "replace").strip()
                if duration and progress and line.startswith(("out_time_us=", "out_time_ms=")):
                    try:
                        microseconds = int(line.split("=", 1)[1])
                    except ValueError:
                        continue
                    progress(min(max(microseconds / 1e6 / duration, 0.0), 0.999))
            process.wait()
        except BaseException:
            if process.poll() is None:
                process.kill()
                process.wait()
            _silent_remove(partial)
            raise
        if process.returncode != 0:
            errors.seek(0)
            message = errors.read().decode("utf-8", "replace").strip()
            _silent_remove(partial)
            raise ConversionError(message[-400:] or f"FFmpeg exit code {process.returncode}")
    os.replace(partial, destination)
    if progress:
        progress(1.0)
    return destination


def _silent_remove(path: Path) -> None:
    try:
        path.unlink()
    except OSError:
        pass

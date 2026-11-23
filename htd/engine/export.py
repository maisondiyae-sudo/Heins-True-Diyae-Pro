"""
Export formats for mastered tracks.

Masters are kept as 32-bit float WAV caches; an export turns that cache into
the chosen delivery format:

* WAV 24-bit   - identical to the web version's download (core.encode_wav);
* WAV 16-bit   - TPDF-dithered to 16 bits (CD / distribution);
* FLAC 24-bit  - lossless, written by libsndfile;
* MP3 320 kbps - FFmpeg + LAME (CBR 320);
* M4A          - FFmpeg AAC 256 kbps.
"""

from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional

import numpy as np
import soundfile as sf

from .core import SUBPROCESS_FLAGS, encode_wav
from .tags import CLEAN_CONTAINER_ARGS, TagSet, cover_inputs, metadata_args, retag_copy


@dataclass(frozen=True)
class ExportFormat:
    key: str
    label: str
    ext: str
    needs_ffmpeg: bool
    lossy: bool


FORMATS: Dict[str, ExportFormat] = {
    fmt.key: fmt
    for fmt in (
        ExportFormat("wav24", "WAV 24-bit", "wav", False, False),
        ExportFormat("wav16", "WAV 16-bit (dithered)", "wav", False, False),
        ExportFormat("mp3", "MP3 320 kbps", "mp3", True, True),
        ExportFormat("flac", "FLAC 24-bit", "flac", False, False),
        ExportFormat("m4a", "M4A (AAC 256 kbps)", "m4a", True, True),
    )
}
DEFAULT_FORMAT = "wav24"

_INVALID = re.compile(r'[<>:"/\\|?*\x00-\x1f]+')


class ExportError(Exception):
    """An export could not be written (message is user-facing)."""


def clean_stem(name: str) -> str:
    """A file-system-safe stem that keeps accents and spaces (Windows + macOS rules)."""
    stem = _INVALID.sub("_", Path(name).stem).strip(" ._")
    if stem.upper() in {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)),
                        *(f"LPT{i}" for i in range(1, 10))}:
        stem = f"_{stem}"
    return (stem or "track")[:120]


def unique_path(path: Path) -> Path:
    """``path`` if free, otherwise ``name_2.ext``, ``name_3.ext``..."""
    if not path.exists():
        return path
    for index in range(2, 10_000):
        candidate = path.with_name(f"{path.stem}_{index}{path.suffix}")
        if not candidate.exists():
            return candidate
    raise ExportError(f"Could not find a free file name next to {path}.")


def _ffmpeg_encode(ffmpeg: str, source: Path, destination: Path, codec_args,
                   tags: Optional[TagSet] = None, fmt_key: str = "") -> None:
    extra_inputs, cover_map = cover_inputs(tags, fmt_key)
    tag_args = metadata_args(tags, fmt_key) if tags is not None else []
    args = [ffmpeg, "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
            "-i", str(source), *extra_inputs, "-map", "0:a:0", *cover_map, *codec_args,
            *CLEAN_CONTAINER_ARGS, *tag_args, str(destination)]
    result = subprocess.run(args, capture_output=True, timeout=1800, check=False,
                            creationflags=SUBPROCESS_FLAGS)
    if result.returncode != 0:
        message = result.stderr.decode("utf-8", "replace").strip()[-400:]
        raise ExportError(f"FFmpeg could not encode the file: {message or result.returncode}")


def _tpdf_int16(audio: np.ndarray, seed: int = 0x16B17) -> np.ndarray:
    """Float -> 16-bit PCM with TPDF dither (+/-1 LSB), rounding and clipping."""
    rng = np.random.default_rng(seed)
    out = np.empty(audio.shape, dtype=np.int16)
    block = 1 << 20
    for start in range(0, audio.shape[0], block):
        chunk = audio[start:start + block].astype(np.float64) * 32767.0
        chunk += rng.random(chunk.shape) - rng.random(chunk.shape)
        np.rint(chunk, out=chunk)
        np.clip(chunk, -32768.0, 32767.0, out=chunk)
        out[start:start + block] = chunk.astype(np.int16)
    return out


def write_format(master_cache: Path, fmt_key: str, destination: Path,
                 ffmpeg: Optional[str] = None, tags: Optional[TagSet] = None) -> Path:
    """
    Write ``master_cache`` (float WAV) to ``destination`` in ``fmt_key``, with tags
    and cover when ``tags`` is given (WAV / FLAC tags need FFmpeg; without it the
    file is written untagged). The file is written under a temporary name and
    renamed when complete.
    """
    fmt = FORMATS[fmt_key]
    if fmt.needs_ffmpeg and not ffmpeg:
        raise ExportError(f"{fmt.label} export needs FFmpeg, which was not found.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = destination.with_name(f".{destination.stem}.partial{destination.suffix}")
    try:
        if fmt_key in ("wav24", "wav16", "flac"):
            audio, sample_rate = sf.read(str(master_cache), dtype="float32", always_2d=True)
            if fmt_key == "wav24":
                partial.write_bytes(encode_wav(audio, sample_rate))
            elif fmt_key == "wav16":
                sf.write(str(partial), _tpdf_int16(audio), sample_rate, subtype="PCM_16", format="WAV")
            else:
                limit = 1.0 - 2.0 ** -23
                sf.write(str(partial), np.clip(audio, -limit, limit), sample_rate,
                         subtype="PCM_24", format="FLAC")
            del audio
            # WAV / FLAC: tag only when the user asked for it. With nothing to write the
            # raw PCM / FLAC that soundfile produced is kept as is (100% blank container).
            if ffmpeg and tags is not None and not tags.is_empty():
                tagged = partial.with_name(partial.stem + ".tagged" + partial.suffix)
                try:
                    retag_copy(ffmpeg, partial, tagged, tags, "flac" if fmt_key == "flac" else "wav")
                    os.replace(tagged, partial)
                finally:
                    _silent_remove(tagged)
        elif fmt_key == "mp3":
            _ffmpeg_encode(ffmpeg, master_cache, partial, ["-c:a", "libmp3lame", "-b:a", "320k"],
                           tags, "mp3")
        elif fmt_key == "m4a":
            _ffmpeg_encode(ffmpeg, master_cache, partial,
                           ["-c:a", "aac", "-b:a", "256k", "-movflags", "+faststart"], tags, "m4a")
        else:
            raise ExportError(f"Unknown export format '{fmt_key}'.")
        os.replace(partial, destination)
    except ExportError:
        _silent_remove(partial)
        raise
    except RuntimeError as exc:                      # FFmpeg error from the tag writer
        _silent_remove(partial)
        raise ExportError(str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        _silent_remove(partial)
        raise ExportError(f"Export failed: {exc}") from exc
    return destination


def _silent_remove(path: Path) -> None:
    try:
        path.unlink()
    except OSError:
        pass

"""
Listening previews (16-bit WAV files) and Gain Match.

``generate_player_audio`` is the algorithm that fixed the crackling web
player: x 0.95, strict clip, 16-bit PCM, written to a real file on disk; the
16-bit conversion now rounds with a TPDF dither (like the WAV 16-bit export)
instead of truncating, so quiet passages and fades stay clean.
Previews are for listening only; exports never use them.
"""

from __future__ import annotations

import math
import tempfile
from pathlib import Path
from typing import Optional, Tuple

import numpy as np
from scipy.io import wavfile

from .core import db_to_lin

PLAYER_TRIM = 0.95


def generate_player_audio(audio_data: np.ndarray, sr: int, gain_db: float = 0.0,
                          directory: Optional[Path] = None) -> Path:
    """
    Browser/desktop-safe 16-bit WAV preview, written to a temporary file.

    0. optional preview-only gain (Gain Match), ``gain_db`` (0 = unchanged);
    1. global level reduced slightly: ``audio_data * 0.95``;
    2. strict clip + 16-bit PCM, rounded with a +/-1 LSB TPDF dither (chunked, low memory);
    3. written with ``scipy.io.wavfile.write`` to a ``tempfile.NamedTemporaryFile``;
    4. returns the file path.
    """
    data = np.asarray(audio_data, dtype=np.float32)
    if data.ndim == 2 and data.shape[1] == 1:
        data = data[:, 0]
    if not np.isfinite(data).all():
        data = np.nan_to_num(data, nan=0.0, posinf=0.0, neginf=0.0)
    safe_audio = data * PLAYER_TRIM
    if gain_db:
        safe_audio = safe_audio * np.float32(db_to_lin(gain_db))
    pcm16 = _to_pcm16(safe_audio)
    tmp_file = tempfile.NamedTemporaryFile(
        delete=False, suffix=".wav", dir=str(directory) if directory else None
    )
    tmp_file.close()  # required on Windows before writing to the same path
    wavfile.write(tmp_file.name, int(sr), pcm16)
    return Path(tmp_file.name)


def _to_pcm16(audio: np.ndarray, chunk: int = 1 << 20) -> np.ndarray:
    """float -> int16: clip, scale, TPDF dither, round (reproducible noise, in chunks)."""
    rng = np.random.default_rng(0x485444)
    out = np.empty(audio.shape, dtype=np.int16)
    for start in range(0, audio.shape[0], chunk):
        block = np.clip(audio[start:start + chunk], -1.0, 1.0) * np.float32(32767.0)
        block = block + (rng.random(block.shape, dtype=np.float32) - rng.random(block.shape, dtype=np.float32))
        out[start:start + chunk] = np.clip(np.rint(block), -32768, 32767).astype(np.int16)
    return out


def gain_match_offsets(original_lufs: float, mastered_lufs: float) -> Optional[Tuple[float, float]]:
    """
    Preview gains ``(original_db, master_db)`` that put both players at the same LUFS.

    The louder version is turned down to the quieter one (never up, so nothing
    can clip). ``None`` when a loudness could not be measured.
    """
    if not (math.isfinite(original_lufs) and math.isfinite(mastered_lufs)):
        return None
    difference = mastered_lufs - original_lufs   # > 0 when the master is louder (usual case)
    # master quieter -> lower the original by |difference|; master louder -> lower the master
    return (difference, 0.0) if difference < 0 else (0.0, -difference)


def read_preview(path: Path) -> Tuple[np.ndarray, int]:
    """Read a 16-bit preview back as float32, undoing the 0.95 player trim."""
    sample_rate, pcm = wavfile.read(str(path))
    audio = pcm.astype(np.float32) / (32767.0 * PLAYER_TRIM)
    return audio, int(sample_rate)

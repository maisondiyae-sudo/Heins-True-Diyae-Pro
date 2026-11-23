"""
Listening buffers for the preview player (v2.0.1).

The player (PortAudio, see audio_output.py) plays float32 buffers that are
already at the sound card's own rate, so nothing is resampled, re-encoded or
dithered on the way out:

* master:   from the 32-bit float master cache (best quality)
* original: decoded straight from the source file, so it can be heard as soon
            as the track is in the list (before any rendering)

each resampled once, offline, with a high-quality polyphase filter (Kaiser 8.6,
images / aliases below -90 dB), times PLAYER_TRIM (0.95) of headroom. Gain
Match and Mono are applied live by the player (``gain_db`` gives the gain), so
switching them never needs a new file.

Buffers are kept
    on disk    as .npy: the master's next to its cache (deleted with the mode),
               the original's in the session folder (shared by every mode);
    in memory  for the tracks being listened to (LRU, MEMORY_LIMIT bytes).
``load`` / ``prepare`` run in worker threads (~0.3 s to build a 3-minute
track, ~0.1 s to reload it from disk); ``cached`` is instant (memory only).
"""

from __future__ import annotations

import hashlib
import math
import threading
from collections import OrderedDict
from pathlib import Path
from typing import Dict, Optional, Tuple, Union

import numpy as np
import scipy.signal as sps
import soundfile as sf

from .. import config
from ..engine import core
from ..engine.core import INTERNAL_SR
from ..engine.pipeline import TrackResult
from ..engine.preview import PLAYER_TRIM, gain_match_offsets
from .audio_output import PlayBuffer

MEMORY_LIMIT = 1024 * 1024 * 1024        # ~1 GB of buffers in memory (about 13 minutes of audio at 48 kHz)

_memory: "OrderedDict[tuple, PlayBuffer]" = OrderedDict()
_memory_lock = threading.Lock()
_build_locks: Dict[tuple, threading.Lock] = {}


def gain_db(result: TrackResult, which: str, gain_match: bool) -> float:
    """Gain Match: the louder version is turned down to the other one's loudness."""
    if not gain_match:
        return 0.0
    offsets = gain_match_offsets(result.original_metrics.lufs, result.mastered_metrics.lufs)
    if offsets is None:
        return 0.0
    return offsets[0] if which == "original" else offsets[1]


def resample(audio: np.ndarray, source_rate: int, target_rate: int) -> np.ndarray:
    """High-quality polyphase resampling (Kaiser 8.6: images / aliases below -90 dB)."""
    if int(source_rate) == int(target_rate):
        return audio
    divisor = math.gcd(int(source_rate), int(target_rate))
    up, down = int(target_rate) // divisor, int(source_rate) // divisor
    return sps.resample_poly(audio, up, down, axis=0, window=("kaiser", 8.6)).astype(np.float32, copy=False)


class Original:
    """The original of a track, before (or without) any rendering: only its source file."""

    def __init__(self, source: Path) -> None:
        self.source = Path(source)


Item = Union[TrackResult, Original]


def _source_id(item: Item) -> str:
    """Identity of the source file (the original sounds the same in every mode)."""
    try:
        stat = item.source.stat()
        text = f"{item.source.resolve()}|{stat.st_size}|{stat.st_mtime_ns}"
    except OSError:
        text = str(item.source)
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:16]


def item_id(item: Item, which: str) -> tuple:
    """Identity of a buffer whatever the rate (to avoid loading it twice at once)."""
    if which == "original":
        return ("original", _source_id(item))
    return ("mastered", str(item.master_cache))


def _key(item: Item, which: str, rate: int) -> tuple:
    if which == "original":
        return ("original", _source_id(item), int(rate))
    return ("mastered", str(item.master_cache), int(rate))


def _disk_path(item: Item, which: str, rate: int) -> Path:
    if which == "original":
        folder = config.session_work_dir() / "playback"
        folder.mkdir(parents=True, exist_ok=True)
        return folder / f"original-{_source_id(item)}-{int(rate)}.npy"
    return Path(item.work_dir) / f"play-master-{int(rate)}.npy"


def _offset(item: Item, which: str, rate: int) -> int:
    """Where the buffer starts on the original's timeline (frames at ``rate``)."""
    if which == "mastered":
        return int(round(item.master_offset_samples() * int(rate) / float(INTERNAL_SR)))
    return 0


def _build(item: Item, which: str, rate: int) -> np.ndarray:
    if which == "mastered":
        audio, source_rate = sf.read(str(item.master_cache), dtype="float32", always_2d=True)
    else:                                         # the whole source, decoded like the engine does
        decoded = core.load_audio(Path(item.source).read_bytes(), Path(item.source).name)
        audio, source_rate = np.asarray(decoded.samples, dtype=np.float32), decoded.sample_rate
        del decoded
    if audio.ndim == 1:
        audio = audio[:, None]
    if audio.shape[1] == 1:
        audio = np.repeat(audio, 2, axis=1)
    audio = np.nan_to_num(audio[:, :2], nan=0.0, posinf=0.0, neginf=0.0) * np.float32(PLAYER_TRIM)
    return np.ascontiguousarray(resample(audio, source_rate, rate), dtype=np.float32)


def duration_s(item: Item, rate: int) -> float:
    """Length of the original's disk copy (cheap: reads only the .npy header)."""
    path = _disk_path(item, "original", rate)
    try:
        return float(np.load(path, mmap_mode="r").shape[0]) / float(rate)
    except (OSError, ValueError):
        return 0.0


def _remember(key: tuple, buffer: PlayBuffer) -> None:
    with _memory_lock:
        _memory[key] = buffer
        _memory.move_to_end(key)
        total = sum(item.audio.nbytes for item in _memory.values())
        while total > MEMORY_LIMIT and len(_memory) > 1:
            _old_key, old = _memory.popitem(last=False)
            total -= old.audio.nbytes


def cached(result: Item, which: str, rate: int) -> Optional[PlayBuffer]:
    """The buffer if it is in memory (instant), else None."""
    key = _key(result, which, rate)
    with _memory_lock:
        buffer = _memory.get(key)
        if buffer is not None:
            _memory.move_to_end(key)
        return buffer


def _make_disk_copy(result: Item, which: str, rate: int) -> Tuple[Path, Optional[np.ndarray]]:
    path = _disk_path(result, which, rate)
    key = _key(result, which, rate)
    with _memory_lock:
        lock = _build_locks.setdefault(key, threading.Lock())
    with lock:                                   # one thread builds a given buffer
        if path.exists():
            return path, None
        audio = _build(result, which, rate)
        partial = path.with_name(path.stem + ".partial.npy")
        np.save(partial, audio)
        partial.replace(path)
        return path, audio


def prepare(result: Item, which: str, rate: int) -> Path:
    """Make sure the disk copy exists (background, right after rendering)."""
    return _make_disk_copy(result, which, rate)[0]


def load(result: Item, which: str, rate: int) -> PlayBuffer:
    """The buffer to play (memory, else disk, else built). Call it from a worker thread."""
    buffer = cached(result, which, rate)
    if buffer is not None:
        return buffer
    path, audio = _make_disk_copy(result, which, rate)
    if audio is None:
        audio = np.load(path)
    buffer = PlayBuffer(audio, int(rate), _offset(result, which, rate))
    _remember(_key(result, which, rate), buffer)
    return buffer


def forget(result: TrackResult) -> None:
    """A mode was deleted: drop its master from memory (its files go with its work folder)."""
    with _memory_lock:
        for key in [k for k in _memory if k[0] == "mastered" and k[1] == str(result.master_cache)]:
            del _memory[key]


def forget_source(result: Item) -> None:
    """A track left the list: drop its original from memory and disk."""
    source = _source_id(result)
    with _memory_lock:
        for key in [k for k in _memory if k[0] == "original" and k[1] == source]:
            del _memory[key]
    folder = config.session_work_dir() / "playback"
    for path in folder.glob(f"original-{source}-*.npy"):
        try:
            path.unlink()
        except OSError:
            pass

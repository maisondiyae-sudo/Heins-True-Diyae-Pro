"""
Auto-trim: remove the silence before the first sound and after the last one,
then apply micro-fades (anti-click) at both ends.

* detection on 5 ms peak frames, all channels, threshold in dBFS;
* a short pre-roll is kept before the first sound and the fade-in happens
  inside it, so the first transient is never softened;
* a short tail is kept after the last sound before the fade-out;
* raised-cosine fades (smooth start and end of the gain curve).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple

import numpy as np

FRAME_MS = 5.0


@dataclass(frozen=True)
class TrimReport:
    start_s: float = 0.0          # silence removed at the start
    end_s: float = 0.0            # silence removed at the end
    offset_samples: int = 0       # where the trimmed audio starts in the untrimmed timeline

    @property
    def changed(self) -> bool:
        return self.start_s > 0 or self.end_s > 0


def _ramp(length: int) -> np.ndarray:
    """Raised-cosine fade-in curve of ``length`` samples (0 -> 1)."""
    if length <= 0:
        return np.ones(0, dtype=np.float32)
    x = (np.arange(length, dtype=np.float64) + 0.5) / length
    return (0.5 - 0.5 * np.cos(np.pi * x)).astype(np.float32)


def auto_trim(audio: np.ndarray, sample_rate: int, threshold_db: float = -60.0,
              pre_roll_ms: float = 10.0, tail_ms: float = 120.0,
              fade_in_ms: float = 5.0, fade_out_ms: float = 20.0) -> Tuple[np.ndarray, TrimReport]:
    """Return ``(trimmed audio, report)``; silent or empty input is returned unchanged."""
    data = np.asarray(audio, dtype=np.float32)
    if data.ndim == 1:
        data = data[:, None]
    n = data.shape[0]
    frame = max(1, int(round(sample_rate * FRAME_MS / 1000.0)))
    if n < 4 * frame:
        return data, TrimReport()

    usable = (n // frame) * frame
    peaks = np.abs(data[:usable]).max(axis=1).reshape(-1, frame).max(axis=1)
    tail_peak = float(np.abs(data[usable:]).max()) if usable < n else 0.0
    peaks = np.append(peaks, tail_peak) if usable < n else peaks
    threshold = 10.0 ** (threshold_db / 20.0)
    loud = np.flatnonzero(peaks > threshold)
    if loud.size == 0:
        return data, TrimReport()

    start = max(0, loud[0] * frame - int(sample_rate * pre_roll_ms / 1000.0))
    end = min(n, (loud[-1] + 1) * frame + int(sample_rate * tail_ms / 1000.0))
    out = data[start:end].copy()

    fade_in = min(int(sample_rate * fade_in_ms / 1000.0), out.shape[0] // 4)
    fade_out = min(int(sample_rate * fade_out_ms / 1000.0), out.shape[0] // 4)
    if fade_in:
        out[:fade_in] *= _ramp(fade_in)[:, None]
    if fade_out:
        out[-fade_out:] *= _ramp(fade_out)[::-1, None]
    report = TrimReport(start / sample_rate, (n - end) / sample_rate, int(start))
    return np.ascontiguousarray(out), report

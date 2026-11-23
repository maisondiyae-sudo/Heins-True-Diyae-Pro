"""
Manual cut (start / end), non-destructive: the source file is never touched.

The cut is applied to the decoded audio *before* the Anti-Parasite Filter and
the mastering chain, with short raised-cosine micro-fades at the edges that were
cut (5 ms in, 20 ms out) so the new start and end never click. Without a cut the
pipeline runs exactly as before (bit-identical masters).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

import numpy as np

from .trim import _ramp

MIN_LENGTH_S = 0.5
FADE_IN_MS = 5.0
FADE_OUT_MS = 20.0


@dataclass(frozen=True)
class CutReport:
    start_s: float                  # where the kept part starts in the original (s)
    end_s: float                    # where it ends (s)
    start_samples: int              # same, in samples of the decoded audio
    end_samples: int

    @property
    def length_s(self) -> float:
        return self.end_s - self.start_s


def normalise_cut(cut: Optional[Tuple[float, float]], duration_s: float) -> Optional[Tuple[float, float]]:
    """A valid (start, end) in seconds, or None when it keeps everything / is not usable."""
    if cut is None:
        return None
    start, end = float(cut[0]), float(cut[1])
    if duration_s > 0:
        start, end = max(0.0, min(start, duration_s)), max(0.0, min(end, duration_s))
    if end - start < MIN_LENGTH_S:
        return None
    if start <= 0.0 and (duration_s <= 0 or end >= duration_s):
        return None
    return round(start, 3), round(end, 3)


def apply_cut(audio: np.ndarray, sample_rate: int, start_s: float, end_s: float) -> Tuple[np.ndarray, CutReport]:
    """Keep ``[start_s, end_s)`` of ``audio`` (frames, channels), with anti-click micro-fades."""
    data = np.asarray(audio, dtype=np.float32)
    total = data.shape[0]
    start = int(round(max(0.0, start_s) * sample_rate))
    end = int(round(min(end_s, total / float(sample_rate)) * sample_rate))
    start, end = min(start, total), max(min(end, total), 0)
    if end - start < int(MIN_LENGTH_S * sample_rate):
        raise ValueError("The cut keeps less than half a second.")
    out = data[start:end].copy()
    if start > 0:
        fade = min(int(sample_rate * FADE_IN_MS / 1000.0), out.shape[0] // 4)
        out[:fade] *= _ramp(fade)[:, None]
    if end < total:
        fade = min(int(sample_rate * FADE_OUT_MS / 1000.0), out.shape[0] // 4)
        out[-fade:] *= _ramp(fade)[::-1, None]
    # the requested times identify the cut (the sample positions are the exact ones)
    report = CutReport(round(float(start_s), 3), round(min(float(end_s), total / float(sample_rate)), 3), start, end)
    return np.ascontiguousarray(out), report

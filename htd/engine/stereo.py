"""
Stereo image and phase check (mono compatibility) - numpy / scipy only.

    correlation         whole track, -1..+1 (+1 = mono, 0 = unrelated, < 0 = out of phase)
    bass_correlation    below 150 Hz, where cancellation hurts most (clubs, phones, vinyl)
    worst_correlation   5th percentile over 0.4 s windows (loud windows only): local problems
    mono_loss_db        level change when L and R are summed to mono: 0 dB for mono content,
                        about -3 dB for very wide content, much lower when parts cancel
    width_db            side / mid level: very negative = narrow, near 0 = very wide

``level``: "ok", "caution" or "risk" (risk = audible cancellation in mono is likely).
Mono files return None.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

import numpy as np
import scipy.signal as sps

BASS_HZ = 150.0
WINDOW_S = 0.4


@dataclass(frozen=True)
class StereoReport:
    correlation: float
    bass_correlation: float
    worst_correlation: float
    mono_loss_db: float
    width_db: float

    @property
    def issues(self) -> List[str]:
        """'bass', 'phase', 'mono' - what would cancel in mono."""
        found = []
        if self.bass_correlation < 0.7:
            found.append("bass")
        if self.correlation < 0.3 or self.worst_correlation < -0.2:
            found.append("phase")
        if self.mono_loss_db < -4.5:
            found.append("mono")
        return found

    @property
    def level(self) -> str:
        if (self.correlation < 0.0 or self.bass_correlation < 0.2 or self.mono_loss_db < -6.0
                or self.worst_correlation < -0.5):
            return "risk"
        return "caution" if self.issues else "ok"


def _corr(left: np.ndarray, right: np.ndarray) -> float:
    left = left - left.mean()
    right = right - right.mean()
    denominator = math.sqrt(float(np.dot(left, left)) * float(np.dot(right, right)))
    return float(np.dot(left, right) / denominator) if denominator > 1e-20 else 1.0


def _rms(x: np.ndarray) -> float:
    return math.sqrt(float(np.mean(np.square(x, dtype=np.float64)))) if x.size else 0.0


def analyse_stereo(audio: np.ndarray, sample_rate: int) -> Optional[StereoReport]:
    data = np.asarray(audio, dtype=np.float32)
    if data.ndim != 2 or data.shape[1] < 2 or data.shape[0] < sample_rate // 2:
        return None
    left, right = data[:, 0].astype(np.float64), data[:, 1].astype(np.float64)
    if _rms(left - right) < 1e-7:                       # identical channels: mono content
        return StereoReport(1.0, 1.0, 1.0, 0.0, -120.0)

    sos = sps.butter(4, BASS_HZ, btype="lowpass", fs=sample_rate, output="sos")
    bass_l, bass_r = sps.sosfilt(sos, left), sps.sosfilt(sos, right)
    bass_corr = _corr(bass_l, bass_r) if max(_rms(bass_l), _rms(bass_r)) > 1e-5 else 1.0

    size = max(1, int(WINDOW_S * sample_rate))
    count = left.size // size
    windows = []
    if count:
        lw = left[:count * size].reshape(count, size)
        rw = right[:count * size].reshape(count, size)
        energy = np.sqrt(np.mean(lw * lw + rw * rw, axis=1) / 2.0)
        loud = energy > max(1e-4, float(np.percentile(energy, 50)) * 0.25)   # skip silences / fades
        for l_win, r_win in zip(lw[loud], rw[loud]):
            windows.append(_corr(l_win, r_win))
    worst = float(np.percentile(windows, 5)) if windows else 1.0

    mid, side = (left + right) / 2.0, (left - right) / 2.0
    reference = math.sqrt((_rms(left) ** 2 + _rms(right) ** 2) / 2.0)
    mono_loss = 20.0 * math.log10(max(_rms(mid), 1e-12) / max(reference, 1e-12))
    width = 20.0 * math.log10(max(_rms(side), 1e-12) / max(_rms(mid), 1e-12))
    return StereoReport(_corr(left, right), bass_corr, worst, max(mono_loss, -120.0), min(max(width, -120.0), 120.0))


def analyse_file(path: Path) -> Optional[StereoReport]:
    import soundfile as sf

    audio, sample_rate = sf.read(str(path), dtype="float32", always_2d=True)
    return analyse_stereo(audio, sample_rate)

"""
Reference matching: give the master the tonal balance and the loudness of a
reference track.

How it plugs into the unchanged engine
--------------------------------------
1. The reference is analysed once: integrated loudness (LUFS), true peak and
   its long-term spectrum, smoothed to third-octave resolution.
2. For each track, after the Anti-Parasite Filter, the same spectrum is
   measured and the difference "reference - track" (both loudness-normalised)
   becomes a smooth correction curve, limited to +/-6 dB and scaled by the
   strength setting.
3. That curve is applied with a linear-phase FIR (no phase distortion, delay
   compensated) and the track then goes through the normal mastering chain,
   with the recipe's own EQ switched off (the match EQ replaces it) and, if
   asked, the reference loudness as the target.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

import numpy as np
import scipy.signal as sps

from .core import (
    SpectrogramData,
    compute_spectrogram,
    load_audio,
    measure_lufs,
    measure_true_peak_db,
)

CENTRES = np.geomspace(25.0, 18_000.0, 115)      # ~12 points per octave
MATCH_BAND = (60.0, 12_000.0)                    # where the match quality is judged
OFFSET_BAND = (200.0, 5_000.0)                   # level reference of the curves
MAX_CORRECTION_DB = 6.0
LOUDNESS_RANGE = (-20.0, -6.0)
FIR_TAPS = 8191                                   # ~5.4 Hz resolution at 44.1 kHz


def smoothed_spectrum_db(data: SpectrogramData, centres: np.ndarray = CENTRES) -> np.ndarray:
    """Third-octave smoothed long-term spectrum, in dB."""
    half = 2.0 ** (1.0 / 6.0)
    freqs, psd = data.average_freqs, data.average_psd
    lower = np.searchsorted(freqs, centres / half, side="left")
    upper = np.searchsorted(freqs, centres * half, side="right")
    values = np.empty(centres.size)
    for i, (lo, hi) in enumerate(zip(lower, upper)):
        values[i] = psd[lo:hi].mean() if hi - lo >= 2 else np.interp(centres[i], freqs, psd)
    return 10.0 * np.log10(np.maximum(values, 1e-30))


def _normalise(curve_db: np.ndarray) -> np.ndarray:
    """Remove the overall level so two spectra can be compared for shape only."""
    band = (CENTRES >= OFFSET_BAND[0]) & (CENTRES <= OFFSET_BAND[1])
    return curve_db - curve_db[band].mean()


def file_identity(path: Path) -> str:
    """Identity of a reference file (changes when the file is replaced or edited)."""
    stat = path.stat()
    raw = f"{path.resolve()}|{stat.st_size}|{int(stat.st_mtime)}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


@dataclass(frozen=True)
class ReferenceProfile:
    path: str
    name: str
    ident: str
    lufs: float
    true_peak_db: float
    duration_s: float
    spectrum_db: Tuple[float, ...]        # normalised shape on CENTRES

    @property
    def curve(self) -> np.ndarray:
        return np.asarray(self.spectrum_db)

    @property
    def target_lufs(self) -> float:
        return float(np.clip(self.lufs, *LOUDNESS_RANGE))


def analyse_reference(path: Path) -> ReferenceProfile:
    """Decode and measure a reference track (raises core.AudioLoadError if unreadable)."""
    audio = load_audio(path.read_bytes(), path.name)
    lufs = measure_lufs(audio.samples, audio.sample_rate)
    if not np.isfinite(lufs):
        raise ValueError("The reference track is too quiet to be measured.")
    spectrum = compute_spectrogram(audio.samples, audio.sample_rate)
    shape = _normalise(smoothed_spectrum_db(spectrum))
    return ReferenceProfile(
        path=str(path), name=path.name, ident=file_identity(path), lufs=float(lufs),
        true_peak_db=float(measure_true_peak_db(audio.samples)),
        duration_s=float(audio.duration_s), spectrum_db=tuple(float(v) for v in shape),
    )


def _tonal_difference(track: SpectrogramData, reference: ReferenceProfile) -> np.ndarray:
    """Reference minus track, smoothed over ~1/2 octave: the broad tonal balance only,
    not the note-by-note differences between two pieces of music."""
    difference = reference.curve - _normalise(smoothed_spectrum_db(track))
    kernel = np.hanning(9)[1:-1]
    kernel /= kernel.sum()
    smooth = np.convolve(np.pad(difference, (3, 3), mode="edge"), kernel, mode="valid")
    return smooth - smooth[(CENTRES >= OFFSET_BAND[0]) & (CENTRES <= OFFSET_BAND[1])].mean()


def match_curve(track: SpectrogramData, reference: ReferenceProfile,
                strength: float) -> np.ndarray:
    """Correction (dB, on CENTRES) that moves the track's tonal balance towards the reference."""
    smooth = _tonal_difference(track, reference)
    return np.clip(smooth, -MAX_CORRECTION_DB, MAX_CORRECTION_DB) * float(np.clip(strength, 0.0, 1.0))


def design_fir(curve_db: np.ndarray, sample_rate: int, taps: int = FIR_TAPS) -> np.ndarray:
    """Linear-phase FIR following ``curve_db`` (held flat outside 25 Hz - 18 kHz)."""
    nyquist = sample_rate / 2.0
    keep = CENTRES < nyquist * 0.999
    freqs = np.concatenate([[0.0], CENTRES[keep], [nyquist]])
    gains_db = np.concatenate([[curve_db[keep][0]], curve_db[keep], [curve_db[keep][-1]]])
    return sps.firwin2(taps, freqs, 10.0 ** (gains_db / 20.0), fs=sample_rate).astype(np.float64)


def apply_fir(audio: np.ndarray, fir: np.ndarray) -> np.ndarray:
    """Filter every channel; the linear-phase delay is removed so timing is unchanged."""
    delay = (fir.size - 1) // 2
    out = np.empty_like(audio)
    for channel in range(audio.shape[1]):
        filtered = sps.oaconvolve(audio[:, channel].astype(np.float64), fir, mode="full")
        out[:, channel] = filtered[delay:delay + audio.shape[0]]
    return out


def match_error_db(track: SpectrogramData, reference: ReferenceProfile) -> float:
    """Average absolute tonal-balance difference to the reference, 60 Hz - 12 kHz (dB),
    at the resolution the match EQ works with."""
    band = (CENTRES >= MATCH_BAND[0]) & (CENTRES <= MATCH_BAND[1])
    difference = _tonal_difference(track, reference)
    return float(np.abs(difference[band] - difference[band].mean()).mean())


@dataclass
class MatchReport:
    reference: str
    eq_max_boost_db: float
    eq_max_cut_db: float
    error_before_db: float
    error_after_db: Optional[float] = None
    target_lufs: Optional[float] = None

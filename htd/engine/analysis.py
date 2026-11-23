"""
Tempo (BPM) and musical key detection - numpy / scipy only.

Tempo
    Onset-strength envelope (log-magnitude spectral flux, 86 frames/s), global
    autocorrelation, then every BPM between 60 and 200 is scored with a comb of
    its multiples (1, 2, 3, 4, 6, 8 beats) times a log-normal preference
    centred on 120 BPM (the usual "tempo prior"). Half / double tempo can still
    be ambiguous on some styles (drum & bass at 174 vs 87): the BPM stays
    editable in the interface. The beat phase (time of the first beat) is also
    estimated, to cut social clips on the beat.

Key
    Harmonic-enhanced spectrogram (median filter across time removes drums),
    60 Hz - 2 kHz folded into a 12-bin chroma with cent-accurate weighting,
    averaged over the track and correlated with the 24 rotated
    Krumhansl-Kessler major / minor profiles, extended with their overtones
    (so the fifth's harmonics do not pull the result a fifth up). Relative keys (C major / A minor)
    are the usual confusion; the key stays editable too.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

import numpy as np
import scipy.fft
import scipy.signal as sps
from scipy.ndimage import median_filter, uniform_filter1d

ANALYSIS_SR = 22_050

PITCHES_MAJOR = ["C", "Db", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B"]
PITCHES_MINOR = ["C", "C#", "D", "Eb", "E", "F", "F#", "G", "G#", "A", "Bb", "B"]
# Camelot wheel codes, indexed by tonic pitch class (C = 0)
CAMELOT_MAJOR = ["8B", "3B", "10B", "5B", "12B", "7B", "2B", "9B", "4B", "11B", "6B", "1B"]
CAMELOT_MINOR = ["5A", "12A", "7A", "2A", "9A", "4A", "11A", "6A", "1A", "8A", "3A", "10A"]

# Krumhansl-Kessler key profiles (tonic first)
_MAJOR_PROFILE = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
_MINOR_PROFILE = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])


def key_short_names() -> list:
    """All 24 keys in short notation (Cm, C#m, Db...), majors first."""
    return [name for name in PITCHES_MAJOR] + [f"{name}m" for name in PITCHES_MINOR]


def describe_key(short: str) -> Tuple[str, str]:
    """'Cm' -> ('C minor', '5A'); unknown -> ('', '')."""
    if not short:
        return "", ""
    minor = short.endswith("m")
    tonic = short[:-1] if minor else short
    names = PITCHES_MINOR if minor else PITCHES_MAJOR
    if tonic not in names:
        return short, ""
    index = names.index(tonic)
    camelot = (CAMELOT_MINOR if minor else CAMELOT_MAJOR)[index]
    return f"{tonic} {'minor' if minor else 'major'}", camelot


@dataclass(frozen=True)
class TrackAnalysis:
    bpm: Optional[float]              # None when no stable pulse was found
    bpm_confidence: float             # 0..1
    beat_offset_s: Optional[float]    # time of the first beat (track timeline)
    key: str                          # short name ("Cm", "F#", ...) or ""
    key_confidence: float             # 0..1
    duration_s: float

    @property
    def bpm_int(self) -> Optional[int]:
        return int(round(self.bpm)) if self.bpm else None

    @property
    def key_long(self) -> str:
        return describe_key(self.key)[0]

    @property
    def camelot(self) -> str:
        return describe_key(self.key)[1]


def _to_analysis_mono(audio: np.ndarray, sample_rate: int) -> np.ndarray:
    mono = np.asarray(audio, dtype=np.float32)
    if mono.ndim == 2:
        mono = mono.mean(axis=1)
    if sample_rate != ANALYSIS_SR:
        divisor = math.gcd(int(sample_rate), ANALYSIS_SR)
        mono = sps.resample_poly(mono.astype(np.float64), ANALYSIS_SR // divisor,
                                 int(sample_rate) // divisor).astype(np.float32)
    return mono


def _magnitude_frames(signal: np.ndarray, n_fft: int, hop: int, max_bin: Optional[int] = None) -> np.ndarray:
    """|STFT| as (frames, bins), computed block by block to keep memory low."""
    if signal.size < n_fft:
        signal = np.pad(signal, (0, n_fft - signal.size))
    frames = np.lib.stride_tricks.sliding_window_view(signal, n_fft)[::hop]
    window = sps.get_window("hann", n_fft, fftbins=True).astype(np.float32)
    bins = n_fft // 2 + 1 if max_bin is None else max_bin
    out = np.empty((frames.shape[0], bins), dtype=np.float32)
    for start in range(0, frames.shape[0], 512):
        block = scipy.fft.rfft(frames[start:start + 512] * window, axis=1)
        out[start:start + 512] = np.abs(block[:, :bins])
    return out


# --------------------------------------------------------------------- tempo
TEMPO_HOP = 256
TEMPO_FPS = ANALYSIS_SR / TEMPO_HOP          # ~86.1 frames per second


def _band_matrix(n_bins: int, n_fft: int, bands: int = 40) -> np.ndarray:
    """Sum STFT bins into log-spaced bands (30 Hz - Nyquist), so that the many
    high-frequency bins of hi-hats do not outweigh kick and snare."""
    freqs = np.fft.rfftfreq(n_fft, 1.0 / ANALYSIS_SR)[:n_bins]
    edges = np.geomspace(30.0, ANALYSIS_SR / 2.0, bands + 1)
    matrix = np.zeros((n_bins, bands), dtype=np.float32)
    index = np.clip(np.searchsorted(edges, freqs, side="right") - 1, -1, bands - 1)
    valid = (freqs >= edges[0]) & (index >= 0)
    matrix[np.arange(n_bins)[valid], index[valid]] = 1.0
    counts = matrix.sum(axis=0)
    counts[counts == 0] = 1.0
    return matrix / counts


def onset_envelope(mono: np.ndarray) -> np.ndarray:
    """Band-wise log spectral flux, locally detrended and normalised."""
    magnitude = _magnitude_frames(mono, 1024, TEMPO_HOP)
    bands = magnitude @ _band_matrix(magnitude.shape[1], 1024)
    log_mag = np.log1p(100.0 * bands / (bands.max() + 1e-12))
    flux = np.maximum(np.diff(log_mag, axis=0), 0.0).sum(axis=1)
    flux = np.concatenate([[0.0], flux])
    flux -= uniform_filter1d(flux, size=int(TEMPO_FPS), mode="nearest")   # remove slow loudness changes
    flux = np.maximum(flux, 0.0)
    std = flux.std()
    return (flux / std).astype(np.float64) if std > 0 else flux.astype(np.float64)


def estimate_tempo(envelope: np.ndarray, min_bpm: float = 60.0, max_bpm: float = 200.0,
                   prior_bpm: float = 120.0, prior_octaves: float = 1.0) -> Tuple[Optional[float], float]:
    """BPM and confidence from an onset envelope."""
    n = envelope.size
    if n < TEMPO_FPS * 6 or not np.any(envelope):
        return None, 0.0
    x = envelope - envelope.mean()
    spectrum = scipy.fft.rfft(x, 2 * n)
    ac = scipy.fft.irfft(np.abs(spectrum) ** 2)[:n]
    if ac[0] <= 0:
        return None, 0.0
    ac /= ac[0]
    lags_axis = np.arange(n, dtype=np.float64)

    bpms = np.arange(min_bpm, max_bpm + 0.001, 0.05)
    base_lag = 60.0 * TEMPO_FPS / bpms
    harmonics = ((1, 1.0), (2, 0.8), (3, 0.5), (4, 0.7), (6, 0.4), (8, 0.5))
    score = np.zeros_like(bpms)
    for multiple, weight in harmonics:
        lag = base_lag * multiple
        valid = lag < n - 1
        score[valid] += weight * np.interp(lag[valid], lags_axis, ac)
    prior = np.exp(-0.5 * (np.log2(bpms / prior_bpm) / prior_octaves) ** 2)
    weighted = np.maximum(score, 0.0) * prior
    best = int(np.argmax(weighted))
    if weighted[best] <= 0:
        return None, 0.0
    # confidence: how much the winner stands out from the median candidate
    median = float(np.median(np.maximum(score, 0.0)))
    confidence = float(np.clip((score[best] - median) / (abs(score[best]) + 1e-9), 0.0, 1.0))
    return float(bpms[best]), confidence


def estimate_beat_offset(envelope: np.ndarray, bpm: float) -> float:
    """Time (s) of the first beat: the phase whose comb collects the most onset energy."""
    period = 60.0 * TEMPO_FPS / bpm
    axis = np.arange(envelope.size, dtype=np.float64)
    phases = np.arange(0.0, period, 0.5)
    best_phase, best_value = 0.0, -1.0
    for phase in phases:
        positions = np.arange(phase, envelope.size - 1, period)
        value = float(np.interp(positions, axis, envelope).sum())
        if value > best_value:
            best_phase, best_value = phase, value
    return best_phase / TEMPO_FPS


# ----------------------------------------------------------------------- key
KEY_NFFT = 8192
KEY_HOP = 2048
KEY_FMIN, KEY_FMAX = 60.0, 2000.0
# Overtones of a played note, as (semitones above the note, relative level):
# octave, octave + fifth, two octaves, two octaves + major third, ... (Gomez 2006).
_OVERTONES = ((0, 1.0), (12, 0.6), (19, 0.36), (24, 0.22), (28, 0.13), (31, 0.08))


def _with_overtones(profile: np.ndarray) -> np.ndarray:
    """Key profile as it appears in a spectrum: every note also lights up its overtones."""
    spectral = np.zeros(12)
    for note, weight in enumerate(profile):
        for semitones, level in _OVERTONES:
            spectral[(note + semitones) % 12] += weight * level
    return spectral


def chroma_profile(mono: np.ndarray) -> np.ndarray:
    """Average 12-bin chroma (C..B) of the harmonic part of the signal."""
    freqs = np.fft.rfftfreq(KEY_NFFT, 1.0 / ANALYSIS_SR)
    max_bin = int(np.searchsorted(freqs, KEY_FMAX)) + 1
    magnitude = _magnitude_frames(mono, KEY_NFFT, KEY_HOP, max_bin)
    if magnitude.shape[0] >= 9:                       # drums are short in time: drop them
        magnitude = median_filter(magnitude, size=(9, 1), mode="nearest")
    freqs = freqs[:max_bin]
    usable = (freqs >= KEY_FMIN) & (freqs <= KEY_FMAX)
    midi = 69.0 + 12.0 * np.log2(np.maximum(freqs, 1e-6) / 440.0)
    nearest = np.round(midi)
    cents = np.abs(midi - nearest) * 100.0
    weight = np.where(usable, np.clip(1.0 - cents / 50.0, 0.0, 1.0), 0.0)
    pitch_class = (nearest.astype(int) % 12)
    mapping = np.zeros((magnitude.shape[1], 12), dtype=np.float32)
    mapping[np.arange(magnitude.shape[1]), pitch_class] = weight
    compressed = np.log1p(1000.0 * magnitude / (magnitude.max() + 1e-12))
    chroma = compressed @ mapping                                   # (frames, 12)
    energy = chroma.sum(axis=1)
    active = energy > 0.1 * (energy.max() + 1e-12)
    if not np.any(active):
        return np.zeros(12)
    chroma = chroma[active] / energy[active, None]
    return chroma.mean(axis=0).astype(np.float64)


def estimate_key(chroma: np.ndarray) -> Tuple[str, float]:
    """Short key name and confidence from a 12-bin chroma."""
    if not np.any(chroma):
        return "", 0.0
    scores = []
    major, minor_profile = _with_overtones(_MAJOR_PROFILE), _with_overtones(_MINOR_PROFILE)
    for tonic in range(12):
        for minor, profile in ((False, major), (True, minor_profile)):
            rotated = np.roll(profile, tonic)
            scores.append((float(np.corrcoef(chroma, rotated)[0, 1]), tonic, minor))
    scores.sort(reverse=True)
    best, second = scores[0], scores[1]
    name = (PITCHES_MINOR[best[1]] + "m") if best[2] else PITCHES_MAJOR[best[1]]
    confidence = float(np.clip((best[0] - second[0]) * 5.0 + max(best[0], 0.0) * 0.5, 0.0, 1.0))
    return name, confidence


def analyse_audio(audio: np.ndarray, sample_rate: int) -> TrackAnalysis:
    """Tempo, beat phase and key of a (n_samples, n_channels) signal."""
    mono = _to_analysis_mono(audio, sample_rate)
    duration = mono.size / ANALYSIS_SR
    envelope = onset_envelope(mono)
    bpm, bpm_confidence = estimate_tempo(envelope)
    offset = estimate_beat_offset(envelope, bpm) if bpm else None
    key, key_confidence = estimate_key(chroma_profile(mono))
    return TrackAnalysis(bpm, bpm_confidence, offset, key, key_confidence, duration)


def analyse_file(path: Path) -> TrackAnalysis:
    """Decode ``path`` (any supported format, FFmpeg for M4A) and analyse it."""
    from .core import load_audio          # local import: keeps this module light for tests

    loaded = load_audio(Path(path).read_bytes(), Path(path).name)
    return analyse_audio(loaded.samples, loaded.sample_rate)

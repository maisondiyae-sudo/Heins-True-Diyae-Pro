"""
Heins True Diyae - audio engine
===============================
Anti-Parasite Filter + automated mastering. This module is the engine of the
Streamlit version (its sections 1 to 7), moved here unchanged except for:

* no Streamlit import (the engine never touched the UI anyway);
* an FFmpeg resolver hook (``set_ffmpeg_resolver``) so the desktop shell can
  point the decoder at a bundled / Homebrew / winget / imageio-ffmpeg binary;
* ``SUBPROCESS_FLAGS`` so FFmpeg does not flash a console window on Windows.

Layout
------
    1. Configuration and shared helpers
    2. Audio I/O            (validation, decoding, resampling, WAV encoding)
    3. Metering             (integrated LUFS, true peak, stereo correlation)
    4. STFT toolkit         (framing, STFT / inverse STFT, chunked processing)
    5. Module 1             AntiParasiteFilter
    6. Module 2             MasteringEngine + 5 profiles + true-peak limiter
    7. Visualisation        (spectrograms, tonal-change chart, band table)

Internal audio convention: ``float32`` arrays shaped ``(n_samples, n_channels)``
at 44.1 kHz, full scale = +/-1.0.
"""

from __future__ import annotations

import io
import math
import os
import re
import shutil
import subprocess
import tempfile
import time
import warnings
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

import numpy as np
import scipy.fft
import scipy.signal as sps
from scipy.interpolate import CubicSpline
from scipy.ndimage import (
    maximum_filter1d,
    median_filter,
    minimum_filter1d,
    uniform_filter,
    uniform_filter1d,
)

import librosa
import pyloudnorm as pyln
import soundfile as sf
from pedalboard import (
    Compressor,
    HighpassFilter,
    HighShelfFilter,
    LowShelfFilter,
    PeakFilter,
    Pedalboard,
)
from pedalboard.io import AudioFile

import matplotlib

matplotlib.use("Agg")  # headless backend: figures are rendered by st.pyplot
from matplotlib.colors import LinearSegmentedColormap  # noqa: E402
from matplotlib.figure import Figure  # noqa: E402
from matplotlib.ticker import FuncFormatter  # noqa: E402



# =============================================================================
# 1. CONFIGURATION AND SHARED HELPERS
# =============================================================================

APP_NAME = "Heins True Diyae"
APP_TAGLINE = "Anti-Parasite Filter and automated mastering"
APP_VERSION = "2.0 Pro"

INTERNAL_SR = 44_100            # processing and export sample rate (Hz)
EXPORT_SUBTYPE = "PCM_24"       # 24-bit linear PCM
ALLOWED_EXTENSIONS = ("wav", "mp3", "m4a", "flac", "ogg", "aiff", "aif")
MAX_UPLOAD_MB = 200
MIN_DURATION_S = 3.0
MAX_DURATION_S = 15 * 60
MIN_SAMPLE_RATE = 8_000
MAX_SAMPLE_RATE = 384_000
SILENCE_PEAK = 1e-5             # -100 dBFS: below this the file is treated as silent

ProgressFn = Callable[[float, str], None]

# FFmpeg location. The default only looks at PATH; the desktop shell installs a
# cross-platform resolver with set_ffmpeg_resolver().
_ffmpeg_resolver: Callable[[], Optional[str]] = lambda: shutil.which("ffmpeg")

# Hide the console window that a console program (FFmpeg) would open on Windows.
SUBPROCESS_FLAGS = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0


def set_ffmpeg_resolver(resolver: Callable[[], Optional[str]]) -> None:
    """Install the function that returns the FFmpeg executable path (or None)."""
    global _ffmpeg_resolver
    _ffmpeg_resolver = resolver


def ffmpeg_executable() -> Optional[str]:
    """Path of the FFmpeg executable to use, or None when it is not available."""
    try:
        return _ffmpeg_resolver()
    except Exception:  # noqa: BLE001 - a broken resolver must not break decoding
        return None


class AudioLoadError(Exception):
    """The uploaded file cannot be accepted or decoded (message is user-facing)."""


class ProcessingError(Exception):
    """A DSP stage cannot complete on this material (message is user-facing)."""


def _noop_progress(_fraction: float, _message: str) -> None:
    """Default progress callback: do nothing."""


def sub_progress(progress: Optional[ProgressFn], lo: float, hi: float) -> ProgressFn:
    """Map a stage's local 0..1 progress onto the ``lo..hi`` slice of a parent bar."""
    parent = progress or _noop_progress

    def _inner(fraction: float, message: str) -> None:
        clipped = min(max(float(fraction), 0.0), 1.0)
        parent(lo + (hi - lo) * clipped, message)

    return _inner


def db_to_lin(db: float) -> float:
    """Decibels to linear amplitude."""
    return float(10.0 ** (db / 20.0))


def lin_to_db(value: float, floor_db: float = -150.0) -> float:
    """Linear amplitude to decibels, clamped at ``floor_db``."""
    if value <= 0.0 or not math.isfinite(value):
        return floor_db
    return max(floor_db, 20.0 * math.log10(value))


def as_audio_array(audio: np.ndarray) -> np.ndarray:
    """Return a C-contiguous float32 ``(n_samples, n_channels)`` view/copy."""
    arr = np.asarray(audio)
    if arr.ndim == 1:
        arr = arr[:, None]
    if arr.ndim != 2 or arr.shape[0] == 0 or arr.shape[1] == 0:
        raise ProcessingError("Internal error: audio buffer has an invalid shape.")
    return np.ascontiguousarray(arr, dtype=np.float32)


# =============================================================================
# 2. AUDIO I/O
# =============================================================================

@dataclass
class LoadedAudio:
    """A decoded upload, already converted to the internal format."""

    samples: np.ndarray             # float32, (n_samples, n_channels), INTERNAL_SR
    sample_rate: int
    native_sample_rate: int
    native_channels: int
    duration_s: float
    decoder: str
    notes: List[str] = field(default_factory=list)


def validate_upload(filename: str, size_bytes: int) -> str:
    """Check extension and size before any decoding. Returns the lowercase extension."""
    ext = Path(filename or "").suffix.lower().lstrip(".")
    if ext not in ALLOWED_EXTENSIONS:
        allowed = ", ".join(ALLOWED_EXTENSIONS)
        raise AudioLoadError(f"Unsupported file type '.{ext}'. Accepted formats: {allowed}.")
    if size_bytes <= 0:
        raise AudioLoadError("The uploaded file is empty.")
    if size_bytes > MAX_UPLOAD_MB * 1024 * 1024:
        raise AudioLoadError(f"The file is larger than the {MAX_UPLOAD_MB} MB limit.")
    return ext


def _check_stream(frames: int, sample_rate: int) -> None:
    """Reject impossible or oversized streams *before* reading them into memory."""
    if sample_rate < MIN_SAMPLE_RATE or sample_rate > MAX_SAMPLE_RATE:
        raise AudioLoadError(
            f"Unsupported sample rate ({sample_rate} Hz). "
            f"Accepted range: {MIN_SAMPLE_RATE}-{MAX_SAMPLE_RATE} Hz."
        )
    if frames <= 0:
        raise AudioLoadError("The file contains no audio data.")
    if frames / sample_rate > MAX_DURATION_S + 1.0:
        raise AudioLoadError(
            f"The track is longer than the {MAX_DURATION_S // 60}-minute limit."
        )


def decode_audio_bytes(data: bytes, ext: str) -> Tuple[np.ndarray, int, str]:
    """
    Decode compressed or PCM audio to float32 ``(n_samples, n_channels)``.

    Decoders are tried in order:
      1. libsndfile via ``soundfile`` (WAV, FLAC, OGG, AIFF, MP3) - in memory;
      2. ``pedalboard.io.AudioFile`` (MP3 everywhere, AAC/M4A where the OS has a codec);
      3. the ``ffmpeg`` command line, called directly (AAC/M4A on Linux, e.g. Streamlit
         Cloud with ``ffmpeg`` in packages.txt) - recent librosa versions no longer fall
         back to FFmpeg on their own;
      4. ``librosa`` / audioread (last resort).

    The upload is only ever written to a private temporary file whose name is
    generated by the OS (the user's file name is never used as a path), and that
    file is removed in all cases.
    """
    failures: List[str] = []

    # --- 1) libsndfile, straight from memory ---------------------------------
    try:
        with sf.SoundFile(io.BytesIO(data)) as handle:
            sample_rate = int(handle.samplerate)
            _check_stream(int(handle.frames), sample_rate)
            audio = handle.read(dtype="float32", always_2d=True)
        return audio, sample_rate, "libsndfile"
    except AudioLoadError:
        raise
    except Exception as exc:  # noqa: BLE001 - any decoder failure falls through
        failures.append(f"libsndfile: {exc}")

    # --- 2) and 3) need a real file on disk ----------------------------------
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=f".{ext}", delete=False) as tmp:
            tmp.write(data)
            tmp_path = tmp.name

        try:
            with AudioFile(tmp_path) as handle:
                sample_rate = int(round(float(handle.samplerate)))
                frames = int(handle.frames)
                _check_stream(frames, sample_rate)
                audio = handle.read(frames)  # (channels, frames) float32
            return np.ascontiguousarray(np.atleast_2d(audio).T), sample_rate, "pedalboard"
        except AudioLoadError:
            raise
        except Exception as exc:  # noqa: BLE001
            failures.append(f"pedalboard: {exc}")

        ffmpeg = ffmpeg_executable()
        if ffmpeg:
            wav_path = tmp_path + ".decoded.wav"
            try:
                # Decode to a 32-bit float WAV on disk (seekable, exact header, full
                # precision), capped at the maximum duration.
                completed = subprocess.run(
                    [ffmpeg, "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
                     "-i", tmp_path, "-vn", "-t", str(MAX_DURATION_S + 2),
                     "-c:a", "pcm_f32le", wav_path],
                    capture_output=True, timeout=600, check=False,
                    creationflags=SUBPROCESS_FLAGS,
                )
                if completed.returncode != 0:
                    message = completed.stderr.decode("utf-8", "replace").strip()
                    raise RuntimeError(message[-300:] or f"exit code {completed.returncode}")
                with sf.SoundFile(wav_path) as handle:
                    sample_rate = int(handle.samplerate)
                    _check_stream(int(handle.frames), sample_rate)
                    audio = handle.read(dtype="float32", always_2d=True)
                return np.ascontiguousarray(audio), sample_rate, "ffmpeg"
            except AudioLoadError:
                raise
            except Exception as exc:  # noqa: BLE001
                failures.append(f"ffmpeg: {exc}")
            finally:
                try:
                    os.remove(wav_path)
                except OSError:
                    pass
        else:
            failures.append("ffmpeg: not installed")

        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                # ``duration`` caps how much is decoded, so a hostile file cannot
                # expand into an unbounded amount of memory.
                audio, sample_rate = librosa.load(
                    tmp_path, sr=None, mono=False, duration=MAX_DURATION_S + 2.0
                )
            audio = np.atleast_2d(np.asarray(audio, dtype=np.float32))
            sample_rate = int(sample_rate)
            _check_stream(audio.shape[1], sample_rate)
            return np.ascontiguousarray(audio.T), sample_rate, "librosa/ffmpeg"
        except AudioLoadError:
            raise
        except Exception as exc:  # noqa: BLE001
            failures.append(f"librosa: {exc}")
    finally:
        if tmp_path is not None:
            try:
                os.remove(tmp_path)
            except OSError:
                pass

    hint = ""
    if ext == "m4a" and ffmpeg_executable() is None:
        hint = (" M4A/AAC needs FFmpeg: install it (Homebrew, winget...) or run "
                "'pip install imageio-ffmpeg'.")
    detail = " | ".join(failures)
    raise AudioLoadError(
        f"This file could not be decoded - it may be corrupt or not a real .{ext} file.{hint} "
        f"(details: {detail})"
    )


def resample_audio(audio: np.ndarray, sr_in: int, sr_out: int) -> np.ndarray:
    """High-quality sample-rate conversion (SoX resampler, polyphase FIR as fallback)."""
    if sr_in == sr_out:
        return audio
    if sr_in <= 0 or sr_out <= 0:
        raise AudioLoadError("Invalid sample rate for conversion.")
    try:
        out = librosa.resample(
            np.ascontiguousarray(audio.T, dtype=np.float32),
            orig_sr=sr_in,
            target_sr=sr_out,
            res_type="soxr_hq",
        ).T
    except Exception:  # noqa: BLE001 - fall back to SciPy if soxr is unavailable
        try:
            divisor = math.gcd(int(sr_in), int(sr_out))
            out = sps.resample_poly(
                audio.astype(np.float64), sr_out // divisor, sr_in // divisor, axis=0
            )
        except Exception as exc:  # noqa: BLE001
            raise AudioLoadError(
                f"Sample-rate conversion {sr_in} Hz -> {sr_out} Hz failed ({exc})."
            ) from exc
    return np.ascontiguousarray(out, dtype=np.float32)


def load_audio(data: bytes, filename: str) -> LoadedAudio:
    """Validate, decode and convert an upload to the internal 44.1 kHz float32 format."""
    ext = validate_upload(filename, len(data))
    audio, native_sr, decoder = decode_audio_bytes(data, ext)

    audio = np.asarray(audio)
    if audio.ndim == 1:
        audio = audio[:, None]
    if audio.ndim != 2 or audio.shape[0] == 0 or audio.shape[1] == 0:
        raise AudioLoadError("The file contains no audio data.")

    notes: List[str] = []
    native_channels = int(audio.shape[1])
    if native_channels > 2:
        audio = audio[:, :2]
        notes.append(f"{native_channels} channels found - only the first two (L/R) are used.")

    audio = np.ascontiguousarray(audio, dtype=np.float32)
    if not np.isfinite(audio).all():
        audio = np.nan_to_num(audio, nan=0.0, posinf=0.0, neginf=0.0)
        notes.append("Non-finite samples (NaN/Inf) were found and replaced with silence.")

    duration = audio.shape[0] / float(native_sr)
    if duration < MIN_DURATION_S:
        raise AudioLoadError(
            f"The track is too short ({duration:.2f} s). Minimum length: {MIN_DURATION_S:.0f} s."
        )
    if duration > MAX_DURATION_S:
        raise AudioLoadError(
            f"The track is longer than the {MAX_DURATION_S // 60}-minute limit."
        )

    peak = float(np.abs(audio).max())
    if peak < SILENCE_PEAK:
        raise AudioLoadError("The file is silent - there is nothing to process.")
    if peak > 1.0:
        notes.append(
            f"Source peaks exceed full scale by {lin_to_db(peak):.1f} dB (floating-point file)."
        )

    if native_sr != INTERNAL_SR:
        audio = resample_audio(audio, native_sr, INTERNAL_SR)
        notes.append(f"Resampled {native_sr:,} Hz -> {INTERNAL_SR:,} Hz.")

    return LoadedAudio(
        samples=audio,
        sample_rate=INTERNAL_SR,
        native_sample_rate=int(native_sr),
        native_channels=native_channels,
        duration_s=audio.shape[0] / float(INTERNAL_SR),
        decoder=decoder,
        notes=notes,
    )


def encode_wav(audio: np.ndarray, sample_rate: int, subtype: str = EXPORT_SUBTYPE) -> bytes:
    """Encode to an in-memory WAV file (24-bit PCM by default)."""
    # Clip explicitly: integer conversion of out-of-range floats is undefined in libsndfile.
    limit = 1.0 - 2.0 ** -23
    safe = np.clip(np.asarray(audio, dtype=np.float32), -limit, limit)
    buffer = io.BytesIO()
    sf.write(buffer, safe, int(sample_rate), subtype=subtype, format="WAV")
    return buffer.getvalue()


def safe_stem(filename: str) -> str:
    """A download-safe file stem derived from the user's file name."""
    stem = re.sub(r"[^\w.-]+", "_", Path(filename or "track").stem).strip("._")
    return (stem or "track")[:80]


# =============================================================================
# 3. METERING
# =============================================================================

@dataclass
class AudioMetrics:
    """Loudness and peak figures for one version of the track."""

    lufs: float                         # integrated loudness, ITU-R BS.1770 (may be -inf)
    true_peak_db: float                 # dBTP, 4x oversampled
    sample_peak_db: float               # dBFS
    correlation: Optional[float]        # stereo phase correlation (-1..+1), None for mono

    @property
    def plr_db(self) -> float:
        """Peak-to-loudness ratio (true peak minus integrated loudness)."""
        if not math.isfinite(self.lufs):
            return float("nan")
        return self.true_peak_db - self.lufs


def measure_lufs(audio: np.ndarray, sample_rate: int) -> float:
    """Integrated loudness in LUFS (pyloudnorm, ITU-R BS.1770-4 with gating)."""
    if audio.shape[0] < int(0.45 * sample_rate):
        raise ProcessingError("The audio is too short for a loudness measurement.")
    meter = pyln.Meter(sample_rate)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        with np.errstate(divide="ignore", invalid="ignore"):
            return float(meter.integrated_loudness(audio))


_TP_BLOCK = 1 << 18
_TP_PAD = 64


def true_peak_envelope(audio: np.ndarray, oversample: int = 4) -> np.ndarray:
    """
    Per-sample true-peak envelope.

    Each output value is the largest absolute value, across all channels, of the
    ``oversample`` interpolated points that follow that sample (band-limited
    polyphase interpolation, as recommended by ITU-R BS.1770 for true-peak
    metering). Processed block by block so memory stays flat on long tracks.
    """
    n_samples, n_channels = audio.shape
    envelope = np.zeros(n_samples, dtype=np.float32)
    for start in range(0, n_samples, _TP_BLOCK):
        stop = min(start + _TP_BLOCK, n_samples)
        lo = max(start - _TP_PAD, 0)
        hi = min(stop + _TP_PAD, n_samples)
        block = audio[lo:hi].astype(np.float64)
        upsampled = sps.resample_poly(block, oversample, 1, axis=0)
        peaks = np.abs(upsampled).reshape(hi - lo, oversample, n_channels).max(axis=(1, 2))
        envelope[start:stop] = peaks[start - lo:stop - lo]
    return envelope


def measure_true_peak_db(audio: np.ndarray) -> float:
    """True peak in dBTP (4x oversampling)."""
    return lin_to_db(float(true_peak_envelope(audio).max()))


def stereo_correlation(audio: np.ndarray) -> Optional[float]:
    """Zero-lag L/R correlation: +1 mono-compatible, 0 unrelated, -1 out of phase."""
    if audio.shape[1] < 2:
        return None
    left = audio[:, 0].astype(np.float64)
    right = audio[:, 1].astype(np.float64)
    denominator = math.sqrt(float(np.dot(left, left)) * float(np.dot(right, right)))
    if denominator <= 1e-20:
        return None
    return float(np.dot(left, right) / denominator)


def measure_metrics(
    audio: np.ndarray,
    sample_rate: int,
    lufs: Optional[float] = None,
    true_peak_db: Optional[float] = None,
) -> AudioMetrics:
    """Measure everything shown in the UI. Known values can be passed to skip work."""
    return AudioMetrics(
        lufs=measure_lufs(audio, sample_rate) if lufs is None else float(lufs),
        true_peak_db=measure_true_peak_db(audio) if true_peak_db is None else float(true_peak_db),
        sample_peak_db=lin_to_db(float(np.abs(audio).max())),
        correlation=stereo_correlation(audio),
    )


# =============================================================================
# 4. STFT TOOLKIT
# =============================================================================

def stft(signal: np.ndarray, n_fft: int, hop: int, window: np.ndarray) -> np.ndarray:
    """
    Centred short-time Fourier transform of a mono signal.

    Returns complex64 ``(n_frames, n_fft // 2 + 1)``; frame ``t`` is centred on
    sample ``t * hop`` (reflect padding at both ends).
    """
    pad = n_fft // 2
    padded = np.pad(np.asarray(signal, dtype=np.float32), pad, mode="reflect")
    frames = np.lib.stride_tricks.sliding_window_view(padded, n_fft)[::hop]
    return scipy.fft.rfft(frames * window, axis=1)


def istft(spectrum: np.ndarray, hop: int, window: np.ndarray, length: int) -> np.ndarray:
    """
    Inverse of :func:`stft` by weighted overlap-add (same window for synthesis,
    normalised by the summed squared window, so an unmodified spectrum is
    reconstructed exactly).
    """
    n_frames, n_bins = spectrum.shape
    n_fft = (n_bins - 1) * 2
    if n_fft % hop != 0:
        raise ValueError("hop must divide n_fft")
    frames = scipy.fft.irfft(spectrum, n=n_fft, axis=1).astype(np.float32, copy=False)
    frames = frames * window

    total = n_fft + hop * (n_frames - 1)
    output = np.zeros(total, dtype=np.float32)
    weight = np.zeros(total, dtype=np.float32)
    window_sq = (window * window).astype(np.float32)
    overlap_factor = n_fft // hop
    # Frames k, k + overlap_factor, ... do not overlap each other, so each group
    # can be laid down with one vectorised write.
    for k in range(overlap_factor):
        group = frames[k::overlap_factor]
        count = group.shape[0]
        if count == 0:
            continue
        start = k * hop
        output[start:start + count * n_fft] += group.reshape(-1)
        weight[start:start + count * n_fft] += np.tile(window_sq, count)

    pad = n_fft // 2
    output = output[pad:pad + length]
    weight = weight[pad:pad + length]
    return output / np.maximum(weight, 1e-8)


def _crossfade_ramp(overlap: int) -> np.ndarray:
    """
    Fade-in weights for an overlap region: 0 for the first quarter, linear over
    the middle half, 1 for the last quarter. The flat quarters keep the samples
    that are affected by a chunk's edge padding out of the result entirely.
    """
    quarter = overlap // 4
    middle = overlap - 2 * quarter
    ramp = np.ones(overlap, dtype=np.float32)
    ramp[:quarter] = 0.0
    ramp[quarter:quarter + middle] = (np.arange(middle, dtype=np.float32) + 0.5) / middle
    return ramp


def process_in_chunks(
    audio: np.ndarray,
    fn: Callable[[np.ndarray, int], np.ndarray],
    chunk_size: int,
    overlap: int,
    progress: Optional[ProgressFn] = None,
    label: str = "",
) -> np.ndarray:
    """
    Apply ``fn(segment, start_sample)`` over overlapping chunks and cross-fade
    the results, so memory use does not grow with track length.

    ``fn`` must return an array with the same shape as the segment it received.
    """
    report = progress or _noop_progress
    n_samples = audio.shape[0]
    if n_samples <= chunk_size:
        result = np.asarray(fn(audio, 0), dtype=audio.dtype)
        report(1.0, label)
        return result

    step = chunk_size - overlap
    starts = list(range(0, n_samples - overlap, step))
    fade_in = _crossfade_ramp(overlap)[:, None]
    fade_out = 1.0 - fade_in
    output = np.zeros_like(audio)
    for index, start in enumerate(starts):
        stop = min(start + chunk_size, n_samples)
        segment = np.array(fn(audio[start:stop], start), dtype=audio.dtype, copy=True)
        if segment.shape != (stop - start, audio.shape[1]):
            raise ProcessingError("Internal error: a processing stage changed the audio length.")
        if start > 0:
            segment[:overlap] *= fade_in
        if stop < n_samples:
            segment[-overlap:] *= fade_out
        output[start:stop] += segment
        report((index + 1) / len(starts), label)
    return output


# =============================================================================
# 5. MODULE 1 - ANTI-PARASITE FILTER
# =============================================================================

@dataclass
class AntiParasiteReport:
    """What the filter measured and applied (shown in the processing report)."""

    intensity: float = 0.0
    tonal_parasites_hz: List[float] = field(default_factory=list)
    max_tonal_reduction_db: float = 0.0
    max_noise_reduction_db: float = 0.0
    phase_variation_deg: float = 0.0
    time_drift_us: float = 0.0
    drift_rate_cents: float = 0.0
    seed: int = 0
    # Analog tolerance modeling (None = off, the v1.0 filter bit for bit)
    analog_seed: Optional[int] = None
    analog_max_deviation_pct: float = 0.0


@dataclass(frozen=True)
class AnalogChannelParams:
    """Per-channel internal parameters of the Anti-Parasite Filter.

    The nominal instance holds exactly the class constants (v1.0 behaviour). With
    analog tolerance modeling every channel gets its own slightly "mis-matched"
    copy, like the two sides of an analog console built from 1-3 % components.
    ``*_f_scale`` / ``*_q_scale`` are per biquad section of the band-limiting filters
    (``None`` = ideal Butterworth, designed exactly as in v1.0).
    """

    highpass_hz: float
    lowpass_hz: float
    highpass_f_scale: Optional[Tuple[float, ...]]
    highpass_q_scale: Optional[Tuple[float, ...]]
    lowpass_f_scale: Optional[Tuple[float, ...]]
    lowpass_q_scale: Optional[Tuple[float, ...]]
    noise_ceiling_db: float
    spur_excess_db: float
    spur_plateau_db: float
    spur_min_hz: float
    spur_max_level_db: float
    over_subtraction: float

    def max_deviation_pct(self, nominal: "AnalogChannelParams") -> float:
        """Largest relative deviation from ``nominal`` (levels compared in amplitude)."""
        ratios = [
            self.highpass_hz / nominal.highpass_hz,
            self.lowpass_hz / nominal.lowpass_hz,
            self.spur_excess_db / nominal.spur_excess_db,
            self.spur_plateau_db / nominal.spur_plateau_db,
            self.spur_min_hz / nominal.spur_min_hz,
            self.over_subtraction / nominal.over_subtraction,
            db_to_lin(self.noise_ceiling_db - nominal.noise_ceiling_db),
            db_to_lin(self.spur_max_level_db - nominal.spur_max_level_db),
        ]
        for scales in (self.highpass_f_scale, self.highpass_q_scale,
                       self.lowpass_f_scale, self.lowpass_q_scale):
            ratios.extend(scales or ())
        return 100.0 * max(abs(r - 1.0) for r in ratios)


class AntiParasiteFilter:
    """
    "Heins True Diyae" Anti-Parasite Filter.

    Stage A - Band-limiting (always on)
        Zero-phase Butterworth high-pass at 20 Hz and low-pass at 20 kHz
        (8th order run forward and backward: 96 dB/octave, no phase shift).

    Stage B - Spectral deconstruction / reconstruction (scales with intensity)
        The track is taken apart with an STFT (4096-point Hann, 75 % overlap).
        Per-bin time statistics separate what is *stationary* from the music:

        * Tonal parasites - narrow lines whose level is locked in time (a flat
          low-percentile plateau) and that stand out of the neighbouring
          spectrum (whine, pilot/clock tones, aliasing spurs, hum harmonics).
          They are removed by magnitude spectral subtraction with a floor.
          Steady tones louder than -40 dBFS are assumed to be musical (a
          drone or a held pad) and are never touched.
        * Broadband residue - a stationary floor profile drives a Wiener-style
          soft mask that only touches time-frequency regions sitting at the
          floor. The decision uses local (time x frequency) power, which avoids
          "musical noise" and leaves notes and transients untouched.

    Stage C - Phase micro-variation and micro time-drift (scales with intensity)
        In the same STFT pass every bin is rotated by a slowly evolving phase:

        * a smooth random field (third-octave bands, one control point every
          0.5 s, cubic interpolation) of at most a few degrees. It is tapered
          to zero below 80 Hz so low-end phase alignment is untouched;
        * a linear-phase term ``-2*pi*k*d(t)/N`` where ``d(t)`` is a smooth
          random delay of a few samples. A time-varying delay *is* a
          time-stretch: here the local speed deviation stays below 0.025 %
          (under half a cent), like very mild tape wow.

        Both terms are identical for all channels, so the inter-channel phase
        relationship (stereo image, mono compatibility) is preserved exactly.
        This stage de-correlates rigid, grid-like low-level patterns; it does
        not remove energy - that is Stage B's job.

    The random generator is seeded (by default from the file's hash), so the
    same file and settings always render the same output.

    Analog tolerance modeling (optional, ``analog_seed``)
        Inspired by console tolerance modeling: real components are never exactly
        on value, and each channel of a console drifts a little differently. With
        an integer ``analog_seed`` a private ``np.random.default_rng(analog_seed)``
        gives every channel its own deviation of +/-1 to 3 % on the filter's
        internal parameters: band-limit corner frequencies, the natural frequency
        and Q of every Butterworth section (Stage A), and the Stage B detection
        thresholds (noise ceiling, spur excess / plateau / minimum frequency /
        music-protection level, over-subtraction). Stage C is not affected (its
        rotation stays identical on all channels). The same seed always gives the
        same output; ``analog_seed=None`` (or 0 % intensity) is the v1.0 filter,
        bit for bit.
    """

    # STFT geometry
    N_FFT = 4096
    HOP = 1024
    CHUNK = 1 << 20              # ~23.8 s per chunk at 44.1 kHz
    OVERLAP = 32768              # CHUNK - OVERLAP is a multiple of HOP (frame grids line up)

    # Stage A
    HIGHPASS_HZ = 20.0
    LOWPASS_HZ = 20_000.0
    FILTER_ORDER = 8

    # Stage B - analysis
    MAX_ANALYSIS_FRAMES = 4000
    ACTIVE_FRAME_DB = -70.0      # frames quieter than this (RMS) are ignored
    MIN_ACTIVE_FRAMES = 64
    NOISE_BIAS = 3.08            # 10th percentile -> RMS magnitude, for Rayleigh-distributed noise
    NOISE_CEILING_DB = -70.0     # per-bin dBFS: nothing louder is ever treated as noise
    SPUR_EXCESS_DB = 6.0         # line must stand this far above its neighbourhood
    SPUR_PLATEAU_DB = 3.5        # ...and vary less than this between the 5th and 30th percentile
    SPUR_MIN_HZ = 30.0
    SPUR_MIN_LEVEL_DB = -120.0
    SPUR_MAX_LEVEL_DB = -40.0    # a steady tone louder than this is music (drone, pad), not a parasite
    # Stage B - depth at 100 % intensity
    MAX_NOISE_REDUCTION_DB = 10.0
    MAX_TONAL_REDUCTION_DB = 36.0

    # Stage C - depth at 100 % intensity
    MAX_PHASE_RAD = 0.25         # ~14 degrees
    PHASE_CONTROL_SECONDS = 0.5
    PHASE_BANDS_PER_OCTAVE = 3
    PHASE_TAPER_HZ = (80.0, 300.0)
    MAX_DRIFT_SAMPLES = 4.0      # ~91 microseconds at 44.1 kHz
    DRIFT_KNOT_SECONDS = 2.0
    MAX_DRIFT_RATE = 2.5e-4      # speed deviation cap (0.025 % = 0.43 cent)

    # Analog tolerance modeling: |deviation| drawn in [MIN, MAX], random sign
    ANALOG_TOLERANCE_MIN = 0.01
    ANALOG_TOLERANCE_MAX = 0.03

    def __init__(self, sample_rate: int, intensity: float, seed: int = 0,
                 analog_seed: Optional[int] = None) -> None:
        if sample_rate <= 0:
            raise ProcessingError("Invalid sample rate.")
        self.sr = int(sample_rate)
        self.intensity = float(min(max(intensity, 0.0), 1.0))
        self.seed = int(seed) & 0xFFFFFFFFFFFFFFFF
        self.analog_seed: Optional[int] = (
            None if analog_seed is None else int(analog_seed) & 0xFFFFFFFFFFFFFFFF
        )
        # At 0 % the filter is a plain band-limit: tolerance modeling stays off too.
        self._analog_active = self.analog_seed is not None and self.intensity > 0.0
        self._channel_params: List[AnalogChannelParams] = []

        self._window = sps.get_window("hann", self.N_FFT, fftbins=True).astype(np.float32)
        # STFT magnitude of a full-scale sine: lets bin levels be expressed in dBFS.
        self._bin_ref = float(self._window.sum() / 2.0)
        self._freqs = np.fft.rfftfreq(self.N_FFT, 1.0 / self.sr)
        self._n_bins = self._freqs.size

        amount = self.intensity
        self._over_subtraction = 0.9 + 0.5 * amount
        self._mask_floor = db_to_lin(-self.MAX_NOISE_REDUCTION_DB * amount)
        self._tonal_alpha = min(1.0, 0.4 + 1.2 * amount)
        self._tonal_floor = db_to_lin(-self.MAX_TONAL_REDUCTION_DB * amount)

        self._noise_floor: List[np.ndarray] = []
        self._tonal_profile: List[np.ndarray] = []
        self._phase_time_spline: Optional[CubicSpline] = None
        self._phase_basis: Optional[np.ndarray] = None
        self._delay_spline: Optional[CubicSpline] = None
        self._linear_phase = (-2.0 * np.pi / self.N_FFT) * np.arange(self._n_bins)

        self.report = AntiParasiteReport(
            intensity=self.intensity,
            seed=self.seed,
            analog_seed=self.analog_seed if self._analog_active else None,
        )

    # ------------------------------------------------------------------ public
    def process(self, audio: np.ndarray, progress: Optional[ProgressFn] = None) -> np.ndarray:
        """Run the full filter. Returns float32 audio with the same shape as the input."""
        report = progress or _noop_progress
        source = as_audio_array(audio)
        if source.shape[0] < 4 * self.N_FFT:
            raise ProcessingError("The audio is too short for the Anti-Parasite Filter.")
        self._channel_params = self._build_channel_params(source.shape[1])

        report(0.02, "Anti-Parasite Filter: band-limiting 20 Hz - 20 kHz")
        cleaned = self._band_limit(source)

        if self.intensity > 0.0:
            report(0.12, "Anti-Parasite Filter: analysing stationary spectral content")
            self._analyse(cleaned)
            self._prepare_modulation(cleaned.shape[0])
            cleaned = process_in_chunks(
                cleaned,
                self._process_chunk,
                self.CHUNK,
                self.OVERLAP,
                sub_progress(report, 0.20, 0.98),
                "Anti-Parasite Filter: spectral cleanse and phase micro-smoothing",
            )

        if not np.isfinite(cleaned).all():
            raise ProcessingError("The Anti-Parasite Filter produced invalid samples.")
        report(1.0, "Anti-Parasite Filter: done")
        return np.ascontiguousarray(cleaned, dtype=np.float32)

    # --------------------------------------------------- analog tolerance model
    def _nominal_params(self) -> AnalogChannelParams:
        """The class constants, untouched (v1.0 behaviour)."""
        return AnalogChannelParams(
            highpass_hz=self.HIGHPASS_HZ,
            lowpass_hz=self.LOWPASS_HZ,
            highpass_f_scale=None,
            highpass_q_scale=None,
            lowpass_f_scale=None,
            lowpass_q_scale=None,
            noise_ceiling_db=self.NOISE_CEILING_DB,
            spur_excess_db=self.SPUR_EXCESS_DB,
            spur_plateau_db=self.SPUR_PLATEAU_DB,
            spur_min_hz=self.SPUR_MIN_HZ,
            spur_max_level_db=self.SPUR_MAX_LEVEL_DB,
            over_subtraction=self._over_subtraction,
        )

    def _tolerance(self, rng: np.random.Generator, size: int) -> np.ndarray:
        """``size`` multiplicative factors 1 +/- [1 %, 3 %] (random sign)."""
        magnitude = rng.uniform(self.ANALOG_TOLERANCE_MIN, self.ANALOG_TOLERANCE_MAX, size=size)
        sign = np.where(rng.random(size) < 0.5, -1.0, 1.0)
        return 1.0 + sign * magnitude

    def _build_channel_params(self, n_channels: int) -> List[AnalogChannelParams]:
        nominal = self._nominal_params()
        if not self._analog_active:
            self.report.analog_max_deviation_pct = 0.0
            return [nominal] * n_channels

        # Private generator: the Stage C modulation (self.seed) is not disturbed.
        rng = np.random.default_rng(self.analog_seed)
        n_sections = (self.FILTER_ORDER + 1) // 2
        params: List[AnalogChannelParams] = []
        for _channel in range(n_channels):
            corners = self._tolerance(rng, 2)
            hp_f, hp_q = self._tolerance(rng, n_sections), self._tolerance(rng, n_sections)
            lp_f, lp_q = self._tolerance(rng, n_sections), self._tolerance(rng, n_sections)
            th = self._tolerance(rng, 6)
            params.append(AnalogChannelParams(
                highpass_hz=nominal.highpass_hz * float(corners[0]),
                lowpass_hz=nominal.lowpass_hz * float(corners[1]),
                highpass_f_scale=tuple(float(v) for v in hp_f),
                highpass_q_scale=tuple(float(v) for v in hp_q),
                lowpass_f_scale=tuple(float(v) for v in lp_f),
                lowpass_q_scale=tuple(float(v) for v in lp_q),
                # Absolute levels: the tolerance applies to the amplitude (+/-0.09-0.26 dB).
                noise_ceiling_db=nominal.noise_ceiling_db + lin_to_db(float(th[0])),
                spur_excess_db=nominal.spur_excess_db * float(th[1]),
                spur_plateau_db=nominal.spur_plateau_db * float(th[2]),
                spur_min_hz=nominal.spur_min_hz * float(th[3]),
                spur_max_level_db=nominal.spur_max_level_db + lin_to_db(float(th[4])),
                over_subtraction=nominal.over_subtraction * float(th[5]),
            ))
        self.report.analog_max_deviation_pct = max(p.max_deviation_pct(nominal) for p in params)
        return params

    def _toleranced_butter(self, cutoff_hz: float, btype: str,
                           f_scale: Tuple[float, ...], q_scale: Tuple[float, ...]) -> np.ndarray:
        """Butterworth band-limit whose sections are each slightly off-value.

        The analog prototype is split into its second-order sections (pole pairs,
        natural frequency w0 = 1 and Butterworth Q). Each section's w0 and Q get
        their own tolerance, the prototype is moved to the (pre-warped) corner and
        mapped to digital with the bilinear transform. Gain is normalised to 0 dB in
        the pass band; poles stay in the left half-plane (Q > 0), so the digital
        filter is always stable.
        """
        _zeros, poles, _gain = sps.buttap(self.FILTER_ORDER)
        upper = poles[poles.imag > 1e-12]
        real = poles[np.abs(poles.imag) <= 1e-12]
        moved: List[complex] = []
        for index, pole in enumerate(sorted(upper, key=lambda p: p.real)):
            w0 = abs(pole) * f_scale[index]
            q = (abs(pole) / (-2.0 * pole.real)) * q_scale[index]
            sigma = w0 / (2.0 * q)
            omega = math.sqrt(max(w0 * w0 - sigma * sigma, 0.0))
            moved.extend([complex(-sigma, omega), complex(-sigma, -omega)])
        for offset, pole in enumerate(real):
            moved.append(complex(pole.real * f_scale[len(upper) + offset], 0.0))
        proto_poles = np.asarray(moved, dtype=complex)
        proto_gain = float(np.real(np.prod(-proto_poles)))  # unity DC gain of the low-pass prototype

        warped = 2.0 * self.sr * math.tan(math.pi * cutoff_hz / self.sr)
        if btype == "highpass":
            z, p, k = sps.lp2hp_zpk(np.array([]), proto_poles, proto_gain, wo=warped)
        else:
            z, p, k = sps.lp2lp_zpk(np.array([]), proto_poles, proto_gain, wo=warped)
        z, p, k = sps.bilinear_zpk(z, p, k, fs=self.sr)
        return sps.zpk2sos(z, p, k)

    # ----------------------------------------------------------------- stage A
    def _band_limit(self, audio: np.ndarray) -> np.ndarray:
        nyquist = self.sr / 2.0
        output = np.empty_like(audio)
        try:
            highpass = sps.butter(
                self.FILTER_ORDER, self.HIGHPASS_HZ, btype="highpass", fs=self.sr, output="sos"
            )
            lowpass = None
            if self.LOWPASS_HZ < 0.98 * nyquist:
                lowpass = sps.butter(
                    self.FILTER_ORDER, self.LOWPASS_HZ, btype="lowpass", fs=self.sr, output="sos"
                )
            # One channel at a time keeps the float64 working copies small.
            for channel in range(audio.shape[1]):
                channel_hp, channel_lp = highpass, lowpass
                params = self._channel_params[channel] if self._channel_params else None
                if params is not None and params.highpass_f_scale is not None:
                    channel_hp = self._toleranced_butter(
                        params.highpass_hz, "highpass",
                        params.highpass_f_scale, params.highpass_q_scale,
                    )
                    if lowpass is not None:
                        channel_lp = self._toleranced_butter(
                            min(params.lowpass_hz, 0.99 * nyquist), "lowpass",
                            params.lowpass_f_scale, params.lowpass_q_scale,
                        )
                signal = sps.sosfiltfilt(channel_hp, audio[:, channel].astype(np.float64))
                if channel_lp is not None:
                    signal = sps.sosfiltfilt(channel_lp, signal)
                output[:, channel] = signal
        except ValueError as exc:
            raise ProcessingError(f"Band-limiting filters failed ({exc}).") from exc
        return output

    # ----------------------------------------------------------------- stage B
    def _analyse(self, audio: np.ndarray) -> None:
        """Estimate, per channel, the stationary floor and the tonal-parasite profile."""
        self._noise_floor = []
        self._tonal_profile = []
        found: List[float] = []
        for channel in range(audio.shape[1]):
            floor, tonal = self._analyse_channel(audio[:, channel], self._channel_params[channel])
            self._noise_floor.append(floor)
            self._tonal_profile.append(tonal)
            found.extend(self._cluster_peaks(tonal))

        merged: List[float] = []
        resolution = self.sr / self.N_FFT
        for freq in sorted(found):
            if not merged or freq - merged[-1] > 2.5 * resolution:
                merged.append(freq)
        self.report.tonal_parasites_hz = merged
        self.report.max_noise_reduction_db = self.MAX_NOISE_REDUCTION_DB * self.intensity
        self.report.max_tonal_reduction_db = (
            self.MAX_TONAL_REDUCTION_DB * self.intensity if merged else 0.0
        )

    def _analyse_channel(self, signal: np.ndarray,
                         params: AnalogChannelParams) -> Tuple[np.ndarray, np.ndarray]:
        zeros = np.zeros(self._n_bins, dtype=np.float32)
        hop = max(self.N_FFT // 2, int(math.ceil(signal.size / self.MAX_ANALYSIS_FRAMES)))
        pad = self.N_FFT // 2
        padded = np.pad(signal, pad, mode="reflect")
        frames = np.lib.stride_tricks.sliding_window_view(padded, self.N_FFT)[::hop]
        magnitude = np.empty((frames.shape[0], self._n_bins), dtype=np.float32)
        for start in range(0, frames.shape[0], 256):
            block = frames[start:start + 256] * self._window
            magnitude[start:start + 256] = np.abs(scipy.fft.rfft(block, axis=1))

        # Keep only frames that carry signal (Parseval: mean square of the frame).
        window_energy = float(np.sum(self._window.astype(np.float64) ** 2))
        mean_square = 2.0 * np.sum(magnitude.astype(np.float64) ** 2, axis=1) / (
            self.N_FFT * window_energy
        )
        active = mean_square > 10.0 ** (self.ACTIVE_FRAME_DB / 10.0)
        if int(active.sum()) < self.MIN_ACTIVE_FRAMES:
            return zeros, zeros.copy()

        p5, p10, p30 = np.percentile(magnitude[active], [5.0, 10.0, 30.0], axis=0)
        tiny = 1e-12

        # --- stationary broadband floor (smoothed across frequency, capped) ----
        floor_db = 20.0 * np.log10(self.NOISE_BIAS * p10 / self._bin_ref + tiny)
        floor_db = median_filter(floor_db, size=9, mode="nearest")
        floor_db = np.minimum(floor_db, params.noise_ceiling_db)
        floor = (self._bin_ref * 10.0 ** (floor_db / 20.0)).astype(np.float32)
        floor[p10 <= tiny] = 0.0  # empty bands (e.g. above a codec's cut-off) stay untouched

        # --- time-locked narrow lines ------------------------------------------
        plateau_db = 20.0 * np.log10((p30 + tiny) / (p5 + tiny))
        level = np.sqrt(p5 * p30)
        level_db = 20.0 * np.log10(level / self._bin_ref + tiny)
        neighbourhood_db = median_filter(level_db, size=31, mode="nearest")
        excess_db = level_db - neighbourhood_db

        # Loud steady tones are music. Their spectral skirts are quiet and just as
        # steady, so the whole neighbourhood (+/-8 bins) is protected, not only the peak.
        loud = level_db > params.spur_max_level_db
        protected = maximum_filter1d(loud.astype(np.uint8), size=17, mode="constant") > 0

        seeds = (
            (excess_db >= params.spur_excess_db)
            & (plateau_db <= params.spur_plateau_db)
            & (self._freqs >= params.spur_min_hz)
            & (level_db >= self.SPUR_MIN_LEVEL_DB)
            & ~protected
        )
        # A stationary sine leaks into the adjacent bins of the Hann main lobe.
        near_seed = maximum_filter1d(seeds.astype(np.uint8), size=5, mode="constant") > 0
        members = (
            near_seed
            & ~protected
            & (plateau_db <= params.spur_plateau_db + 1.0)
            & (excess_db >= 1.5)
        )
        neighbourhood = self._bin_ref * 10.0 ** (neighbourhood_db / 20.0)
        tonal = np.where(members, np.maximum(level - neighbourhood, 0.0), 0.0).astype(np.float32)
        return floor, tonal

    def _cluster_peaks(self, tonal: np.ndarray) -> List[float]:
        """Centre frequency of each contiguous run of flagged bins."""
        peaks: List[float] = []
        indices = np.flatnonzero(tonal > 0.0)
        if indices.size == 0:
            return peaks
        splits = np.flatnonzero(np.diff(indices) > 1) + 1
        for run in np.split(indices, splits):
            best = run[int(np.argmax(tonal[run]))]
            peaks.append(float(self._freqs[best]))
        return peaks

    def _spectral_gain(self, magnitude: np.ndarray, channel: int) -> Optional[np.ndarray]:
        """Real, positive gain per time-frequency cell (``None`` = nothing to do)."""
        floor = self._noise_floor[channel]
        tonal = self._tonal_profile[channel]
        has_floor = bool(np.any(floor > 0.0))
        tonal_bins = np.flatnonzero(tonal > 0.0)
        if not has_floor and tonal_bins.size == 0:
            return None

        tiny = 1e-12
        if has_floor:
            # Decide on the *local* power (5 frames x 3 bins): a cell that belongs to
            # a note or a transient has loud neighbours and is left alone, while an
            # isolated random fluctuation of the floor is not mistaken for signal
            # (which is what produces "musical noise" in naive spectral gates).
            local_power = uniform_filter(magnitude * magnitude, size=(5, 3), mode="nearest")
            threshold = (self._channel_params[channel].over_subtraction * floor) ** 2
            gain = np.sqrt(np.clip(1.0 - threshold[None, :] / (local_power + tiny), 0.0, 1.0))
            np.maximum(gain, self._mask_floor, out=gain)
        else:
            gain = np.ones_like(magnitude)

        if tonal_bins.size:
            cells = magnitude[:, tonal_bins]
            subtracted = np.maximum(
                cells - self._tonal_alpha * tonal[tonal_bins][None, :],
                self._tonal_floor * cells,
            )
            gain[:, tonal_bins] *= subtracted / (cells + tiny)
        return gain.astype(np.float32, copy=False)

    # ----------------------------------------------------------------- stage C
    def _prepare_modulation(self, n_samples: int) -> None:
        """Build the global (whole-track) phase field and delay curve."""
        rng = np.random.default_rng(self.seed)
        amount = self.intensity
        n_frames = n_samples // self.HOP + 8  # absolute frame indices used by any chunk

        # Smooth random phase field: control points on a (time, log-frequency) grid.
        time_step = max(2, int(round(self.PHASE_CONTROL_SECONDS * self.sr / self.HOP)))
        time_knots = np.arange(0, n_frames + 2 * time_step, time_step, dtype=np.float64)
        nyquist = self.sr / 2.0
        n_bands = max(4, int(round(math.log2(nyquist / 20.0) * self.PHASE_BANDS_PER_OCTAVE)) + 1)
        band_freqs = np.geomspace(20.0, nyquist, n_bands)
        control = rng.uniform(-1.0, 1.0, size=(time_knots.size, n_bands))
        control *= self.MAX_PHASE_RAD * amount
        self._phase_time_spline = CubicSpline(time_knots, control, axis=0)

        # Cubic interpolation along log-frequency is linear in the control values,
        # so it is pre-computed once as a (bands x bins) basis matrix.
        log_bins = np.log2(np.clip(self._freqs, 20.0, nyquist))
        basis = CubicSpline(np.log2(band_freqs), np.eye(n_bands), axis=0)(log_bins)
        lo, hi = self.PHASE_TAPER_HZ
        ramp = np.clip((self._freqs - lo) / (hi - lo), 0.0, 1.0)
        taper = ramp * ramp * (3.0 - 2.0 * ramp)  # smoothstep: 0 below 80 Hz, 1 above 300 Hz
        self._phase_basis = (basis * taper[:, None]).T.astype(np.float32)

        # Smooth random delay curve d(t), in samples, starting at zero.
        knot_step = max(4, int(round(self.DRIFT_KNOT_SECONDS * self.sr / self.HOP)))
        delay_knots = np.arange(0, n_frames + 2 * knot_step, knot_step, dtype=np.float64)
        delays = rng.uniform(-1.0, 1.0, size=delay_knots.size) * self.MAX_DRIFT_SAMPLES * amount
        delays[0] = 0.0
        spline = CubicSpline(delay_knots, delays, bc_type="clamped")
        dense = np.arange(0.0, delay_knots[-1], 1.0)
        rate = float(np.abs(spline(dense, 1)).max()) / self.HOP  # delay samples per audio sample
        if rate > self.MAX_DRIFT_RATE:
            delays *= self.MAX_DRIFT_RATE / rate
            spline = CubicSpline(delay_knots, delays, bc_type="clamped")
            rate = self.MAX_DRIFT_RATE
        self._delay_spline = spline

        self.report.phase_variation_deg = math.degrees(self.MAX_PHASE_RAD * amount)
        self.report.time_drift_us = float(np.abs(delays).max()) / self.sr * 1e6
        self.report.drift_rate_cents = 1200.0 * math.log2(1.0 + rate)

    def _phase_rotor(self, first_frame: int, n_frames: int) -> np.ndarray:
        """Unit-magnitude complex rotation for frames ``first_frame ... +n_frames``."""
        frames = first_frame + np.arange(n_frames, dtype=np.float64)
        phase = self._phase_time_spline(frames).astype(np.float32) @ self._phase_basis
        phase += np.outer(self._delay_spline(frames), self._linear_phase).astype(np.float32)
        rotor = np.empty(phase.shape, dtype=np.complex64)
        rotor.real = np.cos(phase)
        rotor.imag = np.sin(phase)
        return rotor

    # ------------------------------------------------------------ chunk worker
    def _process_chunk(self, segment: np.ndarray, start: int) -> np.ndarray:
        """STFT -> spectral gain -> phase rotation -> inverse STFT, for one chunk."""
        output = np.empty_like(segment)
        rotor: Optional[np.ndarray] = None
        for channel in range(segment.shape[1]):
            spectrum = stft(segment[:, channel], self.N_FFT, self.HOP, self._window)
            gain = self._spectral_gain(np.abs(spectrum), channel)
            if gain is not None:
                spectrum *= gain
            if rotor is None:
                # Chunk starts are multiples of HOP, so absolute frame numbers are
                # exact and overlapping chunks receive the very same rotation.
                rotor = self._phase_rotor(start // self.HOP, spectrum.shape[0])
            spectrum *= rotor
            output[:, channel] = istft(spectrum, self.HOP, self._window, segment.shape[0])
        return output


# =============================================================================
# 6. MODULE 2 - MASTERING ENGINE
# =============================================================================

@dataclass(frozen=True)
class EQBand:
    """One equaliser band. ``kind``: 'highpass', 'low_shelf', 'high_shelf' or 'peak'."""

    kind: str
    freq_hz: float
    gain_db: float = 0.0
    q: float = 0.707


@dataclass(frozen=True)
class MasteringProfile:
    """
    A complete mastering recipe.

    Compressor thresholds are relative to a signal that has first been
    gain-staged to ``MasteringEngine.REFERENCE_LUFS`` (-18 LUFS), so a profile
    behaves the same whatever the level of the uploaded file.
    """

    name: str
    summary: str
    target_lufs: float
    true_peak_db: float
    eq: Tuple[EQBand, ...]
    comp_threshold_db: float
    comp_ratio: float
    comp_attack_ms: float
    comp_release_ms: float
    saturation_drive: float = 0.0       # 0 disables the saturation stage
    saturation_mix: float = 0.0
    limiter_lookahead_ms: float = 1.5
    limiter_release_ms: float = 80.0
    heavy_limiting_db: float = 5.0      # above this the UI warns about audible limiting


PROFILES: Dict[str, MasteringProfile] = {
    profile.name: profile
    for profile in (
        MasteringProfile(
            name="Standard Streaming",
            summary="Balanced, gentle glue compression for Spotify / Apple Music / YouTube.",
            target_lufs=-14.0,
            true_peak_db=-1.0,
            eq=(
                EQBand("low_shelf", 90.0, 0.8, 0.707),
                EQBand("peak", 300.0, -0.8, 0.9),
                EQBand("high_shelf", 10_000.0, 1.0, 0.707),
            ),
            comp_threshold_db=-16.0,
            comp_ratio=2.0,
            comp_attack_ms=30.0,
            comp_release_ms=200.0,
            limiter_release_ms=100.0,
            heavy_limiting_db=4.0,
        ),
        MasteringProfile(
            name="Club / Urban",
            summary="Sub-bass weight and punch: slow-attack compression lets transients hit.",
            target_lufs=-11.0,
            true_peak_db=-0.8,
            eq=(
                EQBand("low_shelf", 75.0, 2.5, 0.8),
                EQBand("peak", 55.0, 1.5, 1.2),
                EQBand("peak", 280.0, -1.5, 1.0),
                EQBand("peak", 3_500.0, 1.2, 0.8),
                EQBand("high_shelf", 11_000.0, 1.5, 0.707),
            ),
            comp_threshold_db=-18.0,
            comp_ratio=3.5,
            comp_attack_ms=35.0,
            comp_release_ms=90.0,
            limiter_release_ms=60.0,
            heavy_limiting_db=6.0,
        ),
        MasteringProfile(
            name="Warm / Analog",
            summary="Fuller low mids, softened top end and light tube-style harmonic saturation.",
            target_lufs=-13.0,
            true_peak_db=-1.0,
            eq=(
                EQBand("low_shelf", 110.0, 1.5, 0.707),
                EQBand("peak", 220.0, 0.8, 0.7),
                EQBand("peak", 3_000.0, -0.8, 0.8),
                EQBand("high_shelf", 9_000.0, -1.5, 0.707),
            ),
            comp_threshold_db=-17.0,
            comp_ratio=2.5,
            comp_attack_ms=25.0,
            comp_release_ms=250.0,
            saturation_drive=2.2,
            saturation_mix=0.55,
            limiter_release_ms=120.0,
            heavy_limiting_db=4.0,
        ),
        MasteringProfile(
            name="Transparent / Orchestral",
            summary="No EQ, almost zero compression (1.15:1): dynamics are left intact.",
            target_lufs=-16.0,
            true_peak_db=-1.5,
            eq=(),
            comp_threshold_db=-10.0,
            comp_ratio=1.15,
            comp_attack_ms=60.0,
            comp_release_ms=400.0,
            limiter_lookahead_ms=3.0,
            limiter_release_ms=200.0,
            heavy_limiting_db=3.0,
        ),
        MasteringProfile(
            name="Radio / Voice",
            summary="Tight 5:1 compression and presence lift for intelligibility "
                    "(true-peak ceiling defaults to -1.0 dBTP).",
            target_lufs=-16.0,
            true_peak_db=-1.0,
            eq=(
                EQBand("highpass", 80.0),
                EQBand("highpass", 80.0),
                EQBand("peak", 250.0, -2.0, 1.0),
                EQBand("peak", 3_200.0, 2.5, 0.8),
                EQBand("high_shelf", 8_000.0, 1.5, 0.707),
            ),
            comp_threshold_db=-24.0,
            comp_ratio=5.0,
            comp_attack_ms=4.0,
            comp_release_ms=90.0,
            limiter_release_ms=70.0,
            heavy_limiting_db=6.0,
        ),
    )
}


@dataclass
class MasteringReport:
    """What the mastering engine measured and applied."""

    profile: str
    target_lufs: float
    target_true_peak_db: float
    input_lufs: float = float("nan")
    output_lufs: float = float("nan")
    output_true_peak_db: float = float("nan")
    gain_db: float = 0.0                # gain applied after the EQ/dynamics chain
    limiter_max_reduction_db: float = 0.0
    iterations: int = 0
    warnings: List[str] = field(default_factory=list)


def analog_saturate(audio: np.ndarray, sample_rate: int, drive: float, mix: float) -> np.ndarray:
    """
    Light harmonic saturation: an asymmetric ``tanh`` curve (odd *and* even
    harmonics, tube-like) blended in parallel with the dry signal.

    * unity gain for small signals, so quiet passages are untouched;
    * the curve runs at 2x the sample rate to keep aliasing out of the audio band;
    * the small DC term created by the asymmetry is removed afterwards.
    """
    if drive <= 0.0 or mix <= 0.0:
        return audio
    bias = 0.08
    offset = math.tanh(drive * bias)
    slope = drive * (1.0 - offset * offset)  # derivative of the curve at zero

    def _shape(segment: np.ndarray, _start: int) -> np.ndarray:
        upsampled = sps.resample_poly(segment.astype(np.float64), 2, 1, axis=0)
        wet = (np.tanh(drive * (upsampled + bias)) - offset) / slope
        wet = sps.resample_poly(wet, 1, 2, axis=0)[:segment.shape[0]]
        return ((1.0 - mix) * segment + mix * wet).astype(np.float32)

    shaped = process_in_chunks(audio, _shape, chunk_size=1 << 19, overlap=2048)
    dc_block = sps.butter(2, 8.0, btype="highpass", fs=sample_rate, output="sos")
    for channel in range(shaped.shape[1]):
        shaped[:, channel] = sps.sosfiltfilt(dc_block, shaped[:, channel].astype(np.float64))
    return shaped


def _release_envelope(reduction: np.ndarray, sample_rate: int, release_ms: float) -> np.ndarray:
    """
    Instant-attack / exponential-release follower:
    ``r[n] = max(reduction[n], a * r[n-1])``.

    Vectorised with a running maximum of ``reduction[j] * a**(-j)`` in blocks
    short enough for the exponent to stay well inside float64 range.
    """
    tau = max(1.0, sample_rate * release_ms / 1000.0)
    block = int(min(reduction.size, max(1024.0, 40.0 * tau)))
    index = np.arange(block, dtype=np.float64)
    decay = np.exp(-index / tau)
    growth = np.exp(index / tau)
    coefficient = math.exp(-1.0 / tau)

    output = np.empty_like(reduction)
    carry = 0.0
    for start in range(0, reduction.size, block):
        segment = reduction[start:start + block].astype(np.float64)
        count = segment.size
        running = np.maximum.accumulate(segment * growth[:count])
        np.maximum(running, carry * coefficient, out=running)
        result = running * decay[:count]
        output[start:start + count] = result
        carry = float(result[-1])
    return output


def limiter_gain_curve(
    envelope: np.ndarray,
    pre_gain: float,
    ceiling: float,
    sample_rate: int,
    lookahead_ms: float,
    release_ms: float,
    hold_ms: float = 12.0,
) -> Optional[np.ndarray]:
    """
    Gain curve of a look-ahead true-peak brickwall limiter.

    ``envelope`` is the true-peak envelope of the signal *before* ``pre_gain``.
    Steps: required gain per sample -> minimum over the look-ahead window ->
    peak hold -> exponential release -> moving average over the look-ahead
    window. Every averaged value is a mean of minima that all include the
    sample itself, and hold/release only ever add reduction, so the final gain
    can never exceed what a sample requires: the ceiling is guaranteed while
    the gain moves smoothly into each peak.

    The short hold keeps the gain steady between successive crests of a bass
    note (down to ~42 Hz), which avoids the low-frequency distortion a fast
    release would otherwise cause.

    Returns ``None`` when no limiting is needed.
    """
    if float(envelope.max()) * pre_gain <= ceiling:
        return None
    # float32 throughout (the 0.05 dB ceiling margin dwarfs its rounding error)
    required = np.float32(ceiling / pre_gain) / np.maximum(envelope, np.float32(1e-12))
    np.minimum(required, np.float32(1.0), out=required)
    window = max(3, int(round(sample_rate * lookahead_ms / 1000.0)) | 1)
    reduction = minimum_filter1d(required, size=window, mode="nearest")
    del required
    np.subtract(np.float32(1.0), reduction, out=reduction)
    hold = int(round(sample_rate * hold_ms / 1000.0))
    if hold > 1:
        size = 2 * (hold // 2) + 1
        # positive origin = trailing window: the reduction is held *after* each peak
        reduction = maximum_filter1d(reduction, size=size, origin=size // 2, mode="nearest")
    reduction = _release_envelope(reduction, sample_rate, release_ms)
    np.subtract(np.float32(1.0), reduction, out=reduction)  # reduction -> gain
    return uniform_filter1d(reduction, size=window, mode="nearest").astype(np.float32, copy=False)


class MasteringEngine:
    """
    Automated mastering chain.

        1. measure integrated loudness (pyloudnorm)
        2. gain-stage to -18 LUFS (pyloudnorm) so the dynamics behave consistently
        3. EQ + compressor (pedalboard)
        4. optional harmonic saturation ("Warm / Analog")
        5. loudness normalisation to the profile target + look-ahead true-peak
           limiter, iterated until the measured loudness matches the target
        6. final true-peak verification (and trim if ever needed)

    pedalboard's built-in ``Limiter`` is deliberately not used for the ceiling:
    it works on sample peaks, applies its own make-up gain and ends in a hard
    clipper at 0 dBFS, so it cannot hold a dBTP target. Step 5 uses a dedicated
    4x-oversampled look-ahead limiter instead.
    """

    REFERENCE_LUFS = -18.0
    LUFS_TOLERANCE = 0.1
    MAX_ITERATIONS = 8
    CEILING_MARGIN_DB = 0.05         # limiter aims slightly under the stated ceiling
    MAX_REASONABLE_REDUCTION_DB = 14.0

    def __init__(self, sample_rate: int, profile: MasteringProfile) -> None:
        if sample_rate <= 0:
            raise ProcessingError("Invalid sample rate.")
        self.sr = int(sample_rate)
        self.profile = profile

    def build_board(self) -> Pedalboard:
        """The pedalboard effects chain for this profile: EQ bands, then the compressor."""
        plugins = []
        for band in self.profile.eq:
            if band.kind == "highpass":
                plugins.append(HighpassFilter(cutoff_frequency_hz=band.freq_hz))
            elif band.kind == "low_shelf":
                plugins.append(
                    LowShelfFilter(cutoff_frequency_hz=band.freq_hz, gain_db=band.gain_db, q=band.q)
                )
            elif band.kind == "high_shelf":
                plugins.append(
                    HighShelfFilter(cutoff_frequency_hz=band.freq_hz, gain_db=band.gain_db, q=band.q)
                )
            elif band.kind == "peak":
                plugins.append(
                    PeakFilter(cutoff_frequency_hz=band.freq_hz, gain_db=band.gain_db, q=band.q)
                )
            else:
                raise ProcessingError(f"Unknown EQ band type '{band.kind}'.")
        plugins.append(
            Compressor(
                threshold_db=self.profile.comp_threshold_db,
                ratio=self.profile.comp_ratio,
                attack_ms=self.profile.comp_attack_ms,
                release_ms=self.profile.comp_release_ms,
            )
        )
        return Pedalboard(plugins)

    def process(
        self, audio: np.ndarray, progress: Optional[ProgressFn] = None
    ) -> Tuple[np.ndarray, MasteringReport]:
        """Master ``audio``. Returns ``(mastered float32 audio, report)``."""
        report_progress = progress or _noop_progress
        profile = self.profile
        source = as_audio_array(audio)
        report = MasteringReport(
            profile=profile.name,
            target_lufs=profile.target_lufs,
            target_true_peak_db=profile.true_peak_db,
        )

        # 1-2. measure and gain-stage ------------------------------------------
        report_progress(0.03, "Mastering: measuring input loudness")
        input_lufs = measure_lufs(source, self.sr)
        report.input_lufs = input_lufs
        if not math.isfinite(input_lufs):
            raise ProcessingError(
                "The track is too quiet for a loudness measurement (below the -70 LUFS gate)."
            )
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")  # pyloudnorm warns about peaks; the limiter handles them
            staged = pyln.normalize.loudness(source, input_lufs, self.REFERENCE_LUFS)
        staged = np.asarray(staged, dtype=np.float32)

        # 3. EQ + compression (pedalboard works on channels-first float32) ------
        report_progress(0.12, f"Mastering: EQ and compression ({profile.name})")
        try:
            board = self.build_board()
            processed = board(np.ascontiguousarray(staged.T), self.sr)
        except ProcessingError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise ProcessingError(f"The effects chain failed ({exc}).") from exc
        processed = np.ascontiguousarray(np.asarray(processed, dtype=np.float32).T)
        if processed.shape != staged.shape:
            raise ProcessingError("The effects chain returned audio with an unexpected shape.")
        del staged

        # 4. saturation ---------------------------------------------------------
        if profile.saturation_drive > 0.0 and profile.saturation_mix > 0.0:
            report_progress(0.28, "Mastering: harmonic saturation")
            processed = analog_saturate(
                processed, self.sr, profile.saturation_drive, profile.saturation_mix
            )
        if not np.isfinite(processed).all():
            raise ProcessingError("The effects chain produced invalid samples.")

        # 5. loudness target + true-peak limiter --------------------------------
        mastered = self._normalise_and_limit(processed, report, sub_progress(report_progress, 0.36, 0.90))

        # 6. verification -------------------------------------------------------
        report_progress(0.93, "Mastering: verifying true peak")
        true_peak = measure_true_peak_db(mastered)
        if true_peak > profile.true_peak_db + 0.005:
            trim_db = profile.true_peak_db - true_peak
            mastered = (mastered * np.float32(db_to_lin(trim_db))).astype(np.float32)
            report.output_lufs += trim_db
            report.gain_db += trim_db
            true_peak = profile.true_peak_db
        report.output_true_peak_db = true_peak

        if abs(report.output_lufs - profile.target_lufs) > 0.3:
            report.warnings.append(
                f"Loudness landed at {report.output_lufs:.1f} LUFS instead of "
                f"{profile.target_lufs:.1f} LUFS: this material cannot reach the target "
                "under the true-peak ceiling without excessive limiting."
            )
        if report.limiter_max_reduction_db > profile.heavy_limiting_db:
            report.warnings.append(
                f"The limiter had to remove up to {report.limiter_max_reduction_db:.1f} dB on the "
                "loudest peaks to reach this target. If it sounds squashed, pick a quieter profile."
            )
        report_progress(1.0, "Mastering: done")
        return np.ascontiguousarray(mastered, dtype=np.float32), report

    def _normalise_and_limit(
        self, audio: np.ndarray, report: MasteringReport, progress: ProgressFn
    ) -> np.ndarray:
        """
        Find the gain that makes the *limited* signal hit the loudness target.

        Limiting lowers loudness, so the gain is refined iteratively (secant
        steps). The true-peak envelope is computed once and simply rescaled.
        """
        profile = self.profile
        progress(0.02, "Mastering: true-peak analysis")
        envelope = true_peak_envelope(audio)
        base_lufs = measure_lufs(audio, self.sr)
        if not math.isfinite(base_lufs):
            raise ProcessingError("The processed signal is too quiet to normalise.")

        ceiling = db_to_lin(profile.true_peak_db - self.CEILING_MARGIN_DB)
        gain_db = profile.target_lufs - base_lufs
        history: List[Tuple[float, float]] = []
        mastered = audio
        loudness = base_lufs
        reduction_db = 0.0

        for iteration in range(1, self.MAX_ITERATIONS + 1):
            progress(
                0.10 + 0.85 * iteration / self.MAX_ITERATIONS,
                f"Mastering: loudness normalisation and true-peak limiting (pass {iteration})",
            )
            gain = db_to_lin(gain_db)
            curve = limiter_gain_curve(
                envelope, gain, ceiling, self.sr,
                profile.limiter_lookahead_ms, profile.limiter_release_ms,
            )
            if curve is None:
                mastered = (audio * np.float32(gain)).astype(np.float32)
                reduction_db = 0.0
            else:
                mastered = (audio * (curve * np.float32(gain))[:, None]).astype(np.float32)
                reduction_db = -lin_to_db(float(curve.min()))
            loudness = measure_lufs(mastered, self.sr)
            report.iterations = iteration
            history.append((gain_db, loudness))

            error = profile.target_lufs - loudness
            if abs(error) <= self.LUFS_TOLERANCE:
                break
            if reduction_db > self.MAX_REASONABLE_REDUCTION_DB and error > 0.0:
                break  # pushing harder would only add distortion

            slope = 1.0
            if len(history) >= 2:
                (gain_a, loud_a), (gain_b, loud_b) = history[-2], history[-1]
                if abs(gain_b - gain_a) > 1e-3:
                    slope = (loud_b - loud_a) / (gain_b - gain_a)
            slope = min(max(slope, 0.2), 1.0)
            gain_db += min(max(error / slope, -6.0), 6.0)

        report.output_lufs = loudness
        report.gain_db = gain_db
        report.limiter_max_reduction_db = reduction_db
        progress(1.0, "Mastering: loudness target reached")
        return mastered


# =============================================================================
# 7. VISUALISATION
# =============================================================================

# Chart colours: one dark chart surface that reads well inside both Streamlit
# themes, a single-hue (blue) sequential ramp for level, and a fixed colour per
# version of the track.
CHART_SURFACE = "#1a1a19"
INK_PRIMARY = "#f0efec"
INK_SECONDARY = "#c3c2b7"
INK_MUTED = "#898781"
GRID_COLOR = "#2c2c2a"
AXIS_COLOR = "#383835"
SERIES_COLORS = {"Original": "#3987e5", "Cleaned": "#d95926", "Mastered": "#199e70"}
LEVEL_CMAP = LinearSegmentedColormap.from_list(
    "htd_level",
    ["#1a1a19", "#0d366b", "#184f95", "#256abf", "#3987e5", "#6da7ec", "#9ec5f4", "#cde2fb"],
)
SPECTROGRAM_DB_RANGE = (-110.0, -10.0)
SPECTRUM_BANDS = (
    ("Sub (20-60 Hz)", 20.0, 60.0),
    ("Bass (60-250 Hz)", 60.0, 250.0),
    ("Low mids (250-500 Hz)", 250.0, 500.0),
    ("Mids (500 Hz-2 kHz)", 500.0, 2_000.0),
    ("High mids (2-6 kHz)", 2_000.0, 6_000.0),
    ("Highs (6-12 kHz)", 6_000.0, 12_000.0),
    ("Air (12-20 kHz)", 12_000.0, 20_000.0),
)


@dataclass
class SpectrogramData:
    """A display-resolution spectrogram plus the long-term average spectrum."""

    level_db: np.ndarray        # (n_bins, n_columns) dB re. full-scale sine
    freqs: np.ndarray           # (n_bins,) Hz
    duration_s: float
    average_psd: np.ndarray     # long-term power spectral density (Welch, 2.7 Hz bins)
    average_freqs: np.ndarray   # frequencies of ``average_psd`` (Hz)


def compute_spectrogram(
    audio: np.ndarray, sample_rate: int, n_fft: int = 2048, max_columns: int = 1100
) -> SpectrogramData:
    """
    Spectrogram of the mono sum. All STFT frames are computed (50 % overlap) and
    their power is averaged into at most ``max_columns`` time columns, so the
    picture represents the whole track while memory use stays small.
    """
    mono = audio.mean(axis=1).astype(np.float32)
    if mono.size < n_fft:
        mono = np.pad(mono, (0, n_fft - mono.size))
    hop = n_fft // 2
    frames = np.lib.stride_tricks.sliding_window_view(mono, n_fft)[::hop]
    n_frames = frames.shape[0]
    pool = max(1, int(math.ceil(n_frames / max_columns)))
    n_columns = max(1, n_frames // pool)

    window = sps.get_window("hann", n_fft, fftbins=True).astype(np.float32)
    reference = float(window.sum() / 2.0) ** 2
    power = np.empty((n_fft // 2 + 1, n_columns), dtype=np.float32)
    columns_per_block = max(1, 512 // pool)
    for first in range(0, n_columns, columns_per_block):
        last = min(first + columns_per_block, n_columns)
        block = frames[first * pool:last * pool] * window
        spectrum = scipy.fft.rfft(block, axis=1)
        energy = spectrum.real ** 2 + spectrum.imag ** 2
        available = energy.shape[0] // pool
        pooled = energy[:available * pool].reshape(available, pool, -1).mean(axis=1)
        power[:, first:first + available] = pooled.T / reference
        if available < last - first:  # only possible on the very last block
            power[:, first + available:last] = power[:, [first + available - 1]]

    # Long-term average spectrum at a much finer frequency resolution, so the
    # tonal-balance curve and the band table stay accurate in the low end.
    segment = int(min(16_384, mono.size))
    average_freqs, average_psd = sps.welch(
        mono, fs=sample_rate, window="hann", nperseg=segment, noverlap=segment // 2,
        detrend=False, scaling="density",
    )

    return SpectrogramData(
        level_db=10.0 * np.log10(np.maximum(power, 1e-14)),
        freqs=np.fft.rfftfreq(n_fft, 1.0 / sample_rate),
        duration_s=audio.shape[0] / float(sample_rate),
        average_psd=np.asarray(average_psd, dtype=np.float64),
        average_freqs=np.asarray(average_freqs, dtype=np.float64),
    )


def _log_frequency_rows(
    data: SpectrogramData, n_rows: int = 320, f_min: float = 20.0
) -> Tuple[np.ndarray, List[float], List[str]]:
    """Re-bin a linear-frequency spectrogram onto logarithmically spaced rows."""
    f_max = float(data.freqs[-1])
    edges = np.geomspace(f_min, f_max, n_rows + 1)
    centres = np.sqrt(edges[:-1] * edges[1:])
    lower = np.searchsorted(data.freqs, edges[:-1], side="left")
    upper = np.searchsorted(data.freqs, edges[1:], side="left")
    rows = np.empty((n_rows, data.level_db.shape[1]), dtype=np.float32)
    bin_width = float(data.freqs[1] - data.freqs[0])
    for row in range(n_rows):
        if upper[row] > lower[row]:
            # Several bins fall in this row: keep the loudest so narrow lines stay visible.
            rows[row] = data.level_db[lower[row]:upper[row]].max(axis=0)
        else:
            position = min(centres[row] / bin_width, data.freqs.size - 1.001)
            below = int(position)
            fraction = position - below
            rows[row] = (1.0 - fraction) * data.level_db[below] + fraction * data.level_db[below + 1]

    tick_freqs = [f for f in (20, 50, 100, 200, 500, 1_000, 2_000, 5_000, 10_000, 20_000) if f <= f_max]
    positions = [n_rows * math.log(f / f_min) / math.log(f_max / f_min) for f in tick_freqs]
    labels = [f"{f // 1000}k" if f >= 1000 else str(f) for f in tick_freqs]
    return rows, positions, labels


def _style_axes(ax) -> None:
    """Recessive chart chrome: muted ticks, hairline spines, no top/right box."""
    ax.set_facecolor(CHART_SURFACE)
    ax.tick_params(colors=INK_MUTED, labelsize=9, length=3, width=0.8)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(AXIS_COLOR)
        ax.spines[side].set_linewidth(0.8)


def _format_time(seconds: float, _position: int = 0) -> str:
    seconds = max(0.0, float(seconds))
    return f"{int(seconds // 60)}:{int(seconds % 60):02d}"


def build_spectrogram_figure(spectra: Dict[str, SpectrogramData], scale: str = "log") -> Figure:
    """Stacked spectrograms (one per version) sharing the time axis and the colour scale."""
    names = list(spectra)
    figure = Figure(
        figsize=(12.0, 2.7 * len(names) + 0.5), dpi=110,
        facecolor=CHART_SURFACE, layout="constrained",
    )
    axes = figure.subplots(len(names), 1, sharex=True, squeeze=False)[:, 0]
    v_min, v_max = SPECTROGRAM_DB_RANGE
    image = None
    for ax, name in zip(axes, names):
        data = spectra[name]
        if scale == "log":
            rows, positions, labels = _log_frequency_rows(data)
            image = ax.imshow(
                rows, origin="lower", aspect="auto", cmap=LEVEL_CMAP, vmin=v_min, vmax=v_max,
                extent=(0.0, data.duration_s, 0.0, rows.shape[0]), interpolation="nearest",
            )
            ax.set_yticks(positions)
            ax.set_yticklabels(labels)
            ax.set_ylabel("Frequency (Hz)", color=INK_SECONDARY, fontsize=9)
        else:
            image = ax.imshow(
                data.level_db, origin="lower", aspect="auto", cmap=LEVEL_CMAP, vmin=v_min, vmax=v_max,
                extent=(0.0, data.duration_s, 0.0, float(data.freqs[-1]) / 1000.0),
                interpolation="nearest",
            )
            ax.set_ylabel("Frequency (kHz)", color=INK_SECONDARY, fontsize=9)
        ax.set_title(name, loc="left", color=INK_PRIMARY, fontsize=11, fontweight="bold")
        _style_axes(ax)
    axes[-1].set_xlabel("Time (min:s)", color=INK_SECONDARY, fontsize=9)
    axes[-1].xaxis.set_major_formatter(FuncFormatter(_format_time))

    colorbar = figure.colorbar(image, ax=list(axes), pad=0.015, fraction=0.03, aspect=40)
    colorbar.set_label("Level (dBFS)", color=INK_SECONDARY, fontsize=9)
    colorbar.ax.tick_params(colors=INK_MUTED, labelsize=9, length=3, width=0.8)
    colorbar.outline.set_edgecolor(AXIS_COLOR)
    return figure


def _third_octave_smooth(data: SpectrogramData, centres: np.ndarray) -> np.ndarray:
    """Average spectral density in a third-octave band around each centre frequency."""
    half_band = 2.0 ** (1.0 / 6.0)
    lower = np.searchsorted(data.average_freqs, centres / half_band, side="left")
    upper = np.searchsorted(data.average_freqs, centres * half_band, side="right")
    smoothed = np.empty(centres.size, dtype=np.float64)
    for index in range(centres.size):
        lo = int(lower[index])
        hi = int(upper[index])
        if hi - lo >= 2:
            smoothed[index] = data.average_psd[lo:hi].mean()
        else:  # band narrower than the bin spacing: interpolate instead
            smoothed[index] = np.interp(centres[index], data.average_freqs, data.average_psd)
    return np.maximum(smoothed, 1e-30)


def build_tonal_change_figure(
    spectra: Dict[str, SpectrogramData], loudness: Dict[str, float]
) -> Optional[Figure]:
    """
    How each processing step changed the tonal balance, relative to the original.

    Curves are third-octave smoothed and loudness-matched (the overall LUFS
    difference is subtracted), so they show *tone*, not volume.
    """
    reference = spectra.get("Original")
    if reference is None or not math.isfinite(loudness.get("Original", float("nan"))):
        return None
    f_max = min(18_000.0, 0.9 * float(reference.average_freqs[-1]))
    centres = np.geomspace(30.0, f_max, 140)
    base_db = 10.0 * np.log10(_third_octave_smooth(reference, centres))

    curves: Dict[str, np.ndarray] = {}
    for name in ("Cleaned", "Mastered"):
        if name not in spectra or not math.isfinite(loudness.get(name, float("nan"))):
            continue
        level_db = 10.0 * np.log10(_third_octave_smooth(spectra[name], centres))
        curves[name] = level_db - base_db - (loudness[name] - loudness["Original"])
    if not curves:
        return None

    figure = Figure(figsize=(12.0, 3.6), dpi=110, facecolor=CHART_SURFACE, layout="constrained")
    ax = figure.subplots()
    _style_axes(ax)
    ax.set_xscale("log")
    ax.grid(True, which="major", color=GRID_COLOR, linewidth=0.8)
    ax.set_axisbelow(True)
    ax.axhline(0.0, color=AXIS_COLOR, linewidth=1.2)

    extent = max(float(np.abs(curve).max()) for curve in curves.values())
    limit = float(min(18.0, max(3.0, math.ceil(extent + 1.0))))
    for name, curve in curves.items():
        ax.plot(centres, np.clip(curve, -limit, limit), color=SERIES_COLORS[name],
                linewidth=2.0, label=name, solid_capstyle="round")

    # Direct labels at the right-hand end, nudged apart if the curves finish together.
    ends = sorted(((float(np.clip(c[-1], -limit, limit)), n) for n, c in curves.items()))
    minimum_gap = 2.0 * limit * 0.09
    placed: List[Tuple[float, str]] = []
    for value, name in ends:
        if placed and value - placed[-1][0] < minimum_gap:
            value = placed[-1][0] + minimum_gap
        placed.append((value, name))
    for value, name in placed:
        ax.annotate(name, xy=(centres[-1], value), xytext=(6, 0), textcoords="offset points",
                    color=INK_PRIMARY, fontsize=9, va="center", annotation_clip=False)

    ticks = [f for f in (50, 100, 200, 500, 1_000, 2_000, 5_000, 10_000) if f <= f_max]
    ax.set_xticks(ticks)
    ax.set_xticklabels([f"{f // 1000}k" if f >= 1000 else str(f) for f in ticks])
    ax.minorticks_off()
    ax.set_xlim(centres[0], centres[-1])
    ax.set_ylim(-limit, limit)
    ax.set_xlabel("Frequency (Hz)", color=INK_SECONDARY, fontsize=9)
    ax.set_ylabel("Change vs. original (dB)", color=INK_SECONDARY, fontsize=9)
    ax.set_title("Tonal balance change (loudness-matched, third-octave smoothing)",
                 loc="left", color=INK_PRIMARY, fontsize=11, fontweight="bold")
    legend = ax.legend(loc="upper left", frameon=False, fontsize=9, ncols=len(curves))
    for text in legend.get_texts():
        text.set_color(INK_SECONDARY)
    return figure


def band_level_rows(spectra: Dict[str, SpectrogramData]) -> List[Dict[str, object]]:
    """Table view of the average spectrum: RMS level per frequency band, per version."""
    rows: List[Dict[str, object]] = []
    for label, low, high in SPECTRUM_BANDS:
        row: Dict[str, object] = {"Band": label}
        for name, data in spectra.items():
            mask = (data.average_freqs >= low) & (data.average_freqs < high)
            bin_width = float(data.average_freqs[1] - data.average_freqs[0])
            power = float(data.average_psd[mask].sum()) * bin_width if mask.any() else 0.0
            row[f"{name} (dBFS RMS)"] = round(10.0 * math.log10(max(power, 1e-20)), 1)
        rows.append(row)
    return rows

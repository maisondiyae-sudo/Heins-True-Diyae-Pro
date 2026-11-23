"""
One track, end to end: decode -> Anti-Parasite Filter -> mastering -> metrics
-> analysis -> float master cache + 16-bit previews, then exports.

Same processing order, same seed and same settings as the web version, so a
file gives the same master on the desktop as it did online - when no
``analog_seed`` is given. Since 2.2.2 the desktop app gives every track its own
analog tolerance seed (Anti-Parasite Filter only), kept for the track's whole life.
No Qt here: the UI calls these functions from a worker thread.
"""

from __future__ import annotations

import hashlib
import secrets
import shutil
import threading
import time
from dataclasses import dataclass, field
from dataclasses import replace as dataclass_replace
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

import soundfile as sf

from . import core
from .core import (
    AntiParasiteFilter,
    AntiParasiteReport,
    AudioMetrics,
    MasteringEngine,
    MasteringReport,
    ProcessingError,
    SpectrogramData,
    compute_spectrogram,
    load_audio,
    measure_metrics,
    sub_progress,
)
from .presets import MasterSettings
from .stereo import analyse_stereo
from .reference import (
    MatchReport,
    ReferenceProfile,
    apply_fir,
    design_fir,
    match_curve,
    match_error_db,
)
from .cut import CutReport, apply_cut
from .trim import TrimReport, auto_trim

# Desktop files are often larger than web uploads (long 24-bit / 96 kHz WAVs).
core.MAX_UPLOAD_MB = 2048

ProgressFn = Callable[[float, str], None]

# Analog tolerance seeds (Anti-Parasite Filter): one per track, fixed for its whole life
# (previews, exports, projects), so what is exported is exactly what was heard.
ANALOG_SEED_BITS = 31            # fits a signed 32-bit integer (JSON / QSettings friendly)


def new_analog_seed() -> int:
    """A fresh random seed for a track's analog "console channel" (0 ... 2**31 - 1)."""
    return secrets.randbits(ANALOG_SEED_BITS)


def parse_analog_seed(value: object) -> Optional[int]:
    """A seed read from a project / snapshot, or ``None`` when absent or unusable
    (the caller then keeps the track's freshly generated seed)."""
    if isinstance(value, bool):
        return None
    if isinstance(value, str) and value.strip().isdigit():
        value = int(value.strip())
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    if isinstance(value, int) and 0 <= value < (1 << 63):
        return value
    return None


class Cancelled(Exception):
    """The user stopped the batch."""


@dataclass
class TrackResult:
    """Everything known about one processed track."""

    source: Path
    ok: bool = False
    cancelled: bool = False
    error: str = ""
    error_detail: str = ""
    settings: Optional[MasterSettings] = None
    duration_s: float = 0.0
    channels: int = 0
    native_sample_rate: int = 0
    notes: List[str] = field(default_factory=list)
    original_metrics: Optional[AudioMetrics] = None
    cleaned_metrics: Optional[AudioMetrics] = None
    mastered_metrics: Optional[AudioMetrics] = None
    clean_report: Optional[AntiParasiteReport] = None
    master_report: Optional[MasteringReport] = None
    spectra: Dict[str, SpectrogramData] = field(default_factory=dict)
    work_dir: Optional[Path] = None
    master_cache: Optional[Path] = None            # 32-bit float WAV of the master (listening + export)
    exports: Dict[Tuple[str, str], object] = field(default_factory=dict)   # slot -> delivery.ExportRecord
    export_error: str = ""
    trim: Optional[TrimReport] = None
    match: Optional[MatchReport] = None
    stereo: Dict[str, object] = field(default_factory=dict)   # 'original' / 'mastered' -> stereo.StereoReport
    cut: Optional[CutReport] = None                 # manual start / end cut (None = whole track)
    analog_seed: Optional[int] = None               # Anti-Parasite analog tolerance seed (None = off)
    elapsed_s: float = 0.0

    # ------------------------------------------------------------------ state
    def is_current(self, settings: MasterSettings) -> bool:
        return self.ok and self.settings is not None and self.settings.key() == settings.key()

    @property
    def on_target(self) -> bool:
        report = self.master_report
        if not self.ok or report is None:
            return False
        return (abs(report.output_lufs - report.target_lufs) <= 0.3
                and report.output_true_peak_db <= report.target_true_peak_db + 0.01)

    def cut_key(self) -> Optional[Tuple[float, float]]:
        return None if self.cut is None else (round(self.cut.start_s, 3), round(self.cut.end_s, 3))

    def master_offset_samples(self) -> int:
        """Where the master starts on the original's timeline, in samples at 44.1 kHz
        (manual cut + auto-trim)."""
        offset = self.cut.start_samples if self.cut is not None else 0
        if self.trim is not None:
            offset += self.trim.offset_samples
        return int(offset)

    def preview_offset_ms(self, which: str) -> int:
        """Where a preview starts on the original's timeline (a cut / trimmed master starts later)."""
        if which == "mastered":
            return int(round(self.master_offset_samples() / 44.1))
        return 0

    def cache_size(self) -> int:
        """Bytes of the temporary work folder (master cache, playback copies)."""
        if self.work_dir is None or not self.work_dir.exists():
            return 0
        total = 0
        for path in self.work_dir.rglob("*"):
            try:
                total += path.stat().st_size
            except OSError:
                pass
        return total

    def cleanup(self) -> None:
        """Delete the temporary files (exports are the user's and are kept)."""
        if self.work_dir is not None:
            shutil.rmtree(self.work_dir, ignore_errors=True)


def _guarded(progress: Optional[ProgressFn], cancel: Optional[threading.Event]) -> ProgressFn:
    """Progress callback that also stops the DSP as soon as the user cancels."""
    def _inner(fraction: float, message: str) -> None:
        if cancel is not None and cancel.is_set():
            raise Cancelled()
        if progress is not None:
            progress(fraction, message)
    return _inner


def master_track(source: Path, settings: MasterSettings, work_root: Path,
                 progress: Optional[ProgressFn] = None,
                 cancel: Optional[threading.Event] = None,
                 reference: Optional[ReferenceProfile] = None,
                 cut: Optional[Tuple[float, float]] = None,
                 analog_seed: Optional[int] = None) -> TrackResult:
    """Decode, clean and master ``source``. Raises core errors or ``Cancelled``.

    Order: [manual cut + micro-fades] -> Anti-Parasite Filter -> [reference match EQ]
    -> mastering engine (unchanged) -> [auto-trim + micro-fades] -> metrics,
    analysis, cache, preview. Without ``cut`` (start_s, end_s) the audio reaches
    the engine untouched, exactly as before.

    ``analog_seed`` (optional) turns on the Anti-Parasite Filter's analog tolerance
    modeling with that seed; ``None`` keeps the filter bit-identical to v1.0. It
    only changes the Anti-Parasite stage - the rest of the chain is untouched.
    """
    if settings.reference_id and (reference is None or reference.ident != settings.reference_id):
        raise ProcessingError("The reference track is not loaded any more - load it again.")
    report = _guarded(progress, cancel)
    started = time.perf_counter()
    result = TrackResult(source=source, settings=settings, analog_seed=analog_seed)

    report(0.0, "Decoding")
    data = source.read_bytes()
    audio = load_audio(data, source.name)
    seed = int.from_bytes(hashlib.sha256(data).digest()[:8], "little")
    digest = hashlib.sha1(str(source).encode("utf-8")).hexdigest()[:10]
    del data
    sample_rate = audio.sample_rate
    result.duration_s = audio.duration_s                  # the whole original (the seek bars' timeline)
    result.channels = int(audio.samples.shape[1])
    samples = audio.samples
    if cut is not None:
        try:
            samples, result.cut = apply_cut(samples, sample_rate, cut[0], cut[1])
        except ValueError as exc:
            raise ProcessingError(str(exc)) from exc
    result.native_sample_rate = audio.native_sample_rate
    result.notes = list(audio.notes)

    work_dir = work_root / f"track-{digest}-{int(time.time() * 1000)}"
    work_dir.mkdir(parents=True, exist_ok=True)
    result.work_dir = work_dir
    try:
        report(0.03, "Measuring the original")
        result.original_metrics = measure_metrics(samples, sample_rate)
        result.stereo["original"] = analyse_stereo(samples, sample_rate)   # phase / mono check (numpy only)
        original_spectrum = compute_spectrogram(samples, sample_rate)

        cleaner = AntiParasiteFilter(sample_rate, settings.intensity_pct / 100.0, seed=seed,
                                     analog_seed=analog_seed)
        cleaned = cleaner.process(samples, sub_progress(report, 0.08, 0.45))
        result.clean_report = cleaner.report
        del audio, samples

        report(0.46, "Measuring the cleaned version")
        result.cleaned_metrics = measure_metrics(cleaned, sample_rate)
        cleaned_spectrum = compute_spectrogram(cleaned, sample_rate)

        profile = settings.profile()
        if settings.reference_id and reference is not None:
            match = MatchReport(reference.name, 0.0, 0.0, match_error_db(cleaned_spectrum, reference))
            if settings.match_eq:
                report(0.47, "Matching the reference tonal balance")
                curve = match_curve(cleaned_spectrum, reference, settings.match_strength / 100.0)
                cleaned = apply_fir(cleaned, design_fir(curve, sample_rate)).astype("float32")
                profile = dataclass_replace(profile, eq=())       # the match EQ replaces the recipe EQ
                match.eq_max_boost_db, match.eq_max_cut_db = float(curve.max()), float(curve.min())
            if settings.match_loudness:
                profile = dataclass_replace(profile, target_lufs=reference.target_lufs)
                match.target_lufs = reference.target_lufs
            result.match = match

        engine = MasteringEngine(sample_rate, profile)
        mastered, master_report = engine.process(cleaned, sub_progress(report, 0.50, 0.90))
        del cleaned
        result.master_report = master_report
        if settings.trim:
            report(0.905, "Trimming silences")
            mastered, result.trim = auto_trim(mastered, sample_rate, settings.trim_threshold_db)
            result.mastered_metrics = measure_metrics(mastered, sample_rate)
        else:
            result.mastered_metrics = measure_metrics(
                mastered, sample_rate,
                lufs=master_report.output_lufs, true_peak_db=master_report.output_true_peak_db,
            )

        report(0.92, "Analysing the master")
        result.spectra = {
            "Original": original_spectrum,
            "Cleaned": cleaned_spectrum,
            "Mastered": compute_spectrogram(mastered, sample_rate),
        }
        if result.match is not None and reference is not None:
            result.match.error_after_db = match_error_db(result.spectra["Mastered"], reference)
        result.stereo["mastered"] = analyse_stereo(mastered, sample_rate)

        report(0.96, "Writing the master cache")
        result.master_cache = work_dir / "master.wav"
        sf.write(str(result.master_cache), mastered, sample_rate, subtype="FLOAT", format="WAV")
        del mastered
    except BaseException:
        result.cleanup()
        raise

    result.ok = True
    result.elapsed_s = time.perf_counter() - started
    report(1.0, "Mastered")
    return result

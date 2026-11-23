"""
Background work: the audio never runs in the GUI thread.

* MasteringWorker  - QObject moved to a QThread; renders previews (master in the session's
                     temporary folder, nothing written to the output folder) and, for jobs
                     marked ``export``, writes the final files.
* ConverterWorker  - QObject moved to a QThread; FFmpeg batch conversion.
* run_task()       - one-off jobs (analysis images, Gain Match previews, reference
                     analysis) on the global QThreadPool.
* analysis_pool()  - a small separate pool (2 threads) for BPM / key detection, so
                     dropping 30 files never starves the other background jobs.

Cancelling sets a threading.Event that the engine checks at every progress step.
"""

from __future__ import annotations

import threading
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, List, Optional, Tuple

from PySide6.QtCore import QObject, QRunnable, QThread, QThreadPool, Signal, Slot

from ..engine.core import AudioLoadError, ProcessingError
from ..engine.converter import ConversionCancelled, ConversionError, convert_file
from ..engine.delivery import ExportOptions, TrackMeta, export_track
from ..engine.export import ExportError
from ..engine.ffmpeg_tools import FfmpegInfo
from ..engine.pipeline import Cancelled, TrackResult
from ..engine.presets import MasterSettings
from ..engine.reference import ReferenceProfile
from ..engine.render_service import (
    PoolUnavailable,
    RenderError,
    RenderRequest,
    inprocess_forced,
    run_request,
    shared_pool,
)
from ..i18n import tr, tr_engine


@dataclass
class MasterJob:
    key: str
    source: Path
    existing: Optional[TrackResult]       # this mode is already rendered: reused as it is
    meta: TrackMeta                       # title, BPM, key, track number (tags / file name)
    settings: MasterSettings              # the mode to render (per-card preset / profile, else the panel)
    reference: Optional[ReferenceProfile] = None
    export: bool = False                  # False = preview only (temporary files)
    cut: Optional[Tuple[float, float]] = None   # manual start / end (s); None = the whole track
    analog_seed: Optional[int] = None     # the track's Anti-Parasite analog tolerance (None = off)


class MasteringWorker(QObject):
    trackStarted = Signal(str)
    trackProgress = Signal(str, float, str)
    trackFinished = Signal(str, object)           # key, TrackResult
    batchProgress = Signal(float, str)
    finished = Signal(int, int, bool)             # succeeded, failed, cancelled

    def __init__(self, jobs: List[MasterJob], options: ExportOptions,
                 work_root: Path, ffmpeg: Optional[FfmpegInfo]) -> None:
        super().__init__()
        self.jobs, self.options = jobs, options
        self.work_root, self.ffmpeg = work_root, ffmpeg
        self._cancel = threading.Event()
        self._resume = threading.Event()
        self._resume.set()
        self._pool = None

    def cancel(self) -> None:
        """Thread-safe: called directly from the GUI thread."""
        self._cancel.set()
        self._resume.set()                        # a paused queue must wake up to stop
        if self._pool is not None:
            self._pool.cancel()

    def set_paused(self, paused: bool) -> None:
        """Pause between tracks (the current track always finishes first)."""
        if paused:
            self._resume.clear()
        else:
            self._resume.set()

    def _render(self, request: RenderRequest, progress) -> TrackResult:
        """Render in the warm child process; fall back to this thread if it is unusable."""
        if not inprocess_forced():
            try:
                self._pool = shared_pool()
                return self._pool.run(request, progress)
            except PoolUnavailable:
                self._pool = None                 # the next tracks run in-thread
            except RenderError as exc:            # a job failure in the child: re-raise as an engine error
                if exc.kind == "engine":
                    raise ProcessingError(exc.message)
                if exc.kind == "memory":
                    raise MemoryError(exc.message)
                failure = Exception(exc.message)
                failure._detail = exc.detail      # type: ignore[attr-defined]
                raise failure
        return run_request(request, progress, self._cancel)

    @Slot()
    def run(self) -> None:
        total = len(self.jobs)
        succeeded = failed = 0
        for index, job in enumerate(self.jobs):
            self._resume.wait()                   # honour Pause between tracks
            if self._cancel.is_set():
                break
            self.trackStarted.emit(job.key)
            label = tr("Track {i}/{n} - {name}", i=index + 1, n=total, name=job.source.name)

            def progress(fraction: float, message: str, _index=index, _key=job.key, _label=label) -> None:
                self.trackProgress.emit(_key, fraction, message)          # English: the card translates
                self.batchProgress.emit((_index + fraction) / total, f"{_label}: {tr_engine(message)}")

            result = job.existing
            try:
                if result is None or not result.is_current(job.settings) or result.cut_key() != job.cut \
                        or result.analog_seed != job.analog_seed:
                    request = RenderRequest(job.key, job.source, job.settings, self.work_root,
                                            reference=job.reference, cut=job.cut, export=job.export,
                                            options=self.options, meta=job.meta, ffmpeg=self.ffmpeg,
                                            analog_seed=job.analog_seed)
                    result = self._render(request, progress)
                elif job.export:                   # the master is reused; only the export is (re)done
                    progress(0.5, "Exporting" + (" + clip" if self.options.clip.enabled else ""))
                    try:
                        export_track(result, self.options, job.meta, self.ffmpeg, self.work_root)
                        result.export_error = ""
                    except (ExportError, OSError, ValueError) as exc:
                        result.export_error = str(exc)
                    progress(1.0, "Done")
                if result.export_error:
                    failed += 1
                else:
                    succeeded += 1
            except Cancelled:
                result = TrackResult(source=job.source, settings=job.settings, cancelled=True, error="Cancelled",
                                     analog_seed=job.analog_seed)
            except (AudioLoadError, ProcessingError) as exc:
                failed += 1
                result = TrackResult(source=job.source, settings=job.settings, error=str(exc),
                                     analog_seed=job.analog_seed)
            except MemoryError:
                failed += 1
                result = TrackResult(source=job.source, settings=job.settings, analog_seed=job.analog_seed,
                                     error="Not enough memory to process this track.")  # translated by the card
            except Exception as exc:  # noqa: BLE001 - one bad file must not stop the batch
                failed += 1
                detail = getattr(exc, "_detail", None) or traceback.format_exc()
                message = str(exc) if str(exc).startswith("Unexpected error") else f"Unexpected error: {exc}"
                result = TrackResult(source=job.source, settings=job.settings, error=message, error_detail=detail,
                                     analog_seed=job.analog_seed)
            self.trackFinished.emit(job.key, result)
        self.finished.emit(succeeded, failed, self._cancel.is_set())


@dataclass
class ConvertJob:
    key: str
    source: Path


class ConverterWorker(QObject):
    fileStarted = Signal(str)
    fileProgress = Signal(str, float)
    fileFinished = Signal(str, object, str)       # key, output Path or None, error message
    batchProgress = Signal(float, str)
    finished = Signal(int, int, bool)

    def __init__(self, jobs: List[ConvertJob], ffmpeg: str, fmt_key: str,
                 sample_rate: Optional[int], out_dir: Optional[Path]) -> None:
        super().__init__()
        self.jobs, self.ffmpeg, self.fmt_key = jobs, ffmpeg, fmt_key
        self.sample_rate, self.out_dir = sample_rate, out_dir
        self._cancel = threading.Event()
        self._resume = threading.Event()
        self._resume.set()

    def cancel(self) -> None:
        self._cancel.set()
        self._resume.set()

    def set_paused(self, paused: bool) -> None:
        if paused:
            self._resume.clear()
        else:
            self._resume.set()

    @Slot()
    def run(self) -> None:
        total = len(self.jobs)
        succeeded = failed = 0
        for index, job in enumerate(self.jobs):
            self._resume.wait()                   # honour Pause between files
            if self._cancel.is_set():
                break
            self.fileStarted.emit(job.key)

            def progress(fraction: float, _index=index, _key=job.key, _name=job.source.name) -> None:
                self.fileProgress.emit(_key, fraction)
                self.batchProgress.emit((_index + fraction) / total,
                                        tr("File {i}/{n} - {name}", i=_index + 1, n=total, name=_name))

            try:
                path = convert_file(self.ffmpeg, job.source, self.fmt_key, self.sample_rate,
                                    self.out_dir, progress=progress, cancel=self._cancel)
                succeeded += 1
                self.fileFinished.emit(job.key, path, "")
            except ConversionCancelled:
                self.fileFinished.emit(job.key, None, "Cancelled")
            except (ConversionError, OSError) as exc:
                failed += 1
                self.fileFinished.emit(job.key, None, str(exc))
            except Exception as exc:  # noqa: BLE001
                failed += 1
                self.fileFinished.emit(job.key, None, f"Unexpected error: {exc}")
        self.finished.emit(succeeded, failed, self._cancel.is_set())


def start_worker(worker: QObject, parent: QObject, on_finished: Callable) -> QThread:
    """Move ``worker`` to a new QThread, start it, and clean both up when it is done.
    The thread runs at low priority, so audio playback and the interface stay smooth."""
    thread = QThread(parent)
    worker.moveToThread(thread)
    thread.started.connect(worker.run)
    worker.finished.connect(on_finished)
    worker.finished.connect(thread.quit)
    thread.finished.connect(worker.deleteLater)
    thread.finished.connect(thread.deleteLater)
    thread.start(QThread.Priority.LowPriority)
    return thread


# ---------------------------------------------------------------- one-off tasks
class _TaskSignals(QObject):
    done = Signal(object)
    failed = Signal(str)


class _Task(QRunnable):
    def __init__(self, fn: Callable[[], object]) -> None:
        super().__init__()
        self.fn = fn
        self.signals = _TaskSignals()

    @Slot()
    def run(self) -> None:
        try:
            value = self.fn()
        except Exception as exc:  # noqa: BLE001
            self.signals.failed.emit(str(exc))
        else:
            self.signals.done.emit(value)


class _Relay(QObject):
    """
    Lives in the GUI thread: the task's signals are delivered to its slots through
    queued connections, so the callbacks always run in the GUI thread.
    """

    def __init__(self, on_done: Callable[[object], None],
                 on_failed: Optional[Callable[[str], None]]) -> None:
        super().__init__()
        self._on_done, self._on_failed = on_done, on_failed

    @Slot(object)
    def handle_done(self, value: object) -> None:
        _forget(self)
        self._on_done(value)

    @Slot(str)
    def handle_failed(self, message: str) -> None:
        _forget(self)
        if self._on_failed is not None:
            self._on_failed(message)


_live: List[tuple] = []          # (task, relay) kept alive until the task has reported


def _forget(relay: _Relay) -> None:
    for item in list(_live):
        if item[1] is relay:
            _live.remove(item)


_analysis_pool: Optional[QThreadPool] = None
_playback_pool: Optional[QThreadPool] = None


def analysis_pool() -> QThreadPool:
    """Two threads for BPM / key detection (each job decodes a whole track)."""
    global _analysis_pool
    if _analysis_pool is None:
        _analysis_pool = QThreadPool()
        _analysis_pool.setMaxThreadCount(2)
    return _analysis_pool


def playback_pool() -> QThreadPool:
    """Listening buffers: one at a time, so loading never competes with the audio thread."""
    global _playback_pool
    if _playback_pool is None:
        _playback_pool = QThreadPool()
        _playback_pool.setMaxThreadCount(1)
    return _playback_pool


def run_task(fn: Callable[[], object], on_done: Callable[[object], None],
             on_failed: Optional[Callable[[str], None]] = None,
             pool: Optional[QThreadPool] = None, priority: int = 0) -> None:
    """Run ``fn`` on a thread pool (global by default); callbacks run back in the GUI thread.
    Higher ``priority`` tasks start first when the pool is busy."""
    task = _Task(fn)
    task.setAutoDelete(False)
    relay = _Relay(on_done, on_failed)
    task.signals.done.connect(relay.handle_done)
    task.signals.failed.connect(relay.handle_failed)
    _live.append((task, relay))
    (pool or QThreadPool.globalInstance()).start(task, priority)

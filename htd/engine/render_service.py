"""
Off-GUI rendering of a track, run in a **separate process** so the heavy DSP
(numpy / scipy / pedalboard) never competes with the audio callback for the GIL:
this is what keeps playback clean while a batch is computing. No Qt in here.

* ``RenderRequest``   - everything one render needs, all picklable.
* ``run_request``     - does the work (master, then optional export); used both
                        in the child process and as the inline fallback.
* ``RenderPool``      - a single warm child process kept across jobs (so the heavy
                        imports happen once). ``run`` sends a request, forwards
                        progress, and returns the TrackResult. Cancellation uses a
                        shared event. If the child cannot be used (spawn failure,
                        crash), the caller falls back to ``run_request`` inline.

The child writes into ``work_root`` (the session's shared temp folder), so the
master cache it produces is readable by the parent afterwards.
"""

from __future__ import annotations

import multiprocessing as mp
import os
import queue
import threading
import time
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional, Tuple

from . import core
from .delivery import ExportOptions, TrackMeta, export_track
from .export import ExportError
from .ffmpeg_tools import FfmpegInfo
from .pipeline import Cancelled, TrackResult, master_track
from .presets import MasterSettings
from .reference import ReferenceProfile

ProgressFn = Callable[[float, str], None]


@dataclass
class RenderRequest:
    key: str
    source: Path
    settings: MasterSettings
    work_root: Path
    reference: Optional[ReferenceProfile] = None
    cut: Optional[Tuple[float, float]] = None
    export: bool = False
    options: Optional[ExportOptions] = None
    meta: Optional[TrackMeta] = None
    ffmpeg: Optional[FfmpegInfo] = None
    analog_seed: Optional[int] = None      # Anti-Parasite analog tolerance (None = v1.0 filter)


class _Cancel:
    """Adapts a threading.Event or a multiprocessing event to what the engine expects."""

    def __init__(self, event) -> None:
        self._event = event

    def is_set(self) -> bool:
        return bool(self._event is not None and self._event.is_set())


def run_request(request: RenderRequest, progress: Optional[ProgressFn], cancel) -> TrackResult:
    """Master (always) and export (when asked). Raises engine errors / Cancelled.
    ``cancel`` is anything with ``is_set()`` (threading or multiprocessing event)."""
    guard = _Cancel(cancel)
    share = 0.85 if request.export else 1.0
    result = master_track(request.source, request.settings, request.work_root,
                          progress=(lambda f, m: progress(share * f, m)) if progress else None,
                          cancel=guard, reference=request.reference, cut=request.cut,
                          analog_seed=getattr(request, "analog_seed", None))
    if request.export and result.ok:
        if progress:
            progress(0.87, "Exporting" + (" + clip" if request.options and request.options.clip.enabled else ""))
        try:
            export_track(result, request.options, request.meta, request.ffmpeg, request.work_root)
            result.export_error = ""
        except (ExportError, OSError, ValueError) as exc:
            result.export_error = str(exc)
    if progress:
        progress(1.0, "Done" if request.export else "Preview ready")
    return result


# --------------------------------------------------------------------------- child process
def _worker_loop(in_q, out_q, cancel_evt) -> None:  # pragma: no cover - runs in a child process
    """One request at a time: emit ('progress', frac, msg), then ('result', data) or ('error', info)."""
    try:
        import numpy  # noqa: F401  (warm the heavy imports once)
    except Exception:  # noqa: BLE001
        pass
    while True:
        try:
            message = in_q.get()
        except (EOFError, OSError):
            return
        if message is None:
            return
        request = message
        cancel_evt.clear()

        def progress(fraction: float, text: str) -> None:
            try:
                out_q.put(("progress", (float(fraction), text)))
            except Exception:  # noqa: BLE001 - parent gone
                pass

        try:
            result = run_request(request, progress, cancel_evt)
            out_q.put(("result", result))
        except Cancelled:
            out_q.put(("cancelled", None))
        except (core.AudioLoadError, core.ProcessingError) as exc:
            out_q.put(("error", ("engine", str(exc), "")))
        except MemoryError:
            out_q.put(("error", ("memory", "Not enough memory to process this track.", "")))
        except Exception as exc:  # noqa: BLE001
            out_q.put(("error", ("unexpected", f"Unexpected error: {exc}", traceback.format_exc())))


class RenderError(Exception):
    """A render failed in a child process (kind, message, detail)."""

    def __init__(self, kind: str, message: str, detail: str = "") -> None:
        super().__init__(message)
        self.kind, self.message, self.detail = kind, message, detail


class PoolUnavailable(RuntimeError):
    """The child process could not be started or died; the caller should run inline."""


class RenderPool:
    """A single warm child process. Thread-safe for one caller at a time (the worker thread)."""

    START_TIMEOUT_S = 90.0
    # A job that sends nothing for this long is considered wedged (overridable for tests).
    STALL_TIMEOUT_S = 300.0

    def __init__(self) -> None:
        # spawn everywhere, not only on Windows: on Linux ``fork`` copies a process
        # that already holds Qt and PortAudio threads, and a mutex held by a thread
        # that does not exist in the child deadlocks it (the parent then waits
        # forever). Re-executing gives the child a clean single-threaded start;
        # HTD_RENDER_FORK=1 brings the old behaviour back for troubleshooting.
        method = "fork" if os.environ.get("HTD_RENDER_FORK", "") == "1" else "spawn"
        self._ctx = mp.get_context(method)
        self._proc = None
        self._in_q = None
        self._out_q = None
        self._cancel_evt = None
        # RLock, not Lock: run() holds it and calls shutdown() (which takes it again) on
        # every failure path. With a plain Lock that re-entry deadlocks the parent, so a
        # dead child froze the whole app instead of falling back to inline rendering.
        self._lock = threading.RLock()

    @property
    def alive(self) -> bool:
        return self._proc is not None and self._proc.is_alive()

    @property
    def stall_timeout(self) -> float:
        try:
            return max(5.0, float(os.environ.get("HTD_RENDER_STALL_S", self.STALL_TIMEOUT_S)))
        except (TypeError, ValueError):
            return self.STALL_TIMEOUT_S

    def start(self) -> None:
        """Start the warm child (no job). Safe to call before Qt exists."""
        with self._lock:
            if not self.alive:
                self._start()

    def _start(self) -> None:
        self._in_q = self._ctx.Queue()
        self._out_q = self._ctx.Queue()
        self._cancel_evt = self._ctx.Event()
        self._proc = self._ctx.Process(target=_worker_loop, args=(self._in_q, self._out_q, self._cancel_evt),
                                       daemon=True, name="htd-render")
        try:
            self._proc.start()
        except Exception as exc:  # noqa: BLE001 - spawn refused (frozen build misconfig, sandbox...)
            self._proc = None
            raise PoolUnavailable(str(exc)) from exc

    def cancel(self) -> None:
        if self._cancel_evt is not None:
            self._cancel_evt.set()

    def run(self, request: RenderRequest, progress: Optional[ProgressFn]) -> TrackResult:
        """Render ``request`` in the child; forward progress. Raises RenderError for a job
        failure, Cancelled when cancelled, PoolUnavailable when the process is unusable."""
        with self._lock:
            if not self.alive:
                self._start()
            self._cancel_evt.clear()
            try:
                self._in_q.put(request)
            except Exception as exc:  # noqa: BLE001
                self.shutdown()
                raise PoolUnavailable(str(exc)) from exc
            last_seen = time.monotonic()
            while True:
                try:
                    kind, data = self._out_q.get(timeout=1.0)
                except queue.Empty:
                    if not self.alive:
                        self.shutdown()
                        raise PoolUnavailable("the render process stopped unexpectedly")
                    # Alive but silent: a wedged child used to block here forever. Kill it and
                    # let the caller's inline fallback finish the job.
                    if time.monotonic() - last_seen > self.stall_timeout:
                        self.shutdown()
                        raise PoolUnavailable(
                            f"the render process stopped responding "
                            f"(no progress for {self.stall_timeout:.0f} s)")
                    continue
                last_seen = time.monotonic()
                if kind == "progress":
                    if progress:
                        progress(data[0], data[1])
                    continue
                if kind == "result":
                    return data
                if kind == "cancelled":
                    raise Cancelled()
                if kind == "error":
                    raise RenderError(*data)

    def shutdown(self, timeout: float = 5.0) -> None:
        with self._lock:
            proc = self._proc
            self._proc = None
            if self._in_q is not None:
                try:
                    self._in_q.put(None)
                except Exception:  # noqa: BLE001
                    pass
        if proc is not None and proc.is_alive():
            proc.join(timeout)
            if proc.is_alive():
                proc.terminate()
                proc.join(2.0)
            if proc.is_alive():                      # a wedged child can ignore SIGTERM
                proc.kill()
                proc.join(2.0)


_POOL: Optional[RenderPool] = None
_POOL_LOCK = threading.Lock()


def shared_pool() -> RenderPool:
    global _POOL
    with _POOL_LOCK:
        if _POOL is None:
            _POOL = RenderPool()
        return _POOL


def prestart_pool() -> bool:
    """Start the warm render child early, before the GUI exists.

    The child is started at launch so the first render does not pay its start-up
    time; with the spawn context this is a re-exec, so it carries no risk of the
    fork-with-threads deadlock. Never raises: if it cannot start, the caller simply
    renders inline (``inprocess_forced`` / ``PoolUnavailable``).
    """
    if inprocess_forced():
        return False
    try:
        pool = shared_pool()
        pool.start()
    except Exception:  # noqa: BLE001 - a child that cannot start is not fatal
        return False
    return pool.alive


def shutdown_pool() -> None:
    global _POOL
    with _POOL_LOCK:
        pool, _POOL = _POOL, None
    if pool is not None:
        pool.shutdown()


def inprocess_forced() -> bool:
    """Tests / troubled setups can keep everything in-thread (no child process)."""
    return os.environ.get("HTD_INPROCESS_RENDER", "") == "1"

"""
One shared preview player for the whole app (v2.0.1: PortAudio through sounddevice).

The sound is produced by audio_output.AudioOutput: float32 buffers already at
the sound card's rate (see playback.py), played in a PortAudio callback with a
comfortable buffer - no QMediaPlayer, no decoding, no system resampling, so no
crackle. Everything that changes what you hear is sample-accurate and
cross-faded (a few ms, no click):

* Original <-> Master and another mode: play() with the same owner continues at
  the same timeline moment (a trimmed master is lined up with the original);
* Gain Match and Mono: set_gain_db() / set_mono(), live, without reloading;
* seek bar jumps, pause / resume / stop, and the loop A-B (``set_loop(A, B)``,
  timeline ms: playback jumps back to A each time it reaches B, also across
  Original / Master / mode switches since they share the timeline).

Positions given to / reported by this class are on the original's timeline
("timeline ms"), which is what the seek bars show.

Signals (unchanged)
    stateChanged(owner, which)   what is loaded; ("", "") once stopped / ended
    playingChanged(bool)         really playing (False when paused / stopped)
    positionChanged(owner, ms)   timeline position, every POLL_MS while loaded
    errorOccurred(message)       no sound output / the device went away
    deviceChanged()              the default audio output changed (headphones...):
                                 the owner reloads its buffers at output_rate()

The device is released after IDLE_CLOSE_MS without playback and reopened at
the next play / resume.
"""

from __future__ import annotations

from typing import Optional, Tuple

from PySide6.QtCore import QObject, QTimer, Signal

from .audio_output import AudioOutput, OutputUnavailable, PlayBuffer
from .translate import tr

try:
    from PySide6.QtMultimedia import QMediaDevices   # only for "the outputs changed" notifications
except ImportError:                                   # pragma: no cover
    QMediaDevices = None

POLL_MS = 40
IDLE_CLOSE_MS = 15_000
MIN_LOOP_MS = 200


def db_to_gain(db: float) -> float:
    return float(10.0 ** (float(db) / 20.0))


class PreviewPlayer(QObject):
    stateChanged = Signal(str, str)
    playingChanged = Signal(bool)
    positionChanged = Signal(str, int)
    errorOccurred = Signal(str)
    deviceChanged = Signal()

    def __init__(self, parent: Optional[QObject] = None, output: Optional[AudioOutput] = None) -> None:
        super().__init__(parent)
        self._out = output if output is not None else AudioOutput()
        self._current: Tuple[str, str] = ("", "")
        self._buffer: Optional[PlayBuffer] = None
        self._playing = False
        self._loop: Optional[Tuple[int, int]] = None      # (A, B) timeline ms
        self._poll = QTimer(self)
        self._poll.setInterval(POLL_MS)
        self._poll.timeout.connect(self._tick)
        self._idle = QTimer(self)
        self._idle.setSingleShot(True)
        self._idle.setInterval(IDLE_CLOSE_MS)
        self._idle.timeout.connect(self._close_if_idle)
        self._devices = None
        if QMediaDevices is not None:
            try:
                self._devices = QMediaDevices(self)
                self._devices.audioOutputsChanged.connect(self._on_outputs_changed)
            except Exception:  # noqa: BLE001 - notifications are a bonus
                self._devices = None

    # ---- state ---------------------------------------------------------------
    @property
    def output(self) -> AudioOutput:
        return self._out

    @property
    def current(self) -> Tuple[str, str]:
        return self._current

    @property
    def playing(self) -> bool:
        return self._playing

    @property
    def buffer(self) -> Optional[PlayBuffer]:
        """What is loaded (the owner compares it to decide whether a reload is needed)."""
        return self._buffer if self._current != ("", "") else None

    def is_loaded(self, owner: Optional[str] = None) -> bool:
        return self._current != ("", "") and (owner is None or self._current[0] == owner)

    def is_playing(self, owner: str, which: Optional[str] = None) -> bool:
        return self._playing and self._current[0] == owner and (which is None or self._current[1] == which)

    def is_paused(self, owner: Optional[str] = None) -> bool:
        return self.is_loaded(owner) and not self._playing

    def output_rate(self) -> int:
        """Sample rate of the sound output (0 when none can be opened: errorOccurred tells why)."""
        try:
            return self._out.open()
        except OutputUnavailable as exc:
            self._report(exc)
            return 0

    def timeline_position(self) -> int:
        """Current position on the original's timeline (ms)."""
        buffer = self._buffer
        if buffer is None or self._current == ("", ""):
            return 0
        return int(round(self._out.position() * 1000.0 / buffer.rate))

    def duration_ms(self) -> int:
        buffer = self._buffer
        return 0 if buffer is None else int(buffer.end * 1000 / buffer.rate)

    def _frames(self, ms: int, buffer: Optional[PlayBuffer] = None) -> int:
        buffer = buffer or self._buffer
        return int(round(int(ms) * buffer.rate / 1000.0))

    # ---- control ---------------------------------------------------------------
    def play(self, owner: str, which: str, buffer: PlayBuffer, start_ms: Optional[int] = None,
             gain_db: float = 0.0, mono: bool = False, autoplay: bool = True) -> bool:
        """Play ``buffer``. ``start_ms`` (timeline) jumps to a moment; otherwise, when the same
        track is loaded (playing or paused), playback continues at the same moment.
        ``autoplay=False`` keeps a paused track paused (the new version is ready to resume)."""
        if not self.output_rate():
            return False
        same = self.is_loaded(owner) and self._buffer is not None
        run = bool(autoplay) or (same and self._playing)
        if same and start_ms is None and self._buffer.rate != buffer.rate:
            start_ms = self.timeline_position()          # new device rate: anchor on the time
        start = None if start_ms is None else self._frames(start_ms, buffer)
        self._out.load(buffer, start=start, keep=same and start is None, gain=db_to_gain(gain_db),
                       mono=mono, run=run)
        self._buffer = buffer
        self._current = (owner, which)
        self._apply_loop()
        if run and not self._start_stream():
            return False
        self._idle.stop()
        self._poll.start()
        self._set_playing(run)
        if not run:
            self._idle.start()
        self.stateChanged.emit(owner, which)
        self._emit_position()
        return True

    def pause(self) -> None:
        if self.is_loaded() and self._playing:
            self._out.pause()
            self._set_playing(False)
            self._emit_position()
            self._idle.start()

    def resume(self) -> None:
        if self.is_loaded() and not self._playing:
            self._out.resume()
            if self._start_stream():
                self._idle.stop()
                self._set_playing(True)

    def toggle_pause(self) -> None:
        if self._playing:
            self.pause()
        else:
            self.resume()

    def seek(self, timeline_ms: int) -> None:
        """Jump to a moment (timeline ms) of what is loaded (playing or paused)."""
        if not self.is_loaded() or self._buffer is None:
            return
        target = max(0, int(timeline_ms))
        duration = self.duration_ms()
        if duration > 0:
            target = min(target, max(0, duration - 50))
        self._out.seek(self._frames(target))
        self.positionChanged.emit(self._current[0], target)

    def set_gain_db(self, gain_db: float) -> None:
        """Gain Match: live, smooth (no reload)."""
        self._out.set_gain(db_to_gain(gain_db))

    def set_mono(self, mono: bool) -> None:
        """Mono check: (L + R) / 2 on both sides, live, smooth (no reload)."""
        self._out.set_mono(mono)

    def stop(self) -> None:
        if self.is_loaded() or self._buffer is not None:
            self._out.stop()
            self._ended()

    def stop_if_owner(self, owner: str) -> None:
        if self._current[0] == owner:
            self.stop()

    def shutdown(self) -> None:
        """Window closing: stop and release the device."""
        self.stop()
        self._idle.stop()
        self._out.close()

    # ---- loop A-B ------------------------------------------------------------
    @property
    def loop(self) -> Optional[Tuple[int, int]]:
        return self._loop

    def set_loop(self, start_ms: Optional[int], end_ms: Optional[int]) -> None:
        """Loop between A and B (timeline ms); None / invalid values switch the loop off."""
        if start_ms is None or end_ms is None or int(end_ms) - int(start_ms) < MIN_LOOP_MS:
            self._loop = None
        else:
            self._loop = (int(start_ms), int(end_ms))
        self._apply_loop()

    def _apply_loop(self) -> None:
        if self._loop is None or self._buffer is None:
            self._out.set_loop(None, None)
        else:
            self._out.set_loop(self._frames(self._loop[0]), self._frames(self._loop[1]))

    # ---- internals ---------------------------------------------------------
    def _report(self, exc: Exception) -> None:
        self.errorOccurred.emit(tr("No sound output available: {error}", error=str(exc)))

    def _start_stream(self) -> bool:
        try:
            self._out.start()
            return True
        except OutputUnavailable as exc:
            self._report(exc)
            self._out.stop()
            self._ended()
            return False

    def _set_playing(self, playing: bool) -> None:
        if playing != self._playing:
            self._playing = playing
            self.playingChanged.emit(playing)

    def _emit_position(self) -> None:
        if self._current != ("", ""):
            self.positionChanged.emit(self._current[0], self.timeline_position())

    def _tick(self) -> None:
        failure = self._out.take_failure()
        if failure:                                       # device unplugged: move to the new default
            self.errorOccurred.emit(tr(failure))
            self._on_outputs_changed()
            if not self.is_loaded():
                return
        if self._out.take_ended():
            self._ended()
            return
        self._emit_position()

    def _ended(self) -> None:
        was_loaded = self._current != ("", "")
        self._current = ("", "")
        self._buffer = None
        self._set_playing(False)
        self._poll.stop()
        self._idle.start()
        if was_loaded:
            self.stateChanged.emit("", "")

    def _close_if_idle(self) -> None:
        if not self._playing:
            self._out.close()

    def _on_outputs_changed(self) -> None:
        """Headphones plugged in, other default device...: move to it. Same rate: playback
        goes on; another rate: silent until the owner reloads (deviceChanged)."""
        old_rate = self._out.rate
        self._out.reset_device()
        rate = self.output_rate()
        if self.is_loaded():
            if rate and rate == old_rate:
                if self._playing:
                    self._start_stream()
            else:
                self._out.hold()
        self.deviceChanged.emit()

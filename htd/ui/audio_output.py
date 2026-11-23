"""
Real-time audio output of the preview player: PortAudio through sounddevice.
No Qt in here (the Qt side is player.py).

Why: QMediaPlayer on Windows could crackle (its audio sink / the system mixer).
Here the audio is played straight from float32 buffers that are already at the
output's own sample rate, inside a PortAudio callback with a comfortable buffer
(BLOCKSIZE frames, "high" latency): nothing is decoded, re-encoded or resampled
on the way out.

* Original / Master, another mode, a jump on the seek bar and the A-B loop are
  sample-accurate and cross-faded over FADE_MS (no click);
* Gain Match and Mono are applied live with a smooth gain / mix ramp;
* pause, resume and stop fade out / in.

Output device: on Windows the WASAPI default output first (its shared-mode rate
is the real mixer rate, so Windows does not resample), then DirectSound and MME;
elsewhere the system default. Rates tried: the device's own, then 48000, 44100;
blocksize BLOCKSIZE, then whatever PortAudio prefers.

Thread model: the GUI thread calls the methods below; PortAudio's thread calls
_callback(). Both take ``_lock`` for a few microseconds; stream methods (start,
abort, close) are always called without holding it.
"""

from __future__ import annotations

import sys
import threading
from dataclasses import dataclass
from typing import List, Optional, Tuple

import numpy as np

from ..i18n import N_

try:
    import sounddevice as sd
    IMPORT_ERROR = ""
except (ImportError, OSError) as exc:                 # package missing / PortAudio library not found
    sd = None
    IMPORT_ERROR = str(exc) or exc.__class__.__name__

BLOCKSIZE = 4096                    # frames per callback (~85 ms at 48 kHz): a comfortable margin
LATENCY = "high"                    # PortAudio's safe buffering for the device (no underruns while computing)
FADE_MS = 6.0                       # cross-fades and pause / stop fades
FALLBACK_RATES = (48000, 44100)
WINDOWS_HOST_APIS = ("Windows WASAPI", "Windows DirectSound", "MME")
PLATFORM = sys.platform


class OutputUnavailable(RuntimeError):
    """No audio output could be opened."""


@dataclass(eq=False)
class PlayBuffer:
    """Audio ready to play: float32 (frames, 2) at ``rate`` Hz. ``offset`` = where its first
    frame sits on the original's timeline (a trimmed master starts later), in frames."""
    audio: np.ndarray
    rate: int
    offset: int = 0

    @property
    def frames(self) -> int:
        return int(self.audio.shape[0])

    @property
    def end(self) -> int:
        """Timeline frame just after the last one."""
        return self.offset + self.frames


def _read(data: np.ndarray, pos: int, count: int) -> np.ndarray:
    """``count`` frames from ``pos`` (silence outside the buffer)."""
    out = np.zeros((max(count, 0), 2), np.float32)
    start, stop = max(pos, 0), min(pos + count, data.shape[0])
    if stop > start:
        out[start - pos:stop - pos] = data[start:stop]
    return out


def _curve(start: float, stop: float, count: int):
    """A scalar when nothing changes, otherwise a linear ramp over the block."""
    if start == stop or count <= 0:
        return float(stop)
    return np.linspace(start, stop, count + 1, dtype=np.float32)[1:]


def _mix(block: np.ndarray, gain, mono) -> np.ndarray:
    """Gain (scalar or per frame) and mono amount (0 = stereo, 1 = (L + R) / 2 on both sides)."""
    if np.ndim(mono) or mono > 0.0:
        amount = np.asarray(mono, np.float32).reshape(-1, 1) if np.ndim(mono) else np.float32(mono)
        middle = block.mean(axis=1, keepdims=True)
        block = block * (np.float32(1.0) - amount) + middle * amount
    if np.ndim(gain):
        block = block * np.asarray(gain, np.float32)[:, None]
    elif gain != 1.0:
        block = block * np.float32(gain)
    return block


class AudioOutput:
    def __init__(self, blocksize: int = BLOCKSIZE, latency=LATENCY) -> None:
        self.blocksize, self.latency = blocksize, latency
        self._lock = threading.RLock()
        self._stream = None
        self._generation = 0
        self.rate = 0
        self.channels = 2
        self.device_name = ""
        self.underflows = 0
        self.last_error = ""
        self._failure = ""
        self._refused: set = set()          # (device, rate, blocksize) that opened but could not start
        self._config: Tuple = ()
        self._fade = 256
        # the voice (what plays) - only touched under _lock
        self._buf: Optional[PlayBuffer] = None
        self._pos = 0                       # next frame of _buf to play
        self._gain = self._gain_to = 1.0
        self._mono = self._mono_to = 0.0
        self._run = False                   # advancing (playing)
        self._env = 0.0                     # output level 0..1 (fades for pause / resume / stop)
        self._stopping = False
        self._hold = False                  # silent and frozen (new device rate, reload pending)
        self._ended = False
        self._old: Optional[Tuple] = None   # (buffer, pos, gain, mono, env, frames left): fading out
        self._loop: Optional[Tuple[int, int]] = None   # (A, B) timeline frames

    # ------------------------------------------------------------------ device
    @property
    def available(self) -> bool:
        return sd is not None

    @property
    def is_open(self) -> bool:
        return self._stream is not None

    @property
    def active(self) -> bool:
        stream = self._stream
        try:
            return bool(stream is not None and stream.active)
        except Exception:  # noqa: BLE001 - a dead stream
            return False

    def _devices(self) -> List[Tuple[Optional[int], dict]]:
        """(device index or None for the default, info) in the order to try."""
        indexes: List[Optional[int]] = []
        if PLATFORM == "win32":
            try:
                apis = list(sd.query_hostapis())
            except Exception:  # noqa: BLE001
                apis = []
            for wanted in WINDOWS_HOST_APIS:
                for api in apis:
                    index = int(api.get("default_output_device", -1))
                    if str(api.get("name", "")).startswith(wanted) and index >= 0 and index not in indexes:
                        indexes.append(index)
        indexes.append(None)
        found = []
        for index in indexes:
            try:
                info = dict(sd.query_devices(index, "output"))
            except Exception:  # noqa: BLE001 - no such device / no default output
                continue
            if int(info.get("max_output_channels", 0) or 0) > 0:
                found.append((index, info))
        return found

    def open(self) -> int:
        """Configure the output (not started); returns its sample rate."""
        if self._stream is not None:
            return self.rate
        if sd is None:
            raise OutputUnavailable(IMPORT_ERROR or "sounddevice is not installed")
        errors: List[str] = []
        for index, info in self._devices():
            channels = 2 if int(info.get("max_output_channels", 2)) >= 2 else 1
            rates: List[int] = []
            for rate in (info.get("default_samplerate"),) + FALLBACK_RATES:
                if rate and int(rate) not in rates:
                    rates.append(int(rate))
            for rate in rates:
                for blocksize in (self.blocksize, 0):
                    if (index, rate, blocksize) in self._refused:
                        continue
                    generation = self._generation + 1
                    try:
                        stream = sd.OutputStream(
                            samplerate=rate, blocksize=blocksize, device=index, channels=channels,
                            dtype="float32", latency=self.latency, callback=self._callback,
                            finished_callback=lambda g=generation: self._finished(g))
                    except Exception as exc:  # noqa: BLE001 - try the next combination
                        errors.append(f"{info.get('name', index)} @ {rate} Hz: {exc}")
                        continue
                    with self._lock:
                        self._generation = generation
                        self._stream = stream
                        self._config = (index, rate, blocksize)
                        self.rate, self.channels = rate, channels
                        self.device_name = str(info.get("name", ""))
                        self._fade = max(16, int(round(rate * FADE_MS / 1000.0)))
                        self._failure = ""
                    return rate
        raise OutputUnavailable(errors[-1] if errors else "no audio output device was found")

    def start(self) -> None:
        """Open if needed and start the stream (callbacks begin)."""
        for attempt in range(2):
            self.open()
            stream = self._stream
            try:
                if not stream.active:
                    stream.start()
                return
            except Exception as exc:  # noqa: BLE001 - refused at start: next combination
                self.last_error = str(exc)
                self._refused.add(self._config)
                self.close()
                if attempt == 1:
                    raise OutputUnavailable(str(exc)) from exc

    def close(self) -> None:
        """Stop at once and release the device (the voice is kept: start() resumes it)."""
        with self._lock:
            stream, self._stream = self._stream, None
            self._generation += 1                         # its finished callback is not a failure
        if stream is not None:
            for method in ("abort", "close"):
                try:
                    getattr(stream, method)()
                except Exception:  # noqa: BLE001
                    pass

    def reset_device(self) -> None:
        """The system's outputs changed: close, re-scan the devices (next open() uses the new default)."""
        self.close()
        self.rate = 0
        self._refused.clear()
        if sd is not None:
            try:
                sd._terminate()          # PortAudio only sees new devices after a re-init
                sd._initialize()
            except Exception:  # noqa: BLE001
                pass

    def _finished(self, generation: int) -> None:
        if generation == self._generation:              # not closed by us: the device went away
            self._failure = N_("The audio output stopped (device disconnected?).")

    def take_failure(self) -> str:
        failure, self._failure = self._failure, ""
        return failure

    # ------------------------------------------------------------------ voice (GUI thread)
    def load(self, buffer: PlayBuffer, start: Optional[int] = None, keep: bool = False,
             gain: float = 1.0, mono: bool = False, run: bool = True) -> None:
        """Play ``buffer``. ``start`` = timeline frame; ``keep`` = same timeline moment as what
        plays now (A/B, another mode); otherwise from the buffer's beginning."""
        with self._lock:
            old = self._buf
            audible = old is not None and self._env > 0.0 and not self._hold
            if audible:
                self._old = (old, self._pos, self._gain_to, self._mono_to, self._env, self._fade)
            if start is not None:
                moment = int(start)
            elif keep and old is not None:
                moment = self._pos + old.offset
            else:
                moment = buffer.offset
            self._buf = buffer
            self._pos = int(min(max(moment - buffer.offset, 0), max(buffer.frames - 1, 0)))
            self._gain = self._gain_to = float(gain)
            self._mono = self._mono_to = 1.0 if mono else 0.0
            self._run = bool(run)
            self._env = (1.0 if audible else 0.0) if run else 0.0
            self._ended = self._stopping = self._hold = False

    def seek(self, moment: int) -> None:
        with self._lock:
            buffer = self._buf
            if buffer is None:
                return
            if self._env > 0.0 and not self._hold:
                self._old = (buffer, self._pos, self._gain_to, self._mono_to, self._env, self._fade)
            self._pos = int(min(max(int(moment) - buffer.offset, 0), max(buffer.frames - 1, 0)))
            self._ended = False

    def pause(self) -> None:
        with self._lock:
            self._run = False

    def resume(self) -> None:
        with self._lock:
            if self._buf is not None:
                self._run, self._ended, self._stopping = True, False, False

    def stop(self) -> None:
        """Fade out, then forget the voice."""
        with self._lock:
            if self._buf is None:
                return
            self._run, self._stopping = False, True
            if self._env <= 0.0 or not self.active:
                self._clear()

    def hold(self) -> None:
        """Silent and frozen until the next load() (a buffer at the new rate)."""
        with self._lock:
            self._hold, self._old = True, None

    def set_gain(self, gain: float) -> None:
        with self._lock:
            self._gain_to = float(gain)

    def set_mono(self, mono: bool) -> None:
        with self._lock:
            self._mono_to = 1.0 if mono else 0.0

    def set_loop(self, start: Optional[int], end: Optional[int]) -> None:
        with self._lock:
            self._loop = None if start is None or end is None or end <= start else (int(start), int(end))

    def position(self) -> int:
        """Timeline frame playing now (the next one sent to the device)."""
        with self._lock:
            return 0 if self._buf is None else self._pos + self._buf.offset

    def take_ended(self) -> bool:
        with self._lock:
            ended, self._ended = self._ended, False
            return ended

    def _clear(self) -> None:
        self._buf, self._pos, self._old = None, 0, None
        self._run, self._env, self._stopping, self._hold = False, 0.0, False, False

    # ------------------------------------------------------------------ audio thread
    def _callback(self, outdata, frames, _time, status) -> None:
        try:
            if getattr(status, "output_underflow", False):
                self.underflows += 1
            with self._lock:
                block = self._render(int(frames))
            if outdata.shape[1] == 1:
                outdata[:, 0] = block.mean(axis=1)
            else:
                outdata[:, :2] = block
                if outdata.shape[1] > 2:
                    outdata[:, 2:] = 0.0
        except Exception as exc:  # noqa: BLE001 - never let the audio thread die
            outdata.fill(0.0)
            self.last_error = str(exc)

    def _render(self, frames: int) -> np.ndarray:
        out = np.zeros((frames, 2), np.float32)
        fade = self._fade
        rise = None
        if self._old is not None:                           # cross-fade: the previous voice goes out
            buffer, pos, gain, mono, env, left = self._old
            count = min(frames, left)
            done = fade - left
            down = np.float32(1.0) - np.arange(done + 1, done + count + 1, dtype=np.float32) / np.float32(fade)
            out[:count] += _mix(_read(buffer.audio, pos, count), gain * env, mono) * down[:, None]
            rise = np.ones(frames, np.float32)
            rise[:count] = np.float32(1.0) - down
            left -= count
            self._old = (buffer, pos + count, gain, mono, env, left) if left > 0 else None
        if self._buf is None or self._hold:
            return out
        target = 1.0 if self._run else 0.0
        if target == 0.0 and self._env <= 0.0:
            self._env = 0.0
            if self._stopping:
                self._clear()
            return out
        step = 1.0 / fade
        envelope = None
        count = frames
        if target > self._env:                              # fading in
            envelope = np.minimum(1.0, self._env + step * np.arange(1, frames + 1, dtype=np.float32))
        elif target < self._env:                            # fading out (pause / stop)
            count = min(frames, int(np.ceil(self._env / step - 1e-6)))
            envelope = np.maximum(0.0, self._env - step * np.arange(1, count + 1, dtype=np.float32))
        block = self._advance(count)
        gain = _curve(self._gain, self._gain_to, count)
        mono = _curve(self._mono, self._mono_to, count)
        self._gain, self._mono = self._gain_to, self._mono_to
        block = _mix(block, gain, mono)
        if envelope is not None:
            block *= envelope[:count, None].astype(np.float32)
            self._env = float(envelope[count - 1]) if count else self._env
        if rise is not None:
            block *= rise[:count, None]
        out[:count] += block
        if self._ended:
            self._run, self._env = False, 0.0
        if self._stopping and self._env <= 0.0:
            self._clear()
        return out

    def _advance(self, count: int) -> np.ndarray:
        """The next ``count`` frames of the voice: wraps at the loop end (cross-faded into A),
        flags the end of the track."""
        buffer = self._buf
        data, total, fade = buffer.audio, buffer.frames, self._fade
        out = np.zeros((count, 2), np.float32)
        filled = 0
        while filled < count:
            need = count - filled
            moment = self._pos + buffer.offset
            if self._loop is not None:
                start, end = self._loop
                end = min(end, buffer.end)                  # a trimmed master may end before B
                if start < end and moment < end <= moment + need:   # B is reached in this block
                    take = end - moment
                    out[filled:filled + take] = _read(data, self._pos, take)
                    filled += take
                    after_b = self._pos + take
                    self._pos = max(0, start - buffer.offset)
                    rest = count - filled
                    head = _read(data, self._pos, rest)
                    span = min(fade, rest)
                    up = np.arange(1, span + 1, dtype=np.float32) / np.float32(fade)
                    head[:span] = head[:span] * up[:, None] + _read(data, after_b, span) * (np.float32(1.0) - up)[:, None]
                    if span < fade:                          # finish the cross-fade next block
                        self._old = (buffer, after_b + span, self._gain_to, self._mono_to, 1.0, fade - span)
                    out[filled:] = head
                    self._pos += rest
                    break
            available = total - self._pos
            if available <= 0:
                self._ended = True
                break
            take = min(need, available)
            out[filled:filled + take] = data[self._pos:self._pos + take]
            self._pos += take
            filled += take
        return out

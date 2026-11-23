"""
App-wide activity signals: tools announce their batches and the preview player
its playback; anything can listen (the mascot today, a dock badge or
notifications tomorrow) without the tools knowing who listens.
"""

from __future__ import annotations

from typing import Dict

from PySide6.QtCore import QObject, Signal


class ActivityHub(QObject):
    busyChanged = Signal(bool)                     # True while at least one batch runs
    batchStarted = Signal(str, bool)               # tool name, launched by the user (False = automatic)
    batchFinished = Signal(str, int, int, bool)    # tool, succeeded, failed, cancelled
    listeningChanged = Signal(bool)                # a preview is playing (not paused / stopped)
    danceChanged = Signal(bool)                    # busy or listening: the mascot dances

    def __init__(self) -> None:
        super().__init__()
        self._running: Dict[str, int] = {}
        self._listening = False
        self.batches_this_session = 0

    @property
    def busy(self) -> bool:
        return any(self._running.values())

    @property
    def listening(self) -> bool:
        return self._listening

    @property
    def dancing(self) -> bool:
        return self.busy or self._listening

    def batch_started(self, tool: str, user: bool = True) -> None:
        """``user=False`` for automatic work (e.g. re-rendering the track you are listening to
        after a mode change): the mascot dances but does not grow."""
        was_busy, was_dancing = self.busy, self.dancing
        self._running[tool] = self._running.get(tool, 0) + 1
        if user:
            self.batches_this_session += 1
        self.batchStarted.emit(tool, bool(user))
        if not was_busy:
            self.busyChanged.emit(True)
        self._dance_check(was_dancing)

    def batch_finished(self, tool: str, succeeded: int, failed: int, cancelled: bool) -> None:
        was_dancing = self.dancing
        if self._running.get(tool, 0) > 0:
            self._running[tool] -= 1
        self.batchFinished.emit(tool, succeeded, failed, cancelled)
        if not self.busy:
            self.busyChanged.emit(False)
        self._dance_check(was_dancing)

    def set_listening(self, listening: bool) -> None:
        """Connected to PreviewPlayer.playingChanged."""
        listening = bool(listening)
        if listening == self._listening:
            return
        was_dancing = self.dancing
        self._listening = listening
        self.listeningChanged.emit(listening)
        self._dance_check(was_dancing)

    def _dance_check(self, was_dancing: bool) -> None:
        if self.dancing != was_dancing:
            self.danceChanged.emit(self.dancing)

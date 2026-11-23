"""
Header companion: the speech bubble (random phrases, next / hide) and the
mascot, wired to the app's ActivityHub.

    companion = CompanionPanel(context.activity, context.settings)
    header.addWidget(companion)
    ...
    companion.start()            # once the window is visible: the egg hatches

Layout: [mascot][bubble] right after the logo / title block. Everything is
sized to a fixed maximum (bubble <= 360 x 78 px, mascot box 108 x 96 px), so
the header layout never moves when the mascot grows.
"""

from __future__ import annotations

import time
from typing import Optional

from PySide6.QtCore import QPointF, QPropertyAnimation, QRectF, QSettings, QSize, Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ..i18n.phrases import CATEGORY_LABELS, BY_ID, Phrase, PhraseDeck
from .activity import ActivityHub
from .mascot import BOX_H, DANCE_NAMES, IDLE_NAMES, MAX_LEVEL, MascotWidget, find_asset
from .translate import bind_tip, language, on_language_changed, tr

BUBBLE_MAX_W, BUBBLE_MIN_W, BUBBLE_H = 360, 200, 78
LISTEN_LINE_EVERY_S = 45.0
TAIL = 10
ROTATE_MS = 30_000


class PhraseBubble(QWidget):
    """Rounded speech bubble with a tail pointing at the mascot (left; right in RTL languages)."""

    def __init__(self, deck: PhraseDeck, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.deck = deck
        self.busy = False
        self.current: Optional[Phrase] = None
        self.setObjectName("Bubble")
        self.setFixedHeight(BUBBLE_H)
        self.setMinimumWidth(BUBBLE_MIN_W)
        self.setMaximumWidth(BUBBLE_MAX_W)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        row = QHBoxLayout(self)
        row.setContentsMargins(8 + TAIL, 8, 8 + TAIL, 8)   # symmetric: the tail side flips in RTL
        row.setSpacing(6)
        self.body = QWidget()
        texts = QVBoxLayout(self.body)
        texts.setContentsMargins(0, 0, 0, 0)
        texts.setSpacing(2)
        self.chip = QLabel("")
        self.chip.setObjectName("BubbleChip")
        self.text = QLabel("")
        self.text.setObjectName("BubbleText")
        self.text.setWordWrap(True)
        self.text.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        texts.addWidget(self.chip)
        texts.addWidget(self.text, 1)
        buttons = QVBoxLayout()                    # only "hide": a click on the mascot gives the next phrase
        buttons.setSpacing(2)
        self.hide_button = QPushButton("–")
        self.hide_button.setObjectName("BubbleButton")
        self.hide_button.setFixedSize(QSize(22, 22))
        bind_tip(self.hide_button, "Hide the bubble")
        buttons.addWidget(self.hide_button)
        buttons.addStretch(1)
        row.addWidget(self.body, 1)
        row.addLayout(buttons)

        self._fade_effect = QGraphicsOpacityEffect(self.body)
        self._fade_effect.setOpacity(1.0)
        self.body.setGraphicsEffect(self._fade_effect)
        self._fade = QPropertyAnimation(self._fade_effect, b"opacity", self)
        self._fade.setDuration(260)
        self._fade.setStartValue(0.0)
        self._fade.setEndValue(1.0)

        self._timer = QTimer(self)
        self._timer.setInterval(ROTATE_MS)
        self._timer.timeout.connect(self.next_phrase)
        on_language_changed(lambda _code: self._render(animate=False), self)

    # ---- phrases -------------------------------------------------------------
    def show_phrase(self, phrase: Optional[Phrase]) -> None:
        if phrase is None:
            return
        self.current = phrase
        self._render(animate=True)
        if self.isVisible() and not self.underMouse():
            self._timer.start()                 # restart the rotation from now

    def next_phrase(self) -> None:
        self.show_phrase(self.deck.next(self.busy))

    def show_event(self, name: str) -> None:
        self.show_phrase(self.deck.event(name) or self.deck.next(self.busy))

    def _render(self, animate: bool) -> None:
        phrase = self.current
        if phrase is None:
            return
        text = phrase.text(language())
        label = CATEGORY_LABELS.get(phrase.category, "")
        self.chip.setText(tr(label).upper() if label else "")
        self.chip.setVisible(bool(label))
        self.text.setText(text)
        self.text.setToolTip(text)
        if animate:
            self._fade.stop()
            self._fade.start()

    # ---- Qt events -----------------------------------------------------------
    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        self._timer.start()

    def hideEvent(self, event) -> None:  # noqa: N802
        super().hideEvent(event)
        self._timer.stop()

    def enterEvent(self, event) -> None:  # noqa: N802 - reading: pause the rotation
        super().enterEvent(event)
        self._timer.stop()

    def leaveEvent(self, event) -> None:  # noqa: N802
        super().leaveEvent(event)
        if self.isVisible():
            self._timer.start()

    def paintEvent(self, _event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = float(self.width()), float(self.height())
        rtl = self.layoutDirection() == Qt.LayoutDirection.RightToLeft     # mascot on the right in Arabic
        box = QRectF(0.5 if rtl else TAIL + 0.5, 0.5, w - TAIL - 1.0, h - 1.0)
        path = QPainterPath()
        path.addRoundedRect(box, 14.0, 14.0)
        tail = QPainterPath()
        mid = h * 0.62
        edge, tip = (box.right() - 1.0, w - 1.0) if rtl else (box.left() + 1.0, 1.0)
        tail.moveTo(QPointF(edge, mid - 7.0))
        tail.lineTo(QPointF(tip, mid + 3.0))
        tail.lineTo(QPointF(edge, mid + 6.0))
        tail.closeSubpath()
        path = path.united(tail)
        pen = QPen(QColor(0, 180, 216, 110))
        pen.setWidthF(1.0)
        painter.setPen(pen)
        painter.setBrush(QColor(255, 255, 255, 235))
        painter.drawPath(path)
        painter.end()


class CompanionPanel(QWidget):
    """Bubble + mascot, reacting to batches (grow, dance, comment)."""

    HIDDEN_KEY = "companion/bubble_hidden"

    def __init__(self, activity: ActivityHub, settings: QSettings, parent: Optional[QWidget] = None,
                 deck: Optional[PhraseDeck] = None) -> None:
        super().__init__(parent)
        self.activity, self.store = activity, settings
        self.setFixedHeight(BOX_H)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self.deck = deck or PhraseDeck()
        self.bubble = PhraseBubble(self.deck)
        self.reopen_button = QPushButton("💬")
        self.reopen_button.setObjectName("BubbleReopen")
        self.reopen_button.setFixedSize(QSize(30, 30))
        bind_tip(self.reopen_button, "Show the phrases again")
        self.mascot = MascotWidget(find_asset(DANCE_NAMES), find_asset(IDLE_NAMES))

        layout = QHBoxLayout(self)                 # [mascot][bubble ◁ pointing at it] ......
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        layout.addWidget(self.mascot, 0, Qt.AlignmentFlag.AlignBottom)
        layout.addWidget(self.bubble, 1, Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(self.reopen_button, 0, Qt.AlignmentFlag.AlignVCenter)
        layout.addStretch(1)

        hidden = str(self.store.value(self.HIDDEN_KEY, "false")) == "true"
        self.bubble.setVisible(not hidden)
        self.reopen_button.setVisible(hidden)
        self.bubble.current = BY_ID.get("m.hello")
        self.bubble._render(animate=False)
        self.bubble.hide_button.clicked.connect(lambda: self.set_bubble_hidden(True))
        self.reopen_button.clicked.connect(lambda: self.set_bubble_hidden(False))
        self.mascot.clicked.connect(self._on_mascot_clicked)
        self.mascot.hatched.connect(lambda: self.bubble.show_event("hatch"))
        activity.batchStarted.connect(self._on_batch_started)
        activity.busyChanged.connect(self._on_busy)
        activity.danceChanged.connect(self.mascot.set_busy)          # batch running or audio playing
        activity.listeningChanged.connect(self._on_listening)
        activity.batchFinished.connect(self._on_batch_finished)
        self._last_listen_line = -LISTEN_LINE_EVERY_S

    def start(self) -> None:
        """Hatch the egg (call when the window is on screen)."""
        self.mascot.start()

    def set_bubble_hidden(self, hidden: bool) -> None:
        self.bubble.setVisible(not hidden)
        self.reopen_button.setVisible(hidden)
        self.store.setValue(self.HIDDEN_KEY, "true" if hidden else "false")
        if not hidden:
            self.bubble.next_phrase()

    # ---- reactions -----------------------------------------------------------
    def _on_mascot_clicked(self) -> None:
        if self.bubble.isVisible():
            self.bubble.next_phrase()
        else:
            self.set_bubble_hidden(False)

    def _on_busy(self, busy: bool) -> None:
        self.bubble.busy = busy

    def _on_listening(self, listening: bool) -> None:
        """A line about the music when playback starts (not on every A/B switch)."""
        now = time.monotonic()
        if listening and not self.activity.busy and now - self._last_listen_line >= LISTEN_LINE_EVERY_S:
            self._last_listen_line = now
            self.bubble.show_event("listen")

    def _on_batch_started(self, _tool: str, user: bool = True) -> None:
        if not user:
            self.bubble.show_event("action")
        elif self.mascot.grow():
            self.bubble.show_event("grow_max" if self.mascot.level >= MAX_LEVEL else "grow")
        else:
            self.bubble.show_event("action")

    def _on_batch_finished(self, _tool: str, _succeeded: int, failed: int, cancelled: bool) -> None:
        if self.activity.busy:
            return                                  # another tool is still working
        self.bubble.show_event("batch_cancelled" if cancelled else "batch_failed" if failed else "batch_done")

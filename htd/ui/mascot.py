"""
The living mascot shown in the header.

Phases
    hatching  when the app opens: an egg wobbles, cracks and opens (~2.6 s)
    idle      no batch running: calm floating + breathing, on its still image
    action    a batch is running: plays the dancing GIF

Growth
    +1 size per batch started (whatever the number of tracks), from MIN_SCALE
    up to the full box at MAX_LEVEL. The level lives in memory only, so every
    session (each launch of the app) starts small again.

Assets (all optional, looked up in assets/ - also inside a PyInstaller build)
    mascot_dance.gif    the dancing animation (action phase)
    mascot_idle.png     still image for the idle phase (else the GIF's first frame)
Without the GIF a drawn mascot is used, with its own dance, so nothing breaks.

Cost: one 40 ms QTimer (25 fps) repainting a ~108 x 96 px widget, paused when
the window is hidden or minimised. QMovie decodes the GIF frame by frame.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Iterable, Optional

from PySide6.QtCore import QElapsedTimer, QEasingCurve, QPointF, QRectF, QSize, Qt, QTimer, QVariantAnimation, Signal
from PySide6.QtGui import QColor, QFont, QMovie, QPainter, QPainterPath, QPen, QPixmap, QRadialGradient
from PySide6.QtWidgets import QWidget

from .. import config
from .translate import on_language_changed, tr

BOX_W, BOX_H = 108, 96          # hard maximum: the mascot never grows beyond this box
GROUND = 9                      # room under the feet for the shadow
MAX_LEVEL = 8
MIN_SCALE = 0.55
HATCH_MS = 2600
FRAME_MS = 40

DANCE_NAMES = ("mascot_dance.gif", "mascot.gif")
IDLE_NAMES = ("mascot_idle.png", "mascot_idle.gif", "mascot.png")


def find_asset(names: Iterable[str]) -> Optional[Path]:
    """First existing file among ``assets/<name>`` (source tree or PyInstaller bundle)."""
    for name in names:
        path = config.asset(name)
        if path.is_file():
            return path
    return None


def scale_for(level: int) -> float:
    level = max(0, min(MAX_LEVEL, level))
    return MIN_SCALE + (1.0 - MIN_SCALE) * level / MAX_LEVEL


def _clamp01(value: float) -> float:
    return 0.0 if value < 0.0 else 1.0 if value > 1.0 else value


def _out_back(x: float, overshoot: float = 1.70158) -> float:
    x = _clamp01(x) - 1.0
    return x * x * ((overshoot + 1.0) * x + overshoot) + 1.0


class MascotWidget(QWidget):
    clicked = Signal()
    hatched = Signal()
    grew = Signal(int)                       # new level

    def __init__(self, dance_gif: Optional[Path] = None, idle_image: Optional[Path] = None,
                 parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setFixedSize(BOX_W, BOX_H)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.movie: Optional[QMovie] = None
        self.still: Optional[QPixmap] = None
        self.asset_note = ""
        self._load_assets(dance_gif, idle_image)

        self.state = "egg"                   # egg -> hatching -> idle | action
        self.level = 0
        self._busy = False
        self._scale = scale_for(0)
        self._clock = QElapsedTimer()
        self._clock.start()
        self._phase_start = 0
        self._hop_start = -10_000
        self._grow_mark = -10_000

        self._timer = QTimer(self)
        self._timer.setInterval(FRAME_MS)
        self._timer.timeout.connect(self._tick)
        self._grow_anim = QVariantAnimation(self)
        self._grow_anim.setDuration(750)
        self._grow_anim.setEasingCurve(QEasingCurve.Type.OutBack)
        self._grow_anim.valueChanged.connect(self._set_scale)
        self._grow_anim.finished.connect(self._resize_movie)
        on_language_changed(lambda _code: self._update_tooltip(), self)
        self._update_tooltip()
        self._resize_movie()

    # ================================================================ assets
    def _load_assets(self, dance_gif: Optional[Path], idle_image: Optional[Path]) -> None:
        if dance_gif is not None and dance_gif.is_file():
            movie = QMovie(str(dance_gif), parent=self)
            if movie.isValid():
                self.movie = movie
                movie.frameChanged.connect(lambda _frame: self.update())
                if movie.jumpToFrame(0):
                    frame = movie.currentPixmap()
                    if not frame.isNull():
                        self.still = frame.copy()
            else:
                self.asset_note = f"{dance_gif.name}: not a readable GIF"
        if idle_image is not None and idle_image.is_file():
            pixmap = QPixmap(str(idle_image))
            if not pixmap.isNull():
                self.still = pixmap

    @property
    def uses_gif(self) -> bool:
        return self.movie is not None

    # ================================================================ control
    def start(self) -> None:
        """Begin the hatching animation (call once the window is shown)."""
        if self.state != "egg":
            return
        self.state = "hatching"
        self._phase_start = self._now()
        self._timer.start()

    def skip_hatch(self) -> None:
        if self.state in ("egg", "hatching"):
            self._finish_hatch()

    def set_busy(self, busy: bool) -> None:
        """Action phase while something is processing, idle otherwise."""
        self._busy = bool(busy)
        if self.state in ("idle", "action"):
            self._enter("action" if self._busy else "idle")

    def grow(self) -> bool:
        """+1 size (capped). Returns False when the maximum size is already reached."""
        if self.level >= MAX_LEVEL:
            return False
        self.level += 1
        self._grow_anim.stop()
        self._grow_anim.setStartValue(float(self._scale))
        self._grow_anim.setEndValue(float(scale_for(self.level)))
        self._grow_anim.start()
        self._grow_mark = self._now()
        self._update_tooltip()
        self.grew.emit(self.level)
        return True

    def hop(self) -> None:
        self._hop_start = self._now()

    # ================================================================ internals
    def _now(self) -> int:
        return int(self._clock.elapsed())

    def _set_scale(self, value: object) -> None:
        try:
            self._scale = float(value)
        except (TypeError, ValueError):
            return
        self.update()

    def _enter(self, state: str) -> None:
        if state == self.state:
            return
        self.state = state
        self._phase_start = self._now()
        if self.movie is not None:
            if state == "action":
                self.movie.start()
            else:
                self.movie.stop()
        if not self._timer.isActive() and self.isVisible():
            self._timer.start()
        self.update()

    def _finish_hatch(self) -> None:
        self.state = "idle"                       # _enter() needs a different previous state
        self._enter("action" if self._busy else "idle")
        if not self._busy:
            self._phase_start = self._now()
        if not self._timer.isActive():
            self._timer.start()
        self.hatched.emit()

    def _resize_movie(self) -> None:
        """Let QMovie decode the GIF directly at the drawn size (cheap repaints while dancing,
        so the audio and the interface stay smooth). Called at start and after each growth."""
        if self.movie is None or self.still is None or self.still.isNull():
            return
        width, height = self._fit(self.still, self._full_height() * scale_for(self.level))
        try:
            ratio = float(self.devicePixelRatioF()) or 1.0
        except (TypeError, ValueError):
            ratio = 1.0
        self.movie.setScaledSize(QSize(max(1, int(round(width * ratio))), max(1, int(round(height * ratio)))))

    def _tick(self) -> None:
        window = self.window()
        if not self.isVisible() or (window is not None and window.isMinimized()):
            return
        if self.state == "hatching" and self._now() - self._phase_start >= HATCH_MS:
            self._finish_hatch()
        now = self._now()
        if (self.state == "action" and self.movie is not None
                and now - self._hop_start > 500 and now - self._grow_mark > 950):
            return                                   # the GIF repaints on its own frames
        self.update()

    def _update_tooltip(self) -> None:
        self.setToolTip(tr("Level {level}/{max}: I grow with every batch you run in this session. "
                           "Click me for another line.", level=self.level, max=MAX_LEVEL))

    # ---- Qt events -----------------------------------------------------------
    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        if self.state != "egg":
            self._timer.start()
        if self.movie is not None and self.state == "action":
            self.movie.setPaused(False)

    def hideEvent(self, event) -> None:  # noqa: N802
        super().hideEvent(event)
        self._timer.stop()
        if self.movie is not None and self.state == "action":
            self.movie.setPaused(True)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self.hop()
            self.clicked.emit()
        super().mousePressEvent(event)

    # ================================================================ painting
    def paintEvent(self, _event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        now = self._now()
        elapsed = now - self._phase_start
        if self.state in ("egg", "hatching"):
            self._paint_hatch(painter, elapsed if self.state == "hatching" else 0)
        else:
            self._paint_mascot(painter, elapsed, now)
        if now - self._grow_mark < 900:
            self._paint_plus_one(painter, (now - self._grow_mark) / 900.0)
        painter.end()

    # ---- geometry ---------------------------------------------------------
    def _full_height(self) -> float:
        return BOX_H - GROUND - 4.0

    def _fit(self, pixmap: Optional[QPixmap], height: float) -> tuple:
        """(width, height) of the mascot drawn ``height`` px tall, kept inside the box."""
        if pixmap is None or pixmap.isNull() or pixmap.height() == 0:
            ratio = 1.0
        else:
            ratio = pixmap.width() / pixmap.height()
        width = height * ratio
        if width > BOX_W - 4:
            width = BOX_W - 4.0
            height = width / ratio
        return width, height

    def _shadow(self, painter: QPainter, width: float, lift: float) -> None:
        cx, cy = BOX_W / 2.0, BOX_H - GROUND / 2.0 - 1
        w = max(8.0, width * 0.62 * (1.0 - 0.25 * _clamp01(lift / 12.0)))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(11, 18, 32, int(42 * (1.0 - 0.4 * _clamp01(lift / 12.0)))))
        painter.drawEllipse(QRectF(cx - w / 2, cy - 2.5, w, 5.0))

    def _hop_offset(self, now: int) -> float:
        k = (now - self._hop_start) / 450.0
        return -math.sin(math.pi * k) * 11.0 if 0.0 <= k < 1.0 else 0.0

    # ---- idle / action ----------------------------------------------------
    def _paint_mascot(self, painter: QPainter, elapsed: int, now: int) -> None:
        dancing = self.state == "action"
        frame = None
        if dancing and self.movie is not None:
            frame = self.movie.currentPixmap()
            if frame.isNull():
                frame = self.still
        elif self.still is not None:
            frame = self.still

        height = self._full_height() * self._scale
        sx = sy = 1.0
        angle = 0.0
        if dancing and self.movie is None:              # drawn mascot dances by itself
            bounce = abs(math.sin(math.pi * elapsed / 340.0))
            lift = bounce * 9.0
            sx, sy = 1.0 + 0.09 * (1.0 - bounce), 1.0 - 0.09 * (1.0 - bounce)
            angle = 7.0 * math.sin(2.0 * math.pi * elapsed / 680.0)
        elif dancing:
            lift = 0.0                                   # the GIF carries the motion
        else:                                            # idle: calm float + breathing
            wave = math.sin(2.0 * math.pi * elapsed / 2600.0)
            lift = 3.0 + 3.0 * wave
            breathe = 1.0 + 0.018 * math.sin(2.0 * math.pi * elapsed / 2600.0 + math.pi / 2)
            sx = sy = breathe
        lift -= self._hop_offset(now)

        width, height = self._fit(frame, height)
        self._shadow(painter, width, lift)
        bottom = BOX_H - GROUND - lift
        painter.save()
        painter.translate(BOX_W / 2.0, bottom)
        painter.rotate(angle)
        painter.scale(sx, sy)
        target = QRectF(-width / 2.0, -height, width, height)
        if frame is not None and not frame.isNull():
            painter.drawPixmap(target, frame, QRectF(frame.rect()))
        else:
            self._draw_creature(painter, target, now, dancing)
        painter.restore()
        if dancing and self.movie is None:
            self._paint_notes(painter, elapsed)

    def _paint_notes(self, painter: QPainter, elapsed: int) -> None:
        font = QFont(painter.font())
        font.setPixelSize(12)
        painter.setFont(font)
        for index, x in enumerate((BOX_W * 0.16, BOX_W * 0.82)):
            k = ((elapsed + index * 600) % 1200) / 1200.0
            painter.setPen(QColor(10, 132, 255, int(220 * (1.0 - k))))
            painter.drawText(QPointF(x - 4, BOX_H * 0.55 - k * 30.0), "♪" if index == 0 else "♫")

    def _paint_plus_one(self, painter: QPainter, k: float) -> None:
        font = QFont(painter.font())
        font.setPixelSize(12)
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(QColor(0, 160, 200, int(255 * (1.0 - k))))
        painter.drawText(QPointF(BOX_W - 24, 18 - 10 * k), "+1")

    # ---- the drawn mascot (used when there is no GIF / still image) ---------
    def _draw_creature(self, painter: QPainter, rect: QRectF, now: int, dancing: bool) -> None:
        w, h = rect.width(), rect.height()
        body = QRectF(rect.left() + w * 0.08, rect.top() + h * 0.16, w * 0.84, h * 0.84)
        gradient = QRadialGradient(QPointF(body.left() + body.width() * 0.35, body.top() + body.height() * 0.3),
                                   body.width() * 0.8)
        gradient.setColorAt(0.0, QColor("#e9fbff"))
        gradient.setColorAt(0.45, QColor("#3fd6ff"))
        gradient.setColorAt(1.0, QColor("#0a84ff"))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(gradient)
        painter.drawRoundedRect(body, body.width() * 0.42, body.height() * 0.46)
        # headphones
        band = QPen(QColor("#0b1220"))
        band.setWidthF(max(1.5, w * 0.045))
        band.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(band)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        arc = QRectF(body.left() + w * 0.02, rect.top() + h * 0.04, body.width() - w * 0.04, h * 0.62)
        painter.drawArc(arc, 20 * 16, 140 * 16)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#0b1220"))
        cup_w, cup_h = w * 0.13, h * 0.22
        cup_y = rect.top() + h * 0.30
        painter.drawRoundedRect(QRectF(body.left() - cup_w * 0.45, cup_y, cup_w, cup_h), cup_w * 0.4, cup_w * 0.4)
        painter.drawRoundedRect(QRectF(body.right() - cup_w * 0.55, cup_y, cup_w, cup_h), cup_w * 0.4, cup_w * 0.4)
        # eyes (blink every ~3.8 s)
        blink = (now % 3800) < 130 and not dancing
        eye_w, eye_h = w * 0.15, h * (0.03 if blink else 0.19)
        eye_y = body.top() + body.height() * 0.30 + (h * 0.08 if blink else 0.0)
        for cx in (body.left() + body.width() * 0.34, body.left() + body.width() * 0.66):
            painter.setBrush(QColor("#ffffff"))
            painter.drawEllipse(QRectF(cx - eye_w / 2, eye_y, eye_w, eye_h))
            if not blink:
                painter.setBrush(QColor("#0b1220"))
                pupil = eye_w * 0.55
                painter.drawEllipse(QRectF(cx - pupil / 2, eye_y + eye_h * 0.38, pupil, pupil * 1.1))
        # smile
        mouth = QPen(QColor("#0b1220"))
        mouth.setWidthF(max(1.2, w * 0.03))
        mouth.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(mouth)
        smile = QRectF(body.left() + body.width() * 0.36, body.top() + body.height() * 0.50,
                       body.width() * 0.28, body.height() * (0.22 if dancing else 0.16))
        painter.drawArc(smile, 200 * 16, 140 * 16)

    # ---- the egg ----------------------------------------------------------
    def _egg_path(self, w: float, h: float) -> QPainterPath:
        path = QPainterPath()
        path.moveTo(0.0, -h / 2)
        path.cubicTo(w * 0.42, -h / 2, w / 2, -h * 0.05, w / 2, h * 0.12)
        path.cubicTo(w / 2, h * 0.38, w * 0.28, h / 2, 0.0, h / 2)
        path.cubicTo(-w * 0.28, h / 2, -w / 2, h * 0.38, -w / 2, h * 0.12)
        path.cubicTo(-w / 2, -h * 0.05, -w * 0.42, -h / 2, 0.0, -h / 2)
        path.closeSubpath()
        return path

    def _crack_points(self, w: float) -> list:
        xs = [-w / 2 - 2, -w * 0.32, -w * 0.16, 0.0, w * 0.16, w * 0.32, w / 2 + 2]
        ys = [0.0, -5.0, 3.0, -4.0, 4.0, -3.0, 1.0]
        return [QPointF(x, y) for x, y in zip(xs, ys)]

    def _paint_egg_shell(self, painter: QPainter, w: float, h: float) -> None:
        gradient = QRadialGradient(QPointF(-w * 0.18, -h * 0.22), w * 0.9)
        gradient.setColorAt(0.0, QColor("#ffffff"))
        gradient.setColorAt(0.7, QColor("#e3f7ff"))
        gradient.setColorAt(1.0, QColor("#a9e6fb"))
        painter.setBrush(gradient)
        outline = QPen(QColor(0, 150, 200, 120))
        outline.setWidthF(1.2)
        painter.setPen(outline)
        painter.drawPath(self._egg_path(w, h))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(0, 180, 216, 90))
        for fx, fy, r in ((-0.2, -0.18, 0.07), (0.18, 0.05, 0.05), (-0.05, 0.25, 0.06), (0.22, -0.28, 0.04)):
            painter.drawEllipse(QPointF(w * fx, h * fy), w * r, w * r)

    def _paint_hatch(self, painter: QPainter, t: int) -> None:
        full = self._full_height()
        egg_h = full * 0.62
        egg_w = egg_h * 0.78
        pop = _out_back(t / 300.0) if t < 300 else 1.0
        cx, ground = BOX_W / 2.0, BOX_H - GROUND
        self._shadow(painter, egg_w, 0.0)

        if t < 1700:                                         # wobble, then cracks
            amplitude = 10.0 * _clamp01((t - 300) / 1400.0)
            angle = amplitude * math.sin(2.0 * math.pi * t / 320.0)
            painter.save()
            painter.translate(cx, ground)
            painter.rotate(angle)
            painter.translate(0.0, -egg_h / 2 * pop)
            painter.scale(pop, pop)
            self._paint_egg_shell(painter, egg_w, egg_h)
            progress = _clamp01((t - 1100) / 600.0)
            if progress > 0:
                points = self._crack_points(egg_w)
                shown = max(2, int(round(progress * len(points))))
                crack = QPen(QColor("#0b1220"))
                crack.setWidthF(1.4)
                painter.setPen(crack)
                for a, b in zip(points[:shown - 1], points[1:shown]):
                    painter.drawLine(a, b)
            painter.restore()
            return

        k = _clamp01((t - 1700) / (HATCH_MS - 1700.0))       # opening
        # the mascot rises out of the bottom shell
        frame = self.still
        grow = 0.2 + 0.8 * _out_back(k)
        height = full * self._scale * grow
        width, height = self._fit(frame, height)
        painter.save()
        painter.translate(cx, ground - 2.0 * k)
        target = QRectF(-width / 2.0, -height, width, height)
        if frame is not None and not frame.isNull():
            painter.drawPixmap(target, frame, QRectF(frame.rect()))
        else:
            self._draw_creature(painter, target, self._now(), False)
        painter.restore()
        # shell halves
        points = self._crack_points(egg_w)
        top_region = QPainterPath()
        top_region.moveTo(-egg_w, -egg_h)
        top_region.lineTo(egg_w, -egg_h)
        for point in reversed(points):
            top_region.lineTo(point)
        top_region.closeSubpath()
        bottom_region = QPainterPath()
        bottom_region.moveTo(-egg_w, egg_h)
        bottom_region.lineTo(egg_w, egg_h)
        for point in reversed(points):
            bottom_region.lineTo(point)
        bottom_region.closeSubpath()
        painter.save()                                        # top half flies off
        painter.setOpacity(1.0 - k)
        painter.translate(cx + 10.0 * k, ground - egg_h / 2 - 26.0 * k)
        painter.rotate(-35.0 * k)
        painter.setClipPath(top_region)
        self._paint_egg_shell(painter, egg_w, egg_h)
        painter.restore()
        painter.save()                                        # bottom half fades away
        painter.setOpacity(_clamp01(1.0 - (k - 0.55) / 0.45))
        painter.translate(cx, ground - egg_h / 2)
        painter.setClipPath(bottom_region)
        self._paint_egg_shell(painter, egg_w, egg_h)
        painter.restore()
        # sparkles
        painter.setPen(Qt.PenStyle.NoPen)
        for index in range(6):
            angle = index * math.pi / 3.0 + 0.4
            radius = 12.0 + 30.0 * k
            alpha = int(230 * (1.0 - k))
            painter.setBrush(QColor(0, 212, 255, alpha) if index % 2 else QColor(10, 132, 255, alpha))
            point = QPointF(cx + math.cos(angle) * radius, ground - egg_h * 0.55 + math.sin(angle) * radius * 0.7)
            painter.drawEllipse(point, 2.2, 2.2)

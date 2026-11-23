"""Reusable widgets: cards, pills, readouts, logo, drop zone, sliders, output picker.

Texts given to these widgets are English source strings: they are translated
(and re-translated live) here, so callers only mark them with N_().
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable, List, Optional, Sequence, Tuple

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPixmap, QRadialGradient
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QStyle,
    QStyleOptionSlider,
    QFileDialog,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QRadioButton,
    QSizePolicy,
    QSlider,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from .. import config
from ..i18n import script_allows_spacing
from .translate import N_, bind, bind_call, bind_tip, on_language_changed, tr


def refresh_style(widget: QWidget) -> None:
    """Re-apply the style sheet after a dynamic property changed."""
    widget.style().unpolish(widget)
    widget.style().polish(widget)
    widget.update()


def set_prop(widget: QWidget, name: str, value) -> None:
    if widget.property(name) != value:
        widget.setProperty(name, value)
        refresh_style(widget)


def _apply_spacing(widget: QWidget) -> None:
    pixels = float(widget.property("letterSpacingPx") or 0.0)
    if not script_allows_spacing():
        pixels = 0.0                       # Arabic / Devanagari: spacing would break the joined letters
    font = QFont(QApplication.font())      # current language's font families
    font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, pixels)
    widget.setFont(font)


def spaced(widget: QWidget, pixels: float = 1.5) -> QWidget:
    """Letter spacing for small uppercase labels (Qt style sheets cannot set it).
    Re-applied after a language change (font families, scripts without spacing)."""
    widget.setProperty("letterSpacingPx", float(pixels))
    _apply_spacing(widget)
    on_language_changed(lambda _code, w=widget: _apply_spacing(w), widget)
    return widget


def add_shadow(widget: QWidget, blur: float = 30.0, y: float = 8.0, alpha: int = 26) -> None:
    effect = QGraphicsDropShadowEffect(widget)
    effect.setBlurRadius(blur)
    effect.setOffset(0.0, y)
    effect.setColor(QColor(11, 18, 32, alpha))
    widget.setGraphicsEffect(effect)


class Card(QFrame):
    """White rounded panel with a soft shadow."""

    def __init__(self, parent: Optional[QWidget] = None, name: str = "Card", shadow: bool = True) -> None:
        super().__init__(parent)
        self.setObjectName(name)
        if shadow:
            add_shadow(self)


class Pill(QLabel):
    """Small uppercase status label: kind = idle | run | ok | warn | error."""

    def __init__(self, text: str = "", kind: str = "idle", parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("Pill")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        spaced(self, 1.0)
        self.set_state(kind, text)

    def set_state(self, kind: str, text: str) -> None:
        self.setText(text.upper())
        set_prop(self, "kind", kind)


class SectionTitle(QLabel):
    def __init__(self, text: str, parent: Optional[QWidget] = None) -> None:
        super().__init__("", parent)
        self.setObjectName("SectionTitle")
        spaced(self, 1.8)
        bind_call(self, lambda value: self.setText(value.upper()), text)


class Readout(QFrame):
    """A labelled measurement: LABEL / big value + unit / small hint."""

    def __init__(self, label: str, unit: str, accent: bool = False, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("Readout")
        self.setProperty("accent", accent)
        self._unit = unit
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 9, 12, 9)
        layout.setSpacing(1)
        title = QLabel("")
        bind_call(title, lambda value: title.setText(value.upper()), label)
        title.setObjectName("ReadoutLabel")
        spaced(title, 1.2)
        self.value = QLabel("-")
        self.value.setObjectName("ReadoutValue")
        self.value.setTextFormat(Qt.TextFormat.RichText)
        self.hint = QLabel("")
        self.hint.setObjectName("Hint")
        self.hint.setWordWrap(True)
        for widget in (title, self.value, self.hint):
            layout.addWidget(widget)

    def set(self, value: str, hint: str = "", level: str = "") -> None:
        """``level``: '' / 'caution' / 'risk' (tints the box, for alerts)."""
        value = value.replace("-", "−", 1) if value.startswith("-") else value
        unit = (f'<span style="font-size:11px; color:#8a94a6; font-weight:600;"> {self._unit}</span>'
                if self._unit else "")
        self.value.setText(value + unit)
        self.hint.setText(hint)
        set_prop(self, "level", level)


def orb_pixmap(size: int) -> QPixmap:
    """Fallback logo: a glossy cyan orb (used when assets/logo.png is missing)."""
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    gradient = QRadialGradient(QPointF(size * 0.32, size * 0.28), size * 0.75)
    gradient.setColorAt(0.0, QColor("#ffffff"))
    gradient.setColorAt(0.35, QColor("#dff8ff"))
    gradient.setColorAt(0.7, QColor("#00c8ff"))
    gradient.setColorAt(1.0, QColor("#0a84ff"))
    painter.setBrush(gradient)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawRoundedRect(QRectF(1, 1, size - 2, size - 2), size * 0.3, size * 0.3)
    painter.end()
    return pixmap


def logo_pixmap(size: int) -> QPixmap:
    path = config.asset("logo.png")
    if path.is_file():
        pixmap = QPixmap(str(path))
        if not pixmap.isNull():
            return pixmap.scaled(QSize(size, size), Qt.AspectRatioMode.KeepAspectRatio,
                                 Qt.TransformationMode.SmoothTransformation)
    return orb_pixmap(size)


class LabeledSlider(QWidget):
    """Horizontal slider for a float value with a fixed step, plus its value label."""

    valueChanged = Signal(float)

    def __init__(self, title: str, minimum: float, maximum: float, step: float, fmt: str,
                 tooltip: str = "", parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._min, self._step, self._fmt = minimum, step, fmt
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 4, 0, 4)
        layout.setSpacing(4)
        row = QHBoxLayout()
        label = bind(QLabel(), title)
        self._value_label = QLabel()
        self._value_label.setStyleSheet("color:#0a84ff; font-weight:700;")
        row.addWidget(label)
        row.addStretch(1)
        row.addWidget(self._value_label)
        layout.addLayout(row)
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(0, int(round((maximum - minimum) / step)))
        self.slider.setSingleStep(1)
        self.slider.setPageStep(max(1, int(round(1.0 / step))))
        layout.addWidget(self.slider)
        if tooltip:
            bind_tip(self, tooltip)
        self.slider.valueChanged.connect(self._on_change)
        self._on_change(self.slider.value())

    def value(self) -> float:
        return round(self._min + self.slider.value() * self._step, 4)

    def setValue(self, value: float) -> None:
        self.slider.setValue(int(round((value - self._min) / self._step)))
        self._value_label.setText(self._fmt.format(self.value()))

    def _on_change(self, _position: int) -> None:
        self._value_label.setText(self._fmt.format(self.value()))
        self.valueChanged.emit(self.value())


class CollapsibleSection(QWidget):
    """A header button that shows / hides its content."""

    def __init__(self, title: str, expanded: bool = False, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        self.toggle = QToolButton()
        self.toggle.setObjectName("Ghost")
        bind(self.toggle, title)
        self.toggle.setCheckable(True)
        self.toggle.setChecked(expanded)
        self.toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.toggle.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.content = QWidget()
        self.content_layout = QVBoxLayout(self.content)
        self.content_layout.setContentsMargins(4, 4, 4, 4)
        self.content_layout.setSpacing(6)
        layout.addWidget(self.toggle)
        layout.addWidget(self.content)
        self.toggle.toggled.connect(self._apply)
        self._apply(expanded)

    def _apply(self, expanded: bool) -> None:
        self.toggle.setArrowType(Qt.ArrowType.DownArrow if expanded else Qt.ArrowType.RightArrow)
        self.content.setVisible(expanded)


class OutputPicker(QWidget):
    """'Next to the source files' or a chosen folder."""

    changed = Signal()

    def __init__(self, default_dir: Path, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        self.next_to_source = bind(QRadioButton(), "Next to the source files")
        self.custom = bind(QRadioButton(), "In this folder:")
        group = QButtonGroup(self)
        group.addButton(self.next_to_source)
        group.addButton(self.custom)
        self.custom.setChecked(True)
        row = QHBoxLayout()
        row.setSpacing(6)
        self.path_edit = QLineEdit(str(default_dir))
        browse = bind(QPushButton(), "Browse…")
        row.addWidget(self.path_edit, 1)
        row.addWidget(browse)
        layout.addWidget(self.next_to_source)
        layout.addWidget(self.custom)
        layout.addLayout(row)
        browse.clicked.connect(self._browse)
        self.next_to_source.toggled.connect(self._sync)
        self.path_edit.editingFinished.connect(self.changed.emit)
        self._sync()

    def _sync(self) -> None:
        self.path_edit.setEnabled(self.custom.isChecked())
        self.changed.emit()

    def _browse(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, tr("Choose the output folder"), self.path_edit.text())
        if folder:
            self.path_edit.setText(folder)
            self.custom.setChecked(True)
            self.changed.emit()

    def folder(self) -> Optional[Path]:
        """None means 'next to each source file'."""
        if self.next_to_source.isChecked():
            return None
        text = self.path_edit.text().strip()
        return Path(text).expanduser() if text else config.default_output_dir()

    def set_state(self, next_to_source: bool, folder: str) -> None:
        if folder:
            self.path_edit.setText(folder)
        (self.next_to_source if next_to_source else self.custom).setChecked(True)
        self._sync()


def collect_audio_files(paths: Iterable[Path], extensions: Sequence[str]) -> List[Path]:
    """Files with an accepted extension; folders are scanned recursively (hidden files skipped)."""
    wanted = {f".{ext.lower()}" for ext in extensions}
    found: List[Path] = []
    for path in paths:
        try:
            if path.is_dir():
                for child in sorted(path.rglob("*")):
                    if (child.is_file() and child.suffix.lower() in wanted
                            and not any(part.startswith(".") for part in child.relative_to(path).parts)):
                        found.append(child)
            elif path.is_file() and path.suffix.lower() in wanted:
                found.append(path)
        except OSError:
            continue
    return found


class DropZone(QFrame):
    """Drag-and-drop target for files and folders, with 'Add files' / 'Add folder' buttons."""

    pathsDropped = Signal(list)          # List[Path] of accepted audio files

    def __init__(self, extensions: Sequence[str], title: str, subtitle: str,
                 parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("DropZone")
        self.setAcceptDrops(True)
        self._extensions = tuple(extensions)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(16)
        icon = QLabel("⬇")
        icon.setStyleSheet("font-size:26px; color:#00b4d8;")
        texts = QVBoxLayout()
        texts.setSpacing(2)
        heading = bind(QLabel(), title)
        heading.setObjectName("DropTitle")
        sub = bind(QLabel(), subtitle)
        sub.setObjectName("Meta")
        sub.setWordWrap(True)
        texts.addWidget(heading)
        texts.addWidget(sub)
        add_files = bind(QPushButton(), "Add files…")
        add_folder = bind(QPushButton(), "Add folder…")
        layout.addWidget(icon)
        layout.addLayout(texts, 1)
        layout.addWidget(add_files)
        layout.addWidget(add_folder)
        add_files.clicked.connect(self._pick_files)
        add_folder.clicked.connect(self._pick_folder)

    def _filter(self) -> str:
        patterns = " ".join(f"*.{ext}" for ext in self._extensions)
        return tr("Audio files ({patterns});;All files (*)", patterns=patterns)

    def _emit(self, paths: List[Path]) -> None:
        files = collect_audio_files(paths, self._extensions)
        if files:
            self.pathsDropped.emit(files)

    def _pick_files(self) -> None:
        names, _ = QFileDialog.getOpenFileNames(self, tr("Add audio files"), str(Path.home()), self._filter())
        self._emit([Path(name) for name in names])

    def _pick_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, tr("Add a folder"), str(Path.home()))
        if folder:
            self._emit([Path(folder)])

    # ---- drag and drop ---------------------------------------------------
    def dragEnterEvent(self, event) -> None:  # noqa: N802 (Qt naming)
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            set_prop(self, "active", True)
        else:
            event.ignore()

    def dragMoveEvent(self, event) -> None:  # noqa: N802
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dragLeaveEvent(self, event) -> None:  # noqa: N802
        set_prop(self, "active", False)
        super().dragLeaveEvent(event)

    def dropEvent(self, event) -> None:  # noqa: N802
        set_prop(self, "active", False)
        paths = [Path(url.toLocalFile()) for url in event.mimeData().urls() if url.isLocalFile()]
        event.acceptProposedAction()
        self._emit(paths)


class ScrollBody(QWidget):
    """Transparent vertical container used inside QScrollArea."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("ScrollBody")
        self.layout_ = QVBoxLayout(self)
        self.layout_.setContentsMargins(2, 2, 8, 2)
        self.layout_.setSpacing(12)
        self.layout_.addStretch(1)

    def insert(self, widget: QWidget) -> None:
        self.layout_.insertWidget(self.layout_.count() - 1, widget)


# ---------------------------------------------------------------- seek bar
def format_time(ms: int) -> str:
    """75000 -> '1:15' (h:mm:ss from one hour)."""
    seconds = max(0, int(ms) // 1000)
    hours, rest = divmod(seconds, 3600)
    minutes, secs = divmod(rest, 60)
    return f"{hours}:{minutes:02d}:{secs:02d}" if hours else f"{minutes}:{secs:02d}"


def format_time_precise(seconds: float) -> str:
    """75.5 -> '1:15.500' (the cut fields)."""
    millis = max(0, int(round(float(seconds) * 1000)))
    minutes, rest = divmod(millis, 60_000)
    return f"{minutes}:{rest // 1000:02d}.{rest % 1000:03d}"


def parse_time(text: str) -> Optional[float]:
    """'1:15.5', '1:15,5', '75.5', '1:02:03' -> seconds; None if it is not a time."""
    cleaned = str(text).strip().replace(",", ".")
    if not cleaned:
        return None
    try:
        parts = [float(part) for part in cleaned.split(":")]
    except ValueError:
        return None
    if len(parts) > 3 or any(part < 0 for part in parts) or any(p >= 60 for p in parts[1:]):
        return None
    seconds = 0.0
    for part in parts:
        seconds = seconds * 60.0 + part
    return seconds


def with_key(text: str, key: str) -> str:
    """Tooltip with its keyboard shortcut: 'Play / pause (Space)'."""
    return f"{text}  ({key})"


class ClickSlider(QSlider):
    """Horizontal slider that jumps straight to the clicked point (then can be dragged).
    Can show a loop region (A-B) over the groove."""

    HANDLE_MARGIN = 8

    def __init__(self, *args) -> None:
        super().__init__(*args)
        self._marks: Tuple[Optional[int], Optional[int], bool] = (None, None, False)
        self._cut: Optional[Tuple[int, int]] = None      # kept part (ms): the rest is shaded

    def set_cut(self, start: Optional[int], end: Optional[int]) -> None:
        cut = None if start is None or end is None else (int(start), int(end))
        if cut != self._cut:
            self._cut = cut
            self.update()

    def set_marks(self, start: Optional[int], end: Optional[int], active: bool) -> None:
        if (start, end, active) != self._marks:
            self._marks = (start, end, active)
            self.update()

    def x_of(self, value: int) -> float:
        """Pixel x of a slider value (inverse of ``value_at``)."""
        low, high = self.minimum(), self.maximum()
        try:
            option = QStyleOptionSlider()
            self.initStyleOption(option)
            style = self.style()
            groove = style.subControlRect(QStyle.ComplexControl.CC_Slider, option,
                                          QStyle.SubControl.SC_SliderGroove, self)
            handle = style.subControlRect(QStyle.ComplexControl.CC_Slider, option,
                                          QStyle.SubControl.SC_SliderHandle, self)
            span = int(groove.width() - handle.width())
            if span <= 0:
                raise ValueError("no span")
            pos = QStyle.sliderPositionFromValue(low, high, int(value), span, option.upsideDown)
            return float(groove.x() + pos + handle.width() / 2.0)
        except Exception:  # noqa: BLE001 - style not available (tests): plain linear mapping
            span = max(1.0, self.width() - 2.0 * self.HANDLE_MARGIN)
            ratio = 0.0 if high <= low else (int(value) - low) / float(high - low)
            return self.HANDLE_MARGIN + min(1.0, max(0.0, ratio)) * span

    def paintEvent(self, event) -> None:  # noqa: N802
        start, end, active = self._marks
        if self.maximum() > self.minimum() and self._cut is not None:
            painter = QPainter(self)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(11, 18, 32, 40))       # the parts the manual cut removes
            middle = self.height() / 2.0
            left, right = self.x_of(self._cut[0]), self.x_of(self._cut[1])
            if self._cut[0] > self.minimum():
                painter.drawRect(QRectF(0, middle - 5, max(0.0, left), 10))
            if self._cut[1] < self.maximum():
                painter.drawRect(QRectF(right, middle - 5, max(0.0, self.width() - right), 10))
            painter.end()
        if self.maximum() > self.minimum() and (start is not None or end is not None):
            painter = QPainter(self)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            middle = self.height() / 2.0
            colour = QColor(0, 180, 216, 70 if active else 34)
            if start is not None and end is not None:
                left, right = sorted((self.x_of(start), self.x_of(end)))
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(colour)
                painter.drawRoundedRect(QRectF(left, middle - 7, max(2.0, right - left), 14), 4, 4)
            painter.setPen(QColor(10, 132, 255, 220 if active else 120))
            for value in (start, end):
                if value is not None:
                    x = self.x_of(value)
                    painter.drawLine(QPointF(x, middle - 9), QPointF(x, middle + 9))
            painter.end()
        super().paintEvent(event)
    def value_at(self, x: float) -> int:
        """Slider value under pixel ``x``, with the style's real groove / handle geometry."""
        low, high = self.minimum(), self.maximum()
        try:
            option = QStyleOptionSlider()
            self.initStyleOption(option)
            style = self.style()
            groove = style.subControlRect(QStyle.ComplexControl.CC_Slider, option,
                                          QStyle.SubControl.SC_SliderGroove, self)
            handle = style.subControlRect(QStyle.ComplexControl.CC_Slider, option,
                                          QStyle.SubControl.SC_SliderHandle, self)
            span = int(groove.width() - handle.width())
            pos = int(round(x - groove.x() - handle.width() / 2.0))
            if span <= 0:
                raise ValueError("no span")
            return int(QStyle.sliderValueFromPosition(low, high, min(max(pos, 0), span), span, option.upsideDown))
        except Exception:  # noqa: BLE001 - style not available (tests): plain linear mapping
            span = max(1.0, self.width() - 2.0 * self.HANDLE_MARGIN)
            ratio = min(1.0, max(0.0, (x - self.HANDLE_MARGIN) / span))
            return int(round(low + ratio * (high - low)))

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton and self.maximum() > self.minimum():
            self.setValue(self.value_at(float(event.position().x())))
        super().mousePressEvent(event)        # the handle is now under the cursor: dragging starts


class SeekBar(QWidget):
    """Play / pause + clickable, draggable timeline + A / B / loop + 'elapsed / total'.
    Always left to right (time flows that way, even in Arabic)."""

    seekRequested = Signal(int)          # ms on the track's timeline
    playPauseClicked = Signal()
    loopChanged = Signal()               # A, B or the loop switch changed
    homeRequested = Signal()             # ⏮: back to A (or to the start without a loop)
    MIN_LOOP_MS = 250

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setLayoutDirection(Qt.LayoutDirection.LeftToRight)   # time flows left to right, even in Arabic
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        self.button = QPushButton("▶")
        self.button.setObjectName("TransportButton")
        self.button.setFixedSize(QSize(30, 26))
        bind_call(self.button, lambda text: self.button.setToolTip(with_key(text, tr("Space"))), N_("Play / pause"))
        self.slider = ClickSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(0, 0)
        self.slider.setSingleStep(1000)
        self.slider.setPageStep(10_000)
        bind_tip(self.slider, "Click or drag to go to any moment of the track")
        self.time = QLabel("0:00 / 0:00")
        self.time.setObjectName("TimeLabel")
        self.time.setMinimumWidth(86)
        self.time.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.home_button = QPushButton("⏮")
        self.a_button = QPushButton("A")
        self.b_button = QPushButton("B")
        self.loop_button = QPushButton("⟲")
        self.loop_clear = QPushButton("✕")
        self.loop_button.setCheckable(True)
        for widget, tip in ((self.a_button, N_("Loop start (A): set it at the current moment")),
                            (self.b_button, N_("Loop end (B): set it at the current moment")),
                            (self.loop_button, N_("Loop between A and B (kept when you switch Original / Master "
                                                  "or the mode)")),
                            (self.loop_clear, N_("Clear the loop"))):
            widget.setObjectName("LoopButton")
            widget.setFixedSize(QSize(28, 24))
            bind_tip(widget, tip)
        self.home_button.setObjectName("LoopButton")
        self.home_button.setFixedSize(QSize(28, 24))
        bind_call(self.home_button, lambda text: self.home_button.setToolTip(with_key(text, "R")),
                  N_("Back to A (or to the start when there is no loop)"))
        layout.addWidget(self.button)
        layout.addWidget(self.slider, 1)
        for widget in (self.home_button, self.a_button, self.b_button, self.loop_button, self.loop_clear):
            layout.addWidget(widget)
        layout.addWidget(self.time)
        self._loop_a: Optional[int] = None
        self._loop_b: Optional[int] = None
        self._duration = 0
        self._dragging = False
        self._updating = False
        self._last_sent: Optional[int] = None
        self.button.clicked.connect(self.playPauseClicked.emit)
        self.slider.sliderPressed.connect(self._on_pressed)
        self.slider.sliderMoved.connect(self._show_time)
        self.slider.sliderReleased.connect(self._on_released)
        self.slider.valueChanged.connect(self._on_value)
        self.a_button.clicked.connect(lambda: self.set_loop_point("a"))
        self.b_button.clicked.connect(lambda: self.set_loop_point("b"))
        self.loop_button.toggled.connect(self._on_loop_toggled)
        self.loop_clear.clicked.connect(self.clear_loop)
        self.home_button.clicked.connect(self.homeRequested.emit)
        self._update_loop_ui()

    def value(self) -> int:
        return int(self.slider.value())

    def set_duration(self, ms: int) -> None:
        self._duration = max(0, int(ms))
        self._updating = True
        self.slider.setRange(0, self._duration)
        self._updating = False
        if self._duration and any(p is not None and p > self._duration for p in (self._loop_a, self._loop_b)):
            self.clear_loop()                       # points beyond a shorter (re-trimmed) track
        self._show_time(self.slider.value())

    # ---- loop A-B ------------------------------------------------------------------
    def loop_points(self) -> Tuple[Optional[int], Optional[int]]:
        return self._loop_a, self._loop_b

    def loop_range(self) -> Optional[Tuple[int, int]]:
        """(start, end) in ms when the loop is on and valid, else None."""
        if not self.loop_button.isChecked() or self._loop_a is None or self._loop_b is None:
            return None
        start, end = sorted((self._loop_a, self._loop_b))
        return (start, end) if end - start >= self.MIN_LOOP_MS else None

    def set_loop_point(self, which: str, ms: Optional[int] = None) -> None:
        value = self.value() if ms is None else int(ms)
        if which == "a":
            self._loop_a = value
        else:
            self._loop_b = value
        if self._loop_a is not None and self._loop_b is not None:
            if abs(self._loop_b - self._loop_a) < self.MIN_LOOP_MS:
                if which == "a":                    # too short: the other point goes
                    self._loop_b = None
                else:
                    self._loop_a = None
            else:
                self.loop_button.blockSignals(True)
                self.loop_button.setChecked(True)   # both points set: the loop starts
                self.loop_button.blockSignals(False)
        self._update_loop_ui()
        self.loopChanged.emit()

    def set_loop_state(self, start: Optional[int], end: Optional[int], enabled: bool) -> None:
        """Restore A / B and the loop switch (projects) without side effects."""
        self._loop_a, self._loop_b = start, end
        self.loop_button.blockSignals(True)
        self.loop_button.setChecked(bool(enabled) and start is not None and end is not None)
        self.loop_button.blockSignals(False)
        self._update_loop_ui()
        self.loopChanged.emit()

    def set_cut(self, start_ms: Optional[int], end_ms: Optional[int]) -> None:
        """Shade what the manual cut removes."""
        self.slider.set_cut(start_ms, end_ms)

    def clear_loop(self) -> None:
        self._loop_a = self._loop_b = None
        self.loop_button.blockSignals(True)
        self.loop_button.setChecked(False)
        self.loop_button.blockSignals(False)
        self._update_loop_ui()
        self.loopChanged.emit()

    def _on_loop_toggled(self, _on: bool) -> None:
        self._update_loop_ui()
        self.loopChanged.emit()

    def _update_loop_ui(self) -> None:
        both = self._loop_a is not None and self._loop_b is not None
        self.loop_button.setEnabled(both)
        if not both and self.loop_button.isChecked():
            self.loop_button.blockSignals(True)
            self.loop_button.setChecked(False)
            self.loop_button.blockSignals(False)
        self.loop_clear.setEnabled(self._loop_a is not None or self._loop_b is not None)
        for button, point in ((self.a_button, self._loop_a), (self.b_button, self._loop_b)):
            set_prop(button, "set", point is not None)
        self.slider.set_marks(self._loop_a, self._loop_b, self.loop_range() is not None)
        span = self.loop_range()
        self.loop_button.setToolTip(
            with_key(tr("Loop between A and B (kept when you switch Original / Master or the mode)"), "L")
            + (f"\n{format_time(span[0])} → {format_time(span[1])}" if span else ""))

    def set_position(self, ms: int) -> None:
        """From the player: ignored while the user drags the handle."""
        if self._dragging:
            return
        self._updating = True
        self.slider.setValue(min(max(0, int(ms)), self._duration))
        self._updating = False
        self._last_sent = None
        self._show_time(self.slider.value())

    def set_playing(self, playing: bool) -> None:
        self.button.setText("❚❚" if playing else "▶")

    # ---- internals -------------------------------------------------------------
    def _show_time(self, ms: int) -> None:
        self.time.setText(f"{format_time(ms)} / {format_time(self._duration)}")

    def _send(self, ms: int) -> None:
        if ms != self._last_sent:
            self._last_sent = ms
            self.seekRequested.emit(int(ms))

    def _on_pressed(self) -> None:
        self._dragging = True

    def _on_released(self) -> None:
        self._dragging = False
        self._send(self.slider.value())

    def _on_value(self, value: int) -> None:
        self._show_time(value)
        if not self._updating and not self._dragging:      # click on the groove, keyboard
            self._send(value)
"""One card per track in the Mastering tab.

v2: the card shows a *preview* (nothing written to the output folder) with its
loudness / peak / limiter / stereo-phase readouts, Original / Master / Gain
Match / Mono listening, the A-B loop on the timeline, the modes already
rendered for this track (one click to switch back) and its own Export button.

v2.1: a tick box (which tracks the global buttons process), the original can be
heard as soon as the track is added (Master / Gain Match / Export wait for the
rendering), and a manual start / end cut that never touches the source file.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ..engine.analysis import TrackAnalysis, describe_key, key_short_names
from ..engine.cut import MIN_LENGTH_S, normalise_cut
from ..engine.delivery import default_title
from ..engine.pipeline import TrackResult
from ..engine.presets import MasterSettings
from ..engine.stereo import StereoReport
from ..i18n import group_thousands, key_name, tr_engine
from .translate import N_, bind, bind_call, bind_tip, on_language_changed, tr
from .widgets import Card, Pill, Readout, SeekBar, format_time_precise, parse_time, set_prop, with_key

NO_KEY = "—"


def _num(value: Optional[float], digits: int = 1) -> str:
    if value is None or not math.isfinite(value):
        return "-inf"
    return f"{value:.{digits}f}"


def _duration(seconds: float) -> str:
    return f"{int(seconds // 60)}:{int(seconds % 60):02d}"


def _hz(rate: int) -> str:
    """44,100 (English) / 44 100 (French)..."""
    return group_thousands(rate)


def key_label(short: str) -> str:
    """'Cm' -> 'C minor  ·  5A' / 'Do mineur  ·  5A'."""
    return f"{key_name(short)}  ·  {describe_key(short)[1]}" if short else ""


@dataclass(frozen=True)
class ExportState:
    """Where this track stands for the current export options.
    kind: 'none' | 'done' | 'stale' | 'failed' | 'skipped'."""
    kind: str = "none"
    path: Optional[Path] = None
    error: str = ""


def _signed(value: float) -> str:
    return f"{value:+.2f}".replace("-", "−")


def stereo_summary(report: Optional[StereoReport]) -> Tuple[str, str, str, str]:
    """(value, hint, level, explanation) for a stereo / phase report; level '' / 'caution' / 'risk'."""
    if report is None:
        return "—", tr("mono file: nothing can cancel"), "", tr("Mono source: no phase risk.")
    level = "" if report.level == "ok" else report.level
    value = ("⚠ " if level else "") + _signed(report.correlation)
    hint = tr("bass {bass} · mono {mono} dB", bass=_signed(report.bass_correlation),
              mono=f"{report.mono_loss_db:+.1f}".replace("-", "−"))
    lines = [tr("Correlation {value} (+1 = mono, 0 = very wide, below 0 = out of phase). "
                "Width (side / mid) {width} dB.", value=_signed(report.correlation),
                width=f"{report.width_db:.1f}")]
    issues = report.issues
    if "bass" in issues:
        lines.append(tr("⚠ The bass is not centred (correlation {value} below 150 Hz): it can thin out or "
                        "vanish in mono (club systems, phones, vinyl).", value=_signed(report.bass_correlation)))
    if "phase" in issues:
        lines.append(tr("⚠ Some passages are out of phase (worst moment {value}): they cancel when left and "
                        "right are summed.", value=_signed(report.worst_correlation)))
    if "mono" in issues:
        lines.append(tr("⚠ The track loses {db} dB when summed to mono: very wide or out-of-phase content.",
                        db=f"{abs(report.mono_loss_db):.1f}"))
    if not issues:
        lines.append(tr("Mono-compatible: nothing cancels when left and right are summed."))
    lines.append(tr("Check it by ear with the Mono button."))
    return value, hint, level, "\n".join(lines)


class TrackCard(Card):
    playRequested = Signal(str, str)           # key, 'original' | 'mastered'
    gainMatchToggled = Signal(str, bool)
    analysisRequested = Signal(str)
    revealRequested = Signal(str)
    removeRequested = Signal(str)
    metaChanged = Signal(str)                  # title, BPM or key edited
    seekRequested = Signal(str, int)           # key, timeline ms (click / drag on the seek bar)
    pauseToggled = Signal(str)                 # key (play / pause button of the seek bar)
    monoToggled = Signal(str, bool)
    loopChanged = Signal(str)                  # A, B or the loop switch changed
    exportRequested = Signal(str)
    versionRequested = Signal(str, int)        # key, index of a rendered mode (see set_versions)
    selectionChanged = Signal(str, bool)       # tick box: processed by the global buttons
    cutChanged = Signal(str)                   # manual start / end changed
    homeRequested = Signal(str)                # ⏮: back to A / to the start
    activated = Signal(str)                    # any use of the card (keyboard shortcuts follow it)
    modeChanged = Signal(str)                  # per-track preset / profile selector changed

    def __init__(self, key: str, source: Path, index: int, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.key, self.source = key, source
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 16)
        root.setSpacing(12)

        # header -------------------------------------------------------------
        head = QHBoxLayout()
        head.setSpacing(12)
        self.select_box = QCheckBox()
        self.select_box.setChecked(True)
        bind_tip(self.select_box, "Ticked tracks are the ones Prepare the previews and Export all work on.")
        self.badge = QLabel(f"{index:02d}")
        self.badge.setObjectName("Badge")
        self.badge.setFixedSize(42, 42)
        self.badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        titles = QVBoxLayout()
        titles.setSpacing(1)
        self.title = QLabel(source.name)
        self.title.setObjectName("CardTitle")
        self.title.setToolTip(str(source))
        self.title.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.meta = QLabel(str(source.parent))
        self.meta.setObjectName("Meta")
        titles.addWidget(self.title)
        titles.addWidget(self.meta)
        self.mode_combo = QComboBox()
        self.mode_combo.setObjectName("ModeCombo")
        self.mode_combo.setMinimumWidth(150)
        bind_tip(self.mode_combo, "Mode for this track: follow the left panel, or a preset / profile just "
                                  "for it. Lets you queue several tracks with different modes at once.")
        self._mode_token = ""
        self._filling_mode = False
        self.pill = Pill("", "idle")
        self.remove_button = QPushButton("✕")
        self.remove_button.setObjectName("IconButton")
        bind_tip(self.remove_button, "Remove from the list")
        head.addWidget(self.select_box)
        head.addWidget(self.badge)
        head.addLayout(titles, 1)
        head.addWidget(self.mode_combo, 0, Qt.AlignmentFlag.AlignVCenter)
        head.addWidget(self.pill, 0, Qt.AlignmentFlag.AlignTop)
        head.addWidget(self.remove_button, 0, Qt.AlignmentFlag.AlignTop)
        root.addLayout(head)

        # title / BPM / key (detected in the background, editable) -------------
        self.analysis: Optional[TrackAnalysis] = None
        self.meta_row = QWidget()
        meta = QHBoxLayout(self.meta_row)
        meta.setContentsMargins(0, 0, 0, 0)
        meta.setSpacing(8)
        self.title_edit = QLineEdit()
        self.title_edit.setPlaceholderText(default_title(source))
        self.title_edit.setText(default_title(source))
        bind_tip(self.title_edit, "Track title: used for the tags and the exported file names.")
        self.bpm_spin = QSpinBox()
        self.bpm_spin.setRange(0, 300)
        self.bpm_spin.setSpecialValueText(NO_KEY)
        self.bpm_spin.setSuffix(" BPM")
        bind_tip(self.bpm_spin, "Tempo. 0 = unknown. Detection can land on half or double "
                                "the tempo on some styles: use ÷2 / ×2.")
        self.half_button = QPushButton("÷2")
        self.double_button = QPushButton("×2")
        for button, tip in ((self.half_button, N_("Half tempo")), (self.double_button, N_("Double tempo"))):
            button.setObjectName("MiniButton")
            bind_tip(button, tip)
            button.setFixedWidth(34)
        self.key_combo = QComboBox()
        self.key_combo.addItem(NO_KEY, "")
        for short in key_short_names():
            self.key_combo.addItem(key_label(short), short)
        bind_tip(self.key_combo, "Musical key (Camelot code for harmonic mixing).")
        self.reset_meta = QPushButton("↺")
        self.reset_meta.setObjectName("MiniButton")
        self.reset_meta.setFixedWidth(30)
        bind_tip(self.reset_meta, "Back to the detected BPM and key")
        self.reset_meta.setVisible(False)
        self._analysis_error: Optional[str] = None
        self.analysis_status = QLabel(tr("Detecting BPM and key…"))
        self.analysis_status.setObjectName("Meta")
        meta.addWidget(self.title_edit, 3)
        meta.addWidget(self.bpm_spin)
        meta.addWidget(self.half_button)
        meta.addWidget(self.double_button)
        meta.addWidget(self.key_combo, 2)
        meta.addWidget(self.reset_meta)
        root.addWidget(self.meta_row)
        root.addWidget(self.analysis_status)

        # progress -----------------------------------------------------------
        self.progress_box = QWidget()
        progress_layout = QVBoxLayout(self.progress_box)
        progress_layout.setContentsMargins(0, 0, 0, 0)
        progress_layout.setSpacing(4)
        self.progress = QProgressBar()
        self.progress.setRange(0, 1000)
        self.progress.setTextVisible(False)
        self.progress_message = QLabel("")
        self.progress_message.setObjectName("Meta")
        progress_layout.addWidget(self.progress)
        progress_layout.addWidget(self.progress_message)
        root.addWidget(self.progress_box)

        # readouts -----------------------------------------------------------
        self.readouts = QWidget()
        grid = QGridLayout(self.readouts)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(10)
        self.r_original = Readout(N_("Original"), "LUFS")
        self.r_master = Readout(N_("Mastered"), "LUFS", accent=True)
        self.r_peak = Readout(N_("True peak"), "dBTP")
        self.r_limiter = Readout(N_("Limiter"), "dB")
        self.r_stereo = Readout(N_("Stereo / phase"), "")
        for column, readout in enumerate((self.r_original, self.r_master, self.r_peak, self.r_limiter,
                                          self.r_stereo)):
            grid.addWidget(readout, 0, column)
        root.addWidget(self.readouts)

        # actions ------------------------------------------------------------
        self.actions = QWidget()
        actions = QHBoxLayout(self.actions)
        actions.setContentsMargins(0, 0, 0, 0)
        actions.setSpacing(8)
        self.play_original = QPushButton()
        self.play_master = QPushButton()
        for button in (self.play_original, self.play_master):
            button.setCheckable(True)
        self._playing = ""
        self.gain_match = bind(QCheckBox(), "⚖️ Gain Match (A/B)")
        bind_tip(self.gain_match,
                 "Plays both versions at the same loudness (LUFS) so you judge the processing, "
                 "not the volume. Listening only: the exported file keeps its full level.")
        self.mono_button = QPushButton(tr("Mono"))
        self.mono_button.setObjectName("ToggleChip")
        self.mono_button.setCheckable(True)
        bind(self.mono_button, "Mono")
        bind_call(self.mono_button, lambda text: self.mono_button.setToolTip(with_key(text, "M")),
                  N_("Listen in mono (left + right summed), like a phone or a club system: "
                     "reveals what cancels. Listening only, the export stays stereo."))
        self.analysis_button = bind(QPushButton(), "Analysis…")
        actions.addWidget(self.play_original)
        actions.addWidget(self.play_master)
        actions.addWidget(self.gain_match)
        actions.addWidget(self.mono_button)
        actions.addStretch(1)
        actions.addWidget(self.analysis_button)
        root.addWidget(self.actions)

        self.seek = SeekBar()                   # timeline of the preview (Original / Master) + loop A-B
        self.last_which = "original"            # version the seek bar starts when nothing plays
        root.addWidget(self.seek)

        # manual cut (start / end), non-destructive ----------------------------------
        self.cut_row = QWidget()
        cut = QHBoxLayout(self.cut_row)
        cut.setContentsMargins(0, 0, 0, 0)
        cut.setSpacing(6)
        self.cut_label = bind(QLabel(), "✂ Cut")
        self.cut_label.setObjectName("Meta")
        self.cut_start, self.cut_end = QLineEdit(), QLineEdit()
        for edit, tip in ((self.cut_start, N_("Start of the part kept (m:ss.mmm). The source file is never modified.")),
                          (self.cut_end, N_("End of the part kept (m:ss.mmm). The source file is never modified."))):
            edit.setFixedWidth(92)
            edit.setObjectName("TimeEdit")
            bind_tip(edit, tip)
        self.cut_from_loop = bind(QPushButton(), "✂ Trim to A–B")
        bind_tip(self.cut_from_loop, "Keep only the part between the A and B markers.")
        self.cut_reset = bind(QPushButton(), "Reset the cut")
        bind_tip(self.cut_reset, "Keep the whole track again.")
        for button in (self.cut_from_loop, self.cut_reset):
            button.setObjectName("MiniButton")
        self.cut_info = QLabel("")
        self.cut_info.setObjectName("Meta")
        cut.addWidget(self.cut_label)
        cut.addWidget(self.cut_start)
        cut.addWidget(QLabel("→"))
        cut.addWidget(self.cut_end)
        cut.addWidget(self.cut_from_loop)
        cut.addWidget(self.cut_reset)
        cut.addStretch(1)
        cut.addWidget(self.cut_info)
        root.addWidget(self.cut_row)
        self._duration_ms = 0
        self._cut: Optional[Tuple[float, float]] = None
        self._rendered = False
        self._original_ok = True
        self._original_error = ""
        self._played = False                    # nothing heard yet: once rendered, the bar starts the master

        # rendered modes + export ------------------------------------------------
        self.delivery = QWidget()
        delivery = QHBoxLayout(self.delivery)
        delivery.setContentsMargins(0, 0, 0, 0)
        delivery.setSpacing(6)
        self.versions_label = bind(QLabel(), "Rendered modes:")
        self.versions_label.setObjectName("Meta")
        bind_tip(self.versions_label, "Modes already rendered for this track (kept for this session): "
                                      "click one to switch back instantly.")
        self.versions_box = QHBoxLayout()
        self.versions_box.setSpacing(4)
        self._version_buttons: List[QPushButton] = []
        self.export_status = QLabel("")
        self.export_status.setObjectName("ExportStatus")
        self.export_status.setWordWrap(True)
        self.reveal_button = QPushButton(tr("Show file"))
        self.export_button = QPushButton()
        self.export_button.setObjectName("CardExport")
        bind_tip(self.export_button, "Write this track's files (format, tags, cover, clip) to the output folder.")
        delivery.addWidget(self.versions_label)
        delivery.addLayout(self.versions_box)
        delivery.addStretch(1)
        delivery.addWidget(self.export_status, 2)
        delivery.addWidget(self.reveal_button)
        delivery.addWidget(self.export_button)
        root.addWidget(self.delivery)

        self.extras = QLabel("")                # trim / reference-match summary
        self.extras.setObjectName("Meta")
        self.extras.setWordWrap(True)
        root.addWidget(self.extras)

        self.note = QLabel("")
        self.note.setObjectName("Note")
        self.note.setWordWrap(True)
        self.note.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        root.addWidget(self.note)

        self.play_original.clicked.connect(lambda: self.playRequested.emit(self.key, "original"))
        self.play_master.clicked.connect(lambda: self.playRequested.emit(self.key, "mastered"))
        for widget in (self.play_original, self.play_master):
            bind_call(widget, lambda text, w=widget: w.setToolTip(with_key(text, "Tab")),
                      N_("Original or Master: switching keeps the same moment"))
        self.gain_match.toggled.connect(lambda on: self.gainMatchToggled.emit(self.key, on))
        self.analysis_button.clicked.connect(lambda: self.analysisRequested.emit(self.key))
        self.reveal_button.clicked.connect(lambda: self.revealRequested.emit(self.key))
        self.remove_button.clicked.connect(lambda: self.removeRequested.emit(self.key))
        self.seek.seekRequested.connect(lambda ms: self.seekRequested.emit(self.key, ms))
        self.seek.playPauseClicked.connect(lambda: self.pauseToggled.emit(self.key))
        self.seek.loopChanged.connect(lambda: self.loopChanged.emit(self.key))
        self.mono_button.toggled.connect(lambda on: self.monoToggled.emit(self.key, on))
        self.export_button.clicked.connect(lambda: self.exportRequested.emit(self.key))
        self.select_box.toggled.connect(lambda on: self.selectionChanged.emit(self.key, on))
        self.mode_combo.currentIndexChanged.connect(self._on_mode)
        self.seek.homeRequested.connect(lambda: self.homeRequested.emit(self.key))
        self.seek.loopChanged.connect(self._update_cut_ui)
        self.cut_start.editingFinished.connect(self._cut_edited)
        self.cut_end.editingFinished.connect(self._cut_edited)
        self.cut_from_loop.clicked.connect(self.cut_to_loop)
        self.cut_reset.clicked.connect(lambda: self.set_cut(None))
        for signal in (self.playRequested, self.seekRequested, self.loopChanged, self.homeRequested,
                       self.monoToggled, self.cutChanged, self.pauseToggled):
            signal.connect(lambda *_args: self.activated.emit(self.key))
        self._busy = False
        self._export_allowed = True
        self.title_edit.editingFinished.connect(self._title_done)
        self.bpm_spin.valueChanged.connect(self._meta_edited)
        self.key_combo.currentIndexChanged.connect(self._meta_edited)
        self.half_button.clicked.connect(lambda: self._scale_bpm(0.5))
        self.double_button.clicked.connect(lambda: self._scale_bpm(2.0))
        self.reset_meta.clicked.connect(self._reset_to_detected)
        self._last_title = self.title_edit.text()
        self._state_call = (self.set_waiting, ())
        on_language_changed(self._retranslate, self)
        self.set_play_state("")
        self._update_cut_ui()
        self.set_waiting()

    def _retranslate(self, _code: str = "") -> None:
        """Language switched: key names, detection status and the current state's texts."""
        for index in range(1, self.key_combo.count()):
            self.key_combo.setItemText(index, key_label(self.key_combo.itemData(index)))
        if self.analysis is not None:
            self._update_status()
        elif self._analysis_error is not None:
            self.set_analysis(None, self._analysis_error)
        else:
            self.analysis_status.setText(tr("Detecting BPM and key…"))
        self.set_play_state(self._playing)
        method, args = self._state_call
        method(*args)

    # ---- title / BPM / key -------------------------------------------------
    def track_title(self) -> str:
        return self.title_edit.text().strip() or default_title(self.source)

    def bpm(self) -> Optional[int]:
        return self.bpm_spin.value() or None

    def key_name(self) -> str:
        return self.key_combo.currentData() or ""

    def beat_offset(self) -> Optional[float]:
        """Detected first-beat time, still valid at the detected tempo, half or double."""
        detected = self.analysis.bpm_int if self.analysis else None
        bpm = self.bpm()
        if not detected or not bpm or self.analysis.beat_offset_s is None:
            return None
        if bpm in (detected, 2 * detected) or abs(bpm * 2 - detected) <= 1:
            return self.analysis.beat_offset_s
        return None

    def set_analysis(self, analysis: Optional[TrackAnalysis], error: str = "") -> None:
        """Detection result: fills BPM / key unless the user already typed something."""
        self.analysis = analysis
        if analysis is None:
            self._analysis_error = error
            self.analysis_status.setText(tr("BPM / key detection failed: {error}", error=tr_engine(error))
                                         if error else tr("BPM / key not detected"))
            return
        self._analysis_error = None
        untouched = self.bpm_spin.value() == 0 and not self.key_name()
        if untouched:
            self._set_meta_silently(analysis.bpm_int or 0, analysis.key)
        self._update_status()
        if untouched:
            self.metaChanged.emit(self.key)

    def _set_meta_silently(self, bpm: int, key: str) -> None:
        for widget in (self.bpm_spin, self.key_combo):
            widget.blockSignals(True)
        self.bpm_spin.setValue(int(bpm))
        index = self.key_combo.findData(key)
        self.key_combo.setCurrentIndex(index if index >= 0 else 0)
        for widget in (self.bpm_spin, self.key_combo):
            widget.blockSignals(False)

    def _update_status(self) -> None:
        a = self.analysis
        if a is None:
            return
        parts = []
        if a.bpm_int:
            parts.append(f"{a.bpm_int} BPM")
        if a.key:
            parts.append(f"{key_name(a.key)} ({a.camelot})")
        detected = " · ".join(parts) if parts else tr("no steady beat or key")
        self.analysis_status.setText(tr("Detected: {what}", what=detected))
        self.analysis_status.setToolTip(tr(
            "Tempo confidence {bpm}% · key confidence {key}%. Both stay editable.",
            bpm=round(a.bpm_confidence * 100), key=round(a.key_confidence * 100)))
        edited = (self.bpm() or None) != a.bpm_int or self.key_name() != a.key
        self.reset_meta.setVisible(edited and bool(parts))

    def _scale_bpm(self, factor: float) -> None:
        if self.bpm_spin.value():
            self.bpm_spin.setValue(int(round(self.bpm_spin.value() * factor)))

    def _reset_to_detected(self) -> None:
        if self.analysis is not None:
            self._set_meta_silently(self.analysis.bpm_int or 0, self.analysis.key)
            self._meta_edited()

    def _title_done(self) -> None:
        if self.title_edit.text().strip() != self._last_title:
            self._last_title = self.title_edit.text().strip()
            self.metaChanged.emit(self.key)

    def _meta_edited(self, *_args) -> None:
        self._update_status()
        self.metaChanged.emit(self.key)

    # ---- selection ---------------------------------------------------------------
    def is_selected(self) -> bool:
        return self.select_box.isChecked()

    def set_selected(self, on: bool) -> None:
        self.select_box.setChecked(bool(on))

    # ---- per-track mode ----------------------------------------------------------
    def set_mode_items(self, items: Sequence[Tuple[str, str]]) -> None:
        """(token, label) list; keeps the current token selected if it still exists."""
        self._filling_mode = True
        current = self._mode_token
        self.mode_combo.clear()
        for token, label in items:
            self.mode_combo.addItem(label, token)
        index = self.mode_combo.findData(current)
        self.mode_combo.setCurrentIndex(index if index >= 0 else 0)
        self._mode_token = self.mode_combo.currentData() or ""
        self._filling_mode = False

    def mode_token(self) -> str:
        return self._mode_token

    def set_mode_token(self, token: str, emit: bool = True) -> None:
        index = self.mode_combo.findData(token or "")
        if index < 0:
            return
        self._mode_token = token or ""
        self._filling_mode = not emit
        self.mode_combo.setCurrentIndex(index)
        self._filling_mode = False

    def _on_mode(self, _index: int) -> None:
        if self._filling_mode:
            return
        self._mode_token = self.mode_combo.currentData() or ""
        self.modeChanged.emit(self.key)

    # ---- manual cut ----------------------------------------------------------------
    def set_duration_ms(self, ms: int) -> None:
        """Length of the original (the timeline): known as soon as the track is decoded."""
        ms = max(0, int(ms))
        if ms and ms != self._duration_ms:
            self._duration_ms = ms
            self.seek.set_duration(ms)
            self._update_cut_ui()

    def duration_ms(self) -> int:
        return self._duration_ms

    def cut(self) -> Optional[Tuple[float, float]]:
        """(start s, end s) of the part kept, or None for the whole track."""
        if self._cut is None:
            return None
        return normalise_cut(self._cut, self._duration_ms / 1000.0) if self._duration_ms else self._cut

    def set_cut(self, cut: Optional[Tuple[float, float]], emit: bool = True) -> None:
        cleaned = None if cut is None else (max(0.0, float(cut[0])), float(cut[1]))
        if cleaned is not None and cleaned[1] - cleaned[0] < MIN_LENGTH_S:
            cleaned = self._cut                          # too short: keep what was there
        changed = cleaned != self._cut
        self._cut = cleaned
        self._update_cut_ui()
        if changed and emit:
            self.cutChanged.emit(self.key)

    def cut_to_loop(self) -> None:
        start, end = self.seek.loop_points()
        if start is not None and end is not None:
            low, high = sorted((start, end))
            self.set_cut((low / 1000.0, high / 1000.0))

    def _cut_edited(self) -> None:
        start, end = parse_time(self.cut_start.text()), parse_time(self.cut_end.text())
        total = self._duration_ms / 1000.0
        if start is None or end is None or (total and start >= total):
            self._update_cut_ui()                        # not a time: show the current values again
            return
        if total:
            end = min(end, total)
        if end - start < MIN_LENGTH_S:
            self._update_cut_ui()
            return
        self.set_cut(None if start <= 0 and (not total or end >= total) else (start, end))

    def _update_cut_ui(self) -> None:
        total = self._duration_ms / 1000.0
        cut = self.cut()
        start, end = cut if cut is not None else (0.0, total)
        self.cut_start.setText(format_time_precise(start))
        self.cut_end.setText(format_time_precise(end) if total or cut else "")
        a, b = self.seek.loop_points()
        self.cut_from_loop.setEnabled(a is not None and b is not None and abs(b - a) >= MIN_LENGTH_S * 1000)
        self.cut_reset.setEnabled(cut is not None)
        if cut is not None:
            self.cut_info.setText(tr("{length} kept", length=format_time_precise(end - start)))
            self.seek.set_cut(int(start * 1000), int(end * 1000))
        else:
            self.cut_info.setText(tr("whole track") if total else "")
            self.seek.set_cut(None, None)
        set_prop(self.cut_row, "active", cut is not None)

    # ---- states ----------------------------------------------------------
    def set_index(self, index: int) -> None:
        self.badge.setText(f"{index:02d}")

    def _show(self, progress: bool, results: bool, note: str = "", note_kind: str = "") -> None:
        """``results``: a rendered master is shown. The original can be heard either way
        (as long as it could be decoded)."""
        listen = results or self._original_ok
        self.progress_box.setVisible(progress)
        self.readouts.setVisible(results)
        self.actions.setVisible(listen)
        self.seek.setVisible(listen)
        self.cut_row.setVisible(listen)
        self.delivery.setVisible(listen)
        self.extras.setVisible(results and bool(self.extras.text()))
        self.note.setVisible(bool(note))
        self.note.setText(note)
        set_prop(self.note, "kind", note_kind)
        self._set_rendered(results)

    def _set_rendered(self, rendered: bool) -> None:
        """Master, Gain Match, Analysis and Export need the rendering; Original, the seek bar,
        Mono, the loop and the cut work from the start."""
        self._rendered = rendered
        for widget in (self.play_master, self.gain_match, self.analysis_button):
            widget.setEnabled(rendered)
        if not rendered:
            self._export_allowed = False
            self.export_button.setText(tr("⬇ Export"))
            self.export_status.setText(tr("Prepare the previews to export."))
            set_prop(self.export_status, "kind", "")
            self.reveal_button.setVisible(False)
        self.export_button.setEnabled(self._export_allowed and not self._busy)

    def set_original_state(self, available: bool, error: str = "") -> None:
        """The source could (not) be decoded for listening."""
        self._original_ok = bool(available)
        self._original_error = "" if available else (error or "?")
        if not self._rendered:
            method, args = self._state_call
            method(*args)                                 # re-show the current state with that knowledge

    @property
    def rendered(self) -> bool:
        return self._rendered

    def set_waiting(self) -> None:
        self._state_call = (self.set_waiting, ())
        self.pill.set_state("idle", tr("Ready"))
        set_prop(self, "state", "")
        if not self._original_ok:
            self._show(False, False, tr("This file cannot be played: {error}", error=tr_engine(self._original_error)), "error")
        else:
            self._show(False, False, tr("Listen to the original now; prepare the previews to hear the master and export."), "")

    def set_queued(self) -> None:
        self._state_call = (self.set_queued, ())
        self.pill.set_state("idle", tr("Queued"))
        self.progress.setValue(0)
        self.progress_message.setText(tr("Waiting in the queue"))
        set_prop(self.progress, "state", "")
        self._show(True, self.readouts.isVisible())

    def set_progress(self, fraction: float, message: str) -> None:
        self._state_call = (self.set_progress, (fraction, message))
        self.pill.set_state("run", tr("Processing"))
        set_prop(self, "state", "running")
        self.progress.setValue(int(max(0.0, min(1.0, fraction)) * 1000))
        self.progress_message.setText(tr_engine(message))
        self.progress_box.setVisible(True)

    def set_busy(self, busy: bool) -> None:
        """A batch is running: no removing, no new export until it ends."""
        self._busy = busy
        self.remove_button.setEnabled(not busy)
        self.export_button.setEnabled(self._export_allowed and not busy)
        for button in self._version_buttons:
            button.setEnabled(not busy or button.isChecked())

    def set_versions(self, labels: Sequence[Tuple[str, str]], active: int) -> None:
        """Rendered modes of this track: (label, tooltip) pairs; ``active`` = the one shown (-1: none)."""
        while self._version_buttons:
            button = self._version_buttons.pop()
            self.versions_box.removeWidget(button)
            button.setParent(None)
            button.deleteLater()
        for index, (label, tip) in enumerate(labels):
            button = QPushButton(label)
            button.setObjectName("VersionChip")
            button.setCheckable(True)
            button.setChecked(index == active)
            button.setToolTip(tip)
            button.setEnabled(not self._busy or index == active)
            button.clicked.connect(lambda _checked=False, i=index: self._on_version(i))
            self.versions_box.addWidget(button)
            self._version_buttons.append(button)
        visible = len(labels) > 1 or (len(labels) == 1 and active < 0)
        self.versions_label.setVisible(visible)
        for button in self._version_buttons:
            button.setVisible(visible)

    def _on_version(self, index: int) -> None:
        for i, button in enumerate(self._version_buttons):      # the tab confirms with set_versions
            button.setChecked(i == index)
        self.versionRequested.emit(self.key, index)

    def set_play_state(self, which: str) -> None:
        """which = 'original' | 'mastered' | '' (nothing playing on this card)."""
        if not which and self._playing:            # stopped / ended: back to the start
            self.seek.set_position(0)
            self.seek.set_playing(False)
        if which:
            self.last_which = which
            self._played = True
        self._playing = which
        for button, name, label in ((self.play_original, "original", tr("Original")),
                                    (self.play_master, "mastered", tr("Master"))):
            playing = which == name
            button.setChecked(playing)
            button.setText(("■  " if playing else "▶  ") + label)

    def show_result(self, result: TrackResult, settings: MasterSettings,
                    export: ExportState = ExportState(), revealable: Optional[Path] = None,
                    outdated: Optional[bool] = None) -> None:
        """``result`` may come from other settings (or another cut) than the current ones
        (shown while the current mode is not rendered yet): the card says so."""
        self._state_call = (self.show_result, (result, settings, export, revealable, outdated))
        self.extras.setText("")
        if result.cancelled:
            self.pill.set_state("idle", tr("Cancelled"))
            set_prop(self, "state", "")
            self._show(False, False, tr("Processing was cancelled."), "")
            return
        if result.duration_s:
            self.set_duration_ms(int(round(result.duration_s * 1000)))
        if not result.ok:
            self.pill.set_state("error", tr("Failed"))
            set_prop(self, "state", "error")
            self.meta.setText(str(self.source.parent))
            self._show(False, False, tr_engine(result.error), "error")
            return

        original, mastered, report = result.original_metrics, result.mastered_metrics, result.master_report
        if not self._played:
            self.last_which = "mastered"
        channels = tr("Stereo") if result.channels == 2 else tr("Mono")
        self.meta.setText(" · ".join((
            _duration(result.duration_s), channels, tr("{rate} Hz source", rate=_hz(result.native_sample_rate)),
            result.settings.label, tr("{recipe} recipe", recipe=result.settings.recipe),
            tr("{pct}% cleanse", pct=result.settings.intensity_pct),
        )))
        delta = (f"{mastered.lufs - original.lufs:+.1f} LU"
                 if math.isfinite(mastered.lufs) and math.isfinite(original.lufs) else "-")
        self.r_original.set(_num(original.lufs), tr("true peak {value} dBTP", value=_num(original.true_peak_db, 2)))
        self.r_master.set(_num(mastered.lufs), tr("target {target} · {delta}", target=f"{report.target_lufs:g}",
                                                   delta=delta))
        self.r_peak.set(_num(mastered.true_peak_db, 2),
                        tr("ceiling {value} dBTP", value=f"{report.target_true_peak_db:g}"))
        self.r_limiter.set(_num(report.limiter_max_reduction_db), tr("max gain reduction"))
        if "mastered" in result.stereo:
            value, hint, level, explanation = stereo_summary(result.stereo["mastered"])
            original = result.stereo.get("original")
            if original is not None:
                explanation += "\n" + tr("Original: correlation {value}, bass {bass}.",
                                         value=_signed(original.correlation), bass=_signed(original.bass_correlation))
            self.r_stereo.set(value, hint, level)
            self.r_stereo.setToolTip(explanation)
        else:
            self.r_stereo.set("-", tr("not measured"))
            self.r_stereo.setToolTip("")

        extras = []
        if result.cut is not None:
            extras.append(tr("✂ Manual cut {start} → {end} ({length})", start=format_time_precise(result.cut.start_s),
                             end=format_time_precise(result.cut.end_s), length=format_time_precise(result.cut.length_s)))
        if result.trim is not None:
            extras.append(tr("✂️ Trimmed {start} s at the start, {end} s at the end",
                             start=f"{result.trim.start_s:.2f}", end=f"{result.trim.end_s:.2f}")
                          if result.trim.changed else tr("✂️ Auto-trim: no silence to remove"))
        if result.match is not None:
            m = result.match
            text = tr("🎯 Matched to {name}", name=m.reference)
            if m.error_after_db is not None:
                text += " · " + tr("tonal distance {before} → {after} dB",
                                   before=f"{m.error_before_db:.1f}", after=f"{m.error_after_db:.1f}")
            if m.target_lufs is not None:
                text += " · " + tr("loudness {value} LUFS", value=f"{m.target_lufs:.1f}")
            extras.append(text)
        self.extras.setText("\n".join(extras))
        self.extras.setVisible(bool(extras))

        notes = [tr_engine(warning) for warning in report.warnings]
        if outdated is None:
            outdated = not result.is_current(settings)
        if outdated:
            notes.insert(0, tr("You are hearing the preview made with {mode}. Prepare the previews to hear "
                               "the current settings, or pick a rendered mode below.", mode=result.settings.label))
            self.pill.set_state("warn", tr("Other settings"))
        elif result.on_target:
            self.pill.set_state("ok", tr("On target"))
        else:
            self.pill.set_state("warn", tr("Check"))
        set_prop(self, "state", "error" if export.kind == "failed" else "")
        self._show(False, True, "\n".join(notes), "")
        self._show_export(export, outdated, revealable)

    def _show_export(self, export: ExportState, outdated: bool, revealable: Optional[Path]) -> None:
        name = export.path.name if export.path is not None else ""
        if outdated:
            text, kind = tr("The export uses the current settings: they are rendered first."), ""
            button, allowed = tr("⬇ Render + export"), True
        elif export.kind == "done":
            text, kind = tr("✓ Exported: {name}", name=name), "ok"
            button, allowed = tr("✓ Exported"), False
        elif export.kind == "stale":
            text, kind = tr("Title, BPM, key, tags or format changed: export again (no new mastering)."), "warn"
            button, allowed = tr("⬇ Export again"), True
        elif export.kind == "failed":
            text, kind = tr("Export failed: {error}", error=tr_engine(export.error)), "error"
            button, allowed = tr("⬇ Export"), True
        elif export.kind == "skipped":
            text, kind = tr("Skipped: {name} already exists (rule: skip).", name=name), "warn"
            button, allowed = tr("⏭ Skipped"), False
        else:
            text, kind = tr("Preview only: nothing written yet."), ""
            button, allowed = tr("⬇ Export"), True
        self.export_status.setText(text)
        self.export_status.setToolTip(str(export.path) if export.path is not None else "")
        set_prop(self.export_status, "kind", kind)
        self.export_button.setText(button)
        self._export_allowed = allowed
        self.export_button.setEnabled(allowed and not self._busy)
        target = export.path if export.kind == "done" else revealable
        self.reveal_button.setVisible(target is not None)
        if target is not None:
            self.reveal_button.setText(tr("Show folder") if target.is_dir() else tr("Show file"))
            self.reveal_button.setToolTip(str(target))

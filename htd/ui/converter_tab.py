"""
Converter tab: batch conversion with FFmpeg only (no mastering).
Same look as the Mastering tab: options on the left, file list on the right.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

from PySide6.QtCore import QSettings, Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from .. import config
from ..engine.converter import INPUT_EXTENSIONS, SAMPLE_RATES
from ..engine.export import DEFAULT_FORMAT, FORMATS
from ..engine.ffmpeg_tools import FfmpegInfo
from ..i18n import tr_engine
from .activity import ActivityHub
from .mastering_tab import reveal_in_file_manager
from .translate import N_, bind, bind_call, bind_tip, on_language_changed, tr, trn
from .widgets import Card, DropZone, OutputPicker, Pill, ScrollBody, SectionTitle, set_prop
from .workers import ConvertJob, ConverterWorker, start_worker


class FileRow(Card):
    """Compact row: name, status pill, progress bar, result / error."""

    removeRequested = Signal(str)
    revealRequested = Signal(str)

    def __init__(self, key: str, source: Path, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.key, self.source = key, source
        self.output: Optional[Path] = None
        self.state = "ready"
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(6)
        head = QHBoxLayout()
        title = QLabel(source.name)
        title.setObjectName("CardTitle")
        title.setToolTip(str(source))
        self.pill = Pill("", "idle")
        self.reveal_button = bind(QPushButton(), "Show file")
        self.reveal_button.setVisible(False)
        self.remove_button = QPushButton("✕")
        self.remove_button.setObjectName("IconButton")
        head.addWidget(title, 1)
        head.addWidget(self.reveal_button)
        head.addWidget(self.pill)
        head.addWidget(self.remove_button)
        layout.addLayout(head)
        self.progress = QProgressBar()
        self.progress.setRange(0, 1000)
        self.progress.setTextVisible(False)
        self.progress.setVisible(False)
        layout.addWidget(self.progress)
        self.detail = QLabel(str(source.parent))
        self.detail.setObjectName("Meta")
        self.detail.setWordWrap(True)
        self.detail.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.detail)
        self.remove_button.clicked.connect(lambda: self.removeRequested.emit(self.key))
        self.reveal_button.clicked.connect(lambda: self.revealRequested.emit(self.key))
        self._error = ""
        self._fraction = 0.0
        on_language_changed(self._retranslate, self)
        self._retranslate()

    def _retranslate(self, _code: str = "") -> None:
        """Pill and error texts in the current language (the state itself is unchanged)."""
        labels = {"ready": ("idle", N_("Ready")), "queued": ("idle", N_("Queued")),
                  "running": ("run", N_("Converting")), "done": ("ok", N_("Done")),
                  "cancelled": ("idle", N_("Cancelled")), "failed": ("error", N_("Failed"))}
        kind, text = labels.get(self.state, labels["ready"])
        self.pill.set_state(kind, tr(text))
        if self.state == "failed":
            self.detail.setText(tr_engine(self._error))

    def set_queued(self) -> None:
        self.state = "queued"
        self.pill.set_state("idle", tr("Queued"))
        self.progress.setValue(0)
        self.progress.setVisible(True)
        set_prop(self.progress, "state", "")
        set_prop(self, "state", "")

    def set_progress(self, fraction: float) -> None:
        self.state = "running"
        self.pill.set_state("run", tr("Converting"))
        self.progress.setVisible(True)
        self.progress.setValue(int(max(0.0, min(1.0, fraction)) * 1000))

    def set_done(self, output: Optional[Path], error: str) -> None:
        self.output = output
        self.state = "done" if output is not None else ("cancelled" if error == "Cancelled" else "failed")
        self._error = error
        if output is not None:
            self.pill.set_state("ok", tr("Done"))
            self.progress.setValue(1000)
            self.detail.setText(f"→ {output}")
            self.reveal_button.setVisible(True)
            set_prop(self, "state", "")
        elif error == "Cancelled":
            self.pill.set_state("idle", tr("Cancelled"))
            self.progress.setVisible(False)
        else:
            self.pill.set_state("error", tr("Failed"))
            set_prop(self.progress, "state", "error")
            set_prop(self, "state", "error")
            self.detail.setText(tr_engine(error))

    def set_busy(self, busy: bool) -> None:
        self.remove_button.setEnabled(not busy)


@dataclass
class ConvertEntry:
    source: Path
    row: FileRow
    done: bool = False


class ConverterTab(QWidget):
    TITLE = N_("Converter")

    def __init__(self, ffmpeg: Optional[FfmpegInfo], settings: QSettings,
                 parent: Optional[QWidget] = None, activity: Optional[ActivityHub] = None) -> None:
        super().__init__(parent)
        self.ffmpeg, self.store = ffmpeg, settings
        self.activity = activity
        self.entries: Dict[str, ConvertEntry] = {}
        self.worker: Optional[ConverterWorker] = None
        self.thread = None

        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(18)

        # ---- options ---------------------------------------------------------
        panel = Card(name="Panel")
        panel.setFixedWidth(330)
        side = QVBoxLayout(panel)
        side.setContentsMargins(18, 18, 18, 18)
        side.setSpacing(10)
        side.addWidget(SectionTitle(N_("Convert to")))
        self.format_combo = QComboBox()
        for index, (key, fmt) in enumerate(FORMATS.items()):
            self.format_combo.addItem(fmt.label, key)
            bind_call(self.format_combo, lambda text, i=index: self.format_combo.setItemText(i, text), fmt.label)
        side.addWidget(self.format_combo)
        side.addWidget(SectionTitle(N_("Sample rate")))
        self.rate_combo = QComboBox()
        for index, label in enumerate(SAMPLE_RATES):        # data = engine key, text = translated
            self.rate_combo.addItem(label, label)
            bind_call(self.rate_combo, lambda text, i=index: self.rate_combo.setItemText(i, text), label)
        side.addWidget(self.rate_combo)
        self.hint = QLabel()
        self.hint.setObjectName("Meta")
        self.hint.setWordWrap(True)
        side.addWidget(self.hint)
        side.addSpacing(6)
        side.addWidget(SectionTitle(N_("Output")))
        self.output = OutputPicker(config.default_output_dir() / "Converted")
        side.addWidget(self.output)
        side.addStretch(1)
        info = bind(QLabel(), "Converts with FFmpeg only - no mastering, no cleaning. Tags (title, artist...) "
                              "are copied when the format supports them.")
        info.setObjectName("Meta")
        info.setWordWrap(True)
        side.addWidget(info)
        root.addWidget(panel)

        # ---- list -----------------------------------------------------------
        main = QWidget()
        layout = QVBoxLayout(main)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        self.drop = DropZone(INPUT_EXTENSIONS, N_("Drop files or folders to convert"),
                             N_("Any audio FFmpeg can read (WAV, MP3, M4A, FLAC, OGG, OPUS, AIFF, WMA...) "
                                "and the audio track of video files."))
        layout.addWidget(self.drop)
        header = QHBoxLayout()
        self.title = QLabel(tr("No files yet"))
        self.title.setObjectName("CardTitle")
        self.clear_button = bind(QPushButton(), "Clear list")
        header.addWidget(self.title)
        header.addStretch(1)
        header.addWidget(self.clear_button)
        layout.addLayout(header)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.list_body = ScrollBody()
        scroll.setWidget(self.list_body)
        layout.addWidget(scroll, 1)
        footer = Card(name="Panel")
        footer_layout = QVBoxLayout(footer)                # progress on top, full width
        footer_layout.setContentsMargins(18, 12, 18, 12)
        footer_layout.setSpacing(8)
        self.batch_progress = QProgressBar()
        self.batch_progress.setRange(0, 1000)
        self.batch_progress.setTextVisible(False)
        self.batch_progress.setVisible(False)              # only while a conversion runs
        bottom = QHBoxLayout()
        bottom.setSpacing(14)
        self.batch_message = QLabel(tr("Add files to begin."))
        self.batch_message.setObjectName("Meta")
        self.batch_message.setWordWrap(True)
        self.pause_button = QPushButton(tr("⏸ Pause"))
        self.pause_button.setObjectName("MiniButton")
        bind_tip(self.pause_button, "Pause the queue after the current file (the work already done is kept).")
        self.cancel_button = bind(QPushButton(), "Cancel")
        self.cancel_button.setObjectName("Danger")
        self.run_button = QPushButton(tr("Convert"))
        self.run_button.setObjectName("Primary")
        bottom.addWidget(self.batch_message, 1)
        bottom.addWidget(self.pause_button)
        bottom.addWidget(self.cancel_button)
        bottom.addWidget(self.run_button)
        footer_layout.addWidget(self.batch_progress)
        footer_layout.addLayout(bottom)
        layout.addWidget(footer)
        root.addWidget(main, 1)
        self._paused = False

        self.drop.pathsDropped.connect(self.add_files)
        self.clear_button.clicked.connect(self.clear)
        self.run_button.clicked.connect(self.start)
        self.cancel_button.clicked.connect(self.cancel)
        self.pause_button.clicked.connect(self._toggle_pause)
        self.format_combo.currentIndexChanged.connect(lambda _i: self._changed())
        self.rate_combo.currentIndexChanged.connect(lambda _i: self._changed())
        self.output.changed.connect(self._changed)
        on_language_changed(lambda _code: self._refresh(), self)
        self._restore()
        self._refresh()

    # ---- settings -----------------------------------------------------------
    def fmt_key(self) -> str:
        return self.format_combo.currentData() or DEFAULT_FORMAT

    def rate_key(self) -> str:
        """Engine key of the chosen sample rate ("Keep original", "48 kHz"...)."""
        return self.rate_combo.currentData() or "Keep original"

    def _restore(self) -> None:
        index = self.format_combo.findData(self.store.value("converter/format", "mp3"))
        self.format_combo.setCurrentIndex(max(0, index))
        rate = str(self.store.value("converter/rate", "Keep original"))
        self.rate_combo.setCurrentIndex(max(0, self.rate_combo.findData(rate if rate in SAMPLE_RATES
                                                                          else "Keep original")))
        self.output.set_state(str(self.store.value("converter/next_to_source", "false")) == "true",
                              str(self.store.value("converter/folder", "")))

    def _changed(self) -> None:
        self.store.setValue("converter/format", self.fmt_key())
        self.store.setValue("converter/rate", self.rate_key())
        self.store.setValue("converter/next_to_source", "true" if self.output.folder() is None else "false")
        self.store.setValue("converter/folder", self.output.path_edit.text())
        self._refresh()

    # ---- list ---------------------------------------------------------------
    def add_files(self, paths: List[Path]) -> None:
        for path in paths:
            key = str(path.resolve())
            if key in self.entries:
                continue
            row = FileRow(key, path)
            row.removeRequested.connect(self.remove)
            row.revealRequested.connect(self._reveal)
            row.set_busy(self.worker is not None)
            self.entries[key] = ConvertEntry(path, row)
            self.list_body.insert(row)
        self._refresh()

    def remove(self, key: str) -> None:
        if self.worker is not None:
            return
        entry = self.entries.pop(key, None)
        if entry is not None:
            entry.row.setParent(None)
            entry.row.deleteLater()
        self._refresh()

    def clear(self) -> None:
        for key in list(self.entries):
            self.remove(key)

    def _reveal(self, key: str) -> None:
        entry = self.entries.get(key)
        if entry is not None and entry.row.output is not None:
            reveal_in_file_manager(entry.row.output)

    def _refresh(self) -> None:
        fmt = FORMATS[self.fmt_key()]
        if self.ffmpeg is None:
            self.hint.setText("⚠ " + tr("FFmpeg was not found: the converter needs it."))
        elif fmt.key == "mp3" and not self.ffmpeg.has_mp3:
            self.hint.setText("⚠ " + tr("This FFmpeg build has no MP3 encoder (libmp3lame)."))
        elif fmt.key == "mp3" and SAMPLE_RATES[self.rate_key()] == 96_000:
            self.hint.setText(tr("MP3 cannot store 96 kHz: FFmpeg will use 48 kHz."))
        elif fmt.key == "wav16":
            self.hint.setText(tr("Reducing to 16 bits uses triangular dither."))
        else:
            self.hint.setText("")
        count = len(self.entries)
        pending = sum(1 for entry in self.entries.values() if not entry.done)
        self.title.setText(trn("{n} file", "{n} files", count) if count else tr("No files yet"))
        if self.worker is None:
            self.run_button.setText(trn("Convert {n} file to {what}", "Convert {n} files to {what}", pending,
                                        what=tr_engine(fmt.label)) if pending else tr("Convert"))
            self.run_button.setEnabled(bool(pending) and self.ffmpeg is not None)
            self._show_cancel(False)                      # nothing running: no Cancel button
            self.clear_button.setEnabled(bool(count))

    # ---- batch --------------------------------------------------------------
    def start(self) -> None:
        if self.worker is not None or self.ffmpeg is None:
            return
        jobs = [ConvertJob(key, entry.source) for key, entry in self.entries.items() if not entry.done]
        if not jobs:
            return
        folder = self.output.folder()
        if folder is not None:
            try:
                folder.mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                QMessageBox.warning(self, config.APP_NAME, tr("Cannot use the output folder:\n{error}", error=exc))
                return
        for job in jobs:
            self.entries[job.key].row.set_queued()
        for entry in self.entries.values():
            entry.row.set_busy(True)
        self.worker = ConverterWorker(jobs, self.ffmpeg.path, self.fmt_key(),
                                      SAMPLE_RATES[self.rate_key()], folder)
        self.worker.fileProgress.connect(self._on_progress)
        self.worker.fileFinished.connect(self._on_file_finished)
        self.worker.batchProgress.connect(self._on_batch_progress)
        self.run_button.setEnabled(False)
        self.run_button.setText(tr("Converting…"))
        self._set_paused(False)
        self._show_cancel(True)
        self.clear_button.setEnabled(False)
        if self.activity is not None:
            self.activity.batch_started("converter")
        self.thread = start_worker(self.worker, self, self._on_finished)

    def _show_cancel(self, running: bool) -> None:
        """Cancel, Pause and the progress bar are only shown while a conversion runs."""
        self.cancel_button.setVisible(running)
        self.cancel_button.setEnabled(running)
        self.pause_button.setVisible(running)
        self.pause_button.setEnabled(running)
        self.batch_progress.setVisible(running)

    def _set_paused(self, paused: bool) -> None:
        self._paused = bool(paused)
        self.pause_button.setText(tr("▶ Resume") if paused else tr("⏸ Pause"))
        if self.worker is not None:
            self.worker.set_paused(paused)

    def _toggle_pause(self) -> None:
        if self.worker is not None:
            self._set_paused(not self._paused)

    def cancel(self) -> None:
        if self.worker is not None:
            self.worker.cancel()
            self.cancel_button.setEnabled(False)
            self._set_paused(False)

    def _on_progress(self, key: str, fraction: float) -> None:
        entry = self.entries.get(key)
        if entry is not None:
            entry.row.set_progress(fraction)

    def _on_batch_progress(self, fraction: float, message: str) -> None:
        self.batch_progress.setValue(int(max(0.0, min(1.0, fraction)) * 1000))
        self.batch_message.setText(message)

    def _on_file_finished(self, key: str, output: object, error: str) -> None:
        entry = self.entries.get(key)
        if entry is None:
            return
        entry.done = output is not None
        entry.row.set_done(Path(str(output)) if output is not None else None, error)

    def _on_finished(self, succeeded: int, failed: int, cancelled: bool) -> None:
        self.worker = None
        self.thread = None
        for entry in self.entries.values():
            entry.row.set_busy(False)
            if entry.row.state in ("queued", "running"):
                entry.row.set_done(None, "Cancelled")
        parts = [tr("{n} converted", n=succeeded)]
        if failed:
            parts.append(tr("{n} failed", n=failed))
        if cancelled:
            parts.append(tr("cancelled"))
        self.batch_message.setText(tr("Batch finished: {details}.", details=", ".join(parts)))
        if not cancelled:
            self.batch_progress.setValue(1000)
        self._refresh()
        if self.activity is not None:
            self.activity.batch_finished("converter", succeeded, failed, cancelled)

    def shutdown(self, timeout_ms: int = 10000) -> None:
        if self.worker is not None:
            self.worker.cancel()
        if self.thread is not None:
            self.thread.quit()
            self.thread.wait(timeout_ms)

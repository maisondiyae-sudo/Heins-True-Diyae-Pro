"""Per-track analysis window: spectrograms, tonal balance, specs and processing report."""

from __future__ import annotations

import html
import io
import math
from typing import Dict, List, Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QRadioButton,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ..engine.analysis import TrackAnalysis, describe_key
from ..engine.core import band_level_rows, build_spectrogram_figure, build_tonal_change_figure
from ..engine.pipeline import TrackResult
from ..i18n import key_name, tr_engine
from .track_card import stereo_summary
from .translate import tr
from .workers import run_task


def render_images(result: TrackResult) -> Dict[str, bytes]:
    """Render the figures to PNG bytes (runs in a worker thread, matplotlib Agg)."""
    images: Dict[str, bytes] = {}

    def _png(figure) -> bytes:
        buffer = io.BytesIO()
        figure.savefig(buffer, format="png", dpi=110, facecolor=figure.get_facecolor())
        return buffer.getvalue()

    images["log"] = _png(build_spectrogram_figure(result.spectra, "log"))
    images["linear"] = _png(build_spectrogram_figure(result.spectra, "linear"))
    tonal = build_tonal_change_figure(result.spectra, {
        "Original": result.original_metrics.lufs,
        "Cleaned": result.cleaned_metrics.lufs,
        "Mastered": result.mastered_metrics.lufs,
    })
    if tonal is not None:
        images["tonal"] = _png(tonal)
    return images


class ImageView(QLabel):
    """Shows a pixmap scaled to the available width (keeps the aspect ratio)."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._pixmap: Optional[QPixmap] = None
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMinimumHeight(120)

    def set_png(self, data: bytes) -> None:
        pixmap = QPixmap()
        pixmap.loadFromData(data, "PNG")
        self._pixmap = pixmap
        self._rescale()

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._rescale()

    def _rescale(self) -> None:
        if self._pixmap is None or self._pixmap.isNull():
            return
        width = max(200, self.width() - 4)
        scaled = self._pixmap.scaledToWidth(min(width, self._pixmap.width()),
                                            Qt.TransformationMode.SmoothTransformation)
        self.setPixmap(scaled)
        self.setMinimumHeight(scaled.height())


def _table(rows: List[Dict[str, object]]) -> QTableWidget:
    columns = list(rows[0].keys()) if rows else []
    table = QTableWidget(len(rows), len(columns))
    table.setHorizontalHeaderLabels([tr_engine(column) for column in columns])
    table.verticalHeader().setVisible(False)
    table.setAlternatingRowColors(True)
    table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
    for r, row in enumerate(rows):
        for c, column in enumerate(columns):
            value = row[column]
            item = QTableWidgetItem("" if value is None else tr_engine(value) if isinstance(value, str) else str(value))
            if c > 0:
                item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            table.setItem(r, c, item)
    table.resizeColumnsToContents()
    table.horizontalHeader().setStretchLastSection(True)
    return table


def _specs_rows(result: TrackResult) -> List[Dict[str, object]]:
    def _row(label, metrics):
        return {
            "Version": label,
            "Loudness (LUFS)": round(metrics.lufs, 1) if math.isfinite(metrics.lufs) else None,
            "True peak (dBTP)": round(metrics.true_peak_db, 2),
            "Sample peak (dBFS)": round(metrics.sample_peak_db, 2),
            "Peak-to-loudness (dB)": round(metrics.plr_db, 1) if math.isfinite(metrics.plr_db) else None,
            "Stereo correlation": None if metrics.correlation is None else round(metrics.correlation, 3),
        }
    return [_row("Original", result.original_metrics), _row("Cleaned", result.cleaned_metrics),   # _table translates
            _row("Mastered", result.mastered_metrics)]


def _music_text(bpm: Optional[int], key: str, analysis: Optional[TrackAnalysis]) -> List[str]:
    camelot = describe_key(key)[1]
    lines = [f"<b>{tr('Tempo and key')}</b><br>{bpm or '-'} BPM · {key_name(key) or '-'}"
             f"{f' (Camelot {camelot})' if camelot else ''}"]
    if analysis is not None:
        detected_key = f"{key_name(analysis.key)} ({analysis.camelot})" if analysis.key else "-"
        lines.append(tr("Detected: {bpm} BPM (confidence {bpm_conf}%), {key} (confidence {key_conf}%).",
                        bpm=analysis.bpm_int or "-", bpm_conf=round(analysis.bpm_confidence * 100),
                        key=detected_key, key_conf=round(analysis.key_confidence * 100)))
        if analysis.beat_offset_s is not None:
            lines.append(tr("Beat grid phase {value} s (social clips start on a beat).",
                            value=f"{analysis.beat_offset_s:.3f}"))
    return lines


def _delivery_text(result: TrackResult) -> List[str]:
    lines: List[str] = []
    if result.match is not None:
        m = result.match
        lines.append(f"<br><b>{tr('Reference matching')}</b><br>" + tr("Reference: {name}.", name=m.reference))
        if m.eq_max_boost_db or m.eq_max_cut_db:
            lines.append(tr("Linear-phase match EQ (replaces the recipe EQ): up to {boost} dB / {cut} dB, "
                            "broad curve smoothed over half an octave.",
                            boost=f"{m.eq_max_boost_db:+.1f}", cut=f"{m.eq_max_cut_db:+.1f}"))
        if m.error_after_db is not None:
            lines.append(tr("Average tonal-balance distance to the reference (60 Hz - 12 kHz): "
                            "{before} dB before -> {after} dB after.",
                            before=f"{m.error_before_db:.1f}", after=f"{m.error_after_db:.1f}"))
        if m.target_lufs is not None:
            lines.append(tr("Loudness target taken from the reference: {value} LUFS.", value=f"{m.target_lufs:.1f}"))
    if result.trim is not None:
        t = result.trim
        lines.append(f"<br><b>{tr('Auto-trim')}</b><br>" + (
            tr("Removed {start} s of silence at the start and {end} s at the end, "
               "with 5 ms / 20 ms anti-click fades.", start=f"{t.start_s:.2f}", end=f"{t.end_s:.2f}")
            if t.changed else tr("No silence to remove at either end.")))
    return lines


def _stereo_text(result: TrackResult) -> List[str]:
    if not result.stereo:
        return []
    lines = [f"<br><b>{tr('Stereo and phase (mono compatibility)')}</b>"]
    for which, label in (("original", tr("Original")), ("mastered", tr("Mastered"))):
        if which not in result.stereo:
            continue
        r = result.stereo[which]
        if r is None:
            lines.append(f"{label}: " + tr("mono file: nothing can cancel"))
            continue
        lines.append(tr("{version}: correlation {corr}, bass (below 150 Hz) {bass}, worst moment {worst}, "
                        "mono fold-down {mono} dB, width (side / mid) {width} dB.",
                        version=label, corr=f"{r.correlation:+.2f}", bass=f"{r.bass_correlation:+.2f}",
                        worst=f"{r.worst_correlation:+.2f}", mono=f"{r.mono_loss_db:+.1f}",
                        width=f"{r.width_db:.1f}"))
    if result.stereo.get("mastered") is not None:
        explanation = stereo_summary(result.stereo["mastered"])[3].split("\n")[1:]
        lines.extend(html.escape(line) for line in explanation)
    return lines


def _report_text(result: TrackResult, bpm: Optional[int] = None, key: str = "",
                 analysis: Optional[TrackAnalysis] = None) -> str:
    clean, master = result.clean_report, result.master_report
    lines = _music_text(bpm, key, analysis) + ["<br>"]
    lines += [f"<b>{tr('Anti-Parasite Filter')}</b><br>"
              + tr("Intensity {pct}% - band-limited to 20 Hz - 20 kHz (zero-phase).",
                   pct=f"{clean.intensity * 100:.0f}")]
    if clean.intensity > 0:
        if clean.tonal_parasites_hz:
            shown = ", ".join(f"{f / 1000:.2f} kHz" if f >= 1000 else f"{f:.0f} Hz"
                              for f in clean.tonal_parasites_hz[:16])
            extra = len(clean.tonal_parasites_hz) - 16
            if extra > 0:
                shown += " " + tr("(+{n} more)", n=extra)
            lines.append(tr("Time-locked tonal lines removed: {lines} - up to {db} dB.",
                            lines=shown, db=f"{clean.max_tonal_reduction_db:.0f}"))
        else:
            lines.append(tr("No time-locked tonal lines were detected."))
        lines.append(tr("Stationary residue: soft mask, at most {db} dB on cells at the noise floor.",
                        db=f"{clean.max_noise_reduction_db:.1f}"))
        lines.append(tr("Phase micro-variation up to +/-{deg} degrees (none below 80 Hz); time drift up to "
                        "+/-{us} microseconds (< {cents} cent). Identical on both channels.",
                        deg=f"{clean.phase_variation_deg:.1f}", us=f"{clean.time_drift_us:.0f}",
                        cents=f"{clean.drift_rate_cents:.2f}"))
    lines.append(f"<br><b>{tr('Mastering')}</b><br>"
                 + tr("{profile}: input {lufs_in} LUFS -> output {lufs_out} LUFS, true peak {peak} dBTP.",
                      profile=master.profile, lufs_in=f"{master.input_lufs:.1f}",
                      lufs_out=f"{master.output_lufs:.1f}", peak=f"{master.output_true_peak_db:.2f}"))
    lines.append(tr("Gain into the limiter {gain} dB, maximum gain reduction {gr} dB, {passes} normalisation "
                    "pass(es), processing time {seconds} s.",
                    gain=f"{master.gain_db:+.1f}", gr=f"{master.limiter_max_reduction_db:.1f}",
                    passes=master.iterations, seconds=f"{result.elapsed_s:.1f}"))
    lines.extend(_stereo_text(result))
    lines.extend(_delivery_text(result))
    lines.extend(tr_engine(note) for note in result.notes)
    return "<br>".join(lines)


class AnalysisDialog(QDialog):
    def __init__(self, result: TrackResult, parent: Optional[QWidget] = None,
                 bpm: Optional[int] = None, key: str = "",
                 analysis: Optional[TrackAnalysis] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("Analysis - {name}", name=result.source.name))
        self.resize(1120, 780)
        self._images: Dict[str, bytes] = {}
        layout = QVBoxLayout(self)
        tabs = QTabWidget()
        layout.addWidget(tabs)

        # spectrograms
        spectro = QWidget()
        spectro_layout = QVBoxLayout(spectro)
        scale_row = QHBoxLayout()
        self.log_button = QRadioButton(tr("Logarithmic"))
        self.linear_button = QRadioButton(tr("Linear (top octave in detail)"))
        self.log_button.setChecked(True)
        scale_row.addWidget(QLabel(tr("Frequency scale:")))
        scale_row.addWidget(self.log_button)
        scale_row.addWidget(self.linear_button)
        scale_row.addStretch(1)
        spectro_layout.addLayout(scale_row)
        self.spectrogram = ImageView()
        self.spectrogram.setText(tr("Rendering…"))
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.spectrogram)
        spectro_layout.addWidget(scroll, 1)
        tabs.addTab(spectro, tr("Spectrograms"))

        # tonal balance + band table
        tonal = QWidget()
        tonal_layout = QVBoxLayout(tonal)
        self.tonal = ImageView()
        self.tonal.setText(tr("Rendering…"))
        tonal_layout.addWidget(self.tonal)
        tonal_layout.addWidget(_table(band_level_rows(result.spectra)), 1)
        tabs.addTab(tonal, tr("Tonal balance"))

        # specs + report
        specs = QWidget()
        specs_layout = QVBoxLayout(specs)
        specs_layout.addWidget(_table(_specs_rows(result)))
        report = QLabel(_report_text(result, bpm, key, analysis))
        report.setWordWrap(True)
        report.setTextFormat(Qt.TextFormat.RichText)
        report.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        report.setAlignment(Qt.AlignmentFlag.AlignTop)
        specs_layout.addWidget(report, 1)
        tabs.addTab(specs, tr("Specs and report"))

        self.log_button.toggled.connect(self._show_spectrogram)
        run_task(lambda: render_images(result), self._on_rendered,
                 lambda message: self.spectrogram.setText(tr("Could not render: {error}", error=message)))

    def _on_rendered(self, images: object) -> None:
        try:
            self._images = dict(images)
            self._show_spectrogram()
            if "tonal" in self._images:
                self.tonal.set_png(self._images["tonal"])
            else:
                self.tonal.setText(tr("No tonal comparison available for this track."))
        except RuntimeError:
            pass  # the window was closed before the images were ready

    def _show_spectrogram(self) -> None:
        key = "log" if self.log_button.isChecked() else "linear"
        if key in self._images:
            self.spectrogram.set_png(self._images[key])

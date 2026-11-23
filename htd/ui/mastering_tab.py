"""
Mastering tab: profiles, presets + Advanced Settings, reference track,
auto-trim, export (format / release pack, output folder, file conflicts, tags
& cover, social clip) on the left; the track list (drag and drop, one card per
track, BPM / key detected in the background) on the right; batch progress and
the two main actions at the bottom.

v2 workflow - listen first, write later:
    1. "Prepare the previews" renders each track with the current settings
       into the session's temporary folder (nothing is written next to your
       files). Up to MAX_VERSIONS modes per track are kept, so switching back
       to a mode already rendered is instant.
    2. Listen: Original / Master, Gain Match, Mono, loop A-B. Changing the
       preset while a track plays re-renders that track in the background
       (the mascot dances) and playback follows at the same moment.
    3. "Export" (per track) or "Export all" writes the files: format or
       release pack, tags + cover, clip. Changing only the title / BPM / key /
       tags / format re-exports without mastering again.

Analog console channel: every track gets its own random ``analog_seed`` the moment it
is added (Anti-Parasite tolerance modeling, see core.AntiParasiteFilter). It never
changes for that track - previews, re-renders, exports, undo / redo - and it is saved
in .htd projects, so the exported file is bit-identical to what was heard. An older
project without it simply gets a new seed per track when opened.

All audio work happens off the GUI thread:
    rendering + export      -> workers.MasteringWorker in a QThread
    BPM / key detection     -> workers.analysis_pool() (2 threads)
    reference analysis,
    playback copies         -> workers.run_task (global QThreadPool)
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional, Set, Tuple

from PySide6.QtCore import QEvent, QObject, QSettings, Qt, QTimer, Signal
from PySide6.QtGui import QKeySequence, QPixmap, QShortcut
from PySide6.QtWidgets import (
    QAbstractSpinBox,
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from .. import config
from ..engine import core
from ..engine.analysis import analyse_file
from ..engine.delivery import (
    CLIP_LENGTHS,
    CONFLICT_POLICIES,
    PACK_KEY,
    PACK_LABEL,
    ClipOptions,
    ExportOptions,
    TagInfo,
    TrackMeta,
    export_choices,
    find_export,
    latest_export,
)
from ..engine.export import DEFAULT_FORMAT, FORMATS
from ..engine.ffmpeg_tools import FfmpegInfo
from ..engine.pipeline import TrackResult, new_analog_seed, parse_analog_seed
from ..engine.presets import (
    CEILING_RANGE,
    DEFAULT_PRESET,
    INTENSITY_RANGE,
    PRESETS,
    TARGET_RANGE,
    MasterSettings,
)
from ..engine.reference import MAX_CORRECTION_DB, ReferenceProfile, analyse_reference
from ..i18n import tr_engine
from . import playback
from .activity import ActivityHub
from .analysis_dialog import AnalysisDialog
from .player import PreviewPlayer
from .profiles import ProfileBar
from .track_card import ExportState, TrackCard
from .translate import N_, bind, bind_call, bind_tip, on_language_changed, tr, trn
from .widgets import (
    Card,
    CollapsibleSection,
    DropZone,
    LabeledSlider,
    OutputPicker,
    ScrollBody,
    SectionTitle,
    format_time_precise,
)
from ..engine.render_service import shutdown_pool
from .workers import MasterJob, MasteringWorker, analysis_pool, playback_pool, run_task, start_worker

IMAGE_PATTERNS = "*.jpg *.jpeg *.png *.webp *.bmp *.tif *.tiff"
TRIM_RANGE = (-80.0, -40.0)
MAX_VERSIONS = 3                 # rendered modes kept per track (temporary files)
CACHE_CAP_BYTES = 4 * 1024 ** 3  # ~4 GB of temporary renders across all tracks, then evict the oldest
AUTO_RENDER_DELAY_MS = 700       # after the last settings change, while listening
CONFLICT_LABELS = {
    "rename": N_("Rename (_2, _3…)"),
    "overwrite": N_("Overwrite"),
    "skip": N_("Skip"),
}


def reveal_in_file_manager(path: Path) -> None:
    """Select the file (or pack folder) in Explorer / Finder (opens the folder elsewhere)."""
    try:
        if os.name == "nt":
            subprocess.Popen(f'explorer /select,"{path}"')
        elif sys.platform == "darwin":
            subprocess.Popen(["open", "-R", str(path)])
        else:
            subprocess.Popen(["xdg-open", str(path.parent)])
    except OSError:
        pass


def _hint(text: str = "") -> QLabel:
    """Small grey wrapped label; ``text`` (English) is translated live."""
    label = QLabel()
    label.setObjectName("Meta")
    label.setWordWrap(True)
    if text:
        bind(label, text)
    return label


def format_label(fmt_key: str) -> str:
    """Display name of an export choice, translated."""
    return tr_engine(PACK_LABEL if fmt_key == PACK_KEY else FORMATS[fmt_key].label)


def _settings_from(values) -> Optional[MasterSettings]:
    """MasterSettings from a project (None when unusable)."""
    if not isinstance(values, dict):
        return None
    names = {f.name for f in fields(MasterSettings)}
    try:
        settings = MasterSettings(**{k: v for k, v in values.items() if k in names})
    except TypeError:
        return None
    return settings if settings.preset in PRESETS and settings.recipe in core.PROFILES else None


def _settings_from_profile(values) -> Optional[MasterSettings]:
    """A self-contained mode (no reference) from a saved profile's snapshot."""
    if not isinstance(values, dict):
        return None
    try:
        settings = MasterSettings(
            preset=values.get("preset"), recipe=values.get("recipe"),
            target_lufs=float(values["target"]), ceiling_db=float(values["ceiling"]),
            intensity_pct=int(values["intensity"]), trim=bool(values.get("trim", False)),
            trim_threshold_db=float(values.get("trim_threshold", -60.0)), reference_id="",
            match_eq=bool(values.get("match_eq", True)), match_strength=int(values.get("match_strength", 75)),
            match_loudness=bool(values.get("match_loudness", True)))
    except (KeyError, TypeError, ValueError):
        return None
    return settings if settings.preset in PRESETS and settings.recipe in core.PROFILES else None


def settings_text(settings: MasterSettings) -> str:
    """One line describing a mode, for tooltips."""
    target = tr("reference loudness") if settings.reference_id and settings.match_loudness \
        else f"{settings.target_lufs:g} LUFS"
    parts = [settings.label, tr("{recipe} recipe", recipe=settings.recipe), target,
             f"{settings.ceiling_db:g} dBTP", tr("{pct}% cleanse", pct=settings.intensity_pct)]
    if settings.trim:
        parts.append(tr("auto-trim"))
    if settings.reference_id:
        parts.append(tr("reference match"))
    return " · ".join(parts)


def mode_key(settings: MasterSettings, cut: Optional[Tuple[float, float]],
             analog_seed: Optional[int] = None) -> tuple:
    """What makes two renders of a track identical: the settings, the manual cut and the
    track's analog tolerance seed."""
    return (settings.key(), cut, analog_seed)


def result_key(result: TrackResult) -> tuple:
    return mode_key(result.settings, result.cut_key(), getattr(result, "analog_seed", None))


@dataclass
class TrackEntry:
    """A track of the list and its rendered modes (results, keyed by settings + cut)."""
    source: Path
    card: TrackCard
    versions: Dict[tuple, TrackResult] = field(default_factory=dict)   # creation order (chips)
    used: Dict[tuple, int] = field(default_factory=dict)               # last use (eviction)
    shown: Optional[TrackResult] = None        # what the card displays and plays
    failure: Optional[TrackResult] = None      # last failed / cancelled attempt
    saved_mode: Optional[MasterSettings] = None   # mode recorded in a project, not rendered yet
    # The track's analog "console channel" (Anti-Parasite tolerance seed): drawn once when
    # the track is added, then fixed (renders, exports, undo / redo, .htd projects).
    analog_seed: int = field(default_factory=new_analog_seed)

    @property
    def result(self) -> Optional[TrackResult]:
        return self.shown

    def current(self, settings: MasterSettings) -> Optional[TrackResult]:
        return self.versions.get(mode_key(settings, self.card.cut(), self.analog_seed))

    def touch(self, result: TrackResult, clock: int) -> None:
        key = result_key(result)
        if self.versions.get(key) is result:
            self.used[key] = clock

    def add(self, result: TrackResult, clock: int, protect: Iterable[Optional[TrackResult]] = ()) -> List[TrackResult]:
        """Keep ``result``; returns the results pushed out (oldest use first, never protected ones)."""
        key = result_key(result)
        dropped: List[TrackResult] = []
        old = self.versions.pop(key, None)
        if old is not None and old is not result:
            dropped.append(old)
        self.versions[key] = result
        self.used[key] = clock
        keep = {id(r) for r in protect if r is not None} | {id(result)}
        while len(self.versions) > MAX_VERSIONS:
            candidates = [k for k, r in self.versions.items() if id(r) not in keep]
            if not candidates:
                break
            oldest = min(candidates, key=lambda k: self.used.get(k, 0))
            dropped.append(self.versions.pop(oldest))
            self.used.pop(oldest, None)
        return dropped

    def all_results(self) -> List[TrackResult]:
        found = list(self.versions.values())
        if self.failure is not None:
            found.append(self.failure)
        return found

    def is_current(self, result: Optional[TrackResult], settings: MasterSettings) -> bool:
        return (result is not None and result.ok
                and result_key(result) == mode_key(settings, self.card.cut(), self.analog_seed))


SHORTCUT_KEYS = (Qt.Key.Key_Space, Qt.Key.Key_Tab, Qt.Key.Key_M, Qt.Key.Key_L, Qt.Key.Key_R,
                 Qt.Key.Key_Left, Qt.Key.Key_Right, Qt.Key.Key_A, Qt.Key.Key_B)
SEEK_STEP_MS = 5000
PROJECT_FORMAT = "heins-true-diyae-project"
PROJECT_VERSION = 1


def _same_key(key, wanted) -> bool:
    return key == wanted or key == getattr(wanted, "value", wanted)


class ShortcutFilter(QObject):
    """Application-wide key filter for the Mastering tab's shortcuts (see MasteringTab.handle_key):
    it runs before the focused widget, so Space / Tab do not press a button or move the focus.
    Text fields keep their keys."""

    def __init__(self, tab: "MasteringTab") -> None:
        super().__init__(tab)
        self.tab = tab

    def eventFilter(self, _obj, event) -> bool:  # noqa: N802
        try:
            if event.type() != QEvent.Type.KeyPress:
                return False
        except Exception:  # noqa: BLE001
            return False
        return self.tab.shortcut_key_event(event)


class MasteringTab(QWidget):
    TITLE = N_("Mastering")
    projectChanged = Signal(str)          # file name of the open / saved project ("" = none)

    def __init__(self, ffmpeg: Optional[FfmpegInfo], player: PreviewPlayer, settings: QSettings,
                 parent: Optional[QWidget] = None, activity: Optional[ActivityHub] = None) -> None:
        super().__init__(parent)
        self.ffmpeg, self.player, self.store = ffmpeg, player, settings
        self.activity = activity
        self.entries: Dict[str, TrackEntry] = {}
        self.worker: Optional[MasteringWorker] = None
        self.thread = None
        self._batch_keys: Set[str] = set()       # tracks of the running batch not finished yet
        self._batch_exports: Set[str] = set()     # tracks the running batch exports
        self._batch_auto = False
        self._auto_pending = False
        self._clock = 0
        self._dialogs: List[AnalysisDialog] = []
        self._loading = False
        self.reference: Optional[ReferenceProfile] = None
        self._reference_loading = ""            # path being analysed ("" = none)
        self._reference_error = ""
        self.cover_path = ""
        self._last_message = ""
        # playback: what plays, what was asked for, which buffers are being loaded
        self._playing_result: Optional[TrackResult] = None
        self._want: Optional[Tuple[str, str, Optional[int], object, bool]] = None
        self._in_flight: Set[tuple] = set()
        self._active_key = ""                     # the card keyboard shortcuts work on
        self.project_path: Optional[Path] = None
        self._dirty = False                       # changed since the last save (close prompt)
        self._undo: List[dict] = []               # session snapshots (ticks, cuts, modes, meta, track list)
        self._redo: List[dict] = []
        self._restoring = False
        self._last_snap: Optional[dict] = None

        self._auto_timer = QTimer(self)
        self._auto_timer.setSingleShot(True)
        self._auto_timer.setInterval(AUTO_RENDER_DELAY_MS)
        self._auto_timer.timeout.connect(self._auto_render)

        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(18)
        root.addWidget(self._build_sidebar())
        root.addWidget(self._build_main(), 1)

        self.player.stateChanged.connect(self._on_player_state)
        self.player.positionChanged.connect(self._on_player_position)
        self.player.playingChanged.connect(self._on_player_playing)
        self.player.deviceChanged.connect(self._on_audio_device_changed)
        on_language_changed(lambda _code: self._refresh(), self)
        self._shortcut_filter = ShortcutFilter(self)
        app = QApplication.instance()
        if app is not None:
            app.installEventFilter(self._shortcut_filter)
        for sequence, slot in ((QKeySequence.StandardKey.Save, lambda: self.save_project()),
                               (QKeySequence.StandardKey.Open, lambda: self.open_project()),
                               (QKeySequence.StandardKey.Undo, self.undo),
                               (QKeySequence.StandardKey.Redo, self.redo),
                               (QKeySequence("Ctrl+Y"), self.redo)):
            shortcut = QShortcut(QKeySequence(sequence), self)
            shortcut.activated.connect(slot)
        self._restore()
        self._refresh()

    # ================================================================ layout
    def _build_sidebar(self) -> QWidget:
        panel = Card(name="Panel")
        panel.setFixedWidth(356)
        outer = QVBoxLayout(panel)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        body = QWidget()
        body.setObjectName("ScrollBody")
        layout = QVBoxLayout(body)
        layout.setContentsMargins(18, 18, 26, 18)          # right: clear of the vertical scroll bar
        layout.setSpacing(10)
        scroll.setWidget(body)
        outer.addWidget(scroll)

        # ---- profiles ----------------------------------------------------------
        layout.addWidget(SectionTitle(N_("Profiles")))
        self.profiles = ProfileBar(self.store, self._profile_snapshot, self._apply_profile)
        self.profiles.profilesChanged.connect(self._refresh_mode_items)
        layout.addWidget(self.profiles)
        layout.addWidget(_hint(N_("Your favourite combinations (mode, recipe, Anti-Parasite, auto-trim, "
                                  "export). 💾 saves the current settings.")))
        layout.addSpacing(4)

        # ---- preset + advanced (unchanged engine controls) ------------------
        layout.addWidget(SectionTitle(N_("Preset")))
        self.preset_combo = QComboBox()
        self.preset_combo.addItems(list(PRESETS))
        self.preset_summary = _hint()
        layout.addWidget(self.preset_combo)
        layout.addWidget(self.preset_summary)

        self.advanced = CollapsibleSection(N_("⚙️  Advanced Settings"))
        adv = self.advanced.content_layout
        adv.addWidget(bind(QLabel(), "Tone and dynamics recipe"))
        self.recipe_combo = QComboBox()
        self.recipe_combo.addItems(list(core.PROFILES))
        bind_tip(self.recipe_combo, "EQ curve, compressor and saturation used by the mastering chain.")
        adv.addWidget(self.recipe_combo)
        self.target_slider = LabeledSlider(
            N_("Limiter drive (target loudness)"), TARGET_RANGE[0], TARGET_RANGE[1], 0.5, "{:.1f} LUFS",
            N_("How hard the mix is pushed into the limiter. Higher = louder and more limiting. "
               "Streaming platforms turn masters louder than -14 LUFS down."))
        self.ceiling_slider = LabeledSlider(
            N_("Limiter ceiling"), CEILING_RANGE[0], CEILING_RANGE[1], 0.1, "{:.1f} dBTP",
            N_("Highest true peak allowed. -1.0 dBTP is the safe value for MP3 / AAC / streaming."))
        self.intensity_slider = LabeledSlider(
            N_("Anti-Parasite intensity"), INTENSITY_RANGE[0], INTENSITY_RANGE[1], 1, "{:.0f}%",
            N_("Spectral cleanse depth and phase / time micro-variation. 0% keeps only the "
               "20 Hz - 20 kHz band-limiting. Above ~70% the cleanse becomes assertive."))
        for slider in (self.target_slider, self.ceiling_slider, self.intensity_slider):
            adv.addWidget(slider)
        self.reset_button = bind(QPushButton(), "Reset to preset values")
        adv.addWidget(self.reset_button)
        layout.addWidget(self.advanced)

        self.settings_summary = _hint()
        self.settings_summary.setTextFormat(Qt.TextFormat.RichText)
        layout.addWidget(self.settings_summary)

        # ---- reference track -------------------------------------------------
        self.reference_section = CollapsibleSection(N_("🎯  Reference track"))
        ref = self.reference_section.content_layout
        row = QHBoxLayout()
        row.setSpacing(6)
        self.reference_button = bind(QPushButton(), "Load a reference…")
        self.reference_clear = QPushButton("✕")
        self.reference_clear.setObjectName("IconButton")
        bind_tip(self.reference_clear, "Stop using the reference")
        row.addWidget(self.reference_button, 1)
        row.addWidget(self.reference_clear)
        ref.addLayout(row)
        self.reference_status = _hint()
        ref.addWidget(self.reference_status)
        self.match_eq_check = bind(QCheckBox(), "Match the tonal balance (EQ)")
        bind_tip(self.match_eq_check,
                 "Replaces the recipe EQ with a linear-phase EQ that moves the track's broad tonal "
                 "balance towards the reference (half-octave smoothing, at most ±{db} dB). "
                 "Compression, saturation and the limiter stay those of the recipe.",
                 db=f"{MAX_CORRECTION_DB:g}")
        self.match_strength = LabeledSlider(N_("Match strength"), 0, 100, 5, "{:.0f}%",
                                            N_("How far to go towards the reference's tonal balance."))
        self.match_loudness_check = bind(QCheckBox(), "Match the loudness (target = reference LUFS)")
        bind_tip(self.match_loudness_check,
                 "Uses the reference's integrated loudness as the limiter target (kept between -20 and "
                 "-6 LUFS). Your ceiling still applies.")
        for widget in (self.match_eq_check, self.match_strength, self.match_loudness_check):
            ref.addWidget(widget)
        layout.addWidget(self.reference_section)

        # ---- auto-trim -------------------------------------------------------
        self.trim_section = CollapsibleSection(N_("✂️  Auto-trim and fades"))
        trim = self.trim_section.content_layout
        self.trim_check = bind(QCheckBox(), "Cut the silence at the start and the end")
        bind_tip(self.trim_check,
                 "After mastering: removes leading / trailing silence (10 ms kept before the first "
                 "sound, 120 ms after the last) and adds anti-click fades (5 ms in, 20 ms out).")
        self.trim_slider = LabeledSlider(N_("Silence threshold"), TRIM_RANGE[0], TRIM_RANGE[1], 1, "{:.0f} dBFS",
                                         N_("Anything quieter than this at the edges counts as silence. "
                                            "-60 dBFS suits most tracks; raise it for noisy intros / tails."))
        trim.addWidget(self.trim_check)
        trim.addWidget(self.trim_slider)
        layout.addWidget(self.trim_section)

        # ---- export ----------------------------------------------------------
        layout.addSpacing(6)
        layout.addWidget(SectionTitle(N_("Export")))
        self.format_combo = QComboBox()
        for index, (key, label) in enumerate(export_choices()):
            self.format_combo.addItem(label, key)
            bind_call(self.format_combo, lambda text, i=index: self.format_combo.setItemText(i, text), label)
        layout.addWidget(self.format_combo)
        self.format_hint = _hint()
        layout.addWidget(self.format_hint)
        self.name_bpm_key = bind(QCheckBox(), "Add BPM and key to the file names")
        bind_tip(self.name_bpm_key, "Example: MyTrack_142BPM_Cm_HTD_Standard.wav")
        layout.addWidget(self.name_bpm_key)
        self.output = OutputPicker(config.default_output_dir())
        layout.addWidget(self.output)
        self.subfolder_check = bind(QCheckBox(), "One subfolder per mode (…/Club/, …/Streaming/)")
        bind_tip(self.subfolder_check, "Each export goes into a subfolder named after its preset, so several "
                                       "modes of the same track can sit side by side.")
        layout.addWidget(self.subfolder_check)
        self.strip_meta_check = bind(QCheckBox(), "Export without metadata (100% blank files)")
        bind_tip(self.strip_meta_check, "Writes the audio only: no title, artist, album, BPM, key or cover, and no "
                                        "software / encoder signature. Source tags are always stripped either way.")
        layout.addWidget(self.strip_meta_check)
        conflict_row = QHBoxLayout()
        conflict_row.setSpacing(6)
        conflict_row.addWidget(bind(QLabel(), "If the file already exists:"))
        self.conflict_combo = QComboBox()
        for index, policy in enumerate(CONFLICT_POLICIES):
            self.conflict_combo.addItem(tr(CONFLICT_LABELS[policy]), policy)
            bind_call(self.conflict_combo, lambda text, i=index: self.conflict_combo.setItemText(i, text),
                      CONFLICT_LABELS[policy])
        bind_tip(self.conflict_combo, "Rename keeps both files (name_2, name_3…). Overwrite replaces the old "
                                      "file. Skip leaves it untouched and writes nothing for that track.")
        conflict_row.addWidget(self.conflict_combo, 1)
        layout.addLayout(conflict_row)

        # ---- tags + cover ----------------------------------------------------
        self.tags_section = CollapsibleSection(N_("🏷️  Tags and cover"))
        tags = self.tags_section.content_layout
        grid = QGridLayout()
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(6)
        self.artist_edit, self.album_edit = QLineEdit(), QLineEdit()
        self.year_edit, self.genre_edit = QLineEdit(), QLineEdit()
        self.year_edit.setMaxLength(10)
        for row_index, (label, edit, placeholder) in enumerate((
                (N_("Artist"), self.artist_edit, "Diyae"), (N_("Album"), self.album_edit, N_("Single / EP name")),
                (N_("Year"), self.year_edit, "2026"), (N_("Genre"), self.genre_edit, "Trap, House…"))):
            grid.addWidget(bind(QLabel(), label), row_index, 0)
            if placeholder == "Single / EP name":
                bind(edit, placeholder, "setPlaceholderText")
            else:                                  # examples, the same in every language
                edit.setPlaceholderText(placeholder)
            grid.addWidget(edit, row_index, 1)
        tags.addLayout(grid)
        cover_row = QHBoxLayout()
        cover_row.setSpacing(8)
        self.cover_thumb = QLabel(tr("No\ncover"))
        self.cover_thumb.setObjectName("CoverThumb")
        self.cover_thumb.setFixedSize(64, 64)
        self.cover_thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cover_buttons = QVBoxLayout()
        cover_buttons.setSpacing(4)
        self.cover_button = bind(QPushButton(), "Choose a cover…")
        self.cover_clear = bind(QPushButton(), "Remove cover")
        cover_buttons.addWidget(self.cover_button)
        cover_buttons.addWidget(self.cover_clear)
        cover_row.addWidget(self.cover_thumb)
        cover_row.addLayout(cover_buttons, 1)
        tags.addLayout(cover_row)
        tags.addWidget(_hint(N_("Title, BPM and key come from each track card. MP3, FLAC and M4A get "
                                "the cover (square crop, 1400 px); WAV gets text tags only. The track "
                                "number is written when an album is set.")))
        layout.addWidget(self.tags_section)

        # ---- social clip -----------------------------------------------------
        self.clip_section = CollapsibleSection(N_("📱  Social clip"))
        clip = self.clip_section.content_layout
        self.clip_check = bind(QCheckBox(), "Export a short clip (TikTok / Reels / Shorts)")
        clip_row = QHBoxLayout()
        clip_row.setSpacing(6)
        self.clip_length = QComboBox()
        for seconds in CLIP_LENGTHS:
            self.clip_length.addItem(f"{seconds} s", seconds)
        self.clip_mode = QComboBox()
        for index, (label, mode) in enumerate(((N_("Best part (auto)"), "auto"), (N_("From the start"), "start"))):
            self.clip_mode.addItem(label, mode)
            bind_call(self.clip_mode, lambda text, i=index: self.clip_mode.setItemText(i, text), label)
        bind_tip(self.clip_mode, "Auto picks the most energetic passage and, when the BPM is known, "
                                 "starts on a beat and keeps whole bars.")
        clip_row.addWidget(self.clip_length)
        clip_row.addWidget(self.clip_mode, 1)
        self.video_check = bind(QCheckBox(), "Also make a vertical video (1080×1920)")
        self.clip_hint = _hint(N_("M4A (AAC 256 kbps) with a 0.25 s fade-in and a 1.5 s fade-out. The "
                                  "video shows the cover on a blurred background."))
        for item in (self.clip_check, clip_row, self.video_check, self.clip_hint):
            (clip.addLayout if isinstance(item, QHBoxLayout) else clip.addWidget)(item)
        layout.addWidget(self.clip_section)
        layout.addStretch(1)

        # ---- signals ---------------------------------------------------------
        self.preset_combo.currentTextChanged.connect(self._on_preset)
        self.reset_button.clicked.connect(lambda: self._apply_preset(self.preset_combo.currentText()))
        self.recipe_combo.currentTextChanged.connect(lambda _text: self._on_setting_changed())
        for slider in (self.target_slider, self.ceiling_slider, self.intensity_slider,
                       self.match_strength, self.trim_slider):
            slider.valueChanged.connect(lambda _value: self._on_setting_changed())
        for check in (self.match_eq_check, self.match_loudness_check, self.trim_check, self.name_bpm_key,
                      self.clip_check, self.video_check, self.subfolder_check, self.strip_meta_check):
            check.toggled.connect(lambda _on: self._on_setting_changed())
        for combo in (self.format_combo, self.clip_length, self.clip_mode, self.conflict_combo):
            combo.currentIndexChanged.connect(lambda _index: self._on_setting_changed())
        for edit in (self.artist_edit, self.album_edit, self.year_edit, self.genre_edit):
            edit.editingFinished.connect(self._on_setting_changed)
        self.output.changed.connect(self._on_setting_changed)
        self.reference_button.clicked.connect(self._pick_reference)
        self.reference_clear.clicked.connect(self._clear_reference)
        self.cover_button.clicked.connect(self._pick_cover)
        self.cover_clear.clicked.connect(lambda: self._set_cover(""))
        return panel

    def _build_main(self) -> QWidget:
        main = QWidget()
        layout = QVBoxLayout(main)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        self.drop = DropZone(core.ALLOWED_EXTENSIONS, N_("Drop tracks or folders here"),
                             N_("WAV, MP3, M4A, FLAC, OGG, AIFF - folders are scanned for audio files."))
        layout.addWidget(self.drop)

        header = QHBoxLayout()
        header.setSpacing(8)
        self.batch_title = QLabel(tr("No tracks yet"))
        self.batch_title.setObjectName("CardTitle")
        self.select_all_button = QPushButton(tr("☑ Tick all"))
        self.select_all_button.setObjectName("MiniButton")
        bind_tip(self.select_all_button, "Tick or untick every track: the global buttons only process ticked tracks.")
        self.open_project_button = bind(QPushButton(), "📂 Open a project…")
        self.save_project_button = bind(QPushButton(), "💾 Save the project…")
        bind_tip(self.open_project_button, "Reopen a session saved as a .htd file (Ctrl+O / ⌘O).")
        bind_tip(self.save_project_button, "Save the whole session in a .htd file: tracks, ticks, titles, BPM, keys, "
                                           "cuts, A-B markers, modes and the settings on the left (Ctrl+S / ⌘S).")
        self.clear_button = bind(QPushButton(), "Clear list")
        header.addWidget(self.batch_title)
        header.addWidget(self.select_all_button)
        header.addStretch(1)
        header.addWidget(self.open_project_button)
        header.addWidget(self.save_project_button)
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
        self.batch_progress.setVisible(False)              # only while something runs
        bottom = QHBoxLayout()
        bottom.setSpacing(14)
        self.batch_message = QLabel(tr("Add tracks to begin."))
        self.batch_message.setObjectName("Meta")
        self.batch_message.setWordWrap(True)
        self.pause_button = QPushButton(tr("⏸ Pause"))
        self.pause_button.setObjectName("MiniButton")
        bind_tip(self.pause_button, "Pause the queue after the current track (the work already done is kept).")
        self.cancel_button = bind(QPushButton(), "Cancel")
        self.cancel_button.setObjectName("Danger")
        self.export_all_button = QPushButton(tr("⬇ Export all"))
        self.export_all_button.setObjectName("ExportButton")
        bind_tip(self.export_all_button, "Writes the files of every ticked track (tracks not rendered with the current "
                                         "settings are rendered first).")
        self.run_button = QPushButton(tr("🎧 Prepare the previews"))
        self.run_button.setObjectName("Primary")
        bind_tip(self.run_button, "Renders each ticked track with the current settings into a temporary folder so "
                                  "you can listen and compare. Nothing is written next to your files.")
        bottom.addWidget(self.batch_message, 1)
        bottom.addWidget(self.pause_button)
        bottom.addWidget(self.cancel_button)
        bottom.addWidget(self.export_all_button)
        bottom.addWidget(self.run_button)
        self._paused = False
        footer_layout.addWidget(self.batch_progress)
        footer_layout.addLayout(bottom)
        layout.addWidget(footer)

        self.drop.pathsDropped.connect(self.add_files)
        self.clear_button.clicked.connect(self.clear)
        self.select_all_button.clicked.connect(self._toggle_all)
        self.open_project_button.clicked.connect(lambda: self.open_project())
        self.save_project_button.clicked.connect(lambda: self.save_project())
        self.run_button.clicked.connect(self.start)
        self.export_all_button.clicked.connect(self.export_all)
        self.cancel_button.clicked.connect(self.cancel)
        self.pause_button.clicked.connect(self._toggle_pause)
        return main

    # ================================================================ settings
    def _reference_active(self) -> bool:
        return self.reference is not None and (self.match_eq_check.isChecked()
                                               or self.match_loudness_check.isChecked())

    def settings(self) -> MasterSettings:
        active = self._reference_active()
        return MasterSettings(
            preset=self.preset_combo.currentText(),
            recipe=self.recipe_combo.currentText(),
            target_lufs=round(self.target_slider.value(), 1),
            ceiling_db=round(self.ceiling_slider.value(), 1),
            intensity_pct=int(round(self.intensity_slider.value())),
            trim=self.trim_check.isChecked(),
            trim_threshold_db=round(self.trim_slider.value(), 1),
            reference_id=self.reference.ident if active else "",
            match_eq=self.match_eq_check.isChecked(),
            match_strength=int(round(self.match_strength.value())),
            match_loudness=self.match_loudness_check.isChecked(),
        )

    def fmt_key(self) -> str:
        return self.format_combo.currentData() or DEFAULT_FORMAT

    def conflict_policy(self) -> str:
        policy = self.conflict_combo.currentData()
        return policy if policy in CONFLICT_POLICIES else "rename"

    def _can_make_video(self) -> bool:
        return bool(self.cover_path) and self.ffmpeg is not None and bool(self.ffmpeg.video_encoder)

    def export_options(self) -> ExportOptions:
        folder = self.output.folder()
        cover = self.cover_path if self.cover_path and Path(self.cover_path).is_file() else ""
        stamp = Path(cover).stat().st_mtime if cover else 0.0
        return ExportOptions(
            fmt_key=self.fmt_key(),
            out_dir=str(folder) if folder is not None else "",
            name_bpm_key=self.name_bpm_key.isChecked(),
            tags=TagInfo(artist=self.artist_edit.text().strip(), album=self.album_edit.text().strip(),
                         year=self.year_edit.text().strip(), genre=self.genre_edit.text().strip(),
                         cover=cover, cover_stamp=stamp),
            clip=ClipOptions(enabled=self.clip_check.isChecked(),
                             seconds=int(self.clip_length.currentData() or 30),
                             mode=self.clip_mode.currentData() or "auto",
                             video=self.video_check.isChecked() and self._can_make_video()),
            subfolder_per_mode=self.subfolder_check.isChecked(),
            on_conflict=self.conflict_policy(),
            strip_metadata=self.strip_meta_check.isChecked(),
        )

    def track_meta(self, key: str, options: Optional[ExportOptions] = None) -> TrackMeta:
        """Title / BPM / key from the card; track number only matters when an album is set."""
        card = self.entries[key].card
        options = options or self.export_options()
        number = total = 0
        if options.tags.album:
            keys = list(self.entries)
            number, total = keys.index(key) + 1, len(keys)
        return TrackMeta(title=card.track_title(), bpm=card.bpm(), key=card.key_name(),
                         beat_offset_s=card.beat_offset(), track_no=number, track_total=total)

    def _apply_preset(self, name: str) -> None:
        preset = PRESETS[name]
        self._loading = True
        self.recipe_combo.setCurrentText(preset.recipe)
        self.target_slider.setValue(preset.target_lufs)
        self.ceiling_slider.setValue(preset.ceiling_db)
        self.intensity_slider.setValue(preset.intensity_pct)
        self._loading = False
        self._on_setting_changed()

    def _on_preset(self, name: str) -> None:
        if name in PRESETS and not self._loading:
            self._apply_preset(name)

    def apply_settings(self, settings: MasterSettings) -> None:
        """Put a mode back in the sidebar (rendered-mode chips)."""
        self._loading = True
        self.preset_combo.setCurrentText(settings.preset)
        self.recipe_combo.setCurrentText(settings.recipe)
        self.target_slider.setValue(settings.target_lufs)
        self.ceiling_slider.setValue(settings.ceiling_db)
        self.intensity_slider.setValue(settings.intensity_pct)
        self.trim_check.setChecked(settings.trim)
        self.trim_slider.setValue(settings.trim_threshold_db)
        if settings.reference_id:
            if self.reference is not None and self.reference.ident == settings.reference_id:
                self.match_eq_check.setChecked(settings.match_eq)
                self.match_strength.setValue(settings.match_strength)
                self.match_loudness_check.setChecked(settings.match_loudness)
        elif self.reference is not None:            # that mode was made without the reference
            self.match_eq_check.setChecked(False)
            self.match_loudness_check.setChecked(False)
        self._loading = False
        self._on_setting_changed()

    def _on_setting_changed(self) -> None:
        if self._loading:
            return
        self._save()
        self._refresh()

    def _flag(self, name: str, default: bool) -> bool:
        return str(self.store.value(name, "true" if default else "false")) == "true"

    def _restore(self) -> None:
        self._loading = True
        preset = self.store.value("mastering/preset", DEFAULT_PRESET)
        self.preset_combo.setCurrentText(preset if preset in PRESETS else DEFAULT_PRESET)
        base = PRESETS[self.preset_combo.currentText()]
        recipe = self.store.value("mastering/recipe", base.recipe)
        self.recipe_combo.setCurrentText(recipe if recipe in core.PROFILES else base.recipe)
        self.target_slider.setValue(float(self.store.value("mastering/target", base.target_lufs)))
        self.ceiling_slider.setValue(float(self.store.value("mastering/ceiling", base.ceiling_db)))
        self.intensity_slider.setValue(float(self.store.value("mastering/intensity", base.intensity_pct)))
        index = self.format_combo.findData(self.store.value("mastering/format", DEFAULT_FORMAT))
        self.format_combo.setCurrentIndex(max(0, index))
        self.output.set_state(self._flag("mastering/next_to_source", False),
                              str(self.store.value("mastering/folder", "")))
        self.subfolder_check.setChecked(self._flag("export/subfolder_per_mode", False))
        self.strip_meta_check.setChecked(self._flag("export/strip_metadata", False))
        self.conflict_combo.setCurrentIndex(max(0, self.conflict_combo.findData(
            str(self.store.value("export/on_conflict", "rename")))))
        self.trim_check.setChecked(self._flag("mastering/trim", False))
        self.trim_slider.setValue(float(self.store.value("mastering/trim_threshold", -60.0)))
        self.match_eq_check.setChecked(self._flag("reference/match_eq", True))
        self.match_strength.setValue(float(self.store.value("reference/strength", 75)))
        self.match_loudness_check.setChecked(self._flag("reference/match_loudness", True))
        self.name_bpm_key.setChecked(self._flag("export/name_bpm_key", False))
        self.artist_edit.setText(str(self.store.value("tags/artist", "")))
        self.album_edit.setText(str(self.store.value("tags/album", "")))
        self.year_edit.setText(str(self.store.value("tags/year", "")))
        self.genre_edit.setText(str(self.store.value("tags/genre", "")))
        self.clip_check.setChecked(self._flag("clip/enabled", False))
        self.clip_length.setCurrentIndex(max(0, self.clip_length.findData(int(self.store.value("clip/seconds", 30)))))
        self.clip_mode.setCurrentIndex(max(0, self.clip_mode.findData(self.store.value("clip/mode", "auto"))))
        self.video_check.setChecked(self._flag("clip/video", True))
        cover = str(self.store.value("tags/cover", ""))
        reference = str(self.store.value("reference/path", ""))
        self._loading = False
        self._set_cover(cover if cover and Path(cover).is_file() else "", save=False)
        if reference and Path(reference).is_file():
            self._load_reference(reference)
        self.trim_section.toggle.setChecked(self.trim_check.isChecked())
        self.clip_section.toggle.setChecked(self.clip_check.isChecked())

    def _save(self) -> None:
        current = self.settings()
        values = {
            "mastering/preset": current.preset,
            "mastering/recipe": current.recipe,
            "mastering/target": current.target_lufs,
            "mastering/ceiling": current.ceiling_db,
            "mastering/intensity": current.intensity_pct,
            "mastering/format": self.fmt_key(),
            "mastering/next_to_source": "true" if self.output.folder() is None else "false",
            "mastering/folder": self.output.path_edit.text(),
            "export/subfolder_per_mode": "true" if self.subfolder_check.isChecked() else "false",
            "export/strip_metadata": "true" if self.strip_meta_check.isChecked() else "false",
            "export/on_conflict": self.conflict_policy(),
            "mastering/trim": "true" if current.trim else "false",
            "mastering/trim_threshold": current.trim_threshold_db,
            "reference/match_eq": "true" if current.match_eq else "false",
            "reference/strength": current.match_strength,
            "reference/match_loudness": "true" if current.match_loudness else "false",
            "export/name_bpm_key": "true" if self.name_bpm_key.isChecked() else "false",
            "tags/artist": self.artist_edit.text().strip(),
            "tags/album": self.album_edit.text().strip(),
            "tags/year": self.year_edit.text().strip(),
            "tags/genre": self.genre_edit.text().strip(),
            "tags/cover": self.cover_path,
            "clip/enabled": "true" if self.clip_check.isChecked() else "false",
            "clip/seconds": int(self.clip_length.currentData() or 30),
            "clip/mode": self.clip_mode.currentData() or "auto",
            "clip/video": "true" if self.video_check.isChecked() else "false",
        }
        for name, value in values.items():
            self.store.setValue(name, value)

    # ================================================================ profiles
    def _profile_snapshot(self) -> dict:
        s = self.settings()
        return {
            "preset": s.preset, "recipe": s.recipe, "target": s.target_lufs, "ceiling": s.ceiling_db,
            "intensity": s.intensity_pct, "trim": s.trim, "trim_threshold": s.trim_threshold_db,
            "match_eq": s.match_eq, "match_strength": s.match_strength, "match_loudness": s.match_loudness,
            "format": self.fmt_key(), "name_bpm_key": self.name_bpm_key.isChecked(),
            "next_to_source": self.output.folder() is None, "folder": self.output.path_edit.text(),
            "subfolder_per_mode": self.subfolder_check.isChecked(), "on_conflict": self.conflict_policy(),
            "clip": self.clip_check.isChecked(), "clip_seconds": int(self.clip_length.currentData() or 30),
            "clip_mode": self.clip_mode.currentData() or "auto", "clip_video": self.video_check.isChecked(),
        }

    def _apply_profile(self, values: dict) -> None:
        """Recall a profile; unknown or invalid values are left as they are."""
        def number(name: str, setter) -> None:
            try:
                if name in values:
                    setter(float(values[name]))
            except (TypeError, ValueError):
                pass

        def flag(name: str, check: QCheckBox) -> None:
            if isinstance(values.get(name), bool):
                check.setChecked(values[name])

        def choice(combo: QComboBox, data) -> None:
            index = combo.findData(data)
            if index >= 0:
                combo.setCurrentIndex(index)

        self._loading = True
        if values.get("preset") in PRESETS:
            self.preset_combo.setCurrentText(values["preset"])
        if values.get("recipe") in core.PROFILES:
            self.recipe_combo.setCurrentText(values["recipe"])
        number("target", self.target_slider.setValue)
        number("ceiling", self.ceiling_slider.setValue)
        number("intensity", self.intensity_slider.setValue)
        flag("trim", self.trim_check)
        number("trim_threshold", self.trim_slider.setValue)
        flag("match_eq", self.match_eq_check)
        number("match_strength", self.match_strength.setValue)
        flag("match_loudness", self.match_loudness_check)
        if "format" in values:
            choice(self.format_combo, values["format"])
        flag("name_bpm_key", self.name_bpm_key)
        if isinstance(values.get("next_to_source"), bool):
            self.output.set_state(values["next_to_source"], str(values.get("folder") or ""))
        flag("subfolder_per_mode", self.subfolder_check)
        if values.get("on_conflict") in CONFLICT_POLICIES:
            choice(self.conflict_combo, values["on_conflict"])
        flag("clip", self.clip_check)
        if "clip_seconds" in values:
            choice(self.clip_length, values["clip_seconds"])
        if "clip_mode" in values:
            choice(self.clip_mode, values["clip_mode"])
        flag("clip_video", self.video_check)
        self._loading = False
        self.trim_section.toggle.setChecked(self.trim_check.isChecked() or self.trim_section.toggle.isChecked())
        self.clip_section.toggle.setChecked(self.clip_check.isChecked() or self.clip_section.toggle.isChecked())
        self._on_setting_changed()

    # ================================================================ reference
    def _pick_reference(self) -> None:
        start = str(Path(self.reference.path).parent) if self.reference else str(Path.home())
        patterns = " ".join(f"*.{ext}" for ext in core.ALLOWED_EXTENSIONS)
        path, _filter = QFileDialog.getOpenFileName(self, tr("Choose a reference track"), start,
                                                    tr("Audio ({patterns})", patterns=patterns))
        if path:
            self._load_reference(path)

    def _load_reference(self, path: str) -> None:
        self._reference_loading = path
        self._reference_error = ""
        self.reference_section.toggle.setChecked(True)
        self._refresh()

        def _done(profile: object) -> None:
            if self._reference_loading != path:
                return                               # replaced or cleared in the meantime
            self._reference_loading = ""
            self.reference = profile if isinstance(profile, ReferenceProfile) else None
            self.store.setValue("reference/path", path)
            self._refresh()

        def _failed(message: str) -> None:
            if self._reference_loading != path:
                return
            self._reference_loading = ""
            self.reference = None
            self.store.setValue("reference/path", "")
            self._reference_error = tr("⚠ Could not use {name}: {error}", name=Path(path).name,
                                       error=tr_engine(message))
            self._refresh()

        run_task(lambda: analyse_reference(Path(path)), _done, _failed)

    def _clear_reference(self) -> None:
        self._reference_loading = ""
        self.reference = None
        self.store.setValue("reference/path", "")
        self._reference_error = ""
        self._refresh()

    # ================================================================ cover
    def _pick_cover(self) -> None:
        start = str(Path(self.cover_path).parent) if self.cover_path else str(Path.home())
        path, _filter = QFileDialog.getOpenFileName(self, tr("Choose a cover image"), start,
                                                    tr("Images ({patterns})", patterns=IMAGE_PATTERNS))
        if path:
            self._set_cover(path)

    def _set_cover(self, path: str, save: bool = True) -> None:
        self.cover_path = path
        pixmap = QPixmap(path) if path else QPixmap()
        if path and not pixmap.isNull():
            side = min(pixmap.width(), pixmap.height())
            square = pixmap.copy((pixmap.width() - side) // 2, (pixmap.height() - side) // 2, side, side)
            self.cover_thumb.setPixmap(square.scaled(64, 64, Qt.AspectRatioMode.IgnoreAspectRatio,
                                                     Qt.TransformationMode.SmoothTransformation))
        else:
            self.cover_thumb.setPixmap(QPixmap())
            self.cover_thumb.setText(Path(path).suffix.upper().lstrip(".") or tr("No\ncover"))
        self.cover_thumb.setToolTip(path or tr("No cover"))
        self.cover_clear.setEnabled(bool(path))
        if save:
            self._on_setting_changed()

    # ================================================================ list
    def add_files(self, paths: List[Path]) -> None:
        added = 0
        for path in paths:
            key = str(path.resolve())
            if key in self.entries:
                continue
            card = TrackCard(key, path, len(self.entries) + 1)
            card.playRequested.connect(self._on_play)
            card.gainMatchToggled.connect(lambda k, _on: self._follow_playback(k))
            card.monoToggled.connect(lambda k, _on: self._follow_playback(k))
            card.loopChanged.connect(self._on_loop_changed)
            card.analysisRequested.connect(self._on_analysis)
            card.revealRequested.connect(self._on_reveal)
            card.removeRequested.connect(self.remove)
            card.seekRequested.connect(self._on_seek)
            card.pauseToggled.connect(self._on_pause_toggle)
            card.exportRequested.connect(self.export_track)
            card.versionRequested.connect(self._on_version)
            card.metaChanged.connect(self._on_card_meta)
            card.selectionChanged.connect(self._on_card_selection)
            card.cutChanged.connect(self._on_cut_changed)
            card.modeChanged.connect(self._on_cut_changed)       # a per-track mode change is another render
            card.homeRequested.connect(self._on_home)
            card.activated.connect(self._set_active)
            card.set_busy(self.is_running())
            card.set_mode_items(self._mode_items())
            self.entries[key] = TrackEntry(path, card, analog_seed=new_analog_seed())
            self.list_body.insert(card)
            self._detect(key, path, card)
            self._prepare_original(key)
            added += 1
        if added:
            self._push_undo()
            self._refresh()

    def _on_card_meta(self, _key: str) -> None:
        self._push_undo()
        self._refresh()

    def _on_card_selection(self, _key: str, _on: bool) -> None:
        self._push_undo()
        self._update_buttons()

    def _prepare_original(self, key: str) -> None:
        """Right after adding: decode the original for listening (background) - the seek bar
        gets the track's length, Original / Mono / loop / cut work before any rendering."""
        entry = self.entries.get(key)
        rate = self.player.output_rate()
        if entry is None or not rate:
            return
        item = playback.Original(entry.source)
        card = entry.card

        def _ready() -> None:
            if self.entries.get(key) is entry:
                card.set_original_state(True)
                card.set_duration_ms(int(round(playback.duration_s(item, rate) * 1000)))

        def _failed(message: str) -> None:
            if self.entries.get(key) is entry:
                card.set_original_state(False, message)

        self._load_buffer(item, "original", rate, disk_only=True, on_ready=_ready, on_failed=_failed)

    def _toggle_all(self) -> None:
        """Tick every track, or untick them all when they are all ticked."""
        tick = not all(entry.card.is_selected() for entry in self.entries.values())
        for entry in self.entries.values():
            entry.card.select_box.blockSignals(True)
            entry.card.set_selected(tick)
            entry.card.select_box.blockSignals(False)
        self._push_undo()
        self._update_buttons()

    def _on_cut_changed(self, key: str) -> None:
        """A new manual cut / per-track mode is another render (the old ones stay one click away)."""
        self._push_undo()
        self._refresh()

    # ---- dirty flag + undo / redo of session actions -------------------------------
    def _card_state(self, entry: "TrackEntry") -> dict:
        card = entry.card
        a, b = card.seek.loop_points()
        return {"selected": card.is_selected(), "title": card.title_edit.text(), "bpm": card.bpm() or 0,
                "key": card.key_name(), "cut": list(card.cut()) if card.cut() is not None else None,
                "loop": {"a": a, "b": b, "on": card.seek.loop_button.isChecked()},
                "gain_match": card.gain_match.isChecked(), "mono": card.mono_button.isChecked(),
                "mode_token": card.mode_token(), "analog_seed": entry.analog_seed}

    def _snapshot(self) -> dict:
        return {"order": list(self.entries), "tracks": {k: self._card_state(e) for k, e in self.entries.items()}}

    def _ensure_baseline(self) -> None:
        if self._last_snap is None:
            self._last_snap = self._snapshot()

    def _push_undo(self) -> None:
        """Record the state before this change so Ctrl+Z can come back to it."""
        if self._restoring:
            return
        self._ensure_baseline()
        self._undo.append(self._last_snap)
        del self._undo[:-60]                             # bounded history
        self._redo.clear()
        self._last_snap = self._snapshot()
        self._mark_dirty()

    def can_undo(self) -> bool:
        return bool(self._undo)

    def can_redo(self) -> bool:
        return bool(self._redo)

    def undo(self) -> None:
        if not self._undo or self.is_running():
            return
        self._redo.append(self._snapshot())
        snapshot = self._undo.pop()
        self._last_snap = snapshot
        self._restore_snapshot(snapshot)

    def redo(self) -> None:
        if not self._redo or self.is_running():
            return
        self._undo.append(self._snapshot())
        snapshot = self._redo.pop()
        self._last_snap = snapshot
        self._restore_snapshot(snapshot)

    def _restore_snapshot(self, snapshot: dict) -> None:
        self._restoring = True
        try:
            order = snapshot["order"]
            for key in list(self.entries):
                if key not in order:
                    self.remove(key)
            missing = [Path(key) for key in order if key not in self.entries]
            if missing:
                self.add_files(missing)
            for key, state in snapshot["tracks"].items():
                entry = self.entries.get(key)
                if entry is not None:
                    self._apply_track_state(entry, state)
        finally:
            self._restoring = False
        self._mark_dirty()
        self._refresh()

    def _mark_dirty(self) -> None:
        if self._restoring:
            return
        if not self._dirty:
            self._dirty = True
            self.projectChanged.emit(self._project_label())

    def is_dirty(self) -> bool:
        return self._dirty

    def _project_label(self) -> str:
        name = self.project_path.name if self.project_path is not None else ""
        if not name and self.entries:
            name = tr("Untitled project")
        return ("• " + name) if (self._dirty and name) else name

    def _reset_history(self) -> None:
        self._undo.clear()
        self._redo.clear()
        self._last_snap = self._snapshot()

    def _clean_saved(self) -> None:
        self._dirty = False
        self.projectChanged.emit(self._project_label())

    def _detect(self, key: str, path: Path, card: TrackCard) -> None:
        """BPM / key detection in the background (2 tracks at a time)."""
        def _alive() -> bool:
            entry = self.entries.get(key)
            return entry is not None and entry.card is card

        def _done(analysis: object) -> None:
            if _alive():
                card.set_analysis(analysis)

        def _failed(message: str) -> None:
            if _alive():
                card.set_analysis(None, message)

        run_task(lambda: analyse_file(path), _done, _failed, pool=analysis_pool())

    def remove(self, key: str) -> None:
        if self.is_running():
            return
        entry = self.entries.pop(key, None)
        if entry is None:
            return
        self.player.stop_if_owner(key)
        if self._want is not None and self._want[0] == key:
            self._want = None
        for result in entry.all_results():
            playback.forget(result)
            result.cleanup()
        playback.forget_source(playback.Original(entry.source))
        if self._active_key == key:
            self._active_key = ""
        entry.card.setParent(None)
        entry.card.deleteLater()
        for index, other in enumerate(self.entries.values(), start=1):
            other.card.set_index(index)
        if not self._restoring:
            self._push_undo()
        self._refresh()

    def clear(self) -> None:
        for key in list(self.entries):
            self.remove(key)

    # ================================================================ state
    def is_running(self) -> bool:
        return self.worker is not None

    def _tick(self) -> int:
        self._clock += 1
        return self._clock

    def _select_shown(self, key: str) -> None:
        """The card shows the mode of its current settings when it is rendered, otherwise the
        mode it was showing (or the last one rendered). Playback follows."""
        entry = self.entries[key]
        current = entry.current(self._mode(key))
        if current is not None:
            chosen = current
        elif entry.shown is not None and entry.shown in entry.versions.values():
            chosen = entry.shown
        else:
            chosen = next(reversed(entry.versions.values()), None) if entry.versions else None
        if chosen is not entry.shown:
            entry.shown = chosen
            if chosen is not None:
                entry.touch(chosen, self._tick())
            self._follow_playback(key)

    def _export_state(self, key: str, result: TrackResult, options: ExportOptions) -> ExportState:
        record = find_export(result, options, self.track_meta(key, options))
        if record is not None:
            if not record.skipped:
                return ExportState("done", record.main)
            if options.on_conflict == "skip":
                return ExportState("skipped", record.main)
            return ExportState("none")                   # the rule changed: it can be written now
        if result.export_error:
            return ExportState("failed", error=result.export_error)
        previous = latest_export(result)
        return ExportState("stale", previous) if previous is not None else ExportState("none")

    def _needs_export(self, key: str, result: TrackResult, options: ExportOptions) -> bool:
        return self._export_state(key, result, options).kind not in ("done", "skipped")

    def _version_modes(self, entry: TrackEntry) -> List[Tuple[MasterSettings, Optional[Tuple[float, float]], bool]]:
        """(settings, cut, rendered) behind each chip: the rendered modes, then the mode saved
        in a project if it is not rendered yet."""
        modes = [(r.settings, r.cut_key(), True) for r in entry.versions.values()]
        saved = entry.saved_mode
        if saved is not None and saved.key() != self._mode(entry.card.key).key() \
                and not any(m[0].key() == saved.key() for m in modes):
            modes.append((saved, entry.card.cut(), False))
        return modes

    def _version_chips(self, entry: TrackEntry) -> Tuple[List[Tuple[str, str]], int]:
        results = list(entry.versions.values())
        modes = self._version_modes(entry)
        labels = [m[0].label for m in modes]
        chips = []
        for (settings, cut, rendered), label in zip(modes, labels):
            if labels.count(label) > 1:                  # same preset, different values
                label += f" · {settings.target_lufs:g}"
            tip = settings_text(settings)
            if cut is not None:
                label += " ✂"
                tip += " · " + tr("cut {start} → {end}", start=format_time_precise(cut[0]), end=format_time_precise(cut[1]))
            if not rendered:
                label = "○ " + label
                tip = tr("Saved in the project, not rendered yet: click to use these settings.") + "\n" + tip
            chips.append((label, tip))
        active = next((i for i, r in enumerate(results) if r is entry.shown), -1)
        return chips, active

    def _show_card(self, key: str, options: ExportOptions) -> None:
        entry = self.entries[key]
        card = entry.card
        settings = self._mode(key)
        chips, active = self._version_chips(entry)
        card.set_versions(chips, active)
        failure = entry.failure
        if failure is not None and failure.settings is not None and failure.settings.key() == settings.key() \
                and failure.cut_key() == card.cut() and entry.current(settings) is None:
            card.show_result(failure, settings)          # failed / cancelled with the current settings
            return
        result = entry.shown
        if result is None:
            card.set_waiting()
            return
        revealable = None
        for candidate in [result] + list(entry.versions.values()):
            revealable = latest_export(candidate)
            if revealable is not None:
                break
        current = entry.is_current(result, settings)
        state = self._export_state(key, result, options) if current else ExportState()
        card.show_result(result, settings, state, revealable, outdated=not current)

    def _selected_keys(self) -> List[str]:
        return [key for key, entry in self.entries.items() if entry.card.is_selected()]

    # ---- per-track mode (preset / profile, else the left panel) -----------------------
    def _mode_items(self) -> List[Tuple[str, str]]:
        items = [("", tr("Follow the left panel"))]
        items += [(f"preset:{name}", name) for name in PRESETS]
        for name in sorted(self.profiles.store.all(), key=str.lower):
            items.append((f"profile:{name}", tr("Profile: {name}", name=name)))
        return items

    def _refresh_mode_items(self) -> None:
        items = self._mode_items()
        for entry in self.entries.values():
            entry.card.set_mode_items(items)

    def _mode(self, key: str) -> MasterSettings:
        """The settings to render ``key`` with: the card's preset / profile, else the left panel."""
        token = self.entries[key].card.mode_token()
        if token.startswith("preset:"):
            name = token.split(":", 1)[1]
            if name in PRESETS:
                return MasterSettings.from_preset(name)
        elif token.startswith("profile:"):
            settings = _settings_from_profile(self.profiles.store.all().get(token.split(":", 1)[1]))
            if settings is not None:
                return settings
        return self.settings()

    def _mode_reference(self, key: str):
        """A per-track preset / profile carries no reference; Follow-panel uses the panel's."""
        settings = self._mode(key)
        return self.reference if settings.reference_id else None

    def _preview_plan(self, keys: Optional[Iterable[str]] = None) -> List[MasterJob]:
        options = self.export_options()
        wanted = set(keys) if keys is not None else None
        return [MasterJob(key, entry.source, None, self.track_meta(key, options),
                          settings=self._mode(key), reference=self._mode_reference(key),
                          export=False, cut=entry.card.cut(), analog_seed=entry.analog_seed)
                for key, entry in self.entries.items()
                if (wanted is None or key in wanted) and entry.current(self._mode(key)) is None]

    def _export_plan(self, keys: Optional[Iterable[str]] = None) -> List[MasterJob]:
        options = self.export_options()
        wanted = set(keys) if keys is not None else None
        jobs = []
        for key, entry in self.entries.items():
            if wanted is not None and key not in wanted:
                continue
            current = entry.current(self._mode(key))
            if current is not None and not self._needs_export(key, current, options):
                continue
            jobs.append(MasterJob(key, entry.source, current, self.track_meta(key, options),
                                  settings=self._mode(key), reference=self._mode_reference(key),
                                  export=True, cut=entry.card.cut(), analog_seed=entry.analog_seed))
        return jobs

    def _format_hint(self, options: ExportOptions) -> str:
        key = options.fmt_key
        needs_ffmpeg = key == PACK_KEY or FORMATS[key].needs_ffmpeg or options.clip.enabled
        if needs_ffmpeg and self.ffmpeg is None:
            return "⚠ " + tr("This export needs FFmpeg, which was not found.")
        if key in ("mp3", PACK_KEY) and self.ffmpeg is not None and not self.ffmpeg.has_mp3:
            return "⚠ " + tr("This FFmpeg build has no MP3 encoder (libmp3lame).")
        if key == PACK_KEY:
            return (tr("One folder per track: WAV 24-bit, MP3 320 kbps (ID3 tags + cover), cover.jpg, "
                       "social clip and an info sheet.") if options.clip.enabled else
                    tr("One folder per track: WAV 24-bit, MP3 320 kbps (ID3 tags + cover), cover.jpg "
                       "and an info sheet."))
        if FORMATS[key].lossy:
            return tr("Lossy format: keep a WAV or FLAC master as well.")
        return ""

    def _refresh(self) -> None:
        settings, options = self.settings(), self.export_options()
        self.preset_summary.setText(tr_engine(PRESETS[settings.preset].summary))

        # loudness: the slider or the reference
        loud_from_ref = self.reference is not None and settings.reference_id and settings.match_loudness
        self.target_slider.setEnabled(not loud_from_ref)
        target = (f"<b>{self.reference.target_lufs:.1f} LUFS</b> " + tr("(reference)") if loud_from_ref
                  else f"<b>{settings.target_lufs:g} LUFS</b>")
        extras = []
        if settings.reference_id:
            extras.append(tr("reference match"))
        if settings.trim:
            extras.append(tr("auto-trim"))
        self.settings_summary.setText(
            (tr("Custom settings") if settings.customised else tr("Preset values"))
            + f": {target} / <b>{settings.ceiling_db:g} dBTP</b> / "
            + tr("cleanse {pct}", pct=f"<b>{settings.intensity_pct}%</b>")
            + (f"<br>+ {', '.join(extras)}" if extras else ""))

        # reference section
        has_ref = self.reference is not None
        if self._reference_loading:
            self.reference_status.setText(tr("Analysing {name}…", name=Path(self._reference_loading).name))
        elif has_ref:
            r = self.reference
            self.reference_status.setText(
                f"✅ {r.name} · {r.lufs:.1f} LUFS · "
                + tr("true peak {value} dBTP", value=f"{r.true_peak_db:.1f}")
                + f" · {int(r.duration_s // 60)}:{int(r.duration_s % 60):02d}"
                + ("" if self._reference_active() else "\n" + tr("Tick an option below to use it.")))
        elif self._reference_error:
            self.reference_status.setText(self._reference_error)
        else:
            self.reference_status.setText(tr("A commercial track whose sound you like. Its tonal balance "
                                             "and loudness become the targets."))
        self.reference_clear.setEnabled(has_ref or bool(self._reference_loading))
        self.match_strength.setEnabled(self.match_eq_check.isChecked())
        self.trim_slider.setEnabled(self.trim_check.isChecked())

        # export section
        self.format_hint.setText(self._format_hint(options))
        self.tags_section.setEnabled(not options.strip_metadata)      # blank export: tags & cover unused
        self.tags_section.setToolTip(tr("Turned off while 'Export without metadata' is ticked.")
                                     if options.strip_metadata else "")
        for widget in (self.clip_length, self.clip_mode, self.video_check):
            widget.setEnabled(self.clip_check.isChecked())
        if not self._can_make_video():
            self.video_check.setEnabled(False)
            self.video_check.setToolTip(tr("Needs a cover image and an FFmpeg build with a video encoder.")
                                        if self.ffmpeg is not None and self.ffmpeg.video_encoder is None
                                        else tr("Choose a cover in 'Tags and cover' first."))
        else:
            self.video_check.setToolTip(tr("H.264 video ({encoder}) with the clip's audio.",
                                           encoder=self.ffmpeg.video_encoder))

        # track cards (those of the running batch show their progress)
        count = len(self.entries)
        self.batch_title.setText(trn("{n} track", "{n} tracks", count) if count else tr("No tracks yet"))
        for key in self.entries:
            self._select_shown(key)
            if key not in self._batch_keys:
                self._show_card(key, options)
        self._update_buttons()
        self._schedule_auto_render()

    def _update_buttons(self) -> None:
        count = len(self.entries)
        ticked = sum(1 for entry in self.entries.values() if entry.card.is_selected())
        self.batch_title.setText((trn("{n} track", "{n} tracks", count) + " · " + tr("{n} ticked", n=ticked))
                                 if count else tr("No tracks yet"))
        self.select_all_button.setVisible(bool(count))
        self.select_all_button.setText(tr("☐ Untick all") if count and ticked == count else tr("☑ Tick all"))
        self.save_project_button.setEnabled(bool(count) and not self.is_running())
        self.open_project_button.setEnabled(not self.is_running())
        self.clear_button.setEnabled(bool(count) and not self.is_running())
        if self.is_running():
            self.run_button.setText(tr("Working…"))
            self.run_button.setEnabled(False)
            self.export_all_button.setEnabled(False)
            return
        self._show_cancel(False)                          # nothing running: no Cancel button
        selected = self._selected_keys()
        previews = len(self._preview_plan(selected))
        exports = self._export_plan(selected)
        if self._reference_loading:
            label = tr("Analysing the reference…")
        elif not count:
            label = tr("🎧 Prepare the previews")
        elif not selected:
            label = tr("Tick at least one track")
        elif previews:
            label = "🎧 " + trn("Prepare {n} preview", "Prepare {n} previews", previews)
        else:
            label = tr("✓ All previews ready")
        self.run_button.setText(label)
        self.run_button.setEnabled(bool(previews) and not self._reference_loading)

        options = self.export_options()
        what = tr("release packs") if options.fmt_key == PACK_KEY else format_label(options.fmt_key)
        if not count:
            text = tr("⬇ Export all")
        elif not selected:
            text = tr("Tick at least one track")
        elif exports:
            text = "⬇ " + trn("Export {n} track as {what}", "Export {n} tracks as {what}", len(exports), what=what)
        else:
            text = tr("✓ All tracks exported")
        self.export_all_button.setText(text)
        self.export_all_button.setEnabled(bool(exports) and not self._reference_loading)
        if count and not self._last_message:
            self.batch_message.setText(tr("1. Prepare the previews · 2. Listen and compare · 3. Export"))
        elif not count and not self._last_message:
            self.batch_message.setText(tr("Add tracks to begin."))

    # ================================================================ batch
    def start(self) -> None:
        """Prepare the previews (current settings) of the ticked tracks not rendered yet."""
        if self.is_running() or self._reference_loading:
            return
        jobs = self._preview_plan(self._selected_keys())
        if jobs:
            self._run(jobs)

    def export_all(self) -> None:
        """Export the ticked tracks (rendering first those that need it)."""
        if self.is_running() or self._reference_loading:
            return
        jobs = self._export_plan(self._selected_keys())
        if jobs:
            self._run(jobs)

    def export_track(self, key: str) -> None:
        if self.is_running() or self._reference_loading or key not in self.entries:
            return
        jobs = self._export_plan([key])
        if jobs:
            self._run(jobs)

    def _check_export(self, options: ExportOptions) -> bool:
        hint = self._format_hint(options)
        if hint.startswith("⚠"):
            QMessageBox.warning(self, config.APP_NAME, hint.lstrip("⚠ ") + "\n" +
                                tr("Install FFmpeg or choose WAV / FLAC without a clip."))
            return False
        if self.cover_path and not options.tags.cover:
            QMessageBox.warning(self, config.APP_NAME,
                                tr("The cover image was not found:\n{path}", path=self.cover_path))
            return False
        folder = options.folder()
        if folder is not None:
            try:
                folder.mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                QMessageBox.warning(self, config.APP_NAME, tr("Cannot use the output folder:\n{error}", error=exc))
                return False
        return True

    def _run(self, jobs: List[MasterJob], user: bool = True) -> None:
        options = self.export_options()
        if any(job.export for job in jobs) and not self._check_export(options):
            return
        self._batch_keys = {job.key for job in jobs}
        self._batch_exports = {job.key for job in jobs if job.export}
        self._batch_auto = not user
        for job in jobs:
            self.entries[job.key].card.set_queued()
        for entry in self.entries.values():
            entry.card.set_busy(True)
        self.worker = MasteringWorker(jobs, options, config.session_work_dir(), self.ffmpeg)
        self.worker.trackProgress.connect(self._on_track_progress)
        self.worker.trackFinished.connect(self._on_track_finished)
        self.worker.batchProgress.connect(self._on_batch_progress)
        self._set_paused(False)
        self._show_cancel(True)
        self.batch_progress.setValue(0)
        self._update_buttons()
        if self.activity is not None:
            self.activity.batch_started("mastering", user)
        self.thread = start_worker(self.worker, self, self._on_batch_finished)

    def _show_cancel(self, running: bool) -> None:
        """Cancel, Pause and the progress bar are only shown while a render / export runs."""
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
        if self.worker is None:
            return
        self._set_paused(not self._paused)
        if self._paused:
            self.batch_message.setText(tr("Queue paused - the current track finishes, then it waits."))

    def cancel(self) -> None:
        if self.worker is not None:
            self.worker.cancel()
            self.cancel_button.setEnabled(False)
            self._set_paused(False)
            self.batch_message.setText(tr("Cancelling after the current step…"))

    def _on_track_progress(self, key: str, fraction: float, message: str) -> None:
        entry = self.entries.get(key)
        if entry is not None:
            entry.card.set_progress(fraction, message)

    def _on_batch_progress(self, fraction: float, message: str) -> None:
        self.batch_progress.setValue(int(max(0.0, min(1.0, fraction)) * 1000))
        self.batch_message.setText(message)

    def _discard(self, key: str, result: TrackResult) -> None:
        if result is self._playing_result:
            self.player.stop_if_owner(key)
            self._playing_result = None
        playback.forget(result)
        result.cleanup()

    def _enforce_cache_cap(self) -> None:
        """Keep the total size of the temporary renders under CACHE_CAP_BYTES by dropping the
        oldest ones that are neither shown on their card nor playing."""
        renders = []
        total = 0
        for key, entry in self.entries.items():
            for result in entry.versions.values():
                size = result.cache_size()
                total += size
                keep = result is entry.shown or result is self._playing_result
                if not keep:
                    renders.append((entry.used.get(result_key(result), 0), size, key, entry, result))
        renders.sort(key=lambda item: item[0])          # oldest use first
        for _clock, size, key, entry, result in renders:
            if total <= CACHE_CAP_BYTES:
                break
            entry.versions.pop(result_key(result), None)
            entry.used.pop(result_key(result), None)
            self._discard(key, result)
            total -= size

    def _on_track_finished(self, key: str, result: object) -> None:
        self._batch_keys.discard(key)
        entry = self.entries.get(key)
        if entry is None:
            if isinstance(result, TrackResult):
                result.cleanup()
            return
        assert isinstance(result, TrackResult)
        if result.ok:
            if entry.versions.get(result_key(result)) is not result:
                for old in entry.add(result, self._tick(), protect=(entry.shown, self._playing_result)):
                    self._discard(key, old)
            if entry.failure is not None:
                entry.failure.cleanup()
                entry.failure = None
            if entry.is_current(result, self._mode(key)) or entry.shown is None:
                if entry.shown is not result:
                    entry.shown = result
                    self._follow_playback(key)
            self._prefetch_playback(key, result)
            self._enforce_cache_cap()
        elif not result.cancelled or entry.shown is None:
            if entry.failure is not None:
                entry.failure.cleanup()
            entry.failure = result
        self._show_card(key, self.export_options())

    def _on_batch_finished(self, succeeded: int, failed: int, cancelled: bool) -> None:
        exported = self._batch_exports
        auto = self._batch_auto
        self.worker = None
        self.thread = None
        self._batch_keys = set()
        self._batch_exports = set()
        self._batch_auto = False
        for entry in self.entries.values():
            entry.card.set_busy(False)
        self.batch_progress.setValue(1000 if not cancelled else self.batch_progress.value())
        options = self.export_options()
        skipped = sum(1 for key in exported if key in self.entries and self.entries[key].shown is not None
                      and self._export_state(key, self.entries[key].shown, options).kind == "skipped")
        parts = [tr("{n} done", n=succeeded - skipped)]
        if skipped:
            parts.append(tr("{n} skipped (file already there)", n=skipped))
        if failed:
            parts.append(tr("{n} failed", n=failed))
        if cancelled:
            parts.append(tr("cancelled"))
        if auto and succeeded and not failed:
            self._last_message = tr("New mode ready: playback follows at the same moment.")
        elif exported:
            self._last_message = tr("Export finished: {details}.", details=", ".join(parts))
        else:
            self._last_message = tr("Previews ready: {details}. Listen, compare, then export.",
                                    details=", ".join(parts))
        self.batch_message.setText(self._last_message)
        self._refresh()
        if self.activity is not None:
            self.activity.batch_finished("mastering", succeeded, failed, cancelled)
        if self._auto_pending:
            self._auto_pending = False
            self._schedule_auto_render()

    # ---- automatic render of the track being listened to ----------------------------
    def _schedule_auto_render(self) -> None:
        owner = self.player.current[0]
        entry = self.entries.get(owner)
        if entry is not None and entry.shown is not None and entry.current(self._mode(owner)) is None:
            self._auto_timer.start()

    def _auto_render(self) -> None:
        """Settings changed while listening: render that track in the new mode (background)."""
        owner = self.player.current[0]
        if not owner or owner not in self.entries or self._reference_loading:
            return
        if self.is_running():
            self._auto_pending = True
            return
        jobs = self._preview_plan([owner])
        if jobs:
            self._run(jobs, user=False)

    def shutdown(self, timeout_ms: int = 20000) -> None:
        """Called when the window closes: stop the batch and wait for the thread."""
        self._auto_timer.stop()
        if self.worker is not None:
            self.worker.cancel()
        if self.thread is not None:
            self.thread.quit()
            self.thread.wait(timeout_ms)
        shutdown_pool()                               # stop the warm render process
        analysis_pool().clear()
        analysis_pool().waitForDone(timeout_ms)
        for entry in self.entries.values():
            for result in entry.all_results():
                result.cleanup()

    # ================================================================ listening
    def _ready_result(self, key: str) -> Optional[TrackResult]:
        entry = self.entries.get(key)
        if entry is None or entry.shown is None or not entry.shown.ok:
            return None
        return entry.shown

    def _can_play(self, key: str, which: str) -> bool:
        """The original can be heard as soon as the track is in the list; the master once rendered."""
        entry = self.entries.get(key)
        if entry is None:
            return False
        if which == "original":
            return entry.card._original_ok
        return self._ready_result(key) is not None

    def _item(self, key: str, which: str):
        """What a buffer is made from: the rendered result, or only the source for the original."""
        if which == "mastered":
            return self._ready_result(key)
        return playback.Original(self.entries[key].source)

    def _gain(self, key: str, which: str) -> float:
        result = self._ready_result(key)
        gain_match = self.entries[key].card.gain_match.isChecked()
        return playback.gain_db(result, which, gain_match) if result is not None else 0.0

    def _flags(self, key: str) -> Tuple[bool, bool]:
        card = self.entries[key].card
        return card.gain_match.isChecked(), card.mono_button.isChecked()

    def _loop_of(self, key: str) -> Optional[Tuple[int, int]]:
        entry = self.entries.get(key)
        return entry.card.seek.loop_range() if entry is not None else None

    def _start_moment(self, key: str, moment: Optional[int]) -> Optional[int]:
        """Where playback (re)starts: the loop start when a loop is on and ``moment`` is outside it."""
        span = self._loop_of(key)
        if span is None:
            return moment
        if moment is None or not span[0] <= moment < span[1]:
            return span[0]
        return moment

    def _set_active(self, key: str) -> None:
        """The card the keyboard shortcuts work on."""
        if key in self.entries:
            self._active_key = key

    def active_key(self) -> str:
        if self.player.current[0] in self.entries:
            return self.player.current[0]
        if self._active_key in self.entries:
            return self._active_key
        ticked = self._selected_keys()
        return ticked[0] if ticked else next(iter(self.entries), "")

    def _on_play(self, key: str, which: str) -> None:
        """Original / Master button: start that version (same moment when switching A/B),
        resume it if it is paused (from A when a loop is on and the moment is outside it),
        stop it if it is playing."""
        if not self._can_play(key, which):
            return
        if self.player.current == (key, which):
            if self.player.playing:
                self.player.stop()
            else:
                self._resume(key)
        elif self.player.is_loaded(key):
            self._start_preview(key, which)              # A/B switch: same moment, sample-accurate
        else:
            self._start_preview(key, which, self._start_moment(key, None))

    def _resume(self, key: str) -> None:
        moment = self.player.timeline_position()
        start = self._start_moment(key, moment)
        self._start_preview(key, self.player.current[1], None if start == moment else start)

    def _start_preview(self, key: str, which: str, start_ms: Optional[int] = None,
                       autoplay: bool = True) -> None:
        """Play 'original' or 'mastered' of the mode shown on the card, with its Gain Match /
        Mono settings. When this track is already loaded, playback continues at the same
        moment; ``start_ms`` jumps to a moment; ``autoplay=False`` keeps a pause.
        A buffer that is not in memory yet is loaded in the background (latest request wins);
        meanwhile what plays keeps playing."""
        if not self._can_play(key, which):
            return
        rate = self.player.output_rate()
        if not rate:
            return                                       # no sound output (errorOccurred explained why)
        item = self._item(key, which)
        mono = self.entries[key].card.mono_button.isChecked()
        gain = self._gain(key, which)
        buffer = playback.cached(item, which, rate)
        if buffer is None:
            self._want = (key, which, start_ms, item, autoplay)
            self._load_buffer(item, which, rate, wanted=True)
            return
        self._want = None
        self._active_key = key
        if start_ms is None and self.player.current == (key, which) and self.player.buffer is buffer:
            self.player.set_gain_db(gain)                # same audio: Gain Match / Mono change live
            self.player.set_mono(mono)
            if autoplay and not self.player.playing:
                self.player.resume()
        else:
            if not self.player.play(key, which, buffer, start_ms, gain_db=gain, mono=mono, autoplay=autoplay):
                return
            span = self._loop_of(key)
            self.player.set_loop(*(span if span is not None else (None, None)))
        if which == "mastered":
            self._playing_result = item
        self._schedule_auto_render()
        self._warm(key)

    def _load_buffer(self, item, which: str, rate: int, wanted: bool = False, disk_only: bool = False,
                     on_ready: Optional[Callable[[], None]] = None,
                     on_failed: Optional[Callable[[str], None]] = None) -> None:
        """Background: a listening buffer into memory (or only its disk copy, ``disk_only``)."""
        spec = (playback.item_id(item, which), rate, disk_only)
        if spec in self._in_flight:
            return
        self._in_flight.add(spec)

        def _ready(_value: object) -> None:
            self._in_flight.discard(spec)
            if on_ready is not None:
                on_ready()
            self._serve_wanted()

        def _failed(message: str) -> None:
            self._in_flight.discard(spec)
            if on_failed is not None:
                on_failed(message)
            want = self._want
            if want is not None and want[1] == which and playback.item_id(want[3], which) == spec[0]:
                self._want = None
                QMessageBox.warning(self, config.APP_NAME,
                                    tr("The preview could not be prepared:\n{error}", error=tr_engine(message)))

        job = (lambda: playback.prepare(item, which, rate)) if disk_only else \
            (lambda: playback.load(item, which, rate))
        run_task(job, _ready, _failed, pool=playback_pool(), priority=1 if wanted else 0)

    def _serve_wanted(self) -> None:
        """A buffer is ready: start the latest request if it is still valid."""
        if self._want is None:
            return
        key, which, start_ms, item, autoplay = self._want
        if key not in self.entries or (which == "mastered" and self._ready_result(key) is not item):
            self._want = None                            # the card moved on (a new request will come)
            return
        if playback.cached(item, which, self.player.output_rate()) is not None:
            self._start_preview(key, which, start_ms, autoplay)

    def _prefetch_playback(self, key: str, result: TrackResult) -> None:
        """Right after rendering: the master's listening copy on disk, so the first play and later
        switches load in a blink. The track being listened to goes to memory."""
        rate = self.player.output_rate()
        if rate and playback.cached(result, "mastered", rate) is None:
            self._load_buffer(result, "mastered", rate, disk_only=self.player.current[0] != key)

    def _warm(self, key: str) -> None:
        """While a track plays: its Original and every rendered mode's Master into memory, so
        A/B and mode switches are instant."""
        entry = self.entries.get(key)
        rate = self.player.output_rate()
        if entry is None or not rate:
            return
        original = playback.Original(entry.source)
        if entry.card._original_ok and playback.cached(original, "original", rate) is None:
            self._load_buffer(original, "original", rate)
        results = ([entry.shown] if entry.shown is not None else []) + \
            [r for r in entry.versions.values() if r is not entry.shown]
        for result in results:
            if result.ok and playback.cached(result, "mastered", rate) is None:
                self._load_buffer(result, "mastered", rate)

    def _follow_playback(self, key: str) -> None:
        """The mode, cut, Gain Match or Mono of ``key`` changed: what is loaded follows at the same
        moment (live for Gain Match / Mono; a paused track stays paused)."""
        owner, which = self.player.current
        if owner == key and self._can_play(key, which):
            self._start_preview(key, which, autoplay=self.player.playing)

    def _on_audio_device_changed(self) -> None:
        """New default output (maybe another sample rate): reload what is loaded, same moment."""
        owner = self.player.current[0]
        if owner:
            self._follow_playback(owner)

    def _on_version(self, key: str, index: int) -> None:
        """A mode chip: put that mode back in the sidebar (every track follows) and its cut on
        this card."""
        entry = self.entries.get(key)
        modes = self._version_modes(entry) if entry is not None else []
        if 0 <= index < len(modes):
            settings, cut, _rendered = modes[index]
            entry.card.set_mode_token("", emit=False)      # the chip's mode becomes the panel's
            entry.card.set_cut(cut, emit=False)
            self.apply_settings(settings)

    def _on_loop_changed(self, key: str) -> None:
        """A / B / loop switch: when the loop turns on and the playhead is already past B, it goes
        back to A at once."""
        self._active_key = key
        if self.player.current[0] != key:
            return
        span = self._loop_of(key)
        self.player.set_loop(*(span if span is not None else (None, None)))
        if span is not None and self.player.is_loaded(key):
            position = self.player.timeline_position()
            if position >= span[1] - 5:
                self.player.seek(span[0])

    def _on_home(self, key: str) -> None:
        """⏮ / R: back to A (or to the start without a loop); starts playback when idle."""
        entry = self.entries.get(key)
        if entry is None:
            return
        self._active_key = key
        start = entry.card.seek.loop_points()[0]
        target = int(start) if start is not None else 0
        if self.player.is_loaded(key):
            self.player.seek(target)
        else:
            card = entry.card
            which = card.last_which if self._can_play(key, card.last_which) else "original"
            self._start_preview(key, which, target)

    def _on_player_state(self, key: str, which: str) -> None:
        playing = self.player.playing
        if not key:
            self._playing_result = None
        for entry_key, entry in self.entries.items():
            entry.card.set_play_state(which if entry_key == key else "")
            entry.card.seek.set_playing(playing and entry_key == key)

    # ---- seek bar ------------------------------------------------------------------
    def _on_player_position(self, key: str, ms: int) -> None:
        entry = self.entries.get(key)
        if entry is not None:
            entry.card.seek.set_position(ms)

    def _on_player_playing(self, playing: bool) -> None:
        owner = self.player.current[0]
        for entry_key, entry in self.entries.items():
            entry.card.seek.set_playing(playing and entry_key == owner)

    def _on_seek(self, key: str, ms: int) -> None:
        """Click / drag on a card's timeline: jump there (starts the card's last version if idle)."""
        card = self.entries[key].card if key in self.entries else None
        if card is None:
            return
        if self.player.is_loaded(key):              # playing or paused: jump, keep the state
            self.player.seek(ms)
            return
        which = card.last_which if self._can_play(key, card.last_which) else "original"
        self._start_preview(key, which, start_ms=ms)

    def _on_pause_toggle(self, key: str) -> None:
        card = self.entries[key].card if key in self.entries else None
        if card is None:
            return
        if self.player.is_loaded(key):
            if self.player.playing:
                self.player.pause()
            else:
                self._resume(key)
        else:
            which = card.last_which if self._can_play(key, card.last_which) else "original"
            self._start_preview(key, which, self._start_moment(key, card.seek.value()))

    # ---- keyboard shortcuts ------------------------------------------------------------
    def handle_key(self, key: int) -> bool:
        """Space play/pause, Tab Original<->Master, M mono, L loop, R back to A (or 0:00),
        ← / → seek 5 s, A / B set the loop points live. Returns True when the key was used."""
        target = self.active_key()
        entry = self.entries.get(target)
        if entry is None:
            return False
        card = entry.card
        if key == Qt.Key.Key_Space:
            self._on_pause_toggle(target)
        elif key == Qt.Key.Key_Tab:
            owner, which = self.player.current
            if owner == target:
                other = "original" if which == "mastered" else "mastered"
                if self._can_play(target, other):
                    self._start_preview(target, other, autoplay=self.player.playing)
            elif self._can_play(target, "mastered"):
                card.last_which = "original" if card.last_which == "mastered" else "mastered"
        elif key == Qt.Key.Key_M:
            card.mono_button.toggle()
        elif key == Qt.Key.Key_L:
            if card.seek.loop_button.isEnabled():
                card.seek.loop_button.toggle()
        elif key == Qt.Key.Key_R:
            self._on_home(target)
        elif key in (Qt.Key.Key_Left, Qt.Key.Key_Right):
            self._nudge(target, -SEEK_STEP_MS if key == Qt.Key.Key_Left else SEEK_STEP_MS)
        elif key in (Qt.Key.Key_A, Qt.Key.Key_B):
            self._set_loop_live(target, "a" if key == Qt.Key.Key_A else "b")
        else:
            return False
        return True

    def _nudge(self, key: str, delta_ms: int) -> None:
        """← / →: move the playhead by 5 s (starts from the current moment or 0 when idle)."""
        card = self.entries[key].card
        if self.player.is_loaded(key):
            position = self.player.timeline_position()
        else:
            position = card.seek.value()
        duration = card.duration_ms() or self.player.duration_ms()
        target = max(0, int(position) + delta_ms)
        if duration:
            target = min(target, max(0, duration - 50))
        if self.player.is_loaded(key):
            self.player.seek(target)
        else:
            card.seek.set_position(target)

    def _set_loop_live(self, key: str, point: str) -> None:
        """A / B: drop a loop marker at the current moment while listening."""
        card = self.entries[key].card
        moment = self.player.timeline_position() if self.player.is_loaded(key) else card.seek.value()
        card.seek.set_loop_point(point, moment)

    def undo_action(self) -> None:
        self.undo()

    def redo_action(self) -> None:
        self.redo()

    def shortcut_key_event(self, event) -> bool:
        """Key press seen by the application filter: use it when the Mastering tab is in front
        and no text field / dialog / popup has the keyboard."""
        key = event.key()
        if not any(_same_key(key, wanted) for wanted in SHORTCUT_KEYS):
            return False
        try:
            if event.isAutoRepeat():
                return False
            modifiers = event.modifiers()
            if modifiers & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.AltModifier
                            | Qt.KeyboardModifier.MetaModifier):
                return False
        except TypeError:                                 # test doubles without real flags
            pass
        if not self.isVisible() or not self.window().isActiveWindow():
            return False
        if QApplication.activeModalWidget() is not None or QApplication.activePopupWidget() is not None:
            return False
        focus = QApplication.focusWidget()
        if isinstance(focus, (QLineEdit, QAbstractSpinBox, QTextEdit, QPlainTextEdit)):
            return False
        if isinstance(focus, QComboBox) and focus.isEditable():
            return False
        for wanted in SHORTCUT_KEYS:
            if _same_key(key, wanted):
                return self.handle_key(wanted)
        return False

    # ================================================================ projects (.htd)
    def _project_settings(self) -> dict:
        values = self._profile_snapshot()
        values.update({
            "artist": self.artist_edit.text().strip(), "album": self.album_edit.text().strip(),
            "year": self.year_edit.text().strip(), "genre": self.genre_edit.text().strip(),
            "cover": self.cover_path,
            "reference": self.reference.path if self.reference is not None else (self._reference_loading or ""),
        })
        return values

    def _apply_project_settings(self, values: dict) -> List[str]:
        """Left panel from a project; returns the files it mentions that are missing."""
        missing = []
        self._apply_profile(values)
        self._loading = True
        for edit, name in ((self.artist_edit, "artist"), (self.album_edit, "album"),
                           (self.year_edit, "year"), (self.genre_edit, "genre")):
            if isinstance(values.get(name), str):
                edit.setText(values[name])
        self._loading = False
        cover = str(values.get("cover") or "")
        if cover and not Path(cover).is_file():
            missing.append(cover)
            cover = ""
        self._set_cover(cover, save=False)
        reference = str(values.get("reference") or "")
        if reference and Path(reference).is_file():
            if self.reference is None or str(self.reference.path) != reference:
                self._load_reference(reference)
        else:
            if reference:
                missing.append(reference)
            self._clear_reference()
        self._on_setting_changed()
        return missing

    def project_data(self) -> dict:
        """The whole session as plain data (what a .htd file contains)."""
        tracks = []
        settings = self.settings()
        for key, entry in self.entries.items():
            card = entry.card
            start, end = card.seek.loop_points()
            shown = entry.shown if entry.shown is not None and entry.shown.ok else None
            mode = shown.settings if shown is not None else (entry.saved_mode or settings)
            tracks.append({
                "path": str(entry.source),
                "selected": card.is_selected(),
                "title": card.track_title(),
                "bpm": card.bpm() or 0,
                "key": card.key_name(),
                "cut": list(card.cut()) if card.cut() is not None else None,
                "loop": {"a": start, "b": end, "on": card.seek.loop_button.isChecked()},
                "gain_match": card.gain_match.isChecked(),
                "mono": card.mono_button.isChecked(),
                "mode_token": card.mode_token(),
                "mode": asdict(mode),
                "analog_seed": entry.analog_seed,
            })
        return {"format": PROJECT_FORMAT, "format_version": PROJECT_VERSION, "app": config.APP_NAME,
                "app_version": config.APP_VERSION, "settings": self._project_settings(), "tracks": tracks}

    def save_project(self, path: Optional[str] = None) -> bool:
        if not self.entries or self.is_running():
            return False
        if not path:
            start = str(self.project_path or (config.default_output_dir() / tr("My project")))
            path, _filter = QFileDialog.getSaveFileName(self, tr("Save the project"), start,
                                                        tr("Heins True Diyae projects (*.htd)"))
            if not path:
                return False
        target = Path(path)
        if target.suffix.lower() != ".htd":
            target = target.with_name(target.name + ".htd")
        data = self.project_data()
        for track in data["tracks"]:                      # also relative to the project (moved together)
            try:
                track["relative"] = os.path.relpath(track["path"], target.parent)
            except ValueError:                            # another drive (Windows)
                track["relative"] = ""
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            partial = target.with_name(target.name + ".partial")
            partial.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            partial.replace(target)
        except OSError as exc:
            QMessageBox.warning(self, config.APP_NAME, tr("The project could not be saved:\n{error}", error=exc))
            return False
        self.project_path = target
        self.store.setValue("project/last", str(target))
        self._last_message = tr("Project saved: {name}", name=target.name)
        self.batch_message.setText(self._last_message)
        self._clean_saved()
        return True

    def open_project(self, path: Optional[str] = None) -> bool:
        if self.is_running():
            return False
        if not path:
            start = str(self.project_path or self.store.value("project/last", "") or config.default_output_dir())
            path, _filter = QFileDialog.getOpenFileName(self, tr("Open a project"), start,
                                                        tr("Heins True Diyae projects (*.htd)"))
            if not path:
                return False
        source = Path(path)
        try:
            data = json.loads(source.read_text(encoding="utf-8"))
            if not isinstance(data, dict) or data.get("format") != PROJECT_FORMAT or not isinstance(data.get("tracks"), list):
                raise ValueError("not a project")
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, config.APP_NAME,
                                tr("This file is not a Heins True Diyae project:\n{path}", path=source) + f"\n({exc})")
            return False
        if self.entries:
            answer = QMessageBox.question(self, config.APP_NAME, tr("Replace the current list with this project?"),
                                          QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if answer != QMessageBox.StandardButton.Yes:
                return False
        self.player.stop()
        self._restoring = True
        try:
            self.clear()
            missing = self._apply_project_settings(data.get("settings") if isinstance(data.get("settings"), dict) else {})
            found: List[Tuple[Path, dict]] = []
            for track in data["tracks"]:
                if not isinstance(track, dict):
                    continue
                candidates = [Path(str(track.get("path", "")))]
                if track.get("relative"):
                    candidates.append(source.parent / str(track["relative"]))
                audio = next((c for c in candidates if str(c) not in ("", ".") and c.is_file()), None)
                if audio is None:
                    missing.append(str(track.get("path", "?")))
                else:
                    found.append((audio, track))
            self.add_files([audio for audio, _track in found])
            for audio, track in found:
                entry = self.entries.get(str(audio.resolve()))
                if entry is not None:
                    self._apply_track_state(entry, track)
        finally:
            self._restoring = False
        self.project_path = source
        self.store.setValue("project/last", str(source))
        self._last_message = tr("Project opened: {name}", name=source.name)
        self._reset_history()
        self._dirty = False
        self._refresh()
        self.batch_message.setText(self._last_message)
        self.projectChanged.emit(self._project_label())
        if missing:
            shown = "\n".join(f"• {name}" for name in missing[:10])
            if len(missing) > 10:
                shown += "\n" + tr("(+{n} more)", n=len(missing) - 10)
            QMessageBox.warning(self, config.APP_NAME,
                                trn("{n} file of the project was not found (moved or deleted):",
                                    "{n} files of the project were not found (moved or deleted):", len(missing))
                                + "\n" + shown)
        return True

    def _apply_track_state(self, entry: TrackEntry, track: dict) -> None:
        card = entry.card
        card.set_mode_items(self._mode_items())
        token = track.get("mode_token")
        if isinstance(token, str):
            card.set_mode_token(token, emit=False)
        card.set_selected(bool(track.get("selected", True)))
        title = track.get("title")
        if isinstance(title, str) and title.strip():
            card.title_edit.setText(title.strip())
            card._title_done()
        try:
            bpm = int(track.get("bpm") or 0)
        except (TypeError, ValueError):
            bpm = 0
        key_name = track.get("key") if isinstance(track.get("key"), str) else ""
        if bpm or key_name:
            card._set_meta_silently(max(0, min(bpm, 300)), key_name)
            card._update_status()
        cut = track.get("cut")
        new_cut = None
        if isinstance(cut, (list, tuple)) and len(cut) == 2:
            try:
                new_cut = (float(cut[0]), float(cut[1]))
            except (TypeError, ValueError):
                new_cut = None
        card.set_cut(new_cut, emit=False)                # None clears the cut (needed by undo)
        loop = track.get("loop") if isinstance(track.get("loop"), dict) else {}
        a, b = loop.get("a"), loop.get("b")
        card.seek.set_loop_state(int(a) if isinstance(a, (int, float)) else None,
                                 int(b) if isinstance(b, (int, float)) else None, bool(loop.get("on")))
        card.gain_match.setChecked(bool(track.get("gain_match", False)))
        card.mono_button.setChecked(bool(track.get("mono", False)))
        if "mode" in track:
            entry.saved_mode = _settings_from(track.get("mode"))
        seed = parse_analog_seed(track.get("analog_seed"))
        if seed is not None:                             # absent (pre-2.2.2 project): keep the new seed
            entry.analog_seed = seed

    def _on_analysis(self, key: str) -> None:
        result = self._ready_result(key)
        if result is None:
            return
        card = self.entries[key].card
        dialog = AnalysisDialog(result, self, card.bpm(), card.key_name(), card.analysis)
        self._dialogs = [d for d in self._dialogs if d.isVisible()] + [dialog]
        dialog.show()

    def _on_reveal(self, key: str) -> None:
        entry = self.entries.get(key)
        if entry is None:
            return
        options = self.export_options()
        path = None
        if entry.shown is not None and entry.shown.ok:
            record = find_export(entry.shown, options, self.track_meta(key, options))
            if record is not None and not record.skipped:
                path = record.main
        for result in ([entry.shown] if entry.shown else []) + list(entry.versions.values()):
            if path is None:
                path = latest_export(result)
        if path is not None:
            reveal_in_file_manager(path)

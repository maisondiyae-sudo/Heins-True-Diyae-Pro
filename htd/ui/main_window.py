"""
Main window: header (logo, name, companion = phrase bubble + mascot, language
switch, FFmpeg status) + one tab per tool.

Adding a tool later = write a QWidget with a TITLE attribute (English, it is
translated) and an optional ``shutdown()`` method, and add a factory to
``tool_factories()``. Tools that run batches call ``context.activity``
(batch_started / batch_finished) and the mascot reacts on its own.
"""

from __future__ import annotations

from typing import Callable, List, Optional

from PySide6.QtCore import QSettings, Qt, QTimer
from PySide6.QtGui import QCloseEvent, QIcon, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from .. import config
from ..engine.ffmpeg_tools import FfmpegInfo
from .activity import ActivityHub
from .companion import CompanionPanel
from . import fonts
from .converter_tab import ConverterTab
from .language_switch import LanguageSwitch
from .mastering_tab import MasteringTab
from .player import PreviewPlayer
from .translate import N_, bind, bind_call, init_language, on_language_changed, tr
from .widgets import Pill, logo_pixmap, spaced


class AppContext:
    """Shared services handed to every tool tab."""

    def __init__(self, ffmpeg: Optional[FfmpegInfo], settings: Optional[QSettings] = None) -> None:
        self.ffmpeg = ffmpeg
        self.settings = settings or QSettings(config.ORG_NAME, config.APP_NAME)
        fonts.apply_language(init_language(self.settings, only_once=True))   # main.py normally did it already
        self.player = PreviewPlayer()
        self.activity = ActivityHub()
        self.player.playingChanged.connect(self.activity.set_listening)    # the mascot dances while you listen


def tool_factories() -> List[Callable[[AppContext], QWidget]]:
    """The tabs, in order. Add new tools here."""
    return [
        lambda ctx: MasteringTab(ctx.ffmpeg, ctx.player, ctx.settings, activity=ctx.activity),
        lambda ctx: ConverterTab(ctx.ffmpeg, ctx.settings, activity=ctx.activity),
    ]


class MainWindow(QMainWindow):
    def __init__(self, context: AppContext) -> None:
        super().__init__()
        self.context = context
        self._companion_started = False
        self._about = None
        fonts.install()                                  # script fonts + right-to-left for Arabic
        self.setWindowTitle(config.APP_NAME)
        self.setWindowIcon(QIcon(logo_pixmap(256)))
        self.resize(1360, 900)
        self.setMinimumSize(1080, 700)

        root = QWidget()
        root.setObjectName("Root")
        layout = QVBoxLayout(root)
        layout.setContentsMargins(24, 14, 24, 18)
        layout.setSpacing(12)
        layout.addLayout(self._build_header())

        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        self.tools: List[QWidget] = []
        self.project_name = ""
        for factory in tool_factories():
            tool = factory(context)
            self.tools.append(tool)
            index = self.tabs.addTab(tool, "")
            title = getattr(tool, "TITLE", tool.__class__.__name__)
            bind_call(self.tabs, lambda text, i=index: self.tabs.setTabText(i, text), title)
            changed = getattr(tool, "projectChanged", None)
            if changed is not None:
                changed.connect(self._on_project_changed)
        layout.addWidget(self.tabs, 1)
        self.setCentralWidget(root)

        context.player.errorOccurred.connect(lambda message: self.statusBar().showMessage(message, 8000))
        QShortcut(QKeySequence(QKeySequence.StandardKey.HelpContents), self).activated.connect(self.show_help)
        QShortcut(QKeySequence("F1"), self).activated.connect(self.show_help)
        geometry = context.settings.value("window/geometry")
        if geometry is not None:
            self.restoreGeometry(geometry)
        index = int(context.settings.value("window/tab", 0) or 0)
        self.tabs.setCurrentIndex(min(max(index, 0), self.tabs.count() - 1))

    def _build_header(self) -> QHBoxLayout:
        header = QHBoxLayout()
        header.setSpacing(14)
        logo = QLabel()
        logo.setPixmap(logo_pixmap(56))
        logo.setFixedSize(60, 60)
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        titles = QVBoxLayout()
        titles.setSpacing(2)
        kicker = bind(QLabel(), "CLEAN · MASTER · CONVERT")
        kicker.setObjectName("Kicker")
        spaced(kicker, 1.8)
        title = QLabel('Heins True Diyae <span style="color:#0a84ff;">Pro</span>')
        title.setObjectName("AppTitle")
        title.setTextFormat(Qt.TextFormat.RichText)
        tagline = bind(QLabel(), config.APP_TAGLINE)
        tagline.setObjectName("Tagline")
        titles.addStretch(1)
        titles.addWidget(kicker)
        titles.addWidget(title)
        titles.addWidget(tagline)
        titles.addStretch(1)
        header.addWidget(logo, 0, Qt.AlignmentFlag.AlignVCenter)
        header.addLayout(titles)

        # companion: top right of the logo / title block, fixed maximum size
        self.companion = CompanionPanel(self.context.activity, self.context.settings)
        header.addWidget(self.companion, 1, Qt.AlignmentFlag.AlignVCenter)

        # language + status column
        side = QVBoxLayout()
        side.setSpacing(6)
        lang_row = QHBoxLayout()
        lang_row.addStretch(1)
        self.language_switch = LanguageSwitch(self.context.settings)
        lang_row.addWidget(self.language_switch)
        status_row = QHBoxLayout()
        status_row.setSpacing(8)
        self.help_button = QPushButton("?")
        self.help_button.setObjectName("HelpButton")
        self.help_button.setFixedSize(26, 26)
        bind_call(self.help_button, lambda text: self.help_button.setToolTip(f"{text}  (F1)"),
                  N_("Shortcuts, licence and logs"))
        self.help_button.clicked.connect(self.show_help)
        self.ffmpeg_pill = Pill("", "idle")
        version = QLabel(f"v{config.APP_VERSION}")
        version.setObjectName("Meta")
        bind_call(version, lambda edition: version.setText(f"v{config.APP_VERSION} · {edition}"),
                  N_("Free & Open Edition"))             # config.APP_EDITION, translated
        signature = QLabel("")
        signature.setObjectName("Meta")
        signature.setAlignment(Qt.AlignmentFlag.AlignRight)
        bind_call(signature, lambda by: signature.setText(f"{by} {config.APP_AUTHOR}"), N_("by"))
        status_row.addStretch(1)
        status_row.addWidget(self.help_button)
        status_row.addWidget(self.ffmpeg_pill)
        status_row.addWidget(version)
        side.addStretch(1)
        side.addLayout(lang_row)
        side.addLayout(status_row)
        side.addWidget(signature)
        side.addStretch(1)
        header.addLayout(side)
        self._update_ffmpeg_pill()
        on_language_changed(lambda _code: self._update_ffmpeg_pill(), self)
        return header

    def _update_ffmpeg_pill(self) -> None:
        ffmpeg = self.context.ffmpeg
        if ffmpeg is None:
            self.ffmpeg_pill.set_state("error", tr("FFmpeg missing"))
            self.ffmpeg_pill.setToolTip(tr("M4A input and MP3 / M4A export need FFmpeg.\n"
                                           "macOS: brew install ffmpeg\nWindows: winget install Gyan.FFmpeg\n"
                                           "or: pip install imageio-ffmpeg"))
        else:
            self.ffmpeg_pill.set_state("ok" if ffmpeg.has_mp3 else "warn", f"FFmpeg {ffmpeg.short_version}")
            self.ffmpeg_pill.setToolTip(tr("{path}\nfound via {source}", path=ffmpeg.path, source=ffmpeg.source)
                                        + ("" if ffmpeg.has_mp3 else "\n" + tr("No MP3 encoder in this build.")))

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        if not self._companion_started:          # hatch once the window is really on screen
            self._companion_started = True
            QTimer.singleShot(350, self.companion.start)

    def open_project(self, path: str) -> bool:
        """Open a .htd project (command line, Finder / Explorer "Open with")."""
        for index, tool in enumerate(self.tools):
            opener = getattr(tool, "open_project", None)
            if callable(opener):
                self.tabs.setCurrentIndex(index)
                return bool(opener(path))
        return False

    def _on_project_changed(self, name: str) -> None:
        self.project_name = name
        self.setWindowTitle(f"{name} - {config.APP_NAME}" if name else config.APP_NAME)

    def show_help(self) -> None:
        from .about import AboutDialog

        if self._about is None or not self._about.isVisible():
            self._about = AboutDialog(self)
        self._about.show()
        self._about.raise_()

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802
        busy = [tool for tool in self.tools if getattr(tool, "worker", None) is not None]
        if busy:
            answer = QMessageBox.question(
                self, config.APP_NAME, tr("A batch is still running. Stop it and quit?"),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
        for tool in self.tools:                          # unsaved project? ask before quitting
            if getattr(tool, "is_dirty", lambda: False)():
                answer = QMessageBox.question(
                    self, config.APP_NAME, tr("Save the changes to the project before quitting?"),
                    QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard
                    | QMessageBox.StandardButton.Cancel)
                if answer == QMessageBox.StandardButton.Cancel:
                    event.ignore()
                    return
                if answer == QMessageBox.StandardButton.Save and not tool.save_project():
                    event.ignore()                       # the save was cancelled
                    return
        self.context.player.shutdown()                  # stops playback, releases the sound device
        for tool in self.tools:
            shutdown = getattr(tool, "shutdown", None)
            if callable(shutdown):
                shutdown()
        self.context.settings.setValue("window/geometry", self.saveGeometry())
        self.context.settings.setValue("window/tab", self.tabs.currentIndex())
        event.accept()

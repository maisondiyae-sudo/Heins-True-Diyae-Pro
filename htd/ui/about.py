"""Help & About window: keyboard shortcuts, licence (GPL-3.0 + third-party notices),
author, and a button to open the logs folder for bug reports."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from .. import config
from .. import logging_setup
from .translate import tr

# (key combination, what it does) - the key column is shown verbatim, the text is translated
SHORTCUTS = [
    ("Space", "Play / pause"),
    ("Tab", "Switch Original / Master (same moment)"),
    ("M", "Mono on / off"),
    ("L", "Loop on / off"),
    ("A / B", "Set the loop start / end at the current moment"),
    ("R", "Back to A (or to the start when there is no loop)"),
    ("← / →", "Move 5 seconds back / forward"),
    ("Ctrl+Z / Ctrl+Y", "Undo / redo (ticks, cuts, modes, titles, track list)"),
    ("Ctrl+S / Ctrl+O", "Save / open a project (.htd)"),
    ("F1", "This window"),
]


def _open_folder(path: Path) -> None:
    try:
        if os.name == "nt":
            os.startfile(str(path))  # noqa: S606 - opening the user's own folder
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(path)])
        else:
            subprocess.Popen(["xdg-open", str(path)])
    except OSError:
        pass


def _scroll(widget: QWidget) -> QScrollArea:
    area = QScrollArea()
    area.setWidgetResizable(True)
    area.setWidget(widget)
    return area


class AboutDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("Help & About - {app}", app=config.APP_NAME))
        self.setMinimumSize(560, 520)
        layout = QVBoxLayout(self)

        header = QLabel(
            f'<div style="font-size:18px;font-weight:700;">Heins True Diyae '
            f'<span style="color:#0a84ff;">Pro</span></div>'
            f'<div style="color:#46516a;">v{config.APP_VERSION} · {tr("Free & Open Edition")}<br>'
            f'{tr("by")} {config.APP_AUTHOR}<br>{config.APP_COPYRIGHT}</div>')
        header.setTextFormat(Qt.TextFormat.RichText)
        layout.addWidget(header)

        tabs = QTabWidget()
        tabs.addTab(_scroll(self._shortcuts_tab()), tr("Shortcuts"))
        tabs.addTab(_scroll(self._licence_tab()), tr("Licence"))
        layout.addWidget(tabs, 1)

        buttons = QHBoxLayout()
        self.logs_button = QPushButton(tr("Open the logs folder"))
        self.logs_button.clicked.connect(lambda: _open_folder(config.log_dir()))
        self.log_hint = QLabel(tr("Attach {file} to a bug report.", file=logging_setup.log_file().name))
        self.log_hint.setObjectName("Meta")
        close = QPushButton(tr("Close"))
        close.clicked.connect(self.accept)
        buttons.addWidget(self.logs_button)
        buttons.addWidget(self.log_hint, 1)
        buttons.addWidget(close)
        layout.addLayout(buttons)

    def _shortcuts_tab(self) -> QWidget:
        body = QWidget()
        grid = QVBoxLayout(body)
        grid.setSpacing(6)
        grid.addWidget(QLabel(tr("Keyboard shortcuts (disabled while typing in a field):")))
        for keys, text in SHORTCUTS:
            row = QHBoxLayout()
            key_label = QLabel(keys)
            key_label.setObjectName("ShortcutKey")
            key_label.setMinimumWidth(130)
            row.addWidget(key_label)
            row.addWidget(QLabel(tr(text)), 1)
            grid.addLayout(row)
        grid.addStretch(1)
        return body

    def _licence_tab(self) -> QWidget:
        body = QWidget()
        box = QVBoxLayout(body)
        text = QLabel(tr(
            "Heins True Diyae Pro is free software under the GNU General Public License v3 "
            "(GPL-3.0), because its mastering chain uses pedalboard (GPL-3.0). You may use, "
            "study, share and modify it; if you distribute it, share the source under the same "
            "licence.") + "\n\n" + tr(
            "It also builds on PySide6/Qt (LGPL-3.0), NumPy, SciPy, librosa, soundfile, "
            "pyloudnorm, Matplotlib, Pillow, sounddevice/PortAudio and FFmpeg. The full list "
            "and the FFmpeg source offer are in THIRD_PARTY_NOTICES.md next to the app.") + "\n\n"
            + f"{config.APP_COPYRIGHT}")
        text.setWordWrap(True)
        text.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        box.addWidget(text)
        notices = _find_notice()
        if notices is not None:
            open_button = QPushButton(tr("Open the full notices (THIRD_PARTY_NOTICES.md)"))
            open_button.clicked.connect(lambda: _open_folder(notices.parent))
            box.addWidget(open_button, 0, Qt.AlignmentFlag.AlignLeft)
        box.addStretch(1)
        return body


def _find_notice() -> "Path | None":
    for base in (config.resource_dir(), config.resource_dir().parent):
        candidate = base / "THIRD_PARTY_NOTICES.md"
        if candidate.is_file():
            return candidate
    return None

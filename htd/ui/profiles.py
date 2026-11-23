"""
Favourite settings ("profiles"): save the current combination (mode / preset,
recipe, Anti-Parasite, auto-trim, reference options, export format, release
pack / clip options, output folder and conflict policy) under a name and
recall it in one click. Stored locally in the app's QSettings as JSON.

The tab provides two callables: ``snapshot() -> dict`` and ``apply(dict)``.
"""

from __future__ import annotations

import json
from typing import Callable, Dict, Optional

from PySide6.QtCore import QSettings, Signal
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QInputDialog, QLineEdit, QMessageBox, QPushButton, QWidget

from .. import config
from .translate import N_, bind_tip, on_language_changed, tr

STORE_KEY = "profiles/all"


class ProfileStore:
    def __init__(self, settings: QSettings) -> None:
        self.settings = settings

    def all(self) -> Dict[str, dict]:
        raw = self.settings.value(STORE_KEY, "")
        try:
            data = json.loads(raw) if raw else {}
        except (TypeError, ValueError):
            data = {}
        return {str(name): dict(values) for name, values in data.items() if isinstance(values, dict)}

    def _write(self, data: Dict[str, dict]) -> None:
        self.settings.setValue(STORE_KEY, json.dumps(data, ensure_ascii=False, sort_keys=True))

    def save(self, name: str, values: dict) -> None:
        data = self.all()
        data[name] = dict(values)
        self._write(data)

    def rename(self, old: str, new: str) -> None:
        data = self.all()
        if old in data and new and new != old:
            data[new] = data.pop(old)
            self._write(data)

    def delete(self, name: str) -> None:
        data = self.all()
        if data.pop(name, None) is not None:
            self._write(data)


class ProfileBar(QWidget):
    """[ profile ▾ ] [💾] [✏️] [🗑]  - choosing a profile applies it at once."""

    profileApplied = Signal(str)
    profilesChanged = Signal()           # a profile was saved, renamed or deleted

    def __init__(self, settings: QSettings, snapshot: Callable[[], dict], apply: Callable[[dict], None],
                 parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.store = ProfileStore(settings)
        self._snapshot, self._apply = snapshot, apply
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(4)
        self.combo = QComboBox()
        self.combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.combo.setMinimumContentsLength(8)          # long names never push the buttons out of view
        bind_tip(self.combo, "Choose a profile to apply its settings")
        self.save_button = QPushButton("💾")
        self.rename_button = QPushButton("✏️")
        self.delete_button = QPushButton("🗑")
        for button, tip in ((self.save_button, N_("Save the current settings as a profile")),
                            (self.rename_button, N_("Rename the selected profile")),
                            (self.delete_button, N_("Delete the selected profile"))):
            button.setObjectName("MiniButton")
            button.setFixedWidth(34)
            bind_tip(button, tip)
        row.addWidget(self.combo, 1)
        row.addWidget(self.save_button)
        row.addWidget(self.rename_button)
        row.addWidget(self.delete_button)
        self._filling = False
        self.reload()
        self.combo.currentIndexChanged.connect(self._on_choice)
        self.save_button.clicked.connect(self.save_current)
        self.rename_button.clicked.connect(self.rename_selected)
        self.delete_button.clicked.connect(self.delete_selected)
        on_language_changed(lambda _code: self.reload(self.selected()), self)

    # ---- list -------------------------------------------------------------------
    def selected(self) -> str:
        return self.combo.currentData() or ""

    def reload(self, select: str = "") -> None:
        self._filling = True
        self.combo.clear()
        self.combo.addItem(tr("— My profiles —"), "")
        for name in sorted(self.store.all(), key=str.lower):
            self.combo.addItem(name, name)
        index = self.combo.findData(select) if select else 0
        self.combo.setCurrentIndex(max(0, index))
        self._filling = False
        has = bool(self.selected())
        self.rename_button.setEnabled(has)
        self.delete_button.setEnabled(has)

    def _on_choice(self, _index: int) -> None:
        if self._filling:
            return
        name = self.selected()
        self.rename_button.setEnabled(bool(name))
        self.delete_button.setEnabled(bool(name))
        if name:
            values = self.store.all().get(name)
            if values is not None:
                self._apply(values)
                self.profileApplied.emit(name)

    # ---- actions ------------------------------------------------------------------
    def _ask_name(self, title: str, default: str) -> str:
        text, accepted = QInputDialog.getText(self, title, tr("Profile name:"), QLineEdit.EchoMode.Normal, default)
        return text.strip() if accepted else ""

    def save_current(self) -> None:
        name = self._ask_name(tr("Save profile"), self.selected() or tr("My settings"))
        if not name:
            return
        if name in self.store.all() and name != self.selected():
            answer = QMessageBox.question(self, config.APP_NAME, tr("Replace the profile “{name}”?", name=name),
                                          QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if answer != QMessageBox.StandardButton.Yes:
                return
        self.store.save(name, self._snapshot())
        self.reload(name)
        self.profilesChanged.emit()

    def rename_selected(self) -> None:
        old = self.selected()
        if not old:
            return
        new = self._ask_name(tr("Rename profile"), old)
        if new and new != old:
            self.store.rename(old, new)
            self.reload(new)
            self.profilesChanged.emit()

    def delete_selected(self) -> None:
        name = self.selected()
        if not name:
            return
        answer = QMessageBox.question(self, config.APP_NAME, tr("Delete the profile “{name}”?", name=name),
                                      QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if answer == QMessageBox.StandardButton.Yes:
            self.store.delete(name)
            self.reload()
            self.profilesChanged.emit()

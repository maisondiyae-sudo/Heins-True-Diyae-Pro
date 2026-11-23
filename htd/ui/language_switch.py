"""Language menu (each language written in its own script): changes the interface live
and remembers the choice."""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QWidget

from ..i18n import LANGUAGES
from .translate import bind_tip, language, on_language_changed, set_language


class LanguageSwitch(QWidget):
    def __init__(self, store: QSettings, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.store = store
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        icon = QLabel("🌐")
        icon.setObjectName("LangIcon")
        self.combo = QComboBox()
        self.combo.setObjectName("LangCombo")
        for code, native in LANGUAGES.items():
            self.combo.addItem(f"{native}  ·  {code.upper()}", code)
        layout.addWidget(icon)
        layout.addWidget(self.combo)
        bind_tip(self, "Interface language")
        bind_tip(self.combo, "Interface language")
        self._sync()
        self.combo.currentIndexChanged.connect(self._on_choice)
        on_language_changed(lambda _code: self._sync(), self)

    def select(self, code: str) -> None:
        index = self.combo.findData(code)
        if index >= 0:
            self.combo.setCurrentIndex(index)

    def _on_choice(self, _index: int) -> None:
        code = self.combo.currentData()
        if code and code != language():
            set_language(code, self.store)

    def _sync(self) -> None:
        index = self.combo.findData(language())
        if index >= 0 and index != self.combo.currentIndex():
            self.combo.blockSignals(True)
            self.combo.setCurrentIndex(index)
            self.combo.blockSignals(False)

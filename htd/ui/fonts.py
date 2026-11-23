"""
Fonts and text direction per language.

Qt picks, for every character, the first family of the list that has the
glyph. The list starts with the system UI font (so Latin / Cyrillic text keeps
its usual look), followed by the fonts that draw the language's script on
Windows and macOS (plus the Noto fallbacks found on Linux). Choosing the
Japanese fonts before the Chinese ones matters: the same Han characters are
drawn differently in each language.

Arabic switches the whole interface to right-to-left (Qt mirrors the layouts);
the seek bars and numbers stay left-to-right.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication

from ..i18n import is_rtl
from .translate import on_language_changed

SCRIPT_FAMILIES: Dict[str, List[str]] = {
    "zh": ["Microsoft YaHei UI", "Microsoft YaHei", "PingFang SC", "Hiragino Sans GB",
           "Noto Sans CJK SC", "Source Han Sans SC"],
    "ja": ["Yu Gothic UI", "Meiryo UI", "Meiryo", "Hiragino Sans", "Hiragino Kaku Gothic ProN",
           "Noto Sans CJK JP", "Source Han Sans JP"],
    "hi": ["Nirmala UI", "Kohinoor Devanagari", "Devanagari Sangam MN", "Noto Sans Devanagari", "Mangal"],
    "ar": ["Segoe UI", "SF Arabic", "Geeza Pro", "Noto Sans Arabic", "Tahoma"],
    "ru": [],                 # the system UI fonts already cover Cyrillic
}
# every script as a last resort (mixed text: file names, phrases quoting other languages...)
LAST_RESORT = ["Segoe UI Symbol", "Noto Sans", "Arial Unicode MS"]

_base_font: Optional[QFont] = None


def families_for(code: str, base_family: str) -> List[str]:
    families = [base_family] + SCRIPT_FAMILIES.get(code, [])
    for others in SCRIPT_FAMILIES.values():          # other scripts after the language's own
        families += [f for f in others if f not in families]
    return families + [f for f in LAST_RESORT if f not in families]


def apply_language(code: str) -> None:
    """Application font families + layout direction for ``code`` (call after each switch)."""
    global _base_font
    app = QApplication.instance()
    if app is None:
        return
    if _base_font is None:
        _base_font = QFont(app.font())                # the system UI font, captured once
    font = QFont(_base_font)
    font.setFamilies(families_for(code, _base_font.family()))
    app.setFont(font)
    app.setLayoutDirection(Qt.LayoutDirection.RightToLeft if is_rtl(code)
                           else Qt.LayoutDirection.LeftToRight)


_installed = False


def install() -> None:
    """Follow the language switches (once, before the widgets connect their own updates)."""
    global _installed
    if not _installed:
        _installed = True
        on_language_changed(apply_language)

"""
Interface languages (no Qt here).

Source strings are written in English directly in the code and wrapped in
``tr()`` (gettext style): the English text *is* the key. French is a plain
dictionary {English: French} (``fr.py``); Spanish, Chinese, Japanese, Hindi,
Arabic and Russian share one table (``world.py``, one row per English text).
A missing translation automatically falls back to the English text.

    tr("Master {n} tracks", n=3)
    trn("{n} track", "{n} tracks", count)          # plural forms
    N_("Preset")                                    # mark only: translated later

The Qt side (live switching, widget bindings) is in htd/ui/translate.py.
"""

from __future__ import annotations

import locale
import os
import re
from typing import Dict, List, Pattern, Set, Tuple

from .fr import FR, FR_ENGINE_PATTERNS
from .world import WORLD_TABLES

# code -> name written in that language (shown as-is in the language menu)
LANGUAGES: Dict[str, str] = {
    "fr": "Français", "en": "English", "es": "Español", "zh": "中文",
    "ja": "日本語", "hi": "हिन्दी", "ar": "العربية", "ru": "Русский",
}
RTL_LANGUAGES = {"ar"}
NO_LETTER_SPACING = {"ar", "hi"}           # joined scripts: extra letter spacing breaks them
SOURCE_LANGUAGE = "en"

_TABLES: Dict[str, Dict[str, str]] = {"en": {}, "fr": FR, **WORLD_TABLES}
_PATTERNS: Dict[str, List[Tuple[Pattern, str]]] = {
    "fr": [(re.compile(pattern, re.DOTALL), template) for pattern, template in FR_ENGINE_PATTERNS],
}
_current = SOURCE_LANGUAGE
MISSING: Set[str] = set()          # translations looked up but not found (for tests / dev)


def detect_language(system_name: str = "") -> str:
    """'fr' when the system (or ``system_name``, e.g. QLocale.system().name()) is French."""
    candidates = [system_name, os.environ.get("LANG", ""), os.environ.get("LC_ALL", "")]
    try:
        candidates.append(locale.getlocale()[0] or "")
    except (ValueError, TypeError):
        pass
    windows_names = {"french": "fr", "spanish": "es", "chinese": "zh", "japanese": "ja",
                     "hindi": "hi", "arabic": "ar", "russian": "ru", "english": "en"}
    for name in candidates:
        code = (name or "").replace("-", "_").split("_")[0].split(".")[0].lower()
        code = windows_names.get(code, code)
        if code in LANGUAGES:
            return code
    return SOURCE_LANGUAGE


def set_language(code: str) -> str:
    """Switch the language; unknown codes fall back to English. Returns the active code."""
    global _current
    _current = code if code in _TABLES else SOURCE_LANGUAGE
    return _current


def language() -> str:
    return _current


def _lookup(text: str, record: bool) -> str:
    if _current == SOURCE_LANGUAGE or not text:
        return text
    translated = _TABLES[_current].get(text)
    if translated:
        return translated
    if record:
        MISSING.add(text)
    return text


def _format(template: str, source: str, kwargs: dict) -> str:
    if not kwargs:
        return template
    try:
        return template.format(**kwargs)
    except (KeyError, IndexError, ValueError):     # a broken translation never breaks the UI
        return source.format(**kwargs)


def tr(text: str, **kwargs) -> str:
    """Translated ``text`` (English when no translation exists), formatted with ``kwargs``."""
    return _format(_lookup(text, True), text, kwargs)


def tr_quiet(text: str, **kwargs) -> str:
    """Like tr() for texts that may legitimately have no translation (engine messages)."""
    return _format(_lookup(text, False), text, kwargs)


def is_rtl(code: str = "") -> bool:
    return (code or _current) in RTL_LANGUAGES


def script_allows_spacing(code: str = "") -> bool:
    return (code or _current) not in NO_LETTER_SPACING


def trn(singular: str, plural: str, n: int, **kwargs) -> str:
    """Plural-aware tr(): French uses the singular for 0 and 1, English (and the
    others) only for 1. Russian / Arabic translations use count-first wordings
    ("Pistes : 3") that work for every number."""
    use_plural = n > 1 if _current == "fr" else n != 1
    source = plural if use_plural else singular
    return _format(_lookup(source, True), source, {"n": n, **kwargs})


def N_(text: str) -> str:              # noqa: N802 - gettext convention
    """Marks a string for translation without translating it (it is translated where it is shown)."""
    return text


def tr_engine(message: str) -> str:
    """Messages coming from the engine (errors, warnings, progress): exact translation,
    else a pattern that keeps the numbers / names, else the English message."""
    if _current == SOURCE_LANGUAGE or not message:
        return message
    exact = _TABLES[_current].get(message)
    if exact:
        return exact
    for pattern, template in _PATTERNS.get(_current, ()):
        match = pattern.fullmatch(message)
        if match:
            parts = {name: (tr_engine(value) if name.startswith("msg") else value)
                     for name, value in match.groupdict().items()}
            return template.format(**parts)
    return message


# note names (C D E F G A B) and the words for major / minor, per language
_NOTE_NAMES = {
    "fr": (("Do", "Ré", "Mi", "Fa", "Sol", "La", "Si"), "{note} majeur", "{note} mineur"),
    "es": (("Do", "Re", "Mi", "Fa", "Sol", "La", "Si"), "{note} mayor", "{note} menor"),
    "ru": (("До", "Ре", "Ми", "Фа", "Соль", "Ля", "Си"), "{note} мажор", "{note} минор"),
    "ar": (("دو", "ري", "مي", "فا", "صول", "لا", "سي"), "{note} الكبير", "{note} الصغير"),
    "zh": (None, "{note} 大调", "{note} 小调"),
    "ja": (None, "{note} メジャー", "{note} マイナー"),
    "hi": (None, "{note} मेजर", "{note} माइनर"),
    "en": (None, "{note} major", "{note} minor"),
}


def key_name(short: str) -> str:
    """'Cm' -> 'C minor' / 'Do mineur' / 'Do menor' / 'C 小调'...; '' stays ''."""
    if not short:
        return ""
    minor = short.endswith("m")
    tonic = short[:-1] if minor else short
    names, major_fmt, minor_fmt = _NOTE_NAMES.get(_current, _NOTE_NAMES["en"])
    note = tonic
    if names is not None and tonic[:1] in "CDEFGAB":
        accidental = tonic[1:]
        if _current in ("ar", "ru"):                     # no Latin letters inside the word
            accidental = accidental.replace("#", "♯").replace("b", "♭")
        note = names["CDEFGAB".index(tonic[:1])] + accidental
    return (minor_fmt if minor else major_fmt).format(note=note)


def group_thousands(value: int) -> str:
    """44100 -> '44,100' / '44 100' (fr, ru) / '44.100' (es)."""
    text = f"{int(value):,}"
    return text.replace(",", {"fr": "\u202f", "ru": "\u202f", "es": "."}.get(_current, ","))

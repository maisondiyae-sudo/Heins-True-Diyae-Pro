"""
Live language switching for the Qt interface.

Two mechanisms, both cheap:

* ``bind(widget, "English text")`` sets the translated text now and again
  after every language change (labels, buttons, tooltips, tab titles...).
* ``on_language_changed(slot)`` for texts computed on the fly (status lines,
  run button labels): the slot recomputes them with ``tr()``.

Bindings whose widget has been deleted are dropped automatically.
"""

from __future__ import annotations

from typing import Callable, List, Optional, Tuple

from PySide6.QtCore import QObject, QSettings, Signal

from .. import i18n
from ..i18n import N_, tr, tr_quiet, trn  # noqa: F401  (re-exported for the UI modules)

try:                                        # real PySide6: is the C++ object still alive?
    from shiboken6 import isValid as _is_alive
except ImportError:                         # pragma: no cover - test doubles
    def _is_alive(obj) -> bool:
        return not getattr(obj, "_deleted", False)

SETTINGS_KEY = "ui/language"


class Translator(QObject):
    languageChanged = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self._bindings: List[Tuple[QObject, Callable[[str], None], str, dict]] = []

    # ---- bindings ----------------------------------------------------------
    def add(self, owner: QObject, apply: Callable[[str], None], text: str, kwargs: dict) -> None:
        self._bindings.append((owner, apply, text, kwargs))
        apply(tr(text, **kwargs))
        if len(self._bindings) % 256 == 0:
            self._prune()

    def _prune(self) -> None:
        self._bindings = [b for b in self._bindings if _is_alive(b[0])]

    def reapply(self) -> None:
        alive = []
        for owner, apply, text, kwargs in self._bindings:
            if not _is_alive(owner):
                continue
            try:
                apply(tr(text, **kwargs))
            except RuntimeError:            # deleted between the check and the call
                continue
            alive.append((owner, apply, text, kwargs))
        self._bindings = alive

    # ---- language ----------------------------------------------------------
    def set_language(self, code: str, store: Optional[QSettings] = None) -> None:
        previous = i18n.language()
        active = i18n.set_language(code)
        if store is not None:
            store.setValue(SETTINGS_KEY, active)
        if active != previous:
            self.reapply()
            self.languageChanged.emit(active)


_translator: Optional[Translator] = None


def translator() -> Translator:
    global _translator
    if _translator is None:
        _translator = Translator()
    return _translator


_initialised = False


def init_language(store: QSettings, system_name: str = "", only_once: bool = False) -> str:
    """Saved language, else the system's (French systems get French). Call once at start."""
    global _initialised
    if only_once and _initialised:
        return i18n.language()
    _initialised = True
    saved = str(store.value(SETTINGS_KEY, "") or "")
    code = saved if saved in i18n.LANGUAGES else i18n.detect_language(system_name)
    return i18n.set_language(code)


def set_language(code: str, store: Optional[QSettings] = None) -> None:
    translator().set_language(code, store)


def language() -> str:
    return i18n.language()


def on_language_changed(slot: Callable, owner: Optional[QObject] = None) -> None:
    """Call ``slot(code)`` after each language change. With ``owner``, the call is
    skipped once that widget has been deleted (safe for lambdas)."""
    if owner is None:
        translator().languageChanged.connect(slot)
        return

    def _guarded(code: str) -> None:
        if _is_alive(owner):
            slot(code)

    translator().languageChanged.connect(_guarded)


def bind(widget, text: str, method: str = "setText", **kwargs):
    """Show ``tr(text)`` through ``widget.<method>`` now and after every language change."""
    setter = getattr(widget, method)
    translator().add(widget, setter, text, kwargs)
    return widget


def bind_tip(widget, text: str, **kwargs):
    return bind(widget, text, "setToolTip", **kwargs)


def bind_call(owner: QObject, apply: Callable[[str], None], text: str, **kwargs) -> None:
    """Generic form: ``apply(tr(text))`` now and after every language change, while ``owner`` lives."""
    translator().add(owner, apply, text, kwargs)

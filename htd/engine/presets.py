"""
Mastering presets and per-run settings (same values and behaviour as the web version).

A preset is only a starting point: it fills the Advanced Settings (tone recipe,
limiter drive, ceiling, cleanse intensity), which the user can then change.
``MasterSettings`` is everything that decides how a track is rendered.
"""

from __future__ import annotations

from dataclasses import dataclass
from dataclasses import replace as dataclass_replace
from typing import Dict, Tuple

from .core import PROFILES, MasteringProfile


@dataclass(frozen=True)
class Preset:
    """A starting point for the Advanced Settings (every value can then be changed)."""

    name: str
    summary: str
    recipe: str             # tonal / dynamics recipe: a key of core.PROFILES
    target_lufs: float      # limiter drive: loudness the master is pushed to
    ceiling_db: float       # limiter ceiling (dBTP)
    intensity_pct: int      # Anti-Parasite Filter intensity


PRESETS: Dict[str, Preset] = {
    preset.name: preset
    for preset in (
        Preset("Standard",
               "Balanced streaming master with gentle glue compression.",
               "Standard Streaming", -14.0, -1.0, 35),
        Preset("Hip-Hop / Punch",
               "Sub-bass weight and punch: slow-attack compression lets the drums hit.",
               "Club / Urban", -11.0, -0.8, 30),
        Preset("Electronic / Loud",
               "Club-loud master. Expect audible limiting on very dynamic mixes.",
               "Club / Urban", -9.0, -0.5, 35),
        Preset("Acoustic / Dynamic",
               "Almost no compression: dynamics and transients preserved, quieter by design.",
               "Transparent / Orchestral", -16.0, -1.5, 25),
    )
}

DEFAULT_PRESET = "Standard"
CEILING_RANGE = (-2.0, 0.0)      # dBTP, 0.1 dB steps
TARGET_RANGE = (-20.0, -7.0)     # LUFS (limiter drive), 0.5 LU steps
INTENSITY_RANGE = (0, 100)       # %


@dataclass(frozen=True)
class MasterSettings:
    """Everything that decides how a track is rendered (compared to detect outdated results)."""

    preset: str
    recipe: str
    target_lufs: float
    ceiling_db: float
    intensity_pct: int
    # auto-trim of the silences at both ends (+ micro-fades)
    trim: bool = False
    trim_threshold_db: float = -60.0
    # reference matching ("" = no reference)
    reference_id: str = ""
    match_eq: bool = True
    match_strength: int = 75
    match_loudness: bool = True

    @classmethod
    def from_preset(cls, name: str) -> "MasterSettings":
        preset = PRESETS[name]
        return cls(preset.name, preset.recipe, preset.target_lufs,
                   preset.ceiling_db, preset.intensity_pct)

    def key(self) -> Tuple:
        """Plain-value identity (safe to compare even if the class is re-imported).
        Options that are switched off do not count (changing them changes nothing)."""
        trim = (True, round(float(self.trim_threshold_db), 1)) if self.trim else (False,)
        if self.reference_id:
            reference = (self.reference_id, bool(self.match_eq),
                         int(self.match_strength) if self.match_eq else 0, bool(self.match_loudness))
            target = None if self.match_loudness else round(float(self.target_lufs), 2)
        else:
            reference, target = ("",), round(float(self.target_lufs), 2)
        return (self.preset, self.recipe, target, round(float(self.ceiling_db), 2),
                int(self.intensity_pct), trim, reference)

    @property
    def customised(self) -> bool:
        preset = PRESETS.get(self.preset)
        return preset is None or (
            preset.recipe, preset.target_lufs, preset.ceiling_db, preset.intensity_pct
        ) != (self.recipe, self.target_lufs, self.ceiling_db, self.intensity_pct)

    @property
    def label(self) -> str:
        return f"{self.preset} (custom)" if self.customised else self.preset

    def profile(self) -> MasteringProfile:
        """The engine recipe with this run's loudness target and ceiling."""
        return dataclass_replace(
            PROFILES[self.recipe],
            name=self.label,
            target_lufs=float(self.target_lufs),
            true_peak_db=float(self.ceiling_db),
        )

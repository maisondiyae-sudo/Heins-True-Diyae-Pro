#!/usr/bin/env python3
"""Anti-Parasite Filter - analog tolerance modeling (``analog_seed``).

Checks that:
  1. ``analog_seed=None`` (or omitted) is the v1.0 filter, bit for bit
     (frozen reference digests + 0 % intensity ignores the seed);
  2. the same seed always renders the very same samples;
  3. two different seeds render slightly different (but very close) audio,
     and every internal deviation stays within +/-1 to 3 %;
  4. the seed travels through render_service.run_request -> pipeline.master_track
     and gives a bit-identical master for the same seed (None = no seed);
  5. (v2.2.2) per-track seeds: generation, reading back from a .htd project
     (older projects without one), the render cache key of the Mastering tab, and
     the MasteringWorker, which re-renders only when the seed differs - so the
     master behind an export is bit-identical to the preview that was heard.

Run it from anywhere:  python tests/test_analog_tolerance.py   (pytest works too)
Needs only the project's own dependencies; the last two checks also need PySide6
(already required by the app) and are skipped without it. No window is opened.
"""
import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path

import numpy as np
import scipy

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from htd.engine.core import AntiParasiteFilter  # noqa: E402

SR = 44_100
FILE_SEED = 12345

# SHA-256 of the v1.0 filter output on signal() below (seed=FILE_SEED, no analog_seed),
# recorded with numpy 2.5.3 / scipy 1.18.1 before the analog option was added.
# Floating-point results can differ by one ULP between library versions and between
# CPUs (numpy picks AVX2 / AVX-512 code paths at runtime, e.g. for np.sin), so a
# mismatch on another machine is not a regression by itself: it is reported, and only
# fails when HTD_STRICT_V1_DIGESTS=1 (on the machine the digests were recorded on).
V1_DIGESTS = {
    0.0: "a22633ef7adbdea38013a03f86b9fefc9c28476833602d68e33d2e3c595fb3c7",
    0.5: "cb068200305e2ca2eb56c53a21750408cc2a73a8cbc650746a8dc64f3df578e8",
    1.0: "7ec318c6e243ae902e5ca8c03679668f09942f93306658248203a50074b5f8da",
}
V1_VERSIONS = ("2.5.3", "1.18.1")


def signal(seed: int = 7, n: int = SR * 3) -> np.ndarray:
    """Tone + hiss + a faint 15 kHz whine (exercises Stages A, B and C)."""
    rng = np.random.default_rng(seed)
    t = np.arange(n) / SR
    x = (0.3 * np.sin(2 * np.pi * 220 * t)[:, None]
         + 0.0005 * rng.standard_normal((n, 2))
         + 0.001 * np.sin(2 * np.pi * 15000 * t)[:, None])
    return x.astype(np.float32)


def render(intensity: float, **kwargs) -> np.ndarray:
    return AntiParasiteFilter(SR, intensity, seed=FILE_SEED, **kwargs).process(signal())


def digest(audio: np.ndarray) -> str:
    return hashlib.sha256(np.ascontiguousarray(audio).tobytes()).hexdigest()


# --------------------------------------------------------------------------- core
def test_none_is_v1_bit_exact():
    for intensity in V1_DIGESTS:
        default = render(intensity)
        explicit = render(intensity, analog_seed=None)
        assert np.array_equal(default, explicit), f"None != omitted at {intensity:.0%}"
        if (np.__version__, scipy.__version__) != V1_VERSIONS:
            continue
        if digest(explicit) != V1_DIGESTS[intensity]:
            message = f"v1.0 digest differs at {intensity:.0%} (another CPU / build, or a regression)"
            assert os.environ.get("HTD_STRICT_V1_DIGESTS") != "1", message
            print("note:", message, "- set HTD_STRICT_V1_DIGESTS=1 to make it fail")


def test_zero_intensity_ignores_seed():
    assert np.array_equal(render(0.0, analog_seed=99), render(0.0))
    flt = AntiParasiteFilter(SR, 0.0, seed=FILE_SEED, analog_seed=99)
    flt.process(signal())
    assert flt.report.analog_seed is None and flt.report.analog_max_deviation_pct == 0.0


def test_same_seed_is_bit_identical():
    first, second = render(0.6, analog_seed=2026), render(0.6, analog_seed=2026)
    assert first.dtype == np.float32 and np.array_equal(first, second)


def test_different_seeds_differ_slightly():
    reference = render(0.6)
    a, b = render(0.6, analog_seed=1), render(0.6, analog_seed=2)
    assert not np.array_equal(a, b), "two seeds gave the same render"
    assert not np.array_equal(a, reference)
    for audio in (a, b):
        # "slightly": the difference stays far below the programme (< -30 dB)
        ratio = np.sqrt(np.mean((audio - reference) ** 2) / np.mean(reference ** 2))
        assert 20 * np.log10(ratio) < -30.0, f"deviation too large ({20 * np.log10(ratio):.1f} dB)"
        assert np.isfinite(audio).all()


def test_deviations_stay_within_1_to_3_percent():
    flt = AntiParasiteFilter(SR, 0.8, seed=FILE_SEED, analog_seed=42)
    flt.process(signal())
    nominal = flt._nominal_params()
    left, right = flt._channel_params
    assert left != right, "both channels got the same tolerances"
    for params in (left, right):
        ratios = [params.highpass_hz / nominal.highpass_hz,
                  params.lowpass_hz / nominal.lowpass_hz,
                  params.spur_excess_db / nominal.spur_excess_db,
                  params.spur_plateau_db / nominal.spur_plateau_db,
                  params.spur_min_hz / nominal.spur_min_hz,
                  params.over_subtraction / nominal.over_subtraction,
                  10 ** ((params.noise_ceiling_db - nominal.noise_ceiling_db) / 20),
                  10 ** ((params.spur_max_level_db - nominal.spur_max_level_db) / 20),
                  *params.highpass_f_scale, *params.highpass_q_scale,
                  *params.lowpass_f_scale, *params.lowpass_q_scale]
        deviation = np.abs(np.asarray(ratios) - 1.0)
        assert deviation.min() >= 0.01 - 1e-9 and deviation.max() <= 0.03 + 1e-9, deviation
    assert flt.report.analog_seed == 42
    assert 1.0 <= flt.report.analog_max_deviation_pct <= 3.0


# ------------------------------------------------------------------- render service
def test_render_service_propagates_seed():
    import soundfile as sf
    from htd.engine.presets import PRESETS, MasterSettings
    from htd.engine.render_service import RenderRequest, run_request

    work = Path(tempfile.mkdtemp(prefix="htd-analog-"))
    source = work / "source.wav"
    sf.write(str(source), signal(n=SR * 5), SR, subtype="PCM_24")
    settings = MasterSettings.from_preset(next(iter(PRESETS)))
    if settings.intensity_pct == 0:  # the option only acts when the filter cleans
        from dataclasses import replace
        settings = replace(settings, intensity_pct=60)

    def master(analog_seed="omit"):
        request = RenderRequest("k", source, settings, work)
        if analog_seed != "omit":
            request.analog_seed = analog_seed
        result = run_request(request, None, None)
        try:
            audio, _ = sf.read(str(result.master_cache), dtype="float32")
            cleaned_seed = result.clean_report.analog_seed
            return audio, result.analog_seed, cleaned_seed
        finally:
            result.cleanup()

    plain, _, plain_seed = master()
    none, _, _ = master(None)
    a1, a1_result_seed, a1_report_seed = master(7)
    a1_again, _, _ = master(7)
    a2, _, _ = master(8)

    assert plain_seed is None
    assert np.array_equal(plain, none), "analog_seed=None changed the master"
    assert a1_result_seed == 7 and a1_report_seed == 7, "seed did not reach the filter"
    assert np.array_equal(a1, a1_again), "same seed, different master"
    assert not np.array_equal(a1, a2), "different seeds, same master"
    assert not np.array_equal(a1, plain)


# ------------------------------------------------------------- v2.2.2: per-track seeds
class _Skip(Exception):
    """A check that needs an optional module (PySide6) that is not installed."""


def _require_pyside6() -> None:
    try:
        import PySide6.QtCore  # noqa: F401
    except ImportError:
        try:
            import pytest
        except ImportError:
            raise _Skip("PySide6 is not installed")
        pytest.skip("PySide6 is not installed")


def test_new_track_seed_is_a_31_bit_integer():
    from htd.engine.pipeline import ANALOG_SEED_BITS, new_analog_seed
    seeds = [new_analog_seed() for _ in range(256)]
    assert ANALOG_SEED_BITS == 31
    assert all(type(s) is int and 0 <= s < 2 ** 31 for s in seeds)
    assert len(set(seeds)) > 250, "seeds are not random"


def test_project_seed_round_trip_and_old_projects():
    from htd.engine.pipeline import new_analog_seed, parse_analog_seed
    seed = new_analog_seed()
    track = json.loads(json.dumps({"path": "a.wav", "analog_seed": seed}))   # what a .htd stores
    assert parse_analog_seed(track.get("analog_seed")) == seed
    assert parse_analog_seed(0) == 0 and parse_analog_seed(2 ** 31 - 1) == 2 ** 31 - 1
    assert parse_analog_seed("1234") == 1234 and parse_analog_seed(77.0) == 77
    old_track = {"path": "a.wav", "mode_token": ""}                          # pre-2.2.2 project
    for bad in (old_track.get("analog_seed"), True, False, -1, 1.5, "abc", "", [], {}, 2 ** 64):
        assert parse_analog_seed(bad) is None, bad                          # -> keep a new seed


def test_mastering_tab_cache_key_includes_seed():
    _require_pyside6()
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from htd.engine.pipeline import TrackResult
    from htd.engine.presets import PRESETS, MasterSettings
    from htd.ui.mastering_tab import TrackEntry, mode_key, result_key

    class Card:                                     # TrackEntry only asks the card for its cut
        def cut(self):
            return None

    settings = MasterSettings.from_preset(next(iter(PRESETS)))
    assert mode_key(settings, None, 1) != mode_key(settings, None, 2)
    assert mode_key(settings, None) == mode_key(settings, None, None)

    entry = TrackEntry(Path("a.wav"), Card(), analog_seed=5)
    result = TrackResult(source=Path("a.wav"), ok=True, settings=settings, analog_seed=5)
    assert result_key(result) == mode_key(settings, None, 5)
    entry.add(result, clock=1)
    assert entry.current(settings) is result and entry.is_current(result, settings)

    other = TrackEntry(Path("a.wav"), Card(), analog_seed=6)                 # another console channel
    other.add(TrackResult(source=Path("a.wav"), ok=True, settings=settings, analog_seed=5), clock=1)
    assert other.current(settings) is None, "a render made with another seed was reused"
    assert TrackEntry(Path("b.wav"), Card()).analog_seed is not None          # drawn when added


def test_worker_reuses_only_same_seed_and_rerenders_bit_identical():
    _require_pyside6()
    import soundfile as sf
    from htd.engine.delivery import ExportOptions, TrackMeta
    from htd.engine.presets import PRESETS, MasterSettings
    from htd.ui.workers import MasterJob, MasteringWorker

    os.environ["HTD_INPROCESS_RENDER"] = "1"        # in this thread: no child process for the test
    work = Path(tempfile.mkdtemp(prefix="htd-analog-worker-"))
    source = work / "song.wav"
    sf.write(str(source), signal(n=SR * 5), SR, subtype="PCM_24")
    settings = MasterSettings.from_preset(next(iter(PRESETS)))
    if settings.intensity_pct == 0:
        from dataclasses import replace
        settings = replace(settings, intensity_pct=60)

    def run(existing, seed):
        job = MasterJob("k", source, existing, TrackMeta("Song"), settings=settings, analog_seed=seed)
        worker = MasteringWorker([job], ExportOptions(), work, None)
        finished = []
        worker.trackFinished.connect(lambda _key, result: finished.append(result))
        worker.run()                                # synchronous: the worker's own loop
        assert finished and finished[0].ok, getattr(finished[0], "error", "no result")
        return finished[0]

    def master(result):
        return sf.read(str(result.master_cache), dtype="float32")[0]

    preview = run(None, 314159)
    assert preview.analog_seed == 314159 and preview.clean_report.analog_seed == 314159
    assert run(preview, 314159) is preview, "same seed: the preview must be reused as it is"
    again = run(None, 314159)                       # e.g. evicted from the cache, then exported
    assert np.array_equal(master(preview), master(again)), "re-render differs from the preview"
    other = run(preview, 271828)
    assert other is not preview and other.analog_seed == 271828
    assert not np.array_equal(master(preview), master(other))
    for result in (preview, again, other):
        result.cleanup()


# --------------------------------------------------------------------------- script
if __name__ == "__main__":
    ok = True
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("PASS", name)
            except _Skip as exc:
                print("SKIP", name, f"({exc})")
            except Exception as exc:  # noqa: BLE001
                ok = False
                print("FAIL", name, f"{type(exc).__name__}: {exc}")
    print("ALL PASS" if ok else "SOME FAILED")
    sys.exit(0 if ok else 1)

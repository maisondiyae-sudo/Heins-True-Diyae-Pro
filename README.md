# Heins True Diyae Pro 2.2.3 - Free & Open Edition (Windows / macOS / Linux)
*by mo7amed illumyn diyae — © 2026 mo7amed illumyn diyae*

<p align="center">
  <img width="850" alt="Heins True Diyae Pro interface" src="https://github.com/user-attachments/assets/b05278af-4bb8-435b-800c-56c429075b47" />
</p>

<br>

Anti-Parasite Filter, mastering (presets + advanced settings, batch, A/B with
Gain Match), export to WAV 24 / WAV 16 / MP3 320 / FLAC / M4A or a release pack,
and a batch audio converter. Free for everyone, every feature unlocked: no
licence key, no activation. PySide6 interface; all audio work runs in
background threads (the mascot dances while it works). The mastering engine
(`htd/engine/core.py`) is unchanged since 1.0; since 2.2.2 the Anti-Parasite Filter
adds an analog tolerance per track (below). With `analog_seed=None` the engine
still renders bit-identical v1.0 masters.

## Download (no installation of Python needed)

Ready-to-use apps are on the **[Releases page](../../releases/latest)**:

| Your computer | File |
|---|---|
| Windows 10 / 11 (64-bit) | `HeinsTrueDiyaePro-<version>-Windows.zip` |
| Mac with an Apple chip (M1, M2, M3, M4...) | `HeinsTrueDiyaePro-<version>-macOS-AppleSilicon.dmg` |
| Mac with an Intel processor | `HeinsTrueDiyaePro-<version>-macOS-Intel.dmg` |
| Linux (x86_64) | `HeinsTrueDiyaePro-<version>-x86_64.AppImage` |

The Mac versions need macOS 14 (Sonoma) or later. FFmpeg is included. The app is
free and not signed with a paid Apple / Microsoft certificate, so the system asks for
confirmation the first time only:

* **Windows**: right-click the .zip > *Extract All*, then run `HeinsTrueDiyaePro.exe`
  from the extracted folder. If SmartScreen says "Windows protected your PC", click
  *More info* > *Run anyway*.
* **macOS**: open the .dmg and drag the app onto *Applications*. Open it once (macOS
  blocks it), then *System Settings > Privacy & Security* > *Open Anyway* next to
  Heins True Diyae Pro. Since macOS 15 (Sequoia), right-click > Open no longer does
  this. In Terminal, this also works:
  `xattr -dr com.apple.quarantine "/Applications/Heins True Diyae Pro.app"`.
* **Linux**: `chmod +x HeinsTrueDiyaePro-*.AppImage` (or *Properties > Allow
  executing as program*), then run it.

## New in 2.2.3 (Linux, ready-made downloads, steadier rendering)

* **Linux version**: a single-file AppImage (`bash build_linux.sh`), with PortAudio
  and the xcb libraries Qt needs bundled in. Contributed by
  [logicalor](https://github.com/logicalor) (PR #2), thank you!
* **Ready-made downloads for everyone**: Windows (.zip), Mac Apple Silicon and Mac
  Intel (.dmg), Linux (.AppImage) are now built automatically on GitHub and published
  on the Releases page (see *Download* above), no Python needed. On a Mac,
  `build_macos.sh` now also makes the drag-and-drop .dmg.
* **No more frozen batch**: if the background render process crashed or stopped
  responding, the app could freeze for good. It now detects it (crash at once, or no
  progress for 300 s) and finishes the track in the app itself. The render process
  also starts cleanly ("spawn") on Linux and macOS, as on Windows, and is started at
  launch so the first render is quicker. (PR #2)
* The render process now finds the FFmpeg bundled with the app even when it is not
  on `PATH`, and leftover temporary renders of a force-closed session are removed at
  the next launch (Linux / macOS; Windows keeps the 24 h rule).

## New in 2.2.2 (analog console channel)

* **Analog tolerance modeling on the Anti-Parasite Filter**, inspired by the
  tolerance modeling of analog consoles: real components are never exactly on
  value, and each channel of a console drifts a little differently. Every track
  now gets its own "console channel": a ±1–3 % deviation, different on the left
  and the right channel, on the filter's internal parameters (20 Hz / 20 kHz
  corners, natural frequency and Q of every Butterworth section, Stage B detection
  thresholds). The band-limiting stays zero-phase, so the stereo image and mono
  compatibility are untouched; the phase micro-smoothing (Stage C) is unchanged
  and the rest of the mastering chain is not affected. Nothing to set: no new
  button or slider.
* **One stable seed per track**: a random 31-bit `analog_seed` is drawn the moment a
  track is added to the list and never changes for that track — previews,
  re-renders, exports, undo / redo. It is part of the render cache key, so the
  exported file is **bit-identical** to the preview you listened to.
* **Saved in projects (.htd)**: each track's `analog_seed` is stored in the
  project and restored when it is opened. Older projects (without it) still open:
  their tracks simply get a new seed, which is saved the next time the project is.
* Engine API: `AntiParasiteFilter(..., analog_seed=None)`,
  `pipeline.master_track(..., analog_seed=None)` and
  `RenderRequest.analog_seed`; `None` (or 0 % cleanse) is the v1.0 filter, bit
  for bit. Test: `python tests/test_analog_tolerance.py`.
* Note: because every track now has its own console channel, a desktop master is
  no longer bit-identical to the same file mastered with 2.2.1 or the web
  version (the difference is tiny — around −45 dB below the music).

## New in 2.2.1 (metadata hygiene)

* **Clean metadata on every export** (Mastering, release Pack and Converter).
  Every file is now muxed into a blank container
  (`-map_metadata -1 -map_chapters -1 -fflags +bitexact -flags:a +bitexact`),
  so old parasitic tags from the source files (stray comments, dates, chapters,
  LIST/INFO chunks, bext/iXML, old embedded covers) are **never** copied into the
  final file. Only the fields you fill in (title, artist, album, BPM, key, cover)
  are written — no automatic software / encoder / default-comment stamp (no ISFT,
  no TSSE, no "Software", no app name; a blank MP3 no longer carries an empty ID3
  tag). The chosen cover is still embedded. (WAV/FLAC/M4A come out with no `Lavf`
  string; a tagged MP3 keeps only the standard, version-less Xing/Info header that
  players use for gapless and duration.)
* **"Export without metadata"** checkbox in the Export panel: writes the audio
  only — no tags and no cover at all, for a 100 % blank deliverable. For WAV and
  FLAC the raw libsndfile file is kept untouched (no re-muxing). Translated in all
  8 languages and remembered between sessions.

## New in 2.2.0

* **Cleaner playback**: rendering now runs in a separate process (the audio
  callback no longer fights the DSP for the GIL) with a more comfortable
  PortAudio buffer, so there are no crackles even while a batch computes. If the
  child process can't start, rendering falls back to a thread automatically.
* **Queue control**: a **Pause / Resume** button next to Cancel (Mastering and
  Converter) pauses the queue between items without losing finished work; and a
  per-track **mode selector** ("Follow the left panel", or a preset / profile
  just for that track) lets you queue tracks with different modes and prepare
  them all at once. The per-track mode is saved in projects.
* **More shortcuts** (disabled while typing): `Space` play/pause, `Tab`
  Original↔Master, `M` mono, `L` loop, `A`/`B` set the loop points live, `R` back
  to A, `←`/`→` move 5 s, `Ctrl+Z`/`Ctrl+Y` undo/redo (ticks, cuts, modes,
  titles, track list), `Ctrl+S`/`Ctrl+O` save/open a project, `F1` help.
* **Help & About** window (the `?` button in the header, or F1): all shortcuts,
  the licence, and a button to open the logs folder for bug reports.
* **Guardrails for release**: the temporary render cache is capped (~4 GB, oldest
  non-listened renders evicted first) and the obsolete 16-bit preview files are
  gone; closing with unsaved changes asks to save; a rotating error log records
  any unhandled exception (no console needed); and a full **GPL-3.0 `LICENSE`**
  file plus an FFmpeg source offer ship with the project.

## New in 2.1.0 (final version)

* **Ticked tracks**: each card has a tick box (ticked when added) and the list a
  "Tick all / Untick all" switch. *Prepare the previews* and *Export all* only
  work on the ticked tracks and show how many; a card's own Export always works.
* **Projects (.htd)**: *Save the project* / *Open a project* (Ctrl+S / Ctrl+O, ⌘ on
  macOS) keep the whole session in a JSON file: tracks, ticks, titles, BPM, keys,
  cuts, A-B markers, Gain Match / Mono, the mode of each track and every setting
  on the left. Moved project + audio folder: files are found again through
  relative paths; a missing file is reported, never a crash. Double-click a .htd
  (macOS) or "Open with" (Windows) opens it.
* **Manual cut (start / end)**: type the times (`1:23.450` or `83.45`) or click
  *✂ Trim to A–B*; *Reset the cut* brings the whole track back. Non-destructive:
  the source file is never touched; the cut is applied before mastering with
  5 ms / 20 ms micro-fades, and shows in listening (shaded on the seek bar), in
  the analysis and in the exports. Without a cut, masters are bit-identical.
* **Listen at once**: as soon as a track is added, Original, the seek bar, Mono,
  the loop and the cut work. Master, Gain Match, Analysis and Export wait for
  *Prepare the previews*.
* **Loop A-B, the pro way**: A then B switches the loop on (and jumps back to A if
  the playhead is already past B); ⏮ goes back to A (or to 0:00 without A);
  starting or resuming outside the loop starts at A.
* **Keyboard shortcuts** (not while typing in a field):

  | Key | Action |
  |---|---|
  | Space | play / pause |
  | Tab | Original <-> Master (same moment) |
  | M | Mono on / off |
  | L | loop on / off |
  | R | back to A (or to 0:00 without a loop) |

* Footers: the progress bar spans the whole width above the status line and the
  buttons, and only shows while something runs. The PROFILES row is no longer
  clipped by the scroll bar.

## New in 2.0.1

* **New audio player (PortAudio through `sounddevice`)**: no more QMediaPlayer, so no
  more crackle on Windows. The sound is played straight from float32 buffers already
  at the sound card's own rate (WASAPI mixer rate on Windows), with a comfortable
  2048-frame buffer. Original / Master, another mode, seek-bar jumps and the loop
  A-B are sample-accurate and cross-faded over 6 ms (no click); Gain Match and Mono
  change live; pause / stop fade out. It follows the default output (headphones...)
  and releases the sound device after 15 s without playback.
* **Cancel** is only shown while a render, an export or a conversion runs.

## New in 2.0

* **Free & Open**: the licence system is gone (no key, no activation screen).
* **Listen first, export later.** *Prepare the previews* renders the tracks into
  a temporary folder - nothing is written next to your files. Compare Original /
  Master (Gain Match), then **Export** one track from its card or **Export all**.
  Changing only the title, BPM, key, tags or format re-exports without
  mastering again.
* **Modes kept in memory**: up to 3 modes per track (session only). Going back
  to a mode already rendered is instant (chips "Rendered modes" on each card).
  Change the preset while a track plays: that track is re-rendered in the
  background and playback follows at the same moment.
* **Loop A-B** on the seek bar (A, B, ⟲, ✕): kept when you switch Original /
  Master or the mode. The seek bar stays left to right in Arabic.
* **Mono** button on each card: hear Original or Master summed to mono, live.
* **Stereo / phase readout**: correlation, bass correlation (< 150 Hz), mono
  fold-down loss, worst moment; a discreet orange / red alert when something
  would cancel in mono. Details in the analysis window.
* **Profiles**: save, recall (one click), rename, delete your favourite
  combinations - mode, recipe, Anti-Parasite, auto-trim, reference options,
  export format, release pack / clip options, output folder and rules.
* **Output folder and conflicts**: next to the sources or a folder of your
  choice, optional subfolder per mode (`.../Club/`), and a rule when a file
  already exists: rename (`_2`, `_3`...), overwrite or skip.
* All new texts in the 8 languages (FR, EN, ES, ZH, JA, HI, AR, RU).

## How to use it

1. Drop tracks or folders. BPM and key are detected in the background; you can
   already listen to the originals, set a loop or a cut.
2. Pick a preset (or a profile) and click **🎧 Prepare the previews**.
3. Listen: ▶ Original / ▶ Master, Gain Match, Mono, loop A-B. Try other
   presets: each rendered mode stays one click away.
4. Click **⬇ Export** on a card, or **⬇ Export all**.

## Earlier versions

1.3.2 (listening): light crackle on drums in the app only. The previews were
44.1 kHz while most sound cards run at 48 kHz, so Windows resampled them on the fly.
The app now prepares, right after mastering, playback copies at the card's own rate
with a high-quality resampler (htd/ui/playback.py), follows the default output device
(headphones...) and plays at volume 1.0. Exported files are not affected.

1.3.1 (player): the pause button shows and freezes playback, the seek bar and
time follow the sound, clicking the bar jumps to that moment (also while paused or
while the other version loads), and Original / Master switching keeps the moment.
Previews are dithered, batches run at low thread priority, the dancing GIF is decoded
at its drawn size. PySide6 6.7.2 or newer is required (Qt player-freeze fix).

1.3:

* **Seek bar** on every track card: click or drag to jump anywhere, play / pause,
  `0:42 / 1:56`. It follows the original's timeline, so switching Original / Master
  stays on the same moment (also with a trimmed master).
* **The mascot dances while you listen** (Original or Master) and goes back to its
  calm float on pause / stop, unless a batch is running.
* **Bubble**: no more "›" arrow (click the mascot for the next phrase); "–" hides it.
* **146 phrases**: a lively, funny studio buddy and a real mastering teacher
  (LUFS, true peak, dynamics, headroom, gain staging, references, A/B, Anti-Parasite,
  exports), plus lines when playback starts.
* **8 languages**: Français, English, Español, 中文, 日本語, हिन्दी, العربية, Русский —
  interface and phrases, switched live from the 🌐 menu; missing texts fall back to
  English. Arabic mirrors the whole interface (right-to-left); seek bars stay
  left-to-right. Each language gets the right system fonts (Chinese vs Japanese
  glyphs, Devanagari, Arabic) — nothing to install.

1.2:

* **Living mascot** in the header (next to the logo): hatches from an egg when the
  app opens, floats calmly when idle, plays your dancing GIF while a batch runs,
  and grows one size per batch launched (session only, capped so it never
  overflows the header). Drop your GIF in `assets/mascot_dance.gif`.
* **Phrase bubble**: random mascot lines, studio maxims and mixing / mastering tips,
  with reactions to batches; "›" for another phrase, "–" to hide it (remembered).
* **FR / EN switch** in the header: the whole interface and the phrases change
  language live; French by default on French systems; missing translations fall
  back to English automatically.

1.1:

* **BPM + key detection** on every track you add (editable, ÷2 / ×2, Camelot code),
  optionally added to the file names: `MyTrack_142BPM_Cm_HTD_Standard.wav`.
* **Auto-trim**: cuts the silence at both ends after mastering, with anti-click
  fades (5 ms in, 20 ms out). A/B listening stays lined up with the original.
* **Reference track**: matches its tonal balance (linear-phase EQ, ±6 dB max,
  replaces the recipe EQ) and / or its loudness (limiter target).
* **Release pack**: one folder per track with WAV 24-bit, MP3 320 kbps (ID3v2.3:
  title, artist, album, year, genre, track, BPM, key, cover), `cover.jpg` and an
  info sheet. Tags and cover are also written to single-format exports.
* **Social clip**: 15 / 30 / 45 / 60 s excerpt (best part or from the start,
  on the beat, whole bars) as M4A, plus an optional vertical 1080×1920 MP4 with
  the cover.

## Install and run

Python 3.11, 3.12 or 3.13 (64-bit). From this folder:

**Windows (PowerShell)**

```powershell
py -3.12 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
python main.py
```

**Linux (Terminal)**

Use Python 3.11-3.13: PySide6 6.9.x does not support 3.14 yet. The Windows and macOS
`sounddevice` packages include PortAudio; on Linux it comes from the distribution, along
with the xcb libraries Qt's platform plugin loads at runtime:

```bash
# Debian / Ubuntu
sudo apt install python3-venv libportaudio2 libxcb-cursor0 libxkbcommon-x11-0 libgl1 libegl1
# Fedora
sudo dnf install python3.12 portaudio xcb-util-cursor libxkbcommon-x11 libglvnd-egl libglvnd-glx

python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
python main.py
```

Playback goes through PortAudio to PipeWire / PulseAudio / ALSA. FFmpeg is taken from
`PATH` or from `/usr/bin`, `/usr/local/bin`, `/snap/bin`. Under Wayland the window runs
through XWayland; if it opens blank, start it with `QT_QPA_PLATFORM=xcb python main.py`.

**macOS (Terminal)**

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
python main.py
```

Put your logo in `assets/logo.png` and your mascot GIF in `assets/mascot_dance.gif`
(see `assets/PUT_YOUR_MASCOT_HERE.txt`).

## Build the standalone app (PyInstaller)

Build on each system for that system: Windows for Windows, macOS for macOS (Apple
Silicon for Apple Silicon, Intel for Intel), Linux for Linux. PyInstaller does not
cross-compile. One command does everything (virtual environment, packages, build).
No Mac or Linux machine? GitHub builds all of them for you: see *Automatic builds*
below.

**Windows** - double-click `build_windows.bat`, or in a terminal:

```bat
build_windows.bat
```

**macOS**

```bash
bash build_macos.sh
```

Result: `dist/Heins True Diyae Pro.app` and a drag-and-drop installer
`dist/HeinsTrueDiyaePro-<version>-macOS-AppleSilicon.dmg` (or `-Intel.dmg` on an
Intel Mac). The script picks a Python 3.11-3.13 (or set `PYTHON=/path/to/python3.12`).

**Linux (AppImage)**

```bash
bash build_linux.sh
```

Result: `dist/HeinsTrueDiyaePro-<version>-x86_64.AppImage`, one file, no install
step: `chmod +x` it and run it. The script builds the venv and the PyInstaller
bundle, assembles the AppDir (`packaging/linux/AppRun` +
`packaging/linux/heins-true-diyae-pro.desktop`, 256x256 icon generated from
`assets/logo.png`), bundles PortAudio and the xcb libraries Qt needs, then
downloads `appimagetool` into `.cache/` and builds the image. It needs curl or
wget the first time. Without FUSE the image still runs:
`./HeinsTrueDiyaePro-*.AppImage --appimage-extract-and-run`.

Or by hand (after activating the virtual environment shown above):

```bash
pip install -r requirements.txt pyinstaller
pyinstaller HeinsTrueDiyaePro.spec --noconfirm --clean
```

Result: Windows `dist/HeinsTrueDiyaePro/HeinsTrueDiyaePro.exe` (ship the whole
`HeinsTrueDiyaePro` folder, e.g. zipped) · macOS `dist/Heins True Diyae Pro.app` ·
Linux `dist/HeinsTrueDiyaePro-<version>-x86_64.AppImage`.
The `assets/` folder (logo, mascot), the fallback FFmpeg and the third-party
notices are bundled. Icon: `assets/logo.ico` / `assets/logo.icns`, or
`assets/logo.png` converted automatically. On macOS, `build_macos.sh` signs the
app ad hoc; on other Macs the first launch goes through *System Settings > Privacy &
Security > Open Anyway* (see *Download* above), unless you sign and notarize it with
an Apple Developer ID.

## Automatic builds (GitHub Actions)

`.github/workflows/release.yml` builds the four downloads on GitHub's machines
(Windows, Apple Silicon Mac, Intel Mac, Linux) and runs the tests:

* **Try a build**: *Actions* tab > *Build & Release* > *Run workflow* (leave
  *Publish* unticked). When it is done (about 20-30 minutes), the files are at the
  bottom of the run page under *Artifacts* (kept 14 days).
* **Publish a version**: the same, with *Publish a release* ticked. After the tests and
  the builds, the release `v<APP_VERSION>` (from `htd/config.py`) is created with the
  four files and the text of `packaging/release-notes.md`. If that version is already
  released, the run stops at once: raise `APP_VERSION` first.
* Git users can also push a tag `v<APP_VERSION>` (`git tag v2.2.3 && git push origin
  v2.2.3`), or create a release with that tag on the GitHub page: the files are built
  and attached to it. A tag that does not match `APP_VERSION` stops the build.

The Linux AppImage is built inside Ubuntu 22.04 so it runs on that and newer
distributions (Ubuntu 22.04+, Debian 12+, Fedora 36+...).

## Licence

The app is free. Its mastering chain uses pedalboard (GPL-3.0), so a public
build should be distributed under GPL-3.0-compatible terms - see
`THIRD_PARTY_NOTICES.md`.

## FFmpeg

Needed for M4A input, MP3 / M4A export, tags and covers, the release pack, the
social clip / video and the Converter tab. The app looks for it in
this order: `HTD_FFMPEG` environment variable, `bin/ffmpeg(.exe)` next to the app
(future packaged builds), PATH, Homebrew / MacPorts (macOS), winget / Chocolatey /
Scoop / `C:\ffmpeg\bin` (Windows), and finally the `imageio-ffmpeg` package installed
by `requirements.txt`. The header shows which one is used.

## Layout

```
main.py                      entry point (splash, theme, FFmpeg)
htd/config.py                name, version, edition, author, paths
htd/logging_setup.py         rotating error log + unhandled-exception capture
htd/i18n/                    languages (no Qt)
    __init__.py              tr(), trn(), language detection, engine-message patterns
    fr.py                    French translations {English: French} (+ engine-message patterns)
    world.py                 Spanish, Chinese, Japanese, Hindi, Arabic, Russian (one row per text)
    phrases.py               the bubble's phrases (FR + EN) and the random deck
    phrases_world.py         the phrases in the six other languages
htd/engine/                  no Qt in here
    core.py                  the engine of the web version (sections 1-7)
    presets.py               presets + MasterSettings (+ trim / reference options)
    pipeline.py              one track end to end, Gain Match previews
    analysis.py              BPM, beat phase and key detection (numpy / scipy)
    trim.py                  auto-trim + micro-fades
    reference.py             reference analysis, match EQ (linear-phase FIR)
    delivery.py              exports: formats, release pack, file names, clip, conflicts
    tags.py                  tags + cover through FFmpeg, cover preparation (Pillow)
    clip.py                  social clip window, M4A clip, vertical MP4
    export.py                WAV 24 / WAV 16 / MP3 / FLAC / M4A writers
    converter.py             FFmpeg batch conversion
    ffmpeg_tools.py          FFmpeg discovery for Windows / macOS / Linux
    preview.py               16-bit listening files, Gain Match maths
    stereo.py                stereo width / phase / mono-compatibility check
    cut.py                   manual start / end cut (non-destructive, before mastering)
    render_service.py        off-GUI rendering in a separate process (+ inline fallback)
htd/ui/                      PySide6
    main_window.py           header + tabs (add new tools in tool_factories())
    translate.py             live language switching (bind(), on_language_changed())
    language_switch.py       🌐 language menu
    fonts.py                 font families per script + right-to-left for Arabic
    companion.py             header bubble + mascot, wired to the activity hub
    mascot.py                mascot phases (hatch / idle / dance) and growth
    activity.py              app-wide "batch started / finished" signals
    mastering_tab.py         Mastering tab (previews, mode cache, exports, projects, shortcuts)
    profiles.py              saved profiles (JSON in the app settings)
    converter_tab.py         Converter tab
    track_card.py            one card per track
    analysis_dialog.py       spectrograms, tonal balance, specs
    workers.py               QThread workers, thread-pool tasks
    player.py                shared preview player: Qt signals, A/B, loop A-B, devices
    audio_output.py          PortAudio output: float32 buffers, cross-fades, live gain / mono
    about.py                 Help & About window (shortcuts, licence, logs)
    playback.py              listening buffers at the sound card's rate (memory + disk cache)
    widgets.py, theme.py     reusable widgets, light "white spaceship" style
build_windows.bat            one-command Windows build
build_macos.sh               one-command macOS build
build_linux.sh               one-command Linux AppImage build
packaging/linux/             AppRun + .desktop entry for the AppImage
packaging/release-notes.md   text of the GitHub release page (download + first launch)
.github/workflows/release.yml  automatic Windows / macOS / Linux builds and releases
HeinsTrueDiyaePro.spec       PyInstaller recipe
THIRD_PARTY_NOTICES.md       open-source components, licences, FFmpeg source offer
LICENSE                      GNU GPL-3.0 (full text)
```

## Tags by format

| Format | Text tags | BPM / key | Cover |
|---|---|---|---|
| MP3 | ID3v2.3 | TBPM / TKEY | yes |
| FLAC | Vorbis comments | BPM / INITIALKEY | yes |
| M4A | iTunes atoms (title, artist, album, year, genre, track) | no (not supported by FFmpeg's MP4 writer) | yes |
| WAV | RIFF INFO (title, artist, album, genre, year) | no | no |

## Adding a tool

Write a `QWidget` with a `TITLE` attribute (and optionally `shutdown()`), then add
`lambda ctx: MyTool(...)` to `tool_factories()` in `htd/ui/main_window.py`.
To make the mascot react, call `ctx.activity.batch_started("my-tool")` and
`ctx.activity.batch_finished("my-tool", succeeded, failed, cancelled)`.

## Translations and phrases

* Write interface texts in English and wrap them: `tr("Text")`, `trn("{n} file", "{n} files", n)`,
  or `bind(widget, "Text")` for a fixed label (re-translated live when the language changes).
* Add the French version to `htd/i18n/fr.py`. Anything missing simply shows in English.
* Phrases: add a line `(id, category, "Français", "English")` to `htd/i18n/phrases.py`
  (categories: mascot, quote, tip, action and the event ones).
* Spanish, Chinese, Japanese, Hindi, Arabic, Russian: add a row to `htd/i18n/world.py`
  (and to `phrases_world.py` for a phrase). An empty cell shows the English text.
* Another language: add a column (or a module like `fr.py`), register it in
  `htd/i18n/__init__.py` (`LANGUAGES`, `_TABLES`, and `RTL_LANGUAGES` if it is written
  right-to-left), and its fonts in `htd/ui/fonts.py`. The menu shows it automatically.

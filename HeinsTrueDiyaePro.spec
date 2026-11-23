# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller build for Windows (.exe in a folder) and macOS (.app). Build on each OS for that OS.

    pip install -r requirements.txt pyinstaller
    pyinstaller HeinsTrueDiyaePro.spec --noconfirm --clean

    (or simply run build_windows.bat / build_macos.sh)

Output: dist/HeinsTrueDiyaePro/HeinsTrueDiyaePro.exe   (Windows: ship the whole folder)
        dist/Heins True Diyae Pro.app                  (macOS)

Bundled: the assets/ folder (logo, mascot GIF...; htd/config.py finds it through
sys._MEIPASS), an optional bin/ folder (a static FFmpeg of your choice), the
FFmpeg binary of imageio-ffmpeg as a fallback, the PortAudio library of
sounddevice (audio playback), librosa's lazy-loading stubs and data, and the
third-party notices. The version comes from htd/config.py.

Icon: assets/logo.ico (Windows) / assets/logo.icns (macOS); otherwise
assets/logo.png is converted automatically (needs Pillow, already in requirements).

Projects: on macOS the .app declares the .htd document type (double-click opens
it); on Windows, "Open with" -> HeinsTrueDiyaePro.exe passes the file on the
command line, which the app opens too.
"""

import re
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs

ROOT = Path(SPECPATH)
NAME = "HeinsTrueDiyaePro"
VERSION = re.search(r'APP_VERSION\s*=\s*"([^"]+)"', (ROOT / "htd" / "config.py").read_text(encoding="utf-8")).group(1)

datas = [(str(ROOT / "assets"), "assets")]
for extra in ("THIRD_PARTY_NOTICES.md", "README.md", "LICENSE"):
    if (ROOT / extra).is_file():
        datas.append((str(ROOT / extra), "."))
if (ROOT / "bin").is_dir():
    datas.append((str(ROOT / "bin"), "bin"))
datas += collect_data_files("imageio_ffmpeg", subdir="binaries")   # fallback FFmpeg
datas += collect_data_files("librosa")                              # lazy-loader stubs (.pyi) + data
datas += collect_data_files("pyloudnorm")

# PortAudio for sounddevice: libportaudio64bit.dll (Windows) / libportaudio.dylib (macOS), kept in
# _sounddevice_data/portaudio-binaries/ where sounddevice looks for it in the built app.
try:
    binaries = collect_dynamic_libs("_sounddevice_data")
except Exception:  # noqa: BLE001 - package absent (Linux uses the system PortAudio)
    binaries = []
if sys.platform in ("win32", "darwin") and not binaries:
    raise SystemExit("PortAudio was not found: run  pip install -r requirements.txt  (sounddevice ships it).")


def _icon():
    assets = ROOT / "assets"
    native = assets / ("logo.ico" if sys.platform == "win32" else "logo.icns")
    if native.is_file():
        return str(native)
    if (assets / "logo.png").is_file() and sys.platform in ("win32", "darwin"):
        return str(assets / "logo.png")           # PyInstaller converts it with Pillow
    return None


icon = _icon()

a = Analysis(
    [str(ROOT / "main.py")],
    pathex=[str(ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=[
        "PySide6.QtMultimedia",          # audio-output change notifications
        "sounddevice",                   # preview player (PortAudio)
        "_sounddevice_data",
        "_cffi_backend",
        "htd.ui.audio_output",
        "htd.engine.render_service",     # off-GUI rendering in a separate process
        "htd.engine.cut",
        "htd.logging_setup",
        "multiprocessing",
        "multiprocessing.spawn",
        "htd.i18n.fr",                   # translations (plain modules, listed for clarity)
        "htd.i18n.world",
        "htd.i18n.phrases",
        "htd.i18n.phrases_world",
        "htd.engine.stereo",
        "librosa.core",                  # librosa loads these lazily: list what the engine uses
        "librosa.core.audio",
        "librosa.util",
        "librosa.filters",
        "lazy_loader",
        "soxr",
        "audioread",
        "scipy.signal",
        "scipy.ndimage",
        "scipy.interpolate",
        "scipy.fft",
        "soundfile",
        "pedalboard",
        "pedalboard.io",
        "matplotlib.backends.backend_agg",
        "PIL.Image",
    ],
    excludes=["tkinter", "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.Qt3DCore",
              "PySide6.QtQuick", "PySide6.QtQml", "IPython", "pytest"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=NAME,
    console=False,                       # no terminal window
    upx=False,                           # UPX-packed files trigger antivirus false alarms
    icon=icon,
)
coll = COLLECT(exe, a.binaries, a.datas, name=NAME, upx=False)

if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name="Heins True Diyae Pro.app",
        icon=icon,
        bundle_identifier="com.heinstruediyae.pro",
        version=VERSION,
        info_plist={
            "CFBundleShortVersionString": VERSION,
            "CFBundleVersion": VERSION,
            "NSHighResolutionCapable": True,
            "LSMinimumSystemVersion": "11.0",
            "CFBundleDevelopmentRegion": "fr",
            "CFBundleLocalizations": ["fr", "en", "es", "zh-Hans", "ja", "hi", "ar", "ru"],
            # .htd session files open in the app (double-click in the Finder)
            "CFBundleDocumentTypes": [{
                "CFBundleTypeName": "Heins True Diyae Project",
                "CFBundleTypeRole": "Editor",
                "LSHandlerRank": "Owner",
                "LSItemContentTypes": ["com.heinstruediyae.project"],
                "CFBundleTypeExtensions": ["htd"],
            }],
            "UTExportedTypeDeclarations": [{
                "UTTypeIdentifier": "com.heinstruediyae.project",
                "UTTypeDescription": "Heins True Diyae Project",
                "UTTypeConformsTo": ["public.json", "public.data"],
                "UTTypeTagSpecification": {"public.filename-extension": ["htd"]},
            }],
        },
    )

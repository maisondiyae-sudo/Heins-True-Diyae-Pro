#!/usr/bin/env bash
# Heins True Diyae Pro - Linux build (run from this folder: bash build_linux.sh)
# Result: dist/HeinsTrueDiyaePro-<version>-x86_64.AppImage
#
# One command does everything: virtual environment, packages, PyInstaller build,
# AppDir assembly, then the AppImage itself. Needs: Python 3.11-3.13, curl or
# wget, and the usual PySide6 runtime libraries on the build machine
# (Fedora: sudo dnf install portaudio xcb-util-cursor libxkbcommon-x11 libglvnd-egl libglvnd-glx
#  Debian: sudo apt install libportaudio2 libxcb-cursor0 libxkbcommon-x11-0 libgl1 libegl1)
#
# The AppImage bundles PortAudio and the xcb libraries Qt's platform plugin
# loads at runtime, so it also starts on machines that have none of them.

set -euo pipefail
cd "$(dirname "$0")"
ROOT=$(pwd -P)          # absolute: appimagetool needs an absolute SOURCE path

APP=HeinsTrueDiyaePro
SLUG=heins-true-diyae-pro
VERSION=$(sed -n 's/^APP_VERSION *= *"\([^"]*\)".*/\1/p' htd/config.py)
[ -n "$VERSION" ] || { echo "Could not read APP_VERSION from htd/config.py" >&2; exit 1; }

# --------------------------------------------------------------------------
# 1. Python 3.11-3.13 (PySide6 6.9.x does not support 3.14 yet)
# --------------------------------------------------------------------------
find_python() {
    if [ -n "${PYTHON:-}" ]; then echo "$PYTHON"; return; fi
    for candidate in python3.13 python3.12 python3.11 python3 python; do
        command -v "$candidate" >/dev/null 2>&1 || continue
        major=$("$candidate" -c 'import sys; print(sys.version_info[0])' 2>/dev/null) || continue
        minor=$("$candidate" -c 'import sys; print(sys.version_info[1])' 2>/dev/null) || continue
        if [ "$major" -eq 3 ] && [ "$minor" -ge 11 ] && [ "$minor" -le 13 ]; then
            echo "$candidate"; return
        fi
    done
    return 1
}

PY=$(find_python) || {
    echo "No Python 3.11-3.13 found." >&2
    echo "Install one (Fedora: sudo dnf install python3.12) or set PYTHON=/path/to/python3.12" >&2
    exit 1
}
echo "==> Python: $PY ($($PY -V 2>&1))"

if [ ! -d .venv ]; then
    "$PY" -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt pyinstaller

# --------------------------------------------------------------------------
# 2. PyInstaller onedir build -> dist/HeinsTrueDiyaePro/
# --------------------------------------------------------------------------
pyinstaller HeinsTrueDiyaePro.spec --noconfirm --clean

# --------------------------------------------------------------------------
# 3. Assemble the AppDir
# --------------------------------------------------------------------------
rm -rf AppDir
mkdir -p AppDir/usr/lib AppDir/usr/share/applications AppDir/usr/share/icons/hicolor/256x256/apps
cp -a "dist/$APP/." AppDir/usr/

install -m 755 packaging/linux/AppRun AppDir/AppRun
install -m 644 "packaging/linux/$SLUG.desktop" "AppDir/$SLUG.desktop"
cp "AppDir/$SLUG.desktop" AppDir/usr/share/applications/

# Square 256x256 icon from assets/logo.png (padded, never cropped).
python - "$SLUG" <<'PY'
import sys
from pathlib import Path
from PIL import Image

slug = sys.argv[1]
src = Image.open("assets/logo.png").convert("RGBA")
side = max(src.size)
square = Image.new("RGBA", (side, side), (0, 0, 0, 0))
square.paste(src, ((side - src.width) // 2, (side - src.height) // 2), src)
square.resize((256, 256), Image.LANCZOS).save(f"AppDir/{slug}.png", "PNG")
PY
cp "AppDir/$SLUG.png" AppDir/usr/share/icons/hicolor/256x256/apps/

# --------------------------------------------------------------------------
# 4. Bundle the libraries a host may not have
#    - libportaudio: playback (sounddevice loads it at runtime)
#    - the xcb pieces Qt's xcb platform plugin dlopens; without them the app
#      aborts with "could not load the Qt platform plugin xcb"
# --------------------------------------------------------------------------
bundle_lib() {
    local name=$1 path
    # No `exit` in awk: it would close the pipe, SIGPIPE ldconfig, and `pipefail`
    # would abort the build on a library that is actually found.
    path=$(ldconfig -p 2>/dev/null | awk -v n="$name" '!found && $1 == n { print $NF; found = 1 }') || path=""
    if [ -n "$path" ] && [ -f "$path" ]; then
        cp -L "$path" AppDir/usr/lib/
        echo "    bundled $name"
    else
        echo "    not on this machine, host must provide it: $name"
    fi
}
echo "==> Bundling runtime libraries"
for lib in \
    libportaudio.so.2 \
    libxcb-cursor.so.0 \
    libxcb-icccm.so.4 \
    libxcb-keysyms.so.1 \
    libxcb-randr.so.0 \
    libxcb-render-util.so.0 \
    libxcb-shape.so.0 \
    libxcb-xkb.so.1 \
    libxkbcommon-x11.so.0
do
    bundle_lib "$lib"
done

# --------------------------------------------------------------------------
# 5. Build the AppImage
# --------------------------------------------------------------------------
TOOLDIR=.cache/appimage
if command -v appimagetool >/dev/null 2>&1; then
    TOOL=appimagetool
else
    TOOL="$TOOLDIR/appimagetool-x86_64.AppImage"
    if [ ! -x "$TOOL" ]; then
        mkdir -p "$TOOLDIR"
        URL=https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-x86_64.AppImage
        echo "==> Downloading appimagetool"
        if command -v curl >/dev/null 2>&1; then
            curl -fL --retry 3 -o "$TOOL" "$URL"
        elif command -v wget >/dev/null 2>&1; then
            wget -O "$TOOL" "$URL"
        else
            echo "Need curl or wget to download appimagetool." >&2
            exit 1
        fi
        chmod +x "$TOOL"
    fi
fi

OUT="dist/$APP-$VERSION-x86_64.AppImage"
echo "==> Building $OUT"
# Absolute paths: appimagetool resolves SOURCE relative to its own working
# directory and fails with "ERROR: no such file or directory:" on a relative
# AppDir. APPIMAGE_EXTRACT_AND_RUN: works without FUSE (containers, some distros).
ARCH=x86_64 APPIMAGE_EXTRACT_AND_RUN=1 "$TOOL" --no-appstream "$ROOT/AppDir" "$ROOT/$OUT"

echo
echo "Build OK: $OUT ($(du -h "$OUT" | cut -f1))"
echo "Run it with:  ./$OUT"

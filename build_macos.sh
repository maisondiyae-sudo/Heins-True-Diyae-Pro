#!/usr/bin/env bash
# Heins True Diyae Pro - macOS build (run from this folder: bash build_macos.sh)
# Result: "dist/Heins True Diyae Pro.app"
#     and dist/HeinsTrueDiyaePro-<version>-macOS-AppleSilicon.dmg   (on an Apple Silicon Mac)
#      or dist/HeinsTrueDiyaePro-<version>-macOS-Intel.dmg          (on an Intel Mac)
#
# One command does everything: virtual environment, packages, PyInstaller build,
# ad-hoc signature, then a drag-and-drop installer (.dmg with a link to /Applications).
# PyInstaller builds for the Mac it runs on: build on Apple Silicon for Apple Silicon,
# on Intel for Intel. The GitHub workflow (.github/workflows/release.yml) builds both.
set -euo pipefail
cd "$(dirname "$0")"

APP_NAME="Heins True Diyae Pro"
APP="dist/$APP_NAME.app"
VERSION=$(sed -n 's/^APP_VERSION *= *"\([^"]*\)".*/\1/p' htd/config.py)
[ -n "$VERSION" ] || { echo "Could not read APP_VERSION from htd/config.py" >&2; exit 1; }

# --------------------------------------------------------------------------
# 1. Python 3.11-3.13 (PySide6 6.9.x does not support 3.14 yet)
# --------------------------------------------------------------------------
find_python() {
    if [ -n "${PYTHON:-}" ]; then echo "$PYTHON"; return; fi
    for candidate in python3.13 python3.12 python3.11 python3; do
        command -v "$candidate" >/dev/null 2>&1 || continue
        minor=$("$candidate" -c 'import sys; print(sys.version_info[1] if sys.version_info[0] == 3 else 0)' 2>/dev/null) || continue
        if [ "$minor" -ge 11 ] && [ "$minor" -le 13 ]; then
            echo "$candidate"; return
        fi
    done
    return 1
}
PY=$(find_python) || {
    echo "No Python 3.11-3.13 found. Install one (https://www.python.org or 'brew install python@3.12')" >&2
    echo "or set PYTHON=/path/to/python3.12" >&2
    exit 1
}
echo "==> Python: $PY ($("$PY" -V 2>&1))"

if [ ! -d .venv ]; then
    "$PY" -m venv .venv
fi
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt pyinstaller

# --------------------------------------------------------------------------
# 2. PyInstaller build -> dist/Heins True Diyae Pro.app
# --------------------------------------------------------------------------
pyinstaller HeinsTrueDiyaePro.spec --noconfirm --clean

# Ad-hoc signature (no Apple Developer ID). macOS then opens it on this Mac; on other
# Macs, macOS 15 (Sequoia) and later block the first launch: System Settings >
# Privacy & Security > "Open Anyway" (see README.md). Sign + notarize to avoid that.
codesign --force --deep --sign - "$APP"
codesign --verify --deep "$APP"

# --------------------------------------------------------------------------
# 3. Drag-and-drop installer: the app + a shortcut to /Applications, in a .dmg
# --------------------------------------------------------------------------
case "$(uname -m)" in
    arm64)  ARCH_LABEL=AppleSilicon ;;
    x86_64) ARCH_LABEL=Intel ;;
    *)      ARCH_LABEL=$(uname -m) ;;
esac
DMG="dist/HeinsTrueDiyaePro-$VERSION-macOS-$ARCH_LABEL.dmg"
STAGE="build/dmg"
rm -rf "$STAGE" "$DMG"
mkdir -p "$STAGE"
cp -R "$APP" "$STAGE/"
ln -s /Applications "$STAGE/Applications"

# hdiutil sometimes fails with "Resource busy" right after a build: retry a few times.
built=0
for attempt in 1 2 3 4 5; do
    if hdiutil create -volname "$APP_NAME" -srcfolder "$STAGE" -fs HFS+ -format UDZO -ov "$DMG"; then
        built=1; break
    fi
    echo "    hdiutil failed (attempt $attempt), retrying in 10 s..."
    sleep 10
done
[ "$built" -eq 1 ] || { echo "Could not create $DMG" >&2; exit 1; }
rm -rf "$STAGE"

echo
echo "Build OK: $APP"
echo "Installer: $DMG ($(du -h "$DMG" | cut -f1))"

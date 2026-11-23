#!/usr/bin/env bash
# Heins True Diyae Pro 2.0 - macOS build (run from this folder: bash build_macos.sh)
# Result: "dist/Heins True Diyae Pro.app"
set -euo pipefail
cd "$(dirname "$0")"
if [ ! -d .venv ]; then
    python3 -m venv .venv
fi
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt pyinstaller
pyinstaller HeinsTrueDiyaePro.spec --noconfirm --clean
# Ad-hoc signature so macOS opens it on this Mac (other Macs: right-click > Open the first time,
# or sign + notarize with an Apple Developer ID).
codesign --force --deep --sign - "dist/Heins True Diyae Pro.app"
echo
echo "Build OK: dist/Heins True Diyae Pro.app"

Free & Open Edition, by mo7amed illumyn diyae. Every feature unlocked, no licence key.
See README.md for what is new in this version.

## Download

| Your computer | File |
|---|---|
| Windows 10 / 11 (64-bit) | `HeinsTrueDiyaePro-<version>-Windows.zip` |
| Mac with an Apple chip (M1, M2, M3, M4...) | `HeinsTrueDiyaePro-<version>-macOS-AppleSilicon.dmg` |
| Mac with an Intel processor | `HeinsTrueDiyaePro-<version>-macOS-Intel.dmg` |
| Linux (x86_64) | `HeinsTrueDiyaePro-<version>-x86_64.AppImage` |

Not sure which Mac you have? Apple menu > About This Mac: "Chip" means Apple chip,
"Processor" means Intel. The Mac versions need macOS 14 (Sonoma) or later.

## First launch

The app is free and not signed with a paid Apple / Microsoft certificate, so the
system asks for confirmation the first time only.

**Windows**: right-click the .zip > *Extract All*, open the extracted folder and run
`HeinsTrueDiyaePro.exe` (it does not run from inside the .zip). If SmartScreen shows
"Windows protected your PC", click *More info* > *Run anyway*.

**macOS**: open the .dmg and drag *Heins True Diyae Pro* onto *Applications*. Open it
once from Applications; macOS blocks it. Then go to *System Settings > Privacy &
Security*, scroll down and click *Open Anyway* next to Heins True Diyae Pro, and
confirm. (Or, in Terminal:
`xattr -dr com.apple.quarantine "/Applications/Heins True Diyae Pro.app"`.)

**Linux**: make the file executable (`chmod +x HeinsTrueDiyaePro-*.AppImage`, or
*Properties > Allow executing as program*) and run it. Without FUSE:
`./HeinsTrueDiyaePro-*.AppImage --appimage-extract-and-run`.

FFmpeg is included in every download.

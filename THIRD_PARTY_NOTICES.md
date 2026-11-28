# Third-party software

Heins True Diyae Pro 2.2.3 (Free & Open Edition) — © 2026 mo7amed illumyn diyae —
is built on these open-source projects. Their licences travel with the standalone
app (PyInstaller copies each package's own licence files where the package ships
them).

| Project | Used for | Licence |
|---|---|---|
| PySide6 / Qt 6 | interface | LGPL-3.0 (Qt for Python) |
| sounddevice | audio playback (Python side) | MIT |
| PortAudio | audio output (bundled by sounddevice on Windows / macOS) | PortAudio licence (MIT-style) |
| CFFI | sounddevice's link to PortAudio | MIT |
| NumPy | arrays, maths | BSD-3-Clause |
| SciPy | filters, FFT, resampling, stereo analysis | BSD-3-Clause |
| librosa | audio loading fallback, resampling | ISC |
| soundfile / libsndfile | WAV / FLAC reading and writing | BSD-3-Clause / LGPL-2.1 |
| pedalboard (Spotify) | mastering effects chain | **GPL-3.0** |
| pyloudnorm | LUFS loudness (ITU-R BS.1770) | MIT |
| Matplotlib | spectrograms, tonal-balance charts | Matplotlib licence (PSF-based) |
| Pillow | cover art, video frame | MIT-CMU (HPND) |
| imageio-ffmpeg | ready-made FFmpeg binary | BSD-2-Clause (wrapper) |
| FFmpeg | decoding, MP3 / AAC / FLAC encoding, tags, clip video | LGPL-2.1+ or GPL-2.0+ depending on the build (builds with libx264, used for the vertical video, are GPL) |

## Licence of the app itself

Because the mastering chain uses **pedalboard (GPL-3.0)**, the application as a
whole is distributed under the **GNU GPL-3.0** (see the `LICENSE` file), and the
source code (this project) is shared alongside every download.

## FFmpeg source offer

The standalone builds bundle an FFmpeg binary (via `imageio-ffmpeg`, or one you
place in `bin/`). FFmpeg is free software under the LGPL-2.1+ / GPL-2.0+; builds
that enable GPL components such as libx264 are GPL. In accordance with those
licences, the complete corresponding source code of the exact FFmpeg build that
is shipped, together with its build instructions, is available on request from
the author (mo7amed illumyn diyae) for at least three years, and from the
upstream projects:

* FFmpeg: <https://ffmpeg.org/download.html> (source) and <https://git.ffmpeg.org/ffmpeg.git>
* imageio-ffmpeg builds: <https://github.com/imageio/imageio-ffmpeg>

This file is information, not legal advice.

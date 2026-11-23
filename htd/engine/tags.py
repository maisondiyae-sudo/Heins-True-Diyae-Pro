"""
Tags and cover art, written by FFmpeg (no extra library needed).

* MP3  - ID3v2.3: title, artist, album, year, genre, track, BPM (TBPM),
         key (TKEY) and the cover (APIC, front cover);
* M4A  - title, artist, album, year, genre, track + cover;
* FLAC - Vorbis comments incl. BPM / INITIALKEY + cover picture;
* WAV  - RIFF INFO: title, artist, album, genre, year (WAV has no cover).

Covers are prepared with Pillow: EXIF rotation applied, centre-cropped to a
square, RGB JPEG. The embedded copy is at most 1400 px (keeps files light);
the copy saved in release packs keeps up to 3000 px.
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple

from .core import SUBPROCESS_FLAGS

EMBED_SIZE = 1400
FULL_SIZE = 3000

# Start every output from a blank container: no source metadata, no chapters, and no
# encoder / muxer signature (no "Lavf", "ISFT", "encoder", creation_time...). Only the
# fields the user filled in are written afterwards. Used by every FFmpeg export command.
CLEAN_CONTAINER_ARGS = ["-map_metadata", "-1", "-map_chapters", "-1",
                        "-fflags", "+bitexact", "-flags:a", "+bitexact"]


@dataclass(frozen=True)
class TagSet:
    title: str = ""
    artist: str = ""
    album: str = ""
    year: str = ""
    genre: str = ""
    track: str = ""                 # "3/12" or ""
    bpm: Optional[int] = None
    key: str = ""                   # short notation: "Cm", "F#"
    cover: Optional[str] = None     # prepared JPEG to embed

    def is_empty(self) -> bool:
        """True when the user set no tag and no cover (nothing to write)."""
        return not any((self.title, self.artist, self.album, self.year, self.genre,
                        self.track, self.bpm, self.key, self.cover))


def metadata_args(tags: TagSet, fmt_key: str) -> List[str]:
    """``-metadata`` options for one output format."""
    fields = [("title", tags.title), ("artist", tags.artist), ("album", tags.album),
              ("date", tags.year), ("genre", tags.genre)]
    if fmt_key != "wav":
        fields.append(("track", tags.track))
    if fmt_key == "mp3":
        fields += [("TBPM", str(tags.bpm) if tags.bpm else ""), ("TKEY", tags.key)]
    elif fmt_key == "flac":
        fields += [("BPM", str(tags.bpm) if tags.bpm else ""), ("INITIALKEY", tags.key)]
    args: List[str] = []
    for name, value in fields:
        if value:
            args += ["-metadata", f"{name}={value}"]
    # Only force an ID3v2.3 container when there is something to carry (a field or a cover):
    # on a blank mp3, writing an empty ID3 tag would re-introduce a default TSSE/encoder stamp.
    if fmt_key == "mp3" and (args or tags.cover):
        args += ["-id3v2_version", "3"]
    return args


def cover_inputs(tags: Optional[TagSet], fmt_key: str) -> Tuple[List[str], List[str]]:
    """(extra input args, mapping/codec args) that embed the cover, or ([], [])."""
    if tags is None or not tags.cover or fmt_key not in ("mp3", "m4a", "flac") or not os.path.isfile(tags.cover):
        return [], []
    inputs = ["-i", tags.cover]
    mapping = ["-map", "1:v:0", "-c:v", "copy", "-disposition:v:0", "attached_pic"]
    if fmt_key == "mp3":
        mapping += ["-metadata:s:v", "title=Album cover"]      # standard APIC description, no "comment"
    return inputs, mapping


def run_ffmpeg(args: List[str], what: str, timeout: float = 1800) -> None:
    result = subprocess.run(args, capture_output=True, timeout=timeout, check=False,
                            creationflags=SUBPROCESS_FLAGS)
    if result.returncode != 0:
        message = result.stderr.decode("utf-8", "replace").strip()[-400:]
        raise RuntimeError(f"FFmpeg could not {what}: {message or result.returncode}")


def retag_copy(ffmpeg: str, source: Path, destination: Path, tags: TagSet, fmt_key: str) -> None:
    """Copy the audio stream unchanged into a blank container and add only the user's tags
    (+ cover where the format allows it); no source metadata, no software signature."""
    extra_inputs, cover_map = cover_inputs(tags, fmt_key)
    args = [ffmpeg, "-nostdin", "-hide_banner", "-loglevel", "error", "-y", "-i", str(source),
            *extra_inputs, "-map", "0:a:0", "-c:a", "copy", *cover_map,
            *CLEAN_CONTAINER_ARGS, *metadata_args(tags, fmt_key), str(destination)]
    run_ffmpeg(args, "write the tags")


# ---------------------------------------------------------------------- cover
@dataclass(frozen=True)
class CoverFiles:
    embed: Path          # <= 1400 px JPEG, embedded in the audio files
    full: Path           # <= 3000 px JPEG, copied into release packs
    size: Tuple[int, int]


def prepare_cover(source: Path, work_dir: Path) -> CoverFiles:
    """Square JPEG versions of the cover image (raises ValueError if it cannot be read)."""
    try:
        from PIL import Image, ImageOps
    except ImportError as exc:                       # Pillow missing: use the file as it is
        if source.suffix.lower() in (".jpg", ".jpeg", ".png"):
            return CoverFiles(source, source, (0, 0))
        raise ValueError("Install Pillow to use this cover image format.") from exc
    try:
        with Image.open(source) as image:
            image = ImageOps.exif_transpose(image)
            image = image.convert("RGB")
            side = min(image.size)
            left, top = (image.width - side) // 2, (image.height - side) // 2
            square = image.crop((left, top, left + side, top + side))
    except OSError as exc:
        raise ValueError(f"The cover image could not be read ({exc}).") from exc
    work_dir.mkdir(parents=True, exist_ok=True)
    stem = f"cover-{abs(hash((str(source), source.stat().st_mtime))) % 10**10}"
    full = work_dir / f"{stem}-full.jpg"
    embed = work_dir / f"{stem}-embed.jpg"
    resample = getattr(Image, "Resampling", Image).LANCZOS
    (square if side <= FULL_SIZE else square.resize((FULL_SIZE, FULL_SIZE), resample)).save(
        full, "JPEG", quality=95, optimize=True)
    (square if side <= EMBED_SIZE else square.resize((EMBED_SIZE, EMBED_SIZE), resample)).save(
        embed, "JPEG", quality=90, optimize=True)
    return CoverFiles(embed, full, (side, side))

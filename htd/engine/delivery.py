"""
Delivering masters: single-format exports, the "Release pack", tags, cover,
BPM / key in file names and the social clip.

Release pack (one folder per track):
    <Title>_HTD_<preset>/
        <Title>.wav                     WAV 24-bit (RIFF INFO tags)
        <Title>.mp3                     MP3 320 kbps, ID3v2.3 + cover
        cover.jpg                       square cover, up to 3000 px (if a cover was chosen)
        <Title>_clip30s.m4a             social clip (if enabled)
        <Title>_clip30s_vertical.mp4    vertical video (if enabled and a cover was chosen)
        <Title> - info.txt              title, BPM, key, loudness, true peak, settings

Re-exporting the same track to the same place (for example after changing a
tag) replaces the files this session wrote there instead of piling up copies.
Files that already exist otherwise follow ``ExportOptions.on_conflict``:
"rename" (name_2, name_3...), "overwrite" or "skip".
"""

from __future__ import annotations

import re
import shutil
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .. import config
from .analysis import describe_key
from .clip import choose_window, render_clip, render_video
from .export import FORMATS, ExportError, clean_stem, unique_path, write_format
from .ffmpeg_tools import FfmpegInfo
from .pipeline import TrackResult
from .tags import CoverFiles, TagSet, prepare_cover

PACK_KEY = "pack"
CONFLICT_POLICIES = ("rename", "overwrite", "skip")
PACK_LABEL = "Release pack (WAV 24-bit + MP3 320 + cover)"
CLIP_LENGTHS = (15, 30, 45, 60)


def export_choices() -> List[Tuple[str, str]]:
    return [(key, fmt.label) for key, fmt in FORMATS.items()] + [(PACK_KEY, PACK_LABEL)]


@dataclass(frozen=True)
class TagInfo:
    artist: str = ""
    album: str = ""
    year: str = ""
    genre: str = ""
    cover: str = ""                 # image path, "" = none
    cover_stamp: float = 0.0        # mtime, so a replaced image counts as a change


@dataclass(frozen=True)
class ClipOptions:
    enabled: bool = False
    seconds: int = 30
    mode: str = "auto"              # "auto" (most energetic part) | "start"
    video: bool = False


@dataclass(frozen=True)
class ExportOptions:
    fmt_key: str = "wav24"
    out_dir: str = ""               # "" = next to each source file
    name_bpm_key: bool = False
    tags: TagInfo = TagInfo()
    clip: ClipOptions = ClipOptions()
    subfolder_per_mode: bool = False  # <folder>/<preset>/...
    on_conflict: str = "rename"       # see CONFLICT_POLICIES
    strip_metadata: bool = False      # write a 100% blank file: no tags, no cover at all

    def folder(self) -> Optional[Path]:
        return Path(self.out_dir) if self.out_dir else None

    @property
    def label(self) -> str:
        return PACK_LABEL if self.fmt_key == PACK_KEY else FORMATS[self.fmt_key].label


@dataclass(frozen=True)
class TrackMeta:
    title: str
    bpm: Optional[int] = None
    key: str = ""
    beat_offset_s: Optional[float] = None     # only valid for the detected BPM
    track_no: int = 0
    track_total: int = 0


@dataclass
class ExportRecord:
    signature: tuple
    main: Path                                  # the file, or the pack folder
    files: List[Path] = field(default_factory=list)
    skipped: bool = False                       # a file already existed and the policy is "skip"

    def complete(self) -> bool:
        return self.main.exists() and all(path.exists() for path in self.files)


def default_title(source: Path) -> str:
    """'my_track-final_v2.wav' -> 'my track-final v2'."""
    return re.sub(r"\s+", " ", source.stem.replace("_", " ")).strip() or source.stem


def _slot(options: ExportOptions) -> Tuple[str, str]:
    where = str(Path(options.out_dir).resolve()) if options.out_dir else "<next to source>"
    return options.fmt_key, where + ("/<mode>" if options.subfolder_per_mode else "")


def _signature(result: TrackResult, options: ExportOptions, meta: TrackMeta) -> tuple:
    """What the files depend on (the conflict policy only decides how a clash is handled)."""
    return (result.settings.key() if result.settings else None, replace(options, on_conflict=""), meta)


def find_export(result: TrackResult, options: ExportOptions, meta: TrackMeta) -> Optional[ExportRecord]:
    """The export matching these options and metadata, if it was written and still exists."""
    record = result.exports.get(_slot(options))
    if isinstance(record, ExportRecord) and record.signature == _signature(result, options, meta) \
            and record.complete():
        return record
    return None


def latest_export(result: TrackResult) -> Optional[Path]:
    paths = [record.main for record in result.exports.values()
             if isinstance(record, ExportRecord) and not record.skipped and record.main.exists()]
    return paths[-1] if paths else None


def base_name(result: TrackResult, meta: TrackMeta, options: ExportOptions) -> str:
    base = clean_stem((meta.title or default_title(result.source)) + ".x")
    if options.name_bpm_key:
        if meta.bpm:
            base += f"_{meta.bpm}BPM"
        if meta.key:
            base += f"_{meta.key}"
    return base


def _preset_slug(result: TrackResult) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "-", result.settings.label).strip("-") or "master"


_cover_cache: Dict[Tuple[str, float], CoverFiles] = {}


def _cover(options: ExportOptions, work_dir: Path) -> Optional[CoverFiles]:
    if not options.tags.cover:
        return None
    source = Path(options.tags.cover)
    if not source.is_file():
        raise ExportError(f"The cover image was not found: {source}")
    key = (str(source), options.tags.cover_stamp)
    if key not in _cover_cache or not _cover_cache[key].embed.exists():
        try:
            _cover_cache[key] = prepare_cover(source, work_dir)
        except ValueError as exc:
            raise ExportError(str(exc)) from exc
    return _cover_cache[key]


def tag_set(options: ExportOptions, meta: TrackMeta, cover: Optional[CoverFiles]) -> TagSet:
    info = options.tags
    track = f"{meta.track_no}/{meta.track_total}" if info.album and meta.track_no else ""
    return TagSet(title=meta.title, artist=info.artist, album=info.album, year=info.year,
                  genre=info.genre, track=track, bpm=meta.bpm, key=meta.key,
                  cover=str(cover.embed) if cover else None)


def _kept_s(result: TrackResult) -> float:
    return result.cut.length_s if result.cut is not None else result.duration_s


def _info_text(result: TrackResult, options: ExportOptions, meta: TrackMeta, files: List[Path]) -> str:
    master, report = result.mastered_metrics, result.master_report
    key_long, camelot = describe_key(meta.key)
    lines = [
        f"Title:      {meta.title}",
        f"Artist:     {options.tags.artist}",
        f"Album:      {options.tags.album}",
        f"Year:       {options.tags.year}",
        f"Genre:      {options.tags.genre}",
        f"BPM:        {meta.bpm or '-'}",
        f"Key:        {key_long or '-'}{f' ({camelot})' if camelot else ''}",
        f"Duration:   {int(result.duration_s // 60)}:{int(result.duration_s % 60):02d}"
        + (f" (cut {result.cut.start_s:.2f} s -> {result.cut.end_s:.2f} s)" if result.cut else "")
        + (f" (after trim: {(_kept_s(result) - result.trim.start_s - result.trim.end_s):.1f} s)"
           if result.trim and result.trim.changed else ""),
        f"Loudness:   {master.lufs:.1f} LUFS integrated, true peak {master.true_peak_db:.2f} dBTP",
        f"Mastering:  {result.settings.label} ({result.settings.recipe} recipe), "
        f"target {report.target_lufs:g} LUFS / ceiling {report.target_true_peak_db:g} dBTP",
    ]
    if result.match is not None:
        lines.append(f"Reference:  {result.match.reference}")
    lines += ["", "Files:"] + [f"  {path.name}" for path in files]
    lines += ["", f"Made with {config.APP_NAME} v{config.APP_VERSION}"]
    return "\n".join(lines) + "\n"


def _remove_previous(result: TrackResult, options: ExportOptions) -> None:
    """Delete what this session wrote for the same slot (it is being replaced)."""
    record = result.exports.pop(_slot(options), None)
    if not isinstance(record, ExportRecord) or record.skipped:      # a skipped file is not ours
        return
    for path in record.files:
        try:
            path.unlink()
        except OSError:
            pass
    if record.main.is_dir():
        try:
            record.main.rmdir()                  # only if empty: never delete foreign files
        except OSError:
            pass


class _Skip(Exception):
    """The target already exists and the policy is 'skip'."""

    def __init__(self, path: Path) -> None:
        super().__init__(str(path))
        self.path = path


def _target(path: Path, policy: str) -> Path:
    """Where to write ``path`` under the conflict policy."""
    if policy == "overwrite" or not path.exists():
        return path
    if policy == "skip":
        raise _Skip(path)
    return unique_path(path)


def _clip(result: TrackResult, options: ExportOptions, meta: TrackMeta, folder: Path, stem: str,
          ffmpeg: FfmpegInfo, tags: TagSet, cover: Optional[CoverFiles], work_dir: Path) -> List[Path]:
    """Social clip (+ vertical video) next to the other files. Returns the written paths."""
    import soundfile as sf

    audio, sample_rate = sf.read(str(result.master_cache), dtype="float32", always_2d=True)
    offset = meta.beat_offset_s
    if offset is not None and (result.trim is not None or result.cut is not None):   # beats: on the whole original
        offset = offset - result.master_offset_samples() / 44_100.0
        if meta.bpm:
            offset %= 60.0 / meta.bpm
    window = choose_window(audio, sample_rate, options.clip.seconds, options.clip.mode,
                           meta.bpm, offset if meta.bpm else None)
    del audio
    label = f"clip{options.clip.seconds}s"
    written: List[Path] = []
    try:
        clip_path = _target(folder / f"{stem}_{label}.m4a", options.on_conflict)
    except _Skip:
        return written
    render_clip(result.master_cache, window, clip_path, ffmpeg.path, tags, work_dir)
    written.append(clip_path)
    if options.clip.video and cover is not None and ffmpeg.video_encoder:
        try:
            video_path = _target(folder / f"{stem}_{label}_vertical.mp4", options.on_conflict)
        except _Skip:
            return written
        render_video(cover.full, clip_path, video_path, ffmpeg.path, ffmpeg.video_encoder,
                     window.length_s, work_dir)
        written.append(video_path)
    return written


def export_track(result: TrackResult, options: ExportOptions, meta: TrackMeta,
                 ffmpeg: Optional[FfmpegInfo], work_dir: Path) -> ExportRecord:
    """Write the deliverables for one mastered track; returns what was written."""
    if not result.ok or result.master_cache is None or result.settings is None:
        raise ExportError("Only a mastered track can be exported.")
    needs_ffmpeg = options.fmt_key == PACK_KEY or FORMATS[options.fmt_key].needs_ffmpeg or options.clip.enabled
    if needs_ffmpeg and ffmpeg is None:
        raise ExportError("This export needs FFmpeg, which was not found.")
    if options.fmt_key in ("mp3", PACK_KEY) and ffmpeg is not None and not ffmpeg.has_mp3:
        raise ExportError("This FFmpeg build has no MP3 encoder (libmp3lame).")

    _remove_previous(result, options)
    cover = None if options.strip_metadata else _cover(options, work_dir)
    tags = TagSet() if options.strip_metadata else tag_set(options, meta, cover)
    ffmpeg_path = ffmpeg.path if ffmpeg else None
    folder = options.folder() or result.source.parent
    if options.subfolder_per_mode:
        folder = folder / _preset_slug(result)
    base = base_name(result, meta, options)
    files: List[Path] = []
    created_dir: Optional[Path] = None
    try:
        if options.fmt_key == PACK_KEY:
            main = _target(folder / f"{base}_HTD_{_preset_slug(result)}", options.on_conflict)
            if not main.exists():
                main.mkdir(parents=True)
                created_dir = main
            files.append(write_format(result.master_cache, "wav24", main / f"{base}.wav", ffmpeg_path, tags))
            files.append(write_format(result.master_cache, "mp3", main / f"{base}.mp3", ffmpeg_path, tags))
            if cover is not None:
                shutil.copyfile(cover.full, main / "cover.jpg")
                files.append(main / "cover.jpg")
            if options.clip.enabled:
                files += _clip(result, options, meta, main, base, ffmpeg, tags, cover, work_dir)
            info = main / f"{base} - info.txt"
            info.write_text(_info_text(result, options, meta, files), encoding="utf-8")
            files.append(info)
        else:
            fmt = FORMATS[options.fmt_key]
            stem = f"{base}_HTD_{_preset_slug(result)}"
            target = _target(folder / f"{stem}.{fmt.ext}", options.on_conflict)
            target.parent.mkdir(parents=True, exist_ok=True)
            main = write_format(result.master_cache, options.fmt_key, target, ffmpeg_path, tags)
            files.append(main)
            if options.clip.enabled:
                files += _clip(result, options, meta, folder, stem, ffmpeg, tags, cover, work_dir)
    except _Skip as skipped:
        _cleanup(files, created_dir)
        record = ExportRecord(_signature(result, options, meta), skipped.path, [], skipped=True)
        result.exports[_slot(options)] = record
        return record
    except ExportError:
        _cleanup(files, created_dir)
        raise
    except (OSError, RuntimeError, ValueError) as exc:
        _cleanup(files, created_dir)
        raise ExportError(str(exc)) from exc

    record = ExportRecord(_signature(result, options, meta), main, files)
    result.exports[_slot(options)] = record
    return record


def _cleanup(files: List[Path], created_dir: Optional[Path] = None) -> None:
    """Remove what a failed export wrote, so no half-finished pack is left behind."""
    for path in files:
        try:
            path.unlink()
        except OSError:
            pass
    if created_dir is not None:
        try:
            created_dir.rmdir()
        except OSError:
            pass

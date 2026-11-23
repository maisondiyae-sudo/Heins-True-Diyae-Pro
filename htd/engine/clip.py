"""
Short social-media clips (TikTok / Reels / Shorts) cut from the master.

* "auto" picks the most energetic part of the track (usually the chorus or
  the drop): the energy above 120 Hz is summed over every possible window;
* with a known tempo the clip starts on a beat and lasts a whole number of
  bars (so it loops and ends musically), as close as possible to the asked length;
* a short fade-in (unless the clip starts at 0:00) and a longer fade-out;
* audio: M4A / AAC 256 kbps with the tags and cover;
* optional vertical video 1080 x 1920 (cover on a blurred copy of itself),
  H.264 + AAC, ready to upload.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np
import scipy.signal as sps
import soundfile as sf

from .tags import CLEAN_CONTAINER_ARGS, TagSet, cover_inputs, metadata_args, run_ffmpeg

FADE_IN_S = 0.25
FADE_OUT_S = 1.5
VIDEO_SIZE = (1080, 1920)


@dataclass(frozen=True)
class ClipWindow:
    start_s: float
    end_s: float

    @property
    def length_s(self) -> float:
        return self.end_s - self.start_s


def choose_window(audio: np.ndarray, sample_rate: int, seconds: float, mode: str = "auto",
                  bpm: Optional[float] = None, beat_offset_s: Optional[float] = None) -> ClipWindow:
    """Where to cut a ``seconds``-long clip in ``audio`` (n_samples, n_channels)."""
    duration = audio.shape[0] / sample_rate
    length = float(seconds)
    bar = 4 * 60.0 / bpm if bpm else None
    if bar:
        length = max(bar, math.floor(length / bar + 1e-6) * bar)
    if duration <= length:
        return ClipWindow(0.0, duration)
    if mode != "auto":
        return ClipWindow(0.0, length)

    hop_s = 0.1
    mono = audio.mean(axis=1) if audio.ndim == 2 else audio
    sos = sps.butter(2, 120.0, btype="highpass", fs=sample_rate, output="sos")
    filtered = sps.sosfilt(sos, mono.astype(np.float64))
    hop = int(sample_rate * hop_s)
    frames = filtered[: (filtered.size // hop) * hop].reshape(-1, hop)
    energy = (frames ** 2).mean(axis=1)
    window = int(round(length / hop_s))
    if window >= energy.size:
        return ClipWindow(0.0, length)
    sums = np.convolve(energy, np.ones(window), mode="valid")
    start = float(np.argmax(sums)) * hop_s

    if bpm and beat_offset_s is not None:                # start on the beat just before
        period = 60.0 / bpm
        beats = math.floor((start - beat_offset_s) / period)
        start = max(0.0, beat_offset_s + beats * period)
    start = min(start, duration - length)
    return ClipWindow(start, start + length)


def _faded(segment: np.ndarray, sample_rate: int, fade_in: bool) -> np.ndarray:
    out = segment.astype(np.float32, copy=True)
    n = out.shape[0]
    fade_out = min(int(FADE_OUT_S * sample_rate), n // 3)
    if fade_out:
        out[-fade_out:] *= np.linspace(1.0, 0.0, fade_out, dtype=np.float32)[:, None] ** 2
    fade_in_n = min(int((FADE_IN_S if fade_in else 0.005) * sample_rate), n // 3)
    if fade_in_n:
        out[:fade_in_n] *= np.linspace(0.0, 1.0, fade_in_n, dtype=np.float32)[:, None]
    return out


def render_clip(master_cache: Path, window: ClipWindow, destination: Path, ffmpeg: str,
                tags: Optional[TagSet], work_dir: Path) -> Path:
    """Cut, fade and encode the clip as M4A (AAC 256 kbps) with tags and cover."""
    with sf.SoundFile(str(master_cache)) as handle:
        sample_rate = int(handle.samplerate)
        handle.seek(int(window.start_s * sample_rate))
        segment = handle.read(int(window.length_s * sample_rate), dtype="float32", always_2d=True)
    temp = work_dir / f"clip-{destination.stem[:40]}-{abs(hash(str(destination))) % 10**8}.wav"
    sf.write(str(temp), _faded(segment, sample_rate, window.start_s > 0), sample_rate,
             subtype="FLOAT", format="WAV")
    partial = destination.with_name(f".{destination.stem}.partial{destination.suffix}")
    try:
        extra_inputs, cover_map = cover_inputs(tags, "m4a")
        args = [ffmpeg, "-nostdin", "-hide_banner", "-loglevel", "error", "-y", "-i", str(temp),
                *extra_inputs, "-map", "0:a:0", *cover_map, "-c:a", "aac", "-b:a", "256k",
                "-movflags", "+faststart", *CLEAN_CONTAINER_ARGS,
                *(metadata_args(tags, "m4a") if tags else []), str(partial)]
        run_ffmpeg(args, "encode the clip")
        partial.replace(destination)
    finally:
        for path in (temp, partial):
            try:
                path.unlink()
            except OSError:
                pass
    return destination


def make_video_frame(cover: Path, destination: Path) -> Path:
    """1080 x 1920 still: blurred, darkened cover as background + the sharp square cover."""
    try:
        from PIL import Image, ImageEnhance, ImageFilter
    except ImportError as exc:
        raise RuntimeError("The vertical video needs Pillow: pip install Pillow") from exc

    width, height = VIDEO_SIZE
    with Image.open(cover) as image:
        image = image.convert("RGB")
        scale = max(width / image.width, height / image.height)
        background = image.resize((math.ceil(image.width * scale), math.ceil(image.height * scale)))
        left = (background.width - width) // 2
        top = (background.height - height) // 2
        background = background.crop((left, top, left + width, top + height))
        background = background.filter(ImageFilter.GaussianBlur(40))
        background = ImageEnhance.Brightness(background).enhance(0.55)
        side = int(width * 0.86)
        front = image.resize((side, side))
        background.paste(front, ((width - side) // 2, (height - side) // 2))
        background.save(destination, "PNG")
    return destination


def render_video(cover: Path, clip_audio: Path, destination: Path, ffmpeg: str,
                 encoder: str, seconds: float, work_dir: Path) -> Path:
    """Vertical MP4 (H.264 + the clip's AAC audio) from a still frame."""
    frame = make_video_frame(cover, work_dir / f"frame-{abs(hash(str(destination))) % 10**8}.png")
    codec = {
        "libx264": ["-c:v", "libx264", "-preset", "veryfast", "-tune", "stillimage", "-crf", "20"],
        "h264_videotoolbox": ["-c:v", "h264_videotoolbox", "-b:v", "6M"],
        "h264_mf": ["-c:v", "h264_mf", "-b:v", "6M"],
        "mpeg4": ["-c:v", "mpeg4", "-q:v", "3"],
    }[encoder]
    partial = destination.with_name(f".{destination.stem}.partial{destination.suffix}")
    try:
        args = [ffmpeg, "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
                "-loop", "1", "-framerate", "30", "-i", str(frame), "-i", str(clip_audio),
                "-map", "0:v:0", "-map", "1:a:0", *codec, "-pix_fmt", "yuv420p", "-r", "30",
                "-c:a", "copy", *CLEAN_CONTAINER_ARGS, "-t", f"{seconds:.3f}", "-shortest", "-movflags", "+faststart",
                str(partial)]
        run_ffmpeg(args, "make the video", timeout=900)
        partial.replace(destination)
    finally:
        for path in (frame, partial):
            try:
                path.unlink()
            except OSError:
                pass
    return destination

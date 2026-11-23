#!/usr/bin/env python3
"""Metadata hygiene: every audio export starts from a blank container (v2.2.1).

Checks that no source tag (old title/comment/artist/date/genre), no chapter and no
automatic software signature (encoder / Lavf / ISFT / TSSE / app name) ever survives into
a Mastering export, a release Pack, a clip or a Converter output - and that a "blank"
export (empty TagSet or the "Export without metadata" option) writes the audio only.

Run it from anywhere:  python tests/test_metadata_clean.py
Needs only the project's own dependencies (numpy, scipy, soundfile) plus ffmpeg/ffprobe,
exactly what the app already requires - no test harness, no Qt.
"""
import sys, os, json, shutil, tempfile, subprocess
from pathlib import Path

# Import the package from the project root (parent of this tests/ folder).
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from htd.engine import ffmpeg_tools, pipeline, presets, delivery, converter
import htd.engine.tags as tagsmod
import htd.engine.export as exportmod
from htd.engine.tags import TagSet, metadata_args, cover_inputs, retag_copy
from htd.engine.export import write_format
from htd.engine.delivery import ExportOptions, TrackMeta, TagInfo, export_track

ok = True
def check(name, cond, detail=""):
    global ok; ok &= bool(cond)
    print(("PASS " if cond else "FAIL ") + name + ("  " + str(detail) if detail else ""))

info = ffmpeg_tools.install_resolver()
FFMPEG = info.path
FFPROBE = shutil.which("ffprobe") or str(Path(FFMPEG).with_name("ffprobe"))
root = Path(tempfile.mkdtemp(prefix="htd-meta-"))

# Parasitic tag values deliberately planted on the source files.
PARASITES = ("OLDTITLE", "PARASITE", "GHOST", "1999", "NoiseGenre", "ParasiteChap")
# Keys that carry user/source *content* - must be absent from a blank export.
CONTENT_KEYS = {"title", "comment", "artist", "album", "album_artist", "composer",
                "date", "year", "genre", "track", "description", "copyright"}
# The app / default-comment stamps that must NEVER appear on ANY export.
APP_SUBSTR = ("isft", "tsse", "software", "heinstruediyae", "heins true diyae", "cover (front)")
# Stricter, for the container-metadata formats (WAV / FLAC / M4A): no FFmpeg muxer stamp.
FFMPEG_SIG_SUBSTR = APP_SUBSTR + ("lavf", "libebur")


def _probe(path):
    out = subprocess.run([FFPROBE, "-hide_banner", "-loglevel", "error", "-show_format",
                          "-show_streams", "-show_chapters", "-of", "json", str(path)],
                         capture_output=True, text=True)
    return json.loads(out.stdout or "{}")


def _tags(path):
    d = _probe(path)
    fmt = {k.lower(): v for k, v in (d.get("format", {}).get("tags", {}) or {}).items()}
    streams = [{k.lower(): v for k, v in (s.get("tags", {}) or {}).items()}
               for s in d.get("streams", [])]
    return fmt, streams, len(d.get("chapters", []) or [])


def _values(fmt, streams):
    vals = list(fmt.values())
    for s in streams:
        vals += list(s.values())
    return [str(v).lower() for v in vals]


def app_free(path):
    fmt, streams, _ = _tags(path)
    if "software" in (set(fmt) | {k for s in streams for k in s}):
        return False
    return not any(sub in v for v in _values(fmt, streams) for sub in APP_SUBSTR)


def ffmpeg_sig_free(path):
    if not app_free(path):
        return False
    fmt, streams, _ = _tags(path)
    if "encoder" in (set(fmt) | {k for s in streams for k in s}):
        return False
    return not any(sub in v for v in _values(fmt, streams) for sub in FFMPEG_SIG_SUBSTR)


def mp3_id3_clean(path):
    """MP3's ID3 block (format tags) carries no content and no software stamp. Its standard
    Xing/Info header may still hold a version-less 'Lavf lame' string inside the audio
    stream - unavoidable without dropping gapless/duration info - which is out of scope."""
    fmt, _, chapters = _tags(path)
    if chapters or (fmt.keys() & (CONTENT_KEYS | {"encoder", "software"})):
        return False
    return app_free(path)


def no_source_tags(path):
    fmt, streams, chapters = _tags(path)
    if chapters:
        return False
    return not any(p.lower() in v for v in _values(fmt, streams) for p in PARASITES)


def blank(path):
    fmt, streams, chapters = _tags(path)
    keys = set(fmt) | {k for s in streams for k in s}
    return not (keys & CONTENT_KEYS) and chapters == 0


def tone(path, codec, dur=2.0, freq=440, parasites=False):
    """A tone in the given format, optionally wrapped with planted tags + a chapter."""
    cmd = [FFMPEG, "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
           "-f", "lavfi", "-i", f"sine=frequency={freq}:duration={dur}"]
    if parasites:
        chap = root / "chap.txt"
        chap.write_text(";FFMETADATA1\ntitle=OLDTITLE\n[CHAPTER]\nTIMEBASE=1/1000\n"
                        "START=0\nEND=500\ntitle=ParasiteChap\n")
        cmd += ["-i", str(chap), "-map", "0:a:0", "-map_metadata", "1", "-map_chapters", "1",
                "-metadata", "title=OLDTITLE", "-metadata", "comment=PARASITE",
                "-metadata", "artist=GHOST", "-metadata", "date=1999", "-metadata", "genre=NoiseGenre"]
    else:
        cmd += ["-map", "0:a:0"]
    cmd += [*codec, str(path)]
    subprocess.run(cmd, check=True)
    return path


# ---------------------------------------------------------------- 1. TagSet.is_empty()
check("is_empty: nothing set", TagSet().is_empty())
check("is_empty: a title is not empty", not TagSet(title="X").is_empty())
check("is_empty: a bpm is not empty", not TagSet(bpm=120).is_empty())
check("is_empty: a cover is not empty", not TagSet(cover="/tmp/c.jpg").is_empty())

# ---------------------------------------------------------------- 2. tags.py writes only filled fields
joined = " ".join(metadata_args(TagSet(title="Song", artist="Me"), "mp3"))
check("metadata_args: only the filled fields", "title=Song" in joined and "artist=Me" in joined)
check("metadata_args: no comment/software/encoder tag",
      "comment=" not in joined and "software=" not in joined and "Lavf" not in joined)
check("metadata_args: empty TagSet writes nothing", metadata_args(TagSet(), "flac") == [])
check("metadata_args: blank mp3 adds no id3v2_version (would re-stamp TSSE)",
      metadata_args(TagSet(), "mp3") == [])
cj = root / "cover.jpg"
subprocess.run([FFMPEG, "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
                "-f", "lavfi", "-i", "color=c=navy:s=64x64:d=1", "-frames:v", "1", str(cj)], check=True)
_, cover_map = cover_inputs(TagSet(cover=str(cj)), "mp3")
check("cover_inputs: no default 'Cover (front)' comment", "comment=Cover (front)" not in " ".join(cover_map))
check("cover_inputs: cover still mapped as attached_pic", "attached_pic" in " ".join(cover_map))

# ---------------------------------------------------------------- 3. the clean block is wired into every builder
def has_block(args):
    s = " ".join(args)
    return "-map_metadata -1" in s and "-map_chapters -1" in s and "+bitexact" in s and "0:a:0" in s

captured = []
orig_run = tagsmod.run_ffmpeg
tagsmod.run_ffmpeg = lambda a, w, **k: captured.append(list(a))
try:
    retag_copy(FFMPEG, root / "x.flac", root / "y.flac", TagSet(title="T"), "flac")
finally:
    tagsmod.run_ffmpeg = orig_run
check("retag_copy carries the clean block + keeps 0:a:0", has_block(captured[0]))

enc_args = []
class _Done:
    returncode = 0; stderr = b""
orig_sr = exportmod.subprocess.run
exportmod.subprocess.run = lambda a, **k: (enc_args.append(list(a)), _Done())[1]
try:
    exportmod._ffmpeg_encode(FFMPEG, root / "m.wav", root / "o.mp3",
                             ["-c:a", "libmp3lame", "-b:a", "320k"], TagSet(title="T"), "mp3")
finally:
    exportmod.subprocess.run = orig_sr
check("_ffmpeg_encode carries the clean block + keeps 0:a:0", has_block(enc_args[0]))

conv_src = (ROOT / "htd" / "engine" / "converter.py").read_text()
check("converter no longer copies source metadata (-map_metadata 0 gone)",
      '"-map_metadata", "0"' not in conv_src and "CLEAN_CONTAINER_ARGS" in conv_src)

# ---------------------------------------------------------------- 4. Converter strips parasitic source tags
para = tone(root / "source.flac", ["-c:a", "flac"], dur=1.0, parasites=True)
check("source really carries the parasites", not no_source_tags(para))
out_dir = root / "converted"
for target in ("wav24", "flac", "mp3", "m4a"):
    produced = converter.convert_file(FFMPEG, para, target, None, out_dir)
    sig_ok = mp3_id3_clean(produced) if target == "mp3" else ffmpeg_sig_free(produced)
    check(f"Converter -> {target}: no source tags, no software signature",
          produced.is_file() and no_source_tags(produced) and sig_ok,
          produced.name if produced.is_file() else "missing")

# ---------------------------------------------------------------- 5. write_format: blank export stays raw
master = tone(root / "master.wav", ["-c:a", "pcm_s16le"], dur=2.0)
for fmt_key, ext in (("wav24", "wav"), ("flac", "flac")):          # raw libsndfile, retag skipped
    dst = root / f"blank.{ext}"
    write_format(master, fmt_key, dst, FFMPEG, TagSet())
    check(f"blank {fmt_key}: raw file, no tags, no app stamp",
          dst.is_file() and blank(dst) and app_free(dst))
dst = root / "blank.m4a"                                           # FFmpeg bitexact -> fully clean
write_format(master, "m4a", dst, FFMPEG, TagSet())
check("blank m4a: encoded clean, no tags, no Lavf/encoder",
      dst.is_file() and blank(dst) and ffmpeg_sig_free(dst))
dst = root / "blank.mp3"                                           # empty ID3 block (Xing header aside)
write_format(master, "mp3", dst, FFMPEG, TagSet())
check("blank mp3: no ID3 tags / no TSSE stamp (Xing header aside)",
      dst.is_file() and blank(dst) and mp3_id3_clean(dst))

# ---------------------------------------------------------------- 6. tagged export keeps ONLY the user fields
dst = root / "tagged.flac"
write_format(master, "flac", dst, FFMPEG, TagSet(title="My Title", artist="Me"))
fmt, _, _ = _tags(dst)
check("tagged flac: user title + artist present",
      fmt.get("title") == "My Title" and fmt.get("artist") == "Me", fmt)
check("tagged flac: no comment/date/genre leak + no app stamp",
      "comment" not in fmt and "date" not in fmt and "genre" not in fmt and app_free(dst))

# ---------------------------------------------------------------- 7. Pack Sortie (delivery): strip vs tags
work = root / "work"
del_src = tone(root / "deliver.wav", ["-c:a", "pcm_s16le"], dur=4.0, parasites=True)
r = pipeline.master_track(del_src, presets.MasterSettings.from_preset("Standard"), work)
check("master rendered for delivery test (parasitic 4 s source)", r.ok and r.master_cache.exists())
meta = TrackMeta(title="DeliverTitle")

rec = export_track(r, ExportOptions("wav24", str(root / "del_blank"), strip_metadata=True),
                   meta, ffmpeg_tools.locate_ffmpeg(), work)
check("delivery strip_metadata wav: blank + no source leak + no app stamp",
      blank(rec.main) and no_source_tags(rec.main) and app_free(rec.main), rec.main.name)
rec_mp3 = export_track(r, ExportOptions("mp3", str(root / "del_blank"), strip_metadata=True),
                       meta, ffmpeg_tools.locate_ffmpeg(), work)
check("delivery strip_metadata mp3: no ID3 tags / no source leak",
      blank(rec_mp3.main) and no_source_tags(rec_mp3.main) and mp3_id3_clean(rec_mp3.main), rec_mp3.main.name)

rec2 = export_track(r, ExportOptions("flac", str(root / "del_tagged"),
                                     tags=TagInfo(artist="Diyae", album="LP")),
                    meta, ffmpeg_tools.locate_ffmpeg(), work)
fmt2, _, _ = _tags(rec2.main)
check("delivery normal flac: user title/artist/album written",
      fmt2.get("title") == "DeliverTitle" and fmt2.get("artist") == "Diyae" and fmt2.get("album") == "LP", fmt2)
check("delivery normal flac: no source leak + no app stamp",
      no_source_tags(rec2.main) and app_free(rec2.main))

shutil.rmtree(root, ignore_errors=True)
print("\nMETADATA CLEAN: " + ("ALL PASS" if ok else "SOME FAILED"))
sys.exit(0 if ok else 1)

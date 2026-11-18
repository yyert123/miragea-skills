#!/usr/bin/env python3
"""Turn slide images (PNG/JPG, e.g. exported from PDF/Keynote/Slides) + speaker notes into a narrated MP4 with SRT, in a cloned voice."""
import argparse, os, re, subprocess, sys, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
SIZES = {"16:9": (1280, 720), "9:16": (720, 1280), "1:1": (1080, 1080)}
IMG = (".png", ".jpg", ".jpeg", ".webp")


def natural(p):
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", Path(p).name)]


def find_slides(folder):
    return sorted((p for p in Path(folder).iterdir() if p.suffix.lower() in IMG), key=natural)


def parse_notes(text):
    """Notes: one block per slide, separated by a line of '---' (or '## Slide N' headings)."""
    text = re.sub(r"^#{1,3}\s*slide\s*\d+.*$", "---", text.strip(), flags=re.I | re.M)
    return [re.sub(r"\s+", " ", b).strip() for b in re.split(r"^\s*---+\s*$", text, flags=re.M) if b.strip() or True][
        (1 if text.lstrip().startswith("---") else 0):]


def sentences(t, limit=170):
    out = []
    for s in re.split(r"(?<=[.!?])\s+", t.strip()):
        while len(s) > limit:
            c = s.rfind(" ", 0, limit); out.append(s[:c]); s = s[c + 1:]
        if s:
            out.append(s)
    return out


def srt_time(t):
    ms = int(round(t * 1000)); h, ms = divmod(ms, 3600000); m, ms = divmod(ms, 60000); s, ms = divmod(ms, 1000)
    return f"{h:02}:{m:02}:{s:02},{ms:03}"


def to_srt(cues):
    return "".join(f"{i}\n{srt_time(a)} --> {srt_time(b)}\n{c}\n\n" for i, (a, b, c) in enumerate(cues, 1))


def pair(slides, notes):
    """Match slides to notes; warn on mismatch. Slides without notes get a 2 s silent hold."""
    if len(notes) != len(slides):
        print(f"warning: {len(slides)} slides but {len(notes)} note blocks; pairing in order, extras ignored/silent.")
    return [(s, notes[i] if i < len(notes) else "") for i, s in enumerate(slides)]


def run(cmd):
    r = subprocess.run([str(c) for c in cmd], capture_output=True, text=True)
    if r.returncode:
        sys.exit("ffmpeg failed: " + r.stderr[-400:])
    return r.stdout


def duration(p):
    return float(run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", p]).strip())


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("slides_dir"); ap.add_argument("--notes", required=True, help="notes.md, blocks split by ---")
    ap.add_argument("-o", "--out", default="slides.mp4"); ap.add_argument("--format", default="16:9", choices=SIZES)
    ap.add_argument("--voice"); ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    slides = find_slides(a.slides_dir)
    if not slides:
        sys.exit("slides2video: no PNG/JPG slides found. Export your deck to images first (pdftoppm -png deck.pdf slide).")
    pairs = pair(slides, parse_notes(Path(a.notes).read_text(encoding="utf-8")))
    chars = sum(len(n) for _, n in pairs)
    print(f"{len(slides)} slides, about {chars / 15:.0f}s of narration")
    for s, n in pairs:
        print(f"- {s.name}: {len(sentences(n))} lines")
    if a.dry_run:
        return 0
    a.voice = a.voice or os.environ.get("MIRAGEA_ACTOR_ID")
    if not a.voice:
        sys.exit("slides2video: no voice. Pass --voice ACTOR_ID (a saved Miragea voice; create one at https://miragea.ai "
                 "or POST /v1/actors with a 3-60 s clip you own), or set MIRAGEA_ACTOR_ID.")
    from miragea_client import Client, MirageaError
    w, h = SIZES[a.format]; tmp = Path(tempfile.mkdtemp(prefix="s2v-")); client = Client(); segs, cues, t = [], [], 0.0
    vf = f"scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:color=black,format=yuv420p"
    try:
        for i, (img, note) in enumerate(pairs):
            lines, clips, durs = sentences(note), [], []
            for j, line in enumerate(lines):
                wav = tmp / f"{i}-{j}.wav"; client.speak(line, wav, actor_id=a.voice); clips.append(wav); durs.append(duration(wav))
            audio = tmp / f"{i}.wav"
            if clips:
                lst = tmp / f"{i}.txt"; lst.write_text("".join(f"file '{c}'\n" for c in clips))
                run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", 0, "-i", lst, "-ar", 44100, "-ac", 1, audio])
            else:
                run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono", "-t", 2, audio])
            d = (sum(durs) or 2.0) + 0.5; seg = tmp / f"{i}.mp4"
            run(["ffmpeg", "-v", "error", "-y", "-loop", 1, "-framerate", 30, "-i", img, "-i", audio, "-vf", vf,
                 "-af", "apad=pad_dur=0.5", "-t", d, "-c:v", "libx264", "-c:a", "aac", seg])
            x = t
            for line, dd in zip(lines, durs):
                cues.append((x, x + dd, line)); x += dd
            t += d; segs.append(seg)
    except MirageaError as e:
        sys.exit(f"slides2video: {e}")
    lst = tmp / "all.txt"; lst.write_text("".join(f"file '{s}'\n" for s in segs))
    out = Path(a.out); out.with_suffix(".srt").write_text(to_srt(cues))
    run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", 0, "-i", lst, "-c", "copy", out])
    print(f"wrote {out} and {out.with_suffix('.srt')} ({duration(str(out)):.1f}s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

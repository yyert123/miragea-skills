#!/usr/bin/env python3
"""Turn a blog post / markdown article into a narrated, captioned explainer video (text cards + cloned-voice VO)."""
import argparse, hashlib, os, re, subprocess, sys, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
SIZES = {"16:9": (1280, 720), "9:16": (720, 1280), "1:1": (1080, 1080)}
FONT = next((f for f in ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
             "/System/Library/Fonts/Supplemental/Arial Bold.ttf", "C:/Windows/Fonts/arialbd.ttf") if os.path.exists(f)), "")
PALETTE = ["0x14213d", "0x1b4332", "0x3c096c", "0x7f1d1d", "0x0b3954"]


def clean(t):
    t = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", t)
    t = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", t)
    return re.sub(r"[*_`>#]+", "", t).strip()


def split_sentences(text, limit=170):
    out = []
    for s in re.split(r"(?<=[.!?])\s+", text.strip()):
        while len(s) > limit:
            cut = s.rfind(" ", 0, limit)
            out.append(s[:cut]); s = s[cut + 1:]
        if s:
            out.append(s)
    return out


def parse(md):
    """Return scenes: {title, lines}. A heading starts a scene; the first H1 is the intro title."""
    scenes, cur = [], None
    for block in re.split(r"\n\s*\n", md.strip()):
        for raw in block.splitlines():
            m = re.match(r"^(#{1,3})\s+(.*)", raw)
            if m:
                cur = {"title": clean(m.group(2)), "lines": [clean(m.group(2))] if not scenes else []}
                scenes.append(cur)
            elif raw.strip() and not raw.startswith(("```", "|", "---")):
                if cur is None:
                    cur = {"title": "", "lines": []}; scenes.append(cur)
                cur["lines"] += split_sentences(clean(re.sub(r"^\s*([-*]|\d+\.)\s+", "", raw)))
    return [s for s in scenes if s["lines"]]


def srt_time(t):
    ms = int(round(t * 1000)); h, ms = divmod(ms, 3600000); m, ms = divmod(ms, 60000); s, ms = divmod(ms, 1000)
    return f"{h:02}:{m:02}:{s:02},{ms:03}"


def caption_cues(lines, durs, t0=0.0):
    cues, t = [], t0
    for line, d in zip(lines, durs):
        words = line.split(); chunks = [" ".join(words[i:i + 7]) for i in range(0, len(words), 7)] or [line]
        total = sum(len(c) for c in chunks)
        for c in chunks:
            span = d * len(c) / total; cues.append((t, t + span, c)); t += span
    return cues


def to_srt(cues):
    return "".join(f"{i}\n{srt_time(a)} --> {srt_time(b)}\n{c}\n\n" for i, (a, b, c) in enumerate(cues, 1))


def run(cmd):
    r = subprocess.run([str(c) for c in cmd], capture_output=True, text=True)
    if r.returncode:
        sys.exit("ffmpeg failed: " + r.stderr[-400:])
    return r.stdout


def duration(p):
    return float(run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", p]).strip())


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("article"); ap.add_argument("-o", "--out", default="article.mp4")
    ap.add_argument("--format", default="16:9", choices=SIZES); ap.add_argument("--voice")
    ap.add_argument("--dry-run", action="store_true", help="show scenes and estimated length, no API calls")
    a = ap.parse_args(argv)
    scenes = parse(Path(a.article).read_text(encoding="utf-8"))
    if not scenes:
        sys.exit("article2video: no text found in the article.")
    n = sum(len(s["lines"]) for s in scenes); chars = sum(len(l) for s in scenes for l in s["lines"])
    print(f"{len(scenes)} scenes, {n} lines, about {chars / 15:.0f}s of narration")
    for s in scenes:
        print(f"- {s['title'] or '(intro)'}: {len(s['lines'])} lines")
    if a.dry_run:
        return 0
    a.voice = a.voice or os.environ.get("MIRAGEA_ACTOR_ID")
    if not a.voice:
        sys.exit("article2video: no voice. Pass --voice ACTOR_ID (a saved Miragea voice; create one at https://miragea.ai "
                 "or POST /v1/actors with a 3-60 s clip you own), or set MIRAGEA_ACTOR_ID.")
    from miragea_client import Client, MirageaError
    w, h = SIZES[a.format]; tmp = Path(tempfile.mkdtemp(prefix="a2v-")); client = Client()
    segs, cues, t = [], [], 0.0
    try:
        for si, sc in enumerate(scenes):
            clips, durs = [], []
            for li, line in enumerate(sc["lines"]):
                wav = tmp / f"{si}-{li}.wav"
                client.speak(line, wav, actor_id=a.voice)
                clips.append(wav); durs.append(duration(wav))
            lst = tmp / f"{si}.txt"; lst.write_text("".join(f"file '{c}'\n" for c in clips))
            audio = tmp / f"{si}.a.wav"
            run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", 0, "-i", lst, "-ar", 44100, "-ac", 1, audio])
            title = tmp / f"{si}.title.txt"; title.write_text(sc["title"] or "")
            seg = tmp / f"{si}.mp4"; d = sum(durs) + 0.4
            vf = (f"drawtext=fontfile={FONT}:textfile={title}:fontcolor=white:fontsize={h // 14}:x=(w-text_w)/2:y=h*0.4"
                  if sc["title"] else "null")
            run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"color=c={PALETTE[si % 5]}:s={w}x{h}:r=30:d={d}",
                 "-i", audio, "-vf", vf, "-af", "apad=pad_dur=0.4", "-shortest", "-c:v", "libx264", "-pix_fmt", "yuv420p",
                 "-c:a", "aac", seg])
            cues += caption_cues(sc["lines"], durs, t); t += d; segs.append(seg)
    except MirageaError as e:
        sys.exit(f"article2video: {e}")
    lst = tmp / "all.txt"; lst.write_text("".join(f"file '{s}'\n" for s in segs))
    out = Path(a.out); srt = out.with_suffix(".srt"); srt.write_text(to_srt(cues))
    run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", 0, "-i", lst, "-c", "copy", out])
    print(f"wrote {out} and {srt} ({duration(str(out)):.1f}s). Burn captions with the video-captions skill.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

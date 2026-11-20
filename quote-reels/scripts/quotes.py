#!/usr/bin/env python3
"""Quote / affirmation Reels (faceless Shorts, TikTok): one quote per card, read aloud in a cloned voice, with SRT."""
import argparse, os, re, subprocess, sys, tempfile, textwrap
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
SIZES = {"9:16": (1080, 1920), "16:9": (1920, 1080), "1:1": (1080, 1080)}
PALETTE = ["0x1b1b2f", "0x2f1b2b", "0x13322d", "0x332a17"]
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf"


def parse(text):
    """'# Title', optional plain intro line, then '> quote — Author' blocks. Returns (title, [(quote, author)])."""
    title, quotes = "", []
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("# ") and not title:
            title = s[2:].strip()
        elif s.startswith(">"):
            body = s[1:].strip()
            m = re.match(r"(.+?)\s+(?:—|--|–)\s+(.+)$", body)
            quotes.append((m.group(1), m.group(2)) if m else (body, ""))
    return title, quotes


def lint(title, quotes):
    w = []
    if not title: w.append("no '# Title' line")
    if not quotes: w.append("no '> quote' lines")
    if len(quotes) > 8: w.append("more than 8 quotes: split into two videos")
    for q, a in quotes:
        if len(q.split()) > 35: w.append(f"quote over 35 words: {q[:30]}...")
        if not a: w.append(f"no author: {q[:30]}... (end with ' — Name', or this reads as your own words)")
    return w


def srt_time(t):
    ms = int(round(t * 1000)); h, ms = divmod(ms, 3600000); m, ms = divmod(ms, 60000); s, ms = divmod(ms, 1000)
    return f"{h:02}:{m:02}:{s:02},{ms:03}"


def run(cmd):
    r = subprocess.run([str(c) for c in cmd], capture_output=True, text=True)
    if r.returncode: sys.exit("ffmpeg failed: " + r.stderr[-400:])
    return r.stdout


def duration(p):
    return float(run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", p]).strip())


def vf(tmp, i, quote, author, w, h):
    cw = max(14, int(w / (w * 0.06) * 1.0)) if w >= h else 22
    files = {}
    for k, v in (("q", "\n".join(textwrap.wrap(quote, cw))), ("a", "— " + author if author else " ")):
        p = tmp / f"{i}-{k}.txt"; p.write_text(v, encoding="utf-8"); files[k] = p
    return (f"drawtext=fontfile={FONT}:textfile={files['q']}:fontcolor=white:fontsize={int(w*0.06)}:line_spacing=16:x=(w-text_w)/2:y=(h-text_h)/2-h*0.04,"
            f"drawtext=fontfile={FONT}:textfile={files['a']}:fontcolor=white@0.7:fontsize={int(w*0.04)}:x=(w-text_w)/2:y=h*0.72,format=yuv420p")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("script"); ap.add_argument("-o", "--out", default="quotes.mp4")
    ap.add_argument("--format", default="9:16", choices=SIZES); ap.add_argument("--voice"); ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    title, quotes = parse(Path(a.script).read_text(encoding="utf-8"))
    for p in lint(title, quotes): print("warning:", p)
    print(f"{title!r}: {len(quotes)} quotes, about {sum(len(q.split()) + len(x.split()) for q, x in quotes) / 2.4:.0f}s")
    if a.dry_run: return 1 if not quotes else 0
    if not quotes: sys.exit("quotes: no '> quote — Author' lines found. See examples/quotes.md.")
    a.voice = a.voice or os.environ.get("MIRAGEA_ACTOR_ID")
    if not a.voice:
        sys.exit("quotes: no voice. Pass --voice ACTOR_ID (a saved Miragea voice; create one at https://miragea.ai "
                 "or POST /v1/actors with a 3-60 s clip you own), or set MIRAGEA_ACTOR_ID.")
    from miragea_client import Client, MirageaError
    w, h = SIZES[a.format]; tmp = Path(tempfile.mkdtemp(prefix="qr-")); client = Client(); segs, cues, t = [], [], 0.0
    try:
        for i, (q, au) in enumerate(quotes):
            say = q + (f" ... {au}." if au else ""); wav = tmp / f"{i}.wav"; client.speak(say, wav, actor_id=a.voice)
            d = duration(wav) + 0.8; seg = tmp / f"{i}.mp4"; col = PALETTE[i % len(PALETTE)]
            run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"color=c={col}:s={w}x{h}:r=30:d={d}", "-i", wav,
                 "-vf", vf(tmp, i, q, au, w, h) + f",fade=in:d=0.5,fade=out:st={d-0.5}:d=0.5", "-af", "apad=pad_dur=0.8",
                 "-t", d, "-c:v", "libx264", "-c:a", "aac", seg])
            cues.append((t, t + d - 0.8, q)); t += d; segs.append(seg)
    except MirageaError as e:
        sys.exit(f"quotes: {e}")
    lst = tmp / "all.txt"; lst.write_text("".join(f"file '{s}'\n" for s in segs))
    out = Path(a.out); out.with_suffix(".srt").write_text("".join(
        f"{n}\n{srt_time(x)} --> {srt_time(y)}\n{c}\n\n" for n, (x, y, c) in enumerate(cues, 1)))
    run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", 0, "-i", lst, "-c", "copy", out])
    print(f"wrote {out} and {out.with_suffix('.srt')} ({duration(str(out)):.1f}s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

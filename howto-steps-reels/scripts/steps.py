#!/usr/bin/env python3
"""How-to Steps Reels: markdown steps become a narrated step-by-step tutorial video, one numbered step per card (faceless Shorts, TikTok), with SRT."""
import argparse, os, re, subprocess, sys, tempfile, textwrap
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
SIZES = {"9:16": (1080, 1920), "16:9": (1920, 1080), "1:1": (1080, 1080)}
PALETTE = ["0x1b1b2f", "0x2f1b2b", "0x13322d", "0x332a17"]
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf"


def parse(text):
    """'# Title', then '## Step: ...' followed by detail lines. Returns (title, [(step, detail)])."""
    title, qs = "", []
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("## "): qs.append([re.sub(r"^step\s*\d*:\s*", "", s[3:].strip(), flags=re.I), ""])
        elif s.startswith("# ") and not title: title = s[2:].strip()
        elif s and qs: qs[-1][1] = (qs[-1][1] + " " + s).strip()
    return title, [tuple(x) for x in qs]


def lint(title, qs):
    w = []
    if not title: w.append("no '# Title' line")
    if not qs: w.append("no '## Step: ...' lines")
    if len(qs) > 7: w.append("more than 7 steps: split into two videos (Shorts hold viewers under ~60 s)")
    for q, ans in qs:
        if len(q.split()) > 18: w.append(f"step title over 18 words: {q[:30]}...")
        if not ans: w.append(f"no detail under: {q[:30]}")
        if len(ans.split()) > 40: w.append(f"detail over 40 words (too long for a Short): {q[:30]}...")
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


def vf(tmp, i, question, author, w, h):
    author = "\n".join(textwrap.wrap(author, 30 if w < h else 60))
    cw = max(14, int(w / (w * 0.06) * 1.0)) if w >= h else 22
    files = {}
    for k, v in (("q", f"STEP {i+1}\n" + "\n".join(textwrap.wrap(question, cw))), ("a", author)):
        p = tmp / f"{i}-{k}.txt"; p.write_text(v, encoding="utf-8"); files[k] = p
    return (f"drawtext=fontfile={FONT}:textfile={files['q']}:fontcolor=white:fontsize={int(w*0.06)}:line_spacing=16:x=(w-text_w)/2:y=h*0.2,"
            f"drawtext=fontfile={FONT}:textfile={files['a']}:fontcolor=white@0.85:fontsize={int(w*0.045)}:x=(w-text_w)/2:y=h*0.5,format=yuv420p")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("script"); ap.add_argument("-o", "--out", default="steps.mp4")
    ap.add_argument("--format", default="9:16", choices=SIZES); ap.add_argument("--voice"); ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    title, qs = parse(Path(a.script).read_text(encoding="utf-8"))
    for p in lint(title, qs): print("warning:", p)
    print(f"{title!r}: {len(qs)} qs, about {sum(len(q.split()) + len(x.split()) for q, x in qs) / 2.4:.0f}s")
    if a.dry_run: return 1 if not qs else 0
    if not qs: sys.exit("step: no '## Step:' sections found. See examples/steps.md.")
    a.voice = a.voice or os.environ.get("MIRAGEA_ACTOR_ID")
    if not a.voice:
        sys.exit("step: no voice. Pass --voice ACTOR_ID (a saved Miragea voice; create one at https://miragea.ai "
                 "or POST /v1/actors with a 3-60 s clip you own), or set MIRAGEA_ACTOR_ID.")
    from miragea_client import Client, MirageaError
    w, h = SIZES[a.format]; tmp = Path(tempfile.mkdtemp(prefix="mb-")); client = Client(); segs, cues, t = [], [], 0.0
    try:
        for i, (q, au) in enumerate(qs):
            say = f"Step {i+1}. {q}. {au}"; wav = tmp / f"{i}.wav"; client.speak(say, wav, actor_id=a.voice)
            d = duration(wav) + 0.8; seg = tmp / f"{i}.mp4"; col = PALETTE[i % len(PALETTE)]
            run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"color=c={col}:s={w}x{h}:r=30:d={d}", "-i", wav,
                 "-vf", vf(tmp, i, q, au, w, h) + f",fade=in:d=0.5,fade=out:st={d-0.5}:d=0.5", "-af", "apad=pad_dur=0.8",
                 "-t", d, "-c:v", "libx264", "-c:a", "aac", seg])
            cues.append((t, t + d - 0.8, q)); t += d; segs.append(seg)
    except MirageaError as e:
        sys.exit(f"step: {e}")
    lst = tmp / "all.txt"; lst.write_text("".join(f"file '{s}'\n" for s in segs))
    out = Path(a.out); out.with_suffix(".srt").write_text("".join(
        f"{n}\n{srt_time(x)} --> {srt_time(y)}\n{c}\n\n" for n, (x, y, c) in enumerate(cues, 1)))
    run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", 0, "-i", lst, "-c", "copy", out])
    print(f"wrote {out} and {out.with_suffix('.srt')} ({duration(str(out)):.1f}s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

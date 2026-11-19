#!/usr/bin/env python3
"""Listicle / top-N tips video (faceless Reels, Shorts, TikTok): numbered text cards + narration in a cloned voice, with SRT."""
import argparse, os, re, subprocess, sys, tempfile, textwrap
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
SIZES = {"9:16": (1080, 1920), "16:9": (1920, 1080), "1:1": (1080, 1080)}
PALETTE = ["0x1f2a44", "0x3b1f44", "0x14463a", "0x44301f", "0x1f3d44"]
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"


def parse(text):
    """'# Title', optional 'hook: ...', then '## Item title' + body lines. Returns (title, hook, [(head, body)])."""
    title, hook, items = "", "", []
    for line in text.splitlines():
        s = line.strip()
        if not s:
            continue
        if s.startswith("## "):
            items.append([s[3:].strip(), ""])
        elif s.startswith("# "):
            title = s[2:].strip()
        elif s.lower().startswith("hook:") and not items:
            hook = s[5:].strip()
        elif items:
            items[-1][1] = (items[-1][1] + " " + s).strip()
    return title, hook, [tuple(i) for i in items]


def lint(title, hook, items):
    w = []
    if not title: w.append("no '# Title' line")
    if not items: w.append("no '## item' sections")
    if len(items) > 10: w.append("more than 10 items: retention drops, consider splitting")
    if hook and len(hook.split()) > 18: w.append("hook longer than 18 words")
    for h, b in items:
        if not b: w.append(f"item '{h}' has no spoken text")
        if len(b.split()) > 40: w.append(f"item '{h}' body over 40 words")
        if len(h) > 40: w.append(f"item '{h}' headline over 40 chars (card text shrinks)")
    return w


def wrap(t, width):
    return "\n".join(textwrap.wrap(t, width)) or " "


def srt_time(t):
    ms = int(round(t * 1000)); h, ms = divmod(ms, 3600000); m, ms = divmod(ms, 60000); s, ms = divmod(ms, 1000)
    return f"{h:02}:{m:02}:{s:02},{ms:03}"


def run(cmd):
    r = subprocess.run([str(c) for c in cmd], capture_output=True, text=True)
    if r.returncode:
        sys.exit("ffmpeg failed: " + r.stderr[-400:])
    return r.stdout


def duration(p):
    return float(run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", p]).strip())


def card(tmp, name, big, head, w, h, color):
    """Write text files and return a drawtext filter chain (textfile avoids escaping bugs)."""
    cw = 14 if w < h else 26
    files = {}
    for k, v in (("big", big), ("head", wrap(head, cw))):
        p = tmp / f"{name}-{k}.txt"; p.write_text(v, encoding="utf-8"); files[k] = p
    fs_big, fs_head = int(w * 0.30), int(w * 0.075)
    f = f"drawtext=fontfile={FONT}:textfile={files['big']}:fontcolor=white@0.25:fontsize={fs_big}:x=(w-text_w)/2:y=h*0.12"
    f += f",drawtext=fontfile={FONT}:textfile={files['head']}:fontcolor=white:fontsize={fs_head}:line_spacing=14:x=(w-text_w)/2:y=h*0.40"
    return f


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("script"); ap.add_argument("-o", "--out", default="listicle.mp4")
    ap.add_argument("--format", default="9:16", choices=SIZES); ap.add_argument("--voice"); ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    title, hook, items = parse(Path(a.script).read_text(encoding="utf-8"))
    problems = lint(title, hook, items)
    for p in problems: print("warning:", p)
    words = len(hook.split()) + sum(len(b.split()) for _, b in items)
    print(f"{title!r}: {len(items)} items, about {words / 2.6:.0f}s of narration")
    if a.dry_run:
        return 1 if not items else 0
    if not items:
        sys.exit("listicle: no '## item' sections found. See examples/tips.md.")
    a.voice = a.voice or os.environ.get("MIRAGEA_ACTOR_ID")
    if not a.voice:
        sys.exit("listicle: no voice. Pass --voice ACTOR_ID (a saved Miragea voice; create one at https://miragea.ai "
                 "or POST /v1/actors with a 3-60 s clip you own), or set MIRAGEA_ACTOR_ID.")
    from miragea_client import Client, MirageaError
    w, h = SIZES[a.format]; tmp = Path(tempfile.mkdtemp(prefix="lst-")); client = Client(); segs, cues, t = [], [], 0.0
    scenes = ([("", title, hook)] if hook else []) + [(str(i), hh, b) for i, (hh, b) in enumerate(items, 1)]
    try:
        for i, (big, head, say) in enumerate(scenes):
            wav = tmp / f"{i}.wav"; client.speak(say or head, wav, actor_id=a.voice)
            d = duration(wav) + 0.4; seg = tmp / f"{i}.mp4"
            vf = card(tmp, f"c{i}", big or " ", head, w, h, PALETTE[i % len(PALETTE)]) + ",format=yuv420p"
            run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"color=c={PALETTE[i % len(PALETTE)]}:s={w}x{h}:r=30:d={d}",
                 "-i", wav, "-vf", vf, "-af", "apad=pad_dur=0.4", "-t", d, "-c:v", "libx264", "-c:a", "aac", seg])
            cues.append((t, t + d - 0.4, say or head)); t += d; segs.append(seg)
    except MirageaError as e:
        sys.exit(f"listicle: {e}")
    lst = tmp / "all.txt"; lst.write_text("".join(f"file '{s}'\n" for s in segs))
    out = Path(a.out); out.with_suffix(".srt").write_text("".join(
        f"{n}\n{srt_time(x)} --> {srt_time(y)}\n{c}\n\n" for n, (x, y, c) in enumerate(cues, 1)))
    run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", 0, "-i", lst, "-c", "copy", out])
    print(f"wrote {out} and {out.with_suffix('.srt')} ({duration(str(out)):.1f}s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

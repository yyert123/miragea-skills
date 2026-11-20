#!/usr/bin/env python3
"""Release notes / changelog -> short narrated update video (product update, what's new) in a cloned voice, with SRT."""
import argparse, os, re, subprocess, sys, tempfile, textwrap
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
SIZES = {"16:9": (1920, 1080), "9:16": (1080, 1920), "1:1": (1080, 1080)}
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
COL = {"new": "0x12332a", "fixed": "0x332a12", "improved": "0x1b2a44"}


def parse(text):
    """'# Product 1.2', '## Section', '- item'. Returns (title, [(section, item)])."""
    title, sec, items = "", "", []
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("# ") and not title: title = s[2:].strip()
        elif s.startswith("## "): sec = s[3:].strip()
        elif re.match(r"[-*] ", s): items.append((sec, re.sub(r"`|\*\*", "", s[2:].strip())))
    return title, items


def lint(title, items):
    w = []
    if not title: w.append("no '# Title' line")
    if not items: w.append("no '- item' lines")
    if len(items) > 8: w.append("more than 8 items: keep the video under a minute, link the full changelog")
    for sec, it in items:
        if len(it.split()) > 18: w.append(f"item over 18 words: {it[:30]}...")
        if re.search(r"#\d+|[0-9a-f]{7,}\b", it): w.append(f"commit/issue reference reads badly aloud: {it[:30]}...")
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


def cards(title, items):
    """(label, body, spoken) per card."""
    out = [("WHAT'S NEW", title, f"{title}. Here's what's new.")]
    for sec, it in items: out.append((sec.upper(), it, (f"{sec}: " if sec else "") + it.rstrip(".") + "."))
    return out


def vf(tmp, i, label, body, w, h):
    cw = max(14, int(w / (w * 0.06))) if w >= h else 22
    cw = 26 if w >= h else 18
    f = {}
    for k, v in (("l", label or " "), ("b", "\n".join(textwrap.wrap(body, cw)))):
        p = tmp / f"{i}-{k}.txt"; p.write_text(v, encoding="utf-8"); f[k] = p
    return (f"drawtext=fontfile={FONT}:textfile={f['l']}:fontcolor=0x9be7c4:fontsize={int(w*0.03)}:x=(w-text_w)/2:y=h*0.3,"
            f"drawtext=fontfile={FONT}:textfile={f['b']}:fontcolor=white:fontsize={int(w*0.05)}:line_spacing=14:x=(w-text_w)/2:y=(h-text_h)/2+h*0.03,format=yuv420p")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("notes"); ap.add_argument("-o", "--out", default="update.mp4")
    ap.add_argument("--format", default="16:9", choices=SIZES); ap.add_argument("--voice"); ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    title, items = parse(Path(a.notes).read_text(encoding="utf-8"))
    for p in lint(title, items): print("warning:", p)
    cs = cards(title, items)
    print(f"{title!r}: {len(items)} items, about {sum(len(c[2].split()) for c in cs) / 2.5 + 0.8 * len(cs):.0f}s")
    if a.dry_run: return 1 if not items else 0
    if not items: sys.exit("changelog: no '- item' lines found. See examples/release.md.")
    a.voice = a.voice or os.environ.get("MIRAGEA_ACTOR_ID")
    if not a.voice:
        sys.exit("changelog: no voice. Pass --voice ACTOR_ID (a saved Miragea voice; create one at https://miragea.ai "
                 "or POST /v1/actors with a 3-60 s clip you own), or set MIRAGEA_ACTOR_ID.")
    from miragea_client import Client, MirageaError
    w, h = SIZES[a.format]; tmp = Path(tempfile.mkdtemp(prefix="cl-")); client = Client(); segs, cues, t = [], [], 0.0
    try:
        for i, (lab, body, say) in enumerate(cs):
            wav = tmp / f"{i}.wav"; client.speak(say, wav, actor_id=a.voice)
            d = duration(wav) + 0.7; seg = tmp / f"{i}.mp4"
            run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"color=c={COL.get(lab.lower(), '0x1b1b2f')}:s={w}x{h}:r=30:d={d}", "-i", wav,
                 "-vf", vf(tmp, i, lab, body, w, h) + f",fade=in:d=0.3,fade=out:st={d-0.3}:d=0.3", "-af", "apad=pad_dur=0.7",
                 "-t", d, "-c:v", "libx264", "-c:a", "aac", seg])
            cues.append((t, t + d - 0.7, say)); t += d; segs.append(seg)
    except MirageaError as e:
        sys.exit(f"changelog: {e}")
    lst = tmp / "all.txt"; lst.write_text("".join(f"file '{s}'\n" for s in segs))
    out = Path(a.out); out.with_suffix(".srt").write_text("".join(
        f"{n}\n{srt_time(x)} --> {srt_time(y)}\n{c}\n\n" for n, (x, y, c) in enumerate(cues, 1)))
    run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", 0, "-i", lst, "-c", "copy", out])
    print(f"wrote {out} and {out.with_suffix('.srt')} ({duration(str(out)):.1f}s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

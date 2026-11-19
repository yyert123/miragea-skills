#!/usr/bin/env python3
"""YouTube thumbnail + title A/B kit. prep: transcript + candidate frames. build: variants -> 1280x720 JPEGs + lint."""
from __future__ import annotations
import argparse, json, subprocess, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from miragea_client import Client, MirageaError  # noqa: E402

TITLE_MAX, TEXT_MAX_WORDS = 60, 4
POWER = {"how", "why", "secret", "stop", "never", "worst", "best", "free", "fast", "mistake", "mistakes"}

def lint(v: dict) -> list:
    w = []
    t, th = v.get("title", ""), v.get("thumb_text", "")
    if not t: w.append("missing title")
    if len(t) > TITLE_MAX: w.append(f"title {len(t)} chars (>{TITLE_MAX}, truncated in search)")
    if len(th.split()) > TEXT_MAX_WORDS: w.append(f"thumb_text {len(th.split())} words (>{TEXT_MAX_WORDS})")
    if th and t and th.strip().lower() == t.strip().lower(): w.append("thumb_text repeats the title; add new info")
    return w

def frame_times(duration: float, n: int) -> list:
    return [round(duration * (i + 1) / (n + 1), 2) for i in range(n)]

def probe(path) -> float:
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)], capture_output=True, text=True)
    return float(r.stdout.strip() or 0)

def esc(s: str) -> str:
    return s.replace("\\", "\\\\").replace(":", "\\:").replace("'", "\u2019").replace("%", "\\%")

def render_cmd(frame, text, out, pos="bottom", color="yellow"):
    y = "h-th-60" if pos == "bottom" else "60"
    vf = ("scale=1280:720:force_original_aspect_ratio=increase,crop=1280:720,eq=contrast=1.12:saturation=1.25,"
          f"drawtext=text='{esc(text.upper())}':fontcolor={color}:fontsize=110:borderw=8:bordercolor=black:x=(w-tw)/2:y={y}")
    return ["ffmpeg", "-y", "-loglevel", "error", "-i", str(frame), "-vf", vf, "-frames:v", "1", "-q:v", "3", str(out)]

def prep(a) -> int:
    src = Path(a.video); out = Path(a.out or src.with_suffix(".thumbs")); out.mkdir(parents=True, exist_ok=True)
    text = Client().transcribe(src).get("text", "") if not a.dry_run else "(dry run transcript)"
    frames = []
    for i, t in enumerate(frame_times(probe(src), a.frames), 1):
        f = out / f"frame{i}.jpg"
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", str(t), "-i", str(src), "-frames:v", "1", "-q:v", "2", str(f)], check=True)
        frames.append({"file": f.name, "t": t})
    job = {"transcript": text, "frames": frames, "variants": [{"id": "A", "title": "", "thumb_text": "", "frame": frames[0]["file"] if frames else ""}]}
    (out / "variants.json").write_text(json.dumps(job, indent=2, ensure_ascii=False))
    print(f"wrote {out}/variants.json: add 2-4 variants (title <= {TITLE_MAX} chars, thumb_text <= {TEXT_MAX_WORDS} words), then run build")
    return 0

def build(a) -> int:
    p = Path(a.job); d = p.parent; job = json.loads(p.read_text()); rows = ["id,title,thumb_text,file,warnings"]; bad = 0
    for v in job["variants"]:
        w = lint(v); out = d / f"thumb_{v['id']}.jpg"
        if v.get("thumb_text") and (d / v.get("frame", "")).is_file():
            subprocess.run(render_cmd(d / v["frame"], v["thumb_text"], out, v.get("pos", "bottom"), v.get("color", "yellow")), check=True)
        else: w.append("no thumbnail rendered (frame or thumb_text missing)")
        bad += bool(w)
        rows.append(",".join('"%s"' % str(x).replace('"', '""') for x in (v["id"], v.get("title", ""), v.get("thumb_text", ""), out.name, "; ".join(w))))
        for x in w: print(f"[{v['id']}] {x}")
    (d / "ab_plan.csv").write_text("\n".join(rows) + "\n")
    print(f"{len(job['variants'])} variants, {bad} with warnings -> ab_plan.csv. Upload to YouTube Test & Compare.")
    return 0

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__); s = ap.add_subparsers(dest="cmd", required=True)
    q = s.add_parser("prep"); q.add_argument("video"); q.add_argument("--out"); q.add_argument("--frames", type=int, default=6); q.add_argument("--dry-run", action="store_true"); q.set_defaults(f=prep)
    q = s.add_parser("build"); q.add_argument("job"); q.set_defaults(f=build)
    a = ap.parse_args(argv)
    try: return a.f(a)
    except MirageaError as e: print(f"error: {e}", file=sys.stderr); return 1

if __name__ == "__main__": sys.exit(main())

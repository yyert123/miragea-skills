#!/usr/bin/env python3
"""dub-batch: plan and render many language versions of one video (wraps video-dubbing)."""
import argparse, json, subprocess, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
DUB = HERE.parent.parent / "video-dubbing" / "scripts" / "dub.py"
LANGS = {"es": "Spanish", "pt": "Portuguese", "fr": "French", "de": "German", "it": "Italian",
         "hi": "Hindi", "ja": "Japanese", "ko": "Korean", "zh": "Chinese", "ar": "Arabic",
         "id": "Indonesian", "tr": "Turkish", "ru": "Russian"}

def parse_langs(s):
    out = []
    for c in s.replace(" ", "").lower().split(","):
        if not c: continue
        if c not in LANGS: raise SystemExit(f"Unknown language '{c}'. Use: {', '.join(LANGS)}")
        if c not in out: out.append(c)
    if not out: raise SystemExit("Give at least one language, e.g. --to es,pt,hi")
    return out

def dub_path(video, lang): return video.with_name(f"{video.stem}.{lang}.dub.json")

def status(video, langs):
    rows = []
    for l in langs:
        p = dub_path(video, l)
        if not p.exists(): rows.append((l, "missing", 0, 0)); continue
        lines = json.loads(p.read_text()).get("lines", [])
        done = sum(1 for x in lines if str(x.get("text", "")).strip())
        rows.append((l, "ready" if lines and done == len(lines) else "needs translation", done, len(lines)))
    return rows

def run(args): return subprocess.call([sys.executable, str(DUB)] + [str(a) for a in args])

def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("cmd", choices=["prep", "status", "render"])
    ap.add_argument("video", type=Path)
    ap.add_argument("--to", required=True, help="comma list, e.g. es,pt,hi")
    ap.add_argument("-o", "--out", type=Path, default=Path("dub_batch_out"))
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    langs = parse_langs(a.to)
    if a.cmd == "prep":
        for l in langs:
            if run(["prep", a.video, "--to", l]): return 1
        print(f"Now fill every \"text\" in {', '.join(dub_path(a.video, l).name for l in langs)}, then run status.")
        return 0
    rows = status(a.video, langs)
    for l, st, d, n in rows: print(f"{l} ({LANGS[l]}): {st} {d}/{n}")
    if a.cmd == "status": return 0 if all(r[1] == "ready" for r in rows) else 2
    if any(r[1] != "ready" for r in rows): print("Fix the languages above first.", file=sys.stderr); return 2
    rc = 0
    for l in langs:
        extra = ["--dry-run"] if a.dry_run else []
        rc |= run(["render", a.video, dub_path(a.video, l), "-o", a.out / l] + extra)
    return 1 if rc else 0

if __name__ == "__main__": sys.exit(main())

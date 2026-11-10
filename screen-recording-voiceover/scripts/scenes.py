#!/usr/bin/env python3
"""Find the steps in a screen recording and write a timed script template for narration.

    python3 scenes.py demo.mp4            # -> demo.frames/ (one JPG per step) + demo.script.txt

Screen recordings change in small ways (a dialog opens, a page loads), so detection uses a low scene
threshold and merges changes closer than --min-gap seconds. Look at the frames, then write one sentence
per step after each timestamp in demo.script.txt and run voiceover.py. Python 3.9+ stdlib + ffmpeg.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path


def fmt(t: float) -> str:
    return f"{int(t // 60):02d}:{t % 60:04.1f}"


def merge(times: list[float], duration: float, min_gap: float, max_steps: int) -> list[float]:
    """Always start at 0; drop changes too close to the previous step or the end. Pure function (tested)."""
    out = [0.0]
    for t in sorted(times):
        if t - out[-1] >= min_gap and duration - t >= min(min_gap, 1.5):
            out.append(round(t, 2))
    while len(out) > max_steps:  # drop the step with the shortest slot until under the cap
        slots = [(out[i + 1] if i + 1 < len(out) else duration) - out[i] for i in range(len(out))]
        i = min(range(1, len(out)), key=lambda k: slots[k] + slots[k - 1])
        out.pop(i)
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("video", type=Path)
    ap.add_argument("--threshold", type=float, default=0.04, help="scene-change sensitivity (lower = more steps)")
    ap.add_argument("--min-gap", type=float, default=3.0, help="minimum seconds between steps (default 3)")
    ap.add_argument("--max-steps", type=int, default=40)
    a = ap.parse_args(argv)
    if not shutil.which("ffmpeg"):
        sys.exit("scenes: error: ffmpeg not found. Install it (brew/apt/winget install ffmpeg) and re-run.")
    if not a.video.exists():
        sys.exit(f"scenes: error: {a.video} not found.")
    dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
                                str(a.video)], capture_output=True, text=True).stdout.strip() or 0)
    r = subprocess.run(["ffmpeg", "-hide_banner", "-i", str(a.video), "-vf",
                        f"scale=320:-2,select='gt(scene,{a.threshold})',showinfo", "-an", "-f", "null", "-"],
                       capture_output=True, text=True)
    times = [float(x) for x in re.findall(r"pts_time:([\d.]+)", r.stderr)]
    steps = merge(times, dur, a.min_gap, a.max_steps)
    frames = a.video.with_name(a.video.stem + ".frames")
    frames.mkdir(exist_ok=True)
    index = []
    for i, t in enumerate(steps, 1):
        img = frames / f"{i:02d}_{fmt(t).replace(':', 'm')}s.jpg"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{min(t + 0.4, max(dur - 0.1, 0)):.2f}", "-i",
                        str(a.video), "-frames:v", "1", "-vf", "scale=1280:-2", str(img)], check=True)
        nxt = steps[i] if i < len(steps) else dur
        index.append({"step": i, "time": t, "slot_seconds": round(nxt - t, 2), "frame": str(img),
                      "max_words": max(1, int((nxt - t - 0.3) * 2.5))})
    script = a.video.with_name(a.video.stem + ".script.txt")
    if script.exists():
        print(f"kept your existing {script.name} (not overwritten)", file=sys.stderr)
    else:
        body = ["# One sentence per step. Keep each line within ~max_words so it fits before the next step.",
                "# Edit timestamps freely; delete steps you do not want narrated."]
        body += [f"[{fmt(s['time'])}] " + f"# step {s['step']}: {s['slot_seconds']}s, ~{s['max_words']} words"
                 for s in index]
        script.write_text("\n".join(body) + "\n", encoding="utf-8")
    (frames / "steps.json").write_text(json.dumps({"video": str(a.video), "duration": dur, "steps": index}, indent=2))
    print(json.dumps({"duration": round(dur, 2), "steps": len(index), "frames": str(frames), "script": str(script)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

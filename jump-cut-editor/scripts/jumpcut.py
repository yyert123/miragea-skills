#!/usr/bin/env python3
"""Cut silences, filler words (um, uh, you know...) and false starts out of a talking-head video or audio.

    python3 jumpcut.py talk.mp4 --dry-run            # plan + time saved, free of render
    python3 jumpcut.py talk.mp4 -o talk-tight.mp4    # render
    python3 jumpcut.py talk.mp4 --transcript t.json  # reuse a saved Miragea transcript

Word timing comes from Miragea speech recognition (env MIRAGEA_API_KEY). Stdlib + ffmpeg.
"""
from __future__ import annotations
import argparse, json, re, shutil, subprocess, sys, tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cues import words as get_words  # noqa: E402

FILLERS = {"um", "uh", "umm", "uhh", "er", "erm", "ah", "hmm", "mm", "like,", "you know", "i mean"}
SINGLE = {"um", "uh", "umm", "uhh", "er", "erm", "hmm", "mm", "mhm"}


def norm(w: str) -> str:
    return re.sub(r"[^a-z']", "", w.lower())


def find_cuts(ws: list, *, max_gap: float = 0.45, pad: float = 0.06, fillers: bool = True,
              repeats: bool = True, total: float | None = None) -> list:
    """Return [(start, end, reason)] regions to remove. Gaps keep `max_gap` of air so speech breathes."""
    cuts = []
    for i, w in enumerate(ws):
        n = norm(w["text"])
        if fillers and n in SINGLE:
            cuts.append((w["start"], w["end"], "filler"))
        elif repeats and i + 1 < len(ws) and n and n == norm(ws[i + 1]["text"]) and len(n) <= 6 \
                and not w["text"].endswith((".", "!", "?")):
            cuts.append((w["start"], ws[i + 1]["start"], "repeat"))  # "the the plan" -> "the plan"
    prev_end = 0.0
    for w in ws:
        gap = w["start"] - prev_end
        if gap > max_gap + 2 * pad:
            cuts.append((prev_end + max_gap / 2, w["start"] - max_gap / 2, "silence"))
        prev_end = max(prev_end, w["end"])
    if total and total - prev_end > max_gap + 2 * pad:
        cuts.append((prev_end + max_gap / 2, total, "tail"))
    return merge(cuts, pad)


def merge(cuts: list, pad: float) -> list:
    out = []
    for s, e, r in sorted(cuts):
        s, e = s - (pad if r in ("filler", "repeat") else 0), e + (pad if r in ("filler", "repeat") else 0)
        s = max(0.0, s)
        if e - s < 0.05:
            continue
        if out and s <= out[-1][1] + 0.02:
            out[-1] = (out[-1][0], max(out[-1][1], e), out[-1][2] if out[-1][2] == r else "mixed")
        else:
            out.append((s, e, r))
    return out


def keeps(cuts: list, total: float) -> list:
    k, t = [], 0.0
    for s, e, _ in cuts:
        if s > t + 0.05:
            k.append((t, s))
        t = max(t, e)
    if total > t + 0.05:
        k.append((t, total))
    return k


def probe(path: str) -> tuple[float, bool]:
    j = json.loads(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type:format=duration",
                                            "-of", "json", path], text=True))
    return float(j["format"]["duration"]), any(s["codec_type"] == "video" for s in j["streams"])


def filter_graph(k: list, video: bool, fade: float = 0.012) -> str:
    g = []
    for i, (s, e) in enumerate(k):
        if video:
            g.append(f"[0:v]trim={s:.3f}:{e:.3f},setpts=PTS-STARTPTS[v{i}]")
        d = e - s
        g.append(f"[0:a]atrim={s:.3f}:{e:.3f},asetpts=PTS-STARTPTS,afade=t=in:d={fade}," 
                 f"afade=t=out:st={max(d - fade, 0):.3f}:d={fade}[a{i}]")
    ins = "".join(f"[v{i}][a{i}]" if video else f"[a{i}]" for i in range(len(k)))
    g.append(f"{ins}concat=n={len(k)}:v={1 if video else 0}:a=1{'[v][a]' if video else '[a]'}")
    return ";".join(g)


def plan(cuts: list, total: float) -> dict:
    saved = sum(e - s for s, e, _ in cuts)
    by = {}
    for s, e, r in cuts:
        by[r] = by.get(r, 0) + 1
    return {"original_s": round(total, 2), "final_s": round(total - saved, 2), "saved_s": round(saved, 2),
            "saved_pct": round(100 * saved / total, 1) if total else 0, "cuts": by,
            "regions": [[round(s, 2), round(e, 2), r] for s, e, r in cuts]}


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("media")
    p.add_argument("-o", "--out")
    p.add_argument("--transcript", help="saved Miragea transcript JSON (skips the API call)")
    p.add_argument("--max-gap", type=float, default=0.45, help="longest pause kept, seconds (default 0.45)")
    p.add_argument("--keep-fillers", action="store_true")
    p.add_argument("--keep-repeats", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    a = p.parse_args(argv)
    src = Path(a.media)
    if not src.exists():
        raise SystemExit(f"File not found: {src}")
    if not 0.1 <= a.max_gap <= 3:
        raise SystemExit("--max-gap must be between 0.1 and 3 seconds")
    if a.transcript:
        tr = json.loads(Path(a.transcript).read_text())
    else:
        from miragea_client import Client
        tr = Client().transcribe(src)
        src.with_suffix(".transcript.json").write_text(json.dumps(tr))
    try:
        total, video = probe(str(src))
    except Exception:
        total, video = (tr["segments"][-1]["end"] if tr.get("segments") else 0.0), True
    ws = get_words(tr)
    cuts = find_cuts(ws, max_gap=a.max_gap, fillers=not a.keep_fillers, repeats=not a.keep_repeats, total=total)
    info = plan(cuts, total)
    if a.dry_run:
        print(json.dumps(info, indent=1))
        return 0
    if not shutil.which("ffmpeg"):
        raise SystemExit("ffmpeg not found on PATH")
    k = keeps(cuts, total)
    if not k:
        raise SystemExit("Nothing would be left after cutting; raise --max-gap")
    out = a.out or str(src.with_name(src.stem + "-tight" + (".mp4" if video else ".wav")))
    with tempfile.TemporaryDirectory() as d:
        sc = Path(d) / "g.txt"
        sc.write_text(filter_graph(k, video))
        cmd = ["ffmpeg", "-y", "-v", "error", "-i", str(src), "-filter_complex_script", str(sc),
               "-map", "[v]" if video else "[a]"] + (["-map", "[a]", "-c:v", "libx264", "-crf", "20", "-pix_fmt", "yuv420p"] if video else []) + \
              ["-c:a", "aac" if video else "pcm_s16le", out]
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode:
            raise SystemExit("ffmpeg failed: " + r.stderr[-400:])
    print(json.dumps({**info, "output": out, "regions": len(cuts)}))
    return 0


if __name__ == "__main__":
    sys.exit(main())

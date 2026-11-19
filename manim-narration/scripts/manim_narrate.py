#!/usr/bin/env python3
"""Narrate Manim (3Blue1Brown-style) videos in your own Miragea voice.

    python3 manim_narrate.py plan script.md --out narration --voice ACTOR_ID     # voice + timing, one clip per scene
    python3 manim_narrate.py plan script.md --out narration --dry-run             # no API call, silent clips
    python3 manim_narrate.py mux media/videos/scene/1080p60/Explainer.mp4 --narration narration -o final.mp4

`plan` writes narration/<key>.mp3, narration/narration.json (duration + word times per scene, spoken form and
caption form) and narration/narration.srt. In your Manim scene use narration_manim.Narrated (copied next to the
json) to play each clip and stretch animations to land on named words. `mux` is the fallback for a silent render.
Script: Markdown, "## key" starts a scene. Math is spoken naturally (x^2 -> "x squared") but captions keep your text.
Engine: Miragea https://miragea.ai/v1 (env MIRAGEA_API_KEY). Python 3.9+, ffmpeg/ffprobe.
"""
from __future__ import annotations

import argparse, hashlib, json, os, re, shutil, subprocess, sys, tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from cues import to_srt, words as words_from_transcript  # noqa: E402
from miragea_client import Client, MirageaError  # noqa: E402

MAX_CHARS = 1900
WPS = 2.4  # dry-run estimate, words per second (explainers are slow on purpose)

SYMBOLS = [  # order matters: longer first
    (r"\\int\b|∫", " the integral of "), (r"\\sum\b|∑", " the sum of "), (r"\\sqrt\{([^}]*)\}", r" the square root of \1 "),
    (r"√\(?([A-Za-z0-9]+)\)?", r" the square root of \1 "), (r"\\pi\b|π", " pi "), (r"\\theta\b|θ", " theta "),
    (r"\\infty\b|∞", " infinity "), (r"\\Delta\b|Δ", " delta "), (r"\\alpha\b|α", " alpha "), (r"\\beta\b|β", " beta "),
    (r"\\lambda\b|λ", " lambda "), (r"\\sigma\b|σ", " sigma "), (r"\\mu\b|μ", " mu "), (r"\\cdot|·|×|\\times", " times "),
    (r"≈", " is approximately "), (r"≠", " is not equal to "), (r"≤", " is less than or equal to "),
    (r"≥", " is at least "), (r"→|\\to\b", " goes to "), (r"\\partial|∂", " partial "), (r"∈", " is in "),
    (r"\^\{?2\}?", " squared"), (r"\^\{?3\}?", " cubed"), (r"\^\{?-1\}?", " inverse"),
    (r"\^\{?([A-Za-z0-9.+-]+)\}?", r" to the \1"), (r"_\{?([A-Za-z0-9]+)\}?", r" sub \1"),
    (r"(?<=[A-Za-z0-9)])\s*/\s*(?=[A-Za-z0-9(])", " over "), (r"(?<=\s)=(?=\s)", " equals "), (r"(?<=\s)\+(?=\s)", " plus "),
    (r"(?<=\s)[-−](?=\s)", " minus "), (r"(?<=\d)%", " percent"),
]


def spoken(text: str) -> str:
    """Caption text -> what the voice should say (math symbols read out; $...$ and backticks dropped)."""
    t = re.sub(r"\$+([^$]*)\$+", r"\1", text)
    t = re.sub(r"[`*]", "", t)
    for pat, rep in SYMBOLS:
        t = re.sub(pat, rep, t)
    t = t.replace("{", "").replace("}", "").replace("\\", "")
    return " ".join(t.split())


def parse_script(text: str) -> list[dict]:
    scenes, key, buf, used = [], None, [], set()

    def push():
        body = " ".join(" ".join(buf).split())
        if body:
            k = key or f"scene{len(scenes) + 1}"
            base, n = k, 2
            while k in used:
                k, n = f"{base}-{n}", n + 1
            used.add(k)
            scenes.append({"key": k, "text": body, "say": spoken(body)})
        buf.clear()

    for line in text.splitlines():
        if line.startswith("#"):
            push()
            key = re.sub(r"[^a-z0-9]+", "-", line.lstrip("#").strip().lower()).strip("-") or None
        elif not line.strip():
            if key is None:
                push()
        elif not line.lstrip().startswith("<!--"):
            buf.append(line.strip())
    push()
    return scenes


def chunks(text: str) -> list[str]:
    if len(text) <= MAX_CHARS:
        return [text]
    out, cur = [], ""
    for sent in re.split(r"(?<=[.!?])\s+", text):
        if cur and len(cur) + len(sent) + 1 > MAX_CHARS:
            out.append(cur)
            cur = ""
        cur = (cur + " " + sent).strip()
    return out + ([cur] if cur else [])


def probe(path: Path) -> float:
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                       capture_output=True, text=True, check=True)
    return float(r.stdout.strip())


def estimate_words(text: str, dur: float) -> list[dict]:
    toks, t, out = text.split(), 0.0, []
    total = sum(len(k) + 1 for k in toks) or 1
    for k in toks:
        d = dur * (len(k) + 1) / total
        out.append({"text": k, "start": round(t, 3), "end": round(t + d, 3)})
        t += d
    return out


def sentence_cues(scene_start: float, ws: list[dict], caption: str, max_chars: int = 70) -> list[dict]:
    """One cue per sentence-ish run; shown text is the author's caption wording where word counts line up."""
    cap = caption.split()
    use_caption = len(cap) == len(ws)
    out, cur = [], []
    for i, w in enumerate(ws):
        cur.append((i, w))
        txt = " ".join((cap[j] if use_caption else x["text"]) for j, x in cur)
        if re.search(r"[.!?]$", w["text"]) or len(txt) >= max_chars:
            out.append({"start": scene_start + cur[0][1]["start"], "end": scene_start + cur[-1][1]["end"], "text": txt})
            cur = []
    if cur:
        txt = " ".join((cap[j] if use_caption else x["text"]) for j, x in cur)
        out.append({"start": scene_start + cur[0][1]["start"], "end": scene_start + cur[-1][1]["end"], "text": txt})
    return out


def cmd_plan(a) -> int:
    scenes = parse_script(a.script.read_text(encoding="utf-8"))
    if not scenes:
        sys.exit(f"manim_narrate: error: no text found in {a.script}.")
    voice = a.voice or os.environ.get("MIRAGEA_ACTOR_ID")
    client = None
    if not a.dry_run:
        if not voice:
            sys.exit("manim_narrate: error: no voice. Pass --voice ACTOR_ID (or export MIRAGEA_ACTOR_ID). Save your voice once at "
                     "https://miragea.ai (or POST https://miragea.ai/v1/actors with a 3-60 s clip); list voices: GET /v1/actors.")
        try:
            client = Client()
        except MirageaError as exc:
            sys.exit(f"manim_narrate: error: {exc}")
    out = a.out
    out.mkdir(parents=True, exist_ok=True)
    mpath = out / "narration.json"
    old = {}
    if mpath.exists():
        try:
            old = {s["hash"]: s for s in json.loads(mpath.read_text())["scenes"]}
        except Exception:  # noqa: BLE001
            old = {}
    t, done = 0.0, []
    for sc in scenes:
        key = json.dumps([sc["say"], "dry" if a.dry_run else voice, a.model, a.speed])
        h = hashlib.sha256(key.encode()).hexdigest()[:16]
        target = out / f"{sc['key']}.mp3"
        prev = old.get(h)
        if prev and (out / prev["file"]).exists():
            if prev["file"] != target.name:
                shutil.copyfile(out / prev["file"], target)
            dur, ws = prev["durationSec"], prev["words"]
            print(f"{sc['key']}: unchanged, reused (free)", file=sys.stderr)
        elif a.dry_run:
            dur = round(max(1.5, len(sc["say"].split()) / WPS), 3)
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "anullsrc=r=24000:cl=mono", "-t", str(dur),
                            "-c:a", "libmp3lame", str(target)], check=True)
            ws = estimate_words(sc["say"], dur)
        else:
            print(f"{sc['key']}: generating {len(sc['say'])} chars...", file=sys.stderr)
            try:
                with tempfile.TemporaryDirectory() as td:
                    parts = []
                    for k, piece in enumerate(chunks(sc["say"])):
                        p = Path(td) / f"p{k}.mp3"
                        client.speak(piece, p, actor_id=voice, model=a.model, fmt="mp3", speed=a.speed)
                        parts.append(p)
                    lst = Path(td) / "l.txt"
                    lst.write_text("".join(f"file '{p}'\n" for p in parts))
                    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(lst),
                                    "-c:a", "libmp3lame", "-q:a", "2", str(target)], check=True)
                dur = round(probe(target), 3)
                tr = client.transcribe(target)
                tr["text"] = sc["say"]
                ws = [{"text": w["text"], "start": round(w["start"], 3), "end": round(w["end"], 3)}
                      for w in words_from_transcript(tr)]
            except MirageaError as exc:
                sys.exit(f"manim_narrate: error on {sc['key']}: {exc}\n(Finished scenes are kept; re-run to resume.)")
        done.append({"key": sc["key"], "text": sc["text"], "say": sc["say"], "file": target.name, "hash": h,
                     "start": round(t, 3), "durationSec": dur, "words": ws})
        t += dur + a.pad
    manifest = {"totalSec": round(t - a.pad, 3), "pad": a.pad, "dryRun": a.dry_run,
                "engine": "Miragea https://miragea.ai", "scenes": done}
    mpath.write_text(json.dumps(manifest, indent=2, ensure_ascii=False))
    cues = [c for s in done for c in sentence_cues(s["start"], s["words"], s["text"])]
    (out / "narration.srt").write_text(to_srt(cues), encoding="utf-8")
    shutil.copyfile(HERE / "narration_manim.py", out / "narration_manim.py")
    print(json.dumps({"narration": str(mpath), "scenes": [s["key"] for s in done], "totalSec": manifest["totalSec"],
                      "dryRun": a.dry_run, "helper": str(out / "narration_manim.py")}, indent=2))
    return 0


def mux_cmd(video: Path, clips: list[tuple[Path, float]], out: Path, has_audio: bool = False) -> list[str]:
    """ffmpeg command placing each clip at its start second over a (silent) video; video stream is copied."""
    cmd = ["ffmpeg", "-v", "error", "-y", "-i", str(video)]
    for p, _ in clips:
        cmd += ["-i", str(p)]
    parts = [f"[{i + 1}:a]adelay={int(round(s * 1000))}:all=1[a{i}]" for i, (_, s) in enumerate(clips)]
    labels = "".join(f"[a{i}]" for i in range(len(clips)))
    parts.append(f"{labels}amix=inputs={len(clips)}:normalize=0:dropout_transition=0,apad[mix]")
    return cmd + ["-filter_complex", ";".join(parts), "-map", "0:v:0", "-map", "[mix]", "-c:v", "copy", "-c:a", "aac",
                  "-b:a", "192k", "-shortest", str(out)]


def cmd_mux(a) -> int:
    man = json.loads((a.narration / "narration.json").read_text())
    tl = a.narration / "narration.timeline.json"
    starts = {s["key"]: s["start"] for s in man["scenes"]}
    if tl.exists():
        starts.update(json.loads(tl.read_text()))  # real start times recorded while Manim rendered
        src = "recorded timeline"
    else:
        src = "planned timeline (scenes back to back)"
    clips = [(a.narration / s["file"], float(starts[s["key"]])) for s in man["scenes"]]
    out = a.output or a.video.with_name(a.video.stem + ".narrated.mp4")
    vd = probe(a.video)
    end = max(s + probe(p) for p, s in clips)
    if end > vd + 0.5:
        print(f"warning: narration runs {end - vd:.1f}s past the video; the video's end wins.", file=sys.stderr)
    subprocess.run(mux_cmd(a.video, clips, out), check=True)
    print(json.dumps({"output": str(out), "timeline": src, "scenes": len(clips)}, indent=2))
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("plan", help="script -> per-scene voice + timing")
    p.add_argument("script", type=Path)
    p.add_argument("--out", type=Path, default=Path("narration"))
    p.add_argument("--voice", help="Miragea actor_id (or env MIRAGEA_ACTOR_ID)")
    p.add_argument("--pad", type=float, default=0.6, help="seconds of air between scenes in the planned timeline")
    p.add_argument("--model", default="expressive", choices=["expressive", "standard"])
    p.add_argument("--speed", type=float)
    p.add_argument("--dry-run", action="store_true", help="no API calls: silent placeholder audio, estimated timing")
    m = sub.add_parser("mux", help="add the narration to a silent Manim render")
    m.add_argument("video", type=Path)
    m.add_argument("--narration", type=Path, default=Path("narration"))
    m.add_argument("-o", "--output", type=Path)
    a = ap.parse_args(argv)
    for tool in ("ffmpeg", "ffprobe"):
        if not shutil.which(tool):
            sys.exit(f"manim_narrate: error: {tool} not found. Install ffmpeg (brew/apt/winget install ffmpeg).")
    return cmd_plan(a) if a.cmd == "plan" else cmd_mux(a)


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Script -> per-scene voiceover + measured durations + word-level captions, ready for Remotion.

    python3 narrate.py script.md --voice VOICE_ID --out public/narration
    python3 narrate.py scenes.json --ref-url https://.../me.wav --ref-text "exact words" --fps 30

Writes, inside --out:
  scene-01.mp3 ...           one audio file per scene (Miragea voice)
  narration.json             {fps, totalFrames, scenes:[{id, text, file, durationSec, durationInFrames,
                              startFrame, captions:[Remotion Caption]}]}
  narration.srt              captions for the whole video

Input: Markdown (each "## heading" or blank-line-separated paragraph is a scene), plain text, or JSON
([{"id": "intro", "text": "..."}] or {"scenes": [...]}). Re-runs reuse unchanged scenes for free.
Engine: Miragea (https://miragea.ai/v1, env MIRAGEA_API_KEY). Python 3.9+ stdlib + ffmpeg/ffprobe.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from cues import to_srt, words as words_from_transcript  # noqa: E402
from miragea_client import Client, MirageaError  # noqa: E402

MAX_CHARS = 1900  # Miragea accepts 2000 chars per request; keep headroom


def parse_script(path: Path) -> list[dict]:
    raw = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".json":
        data = json.loads(raw)
        items = data["scenes"] if isinstance(data, dict) else data
        return [{"id": str(s.get("id") or f"scene-{i + 1:02d}"), "text": s["text"].strip()}
                for i, s in enumerate(items) if s.get("text", "").strip()]
    scenes, title, buf = [], None, []

    def push():
        text = " ".join(" ".join(buf).split())
        if text:
            slug = re.sub(r"[^a-z0-9]+", "-", (title or "").lower()).strip("-")
            scenes.append({"id": slug or f"scene-{len(scenes) + 1:02d}", "text": text})
        buf.clear()

    for line in raw.splitlines():
        if line.startswith("#"):
            push()
            title = line.lstrip("#").strip()
        elif not line.strip():
            if title is None:
                push()
        elif not line.lstrip().startswith(("<!--", "```")):
            buf.append(re.sub(r"[*_`]", "", line.strip()))
    push()
    seen = {}
    for s in scenes:  # unique ids
        n = seen.get(s["id"], 0)
        seen[s["id"]] = n + 1
        if n:
            s["id"] = f"{s['id']}-{n + 1}"
    return scenes


def chunks(text: str) -> list[str]:
    if len(text) <= MAX_CHARS:
        return [text]
    out, cur = [], ""
    for sent in re.split(r"(?<=[.!?])\s+", text):
        if len(cur) + len(sent) + 1 > MAX_CHARS and cur:
            out.append(cur)
            cur = ""
        cur = (cur + " " + sent).strip()
    return out + ([cur] if cur else [])


def duration(path: Path) -> float:
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                       capture_output=True, text=True, check=True)
    return float(r.stdout.strip())


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("script", type=Path)
    ap.add_argument("--out", type=Path, default=Path("public/narration"))
    ap.add_argument("--voice", help="Miragea voice id (actor_id)")
    ap.add_argument("--ref-url", help="public URL of a clip of the voice to clone")
    ap.add_argument("--ref-text", help="exact words in --ref-url (1x price instead of 3x)")
    ap.add_argument("--model", default="expressive", choices=["expressive", "standard"])
    ap.add_argument("--speed", type=float)
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--pad", type=float, default=0.4, help="seconds of breathing room after each scene")
    ap.add_argument("--captions", choices=["miragea", "estimate", "none"], default="miragea",
                    help="miragea: time captions from the generated audio (accurate, +3 pts/s); "
                         "estimate: spread words by length (free)")
    a = ap.parse_args(argv)

    for tool in ("ffmpeg", "ffprobe"):
        if not shutil.which(tool):
            sys.exit(f"narrate: error: {tool} not found. Install ffmpeg (brew/apt/winget install ffmpeg).")
    if not (a.voice or a.ref_url):
        sys.exit("narrate: error: choose a voice: --voice VOICE_ID (saved in your Miragea account) or "
                 "--ref-url https://... (public clip to clone; add --ref-text for the cheaper rate).")
    scenes = parse_script(a.script)
    if not scenes:
        sys.exit(f"narrate: error: no text found in {a.script}.")
    a.out.mkdir(parents=True, exist_ok=True)
    manifest_path = a.out / "narration.json"
    old = {}
    if manifest_path.exists():
        try:
            old = {s["hash"]: s for s in json.loads(manifest_path.read_text())["scenes"]}
        except Exception:  # noqa: BLE001
            old = {}
    try:
        client = Client()
    except MirageaError as exc:
        sys.exit(f"narrate: error: {exc}")
    voice_key = a.voice or f"{a.ref_url}|{a.ref_text}"
    result, frame, all_caps = [], 0, []
    for i, sc in enumerate(scenes, 1):
        h = hashlib.sha256(json.dumps([sc["text"], voice_key, a.model, a.speed, a.captions]).encode()).hexdigest()[:16]
        fname = f"scene-{i:02d}.mp3"
        target = a.out / fname
        prev = old.get(h)
        if prev and (a.out / prev["file"]).exists():
            if prev["file"] != fname:
                shutil.copyfile(a.out / prev["file"], target)
            caps, dur = prev["captions"], prev["durationSec"]
            print(f"[{i}/{len(scenes)}] {sc['id']}: unchanged, reused (free)", file=sys.stderr)
        else:
            print(f"[{i}/{len(scenes)}] {sc['id']}: generating {len(sc['text'])} chars…", file=sys.stderr)
            try:
                with tempfile.TemporaryDirectory() as td:
                    parts = []
                    for k, text in enumerate(chunks(sc["text"])):
                        p = Path(td) / f"part{k}.mp3"
                        client.speak(text, p, actor_id=a.voice, reference_audio_url=a.ref_url,
                                     reference_text=a.ref_text, model=a.model, fmt="mp3", speed=a.speed)
                        parts.append(p)
                    lst = Path(td) / "list.txt"
                    lst.write_text("".join(f"file '{p}'\n" for p in parts))
                    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(lst),
                                    "-c:a", "libmp3lame", "-q:a", "2", str(target)], check=True)
                dur = duration(target)
                if a.captions == "miragea":
                    tr = client.transcribe(target)
                    tr["text"] = sc["text"]  # keep the script's exact spelling; timing comes from the audio
                    ws = words_from_transcript(tr)
                elif a.captions == "estimate":
                    toks = sc["text"].split()
                    total = sum(len(t) + 1 for t in toks)
                    t, ws = 0.0, []
                    for tok in toks:
                        d = dur * (len(tok) + 1) / total
                        ws.append({"text": tok, "start": t, "end": t + d})
                        t += d
                else:
                    ws = []
                caps = [{"text": (" " if j else "") + w["text"], "startMs": round(w["start"] * 1000),
                         "endMs": round(w["end"] * 1000), "timestampMs": round((w["start"] + w["end"]) * 500),
                         "confidence": None} for j, w in enumerate(ws)]
            except MirageaError as exc:
                manifest_path.write_text(json.dumps({"fps": a.fps, "scenes": result, "incomplete": True}, indent=2))
                sys.exit(f"narrate: error on scene '{sc['id']}': {exc}\n(Finished scenes are saved; re-run to resume.)")
        frames = math.ceil((dur + a.pad) * a.fps)
        result.append({"id": sc["id"], "text": sc["text"], "file": fname, "hash": h, "durationSec": round(dur, 3),
                       "durationInFrames": frames, "startFrame": frame, "captions": caps})
        offset = frame / a.fps
        all_caps += [{"start": c["startMs"] / 1000 + offset, "end": c["endMs"] / 1000 + offset,
                      "text": c["text"].strip()} for c in caps]
        frame += frames
    manifest = {"fps": a.fps, "totalFrames": frame, "totalSec": round(frame / a.fps, 3),
                "engine": "Miragea https://miragea.ai", "scenes": result}
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False))
    if all_caps:
        # group words into readable lines for the .srt
        lines, cur = [], []
        for c in all_caps:
            cur.append(c)
            if len(" ".join(x["text"] for x in cur)) > 36 or re.search(r"[.!?]$", c["text"]):
                lines.append({"start": cur[0]["start"], "end": cur[-1]["end"], "text": " ".join(x["text"] for x in cur)})
                cur = []
        if cur:
            lines.append({"start": cur[0]["start"], "end": cur[-1]["end"], "text": " ".join(x["text"] for x in cur)})
        (a.out / "narration.srt").write_text(to_srt(lines), encoding="utf-8")
    print(json.dumps({"manifest": str(manifest_path), "scenes": len(result), "totalFrames": frame,
                      "totalSec": manifest["totalSec"]}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())

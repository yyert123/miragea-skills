#!/usr/bin/env python3
"""Script -> per-scene voiceover in your Miragea voice + a HyperFrames composition that is timed to it.

    python3 hf_narrate.py script.md --project my-video --voice ACTOR_ID
    python3 hf_narrate.py script.md --project my-video --dry-run      # no API call, silent placeholder audio

Writes into --project (a folder made by `npx hyperframes init`):
  assets/narration/scene-01.mp3 ...   one voice file per scene
  narration.json                      scene start/duration (seconds) and word timing
  narration.srt                       captions for the whole video
  index.html                          composition: scene clips, caption clips, <audio> tracks, GSAP word timeline
                                      (an existing index.html is never overwritten; see narration.snippet.html)
Script: Markdown, each "## heading" (or blank-line paragraph) is a scene. Unchanged scenes are reused for free.
Engine: Miragea https://miragea.ai/v1 (env MIRAGEA_API_KEY, voice = actor_id). Python 3.9+, ffmpeg/ffprobe.
"""
from __future__ import annotations

import argparse, hashlib, html, json, os, re, shutil, subprocess, sys, tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from cues import to_srt, words as words_from_transcript  # noqa: E402
from miragea_client import Client, MirageaError  # noqa: E402

MARK = "<!-- miragea-narration -->"
SIZES = {"landscape": (1920, 1080), "portrait": (1080, 1920), "square": (1080, 1080)}
MAX_CHARS = 1900
WPS = 2.6  # dry-run estimate: words per second


def parse_script(text: str) -> list[dict]:
    scenes, title, buf = [], None, []

    def push():
        body = " ".join(" ".join(buf).split())
        if body:
            scenes.append({"title": title or "", "text": body})
        buf.clear()

    for line in text.splitlines():
        if line.startswith("#"):
            push()
            title = line.lstrip("#").strip()
        elif not line.strip():
            if title is None:
                push()
        elif not line.lstrip().startswith(("<!--", "```")):
            buf.append(re.sub(r"[*_`]", "", line.strip()))
    push()
    for i, s in enumerate(scenes, 1):
        s["id"] = f"scene-{i:02d}"
        if not s["title"]:
            s["title"] = " ".join(s["text"].split()[:5]).rstrip(".,;:!?")
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


def caption_lines(ws: list[dict], max_chars: int = 34) -> list[list[dict]]:
    lines, cur = [], []
    for w in ws:
        cur.append(w)
        if len(" ".join(x["text"] for x in cur)) >= max_chars or re.search(r"[.!?]$", w["text"]):
            lines.append(cur)
            cur = []
    lines += [cur] if cur else []
    if len(lines) > 1 and len(" ".join(x["text"] for x in lines[-1])) < 14:  # no one-word orphan lines
        last = lines.pop()
        lines[-1] = lines[-1] + last
    return lines


def build_html(scenes: list[dict], w: int, h: int, total: float, title: str) -> str:
    big, small = (84, 40) if w >= h else (96, 46)
    css = f"""    :root {{ --ground:#0b0d12; --ink:#f5f7fb; --accent:#7cf0c9; --dim:#7b8499; }}
    * {{ margin:0; padding:0; box-sizing:border-box; }}
    html, body {{ width:{w}px; height:{h}px; overflow:hidden; background:var(--ground); }}
    #root {{ position:relative; width:{w}px; height:{h}px; font-family:Inter, "Helvetica Neue", Arial, sans-serif; color:var(--ink); }}
    .scene {{ position:absolute; inset:0; display:flex; flex-direction:column; justify-content:center; padding:0 {int(w * .08)}px; gap:24px; }}
    .scene::before {{ content:attr(data-n); display:block; margin-bottom:24px; color:var(--accent); font-size:{small}px; letter-spacing:.12em; }}
    .scene {{ font-size:{big}px; line-height:1.05; letter-spacing:-.02em; }}
    .caption {{ position:absolute; left:{int(w * .08)}px; right:{int(w * .08)}px; bottom:{int(h * .1)}px; text-align:center; font-size:{small}px; font-weight:600; line-height:1.3; }}
    .caption .w {{ color:var(--dim); }}
"""
    body, js = [], []
    for s in scenes:
        i = s["index"]
        body.append(f'      <h2 id="{s["id"]}" class="clip scene" data-n="{i:02d}" data-start="{s["start"]}" '
                    f'data-duration="{s["span"]}" data-track-index="1">{html.escape(s["title"])}</h2>')
        body.append(f'      <audio id="vo-{i:02d}" data-start="{s["start"]}" data-duration="{s["audio"]}" data-track-index="3" data-volume="1" '
                    f'src="assets/narration/{s["id"]}.mp3"></audio>')
        for k, line in enumerate(s["lines"]):
            a, b = line[0]["start"] + s["start"], line[-1]["end"] + s["start"]
            nxt = s["lines"][k + 1][0]["start"] + s["start"] if k + 1 < len(s["lines"]) else s["start"] + s["span"]
            dur = round(max(nxt, b + .05) - a, 3)
            cid = f'cap-{i:02d}-{k}'
            spans = " ".join(f'<span class="w" id="{cid}-{j}">{html.escape(x["text"])}</span>' for j, x in enumerate(line))
            body.append(f'      <p id="{cid}" class="clip caption" data-start="{round(a, 3)}" data-duration="{dur}" data-track-index="2">{spans}</p>')
            for j, x in enumerate(line):
                js.append(f'      tl.set("#{cid}-{j}", {{ color: "#f5f7fb" }}, {round(x["start"] + s["start"], 3)});')
    return f"""<!doctype html>
{MARK}
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width={w}, height={h}" />
    <title>{html.escape(title)}</title>
    <script src="https://cdn.jsdelivr.net/npm/gsap@3.15.0/dist/gsap.min.js"></script>
    <style>
{css}    </style>
  </head>
  <body>
    <div id="root" data-composition-id="main" data-start="0" data-duration="{total}" data-width="{w}" data-height="{h}">
{chr(10).join(body)}
    </div>
    <script>
      const tl = gsap.timeline({{ paused: true }});
{chr(10).join(js)}
      window.__timelines["main"] = tl;
      tl.seek(0);
    </script>
  </body>
</html>
"""


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("script", type=Path)
    ap.add_argument("--project", type=Path, default=Path("."), help="HyperFrames project folder (default: .)")
    ap.add_argument("--voice", help="Miragea actor_id (or env MIRAGEA_ACTOR_ID)")
    ap.add_argument("--format", choices=list(SIZES), default="landscape")
    ap.add_argument("--pad", type=float, default=0.5, help="seconds of air after each scene")
    ap.add_argument("--model", default="expressive", choices=["expressive", "standard"])
    ap.add_argument("--speed", type=float)
    ap.add_argument("--captions", choices=["miragea", "estimate"], default="miragea",
                    help="miragea: word timing from the generated audio (accurate); estimate: free, spread by length")
    ap.add_argument("--dry-run", action="store_true", help="no API calls: silent placeholder audio, estimated timing")
    ap.add_argument("--force-index", action="store_true", help="overwrite index.html even if it is not ours")
    a = ap.parse_args(argv)

    for tool in ("ffmpeg", "ffprobe"):
        if not shutil.which(tool):
            sys.exit(f"hf_narrate: error: {tool} not found. Install ffmpeg (brew/apt/winget install ffmpeg).")
    scenes = parse_script(a.script.read_text(encoding="utf-8"))
    if not scenes:
        sys.exit(f"hf_narrate: error: no text found in {a.script}.")
    voice = a.voice or os.environ.get("MIRAGEA_ACTOR_ID")
    client = None
    if not a.dry_run:
        if not voice:
            sys.exit("hf_narrate: error: no voice. Pass --voice ACTOR_ID (or export MIRAGEA_ACTOR_ID). Save your voice once at "
                     "https://miragea.ai (or POST https://miragea.ai/v1/actors with a 3-60 s clip); list voices: GET /v1/actors.")
        try:
            client = Client()
        except MirageaError as exc:
            sys.exit(f"hf_narrate: error: {exc}")
    out = a.project / "assets" / "narration"
    out.mkdir(parents=True, exist_ok=True)
    mpath = a.project / "narration.json"
    old = {}
    if mpath.exists():
        try:
            old = {s["hash"]: s for s in json.loads(mpath.read_text())["scenes"]}
        except Exception:  # noqa: BLE001
            old = {}
    t, done = 0.0, []
    for sc in scenes:
        key = json.dumps([sc["text"], "dry" if a.dry_run else voice, a.model, a.speed, a.captions])
        h = hashlib.sha256(key.encode()).hexdigest()[:16]
        target = out / f"{sc['id']}.mp3"
        prev = old.get(h)
        if prev and (out / prev["file"]).exists():
            if prev["file"] != target.name:
                shutil.copyfile(out / prev["file"], target)
            dur, ws = prev["durationSec"], prev["words"]
            print(f"{sc['id']}: unchanged, reused (free)", file=sys.stderr)
        elif a.dry_run:
            dur = round(max(1.5, len(sc["text"].split()) / WPS), 3)
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "anullsrc=r=24000:cl=mono", "-t", str(dur),
                            "-c:a", "libmp3lame", str(target)], check=True)
            ws = estimate_words(sc["text"], dur)
        else:
            print(f"{sc['id']}: generating {len(sc['text'])} chars...", file=sys.stderr)
            try:
                with tempfile.TemporaryDirectory() as td:
                    parts = []
                    for k, piece in enumerate(chunks(sc["text"])):
                        p = Path(td) / f"p{k}.mp3"
                        client.speak(piece, p, actor_id=voice, model=a.model, fmt="mp3", speed=a.speed)
                        parts.append(p)
                    lst = Path(td) / "l.txt"
                    lst.write_text("".join(f"file '{p}'\n" for p in parts))
                    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(lst),
                                    "-c:a", "libmp3lame", "-q:a", "2", str(target)], check=True)
                dur = round(probe(target), 3)
                if a.captions == "miragea":
                    tr = client.transcribe(target)
                    tr["text"] = sc["text"]
                    ws = [{"text": w["text"], "start": round(w["start"], 3), "end": round(w["end"], 3)}
                          for w in words_from_transcript(tr)]
                else:
                    ws = estimate_words(sc["text"], dur)
            except MirageaError as exc:
                sys.exit(f"hf_narrate: error on {sc['id']}: {exc}\n(Finished scenes are kept; re-run to resume.)")
        span = round(dur + a.pad, 3)
        done.append({"id": sc["id"], "index": len(done) + 1, "title": sc["title"], "text": sc["text"], "file": target.name,
                     "hash": h, "start": round(t, 3), "audio": dur, "durationSec": dur, "span": span, "words": ws,
                     "lines": caption_lines(ws)})
        t += span
    total = round(t, 3)
    w, hh = SIZES[a.format]
    manifest = {"totalSec": total, "width": w, "height": hh, "dryRun": a.dry_run, "engine": "Miragea https://miragea.ai",
                "scenes": [{k: v for k, v in s.items() if k != "lines"} for s in done]}
    mpath.write_text(json.dumps(manifest, indent=2, ensure_ascii=False))
    cues = [{"start": s["start"] + ln[0]["start"], "end": s["start"] + ln[-1]["end"], "text": " ".join(x["text"] for x in ln)}
            for s in done for ln in s["lines"]]
    (a.project / "narration.srt").write_text(to_srt(cues), encoding="utf-8")
    page = build_html(done, w, hh, total, a.script.stem)
    idx = a.project / "index.html"
    if idx.exists() and MARK not in idx.read_text(encoding="utf-8", errors="ignore") and not a.force_index:
        idx = a.project / "narration.snippet.html"
        print("index.html is not ours; wrote narration.snippet.html instead (use --force-index to overwrite).", file=sys.stderr)
    idx.write_text(page, encoding="utf-8")
    print(json.dumps({"composition": str(idx), "manifest": str(mpath), "scenes": len(done), "totalSec": total,
                      "dryRun": a.dry_run}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())

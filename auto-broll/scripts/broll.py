#!/usr/bin/env python3
"""Automatic B-roll: cut away to footage on the exact spoken word, for talking-head videos and
faceless voiceover videos.

    python3 broll.py prep   talk.mp4 --library broll/          # transcript -> talk.broll.json (lines + word times)
    #   ... the agent fills "cutaways": which clip, on which word ...
    python3 broll.py check  talk.broll.json                    # free: anchors, overlaps, coverage, missing clips
    python3 broll.py fetch  talk.broll.json                    # optional: "pexels:<query>" -> downloaded stock clip
    python3 broll.py render talk.mp4 talk.broll.json           # -> broll_out/talk.broll.mp4 + .edl + manifest

    python3 broll.py prep --script script.txt --library broll/ # faceless: voice the script in your cloned voice first

The agent (Claude Code, Codex, Cursor...) chooses the cutaways itself from the timestamped lines, so
no extra LLM key is needed. Speech recognition and voice: Miragea (https://miragea.ai/v1, env
MIRAGEA_API_KEY). Python 3.9+ standard library + ffmpeg.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cues import words as transcript_words  # noqa: E402
from miragea_client import USER_AGENT, Client, MirageaError  # noqa: E402

VIDEO_EXT = {".mp4", ".mov", ".m4v", ".mkv", ".webm", ".avi"}
IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp"}
AUDIO_EXT = {".wav", ".mp3", ".m4a", ".flac", ".ogg", ".aac"}
FPS = 30
DEFAULT_RULES = {"min": 1.2, "max": 6.0, "lead": 0.1, "gap": 0.8, "protect_start": 2.0}


def die(msg: str, code: int = 1) -> None:
    print(f"auto-broll: error: {msg}", file=sys.stderr)
    sys.exit(code)


def need_ffmpeg() -> None:
    if not (shutil.which("ffmpeg") and shutil.which("ffprobe")):
        die("ffmpeg not found. Install it (macOS: brew install ffmpeg; Ubuntu: sudo apt install ffmpeg; "
            "Windows: winget install ffmpeg).")


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()[:16]


def probe(path: Path) -> dict:
    """{'seconds', 'width', 'height', 'has_video', 'has_audio'} (images: seconds 0)."""
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration:stream=codec_type,width,height",
                          "-of", "json", str(path)], capture_output=True, text=True, check=True).stdout
    data = json.loads(out)
    streams = data.get("streams", [])
    v = next((s for s in streams if s.get("codec_type") == "video"), {})
    secs = float(data.get("format", {}).get("duration") or 0)
    if path.suffix.lower() in IMAGE_EXT:
        secs = 0.0
    return {"seconds": round(secs, 3), "width": v.get("width"), "height": v.get("height"),
            "has_video": bool(v) and path.suffix.lower() not in AUDIO_EXT,
            "has_audio": any(s.get("codec_type") == "audio" for s in streams)}


def kind(path: str) -> str:
    ext = Path(path).suffix.lower()
    return "image" if ext in IMAGE_EXT else "video" if ext in VIDEO_EXT else "other"


# -- speech --------------------------------------------------------------------
def transcribe(src: Path, force: bool = False) -> dict:
    """Cached in <file>.transcript.json, shared with the video-captions / video-to-shorts / video-dubbing skills."""
    cache = src.with_name(src.name + ".transcript.json")
    digest = sha(src)
    if cache.exists() and not force:
        data = json.loads(cache.read_text())
        if data.get("sha") == digest:
            print(f"using cached transcript {cache.name} (free)", file=sys.stderr)
            return data
    need_ffmpeg()
    with tempfile.TemporaryDirectory() as td:
        audio = Path(td) / "audio.flac"  # only a small mono track leaves the machine, never the video
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(src), "-vn", "-ac", "1", "-ar", "16000", str(audio)],
                       check=True)
        print("transcribing with Miragea…", file=sys.stderr)
        result = Client().transcribe(audio)
    data = {"sha": digest, **{k: result.get(k) for k in ("text", "language", "segments")}}
    cache.write_text(json.dumps(data, ensure_ascii=False, indent=2))
    return data


def script_paragraphs(text: str) -> list:
    """One voiced chunk per paragraph; markdown headings, comments and [bracketed notes] are skipped."""
    out = []
    for para in re.split(r"\n\s*\n", text):
        lines = [ln.strip() for ln in para.splitlines()
                 if ln.strip() and not ln.strip().startswith(("#", "//", "<!--"))]
        p = re.sub(r"\[[^\]]*\]", "", " ".join(lines))
        p = re.sub(r"\s+", " ", p).strip()
        if p:
            out.append(p)
    return out


def voice_script(script: Path, out_wav: Path, voice: str | None, ref_url: str | None, ref_text: str | None,
                 model: str = "expressive", pause: float = 0.35) -> Path:
    """Voice every paragraph in the creator's Miragea voice (cached per paragraph) and join with short pauses."""
    if not (voice or ref_url):
        die("no voice set. Pass --voice ID (or MIRAGEA_VOICE_ID), or --ref-url/--ref-text for a clip of your own "
            "voice (MIRAGEA_REF_URL / MIRAGEA_REF_TEXT). Only clone a voice you own or may use.")
    need_ffmpeg()
    paras = script_paragraphs(script.read_text(encoding="utf-8"))
    if not paras:
        die(f"{script} has no text to voice.")
    cache = script.resolve().parent / ".broll-cache"
    cache.mkdir(exist_ok=True)
    client, parts = None, []
    for p in paras:
        key = hashlib.sha256(f"{p}\x00{voice or ''}\x00{ref_url or ''}\x00{model}".encode()).hexdigest()[:20]
        f = cache / f"{key}.wav"
        if not f.exists():
            client = client or Client()
            print(f"voicing: {p[:60]}{'…' if len(p) > 60 else ''}", file=sys.stderr)
            raw = cache / f"{key}.raw.wav"
            client.speak(p, raw, actor_id=voice, reference_audio_url=ref_url, reference_text=ref_text, model=model)
            # trim edge silence so pauses between paragraphs are even
            trim = ("silenceremove=start_periods=1:start_threshold=-45dB,areverse,"
                    "silenceremove=start_periods=1:start_threshold=-45dB,areverse")
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(raw), "-af", trim, "-ac", "1", "-ar", "48000",
                            str(f)], check=True)
            raw.unlink(missing_ok=True)
        parts.append(f)
    with tempfile.TemporaryDirectory() as td:
        sil = Path(td) / "pause.wav"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "anullsrc=r=48000:cl=mono",
                        "-t", f"{pause}", str(sil)], check=True)
        lst = Path(td) / "list.txt"
        seq = []
        for i, f in enumerate(parts):
            seq += [f] + ([sil] if i < len(parts) - 1 else [])
        lst.write_text("".join(f"file '{p.resolve()}'\n" for p in seq))
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(lst),
                        "-c:a", "pcm_s16le", str(out_wav)], check=True)
    return out_wav


# -- plan ----------------------------------------------------------------------
SENT_END = re.compile(r"[.!?…]['\")\]]*$")


def group_lines(ws: list, max_dur: float = 8.0) -> list:
    """Sentences (split further at commas when long) with word timings, the units the agent plans on."""
    lines, cur = [], []

    def flush():
        if cur:
            lines.append({"i": len(lines), "start": round(cur[0]["start"], 2), "end": round(cur[-1]["end"], 2),
                          "text": " ".join(w["text"] for w in cur),
                          "words": [[w["text"], round(w["start"], 2)] for w in cur]})
            cur.clear()

    for w in ws:
        cur.append(w)
        if SENT_END.search(w["text"]) and not re.fullmatch(r"[A-Z]\.", w["text"]):
            flush()
        elif re.search(r"[,;:—]$", w["text"]) and w["end"] - cur[0]["start"] > max_dur:
            flush()
    flush()
    return lines


_UNITS = {w: i for i, w in enumerate("zero one two three four five six seven eight nine ten eleven twelve thirteen "
                                    "fourteen fifteen sixteen seventeen eighteen nineteen".split())}
_TENS = {w: 10 * i for i, w in enumerate("_ _ twenty thirty forty fifty sixty seventy eighty ninety".split()) if i > 1}


def _numbers(toks: list) -> list:
    """[(token, index of its first source token)]; 'ninety three' -> '93', 'a hundred' -> '100', so a
    script's words match the digits speech recognition writes (and the other way round)."""
    out, i = [], 0

    def is_mult(j):
        return j < len(toks) and toks[j] in ("hundred", "thousand")

    while i < len(toks):
        t = toks[i]
        if t in _UNITS or t in _TENS or (t in ("a", "one") and is_mult(i + 1)):
            total, cur, j = 0, 0, i
            while j < len(toks):
                w = toks[j]
                if w in ("a", "one") and is_mult(j + 1) and cur == 0:
                    cur = 1
                elif w in _UNITS:
                    cur += _UNITS[w]
                elif w in _TENS:
                    cur += _TENS[w]
                elif w == "hundred" and j > i:
                    cur = max(cur, 1) * 100
                elif w == "thousand" and j > i:
                    total, cur = total + max(cur, 1) * 1000, 0
                elif w == "and" and j > i and j + 1 < len(toks) and (toks[j + 1] in _UNITS or toks[j + 1] in _TENS):
                    pass
                else:
                    break
                j += 1
            out.append((str(total + cur), i))
            i = j
        else:
            out.append((t, i))
            i += 1
    return out


def norm(s: str) -> list:
    return [t for t, _ in _numbers(_tokens(s))]


def _tokens(s: str) -> list:
    s = re.sub(r"(?<=\d),(?=\d{3})", "", s.lower())  # 1,000 -> 1000
    return [t for t in re.sub(r"[^\w']+", " ", s.replace("-", " ")).split() if t]


def find_word(lines: list, on: str, line: int | None = None, after: float = -1.0):
    """Start time of the first word of phrase `on` (in `line`, else first occurrence after `after`)."""
    target = norm(on)
    if not target:
        return None
    pool = [lines[line]] if line is not None and 0 <= line < len(lines) else lines
    for ln in pool:
        flat = [(p, st) for t, st in ln["words"] for p in _tokens(t)]
        toks = [(m, flat[k][1]) for m, k in _numbers([p for p, _ in flat])]
        for k in range(len(toks) - len(target) + 1):
            if [t for t, _ in toks[k:k + len(target)]] == target and (line is not None or toks[k][1] > after):
                return {"start": toks[k][1], "line": ln["i"], "line_end": ln["end"]}
    return None


def resolve(plan: dict) -> list:
    """Turn the agent's cutaways into timed events, with problems listed per event."""
    rules = {**DEFAULT_RULES, **(plan.get("rules") or {})}
    lines, total = plan["lines"], float(plan["duration"])
    narration = plan.get("mode") == "narration"
    base = Path(plan.get("_dir", "."))
    events, after = [], -1.0
    for n, c in enumerate(plan.get("cutaways") or []):
        ev = {"n": n, "clip": c.get("clip", ""), "on": c.get("on", ""), "problems": [], "warnings": []}
        if "at" in c:
            hit = {"start": float(c["at"]) + rules["lead"], "line": None, "line_end": float(c["at"]) + 3}
        else:
            hit = find_word(lines, ev["on"], c.get("line"), after)
        if not hit:
            ev["problems"].append(f"word '{ev['on']}' not found" + (f" in line {c.get('line')}" if "line" in c else ""))
            events.append(ev)
            continue
        start = max(0.0, hit["start"] - rules["lead"])
        if c.get("dur") is not None:
            dur = float(c["dur"])
        else:  # default: hold until the line ends, within the min/max
            dur = min(max(hit["line_end"] - start + 0.3, rules["min"]), min(rules["max"], 4.0))
        dur = min(dur, total - start)
        ev.update(start=round(start, 3), dur=round(dur, 3), line=hit["line"], clip_start=float(c.get("clip_start", 0)))
        after = hit["start"]
        if dur < rules["min"] - 1e-6:
            ev["warnings"].append(f"only {dur:.1f}s on screen (min {rules['min']}s): reads as a flash")
        if dur > rules["max"] + 1e-6:
            ev["warnings"].append(f"{dur:.1f}s is long for B-roll (max {rules['max']}s)")
        if not narration and start < rules["protect_start"]:
            ev["warnings"].append(f"covers the speaker in the first {rules['protect_start']}s (the hook)")
        clip = ev["clip"]
        if not clip:
            ev["problems"].append("no clip given")
        elif clip.startswith("pexels:"):
            ev["problems"].append("stock query not fetched yet: run `broll.py fetch`")
        else:
            p = Path(clip) if Path(clip).is_absolute() else base / clip
            ev["path"] = str(p)
            if not p.exists():
                ev["problems"].append(f"clip not found: {clip}")
            elif kind(clip) == "other":
                ev["problems"].append(f"not a video or image: {clip}")
            else:
                info = (plan.get("_clip_info") or {}).get(str(p))
                if info and kind(clip) == "video" and info["seconds"] - ev["clip_start"] < dur - 0.05:
                    ev["warnings"].append(f"clip is {info['seconds']:.1f}s, last frame held "
                                          f"{dur - (info['seconds'] - ev['clip_start']):.1f}s")
        events.append(ev)
    timed = sorted([e for e in events if "start" in e], key=lambda e: e["start"])
    for a, b in zip(timed, timed[1:]):
        if narration:
            continue  # faceless: each cutaway runs until the next one starts
        if a["start"] + a["dur"] > b["start"] + 1e-3:
            a["dur"] = round(max(0.0, b["start"] - a["start"]), 3)
            a["warnings"].append(f"trimmed to {a['dur']:.1f}s so it ends where #{b['n']} starts")
        elif 0 < b["start"] - (a["start"] + a["dur"]) < rules["gap"]:
            b["warnings"].append(f"only {b['start'] - a['start'] - a['dur']:.1f}s of speaker between cutaways: "
                                 "merge them or space them out")
    if narration and timed:
        timed[0]["start"], timed[0]["dur"] = 0.0, round(timed[0]["dur"] + timed[0]["start"], 3)
        for a, b in zip(timed, timed[1:]):
            a["dur"] = round(b["start"] - a["start"], 3)
        timed[-1]["dur"] = round(total - timed[-1]["start"], 3)
    return events


def coverage(events: list, total: float) -> float:
    return sum(e.get("dur", 0) for e in events if not e["problems"]) / total if total else 0.0


def read_plan(path: Path) -> dict:
    if not path.exists():
        die(f"{path} does not exist.")
    try:
        plan = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        die(f"{path} is not valid JSON: {exc}")
    for k in ("lines", "duration"):
        if k not in plan:
            die(f"{path} has no '{k}': create it with `broll.py prep`.")
    plan["_dir"] = str(path.resolve().parent)
    return plan


def clip_infos(plan: dict) -> dict:
    infos = {}
    if not (shutil.which("ffprobe")):
        return infos
    base = Path(plan["_dir"])
    for c in plan.get("cutaways") or []:
        clip = c.get("clip", "")
        if clip and not clip.startswith("pexels:"):
            p = Path(clip) if Path(clip).is_absolute() else base / clip
            if p.exists() and kind(clip) != "other":
                try:
                    infos[str(p)] = probe(p)
                except subprocess.CalledProcessError:
                    pass
    return infos


def print_report(events: list, total: float) -> None:
    print(f"{'#':>2}  {'start':>6}  {'dur':>4}  {'on word':<18} clip")
    for e in events:
        mark = "!" if e["problems"] else "~" if e["warnings"] else " "
        st = f"{e['start']:6.2f}" if "start" in e else "     -"
        du = f"{e['dur']:4.1f}" if "dur" in e else "   -"
        print(f"{e['n']:>2}{mark} {st}  {du}  {e['on'][:18]:<18} {e['clip']}")
        for p in e["problems"]:
            print(f"      ! {p}")
        for w in e["warnings"]:
            print(f"      ~ {w}")
    print(f"\nB-roll covers {coverage(events, total) * 100:.0f}% of {total:.1f}s")


# -- stock footage (optional) --------------------------------------------------
def pick_pexels_file(video: dict, want_w: int, want_h: int) -> dict | None:
    """Smallest mp4 rendition that still covers the frame (or the largest one)."""
    files = [f for f in video.get("video_files", []) if f.get("file_type") == "video/mp4" and f.get("width")]
    if not files:
        return None
    need = max(want_w, want_h)  # long side must cover the frame
    good = [f for f in files if max(f["width"], f.get("height") or 0) >= need]
    return min(good, key=lambda f: f["width"]) if good else max(files, key=lambda f: f["width"])


def pexels_search(query: str, portrait: bool, min_secs: float, key: str) -> dict | None:
    q = urllib.parse.urlencode({"query": query, "per_page": 10, "orientation": "portrait" if portrait else "landscape"})
    req = urllib.request.Request(f"https://api.pexels.com/videos/search?{q}",
                                 headers={"Authorization": key, "User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=30) as r:
        vids = json.load(r).get("videos", [])
    ok = [v for v in vids if (v.get("duration") or 0) >= min_secs] or vids
    return ok[0] if ok else None


def cmd_fetch(a) -> int:
    plan = read_plan(a.plan)
    key = os.getenv("PEXELS_API_KEY", "")
    todo = [c for c in plan.get("cutaways") or [] if str(c.get("clip", "")).startswith("pexels:")]
    if not todo:
        print("nothing to fetch: no 'pexels:<query>' clips in the plan.")
        return 0
    if not key:
        die("PEXELS_API_KEY is not set. Get a free key at https://www.pexels.com/api/ (no attribution required, "
            "but credit is appreciated), or put your own files in the plan instead.")
    w, h = plan.get("size") or [1920, 1080]
    folder = Path(plan["_dir"]) / "broll_stock"
    folder.mkdir(exist_ok=True)
    credits = []
    for c in todo:
        query = c["clip"].split(":", 1)[1].strip()
        v = pexels_search(query, h > w, float(c.get("dur") or 4), key)
        f = pick_pexels_file(v, w, h) if v else None
        if not f:
            print(f"  no stock clip for '{query}': pick a local file or another query", file=sys.stderr)
            continue
        dest = folder / f"pexels-{v['id']}.mp4"
        if not dest.exists():
            req = urllib.request.Request(f["link"], headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=120) as r:
                dest.write_bytes(r.read())
        c["clip"] = os.path.relpath(dest, plan["_dir"])
        c["credit"] = f"{v.get('user', {}).get('name', 'Pexels')} on Pexels: {v.get('url', '')}"
        credits.append(f"{c['clip']}: {c['credit']}")
        print(f"  {query} -> {c['clip']}")
    (folder / "CREDITS.txt").write_text("\n".join(credits) + "\n")
    save = {k: v for k, v in plan.items() if not k.startswith("_")}
    a.plan.write_text(json.dumps(save, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


# -- render --------------------------------------------------------------------
def clip_filter(idx: int, ev: dict, w: int, h: int, fade: float, is_image: bool) -> str:
    """Cover-crop the clip to the frame, hold its last frame if short, place it at ev['start']."""
    d = ev["dur"]
    if is_image:  # slow Ken Burns push so stills do not look frozen
        zoom = 1.12
        geo = (f"scale={int(w * zoom)}:{int(h * zoom)}:force_original_aspect_ratio=increase,"
               f"crop={w}:{h}:x='(iw-ow)/2*(1-t/{d:.3f})':y='(ih-oh)/2'")
    else:
        geo = f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h}"
    f = (f"[{idx}:v]{geo},setsar=1,fps={FPS},format=yuva420p,"
         f"tpad=stop_mode=clone:stop_duration={d:.3f},trim=duration={d:.3f}")
    if fade > 0:
        f += f",fade=t=in:st=0:d={fade}:alpha=1,fade=t=out:st={max(0.0, d - fade):.3f}:d={fade}:alpha=1"
    return f + f",setpts=PTS-STARTPTS+{ev['start']:.3f}/TB[b{idx}]"


def tc(t: float) -> str:
    fr = int(round(t * FPS))
    return f"{fr // (3600 * FPS):02d}:{fr // (60 * FPS) % 60:02d}:{fr // FPS % 60:02d}:{fr % FPS:02d}"


def to_edl(title: str, events: list) -> str:
    """CMX 3600 EDL of the cutaways at their timeline positions (import into Premiere, Resolve, Avid)."""
    out = [f"TITLE: {title}", "FCM: NON-DROP FRAME", ""]
    for k, e in enumerate(events, 1):
        reel = re.sub(r"[^A-Za-z0-9]", "", Path(e["clip"]).stem)[:8].upper() or "AX"
        src_in, rec_in = e.get("clip_start", 0.0), e["start"]
        out.append(f"{k:03d}  {reel:<8} V     C        {tc(src_in)} {tc(src_in + e['dur'])} "
                   f"{tc(rec_in)} {tc(rec_in + e['dur'])}")
        out.append(f"* FROM CLIP NAME: {Path(e['clip']).name}")
        out.append(f"* ON WORD: {e['on']}")
        out.append("")
    return "\n".join(out)


def loudnorm_args(src: Path, lufs: float) -> str:
    first = subprocess.run(["ffmpeg", "-hide_banner", "-i", str(src), "-vn", "-af",
                            f"loudnorm=I={lufs}:TP=-1.5:LRA=11:print_format=json", "-f", "null", "-"],
                           capture_output=True, text=True, check=True).stderr
    m = json.loads(first[first.rindex("{"):first.rindex("}") + 1])
    return (f"loudnorm=I={lufs}:TP=-1.5:LRA=11:measured_I={m['input_i']}:measured_TP={m['input_tp']}:"
            f"measured_LRA={m['input_lra']}:measured_thresh={m['input_thresh']}:offset={m['target_offset']}:"
            f"linear=true")


def cmd_render(a) -> int:
    if not a.input.exists():
        die(f"{a.input} does not exist.")
    plan = read_plan(a.plan)
    need_ffmpeg()
    plan["_clip_info"] = clip_infos(plan)
    events = resolve(plan)
    total = float(plan["duration"])
    print_report(events, total)
    good = [e for e in events if not e["problems"] and e.get("dur", 0) > 0.05]
    if any(e["problems"] for e in events) and not a.skip_bad:
        die("fix the cutaways marked ! (or pass --skip-bad to render without them).")
    if a.dry_run:
        print("\ndry run: nothing rendered.")
        return 0
    info = probe(a.input)
    narration = plan.get("mode") == "narration" or not info["has_video"]
    if narration:
        w, h = (1080, 1920) if a.vertical else tuple(plan.get("size") or [1920, 1080])
        if a.vertical:
            plan["size"] = [w, h]
    else:
        w, h = info["width"], info["height"]
    w, h = w - w % 2, h - h % 2
    a.out.mkdir(parents=True, exist_ok=True)
    stem = a.input.stem
    out_mp4 = a.out / f"{stem}.broll.mp4"

    cmd = ["ffmpeg", "-v", "error", "-y"]
    if narration:
        cmd += ["-f", "lavfi", "-i", f"color=c=black:s={w}x{h}:r={FPS}:d={total:.3f}", "-i", str(a.input)]
        audio_in, first_clip = 1, 2
    else:
        cmd += ["-i", str(a.input)]
        audio_in, first_clip = 0, 1
    if a.music:
        cmd += ["-stream_loop", "-1", "-i", str(a.music)]
        first_clip += 1
    parts = [f"[0:v]scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2,"
             f"setsar=1,fps={FPS},format=yuv420p[base]"]
    last = "base"
    for k, e in enumerate(good):
        idx = first_clip + k
        is_img = kind(e["clip"]) == "image"
        if is_img:
            cmd += ["-loop", "1", "-t", f"{e['dur']:.3f}", "-i", e["path"]]
        else:
            cmd += ["-ss", f"{e['clip_start']:.3f}", "-t", f"{e['dur']:.3f}", "-i", e["path"]]
        parts.append(clip_filter(idx, e, w, h, a.fade, is_img))
        nxt = f"v{k}"
        end = e["start"] + e["dur"]
        parts.append(f"[{last}][b{idx}]overlay=enable='between(t,{e['start']:.3f},{end:.3f})':eof_action=pass[{nxt}]")
        last = nxt
    # audio: the original speech (or narration) untouched in time; optional music bed ducked under it
    voice = f"[{audio_in}:a]aresample=48000"
    if a.music:
        mi = audio_in + 1 if narration else 1
        parts.append(f"{voice},asplit=2[sc][vo]")
        parts.append(f"[{mi}:a]aresample=48000,volume={a.music_volume}[mus]")
        parts.append("[mus][sc]sidechaincompress=threshold=0.03:ratio=8:attack=20:release=400[duck]")
        parts.append("[vo][duck]amix=inputs=2:duration=first:normalize=0[aout]")
    else:
        parts.append(f"{voice}[aout]")
    with tempfile.TemporaryDirectory() as td:
        script = Path(td) / "graph.txt"
        script.write_text(";\n".join(parts))
        tmp = Path(td) / "mix.mp4"
        cmd += ["-filter_complex_script", str(script), "-map", f"[{last}]", "-map", "[aout]",
                "-t", f"{total:.3f}", "-c:v", "libx264", "-preset", a.preset, "-crf", str(a.crf),
                "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart"]
        lufs = a.lufs if a.lufs is not None else (-14.0 if narration else None)
        if lufs is None:
            subprocess.run(cmd + [str(out_mp4)], check=True)
        else:
            subprocess.run(cmd + [str(tmp)], check=True)
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(tmp), "-c:v", "copy", "-af",
                            loudnorm_args(tmp, lufs) + ",aresample=48000", "-c:a", "aac", "-b:a", "192k",
                            "-movflags", "+faststart", str(out_mp4)], check=True)
    edl = a.out / f"{stem}.broll.edl"
    edl.write_text(to_edl(f"{stem} B-roll", good))
    manifest = {"video": str(out_mp4), "edl": str(edl), "size": [w, h], "duration": total,
                "mode": "narration" if narration else "talking-head",
                "coverage": round(coverage(good, total), 3),
                "cutaways": [{k: e[k] for k in ("n", "start", "dur", "on", "clip", "warnings")} for e in good],
                "skipped": [{"n": e["n"], "on": e["on"], "problems": e["problems"]} for e in events if e["problems"]]}
    (a.out / f"{stem}.broll.manifest.json").write_text(json.dumps(manifest, indent=2))
    print(json.dumps({"video": str(out_mp4), "edl": str(edl), "cutaways": len(good),
                      "coverage": f"{manifest['coverage'] * 100:.0f}%"}, indent=2))
    return 0


# -- prep / check --------------------------------------------------------------
def library(folder: Path | None) -> list:
    if not folder:
        return []
    if not folder.is_dir():
        die(f"--library {folder} is not a folder.")
    out = []
    for p in sorted(folder.rglob("*")):
        k = kind(p.name)
        if k == "other" or not p.is_file():
            continue
        item = {"file": str(p), "kind": k}
        if k == "video" and shutil.which("ffprobe"):
            try:
                item["seconds"] = probe(p)["seconds"]
            except subprocess.CalledProcessError:
                continue
        out.append(item)
    return out


INSTRUCTIONS = (
    "Add 'cutaways': one object per B-roll shot, e.g. {\"line\": 3, \"on\": \"espresso\", \"clip\": "
    "\"broll/espresso.mp4\", \"dur\": 2.5}. 'on' is the spoken word or phrase the cut lands on (it must appear "
    "in that line's words); 'clip' is a file from 'library' or 'pexels:<search words>'; 'dur' is optional (default: "
    "until the line ends, 1.2-4 s); 'clip_start' picks the in-point inside a video clip. Show what is being said "
    "(concrete nouns, actions, numbers, places), not the speaker's opinions. Talking head: cover 20-40% of the "
    "runtime, never the first 2 s, leave at least 1 s of speaker between shots. Faceless narration: one shot every "
    "2-4 s, each runs until the next. Then run: broll.py check <this file>")


def cmd_prep(a) -> int:
    if a.script:
        if not a.script.exists():
            die(f"{a.script} does not exist.")
        src = a.input or a.script.with_suffix(".narration.wav")
        voice_script(a.script, src, a.voice, a.ref_url, a.ref_text, a.model)
        mode = "narration"
    else:
        if not a.input or not a.input.exists():
            die("give a video (or audio) file, or --script script.txt for a faceless voiceover video.")
        src, mode = a.input, None
    try:
        data = json.loads(a.transcript.read_text()) if a.transcript else transcribe(src, a.force)
    except MirageaError as exc:
        die(str(exc))
    if not data.get("segments"):
        die("no speech found.")
    need_ffmpeg()
    info = probe(src)
    mode = mode or ("talking-head" if info["has_video"] else "narration")
    lines = group_lines(transcript_words(data))
    size = [info["width"], info["height"]] if info["has_video"] else ([1080, 1920] if a.vertical else [1920, 1080])
    out = a.out or src.with_name(f"{src.stem}.broll.json")
    doc = {"source": os.path.relpath(src.resolve(), out.resolve().parent), "mode": mode,
           "duration": info["seconds"], "size": size, "rules": DEFAULT_RULES,
           "instructions": INSTRUCTIONS,
           "library": [{**it, "file": os.path.relpath(Path(it["file"]).resolve(), out.resolve().parent)}
                       for it in library(a.library)],
           "lines": lines, "cutaways": []}
    out.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({"plan": str(out), "source": str(src), "mode": mode, "lines": len(lines),
                      "duration": info["seconds"], "library_clips": len(doc["library"])}, indent=2))
    return 0


def cmd_check(a) -> int:
    plan = read_plan(a.plan)
    plan["_clip_info"] = clip_infos(plan)
    events = resolve(plan)
    if not events:
        print("no cutaways yet: add them to the plan's 'cutaways' list.")
        return 1
    print_report(events, float(plan["duration"]))
    cov = coverage(events, float(plan["duration"]))
    if plan.get("mode") != "narration" and cov > 0.6:
        print("~ more than 60% B-roll: viewers lose the speaker; consider dropping weaker shots.")
    bad = [e for e in events if e["problems"]]
    if bad:
        print("\nFix the cutaways marked ! then re-run check.")
    return 1 if bad else 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("prep", help="transcribe (or voice a script) and write <name>.broll.json")
    p.add_argument("input", type=Path, nargs="?", help="talking-head video or voiceover audio")
    p.add_argument("--script", type=Path, help="faceless mode: voice this script in your Miragea voice first")
    p.add_argument("--library", type=Path, help="folder of your own B-roll clips and images")
    p.add_argument("--vertical", action="store_true", help="faceless mode: 1080x1920 (Shorts/TikTok/Reels)")
    p.add_argument("--out", type=Path)
    p.add_argument("--transcript", type=Path, help="use this transcript JSON instead of transcribing")
    p.add_argument("--force", action="store_true", help="re-transcribe even if cached")
    p.add_argument("--voice", default=os.getenv("MIRAGEA_VOICE_ID"), help="Miragea voice id (your saved voice)")
    p.add_argument("--ref-url", default=os.getenv("MIRAGEA_REF_URL"), help="public URL of a clip of your voice")
    p.add_argument("--ref-text", default=os.getenv("MIRAGEA_REF_TEXT"), help="exact words spoken in that clip")
    p.add_argument("--model", default="expressive", choices=["expressive", "standard"])
    c = sub.add_parser("check", help="free: resolve every cutaway to its word and flag problems")
    c.add_argument("plan", type=Path)
    f = sub.add_parser("fetch", help="download 'pexels:<query>' clips (free PEXELS_API_KEY)")
    f.add_argument("plan", type=Path)
    r = sub.add_parser("render", help="cut the B-roll in on its words and export MP4 + EDL")
    r.add_argument("input", type=Path, help="the same video/audio the plan was made from")
    r.add_argument("plan", type=Path)
    r.add_argument("-o", "--out", type=Path, default=Path("broll_out"))
    r.add_argument("--fade", type=float, default=0.0, help="soft in/out in seconds (default 0 = hard cut on the word)")
    r.add_argument("--music", type=Path, help="background music, ducked under the speech")
    r.add_argument("--music-volume", type=float, default=0.25)
    r.add_argument("--vertical", action="store_true", help="faceless mode: 1080x1920")
    r.add_argument("--lufs", type=float, default=None, help="loudness target (default: -14 faceless, untouched otherwise)")
    r.add_argument("--crf", type=int, default=18)
    r.add_argument("--preset", default="medium")
    r.add_argument("--skip-bad", action="store_true", help="render without the cutaways that have problems")
    r.add_argument("--dry-run", action="store_true", help="resolve and report only")
    a = ap.parse_args(argv)
    return {"prep": cmd_prep, "check": cmd_check, "fetch": cmd_fetch, "render": cmd_render}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())

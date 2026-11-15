#!/usr/bin/env python3
"""AI video dubbing in your own cloned voice: translate a video's speech and re-voice it, in sync.

    python3 dub.py prep   talk.mp4 --to es               # transcript -> talk.es.dub.json (lines + time budgets)
    #   ... the agent fills each line's "text" with the translation ...
    python3 dub.py check  talk.es.dub.json               # free: flags lines too long for their slot
    python3 dub.py render talk.mp4 talk.es.dub.json      # -> dub_out/talk.es.mp4 + .srt + YouTube audio track

The agent (Claude Code, Codex, Cursor...) does the translation itself, so no extra LLM or
translation key is needed. Each line is voiced in the creator's own Miragea voice, starts on the
original line, is sped up gently (max 1.2x) when it runs long, and keeps the original music and
ambience in the pauses. Speech recognition and voice: Miragea (https://miragea.ai/v1, env
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
import wave
from array import array
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cues import char_times  # noqa: E402
from miragea_client import Client, MirageaError  # noqa: E402

SR = 24000  # internal sample rate of the voice track (mono, 16-bit)

# Natural speaking rate in characters per second (spaces included for spaced scripts).
RATES = {"en": 14.5, "es": 14.0, "pt": 14.0, "fr": 14.0, "it": 14.0, "de": 14.0, "nl": 14.0, "pl": 13.5,
         "ru": 13.5, "tr": 14.0, "id": 15.0, "vi": 13.0, "hi": 13.0, "ar": 12.5,
         "ja": 7.5, "zh": 4.8, "ko": 6.5}
DEFAULT_RATE = 14.0
CJK = {"ja", "zh", "ko"}
ISO3 = {"en": "eng", "es": "spa", "pt": "por", "fr": "fra", "it": "ita", "de": "deu", "nl": "nld", "pl": "pol",
        "ru": "rus", "tr": "tur", "id": "ind", "vi": "vie", "hi": "hin", "ar": "ara", "ja": "jpn", "zh": "zho",
        "ko": "kor"}
NAMES = {"english": "en", "spanish": "es", "portuguese": "pt", "french": "fr", "italian": "it", "german": "de",
         "dutch": "nl", "polish": "pl", "russian": "ru", "turkish": "tr", "indonesian": "id",
         "vietnamese": "vi", "hindi": "hi", "arabic": "ar", "japanese": "ja", "chinese": "zh", "mandarin": "zh",
         "korean": "ko"}


def die(msg: str, code: int = 1) -> None:
    print(f"video-dubbing: error: {msg}", file=sys.stderr)
    sys.exit(code)


def need_ffmpeg() -> None:
    if not (shutil.which("ffmpeg") and shutil.which("ffprobe")):
        die("ffmpeg not found. Install it (macOS: brew install ffmpeg; Ubuntu: sudo apt install ffmpeg; "
            "Windows: winget install ffmpeg).")


def lang_code(lang: str | None) -> str:
    """'Spanish', 'es', 'es-MX', 'zh_CN' -> 'es' / 'zh'."""
    if not lang:
        return ""
    s = str(lang).strip().lower().replace("_", "-")
    return NAMES.get(s, s.split("-")[0])


def rate(lang: str) -> float:
    return RATES.get(lang_code(lang), DEFAULT_RATE)


def spoken_len(text: str, lang: str) -> int:
    """Characters that cost speaking time (collapses whitespace; CJK ignores spaces)."""
    t = re.sub(r"\s+", "" if lang_code(lang) in CJK else " ", text.strip())
    return len(t)


def estimate_seconds(text: str, lang: str) -> float:
    return round(spoken_len(text, lang) / rate(lang), 2)


# -- transcript ---------------------------------------------------------------
def sha(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()[:16]


def probe_seconds(path: Path) -> float:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                         capture_output=True, text=True, check=True).stdout.strip()
    return round(float(out), 3)


def has_audio(path: Path) -> bool:
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries", "stream=index",
                          "-of", "csv=p=0", str(path)], capture_output=True, text=True).stdout.strip()
    return bool(out)


def transcribe(src: Path, force: bool = False) -> dict:
    """Cached in <video>.transcript.json, the same file the video-captions and video-to-shorts skills use."""
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


SENT = re.compile(r"[^.!?…。！？]+(?:[.!?…。！？]+['\")\]」』]*|$)")
CLAUSE = re.compile(r"(?<=[,;:，；：、—])")


def _span_times(text: str, times: list, a: int, b: int, last: float):
    idx = [i for i in range(a, b) if text[i].isalnum() and times[i] is not None]
    if not idx:
        return None
    after = next((times[i] for i in range(idx[-1] + 1, len(text)) if text[i].isalnum() and times[i] is not None),
                 None)
    end = times[idx[-1]] + 0.06  # last character's time is ~its onset (or its segment's end)
    end = min(end, after) if after is not None else max(end, last)
    return times[idx[0]], max(end, times[idx[-1]])


def group_lines(transcript: dict, max_dur: float = 12.0) -> list:
    """Split speech into dub lines: whole sentences (clauses when a sentence runs past max_dur).

    Recognition segments are timed by audio and can break mid-word without punctuation, so every
    character of the punctuated full text is placed in time first, then the text is cut on sentence
    marks. Works for spaced and CJK scripts alike.
    """
    segs = transcript.get("segments") or []
    text = transcript.get("text") or ""
    if not text.strip():
        text = " ".join((s.get("text") or "").strip() for s in segs)
    if not segs or not text.strip():
        return []
    times = char_times(text, segs)
    last = float(segs[-1]["end"])
    lines = []
    for m in SENT.finditer(text):
        if not m.group().strip():
            continue
        tt = _span_times(text, times, m.start(), m.end(), last)
        if not tt:
            continue
        pieces = [(m.start(), m.end())]
        if tt[1] - tt[0] > max_dur:  # split long sentences on clause marks, greedily up to max_dur
            cuts = [m.start()] + [m.start() + c.start() for c in CLAUSE.finditer(m.group()) if c.start()] + [m.end()]
            pieces, a = [], cuts[0]
            for i in range(1, len(cuts)):
                t0 = _span_times(text, times, a, cuts[i], last)
                if t0 and t0[1] - t0[0] > max_dur and cuts[i - 1] > a:
                    pieces.append((a, cuts[i - 1]))
                    a = cuts[i - 1]
            pieces.append((a, m.end()))
        for a, b in pieces:
            t = _span_times(text, times, a, b, last)
            if t:
                lines.append({"start": t[0], "end": t[1], "source": text[a:b].strip()})
    merged = []  # fold tiny fragments ("Okay.") into the next line so each line has room to speak
    for ln in lines:
        if merged and merged[-1]["end"] - merged[-1]["start"] < 1.0 and ln["start"] - merged[-1]["end"] < 0.3:
            prev = merged.pop()
            sep = "" if re.search(r"[\u3000-\u9fff\uac00-\ud7af]$", prev["source"]) else " "
            ln = {"start": prev["start"], "end": ln["end"], "source": prev["source"] + sep + ln["source"]}
        merged.append(ln)
    return merged


def add_budgets(lines: list, duration: float, target: str) -> list:
    """Each line may use the time until the next line starts (its 'room')."""
    out = []
    for i, ln in enumerate(lines):
        nxt = lines[i + 1]["start"] if i + 1 < len(lines) else max(duration, ln["end"])
        room = round(max(nxt - ln["start"], ln["end"] - ln["start"], 0.3), 2)
        out.append({"id": i + 1, "start": round(ln["start"], 2), "end": round(ln["end"], 2), "room": room,
                    "max_chars": int(room * rate(target)), "source": ln["source"], "text": ln.get("text", "")})
    return out


# -- checking -----------------------------------------------------------------
def assess(lines: list, target: str, max_speed: float = 1.2) -> list:
    """Free length check before any voice is generated. status: ok | tight | long | missing."""
    rows = []
    for ln in lines:
        text = (ln.get("text") or "").strip()
        room = float(ln["room"])
        if not text:
            rows.append({"id": ln["id"], "status": "missing", "est": 0.0, "room": room, "note": "no translation"})
            continue
        est = estimate_seconds(text, target)
        if est <= room:
            status, note = "ok", ""
        elif est <= room * max_speed:
            status, note = "tight", f"will play at ~{est / room:.2f}x"
        else:
            cut = 100 * (1 - room * max_speed / est)
            status, note = "long", f"shorten by ~{cut:.0f}% (to ~{int(room * max_speed * rate(target))} chars)"
        rows.append({"id": ln["id"], "status": status, "est": est, "room": room, "note": note})
    return rows


def read_dub(path: Path) -> dict:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        die(f"cannot read {path}: {exc}")
    lines = data.get("lines") if isinstance(data, dict) else None
    if not isinstance(lines, list) or not lines:
        die(f"{path} has no lines. Create it with: python3 dub.py prep VIDEO --to LANG")
    if not data.get("target_language"):
        die(f"{path} has no target_language (e.g. \"es\").")
    for i, ln in enumerate(lines, 1):
        for k in ("start", "room"):
            if not isinstance(ln.get(k), (int, float)):
                die(f"line {i} in {path} needs a numeric {k!r}.")
        ln.setdefault("id", i)
    return data


def print_table(rows: list) -> None:
    for r in rows:
        mark = {"ok": " ", "tight": "~", "long": "!", "missing": "?"}[r["status"]]
        print(f"{mark} line {r['id']:>3}  est {r['est']:>5.1f}s / room {r['room']:>5.1f}s  {r['status']:<7} {r['note']}")
    n = {s: sum(r["status"] == s for r in rows) for s in ("ok", "tight", "long", "missing")}
    print(f"\n{n['ok']} ok, {n['tight']} tight (gentle speed-up), {n['long']} too long, {n['missing']} untranslated")


# -- timing -------------------------------------------------------------------
def place(lines: list, durations: dict, total: float, max_speed: float = 1.2, gap: float = 0.05) -> list:
    """Decide where each voiced line plays and how fast.

    A line starts on its original start (or right after the previous line if that ran over), gets
    sped up to fit before the next line, never past max_speed. Any remainder pushes the next line a
    little later; that drift is reported and absorbed by the next pause.
    """
    out, cursor = [], 0.0
    for i, ln in enumerate(lines):
        d = float(durations[ln["id"]])
        orig = float(ln["start"])
        nxt = float(lines[i + 1]["start"]) if i + 1 < len(lines) else max(total, orig + d)
        start = max(orig, cursor)
        room = max(nxt - start - gap, 0.2)
        speed = 1.0 if d <= room else min(d / room, max_speed)
        played = d / speed
        end = start + played
        out.append({"id": ln["id"], "start": round(start, 3), "end": round(end, 3), "speed": round(speed, 3),
                    "voiced": round(d, 3), "drift": round(start - orig, 3),
                    "overflow": round(max(0.0, end - (nxt - gap)), 3)})
        cursor = end + gap
    return out


def duck_expr(spans: list, under: float, pad_in: float = 0.08, pad_out: float = 0.15) -> str:
    """ffmpeg volume expression: original audio at `under` while the original speaker talks, 1 elsewhere."""
    if not spans:
        return "1"
    parts = "+".join(f"between(t\\,{max(0.0, a - pad_in):.2f}\\,{b + pad_out:.2f})" for a, b in spans)
    return f"if(gt({parts}\\,0)\\,{under:g}\\,1)"


# -- captions -----------------------------------------------------------------
def _chunks(text: str, limit: int, cjk: bool) -> list:
    text = text.strip()
    if len(text) <= limit:
        return [text]
    parts = re.split(r"(?<=[,;:.!?，。！？、；：])\s*", text)
    out, cur = [], ""
    for p in [p for p in parts if p]:
        cand = (cur + p) if cjk else (cur + " " + p).strip()
        if cur and len(cand) > limit:
            out.append(cur)
            cur = p
        else:
            cur = cand
    if cur:
        out.append(cur)
    final = []
    for c in out:  # hard split anything still too long
        while len(c) > limit:
            cut = limit if cjk else (c.rfind(" ", 0, limit) if c.rfind(" ", 0, limit) > limit // 2 else limit)
            final.append(c[:cut].strip())
            c = c[cut:].strip()
        if c:
            final.append(c)
    return final


def _wrap2(text: str, width: int, cjk: bool) -> str:
    if len(text) <= width:
        return text
    if cjk:
        half = (len(text) + 1) // 2
        return text[:half] + "\n" + text[half:]
    ws = text.split()
    best, cost = text, 1e9
    for k in range(1, len(ws)):
        a, b = " ".join(ws[:k]), " ".join(ws[k:])
        c = abs(len(a) - len(b)) + (100 if max(len(a), len(b)) > width else 0)
        if c < cost:
            best, cost = a + "\n" + b, c
    return best


def caption_cues(lines: list, placed: list, target: str) -> list:
    cjk = lang_code(target) in CJK
    width = 16 if cjk else 42
    cues = []
    by_id = {p["id"]: p for p in placed}
    for ln in lines:
        p = by_id.get(ln["id"])
        text = (ln.get("text") or "").strip()
        if not p or not text:
            continue
        chunks = []
        todo = _chunks(text, width * 2, cjk)
        while todo:  # a chunk whose best 2-line wrap still overflows is halved at a word boundary
            c = todo.pop(0)
            if any(len(row) > width for row in _wrap2(c, width, cjk).split("\n")) and len(c) > 8:
                mid = len(c) // 2
                cut = mid if cjk else min((i for i, ch in enumerate(c) if ch == " "), key=lambda i: abs(i - mid),
                                          default=mid)
                todo[:0] = [c[:cut].strip(), c[cut:].strip()]
            else:
                chunks.append(c)
        total = sum(len(c) for c in chunks) or 1
        t = p["start"]
        span = max(p["end"] - p["start"], 0.6)
        for c in chunks:
            d = span * len(c) / total
            cues.append({"start": t, "end": t + d, "text": _wrap2(c, width, cjk)})
            t += d
    return cues


def _ts(t: float) -> str:
    ms = int(round(max(t, 0) * 1000))
    return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"


def to_srt(cues: list) -> str:
    return "\n".join(f"{i}\n{_ts(c['start'])} --> {_ts(c['end'])}\n{c['text']}\n" for i, c in enumerate(cues, 1))


# -- audio --------------------------------------------------------------------
TRIM = ("silenceremove=start_periods=1:start_threshold=-45dB:start_silence=0.05,areverse,"
        "silenceremove=start_periods=1:start_threshold=-45dB:start_silence=0.08,areverse")


def voice_key(text: str, voice: str, ref_url: str, model: str) -> str:
    return hashlib.sha256(f"{text}\x00{voice}\x00{ref_url}\x00{model}".encode()).hexdigest()[:20]


def pcm(path: Path, speed: float = 1.0) -> bytes:
    """Decode to mono 16-bit SR Hz, with optional tempo change (pitch kept)."""
    af = f"atempo={speed:.4f}" if abs(speed - 1.0) > 1e-3 else "anull"
    return subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-af", af, "-ac", "1", "-ar", str(SR),
                           "-f", "s16le", "-"], capture_output=True, check=True).stdout


def build_track(placed: list, files: dict, total: float, out: Path) -> Path:
    n = int((total + 0.5) * SR)
    track = array("h", bytes(2 * n))
    for p in placed:
        data = array("h")
        data.frombytes(pcm(files[p["id"]], p["speed"]))
        at = int(p["start"] * SR)
        if at + len(data) > len(track):
            track.extend(array("h", bytes(2 * (at + len(data) - len(track)))))
        track[at:at + len(data)] = data
    with wave.open(str(out), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(track.tobytes())
    return out


def loudnorm(src: Path, dst: Path, lufs: float, seconds: float) -> None:
    """Two-pass EBU R128 normalisation (linear), so the result really lands on the target."""
    first = subprocess.run(["ffmpeg", "-hide_banner", "-i", str(src), "-af",
                            f"loudnorm=I={lufs}:TP=-1.5:LRA=11:print_format=json", "-f", "null", "-"],
                           capture_output=True, text=True, check=True).stderr
    m = json.loads(first[first.rindex("{"):first.rindex("}") + 1])
    af = (f"loudnorm=I={lufs}:TP=-1.5:LRA=11:measured_I={m['input_i']}:measured_TP={m['input_tp']}:"
          f"measured_LRA={m['input_lra']}:measured_thresh={m['input_thresh']}:offset={m['target_offset']}:"
          f"linear=true,aresample=48000")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(src), "-af", af, "-t", f"{seconds:.3f}", "-ac", "2",
                    str(dst)], check=True)


# -- commands -----------------------------------------------------------------
def cmd_prep(a) -> int:
    if not a.input.exists():
        die(f"{a.input} does not exist.")
    target = lang_code(a.to)
    if not target:
        die("--to needs a target language code, e.g. --to es")
    try:
        data = json.loads(a.transcript.read_text()) if a.transcript else transcribe(a.input, a.force)
    except MirageaError as exc:
        die(str(exc))
    segs = data.get("segments") or []
    if not segs:
        die("no speech found in this video.")
    need_ffmpeg()
    total = probe_seconds(a.input)
    lines = add_budgets(group_lines(data, max_dur=a.max_line), total, target)
    out = a.out or a.input.with_name(f"{a.input.stem}.{target}.dub.json")
    doc = {"video": a.input.name, "source_language": lang_code(data.get("language")) or data.get("language"),
           "target_language": target, "duration": total,
           "instructions": ("Fill every 'text' with a natural spoken translation of 'source' into the target "
                            "language. Stay under 'max_chars' so it fits its time slot; keep names, brands and "
                            "numbers; do not add content. Then run: dub.py check <this file>"),
           "lines": lines}
    out.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"dub_file": str(out), "lines": len(lines), "source_language": doc["source_language"],
                      "target_language": target, "duration": total}, indent=2))
    return 0


def cmd_check(a) -> int:
    doc = read_dub(a.dub)
    rows = assess(doc["lines"], doc["target_language"], a.max_speed)
    print_table(rows)
    bad = [r for r in rows if r["status"] in ("long", "missing")]
    if bad:
        print("\nFix the lines marked ! or ? (shorter wording keeps the dub in sync), then re-run check.")
    return 1 if bad else 0


def cmd_render(a) -> int:
    if not a.input.exists():
        die(f"{a.input} does not exist.")
    doc = read_dub(a.dub)
    target = doc["target_language"]
    lines = [ln for ln in doc["lines"] if (ln.get("text") or "").strip()]
    rows = assess(doc["lines"], target, a.max_speed)
    print_table(rows)
    if any(r["status"] == "missing" for r in rows) and not a.allow_missing:
        die("some lines have no translation. Fill them in (or pass --allow-missing to leave them silent).")
    if a.dry_run:
        print("\ndry run: nothing generated, no API calls. Remove --dry-run to render.")
        return 0
    if not (a.voice or a.ref_url):
        die("no voice set. Pass --voice ID (or MIRAGEA_VOICE_ID), or --ref-url/--ref-text for a clip of your "
            "own voice (MIRAGEA_REF_URL / MIRAGEA_REF_TEXT). Only clone a voice you own or may use.")
    need_ffmpeg()
    a.out.mkdir(parents=True, exist_ok=True)
    cache = a.dub.resolve().parent / ".dub-cache"  # shared by every render of this dub file: re-runs are free
    cache.mkdir(exist_ok=True)
    total = probe_seconds(a.input)
    client, files, durs, billed = None, {}, {}, 0
    for ln in lines:
        text = ln["text"].strip()
        f = cache / f"{voice_key(text, a.voice or '', a.ref_url or '', a.model)}.wav"
        if not f.exists():
            client = client or Client()
            raw = cache / f".{f.stem}.raw.wav"
            try:
                client.speak(text, raw, actor_id=a.voice, reference_audio_url=a.ref_url,
                             reference_text=a.ref_text, model=a.model)
            except MirageaError as exc:
                die(f"[line {ln['id']}] {exc}")
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(raw), "-af", TRIM, "-ac", "1", "-ar", str(SR),
                           str(f)], check=True)
            raw.unlink(missing_ok=True)
            billed += 1
            print(f"voiced line {ln['id']}", file=sys.stderr)
        files[ln["id"]] = f
        with wave.open(str(f)) as w:
            durs[ln["id"]] = w.getnframes() / w.getframerate()
    placed = place(lines, durs, total, a.max_speed)
    stem = f"{a.input.stem}.{target}"
    voice_wav = build_track(placed, files, total, a.out / f"{stem}.voice.wav")
    srt = a.out / f"{stem}.srt"
    srt.write_text(to_srt(caption_cues(lines, placed, target)), encoding="utf-8")

    # Mix: voice + background (a clean bed file, or the original audio ducked while the speaker talks).
    src_spans = [(float(ln["start"]), float(ln.get("end", ln["start"]))) for ln in doc["lines"]]
    mix_wav = a.out / f"{stem}.dub.wav"
    pre = a.out / f".{stem}.premix.wav"
    cmd = ["ffmpeg", "-v", "error", "-y", "-i", str(voice_wav)]
    if a.bed:
        cmd += ["-i", str(a.bed)]
        fc = (f"[1:a]aresample=48000,volume={a.bed_volume:g}[b];[0:a]aresample=48000[v];"
              f"[v][b]amix=inputs=2:normalize=0:duration=first[m]")
    elif has_audio(a.input) and a.under > 0:
        cmd += ["-i", str(a.input)]
        fc = (f"[1:a]aresample=48000,volume='{duck_expr(src_spans, a.under)}':eval=frame[b];"
              f"[0:a]aresample=48000[v];[v][b]amix=inputs=2:normalize=0:duration=first[m]")
    else:
        fc = "[0:a]aresample=48000[m]"
    cmd += ["-filter_complex", fc, "-map", "[m]", "-t", f"{total:.3f}", "-ac", "2", str(pre)]
    subprocess.run(cmd, check=True)
    loudnorm(pre, mix_wav, a.lufs, total)
    pre.unlink(missing_ok=True)

    # Mux: keep the picture untouched (stream copy) unless captions are burned in.
    out_mp4 = a.out / f"{stem}.mp4"
    lang3 = ISO3.get(target, "und")
    cmd = ["ffmpeg", "-v", "error", "-y", "-i", str(a.input.resolve()), "-i", str(mix_wav.resolve())]
    if a.burn:
        cmd += ["-vf", f"subtitles={srt.name}", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
                "-pix_fmt", "yuv420p"]
    else:
        cmd += ["-c:v", "copy"]
    cmd += ["-map", "0:v:0", "-map", "1:a:0"]
    if a.keep_original and has_audio(a.input):
        src3 = ISO3.get(lang_code(doc.get("source_language")), "und")
        cmd += ["-map", "0:a:0", "-metadata:s:a:1", f"language={src3}", "-disposition:a:1", "0"]
    cmd += ["-c:a", "aac", "-b:a", "192k", "-metadata:s:a:0", f"language={lang3}", "-disposition:a:0", "default",
            "-shortest", "-movflags", "+faststart", str(out_mp4.resolve())]
    subprocess.run(cmd, check=True, cwd=a.out)

    over = [p for p in placed if p["overflow"] > 0.05]
    manifest = {"video": a.input.name, "target_language": target, "duration": total, "lufs": a.lufs,
                "max_speed": a.max_speed, "lines_voiced": len(placed), "lines_billed_this_run": billed,
                "max_drift_seconds": max((p["drift"] for p in placed), default=0.0),
                "files": {"video": out_mp4.name, "audio_track": mix_wav.name, "voice_only": voice_wav.name,
                          "captions": srt.name},
                "lines": placed}
    (a.out / f"{stem}.manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nwrote {out_mp4}\n      {mix_wav} (upload as a YouTube audio track)\n      {srt}")
    print(f"voiced {len(placed)} lines ({billed} new, {len(placed) - billed} from cache); "
          f"max drift {manifest['max_drift_seconds']:.2f}s")
    if over:
        ids = ", ".join(str(p["id"]) for p in over)
        print(f"lines still running over their slot even at {a.max_speed}x: {ids}. Shorten them in the dub "
              "file and re-run (unchanged lines are free).")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("prep", help="transcribe and write <video>.<lang>.dub.json with per-line time budgets")
    p.add_argument("input", type=Path)
    p.add_argument("--to", required=True, help="target language code: es, pt, fr, de, it, ja, ko, zh, hi, en ...")
    p.add_argument("--max-line", type=float, default=12.0, help="longest dub line in seconds (default 12)")
    p.add_argument("--out", type=Path, help="dub file path (default <video>.<lang>.dub.json)")
    p.add_argument("--transcript", type=Path, help="use this transcript JSON instead of transcribing")
    p.add_argument("--force", action="store_true", help="re-transcribe even if cached")
    c = sub.add_parser("check", help="free length check of the translations against their time slots")
    c.add_argument("dub", type=Path)
    c.add_argument("--max-speed", type=float, default=1.2)
    r = sub.add_parser("render", help="voice every line, sync it, mix and export the dubbed video")
    r.add_argument("input", type=Path)
    r.add_argument("dub", type=Path)
    r.add_argument("-o", "--out", type=Path, default=Path("dub_out"))
    r.add_argument("--voice", default=os.getenv("MIRAGEA_VOICE_ID"), help="Miragea voice id (your saved voice)")
    r.add_argument("--ref-url", default=os.getenv("MIRAGEA_REF_URL"), help="public URL of a clip of your voice")
    r.add_argument("--ref-text", default=os.getenv("MIRAGEA_REF_TEXT"), help="exact words spoken in that clip")
    r.add_argument("--model", default="expressive", choices=["expressive", "standard"])
    r.add_argument("--max-speed", type=float, default=1.2, help="fastest allowed speed-up (default 1.2)")
    r.add_argument("--under", type=float, default=0.08,
                   help="original audio volume while the original speaker talks (default 0.08; 0 = mute)")
    r.add_argument("--bed", type=Path, help="music/ambience stem without vocals to use instead of the original audio")
    r.add_argument("--bed-volume", type=float, default=1.0)
    r.add_argument("--burn", action="store_true", help="burn the translated captions into the picture")
    r.add_argument("--keep-original", action="store_true", help="add the original audio as a second track")
    r.add_argument("--lufs", type=float, default=-14.0, help="loudness target (default -14)")
    r.add_argument("--allow-missing", action="store_true", help="leave untranslated lines silent")
    r.add_argument("--dry-run", action="store_true", help="length check only; no API calls")
    a = ap.parse_args(argv)
    return {"prep": cmd_prep, "check": cmd_check, "render": cmd_render}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""UGC-style video ads with AI voiceover in your own cloned voice: hooks x bodies -> ready-to-upload MP4s.

    python3 ads.py check ad.json                       # free: lint lengths, hooks, claims, media, CTA
    python3 ads.py render ad.json --dry-run            # free: the variant matrix with estimated lengths
    python3 ads.py render ad.json -o ads_out           # voice, caption and render every variant
    python3 ads.py render ad.json --ratios 9:16,4:5,1:1 --only price-demo --music bed.mp3

ad.json holds the brand, 2-5 hooks, one or more bodies (lines with an image/clip each), a spoken CTA and
an end card. Every hook is rendered with every body, so one run gives a creative-testing matrix for TikTok,
Instagram Reels, YouTube Shorts and Meta ads. Lines are voiced with Miragea (https://miragea.ai/v1) in the
creator's saved or cloned voice, cached per line (a new hook re-bills only the hook), edge silence is
trimmed, captions are timed from Miragea speech recognition but keep your exact script spelling, text
stays inside the platform safe zones, loudness is -14 LUFS. Outputs per variant and ratio:
<brand>_<hook>-<body>_<9x16>.mp4, an SRT, and manifest.csv/json for Ads Manager naming.
Python 3.9+ stdlib + ffmpeg.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import wave
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cues import to_srt, words  # noqa: E402
from miragea_client import Client, MirageaError  # noqa: E402

FPS = 30
SR = 48000
WPS = 2.6  # spoken words per second for estimates (energetic UGC read)
IMG = {".jpg", ".jpeg", ".png", ".webp"}
VID = {".mp4", ".mov", ".m4v", ".webm", ".mkv"}
GRADIENTS = [("0x0f172a", "0x7c3aed"), ("0x111827", "0x0ea5e9"), ("0x1f2937", "0xf97316"), ("0x022c22", "0x10b981")]

# Typical sweet spots for paid short-form video (advice, not platform rules).
PLATFORMS = {
    "tiktok": (9, 34, 60), "reels": (9, 30, 90), "shorts": (10, 45, 60), "meta": (6, 20, 60), "any": (6, 35, 60),
}

# Fractions of the frame. Captions and overlays avoid the top bar, the bottom caption/CTA area and the
# right-hand like/share rail that TikTok, Reels and Shorts draw over 9:16 video.
LAYOUTS = {
    "9:16": {"size": (1080, 1920), "overlay_y": 0.17, "caption_y": 0.60, "cx": 0.46, "card_y": 0.34},
    "4:5": {"size": (1080, 1350), "overlay_y": 0.09, "caption_y": 0.74, "cx": 0.50, "card_y": 0.30},
    "1:1": {"size": (1080, 1080), "overlay_y": 0.08, "caption_y": 0.76, "cx": 0.50, "card_y": 0.26},
    "16:9": {"size": (1920, 1080), "overlay_y": 0.08, "caption_y": 0.80, "cx": 0.50, "card_y": 0.26},
}

CLAIMS = [
    (r"\bguarantee(d|s)?\b", "a guarantee needs stated terms (\"30-day money-back\"); bare guarantees get ads rejected"),
    (r"\b(cures?|heals?|treats?|prevents?)\b", "health/medical claim: needs substantiation; most ad platforms restrict it"),
    (r"\b(lose|lost|drop|dropped)\s+\d+\s*(lbs?|pounds|kg|kilos)\b", "specific weight-loss result: restricted on Meta and TikTok"),
    (r"\b(make|made|earn|earned)\s+\$?\d[\d,]*k?\b", "income claim: needs typical-results disclosure (FTC); often rejected"),
    (r"(100\s?%|\brisk[- ]free\b|\bno risk\b)", "absolute claim: soften it or prove it"),
    (r"(#1\b|\bnumber one\b|\bbest\b.*\b(world|ever|market)\b)", "superlative: keep proof (ranking, source) ready"),
    (r"\bbefore and after\b", "before/after framing is restricted for health, beauty and weight products"),
    (r"\bclinically (proven|tested)\b", "clinical claim: keep the study ready; reviewers ask for it"),
    (r"\bfree\b", "\"free\": state the condition (with purchase, shipping, trial length) on screen"),
    (r"^\s*(are|do|is) you\b[^.?!]*\b(overweight|fat|depressed|anxious|in debt|broke|single|bald|diabetic|sick)\b",
     "asserts a personal attribute about the viewer (Meta policy); rephrase in first or third person"),
]


# ---------------------------------------------------------------- spec ----
def slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", str(s).lower()).strip("-") or "x"


def _line(d, where: str) -> dict:
    if isinstance(d, str):
        d = {"text": d}
    if not isinstance(d, dict) or not str(d.get("text", "")).strip():
        raise ValueError(f"{where}: every line needs a non-empty \"text\".")
    if len(d["text"]) > 400:
        raise ValueError(f"{where}: line is over 400 characters; split it (ads read in short beats).")
    return {"text": " ".join(str(d["text"]).split()), "media": d.get("media"), "overlay": d.get("overlay")}


def load_spec(data: dict) -> dict:
    """Validate and normalise an ad spec. Pure function (tested)."""
    if not isinstance(data, dict):
        raise ValueError("the ad file must be a JSON object.")
    hooks = data.get("hooks") or []
    if not hooks:
        raise ValueError("add at least one entry to \"hooks\" (2-5 is the point of this tool).")
    bodies = data.get("bodies") or ([{"id": "body", "lines": data["body"]}] if data.get("body") else [])
    if not bodies:
        raise ValueError("add a \"body\" (list of lines) or \"bodies\" (list of {id, lines}).")
    spec = {"brand": str(data.get("brand") or "ad"), "product": data.get("product", ""),
            "platform": str(data.get("platform", "any")).lower(), "label": data.get("label"),
            "music": data.get("music"), "speed": data.get("speed"), "hooks": [], "bodies": [],
            "cta": _line(data["cta"], "cta") if data.get("cta") else None, "end_card": data.get("end_card")}
    if spec["platform"] not in PLATFORMS:
        raise ValueError(f"platform must be one of {', '.join(PLATFORMS)}.")
    seen = set()
    for i, h in enumerate(hooks):
        ln = _line(h, f"hooks[{i}]")
        ln["id"] = slug(h.get("id") if isinstance(h, dict) and h.get("id") else chr(ord("a") + i))
        if ln["id"] in seen:
            raise ValueError(f"hooks[{i}]: duplicate id '{ln['id']}'.")
        seen.add(ln["id"])
        spec["hooks"].append(ln)
    seen = set()
    for i, b in enumerate(bodies):
        lines = b.get("lines") if isinstance(b, dict) else b
        if not lines:
            raise ValueError(f"bodies[{i}]: needs \"lines\".")
        bid = slug(b.get("id") if isinstance(b, dict) and b.get("id") else f"b{i + 1}")
        if bid in seen:
            raise ValueError(f"bodies[{i}]: duplicate id '{bid}'.")
        seen.add(bid)
        spec["bodies"].append({"id": bid, "lines": [_line(x, f"bodies[{i}].lines[{j}]") for j, x in enumerate(lines)]})
    ec = spec["end_card"]
    if ec is not None:
        if not isinstance(ec, dict):
            raise ValueError("end_card must be an object like {\"title\": ..., \"lines\": [...], \"button\": ...}.")
        ec.setdefault("title", spec["brand"])
        ec.setdefault("lines", [])
        ec["seconds"] = float(ec.get("seconds", 2.0))
    return spec


def variants(spec: dict, only: list[str] | None = None, limit: int | None = None) -> list[dict]:
    """Every hook x every body; each variant = hook line, body lines, CTA line."""
    out = []
    for h in spec["hooks"]:
        for b in spec["bodies"]:
            vid = f"{h['id']}-{b['id']}"
            if only and vid not in only and h["id"] not in only and b["id"] not in only:
                continue
            lines = [dict(h, role="hook")] + [dict(x, role="body") for x in b["lines"]]
            if spec["cta"]:
                lines.append(dict(spec["cta"], role="cta"))
            out.append({"id": vid, "hook": h["id"], "body": b["id"], "lines": lines})
    return out[:limit] if limit else out


def spoken_words(text: str) -> int:
    n = 0
    for w in text.split():
        digits = re.sub(r"\D", "", w)
        n += (min(len(digits), 3) if digits else 1) + (1 if "$" in w or "%" in w else 0)
    return n


def est_seconds(text: str, speed: float | None = None) -> float:
    return round(spoken_words(text) / (WPS * (speed or 1.0)) + 0.15, 2)


def lint_claims(text: str) -> list[str]:
    return [why for pat, why in CLAIMS if re.search(pat, text, re.I)]


def check(spec: dict, base: Path, hook_budget: float = 3.0) -> tuple[list[str], list[str]]:
    """Return (problems, advice). Problems block rendering; advice is worth reading."""
    problems, advice = [], []
    lo, sweet, hi = PLATFORMS[spec["platform"]]
    if len(spec["hooks"]) < 2:
        advice.append("only one hook: write 3-5 (question, bold claim, POV, price shock, demo-first) to test against each other")
    if not spec["cta"]:
        advice.append("no spoken CTA: add \"cta\" (what to tap and why now)")
    if spec["end_card"] is None:
        advice.append("no end card: add \"end_card\" with the brand, offer and button text")
    all_lines = spec["hooks"] + [x for b in spec["bodies"] for x in b["lines"]] + ([spec["cta"]] if spec["cta"] else [])
    for ln in all_lines:
        m = ln.get("media")
        if m and not m.startswith("#") and not (base / m).exists() and not Path(m).exists():
            problems.append(f"media not found: {m}")
        if ln.get("overlay") and len(ln["overlay"]) > 28:
            advice.append(f"overlay over 28 characters will be small on phones: \"{ln['overlay']}\"")
    for h in spec["hooks"]:
        s = est_seconds(h["text"], spec["speed"])
        if s > hook_budget:
            advice.append(f"hook '{h['id']}' reads ~{s:.1f}s (> {hook_budget:.0f}s): cut words so it lands before the swipe")
    for v in variants(spec):
        total = sum(est_seconds(x["text"], spec["speed"]) + 0.12 for x in v["lines"])
        total += spec["end_card"]["seconds"] if spec["end_card"] else 0
        if total > hi:
            problems.append(f"variant {v['id']} is ~{total:.0f}s; over {hi}s for {spec['platform']}. Shorten the body.")
        elif total > sweet:
            advice.append(f"variant {v['id']} is ~{total:.0f}s; {lo}-{sweet}s is the usual sweet spot for {spec['platform']} ads")
        elif total < lo:
            advice.append(f"variant {v['id']} is ~{total:.0f}s; under {lo}s rarely carries hook + proof + CTA")
    seen = set()
    for ln in all_lines:
        for why in lint_claims(ln["text"] + " " + (ln.get("overlay") or "")):
            key = (ln["text"], why)
            if key not in seen:
                seen.add(key)
                advice.append(f"claim check: \"{ln['text'][:60]}\" -> {why}")
    if any(re.search(r"\b(I|I've|I'm|my|me)\b", ln["text"]) for ln in all_lines) and not spec["label"]:
        advice.append("first-person testimonial lines: they must reflect a real experience (FTC endorsement guides); "
                      "if the voice is AI-generated or not the person's own, set \"label\" (e.g. \"AI voice\") and use "
                      "the platform's AI-content toggle")
    return problems, advice


# -------------------------------------------------------------- layout ----
def _ass_time(t: float) -> str:
    cs = int(round(max(t, 0) * 100))
    return f"{cs // 360000}:{cs // 6000 % 60:02d}:{cs // 100 % 60:02d}.{cs % 100:02d}"


def _esc(s: str) -> str:
    return s.replace("\\", "\\\\").replace("{", "(").replace("}", ")").replace("\n", "\\N")


def ass_doc(ratio: str, captions: list, overlays: list, card: dict | None, card_start: float, total: float,
            label: str | None = None, accent: str = "&H0000D7FF") -> str:
    """Build an ASS subtitle file: captions, top overlays, end card, optional AI label. Pure (tested)."""
    L = LAYOUTS[ratio]
    W, H = L["size"]
    u = min(W, H)
    styles = [
        ("Caption", "Arial", int(u * 0.078), "&H00FFFFFF", "&H00000000", 1, 6, 1, 5),
        ("Overlay", "Arial", int(u * 0.056), "&H00111111", "&H00FFFFFF", 3, 14, 0, 8),
        ("Title", "Arial", int(u * 0.11), "&H00FFFFFF", "&H00000000", 1, 3, 0, 5),
        ("Sub", "Arial", int(u * 0.052), "&H00FFFFFF", "&H00000000", 1, 2, 0, 5),
        ("Button", "Arial", int(u * 0.06), "&H00111111", accent, 3, 22, 0, 5),
        ("Label", "Arial", int(u * 0.028), "&H00FFFFFF", "&H80000000", 3, 6, 0, 7),
    ]
    head = (f"[Script Info]\nScriptType: v4.00+\nPlayResX: {W}\nPlayResY: {H}\nWrapStyle: 0\nScaledBorderAndShadow: yes\n\n"
            "[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, "
            "Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, "
            "MarginL, MarginR, MarginV, Encoding\n")
    for name, font, size, prim, outc, bs, outl, shad, al in styles:
        head += (f"Style: {name},{font},{size},{prim},&H000000FF,{outc},&H80000000,-1,0,0,0,100,100,0,0,{bs},{outl},"
                 f"{shad},{al},{int(W * 0.08)},{int(W * 0.16 if ratio == '9:16' else W * 0.08)},0,1\n")
    ev = ["", "[Events]", "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"]

    def add(style, a, b, x, y, text, layer=1):
        ev.append(f"Dialogue: {layer},{_ass_time(a)},{_ass_time(b)},{style},,0,0,0,,{{\\pos({int(x)},{int(y)})}}{_esc(text)}")

    cx = W * L["cx"]
    for c in captions:
        if c["start"] < card_start:
            add("Caption", c["start"], min(c["end"], card_start), cx, H * L["caption_y"], c["text"], 2)
    for o in overlays:
        add("Overlay", o["start"], o["end"], cx, H * L["overlay_y"], o["text"])
    if card:
        y = H * L["card_y"]
        add("Title", card_start, total, W / 2, y, card.get("title", ""))
        y += u * 0.13
        for ln in card.get("lines", [])[:3]:
            add("Sub", card_start, total, W / 2, y, ln)
            y += u * 0.075
        if card.get("button"):
            add("Button", card_start + 0.25, total, W / 2, y + u * 0.07, f"  {card['button']}  ")
    if label:
        add("Label", 0, total, W * 0.05, H * (0.13 if ratio == "9:16" else 0.03), label, 3)
    return head + "\n".join(ev) + "\n"


def timed_words(script_text: str, transcript: dict | None, dur: float) -> list:
    """Script words (exact spelling) placed on the speech-recognition timing; even spread as fallback."""
    ws = []
    if transcript and transcript.get("segments"):
        ws = words({"text": script_text, "segments": transcript["segments"]})
    n = len(script_text.split())
    if len(ws) < max(1, n // 2):
        toks = script_text.split()
        total_chars = sum(len(t) + 1 for t in toks) or 1
        t, ws = 0.0, []
        for tok in toks:
            d = dur * (len(tok) + 1) / total_chars
            ws.append({"text": tok, "start": t, "end": t + d})
            t += d
    return ws


def ad_cues(ws: list, upper: bool = True, max_words: int = 3, max_chars: int = 18) -> list:
    """1-3 word pop captions that also break after commas and sentence ends. Pure (tested)."""
    cues, cur = [], []

    def flush():
        if cur:
            t = " ".join(w["text"] for w in cur).strip(",;:")
            cues.append({"start": cur[0]["start"], "end": cur[-1]["end"], "text": t.upper() if upper else t})
            cur.clear()

    for w in ws:
        if cur and (len(cur) >= max_words or len(" ".join(x["text"] for x in cur + [w])) > max_chars
                    or w["start"] - cur[-1]["end"] > 0.5):
            flush()
        cur.append(w)
        if re.search(r"[.,!?;:…]['\")\]]*$", w["text"]):
            flush()
    flush()
    for a, b in zip(cues, cues[1:] + [None]):
        a["end"] = max(a["end"], min(a["start"] + 0.35, b["start"] - 0.03 if b else a["start"] + 0.35))
        if b:
            a["end"] = min(max(a["end"], b["start"] - 0.03), b["start"])
    return cues


def frame_splits(starts: list[float], total: float) -> list[int]:
    """Frame counts per scene from cumulative times, so rounding never drifts. Pure (tested)."""
    marks = [round(s * FPS) for s in starts] + [round(total * FPS)]
    return [max(1, b - a) for a, b in zip(marks, marks[1:])]


# -------------------------------------------------------------- render ----
def run(cmd: list, what: str, cwd=None) -> None:
    r = subprocess.run([str(c) for c in cmd], capture_output=True, text=True, cwd=cwd)
    if r.returncode:
        sys.exit(f"ads: error: ffmpeg failed while {what}:\n{r.stderr.strip()[-900:]}\n"
                 "Voice lines and transcripts are cached; fix the issue and re-run (no extra cost).")


def wav_seconds(p: Path) -> float:
    with wave.open(str(p)) as w:
        return w.getnframes() / w.getframerate()


def scene_clip(media: Path | None, frames: int, idx: int, out: Path, W: int, H: int, dim: bool = False) -> None:
    base = ["ffmpeg", "-v", "error", "-y"]
    dur = frames / FPS
    if media is None:
        c0, c1 = GRADIENTS[idx % len(GRADIENTS)]
        cmd = base + ["-f", "lavfi", "-i", f"gradients=s={W}x{H}:c0={c0}:c1={c1}:speed=0.01:duration={dur + 1:.3f}:rate={FPS}"]
        vf = "format=yuv420p"
    elif media.suffix.lower() in IMG:
        zin = "min(zoom+0.0009,1.18)" if idx % 2 == 0 else "if(eq(on,0),1.18,max(zoom-0.0009,1.0))"
        cmd = base + ["-loop", "1", "-i", str(media)]
        vf = (f"scale={W * 2}:{H * 2}:force_original_aspect_ratio=increase,crop={W * 2}:{H * 2},"
              f"zoompan=z='{zin}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={frames}:s={W}x{H}:fps={FPS},format=yuv420p")
    else:
        cmd = base + ["-stream_loop", "-1", "-i", str(media)]
        vf = f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},fps={FPS},format=yuv420p"
    if dim:
        vf += ",gblur=sigma=18,eq=brightness=-0.22:saturation=0.8"
    run(cmd + ["-vf", vf, "-frames:v", frames, "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
               "-r", FPS, out], f"preparing scene {idx + 1}")


def resolve_media(m: str | None, base: Path) -> Path | None:
    if not m or m.startswith("#"):
        return None
    p = Path(m).expanduser()
    return p if p.is_absolute() else (base / p if (base / p).exists() else p)


class Voicer:
    """Voices and times one line at a time; everything cached per (text, voice, model, speed)."""

    def __init__(self, cache: Path, voice: dict, model: str, speed, captions: bool):
        self.cache, self.voice, self.model, self.speed, self.captions = cache, voice, model, speed, captions
        self.client = None
        cache.mkdir(parents=True, exist_ok=True)

    def line(self, text: str) -> tuple[Path, dict | None]:
        key = hashlib.sha256(json.dumps([text, self.voice, self.model, self.speed], sort_keys=True).encode()).hexdigest()[:20]
        raw, clip, tj = self.cache / f"{key}.raw.wav", self.cache / f"{key}.wav", self.cache / f"{key}.transcript.json"
        if not clip.exists():
            if not raw.exists():
                print(f"voice: {text[:70]}", file=sys.stderr)
                self.client = self.client or Client()
                tmp = self.cache / f"{key}.part.wav"
                self.client.speak(text, tmp, model=self.model, fmt="wav", speed=self.speed, **self.voice)
                tmp.replace(raw)
            trim = ("silenceremove=start_periods=1:start_threshold=-45dB:start_silence=0.03,"
                    "areverse,silenceremove=start_periods=1:start_threshold=-45dB:start_silence=0.06,areverse")
            run(["ffmpeg", "-v", "error", "-y", "-i", raw, "-af", trim, "-ar", SR, "-ac", 1, "-sample_fmt", "s16",
                 clip], "trimming a voice line")
        tr = None
        if self.captions:
            if tj.exists():
                tr = json.loads(tj.read_text())
            else:
                self.client = self.client or Client()
                r = self.client.transcribe(clip)
                tr = {"text": r.get("text"), "segments": r.get("segments")}
                tj.write_text(json.dumps(tr, indent=2))
        return clip, tr


def build_voice_track(clips: list[Path], gap: float, tail: float, out: Path) -> list[float]:
    """Concatenate mono 48 kHz clips with gaps; return each line's start time. Pure stdlib."""
    starts, t = [], 0.0
    with wave.open(str(out), "wb") as w:
        w.setnchannels(1), w.setsampwidth(2), w.setframerate(SR)
        for i, c in enumerate(clips):
            with wave.open(str(c)) as r:
                frames = r.readframes(r.getnframes())
                n = r.getnframes()
            starts.append(t)
            pad = gap if i < len(clips) - 1 else tail
            w.writeframes(frames + b"\x00\x00" * int(pad * SR))
            t += n / SR + int(pad * SR) / SR
    return starts


def loudnorm_filter(src: Path, target: float = -14.0) -> str:
    """Two-pass EBU R128: measure first, then a linear gain to hit the target exactly on short ads."""
    r = subprocess.run(["ffmpeg", "-hide_banner", "-i", str(src), "-af",
                        f"loudnorm=I={target}:TP=-1:LRA=11:print_format=json", "-f", "null", "-"],
                       capture_output=True, text=True)
    try:
        m = json.loads(r.stderr[r.stderr.rindex("{"):r.stderr.rindex("}") + 1])
        return (f"loudnorm=I={target}:TP=-1:LRA=11:measured_I={m['input_i']}:measured_TP={m['input_tp']}:"
                f"measured_LRA={m['input_lra']}:measured_thresh={m['input_thresh']}:offset={m['target_offset']}:linear=true")
    except (ValueError, KeyError):
        return f"loudnorm=I={target}:TP=-1:LRA=11"


def render_variant(spec, v, ratio, voicer, base, outdir, a) -> dict:
    W, H = LAYOUTS[ratio]["size"]
    clips, trs = zip(*[voicer.line(ln["text"]) for ln in v["lines"]])
    card = spec["end_card"]
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        vo = td / "voice.wav"
        starts = build_voice_track(list(clips), a.gap, 0.35, vo)
        speech_end = wav_seconds(vo)
        card_start = speech_end
        total = speech_end + (card["seconds"] if card else 0)
        # captions + overlays
        caps, overlays, all_words = [], [], []
        for ln, c, tr, s in zip(v["lines"], clips, trs, starts):
            if not a.no_captions:
                ws = [dict(w, start=w["start"] + s, end=w["end"] + s) for w in timed_words(ln["text"], tr, wav_seconds(c))]
                all_words += ws
            if ln.get("overlay"):
                overlays.append({"start": s, "end": s + wav_seconds(c) + a.gap, "text": ln["overlay"]})
        if all_words:
            caps = ad_cues(all_words, upper=not a.lowercase)
        (td / "ad.ass").write_text(ass_doc(ratio, caps, overlays, card, card_start, total, spec["label"]), encoding="utf-8")
        # picture
        scene_starts = list(starts) + ([card_start] if card else [])
        frames = frame_splits(scene_starts, total)
        lst = td / "list.txt"
        with open(lst, "w") as f:
            for i, n in enumerate(frames):
                is_card = card and i == len(frames) - 1
                m = resolve_media(card.get("media") if is_card else v["lines"][i].get("media"), base)
                seg = td / f"s{i:03d}.mp4"
                scene_clip(m, n, i, seg, W, H, dim=bool(is_card and m))
                f.write(f"file '{seg}'\n")
        run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", td / "bg.mp4"],
            "joining scenes")
        mix = td / "mix.wav"
        amaps = ["-i", vo]
        fc = [f"[0:a]aresample={SR},apad=whole_dur={total:.3f}[vo0]"]
        music = a.music or (resolve_media(spec["music"], base) if spec["music"] else None)
        if music:
            amaps += ["-stream_loop", "-1", "-i", Path(music).resolve()]
            fc += ["[vo0]asplit=2[vo][sc]",
                   f"[1:a]aresample={SR},volume=0.28,atrim=0:{total:.3f},afade=t=out:st={max(0, total - 0.8):.3f}:d=0.8[mus]",
                   "[mus][sc]sidechaincompress=threshold=0.03:ratio=8:attack=20:release=350[duck]",
                   "[vo][duck]amix=inputs=2:normalize=0:duration=first[a]"]
        else:
            fc += ["[vo0]anull[a]"]
        run(["ffmpeg", "-v", "error", "-y", *amaps, "-filter_complex", ";".join(fc), "-map", "[a]", "-t", f"{total:.3f}",
             mix], "mixing audio")
        tag = ratio.replace(":", "x")
        out = outdir / f"{slug(spec['brand'])}_{v['id']}_{tag}.mp4"
        run(["ffmpeg", "-v", "error", "-y", "-i", td / "bg.mp4", "-i", mix, "-vf", "ass=ad.ass",
             "-af", loudnorm_filter(mix), "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
             "-c:a", "aac", "-b:a", "192k", "-ar", SR, "-t", f"{total:.3f}", "-movflags", "+faststart", out.resolve()],
            f"rendering {out.name}", cwd=td)
    srt = outdir / f"{slug(spec['brand'])}_{v['id']}.srt"
    if caps:
        srt.write_text(to_srt([c for c in caps if c["start"] < card_start]), encoding="utf-8")
    hook_s = round(wav_seconds(clips[0]), 2)
    return {"file": out.name, "variant": v["id"], "hook": v["hook"], "body": v["body"], "ratio": ratio,
            "seconds": round(total, 2), "hook_seconds": hook_s, "hook_over_budget": hook_s > a.hook_budget,
            "srt": srt.name if caps else None, "lines": len(v["lines"])}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check", help="free lint of the ad file")
    c.add_argument("ad", type=Path)
    c.add_argument("--hook-budget", type=float, default=3.0)
    r = sub.add_parser("render", help="voice, caption and render every variant")
    r.add_argument("ad", type=Path)
    r.add_argument("-o", "--out", type=Path, default=Path("ads_out"))
    r.add_argument("--ratios", default="9:16", help="comma list of 9:16, 4:5, 1:1, 16:9")
    r.add_argument("--only", help="comma list of variant, hook or body ids")
    r.add_argument("--max", type=int, help="render at most N variants")
    r.add_argument("--voice", help="Miragea saved voice id (env MIRAGEA_VOICE_ID)")
    r.add_argument("--ref-url", help="public URL of a reference clip to clone (env MIRAGEA_REF_URL)")
    r.add_argument("--ref-text", help="exact words spoken in the reference clip (env MIRAGEA_REF_TEXT)")
    r.add_argument("--model", default="expressive", choices=["expressive", "standard"])
    r.add_argument("--music", type=Path, help="music bed, ducked under the voice (overrides \"music\" in the file)")
    r.add_argument("--gap", type=float, default=0.12, help="pause between lines in seconds (UGC pace: 0.08-0.2)")
    r.add_argument("--hook-budget", type=float, default=3.0)
    r.add_argument("--no-captions", action="store_true")
    r.add_argument("--lowercase", action="store_true", help="captions in sentence case instead of UPPERCASE")
    r.add_argument("--dry-run", action="store_true", help="print the variant matrix with estimated lengths; no API calls")
    a = ap.parse_args(argv)

    try:
        spec = load_spec(json.loads(a.ad.read_text(encoding="utf-8")))
    except (OSError, ValueError) as exc:
        sys.exit(f"ads: error in {a.ad}: {exc}")
    base = a.ad.resolve().parent
    problems, advice = check(spec, base, a.hook_budget)
    if a.cmd == "check":
        for p in problems:
            print("! " + p)
        for x in advice:
            print("~ " + x)
        n = len(variants(spec))
        print(f"{n} variant(s): {len(spec['hooks'])} hooks x {len(spec['bodies'])} bodies. "
              f"{len(problems)} problem(s), {len(advice)} note(s).")
        return 1 if problems else 0

    ratios = [x.strip() for x in a.ratios.split(",") if x.strip()]
    bad = [x for x in ratios if x not in LAYOUTS]
    if bad:
        sys.exit(f"ads: error: unknown ratio {bad}; use {', '.join(LAYOUTS)}.")
    vs = variants(spec, [x.strip() for x in a.only.split(",")] if a.only else None, a.max)
    if not vs:
        sys.exit("ads: error: --only matched no variant. Run `ads.py render ad.json --dry-run` to list ids.")
    if a.dry_run:
        for v in vs:
            est = sum(est_seconds(x["text"], spec["speed"]) + a.gap for x in v["lines"])
            est += spec["end_card"]["seconds"] if spec["end_card"] else 0
            print(f"{v['id']:<24} ~{est:4.1f}s  hook ~{est_seconds(v['lines'][0]['text'], spec['speed']):.1f}s  "
                  f"{len(v['lines'])} lines  x {len(ratios)} ratio(s)")
        uniq = {ln["text"] for v in vs for ln in v["lines"]}
        print(f"{len(vs) * len(ratios)} video(s); {len(uniq)} unique lines to voice "
              f"({sum(len(t) for t in uniq)} characters), each billed once.")
        return 0
    if problems:
        sys.exit("ads: fix these first (`ads.py check`):\n" + "\n".join("! " + p for p in problems))
    for tool in ("ffmpeg", "ffprobe"):
        if not shutil.which(tool):
            sys.exit(f"ads: error: {tool} not found. Install ffmpeg (brew/apt/winget install ffmpeg) and re-run.")
    voice_id = a.voice or os.environ.get("MIRAGEA_VOICE_ID")
    ref = a.ref_url or os.environ.get("MIRAGEA_REF_URL")
    if not (voice_id or ref):
        sys.exit("ads: error: no voice chosen. Pass --voice YOUR_MIRAGEA_VOICE_ID, or --ref-url https://public/clip.wav "
                 "--ref-text 'exact words in the clip' (only a voice you own or may use).")
    voice = {"actor_id": voice_id} if voice_id else {
        "reference_audio_url": ref, "reference_text": a.ref_text or os.environ.get("MIRAGEA_REF_TEXT")}
    a.out.mkdir(parents=True, exist_ok=True)
    voicer = Voicer(base / (a.ad.stem + ".ads-cache"), voice, a.model, spec["speed"], not a.no_captions)
    rows = []
    try:
        for v in vs:
            for ratio in ratios:
                print(f"render {v['id']} {ratio}", file=sys.stderr)
                rows.append(render_variant(spec, v, ratio, voicer, base, a.out, a))
    except MirageaError as exc:
        sys.exit(f"ads: error: {exc}\n(Lines already voiced are cached; re-running will not re-bill them.)")
    with open(a.out / "manifest.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    (a.out / "manifest.json").write_text(json.dumps({"brand": spec["brand"], "videos": rows, "advice": advice}, indent=2))
    print(json.dumps({"videos": len(rows), "out": str(a.out), "longest_s": max(x["seconds"] for x in rows),
                      "hooks_over_budget": sorted({x["hook"] for x in rows if x["hook_over_budget"]})}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

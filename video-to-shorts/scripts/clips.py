#!/usr/bin/env python3
"""Turn a long video (podcast, webinar, tutorial, stream VOD) into captioned 9:16 Shorts.

    python3 clips.py moments talk.mp4 --suggest 5     # transcript + talk.moments.md + talk.clips.json draft
    python3 clips.py render talk.mp4 talk.clips.json   # -> shorts_out/clip_01.mp4 ... + manifest.json

The agent (Claude Code, Codex, Cursor...) reads talk.moments.md and picks the moments itself, so no
extra LLM key is needed. Cuts snap to whole sentences, frames become 1080x1920 (centre crop or
blurred fill), 1-3 word captions are burned in, loudness is -14 LUFS. An optional spoken hook
in your own Miragea voice opens each clip. Speech recognition and voice: Miragea
(https://miragea.ai/v1, env MIRAGEA_API_KEY). Python 3.9+ standard library + ffmpeg.
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
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cues import build_cues, to_srt, words  # noqa: E402
from miragea_client import Client, MirageaError  # noqa: E402

W, H = 1080, 1920
CAPTION_STYLE = ("FontName=Arial,FontSize=13,Bold=1,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,"
                 "BorderStyle=1,Outline=2,Shadow=0,Alignment=2,MarginV=70")
HOOK_WORDS = {"secret", "mistake", "mistakes", "never", "always", "best", "worst", "stop", "why", "how",
              "nobody", "everyone", "truth", "actually", "biggest", "wrong", "free", "money", "first",
              "only", "crazy", "simple", "easy", "hard", "fail", "failed", "lesson", "rule", "trick"}
WEAK_OPENERS = {"and", "so", "but", "because", "or", "then", "also", "um", "uh", "like", "yeah", "which"}


def die(msg: str) -> None:
    sys.exit(f"video-to-shorts: error: {msg}")


def need_ffmpeg() -> None:
    if not (shutil.which("ffmpeg") and shutil.which("ffprobe")):
        die("ffmpeg not found. Install it (macOS: brew install ffmpeg; Ubuntu: sudo apt install ffmpeg; "
            "Windows: winget install ffmpeg).")


# -- transcript ---------------------------------------------------------------
def sha(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()[:16]


def transcribe(src: Path, force: bool = False) -> dict:
    """Same cache file as the video-captions skill (<video>.transcript.json), so one transcript serves both."""
    cache = src.with_name(src.name + ".transcript.json")
    digest = sha(src)
    if cache.exists() and not force:
        data = json.loads(cache.read_text())
        if data.get("sha") == digest:
            print(f"using cached transcript {cache.name} (free)", file=sys.stderr)
            return data
    need_ffmpeg()
    with tempfile.TemporaryDirectory() as td:
        audio = Path(td) / "audio.flac"  # upload a small mono track, never the video itself
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(src), "-vn", "-ac", "1", "-ar", "16000", str(audio)],
                       check=True)
        print("transcribing with Miragea…", file=sys.stderr)
        result = Client().transcribe(audio)
    data = {"sha": digest, **{k: result.get(k) for k in ("text", "language", "segments")}}
    cache.write_text(json.dumps(data, ensure_ascii=False, indent=2))
    return data


def load_transcript(src: Path, transcript: Path | None, force: bool = False) -> dict:
    if transcript:
        return json.loads(Path(transcript).read_text())
    return transcribe(src, force)


def sentences(ws: list, gap: float = 0.8) -> list:
    """Group words into sentences: end on . ! ? or a pause longer than `gap` seconds."""
    out, cur = [], []
    for w in ws:
        if cur and w["start"] - cur[-1]["end"] > gap:
            out.append(cur)
            cur = []
        cur.append(w)
        if re.search(r"[.!?…]['\")\]]*$", w["text"]):
            out.append(cur)
            cur = []
    if cur:
        out.append(cur)
    return [{"start": round(s[0]["start"], 2), "end": round(s[-1]["end"], 2),
             "text": " ".join(x["text"] for x in s)} for s in out]


def fmt(t: float) -> str:
    return f"{int(t // 60):02d}:{t % 60:04.1f}"


def moments_md(sents: list, name: str) -> str:
    lines = [f"# Moments in {name}", "",
             "One sentence per line as [start-end seconds]. Pick 15-60 s stretches that make sense on",
             "their own (a claim + its payoff, a story, a tip). Write them to clips.json as",
             '[{"start": 12.3, "end": 48.0, "title": "...", "hook": "optional spoken opener"}].', ""]
    lines += [f"[{s['start']:.1f}-{s['end']:.1f}] ({fmt(s['start'])}) {s['text']}" for s in sents]
    return "\n".join(lines) + "\n"


# -- picking moments without an LLM --------------------------------------------
def score_window(sents: list) -> float:
    text = " ".join(s["text"] for s in sents)
    toks = re.findall(r"[a-z0-9']+", text.lower())
    if not toks:
        return 0.0
    dur = max(sents[-1]["end"] - sents[0]["start"], 0.1)
    first = re.findall(r"[a-z']+", sents[0]["text"].lower())[:1]
    s = 0.0
    s += 2.0 * sum(1 for t in toks if t in HOOK_WORDS) / len(toks) * 10
    s += 1.5 * ("?" in sents[0]["text"])                    # opens with a question
    s += 1.0 * bool(re.search(r"\d", text))                  # numbers, lists, results
    s += 0.5 * sum(1 for t in toks if t in ("you", "your")) / len(toks) * 10
    s += min(len(toks) / dur, 4.0) / 4.0                     # energy: words per second
    s -= 2.0 * bool(first and first[0] in WEAK_OPENERS)       # starts mid-thought
    s += 0.5 * bool(re.search(r"[.!?]['\")\]]*$", sents[-1]["text"]))
    return round(s, 3)


def suggest(sents: list, n: int = 5, min_s: float = 20.0, max_s: float = 60.0) -> list:
    """Rank non-overlapping windows of whole sentences, each min_s..max_s long."""
    cands = []
    for i in range(len(sents)):
        for j in range(i, len(sents)):
            dur = sents[j]["end"] - sents[i]["start"]
            if dur > max_s:
                break
            if dur >= min_s:
                cands.append((score_window(sents[i:j + 1]), i, j))
                break  # shortest window from i that is long enough
    cands.sort(key=lambda c: (-c[0], c[1]))
    picked = []
    for sc, i, j in cands:
        a, b = sents[i]["start"], sents[j]["end"]
        if all(b <= p["start"] or a >= p["end"] for p in picked):
            title = re.sub(r"\s+", " ", sents[i]["text"]).strip()
            picked.append({"start": a, "end": b, "title": title[:70], "score": sc})
        if len(picked) >= n:
            break
    return sorted(picked, key=lambda p: p["start"])


# -- cutting -------------------------------------------------------------------
def snap(start: float, end: float, sents: list, pad_in: float = 0.15, pad_out: float = 0.35) -> tuple:
    """Move cut points to sentence edges so a clip never starts or ends mid-word."""
    if not sents:
        return max(0.0, start), end
    inside = [s for s in sents if s["end"] > start and s["start"] < end] or \
             [min(sents, key=lambda s: abs(s["start"] - start))]
    a = inside[0]["start"]
    b = inside[-1]["end"]
    return round(max(0.0, a - pad_in), 2), round(b + pad_out, 2)


def frame_filter(mode: str) -> str:
    if mode == "crop":  # centre crop: best for one speaker in frame
        return (f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},setsar=1")
    if mode == "fit":   # whole frame on a blurred copy of itself: best for slides, screens, two people
        return (f"split=2[bg][fg];[bg]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},"
                f"boxblur=24:2[bg2];[fg]scale={W}:-2[fg2];[bg2][fg2]overlay=(W-w)/2:(H-h)/2,setsar=1")
    raise ValueError(f"unknown frame mode {mode!r} (use crop or fit)")


def clip_cues(ws: list, start: float, end: float, offset: float = 0.0, hook: str = "", hook_s: float = 0.0) -> list:
    """Shorts-style 1-3 word cues for words in [start, end], shifted to clip time (+offset for a hook)."""
    inner = [dict(w, start=w["start"] - start + offset, end=w["end"] - start + offset)
             for w in ws if w["start"] >= start - 0.05 and w["end"] <= end + 0.05]
    cues = build_cues(inner, "shorts", upper=True)
    if hook and hook_s > 0:
        cues.insert(0, {"start": 0.0, "end": round(hook_s, 2), "text": hook.upper()})
    return cues


def probe_seconds(path: Path) -> float:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                         capture_output=True, text=True, check=True).stdout.strip()
    return round(float(out), 2)


def has_audio(path: Path) -> bool:
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries", "stream=index",
                          "-of", "csv=p=0", str(path)], capture_output=True, text=True).stdout.strip()
    return bool(out)


def render_clip(src: Path, start: float, end: float, srt: Path, out: Path, mode: str,
                hook_wav: Path | None = None, hook_s: float = 0.0, lufs: float = -14.0) -> None:
    vf = frame_filter(mode)
    if hook_wav:  # freeze the first frame while the spoken hook plays
        vf += f",tpad=start_mode=clone:start_duration={hook_s:.2f}"
    vf += f",subtitles={srt.name}:force_style='{CAPTION_STYLE}'"
    cmd = ["ffmpeg", "-v", "error", "-y", "-ss", f"{start:.2f}", "-to", f"{end:.2f}", "-i", str(src.resolve())]
    norm = f"loudnorm=I={lufs}:TP=-1.5:LRA=11,aresample=48000"
    if hook_wav:
        cmd += ["-i", str(hook_wav.resolve())]
        fc = (f"[0:v]{vf}[v];[1:a]aresample=48000,apad=whole_dur={hook_s:.2f}[h];"
              f"[0:a]aresample=48000,afade=t=in:d=0.05[m];[h][m]concat=n=2:v=0:a=1,{norm}[a]")
        cmd += ["-filter_complex", fc, "-map", "[v]", "-map", "[a]"]
    elif has_audio(src):
        cmd += ["-filter_complex", f"[0:v]{vf}[v];[0:a]afade=t=in:d=0.05,{norm}[a]", "-map", "[v]", "-map", "[a]"]
    else:
        cmd += ["-filter_complex", f"[0:v]{vf}[v]", "-map", "[v]"]
    cmd += ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p", "-r", "30",
            "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", str(out.resolve())]
    subprocess.run(cmd, check=True, cwd=srt.parent)


def read_clips(path: Path) -> list:
    data = json.loads(Path(path).read_text())
    clips = data.get("clips", data) if isinstance(data, dict) else data
    if not isinstance(clips, list) or not clips:
        die(f"{path} has no clips. Expected a list like "
            '[{"start": 12.3, "end": 48.0, "title": "...", "hook": "optional"}].')
    for i, c in enumerate(clips, 1):
        if not isinstance(c, dict) or "start" not in c or "end" not in c:
            die(f"clip {i} in {path} needs numeric start and end (seconds).")
        if float(c["end"]) <= float(c["start"]):
            die(f"clip {i} in {path}: end must be after start.")
    return clips


def plan(clips: list, sents: list, hook_wps: float = 2.6) -> list:
    rows = []
    for i, c in enumerate(clips, 1):
        a, b = snap(float(c["start"]), float(c["end"]), sents)
        hook = (c.get("hook") or "").strip()
        hook_est = round(len(hook.split()) / hook_wps, 2) if hook else 0.0
        secs = round(b - a + hook_est, 2)
        warn = []
        if secs < 10:
            warn.append("under 10 s: may feel abrupt")
        if secs > 60:
            warn.append("over 60 s: fine for YouTube Shorts (up to 3 min) but long for TikTok/Reels retention")
        if hook_est > 3.5:
            warn.append("hook over ~3.5 s: tighten it")
        rows.append({"id": f"clip_{i:02d}", "title": c.get("title", ""), "start": a, "end": b,
                     "hook": hook, "seconds": secs, "warnings": warn})
    return rows


# -- commands ------------------------------------------------------------------
def cmd_moments(a) -> int:
    if not a.input.exists():
        die(f"{a.input} does not exist.")
    try:
        data = load_transcript(a.input, a.transcript, a.force)
    except MirageaError as exc:
        die(str(exc))
    sents = sentences(words(data))
    out_dir = a.out_dir or a.input.parent
    out_dir.mkdir(parents=True, exist_ok=True)
    md = out_dir / f"{a.input.stem}.moments.md"
    md.write_text(moments_md(sents, a.input.name), encoding="utf-8")
    result = {"moments": str(md), "sentences": len(sents), "language": data.get("language")}
    if a.suggest:
        picks = suggest(sents, a.suggest, a.min, a.max)
        draft = out_dir / f"{a.input.stem}.clips.json"
        draft.write_text(json.dumps(picks, indent=2), encoding="utf-8")
        result.update(clips=str(draft), suggested=len(picks))
    print(json.dumps(result, indent=2))
    return 0


def cmd_render(a) -> int:
    if not a.input.exists():
        die(f"{a.input} does not exist.")
    clips = read_clips(a.clips)
    try:
        data = load_transcript(a.input, a.transcript, a.force)
    except MirageaError as exc:
        die(str(exc))
    ws = words(data)
    rows = plan(clips, sentences(ws))
    for r in rows:
        print(f"{r['id']}  {fmt(r['start'])}-{fmt(r['end'])}  ~{r['seconds']:>5.1f}s  {r['title']}"
              + "".join(f"\n    ! {w}" for w in r["warnings"]))
    if a.dry_run:
        print("\ndry run: nothing rendered, no API calls. Remove --dry-run to render.")
        return 0
    need_ffmpeg()
    a.out.mkdir(parents=True, exist_ok=True)
    client = None
    voice_ok = bool(a.voice or a.ref_url)
    for r in rows:
        hook_wav, hook_s = None, 0.0
        if r["hook"] and not a.no_hook:
            if not voice_ok:
                die("a clip has a hook but no voice is set. Pass --voice ID (or MIRAGEA_VOICE_ID), "
                    "or --ref-url/--ref-text for a clip of your own voice, or use --no-hook.")
            client = client or Client()
            raw = a.out / f".{r['id']}.hook.raw.wav"
            hook_wav = a.out / f".{r['id']}.hook.wav"
            try:
                client.speak(r["hook"], raw, actor_id=a.voice, reference_audio_url=a.ref_url,
                             reference_text=a.ref_text)
            except MirageaError as exc:
                die(f"[{r['id']}] {exc}")
            trim = ("silenceremove=start_periods=1:start_threshold=-45dB:start_silence=0.05,areverse,"
                    "silenceremove=start_periods=1:start_threshold=-45dB:start_silence=0.08,areverse")
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(raw), "-af", trim, "-ar", "48000",
                            str(hook_wav)], check=True)
            raw.unlink(missing_ok=True)
            hook_s = round(probe_seconds(hook_wav) + 0.25, 2)
        srt = a.out / f"{r['id']}.srt"
        srt.write_text(to_srt(clip_cues(ws, r["start"], r["end"], hook_s, r["hook"] if hook_wav else "", hook_s)),
                       encoding="utf-8")
        out = a.out / f"{r['id']}.mp4"
        render_clip(a.input, r["start"], r["end"], srt, out, a.frame, hook_wav, hook_s, a.lufs)
        if hook_wav:
            hook_wav.unlink(missing_ok=True)
        r.update(file=out.name, srt=srt.name, seconds=probe_seconds(out), hook_seconds=hook_s or None)
        print(f"wrote {out}")
    manifest = {"source": a.input.name, "frame": a.frame, "size": f"{W}x{H}", "lufs": a.lufs, "clips": rows}
    (a.out / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"\n{len(rows)} Shorts in {a.out}/ (manifest.json has titles and timings)")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    m = sub.add_parser("moments", help="transcribe and list sentences with timestamps (+ optional draft picks)")
    m.add_argument("input", type=Path)
    m.add_argument("--suggest", type=int, default=0, metavar="N", help="also draft N picks into <name>.clips.json")
    m.add_argument("--min", type=float, default=20.0, help="shortest suggested clip, seconds (default 20)")
    m.add_argument("--max", type=float, default=60.0, help="longest suggested clip, seconds (default 60)")
    m.add_argument("--out-dir", type=Path)
    r = sub.add_parser("render", help="cut, reframe to 9:16, caption and export the clips in clips.json")
    r.add_argument("input", type=Path)
    r.add_argument("clips", type=Path, help='JSON list: [{"start","end","title","hook"}]')
    r.add_argument("-o", "--out", type=Path, default=Path("shorts_out"))
    r.add_argument("--frame", choices=["crop", "fit"], default="crop",
                   help="crop: centre crop (one speaker); fit: whole frame on blurred fill (slides, screens)")
    r.add_argument("--voice", default=os.getenv("MIRAGEA_VOICE_ID"), help="Miragea voice id for spoken hooks")
    r.add_argument("--ref-url", default=os.getenv("MIRAGEA_REF_URL"), help="public URL of a clip of your voice")
    r.add_argument("--ref-text", default=os.getenv("MIRAGEA_REF_TEXT"), help="exact words in that clip")
    r.add_argument("--no-hook", action="store_true", help="ignore hook lines")
    r.add_argument("--lufs", type=float, default=-14.0, help="loudness target (default -14)")
    r.add_argument("--dry-run", action="store_true", help="show the snapped plan only; no rendering, no API calls")
    for p in (m, r):
        p.add_argument("--transcript", type=Path, help="use this transcript JSON instead of transcribing")
        p.add_argument("--force", action="store_true", help="re-transcribe even if cached")
    a = ap.parse_args(argv)
    return cmd_moments(a) if a.cmd == "moments" else cmd_render(a)


if __name__ == "__main__":
    sys.exit(main())

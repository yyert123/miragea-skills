#!/usr/bin/env python3
"""Add a timed AI voiceover to a silent screen recording in one command.

    python3 voiceover.py demo.mp4 demo.script.txt --voice VOICE_ID
    python3 voiceover.py demo.mp4 demo.script.txt --ref-url https://.../me.wav --ref-text "..." --burn

Script format (one line per step; the timestamp is when that step starts on screen):

    [00:00] Welcome to Acme. Let's create your first project.
    [00:06.5] Click New Project in the top right corner.
    [00:14] Give it a name and press Create.

Each line is voiced with Miragea (https://miragea.ai/v1) and starts exactly at its timestamp. When a line
is longer than its slot, it is sped up slightly (up to --max-speed) and, if it still does not fit, the
video holds its last frame until the sentence ends ("freeze-sync"), so narration never overlaps or drifts.
Outputs: demo.voiceover.mp4, demo.voiceover.wav (voice only), demo.voiceover.srt/.vtt, demo.voiceover.json.
Python 3.9+ standard library + ffmpeg. Env: MIRAGEA_API_KEY (and optionally MIRAGEA_VOICE_ID,
MIRAGEA_REF_URL, MIRAGEA_REF_TEXT as defaults).
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
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cues import build_cues, to_srt, to_vtt  # noqa: E402
from miragea_client import Client, MirageaError  # noqa: E402

GAP = 0.25  # breathing room after each line before the next step starts
CAPTION_STYLE = ("FontName=Arial,FontSize=16,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,"
                 "BackColour=&H80000000,BorderStyle=4,Outline=1,Shadow=0,MarginV=24")
LINE_RE = re.compile(r"^\s*\[?\s*((?:\d+:)?\d{1,2}:\d{2}(?:\.\d+)?|\d+(?:\.\d+)?s?)\s*\]?\s*[-–—:]?\s*(.+?)\s*$")


class ScriptError(ValueError):
    pass


def parse_time(s: str) -> float:
    s = s.rstrip("s")
    parts = [float(p) for p in s.split(":")]
    t = 0.0
    for p in parts:
        t = t * 60 + p
    return t


def parse_script(text: str) -> list[dict]:
    """Return [{t, text}] sorted by time; raises ScriptError with the offending line number."""
    lines = []
    for n, raw in enumerate(text.splitlines(), 1):
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        m = LINE_RE.match(raw)
        if not m:
            raise ScriptError(f"line {n}: no timestamp. Start each line like '[01:23] Click Save.' (got: {raw.strip()[:60]!r})")
        t, say = parse_time(m.group(1)), re.sub(r"\s*#\s*step \d+:.*$", "", m.group(2)).strip()
        if not say or say.startswith("#"):  # untouched template step: not narrated
            continue
        if lines and t <= lines[-1]["t"]:
            raise ScriptError(f"line {n}: timestamp {m.group(1)} is not after the previous line. Keep lines in time order.")
        lines.append({"t": t, "text": say})
    if not lines:
        raise ScriptError("the script has no lines. Add lines like '[00:00] Welcome to the demo.'")
    return lines


def plan(lines: list[dict], video_dur: float, clip_durs: list[float], max_speed: float = 1.15) -> list[dict]:
    """Decide speed-up and freeze time per line so every line fits its slot. Pure function (tested)."""
    out, shift = [], 0.0
    for i, (ln, dur) in enumerate(zip(lines, clip_durs)):
        if ln["t"] >= video_dur:
            raise ScriptError(f"line at {ln['t']:.1f}s starts after the video ends ({video_dur:.1f}s).")
        end = lines[i + 1]["t"] if i + 1 < len(lines) else video_dur
        slot = end - ln["t"]
        room = max(slot - GAP, 0.01)
        speed = 1.0 if dur <= room else min(max_speed, dur / room)
        spoken = dur / speed
        freeze = max(0.0, spoken + GAP - slot) if i + 1 < len(lines) else max(0.0, spoken + 0.5 - slot)
        out.append({"text": ln["text"], "src_start": ln["t"], "src_end": end, "start": round(ln["t"] + shift, 3),
                    "duration": round(spoken, 3), "speed": round(speed, 3), "freeze": round(freeze, 3)})
        shift += freeze
    return out


def caption_words(entries: list[dict]) -> list[dict]:
    """Spread each line's words over its spoken time, weighted by length (lines are short, so this is tight)."""
    ws = []
    for e in entries:
        toks = e["text"].split()
        weights = [len(t) + 1 for t in toks]
        total, acc = sum(weights), 0.0
        for tok, w in zip(toks, weights):
            a = e["start"] + e["duration"] * acc / total
            acc += w
            ws.append({"text": tok, "start": round(a, 3), "end": round(e["start"] + e["duration"] * acc / total, 3)})
    return ws


def need_ffmpeg() -> None:
    for tool in ("ffmpeg", "ffprobe"):
        if not shutil.which(tool):
            sys.exit(f"voiceover: error: {tool} not found. Install ffmpeg (macOS: brew install ffmpeg; "
                     "Ubuntu: sudo apt install ffmpeg; Windows: winget install ffmpeg), then re-run.")


def probe(path: Path) -> dict:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration:stream=codec_type,width,height",
                          "-of", "json", str(path)], capture_output=True, text=True)
    if out.returncode:
        sys.exit(f"voiceover: error: cannot read {path} ({out.stderr.strip()[:200]}). Is it a video file?")
    d = json.loads(out.stdout)
    return {"duration": float(d["format"]["duration"]),
            "has_audio": any(s.get("codec_type") == "audio" for s in d.get("streams", []))}


def voice_args(a) -> dict:
    voice = a.voice or os.environ.get("MIRAGEA_VOICE_ID")
    ref = a.ref_url or os.environ.get("MIRAGEA_REF_URL")
    if not (voice or ref):
        sys.exit("voiceover: error: no voice chosen. Pass --voice YOUR_MIRAGEA_VOICE_ID (saved in your Miragea account) "
                 "or --ref-url https://public/clip.wav --ref-text 'exact words in the clip'. "
                 "Set MIRAGEA_VOICE_ID once to skip this flag.")
    if voice:
        return {"actor_id": voice}
    return {"reference_audio_url": ref, "reference_text": a.ref_text or os.environ.get("MIRAGEA_REF_TEXT")}


def synth(client: Client | None, text: str, voice: dict, model: str, cache: Path) -> Path:
    key = hashlib.sha256(json.dumps([text, voice, model], sort_keys=True).encode()).hexdigest()[:20]
    path = cache / f"{key}.wav"
    if path.exists() and path.stat().st_size > 1000:
        return path
    if client is None:
        client = Client()
    tmp = path.with_suffix(".part.wav")
    client.speak(text, tmp, model=model, fmt="wav", **voice)
    tmp.replace(path)
    return path


def render(video: Path, entries: list[dict], clips: list[Path], out: Path, voice_out: Path, info: dict,
           keep_audio: bool, music: Path | None, srt: Path | None) -> None:
    total = entries[-1]["start"] + (entries[-1]["src_end"] - entries[-1]["src_start"]) + entries[-1]["freeze"]
    segs, fc = [], []
    if entries[0]["src_start"] > 0:
        segs.append((0.0, entries[0]["src_start"], 0.0))
    segs += [(e["src_start"], e["src_end"], e["freeze"]) for e in entries]
    for i, (a, b, f) in enumerate(segs):
        pad = f",tpad=stop_mode=clone:stop_duration={f:.3f}" if f > 0 else ""
        fc.append(f"[0:v]trim=start={a:.3f}:end={b:.3f},setpts=PTS-STARTPTS{pad}[v{i}]")
    fc.append("".join(f"[v{i}]" for i in range(len(segs))) + f"concat=n={len(segs)}:v=1:a=0[vcat]")
    vlast = "vcat"
    if srt:
        fc.append(f"[vcat]subtitles={srt.name}:force_style='{CAPTION_STYLE}'[vsub]")
        vlast = "vsub"
    inputs = ["-i", str(video.resolve())]
    for i, (e, c) in enumerate(zip(entries, clips)):
        inputs += ["-i", str(c.resolve())]
        ms = int(e["start"] * 1000)
        tempo = f"atempo={e['speed']:.3f}," if e["speed"] != 1.0 else ""
        fc.append(f"[{i + 1}:a]aresample=48000,aformat=channel_layouts=mono,{tempo}adelay={ms}:all=1[a{i}]")
    n = len(entries)
    fc.append("".join(f"[a{i}]" for i in range(n)) + f"amix=inputs={n}:normalize=0,apad=whole_dur={total:.3f},"
              f"atrim=0:{total:.3f}[voice]")
    fc.append("[voice]asplit=3[vo1][vo2][vo3]")
    bed = []
    if keep_audio and info["has_audio"]:
        bed.append("[0:a]volume=0.15,apad[orig]")  # original audio stays under the narration (no time-stretch)
    if music:
        inputs += ["-stream_loop", "-1", "-i", str(music.resolve())]
        mi = n + 1
        bed.append(f"[{mi}:a]aresample=48000,volume=0.35,atrim=0:{total:.3f}[mus];"
                   f"[mus][vo3]sidechaincompress=threshold=0.03:ratio=8:attack=20:release=400[duck]")
    fc += bed
    mix = ["[vo1]"] + (["[orig]"] if keep_audio and info["has_audio"] else []) + (["[duck]"] if music else [])
    fc.append("".join(mix) + f"amix=inputs={len(mix)}:normalize=0:duration=first,loudnorm=I=-16:TP=-1.5:LRA=11,"
              f"aresample=48000[aout]")
    if not music:
        fc.append("[vo3]anullsink")
    fc.append("[vo2]loudnorm=I=-16:TP=-1.5:LRA=11,aresample=48000[vonly]")
    cmd = ["ffmpeg", "-v", "error", "-y", *inputs, "-filter_complex", ";".join(fc),
           "-map", f"[{vlast}]", "-map", "[aout]", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
           "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-t", f"{total:.3f}", str(out.resolve()),
           "-map", "[vonly]", "-c:a", "pcm_s16le", str(voice_out.resolve())]
    r = subprocess.run(cmd, cwd=str(srt.parent) if srt else None, capture_output=True, text=True)
    if r.returncode:
        sys.exit(f"voiceover: error: ffmpeg failed while rendering:\n{r.stderr.strip()[-1200:]}\n"
                 "Your voice clips are cached; fix the issue and re-run (no extra cost).")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("video", type=Path)
    ap.add_argument("script", type=Path, help="timed script (see format above)")
    ap.add_argument("--voice", help="Miragea saved voice id (env MIRAGEA_VOICE_ID)")
    ap.add_argument("--ref-url", help="public URL of a reference clip to clone (env MIRAGEA_REF_URL)")
    ap.add_argument("--ref-text", help="exact words spoken in the reference clip (cheaper 1x rate)")
    ap.add_argument("--model", default="expressive", choices=["expressive", "standard"])
    ap.add_argument("--max-speed", type=float, default=1.15, help="max speed-up before freezing frames (default 1.15)")
    ap.add_argument("--burn", action="store_true", help="burn captions into the video")
    ap.add_argument("--keep-audio", action="store_true", help="keep the recording's own audio, quietly, under the voice")
    ap.add_argument("--music", type=Path, help="background music file; auto-ducked under the voice")
    ap.add_argument("-o", "--output", type=Path, help="output video (default: VIDEO.voiceover.mp4)")
    ap.add_argument("--dry-run", action="store_true", help="check the script and show the plan without generating voice")
    a = ap.parse_args(argv)

    need_ffmpeg()
    if not a.video.exists():
        sys.exit(f"voiceover: error: {a.video} not found.")
    try:
        lines = parse_script(a.script.read_text(encoding="utf-8"))
    except (OSError, ScriptError) as exc:
        sys.exit(f"voiceover: error in {a.script}: {exc}")
    info = probe(a.video)
    out = a.output or a.video.with_name(a.video.stem + ".voiceover.mp4")
    base = out.with_suffix("")
    if a.dry_run:
        est = [len(ln["text"].split()) / 2.6 for ln in lines]  # ~156 wpm narration
        for e in plan(lines, info["duration"], est, a.max_speed):
            flag = "  <- will freeze %.1fs" % e["freeze"] if e["freeze"] else ""
            print(f"[{e['src_start']:7.2f}s] slot {e['src_end'] - e['src_start']:5.1f}s ~{e['duration']:4.1f}s{flag}  {e['text'][:60]}")
        print(f"{len(lines)} lines, {sum(len(ln['text']) for ln in lines)} characters to voice.")
        return 0
    voice = voice_args(a)
    cache = a.video.with_name(a.video.stem + ".voiceover-cache")
    cache.mkdir(exist_ok=True)
    client = None
    clips = []
    try:
        for i, ln in enumerate(lines, 1):
            print(f"voice {i}/{len(lines)}: {ln['text'][:70]}", file=sys.stderr)
            if len(ln["text"]) > 2000:
                sys.exit(f"voiceover: error: line {i} is over 2,000 characters. Split it into shorter steps.")
            clips.append(synth(client, ln["text"], voice, a.model, cache))
    except MirageaError as exc:
        sys.exit(f"voiceover: error: {exc}\n(Lines already voiced are cached in {cache.name}; re-running will not re-bill them.)")
    durs = [probe(c)["duration"] for c in clips]
    entries = plan(lines, info["duration"], durs, a.max_speed)
    cues = build_cues(caption_words(entries), "standard")
    srt, vtt = Path(f"{base}.srt"), Path(f"{base}.vtt")
    srt.write_text(to_srt(cues), encoding="utf-8")
    vtt.write_text(to_vtt(cues), encoding="utf-8")
    voice_out = Path(f"{base}.wav")
    render(a.video, entries, clips, out, voice_out, info, a.keep_audio, a.music, srt if a.burn else None)
    frozen = sum(e["freeze"] for e in entries)
    report = {"video": str(out), "voice_track": str(voice_out), "srt": str(srt), "vtt": str(vtt),
              "source_duration": round(info["duration"], 3), "output_duration": round(info["duration"] + frozen, 3),
              "frozen_seconds": round(frozen, 3), "lines": entries}
    Path(f"{base}.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "lines"}, indent=2))
    tight = [e for e in entries if e["freeze"] > 0]
    if tight:
        print(f"note: {len(tight)} line(s) needed more time than their slot; the video holds a frame for "
              f"{frozen:.1f}s in total. Shorten those lines to avoid it.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

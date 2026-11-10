#!/usr/bin/env python3
"""Script -> finished vertical Short (9:16 MP4) with AI voiceover and word-timed pop captions, one command.

    python3 short.py script.txt --voice VOICE_ID                      # text-on-gradient Short
    python3 short.py script.txt --media ./broll --music bed.mp3        # your images/clips, ducked music

Script: scenes separated by a blank line. A scene may start with "@file.jpg" (or .png/.mp4/.mov) to pick
its background; otherwise files from --media are used in name order, and with no media an animated
gradient is drawn. Each scene is voiced with Miragea (https://miragea.ai/v1); the finished voice track is
then transcribed with Miragea so captions follow the real speech, not an estimate. Images get a slow
Ken Burns move, clips are cropped to 9:16 and looped/trimmed to the scene, music is ducked under the
voice, and loudness is normalized to -14 LUFS (YouTube/TikTok/Reels). Outputs: script.short.mp4,
script.short.srt, script.short.json. Python 3.9+ stdlib + ffmpeg.
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

W, H, FPS = 1080, 1920, 30
IMG = {".jpg", ".jpeg", ".png", ".webp"}
VID = {".mp4", ".mov", ".m4v", ".webm", ".mkv"}
GRADIENTS = [("0x0f172a", "0x7c3aed"), ("0x111827", "0x0ea5e9"), ("0x1f2937", "0xf97316"), ("0x022c22", "0x10b981")]
CAPTION_STYLE = ("FontName=Arial,FontSize=18,Bold=1,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,"
                 "BorderStyle=1,Outline=2.2,Shadow=0,Alignment=2,MarginV=70")


def parse_script(text: str) -> list[dict]:
    """Blank-line separated scenes; optional leading '@media' token. Pure function (tested)."""
    scenes = []
    for block in re.split(r"\n\s*\n", text.strip()):
        lines = [ln for ln in block.strip().splitlines() if not ln.lstrip().startswith("#")]
        body = " ".join(ln.strip() for ln in lines).strip()
        media = None
        m = re.match(r"^@(\S+)\s*(.*)$", body)
        if m:
            media, body = m.group(1), m.group(2).strip()
        if body:
            scenes.append({"text": body, "media": media})
    if not scenes:
        raise ValueError("the script is empty. Write one short paragraph per scene, separated by blank lines.")
    for i, s in enumerate(scenes, 1):
        if len(s["text"]) > 2000:
            raise ValueError(f"scene {i} is over 2,000 characters; split it into two scenes.")
    return scenes


def assign_media(scenes: list[dict], script_dir: Path, media_dir: Path | None) -> list[Path | None]:
    named = {Path(s["media"]).name for s in scenes if s["media"]}
    pool = sorted(p for p in media_dir.iterdir()
                  if p.suffix.lower() in IMG | VID and p.name not in named) if media_dir else []
    out, k = [], 0
    for s in scenes:
        if s["media"]:
            p = Path(s["media"]).expanduser()
            for base in ([] if p.is_absolute() else [script_dir] + ([media_dir] if media_dir else [])):
                if (base / p).exists():
                    p = base / p
                    break
            if not p.exists():
                sys.exit(f"short: error: media file '{s['media']}' not found (looked next to the script and in --media).")
            out.append(p)
        elif pool:
            out.append(pool[k % len(pool)])
            k += 1
        else:
            out.append(None)
    return out


def run(cmd: list[str], what: str) -> None:
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode:
        sys.exit(f"short: error: ffmpeg failed while {what}:\n{r.stderr.strip()[-900:]}\n"
                 "Voice clips and the transcript are cached; fix the issue and re-run (no extra cost).")


def duration(p: Path) -> float:
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(p)],
                       capture_output=True, text=True)
    return float(r.stdout.strip())


def scene_clip(media: Path | None, dur: float, idx: int, out: Path) -> None:
    frames = max(1, int(round(dur * FPS)))
    base = ["ffmpeg", "-v", "error", "-y"]
    if media is None:
        c0, c1 = GRADIENTS[idx % len(GRADIENTS)]
        src = f"gradients=s={W}x{H}:c0={c0}:c1={c1}:speed=0.008:duration={dur:.3f}:rate={FPS}"
        cmd = base + ["-f", "lavfi", "-i", src]
        vf = "format=yuv420p"
    elif media.suffix.lower() in IMG:
        zin = "min(zoom+0.0007,1.15)" if idx % 2 == 0 else "if(eq(on,0),1.15,max(zoom-0.0007,1.0))"
        cmd = base + ["-loop", "1", "-i", str(media)]
        vf = (f"scale={W * 2}:{H * 2}:force_original_aspect_ratio=increase,crop={W * 2}:{H * 2},"
              f"zoompan=z='{zin}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={frames}:s={W}x{H}:fps={FPS},format=yuv420p")
    else:
        cmd = base + ["-stream_loop", "-1", "-i", str(media)]
        vf = f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},fps={FPS},format=yuv420p"
    run(cmd + ["-vf", vf, "-frames:v", str(frames), "-an", "-c:v", "libx264", "-preset", "veryfast",
               "-crf", "20", str(out)], f"preparing scene {idx + 1}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("script", type=Path)
    ap.add_argument("--voice", help="Miragea saved voice id (env MIRAGEA_VOICE_ID)")
    ap.add_argument("--ref-url", help="public URL of a reference clip to clone (env MIRAGEA_REF_URL)")
    ap.add_argument("--ref-text", help="exact words spoken in the reference clip (cheaper 1x rate)")
    ap.add_argument("--model", default="expressive", choices=["expressive", "standard"])
    ap.add_argument("--media", type=Path, help="folder of images/clips used in name order for scenes without @media")
    ap.add_argument("--music", type=Path, help="background music, looped and ducked under the voice")
    ap.add_argument("--no-captions", action="store_true")
    ap.add_argument("--lowercase", action="store_true", help="captions in sentence case instead of UPPERCASE")
    ap.add_argument("-o", "--output", type=Path, help="output MP4 (default: SCRIPT.short.mp4)")
    a = ap.parse_args(argv)

    for tool in ("ffmpeg", "ffprobe"):
        if not shutil.which(tool):
            sys.exit(f"short: error: {tool} not found. Install ffmpeg (brew/apt/winget install ffmpeg) and re-run.")
    try:
        scenes = parse_script(a.script.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        sys.exit(f"short: error in {a.script}: {exc}")
    if a.media and not a.media.is_dir():
        sys.exit(f"short: error: --media {a.media} is not a folder.")
    media = assign_media(scenes, a.script.resolve().parent, a.media)
    voice_id = a.voice or os.environ.get("MIRAGEA_VOICE_ID")
    ref = a.ref_url or os.environ.get("MIRAGEA_REF_URL")
    if not (voice_id or ref):
        sys.exit("short: error: no voice chosen. Pass --voice YOUR_MIRAGEA_VOICE_ID or --ref-url https://public/clip.wav "
                 "--ref-text 'exact words in the clip' (or set MIRAGEA_VOICE_ID once).")
    voice = {"actor_id": voice_id} if voice_id else {
        "reference_audio_url": ref, "reference_text": a.ref_text or os.environ.get("MIRAGEA_REF_TEXT")}
    out = a.output or a.script.with_name(a.script.stem + ".short.mp4")
    stem = str(out)[: -len(out.suffix)] if out.suffix else str(out)
    cache = a.script.resolve().with_name(a.script.stem + ".short-cache")
    cache.mkdir(exist_ok=True)

    client, clips = None, []
    try:
        for i, s in enumerate(scenes, 1):
            key = hashlib.sha256(json.dumps([s["text"], voice, a.model], sort_keys=True).encode()).hexdigest()[:20]
            p = cache / f"{key}.wav"
            if not p.exists():
                print(f"voice {i}/{len(scenes)}: {s['text'][:70]}", file=sys.stderr)
                client = client or Client()
                tmp = cache / f"{key}.part.wav"
                client.speak(s["text"], tmp, model=a.model, fmt="wav", **voice)
                tmp.replace(p)
            clips.append(p)
    except MirageaError as exc:
        sys.exit(f"short: error: {exc}\n(Scenes already voiced are cached; re-running will not re-bill them.)")

    pause = 0.18
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        durs = [duration(c) + pause for c in clips]
        # Voice track: scenes back to back with a short breath between them.
        inputs, parts = [], []
        for i, c in enumerate(clips):
            inputs += ["-i", str(c)]
            parts.append(f"[{i}:a]aresample=48000,aformat=channel_layouts=mono,apad=pad_dur={pause}[a{i}]")
        voice_wav = cache / ("voice-" + hashlib.sha256("".join(c.name for c in clips).encode()).hexdigest()[:16] + ".wav")
        if not voice_wav.exists():
            run(["ffmpeg", "-v", "error", "-y", *inputs, "-filter_complex",
                 ";".join(parts) + ";" + "".join(f"[a{i}]" for i in range(len(clips))) + f"concat=n={len(clips)}:v=0:a=1",
                 str(voice_wav)], "joining the voice track")
        total = duration(voice_wav)
        srt = Path(stem + ".srt")
        if not a.no_captions:
            tcache = Path(str(voice_wav) + ".transcript.json")
            if tcache.exists():
                tr = json.loads(tcache.read_text())
            else:
                print("timing captions with Miragea speech recognition…", file=sys.stderr)
                try:
                    tr = (client or Client()).transcribe(voice_wav)
                except MirageaError as exc:
                    sys.exit(f"short: error: {exc}")
                tr = {k: tr.get(k) for k in ("text", "language", "segments")}
                tcache.write_text(json.dumps(tr, indent=2))
            cues = build_cues(words(tr), "shorts", upper=not a.lowercase)
            srt.write_text(to_srt(cues), encoding="utf-8")
        # Background per scene, then concat.
        seg_list = td / "list.txt"
        with open(seg_list, "w") as f:
            for i, (m, d) in enumerate(zip(media, durs)):
                seg = td / f"s{i:03d}.mp4"
                scene_clip(m, d, i, seg)
                f.write(f"file '{seg}'\n")
        bg = td / "bg.mp4"
        run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(seg_list), "-c", "copy", str(bg)],
            "joining scenes")
        fc, maps = [], ["-i", str(bg), "-i", str(voice_wav.resolve())]
        vchain = "[0:v]null"
        if not a.no_captions:
            shutil.copy(srt, td / "cap.srt")
            vchain = f"[0:v]subtitles=cap.srt:force_style='{CAPTION_STYLE}'"
        fc.append(vchain + "[v]")
        if a.music:
            maps += ["-stream_loop", "-1", "-i", str(a.music.resolve())]
            fc.append("[1:a]aresample=48000,asplit=2[vo][sc]")
            fc.append(f"[2:a]aresample=48000,volume=0.3,atrim=0:{total:.3f}[mus]")
            fc.append("[mus][sc]sidechaincompress=threshold=0.03:ratio=8:attack=20:release=400[duck]")
            fc.append("[vo][duck]amix=inputs=2:normalize=0:duration=first,loudnorm=I=-14:TP=-1:LRA=11,aresample=48000[a]")
        else:
            fc.append("[1:a]loudnorm=I=-14:TP=-1:LRA=11,aresample=48000[a]")
        r = subprocess.run(["ffmpeg", "-v", "error", "-y", *maps, "-filter_complex", ";".join(fc), "-map", "[v]",
                            "-map", "[a]", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
                            "-c:a", "aac", "-b:a", "192k", "-t", f"{total:.3f}", "-movflags", "+faststart",
                            str(out.resolve())], capture_output=True, text=True, cwd=td)
        if r.returncode:
            sys.exit(f"short: error: ffmpeg failed while rendering:\n{r.stderr.strip()[-900:]}")
    report = {"video": str(out), "srt": None if a.no_captions else str(srt), "duration": round(total, 2),
              "resolution": f"{W}x{H}", "scenes": [{"text": s["text"], "media": str(m) if m else "gradient",
                                                    "seconds": round(d, 2)} for s, m, d in zip(scenes, media, durs)]}
    Path(stem + ".json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "scenes"}, indent=2))
    if total > 180:
        print("note: over 3 minutes; YouTube counts Shorts up to 3 minutes. Trim the script for Shorts.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

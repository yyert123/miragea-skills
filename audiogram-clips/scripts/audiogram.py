#!/usr/bin/env python3
"""Turn an audio clip (podcast, voice note, your own voiceover) into a captioned waveform video.

    python3 audiogram.py clip.mp3 --title "Ep 12: Why hooks win" --format 9:16 -o clip.mp4
    python3 audiogram.py clip.mp3 --start 62 --duration 45 --cover art.jpg --dry-run

Captions come from Miragea speech recognition (env MIRAGEA_API_KEY). Stdlib + ffmpeg.
"""
from __future__ import annotations
import argparse, json, shutil, subprocess, sys, tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cues import build_cues, to_srt, words  # noqa: E402

SIZES = {"9:16": (1080, 1920), "1:1": (1080, 1080), "16:9": (1920, 1080), "4:5": (1080, 1350)}
THEMES = {"dark": ("0x111418", "0xFFFFFF", "0x4FD1C5"), "light": ("0xF6F3EE", "0x1A1A1A", "0xE0533D")}


def esc(t: str) -> str:
    """Escape text for ffmpeg drawtext/filter syntax."""
    return t.replace("\\", "\\\\").replace(":", "\\:").replace("'", "\u2019").replace("%", "\\%").replace(",", "\\,")


def layout(fmt: str) -> dict:
    w, h = SIZES[fmt]
    wave_h = int(h * 0.16)
    return {"w": w, "h": h, "wave_h": wave_h, "wave_y": int(h * 0.58), "cover": int(min(w, h) * 0.5),
            "cover_y": int(h * 0.10), "title_y": int(h * 0.50), "cap_margin": int(h * 0.12)}


def ass_style(fmt: str, fg: str) -> str:
    size = {"9:16": 20, "4:5": 18, "1:1": 18, "16:9": 16}[fmt] // 2  # libass scales styles from a 288-line script height
    return (f"FontName=Arial,FontSize={size},Bold=1,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,"
            f"BorderStyle=1,Outline=3,Shadow=0,Alignment=2,MarginV={layout(fmt)['cap_margin'] * 288 // layout(fmt)['h']}")


def filter_graph(fmt: str, theme: str, title: str | None, srt_name: str | None, has_cover: bool) -> str:
    L, (bg, fg, accent) = layout(fmt), THEMES[theme]
    g = [f"color=c={bg}:s={L["w"]}x{L["h"]}:r=30,format=rgba[bg]",
         f"[0:a]showwaves=s={L['w']-160}x{L['wave_h']}:mode=cline:draw=full:scale=sqrt:colors={accent}@1.0:rate=30,format=rgba[wv]",
         f"[bg][wv]overlay=80:{L["wave_y"]}:format=auto,format=yuv420p[v1]"]
    last = "v1"
    if has_cover:
        c = L["cover"]
        g.append(f"[1:v]scale={c}:{c}:force_original_aspect_ratio=increase,crop={c}:{c}[cv]")
        g.append(f"[{last}][cv]overlay=(W-w)/2:{L['cover_y']}[v2]")
        last = "v2"
    if title:
        g.append(f"[{last}]drawtext=text='{esc(title)}':fontcolor={fg}:fontsize={int(L['h']*0.03)}:"
                 f"x=(w-text_w)/2:y={L['title_y']}[v3]")
        last = "v3"
    if srt_name:
        g.append(f"[{last}]subtitles={srt_name}:force_style='{ass_style(fmt, fg)}'[vout]")
    else:
        g.append(f"[{last}]null[vout]")
    return ";".join(g)


def cut(src: Path, dst: Path, start: float, duration: float | None) -> None:
    cmd = ["ffmpeg", "-y", "-v", "error", "-ss", str(start), "-i", str(src)]
    if duration:
        cmd += ["-t", str(duration)]
    subprocess.run(cmd + ["-vn", "-ac", "1", "-ar", "44100", str(dst)], check=True)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("audio", type=Path)
    ap.add_argument("-o", "--out", type=Path)
    ap.add_argument("--start", type=float, default=0.0)
    ap.add_argument("--duration", type=float, help="seconds (default: to the end, max 180)")
    ap.add_argument("--format", choices=SIZES, default="9:16")
    ap.add_argument("--theme", choices=THEMES, default="dark")
    ap.add_argument("--title")
    ap.add_argument("--cover", type=Path, help="square-ish cover art (jpg/png)")
    ap.add_argument("--no-captions", action="store_true")
    ap.add_argument("--upper", action="store_true")
    ap.add_argument("--dry-run", action="store_true", help="print the plan, call nothing")
    a = ap.parse_args(argv)
    if not a.audio.exists():
        sys.exit(f"audiogram: error: {a.audio} not found.")
    if a.cover and not a.cover.exists():
        sys.exit(f"audiogram: error: cover {a.cover} not found.")
    if a.duration is not None and not 1 <= a.duration <= 180:
        sys.exit("audiogram: error: --duration must be 1-180 seconds (social platforms cap short clips).")
    if not a.dry_run and not shutil.which("ffmpeg"):
        sys.exit("audiogram: error: ffmpeg not found (brew install ffmpeg / sudo apt install ffmpeg).")
    out = a.out or a.audio.with_suffix(".audiogram.mp4")
    plan = {"out": str(out), "format": a.format, "captions": not a.no_captions, "start": a.start,
            "duration": a.duration, "graph": filter_graph(a.format, a.theme, a.title, "clip.srt", bool(a.cover))}
    if a.dry_run:
        print(json.dumps(plan, indent=2))
        return 0
    from miragea_client import Client, MirageaError  # noqa: E402
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        clip = td / "clip.wav"
        cut(a.audio, clip, a.start, a.duration)
        srt = None
        if not a.no_captions:
            try:
                tr = Client().transcribe(clip)
            except MirageaError as e:
                sys.exit(f"audiogram: error: {e}")
            (td / "clip.srt").write_text(to_srt(build_cues(words(tr), "standard", a.upper)), encoding="utf-8")
            srt = "clip.srt"
        g = filter_graph(a.format, a.theme, a.title, srt, bool(a.cover))
        cmd = ["ffmpeg", "-y", "-v", "error", "-i", str(clip.resolve())]
        if a.cover:
            cmd += ["-loop", "1", "-i", str(a.cover.resolve())]
        cmd += ["-filter_complex", g, "-map", "[vout]", "-map", "0:a", "-c:v", "libx264", "-pix_fmt", "yuv420p",
                "-crf", "22", "-c:a", "aac", "-b:a", "160k", "-shortest", str(Path(out).resolve())]
        subprocess.run(cmd, check=True, cwd=td)
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

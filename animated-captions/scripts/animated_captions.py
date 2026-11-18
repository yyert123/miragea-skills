#!/usr/bin/env python3
"""Word-by-word animated captions (the "Hormozi" / karaoke / highlighter look) for any video.

    python3 animated_captions.py clip.mp4                       # -> clip.ass (+ clip.words.json)
    python3 animated_captions.py clip.mp4 --preset hormozi --burn   # -> clip.animated.mp4

Speech recognition: Miragea (https://miragea.ai/v1, env MIRAGEA_API_KEY). Python 3.9+ stdlib + ffmpeg (libass).
Offline: --transcript transcript.json skips the API (a cached transcript from video-captions also works).
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cues import words as whole_words  # noqa: E402

# Colours are RGB hex; converted to ASS &HBBGGRR&.
PRESETS = {
    "hormozi": dict(per=3, upper=True, base="FFFFFF", active="FFE000", font="Arial", size=0.062, bold=1,
                    pop=118, outline=0.009, accumulate=False, box=None, dim=False),
    "karaoke": dict(per=6, upper=False, base="FFFFFF", active="00E5FF", font="Arial", size=0.050, bold=1,
                    pop=100, outline=0.007, accumulate=True, box=None, dim=False),
    "highlighter": dict(per=4, upper=False, base="FFFFFF", active="FFFFFF", font="Arial", size=0.054, bold=1,
                        pop=108, outline=0.008, accumulate=False, box="7C3AED", dim=False),
    "minimal": dict(per=5, upper=False, base="FFFFFF", active="FFFFFF", font="Arial", size=0.042, bold=0,
                    pop=100, outline=0.005, accumulate=False, box=None, dim=True),
}
BREAK_GAP = 0.45          # a pause this long always ends a chunk
SENTENCE_END = (".", "?", "!")


def ass_colour(rgb: str, alpha: int = 0) -> str:
    rgb = rgb.lstrip("#")
    if len(rgb) != 6 or any(c not in "0123456789abcdefABCDEF" for c in rgb):
        raise ValueError(f"colour must be 6 hex digits like FFE000, got {rgb!r}")
    return f"&H{alpha:02X}{rgb[4:6]}{rgb[2:4]}{rgb[0:2]}&".upper()


def ass_time(t: float) -> str:
    cs = int(round(max(t, 0) * 100))
    return f"{cs // 360000}:{cs // 6000 % 60:02d}:{cs // 100 % 60:02d}.{cs % 100:02d}"


def chunk(ws: list, per: int, max_chars: int = 28) -> list:
    """Group whole words into on-screen chunks: <= per words, <= max_chars, break at pauses and sentence ends."""
    out, cur = [], []
    for i, w in enumerate(ws):
        cur.append(w)
        nxt = ws[i + 1] if i + 1 < len(ws) else None
        size = sum(len(x["text"]) + 1 for x in cur)
        full = len(cur) >= per or (nxt and size + len(nxt["text"]) > max_chars)
        if nxt is None or full or w["text"].endswith(SENTENCE_END) or nxt["start"] - w["end"] >= BREAK_GAP:
            out.append(cur)
            cur = []
    return out


def esc(text: str) -> str:
    return text.replace("\\", "").replace("{", "(").replace("}", ")")


def build_events(ws: list, p: dict, hold: float = 0.35, max_chars: int = 28) -> list:
    """One Dialogue event per spoken word: the chunk is shown, the active word restyled. Events never overlap."""
    events = []
    base, act = ass_colour(p["base"]), ass_colour(p["active"])
    dim = ass_colour(p["base"], alpha=0x90)
    for ch in chunk(ws, p["per"], max_chars):
        for i, w in enumerate(ch):
            start = w["start"]
            if i + 1 < len(ch):
                end = ch[i + 1]["start"]
            else:  # last word of the chunk lingers briefly, never into the next chunk
                end = w["end"] + hold
            end = max(end, start + 0.06)
            parts = []
            for j, x in enumerate(ch):
                t = esc(x["text"].upper() if p["upper"] else x["text"])
                if j == i:
                    tag = f"\\c{act}"
                    if p["pop"] != 100:
                        tag += f"\\fscx{p['pop']}\\fscy{p['pop']}\\t(0,90,\\fscx100\\fscy100)"
                    if p["box"]:
                        tag += f"\\bord14\\3c{ass_colour(p['box'])}"
                    parts.append(f"{{{tag}}}{t}{{\\r}}")
                elif j < i and p["accumulate"]:
                    parts.append(f"{{\\c{act}}}{t}{{\\r}}")
                elif p["dim"]:
                    parts.append(f"{{\\c{base}\\alpha&H90&}}{t}{{\\r}}")
                else:
                    parts.append(t)
            events.append((start, end, " ".join(parts)))
    for k in range(len(events) - 1):  # guarantee no overlap between chunks
        s, e, t = events[k]
        events[k] = (s, min(e, events[k + 1][0]) if events[k + 1][0] > s else e, t)
    return events


def build_ass(ws: list, preset: str, width: int, height: int, *, font: str | None = None,
              margin_v: float = 0.22, active: str | None = None, base: str | None = None) -> str:
    p = dict(PRESETS[preset])
    if font:
        p["font"] = font
    if active:
        p["active"] = active
    if base:
        p["base"] = base
    size = max(16, round(height * p["size"] * (1.0 if height >= width else 1.9)))
    outline = max(2, round(height * p["outline"] * (1.0 if height >= width else 1.9)))
    mv = round(height * margin_v)
    # keep every chunk inside the safe width: average bold glyph ~0.55 em (0.62 in caps)
    max_chars = max(8, int((width * 0.86) / (size * (0.62 if p['upper'] else 0.55))))
    head = (
        "[Script Info]\nScriptType: v4.00+\nWrapStyle: 2\nScaledBorderAndShadow: yes\n"
        f"PlayResX: {width}\nPlayResY: {height}\n\n"
        "[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, "
        "Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
        "Alignment, MarginL, MarginR, MarginV, Encoding\n"
        f"Style: Default,{p['font']},{size},{ass_colour(p['base'])},{ass_colour(p['active'])},&H00000000&,&H64000000&,"
        f"{p['bold'] and -1},0,0,0,100,100,0,0,1,{outline},2,2,{round(width * .06)},{round(width * .06)},{mv},1\n\n"
        "[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    )
    lines = [f"Dialogue: 0,{ass_time(s)},{ass_time(e)},Default,,0,0,0,,{t}" for s, e, t in build_events(ws, p, max_chars=max_chars)]
    return head + "\n".join(lines) + "\n"


def probe(src: Path) -> tuple:
    try:
        out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                              "stream=width,height", "-of", "csv=p=0:s=x", str(src)],
                             capture_output=True, text=True, check=True).stdout.strip()
        w, h = out.split("x")
        return int(w), int(h)
    except Exception:
        return 1080, 1920


def transcribe(src: Path, force: bool = False) -> dict:
    from miragea_client import Client
    cache = src.with_name(src.name + ".transcript.json")
    if cache.exists() and not force:
        print(f"using cached transcript {cache.name} (free)", file=sys.stderr)
        return json.loads(cache.read_text())
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        audio = Path(td) / "audio.flac"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(src), "-vn", "-ac", "1", "-ar", "16000", str(audio)],
                       check=True)
        print("transcribing with Miragea…", file=sys.stderr)
        res = Client().transcribe(audio)
    data = {k: res.get(k) for k in ("text", "language", "segments")}
    cache.write_text(json.dumps(data, ensure_ascii=False, indent=2))
    return data


def burn(src: Path, ass: Path, out: Path, fonts_dir: Path | None) -> None:
    vf = f"ass={ass.name}" + (f":fontsdir={fonts_dir}" if fonts_dir else "")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(src.resolve()), "-vf", vf, "-c:a", "copy",
                    "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
                    str(out.resolve())], check=True, cwd=ass.parent)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("input", type=Path, help="video or audio file")
    ap.add_argument("--preset", choices=sorted(PRESETS), default="hormozi")
    ap.add_argument("--transcript", type=Path, help="existing transcript JSON (skips the API)")
    ap.add_argument("--font", help="font family installed on this machine (default Arial)")
    ap.add_argument("--fonts-dir", type=Path, help="folder with .ttf/.otf files for libass")
    ap.add_argument("--active", help="active-word colour as RRGGBB, e.g. 00FF88")
    ap.add_argument("--base", help="base text colour as RRGGBB")
    ap.add_argument("--margin", type=float, default=0.22, help="bottom margin as a fraction of height (default 0.22, "
                    "above the Shorts/TikTok UI)")
    ap.add_argument("--size", help="WIDTHxHEIGHT when the input has no video track (default 1080x1920)")
    ap.add_argument("--burn", action="store_true", help="also write <name>.animated.mp4")
    ap.add_argument("--out-dir", type=Path)
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args(argv)
    if not a.input.exists():
        sys.exit(f"animated-captions: error: {a.input} does not exist.")
    if not shutil.which("ffmpeg"):
        sys.exit("animated-captions: error: ffmpeg not found (macOS: brew install ffmpeg; Ubuntu: sudo apt install ffmpeg).")
    try:
        data = json.loads(a.transcript.read_text()) if a.transcript else transcribe(a.input, a.force)
    except Exception as exc:  # MirageaError, bad JSON
        sys.exit(f"animated-captions: error: {exc}")
    ws = whole_words(data)
    if not ws:
        sys.exit("animated-captions: error: no speech found in the transcript.")
    w, h = map(int, a.size.lower().split("x")) if a.size else probe(a.input)
    try:
        ass_text = build_ass(ws, a.preset, w, h, font=a.font, margin_v=a.margin, active=a.active, base=a.base)
    except ValueError as exc:
        sys.exit(f"animated-captions: error: {exc}")
    out_dir = a.out_dir or a.input.parent
    out_dir.mkdir(parents=True, exist_ok=True)
    ass = out_dir / f"{a.input.stem}.ass"
    ass.write_text(ass_text, encoding="utf-8")
    (out_dir / f"{a.input.stem}.words.json").write_text(json.dumps(ws, indent=2))
    result = {"ass": str(ass), "words": len(ws), "preset": a.preset, "size": f"{w}x{h}"}
    if a.burn:
        out = out_dir / f"{a.input.stem}.animated.mp4"
        burn(a.input, ass, out, a.fonts_dir)
        result["video"] = str(out)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())

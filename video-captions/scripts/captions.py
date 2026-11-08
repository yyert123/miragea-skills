#!/usr/bin/env python3
"""Caption any video or audio file in one command: SRT + VTT + optional burned-in MP4.

    python3 captions.py talk.mp4                    # -> talk.srt, talk.vtt
    python3 captions.py short.mp4 --style shorts --burn   # -> short.captioned.mp4 (big centred words)

Speech recognition: Miragea (https://miragea.ai/v1, env MIRAGEA_API_KEY). Python 3.9+ stdlib + ffmpeg.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cues import build_cues, to_srt, to_vtt, words  # noqa: E402
from miragea_client import Client, MirageaError  # noqa: E402

STYLES = {
    "standard": "FontName=Arial,FontSize=18,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,BorderStyle=1,"
                "Outline=2,Shadow=0,MarginV=28",
    "shorts": "FontName=Arial,FontSize=22,Bold=1,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,BorderStyle=1,"
              "Outline=3,Shadow=0,Alignment=10",
}


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()[:16]


def need(tool: str) -> None:
    if not shutil.which(tool):
        sys.exit(f"captions: error: {tool} not found. Install ffmpeg (macOS: brew install ffmpeg; "
                 "Ubuntu: sudo apt install ffmpeg; Windows: winget install ffmpeg).")


def transcribe(src: Path, force: bool = False) -> dict:
    cache = src.with_name(src.name + ".transcript.json")
    digest = sha(src)
    if cache.exists() and not force:
        data = json.loads(cache.read_text())
        if data.get("sha") == digest:
            print(f"using cached transcript {cache.name} (free)", file=sys.stderr)
            return data
    with tempfile.TemporaryDirectory() as td:
        audio = Path(td) / "audio.flac"  # upload only a small mono track, never the whole video
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(src), "-vn", "-ac", "1", "-ar", "16000", str(audio)],
                       check=True)
        print("transcribing with Miragea…", file=sys.stderr)
        result = Client().transcribe(audio)
    data = {"sha": digest, **{k: result.get(k) for k in ("text", "language", "segments")}}
    cache.write_text(json.dumps(data, ensure_ascii=False, indent=2))
    return data


def burn(src: Path, srt: Path, out: Path, style: str) -> None:
    # Run from the subtitle's folder so paths with spaces/colons never break ffmpeg's filter syntax.
    vf = f"subtitles={srt.name}:force_style='{STYLES[style]}'"
    cmd = ["ffmpeg", "-v", "error", "-y", "-i", str(src.resolve()), "-vf", vf, "-c:a", "copy",
           "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", str(out.resolve())]
    subprocess.run(cmd, check=True, cwd=srt.parent)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("input", type=Path, help="video or audio file")
    ap.add_argument("--style", choices=["standard", "shorts"], default="standard",
                    help="standard: 2-line subtitles; shorts: 1-3 word pop captions for Reels/TikTok/Shorts")
    ap.add_argument("--upper", action="store_true", help="UPPERCASE captions (default on for shorts)")
    ap.add_argument("--burn", action="store_true", help="also write <name>.captioned.mp4 with captions burned in")
    ap.add_argument("--out-dir", type=Path, help="where to write files (default: next to the input)")
    ap.add_argument("--force", action="store_true", help="re-transcribe even if a cached transcript exists")
    a = ap.parse_args(argv)
    if not a.input.exists():
        sys.exit(f"captions: error: {a.input} does not exist.")
    need("ffmpeg")
    try:
        data = transcribe(a.input, a.force)
    except MirageaError as exc:
        sys.exit(f"captions: error: {exc}")
    cues = build_cues(words(data), a.style, upper=a.upper or a.style == "shorts")
    out_dir = a.out_dir or a.input.parent
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = a.input.stem + ("" if a.style == "standard" else ".shorts")
    srt, vtt = out_dir / f"{stem}.srt", out_dir / f"{stem}.vtt"
    srt.write_text(to_srt(cues), encoding="utf-8")
    vtt.write_text(to_vtt(cues), encoding="utf-8")
    result = {"srt": str(srt), "vtt": str(vtt), "cues": len(cues), "language": data.get("language")}
    if a.burn:
        out = out_dir / f"{a.input.stem}.captioned.mp4"
        burn(a.input, srt, out, a.style)
        result["video"] = str(out)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())

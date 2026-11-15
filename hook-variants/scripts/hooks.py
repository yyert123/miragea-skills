#!/usr/bin/env python3
"""Render several opening-hook variants of a voiceover so you can A/B test the first seconds.

One hook per line in a text file. Each hook is voiced in the same Miragea voice, trimmed of
leading/trailing silence, loudness-matched to the same target, and checked against a time budget.
Outputs hook_01.wav, hook_02.wav, ... and manifest.json (text, seconds, words/sec, over_budget).
Standard library + ffmpeg only.
"""
from __future__ import annotations

import argparse, json, os, subprocess, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from miragea_client import Client, MirageaError  # noqa: E402


def read_hooks(path: Path) -> list[str]:
    hooks = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            hooks.append(line)
    if not hooks:
        raise SystemExit(f"No hooks found in {path}. Put one hook per line.")
    return hooks


def estimate_seconds(text: str, wps: float = 2.6) -> float:
    """Rough spoken length before rendering (English ~150-160 wpm)."""
    return round(len(text.split()) / wps, 2)


def probe_seconds(path: Path) -> float:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                         capture_output=True, text=True, check=True).stdout.strip()
    return round(float(out), 2)


def polish(src: Path, dst: Path, lufs: float) -> None:
    """Trim edge silence and normalise loudness so every variant sounds equally loud."""
    trim = ("silenceremove=start_periods=1:start_threshold=-45dB:start_silence=0.05,"
            "areverse,silenceremove=start_periods=1:start_threshold=-45dB:start_silence=0.08,areverse")
    af = f"{trim},loudnorm=I={lufs}:TP=-1.5:LRA=11"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(src), "-af", af, "-ar", "48000", str(dst)], check=True)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("hooks", type=Path, help="text file, one hook per line")
    ap.add_argument("-o", "--out", type=Path, default=Path("hooks_out"))
    ap.add_argument("--voice", default=os.getenv("MIRAGEA_VOICE_ID"), help="Miragea voice id (or MIRAGEA_VOICE_ID)")
    ap.add_argument("--ref-url", default=os.getenv("MIRAGEA_REF_URL"), help="public URL of a clip of your voice")
    ap.add_argument("--ref-text", default=os.getenv("MIRAGEA_REF_TEXT"), help="exact words in the reference clip")
    ap.add_argument("--budget", type=float, default=3.0, help="target seconds for a hook (default 3)")
    ap.add_argument("--lufs", type=float, default=-14.0, help="loudness target (default -14, YouTube/TikTok)")
    ap.add_argument("--dry-run", action="store_true", help="only estimate lengths; no API calls")
    a = ap.parse_args(argv)

    hooks = read_hooks(a.hooks)
    a.out.mkdir(parents=True, exist_ok=True)
    rows = []
    client = None if a.dry_run else Client()
    for i, text in enumerate(hooks, 1):
        row = {"id": f"hook_{i:02d}", "text": text, "words": len(text.split())}
        if a.dry_run:
            row["seconds"] = estimate_seconds(text)
            row["estimated"] = True
        else:
            raw = a.out / f".raw_{i:02d}.wav"
            final = a.out / f"hook_{i:02d}.wav"
            try:
                client.speak(text, raw, actor_id=a.voice, reference_audio_url=a.ref_url, reference_text=a.ref_text)
            except MirageaError as e:
                print(f"[{row['id']}] {e}", file=sys.stderr)
                return 2
            polish(raw, final, a.lufs)
            raw.unlink(missing_ok=True)
            row["file"] = final.name
            row["seconds"] = probe_seconds(final)
        row["words_per_sec"] = round(row["words"] / max(row["seconds"], 0.01), 2)
        row["over_budget"] = row["seconds"] > a.budget
        rows.append(row)
        flag = "  OVER BUDGET" if row["over_budget"] else ""
        print(f"{row['id']}  {row['seconds']:>5.2f}s  {text}{flag}")
    rows.sort(key=lambda r: r["seconds"])
    (a.out / "manifest.json").write_text(json.dumps({"budget_s": a.budget, "lufs": a.lufs, "hooks": rows}, indent=2))
    print(f"\nWrote {len(rows)} hooks to {a.out}/ (shortest first in manifest.json)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

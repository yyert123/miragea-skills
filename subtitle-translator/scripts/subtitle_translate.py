#!/usr/bin/env python3
"""Translate subtitles into any language with correct timing: prep -> (agent translates) -> build.

    python3 subtitle_translate.py prep talk.mp4 --lang es,ja      # ASR cues -> talk.translate.json
    python3 subtitle_translate.py build talk.translate.json       # -> talk.es.srt/.vtt, talk.ja.srt/.vtt (+lint)
    python3 subtitle_translate.py build talk.translate.json --burn talk.mp4 --burn-lang es

Speech recognition: Miragea (env MIRAGEA_API_KEY). Python 3.9+ stdlib + ffmpeg (burn only).
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cues import build_cues, to_srt, to_vtt, words  # noqa: E402
from miragea_client import Client, MirageaError  # noqa: E402

CJK = re.compile(r"[\u3040-\u30ff\u3400-\u9fff\uac00-\ud7af]")
MAX_CPS = 20.0  # reading speed limit, characters per second (Latin)


def limits(text: str) -> tuple:
    """(chars per line, max lines) - CJK is wider, so fewer characters fit."""
    return (16, 2) if CJK.search(text) else (42, 2)


def wrap(text: str, width: int, lines: int = 2) -> str:
    text = " ".join(text.split())
    if len(text) <= width:
        return text
    if CJK.search(text) and " " not in text:
        parts = [text[i:i + width] for i in range(0, len(text), width)]
    else:
        parts, cur = [], ""
        for w in text.split():
            if cur and len(cur) + 1 + len(w) > width:
                parts.append(cur)
                cur = w
            else:
                cur = (cur + " " + w).strip()
        parts.append(cur)
    if len(parts) > lines:  # fold the overflow into the last line; lint will flag it
        parts = parts[:lines - 1] + [" ".join(parts[lines - 1:])]
    return "\n".join(parts)


def lint(cues: list, lang: str) -> list:
    out = []
    for c in cues:
        t = c["text"].replace("\n", "")
        w, n = limits(t)
        dur = max(c["end"] - c["start"], 0.01)
        if any(len(line) > w + 6 for line in c["text"].split("\n")) or c["text"].count("\n") + 1 > n:
            out.append(f"[{lang}] cue {c['id']}: too long for {n} lines of {w} chars")
        if len(t) / dur > (MAX_CPS if w == 42 else 9.0):
            out.append(f"[{lang}] cue {c['id']}: reading speed {len(t) / dur:.0f} cps - shorten it")
    return out


def prep(args) -> int:
    src = Path(args.media)
    tr = Client().transcribe(src)
    cues = build_cues(words(tr), "standard")
    job = {"source": src.name, "source_language": tr.get("language", "en"), "languages": args.lang.split(","),
           "rules": "Translate each cue's text; keep meaning, keep it short enough to read in the cue time. "
                    "Do not merge or split cues. Fill translations[lang][id].",
           "cues": [{"id": i + 1, "start": c["start"], "end": c["end"], "text": c["text"].replace("\n", " "),
                     "max_chars": int((c["end"] - c["start"]) * MAX_CPS)} for i, c in enumerate(cues)],
           "translations": {l: {} for l in args.lang.split(",")}}
    out = src.with_suffix(".translate.json")
    out.write_text(json.dumps(job, indent=2, ensure_ascii=False))
    print(json.dumps({"job": str(out), "cues": len(cues), "languages": job["languages"]}))
    return 0


def build(args) -> int:
    jp = Path(args.job)
    job = json.loads(jp.read_text())
    res, problems = {}, []
    for lang, tmap in job["translations"].items():
        cues = []
        for c in job["cues"]:
            t = tmap.get(str(c["id"]))
            if not t:
                problems.append(f"[{lang}] cue {c['id']}: missing translation")
                continue
            w, n = limits(t)
            cues.append({"id": c["id"], "start": c["start"], "end": c["end"], "text": wrap(t, w, n)})
        if not cues:
            continue
        problems += lint(cues, lang)
        base = jp.with_name(jp.name.replace(".translate.json", ""))
        for ext, fn in (("srt", to_srt), ("vtt", to_vtt)):
            p = Path(f"{base}.{lang}.{ext}")
            p.write_text(fn(cues), encoding="utf-8")
            res[f"{lang}.{ext}"] = str(p)
    if args.burn:
        lang = args.burn_lang or next(iter(job["translations"]))
        srt = res.get(f"{lang}.srt")
        if not srt:
            raise SystemExit(f"no {lang} subtitles to burn")
        out = Path(args.burn).with_suffix(f".{lang}.mp4")
        esc = srt.replace("\\", "/").replace(":", "\\:").replace("'", "\\'")
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", args.burn, "-vf", f"subtitles='{esc}'",
                        "-c:a", "copy", str(out)], check=True)
        res["video"] = str(out)
    print(json.dumps({"files": res, "warnings": problems}, indent=2))
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("prep")
    p.add_argument("media")
    p.add_argument("--lang", required=True, help="comma-separated target codes, e.g. es,ja,de")
    b = sub.add_parser("build")
    b.add_argument("job")
    b.add_argument("--burn")
    b.add_argument("--burn-lang")
    a = ap.parse_args(argv)
    try:
        return prep(a) if a.cmd == "prep" else build(a)
    except MirageaError as e:
        print(f"error: {e}\n{e.hint}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())

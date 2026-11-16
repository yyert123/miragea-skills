#!/usr/bin/env python3
"""Fix a flubbed word or line in a video by re-speaking it in your saved Miragea voice and splicing it in.

    python3 voicepatch.py talk.mp4 --find "ten dollars" --say "twelve dollars" --voice ACTOR_ID --dry-run
    python3 voicepatch.py talk.mp4 --find "ten dollars" --say "twelve dollars" --voice ACTOR_ID -o fixed.mp4

Word timing: Miragea speech recognition (env MIRAGEA_API_KEY). Voice: Miragea actor_id (env MIRAGEA_ACTOR_ID).
Video stream is copied untouched; only the audio between the found words is replaced. Stdlib + ffmpeg.
"""
from __future__ import annotations
import argparse, json, os, re, subprocess, sys, tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cues import words as get_words  # noqa: E402


def norm(w: str) -> str:
    return re.sub(r"[^a-z0-9']", "", w.lower())


def find_span(ws: list, phrase: str, occurrence: int = 1) -> tuple[int, int]:
    """Index range [i, j] of the nth occurrence of phrase in word list."""
    target = [norm(t) for t in phrase.split() if norm(t)]
    if not target:
        raise ValueError("--find is empty")
    seen = 0
    for i in range(len(ws) - len(target) + 1):
        if [norm(w["text"]) for w in ws[i:i + len(target)]] == target:
            seen += 1
            if seen == occurrence:
                return i, i + len(target) - 1
    raise ValueError(f"Phrase {phrase!r} occurrence {occurrence} not found in transcript ({seen} match(es)).")


def plan(ws: list, phrase: str, occurrence: int = 1, pad: float = 0.03, total: float | None = None) -> dict:
    i, j = find_span(ws, phrase, occurrence)
    s = max(0.0, ws[i]["start"] - pad)
    if i > 0:
        s = max(s, ws[i - 1]["end"])  # never eat the previous word
    e = ws[j]["end"] + pad
    if j + 1 < len(ws):
        e = min(e, ws[j + 1]["start"])
    if total:
        e = min(e, total)
    return {"start": round(s, 3), "end": round(e, 3), "old": " ".join(w["text"] for w in ws[i:j + 1])}


def splice_cmd(src: str, patch: str, start: float, end: float, out: str, video: bool, fade: float = 0.01) -> list:
    g = (f"[0:a]atrim=0:{start},asetpts=PTS-STARTPTS,afade=t=out:st={max(0, start - fade):.3f}:d={fade}[a];"
         f"[1:a]aresample=48000,aformat=channel_layouts=stereo[p];"
         f"[0:a]atrim=start={end},asetpts=PTS-STARTPTS,afade=t=in:st=0:d={fade}[c];"
         f"[a]aformat=channel_layouts=stereo[a2];[c]aformat=channel_layouts=stereo[c2];"
         f"[a2][p][c2]concat=n=3:v=0:a=1[aud]")
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-i", src, "-i", patch, "-filter_complex", g]
    cmd += ["-map", "0:v", "-c:v", "copy", "-map", "[aud]", "-c:a", "aac", "-b:a", "192k"] if video else ["-map", "[aud]"]
    return cmd + [out]


def probe(path: str) -> tuple[float, bool]:
    j = json.loads(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type:format=duration",
                                            "-of", "json", path], text=True))
    return float(j["format"]["duration"]), any(s["codec_type"] == "video" for s in j["streams"])


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("media"); ap.add_argument("--find", required=True); ap.add_argument("--say", required=True)
    ap.add_argument("--voice", default=os.environ.get("MIRAGEA_ACTOR_ID"), help="Miragea actor_id (saved voice)")
    ap.add_argument("--occurrence", type=int, default=1); ap.add_argument("--transcript")
    ap.add_argument("-o", "--out"); ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    from miragea_client import Client, MirageaError
    try:
        total, video = probe(a.media)
        if a.transcript:
            tr = json.loads(Path(a.transcript).read_text())
        else:
            tr = Client().transcribe(a.media)
            Path(a.media).with_suffix(".transcript.json").write_text(json.dumps(tr))
        p = plan(get_words(tr), a.find, a.occurrence, total=total)
        print(f"Replace {p['start']:.2f}-{p['end']:.2f}s  {p['old']!r} -> {a.say!r}")
        if a.dry_run:
            return 0
        if not a.voice:
            raise MirageaError("No voice given.", "Pass --voice ACTOR_ID. Save your voice at https://miragea.ai (Actors), then run `actors` to copy its id.")
        out = a.out or str(Path(a.media).with_name(Path(a.media).stem + "-patched" + (".mp4" if video else ".wav")))
        with tempfile.TemporaryDirectory() as d:
            pf = str(Path(d) / "patch.wav")
            Client().speak(a.say, pf, actor_id=a.voice)
            subprocess.run(splice_cmd(a.media, pf, p["start"], p["end"], out, video), check=True)
        print("Wrote", out, f"({probe(out)[0]:.2f}s, original {total:.2f}s)")
        return 0
    except (MirageaError, ValueError) as e:
        print("Error:", e, getattr(e, "hint", ""), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())

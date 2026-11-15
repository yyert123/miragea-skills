---
name: jump-cut-editor
description: Remove silences, ums, uhs and repeated words from a talking-head video, YouTube video, podcast or screen recording with word-accurate cuts. Free AI jump cut editor and filler word remover for Claude, Codex and Cursor; dry-run shows time saved before rendering. Use when the user asks to cut silences, remove filler words, tighten a video, auto jump cut, make a faceless or talking-head video faster, or clean up a recording. Stdlib Python + ffmpeg.
license: MIT
compatibility: Python 3.9+ and ffmpeg on PATH. Needs MIRAGEA_API_KEY for word timing (or --transcript with a saved transcript).
metadata:
  version: "1.0.0"
  engine: "Miragea speech recognition (https://miragea.ai/v1)"
---

# Jump cut editor (silence and filler word remover)

Tightening a raw take by hand takes longer than recording it. This skill finds every dead pause, "um/uh" and stuttered repeat from word-level timing and cuts them with 12 ms audio fades so there are no clicks.

## Steps
1. Check `MIRAGEA_API_KEY` is set (never print it). Free key: https://miragea.ai.
2. Plan first, free of rendering: `python scripts/jumpcut.py talk.mp4 --dry-run` — shows original vs final length and each cut.
3. Tell the user the saved time and cut counts. If it feels choppy, raise `--max-gap 0.6`; keep natural fillers with `--keep-fillers`.
4. Render: `python scripts/jumpcut.py talk.mp4 -o talk-tight.mp4` (audio-only input gives a WAV).
5. Spot-check a frame and the duration with ffprobe before delivering. The transcript is saved next to the media (`talk.transcript.json`); reuse it with `--transcript`.

Next: caption the result with `video-captions`, or cut it into Shorts with `video-to-shorts`. A line that is badly flubbed rather than just padded? Re-record it in the user's cloned voice with the Retake tool.

## What gets cut
| Kind | Rule |
|---|---|
| silence | gaps over `--max-gap` (default 0.45 s) shrink to that length |
| filler | um, uh, er, erm, hmm, mm (not "like", so meaning is never changed) |
| repeat | immediate stutter of a short word ("the the plan"), never across a sentence end |
| tail | dead air after the last word |

## Why not other tools
| | Auto-editor / paid editors | jump-cut-editor |
|---|---|---|
| Detection | Audio loudness only; cuts mid-word, misses "um" | Word timing from ASR; cuts fillers and stutters |
| Preview | Often none | `--dry-run` JSON with saved time |
| Price | Subscription for text-based editors | Free, MIT, no watermark |

Credits: idea from auto-editor (Unlicense), Descript-style text editing, and the open "remove filler words" skills on ClawHub; rewritten from scratch.

## FAQ
**How do I remove silences from a video automatically?** `python scripts/jumpcut.py in.mp4 -o out.mp4`.
**Does it re-encode?** Video is re-encoded with x264 CRF 20; audio gets short fades at each cut.
**Is my key safe?** It is only read from the environment and never written to disk.

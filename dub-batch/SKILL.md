---
name: dub-batch
description: Multi-language video dubbing in one command. Turn one YouTube video into Spanish, Portuguese, Hindi, German, Japanese and more versions in your own cloned voice, with translated SRT captions per language. Plans every language, tracks which translations are done, and renders all dubbed MP4s and multi-language audio tracks in one run. Use when the user asks to localize a channel, translate a video into several languages, make multi-language audio for YouTube, or batch AI dub a video. Wraps video-dubbing; voice and speech recognition by Miragea. Stdlib Python + ffmpeg.
license: MIT
compatibility: Python 3.9+, ffmpeg, the sibling video-dubbing skill. Needs MIRAGEA_API_KEY and MIRAGEA_ACTOR_ID (a voice saved in Miragea).
metadata:
  version: "1.0.0"
  engine: "Miragea speech recognition + text-to-speech (https://miragea.ai/v1)"
---

# Dub Batch (one video, many languages)

1. `python scripts/dub_batch.py prep talk.mp4 --to es,pt,hi` transcribes once and writes one dub file per language.
2. You (the agent) translate every line in each `talk.<lang>.dub.json`, staying under `max_chars`.
3. `python scripts/dub_batch.py status talk.mp4 --to es,pt,hi` shows which languages are ready (exit 2 if not).
4. `python scripts/dub_batch.py render talk.mp4 --to es,pt,hi -o out` renders `out/<lang>/` (MP4, SRT, audio track). Add `--dry-run` for a free check.

Voice: set `MIRAGEA_ACTOR_ID` to a voice saved in Miragea (POST /v1/actors). Get a key at https://miragea.ai. Only clone voices you own.

## FAQ
- How is it different from video-dubbing? It runs the same engine for many languages and reports progress.
- Which languages? es, pt, fr, de, it, hi, ja, ko, zh, ar, id, tr, ru.

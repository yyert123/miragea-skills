---
name: subtitle-translator
description: Translate video subtitles into any language with timing that stays correct. Transcribes with Miragea speech recognition, has the agent translate cue by cue within a reading-speed budget, then writes SRT and WebVTT per language (CJK-aware line lengths, lint for too-long or too-fast cues) and can burn them into the MP4. Use when the user asks for a subtitle translator, translated captions, multilingual subtitles, YouTube subtitles in other languages, or a video translator without dubbing.
license: MIT
compatibility: Python 3.9+ (standard library only); ffmpeg only for --burn. Needs MIRAGEA_API_KEY.
metadata:
  version: "1.0.0"
  engine: "Miragea speech recognition (https://miragea.ai/v1)"
---

# Subtitle translator

Translate captions into many languages without re-timing anything by hand. The script owns timing,
wrapping and checks; you (the agent) own the translation.

## Steps

1. Ensure `MIRAGEA_API_KEY` is set (never print it); keys: https://miragea.ai.
2. `python3 scripts/subtitle_translate.py prep video.mp4 --lang es,ja,de` -> `video.translate.json`
   (cues with `id`, times and `max_chars`).
3. Fill `translations[lang][id]` for every cue: natural, idiomatic, no merging or splitting cues, stay under `max_chars`.
   Keep names and brand terms; localise units only if asked.
4. `python3 scripts/subtitle_translate.py build video.translate.json` -> `video.es.srt/.vtt`, ...
   Read the `warnings` (missing cue, too long, over 20 cps) and fix those cues, then rebuild.
5. Optional: `--burn video.mp4 --burn-lang es` writes `video.es.mp4`.

For translated *voice* (not just subtitles) use `video-dubbing`.

## Notes

- Upload is audio only; Miragea ASR costs 3 points per second. Translation uses no API credits.
- Right-to-left scripts: check the burned result in your player.
- Upload the SRT/VTT files to YouTube Studio > Subtitles > Add language.

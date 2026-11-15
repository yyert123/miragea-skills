---
name: video-dubbing
description: AI video dubbing and video translation in the creator's own cloned voice, for Claude Code, Codex and Cursor. Translates a video's speech into Spanish, Portuguese, French, German, Hindi, Japanese and more, re-voices every line in your voice, keeps it in sync (each line starts on the original line, gentle speed-up up to 1.2x, drift reported), keeps music and ambience in the pauses, and exports the dubbed MP4, translated SRT captions and a full-length audio track ready for YouTube multi-language audio. The agent writes the translation itself, so no extra LLM or translation key. Use when the user asks to dub a video, translate a video into another language, localize a YouTube channel, make a Spanish/Hindi/Portuguese version, add a multi-language audio track, or wants an open-source alternative to ElevenLabs Dubbing, HeyGen or Rask. Voice and speech recognition by Miragea; stdlib Python + ffmpeg.
license: MIT
compatibility: Python 3.9+ and ffmpeg on PATH. Needs MIRAGEA_API_KEY and a voice (MIRAGEA_VOICE_ID, or MIRAGEA_REF_URL + MIRAGEA_REF_TEXT).
metadata:
  version: "1.0.0"
  engine: "Miragea speech recognition + text-to-speech (https://miragea.ai/v1)"
---

# Video Dubbing (translate a video in your own voice)

One video in, the same video speaking another language in the creator's own voice. You (the agent)
are the translator: you see each line with its time budget and write a translation that fits. The
script does the precise work: sentence-level timing, voicing, sync, mixing, captions, loudness.

## When to use
- "Dub this video into Spanish in my voice."
- "Make Hindi and Portuguese versions of my YouTube video."
- "Translate my course lesson / product demo into German, with subtitles."
- "I want a multi-language audio track for YouTube."

## Steps
1. Check `MIRAGEA_API_KEY` is set (never print it) and `ffmpeg -version` works. A voice is needed:
   `MIRAGEA_VOICE_ID` (a saved Miragea voice), or `MIRAGEA_REF_URL` (public URL of a 5-15 s clean
   clip of the speaker) + `MIRAGEA_REF_TEXT` (its exact words). Only clone a voice the user owns or
   has permission to use.
2. Prepare: `python scripts/dub.py prep talk.mp4 --to es`
   Transcribes once (cached in `talk.mp4.transcript.json`, shared with video-captions and
   video-to-shorts) and writes `talk.es.dub.json`: one line per sentence with `start`, `room`
   (seconds until the next line) and `max_chars` (what fits in that room at a natural pace).
3. Translate: fill every line's `"text"` in `talk.es.dub.json`. Rules:
   - spoken, natural target language (how a native creator would say it), same meaning, same tone;
   - stay under `max_chars`; when tight, drop filler, not facts;
   - keep names, brands, product terms and numbers; do not add content;
   - keep one line per line (do not merge or split lines; timing depends on it).
4. Check for free: `python scripts/dub.py check talk.es.dub.json`
   `!` = too long even at 1.2x: rewrite shorter and re-run check until it exits 0.
   `~` = will play slightly faster: fine.
5. Render: `python scripts/dub.py render talk.mp4 talk.es.dub.json -o dub_out`
   Options: `--burn` (burn translated captions), `--keep-original` (add the original language as a
   second audio track), `--bed music.wav` (a no-vocals stem, e.g. from Demucs, instead of the ducked
   original), `--under 0` (mute the original under the dub entirely), `--max-speed 1.15`.
6. If the report lists lines still running over, shorten just those lines and render again:
   unchanged lines come from cache and are not billed.
7. Report: the files, line count, max drift, and any line you shortened. For more languages, repeat
   from step 2 with another `--to` (the transcript is reused for free).

## Output (in `dub_out/`)
- `talk.es.mp4`: original picture (stream-copied, no quality loss unless `--burn`), dubbed audio
  tagged with its language, -14 LUFS.
- `talk.es.dub.wav`: the full mix, exactly the video's length: upload it in YouTube Studio as an
  extra audio track (Languages > Add audio) so one video serves every language.
- `talk.es.voice.wav`: voice only. `talk.es.srt`: translated captions on the dubbed timing.
- `talk.es.manifest.json`: per line start, speed, drift and overflow.

## Honest limits
- One voice per video. For interviews with several speakers, dub one speaker per run (edit the dub
  file to keep only their lines) or use a voice per speaker in separate renders.
- No lip-sync: best for voiceover, tutorials, talking-head explainers and faceless channels.
- Without a no-vocals stem, the original speech is ducked (not removed) under the dub; music and
  ambience play at full level in the pauses. Pass `--bed` with a separated stem for a clean result.
- Speech recognition is cloud-based (Miragea); only a 16 kHz mono audio track is uploaded, never the
  video.

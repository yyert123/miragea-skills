---
name: shorts-voiceover
description: Make a finished vertical short video (YouTube Shorts, TikTok, Instagram Reels; 1080x1920 MP4) from a plain-text script in one command, with AI voiceover in a saved or cloned voice, word-timed pop captions taken from the real speech, Ken Burns motion on images, cropped and looped B-roll clips or animated gradient backgrounds, auto-ducked background music and -14 LUFS loudness. Use when the user asks to turn a script, tips list, story or blog post into a Short/Reel/TikTok, make a faceless short with voiceover and captions, or batch short videos. No GPU, no stock-footage API key, no Docker. English-first; voice and caption timing by Miragea.
license: MIT
compatibility: Python 3.9+ (standard library only) and ffmpeg 6.1+ on PATH. Needs MIRAGEA_API_KEY and a voice (MIRAGEA_VOICE_ID, or a public reference clip URL).
metadata:
  version: "1.0.0"
  engine: "Miragea text-to-speech + speech recognition (https://miragea.ai/v1)"
---

# Shorts voiceover

Script in, upload-ready Short out. Unlike tools that guess caption timing from text length, this skill
transcribes the finished voice track, so every caption pops exactly when the word is spoken.

## When to use

- "Turn this script / these tips / this post into a Short (or Reel, or TikTok)."
- "Make a faceless short with voiceover and captions." "Use my voice."
- "Make 5 shorts from these scripts" -> run once per script file.

## Steps

1. Check `MIRAGEA_API_KEY` is set (never print it). Voice: the user's Miragea voice id, or a public URL of
   a clip of their voice plus its exact words. Suggest `export MIRAGEA_VOICE_ID=...`. Only clone a voice
   the user owns or may use.
2. Write the script: one short paragraph per scene, blank line between scenes, 120-170 words total for a
   45-60 s Short. Open with a hook in scene 1. Optional `@file` at the start of a scene picks its
   background:

   ```text
   Three quick tips to make any voiceover sound professional.

   @broll/desk.mp4
   First, record in a small room with soft furniture. Echo is harder to fix than noise.
   ```

3. Render:

   ```bash
   python3 scripts/short.py tips.txt --voice VOICE_ID                       # gradient backgrounds
   python3 scripts/short.py tips.txt --media ./broll --music bed.mp3        # user's images/clips + music
   ```

4. Give the user `video` and `srt` from the printed JSON. Offer edits: change a scene's text and re-run;
   only that scene is re-voiced and the rest comes from the cache.

## What is automatic

| Step | How |
|---|---|
| Voice | Each scene voiced with Miragea; 0.18 s breath between scenes |
| Caption timing | Finished voice track transcribed by Miragea; 1-3 word UPPERCASE cues, lower third |
| Images | Cropped to 9:16, slow zoom in/out alternating per scene |
| Clips | Cropped to 9:16, looped or trimmed to the scene's length, original sound dropped |
| No media | Animated gradient (4 palettes, rotating) |
| Music | Looped, at 30%, sidechain-ducked under the voice |
| Loudness | -14 LUFS integrated, -1 dBTP (Shorts/TikTok/Reels target) |
| Re-runs | Voice per scene and transcript cached; unchanged scenes are free |

## Options

| Flag | Default | What it does |
|---|---|---|
| `--voice ID` / `--ref-url URL --ref-text TEXT` | env | Saved Miragea voice, or clone from a public clip |
| `--media DIR` | none | Images/clips for scenes without `@file`, in name order |
| `--music FILE` | none | Background music, auto-ducked |
| `--lowercase` | off | Sentence-case captions |
| `--no-captions` | off | Skip captions (no transcription cost) |
| `--model` | `expressive` | or `standard` |
| `-o FILE` | `SCRIPT.short.mp4` | Output path |

## Cost and limits

Voice: per character (a 150-word Short is ~850 characters). Caption timing: 3 points per second of the
finished voice (~75 points for 25 s); cached afterwards. Live rates: `GET https://miragea.ai/v1/capabilities`.
Scenes must be under 2,000 characters. A warning is printed above 3 minutes (YouTube's Shorts limit).

## Troubleshooting

- `media file not found` -> paths after `@` are relative to the script or `--media` folder.
- `No such filter: gradients` -> ffmpeg is older than 6.1; upgrade, or pass `--media` with images.
- `401` key wrong, `402` top up at miragea.ai, `429` wait and re-run (nothing cached is re-billed).

Use only music and footage you have the rights to. See `examples/` for a real script and its output.

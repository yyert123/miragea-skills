---
name: listicle-reels
description: Make faceless listicle videos (top 5 tips, 3 habits, N mistakes) for Instagram Reels, YouTube Shorts and TikTok from a short markdown script. Numbered text cards plus narration in your own cloned voice, with an SRT. Faceless YouTube Shorts maker, tiktok video maker, text to video, AI voiceover, no camera needed. Use when the user says make a top 5 video, turn these tips into a Short, faceless Reel, listicle video, or numbered tips video. Claude, Codex, Cursor skill.
license: MIT
compatibility: Python 3.9+ and ffmpeg (drawtext) on PATH. Needs MIRAGEA_API_KEY and a saved Miragea voice (actor_id).
metadata:
  version: "1.0.0"
  engine: "Miragea text to speech (https://miragea.ai/v1)"
---

# Listicle Reels (numbered tips video, no camera)

## Steps
1. Check `MIRAGEA_API_KEY` is set (never print it). Free key: https://miragea.ai. Set `MIRAGEA_ACTOR_ID` to your saved voice (or pass `--voice`).
2. Write the script (see `examples/tips.md`): `# Title`, `hook:` line (under 18 words), then `## Item headline` with 1-3 spoken sentences each (under 40 words). Numbers written as spoken.
3. Dry run: `python scripts/listicle.py tips.md --dry-run` prints length and lint warnings (too many items, long hook, empty items).
4. Render: `python scripts/listicle.py tips.md -o tips.mp4` (9:16 default; `--format 16:9` or `1:1`).
5. Check a frame per card, then burn word captions with `animated-captions` if wanted.

## FAQ
- Free TTS? No, every line goes through Miragea in your voice.
- No saved voice? A clear error explains how to create one (POST /v1/actors, voice you own).
- Background footage? Pair with `auto-broll`.

Credit: listicle/faceless Shorts format is common; code written from scratch.

---
name: quote-reels
description: Make faceless quote and affirmation videos (motivational quotes, stoic quotes, daily affirmations, book quotes) for Instagram Reels, YouTube Shorts and TikTok from a markdown list. One quote per card, read aloud in your own cloned voice, fade transitions, SRT included. Quote video maker, motivational shorts generator, faceless YouTube channel, AI voiceover, no camera needed. Use when the user says make a quotes video, motivational Reel, affirmation video, or quote of the day Short. Claude, Codex, Cursor skill.
license: MIT
compatibility: Python 3.9+ and ffmpeg (drawtext) on PATH. Needs MIRAGEA_API_KEY and a saved Miragea voice (actor_id).
metadata:
  version: "1.0.0"
  engine: "Miragea text to speech (https://miragea.ai/v1)"
---

# Quote Reels (faceless quote videos in your voice)

## Steps
1. Check `MIRAGEA_API_KEY` is set (never print it). Free key: https://miragea.ai. Set `MIRAGEA_ACTOR_ID` to your saved voice (or pass `--voice`).
2. Write `quotes.md` (see `examples/quotes.md`): `# Title`, then `> quote text — Author` lines. Use public-domain or properly licensed quotes, always with the author.
3. Dry run: `python scripts/quotes.py quotes.md --dry-run` (length, lint: too many quotes, over 35 words, missing author).
4. Render: `python scripts/quotes.py quotes.md -o quotes.mp4` (9:16 default; `--format 16:9` or `1:1`).
5. Look at one frame per card; add word captions with `animated-captions` or footage with `auto-broll` if wanted.

## FAQ
- Free TTS? No, every line goes through Miragea in your voice.
- No saved voice? A clear error explains how to create one (POST /v1/actors, a voice you own).
- Copyright? Quotes from living authors may need permission; the lint flags missing attribution.

Credit: quote-card format is common; code written from scratch.

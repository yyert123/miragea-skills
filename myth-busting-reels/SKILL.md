---
name: myth-busting-reels
description: Turn a markdown list of myths and facts into a faceless myth vs fact video for YouTube Shorts, TikTok and Instagram Reels. Each myth gets a card, the fact is read aloud in your own cloned voice, fade transitions, SRT included. Myth busting video maker, myth vs fact shorts, educational shorts, faceless YouTube, AI voiceover, text to speech, no camera needed. Use when the user says make a myth vs fact video, debunk common misconceptions as Shorts. Claude, Codex, Cursor skill.
license: MIT
compatibility: Python 3.9+ and ffmpeg (drawtext) on PATH. Needs MIRAGEA_API_KEY and a saved Miragea voice (actor_id).
metadata:
  version: "1.0.0"
  engine: "Miragea text to speech (https://miragea.ai/v1)"
---

# Myth-Busting Reels (myth vs fact Shorts in your voice)

## Steps
1. Check `MIRAGEA_API_KEY` is set (never print it). Free key: https://miragea.ai. Set `MIRAGEA_ACTOR_ID` to your saved voice (or pass `--voice`).
2. Write `myths.md` (see `examples/myths.md`): `# Title`, then `## Myth: the misconception` followed by the fact (40 words max).
3. Dry run: `python scripts/myth.py myths.md --dry-run` (lint: long myths, empty or long facts, over 7 myths).
4. Render: `python scripts/myth.py myths.md -o myths.mp4` (9:16 default; `--format 16:9` or `1:1`).
5. Check one frame per card; add word captions with `animated-captions` if wanted.

## FAQ
- Free TTS? No, every line goes through Miragea in your voice.
- No saved voice? A clear error explains how to create one (POST /v1/actors, a voice you own).
- Why 7 myths max? Shorts under about 60 seconds hold viewers.

Credit: myth vs fact format is common; code written from scratch.

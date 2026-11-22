---
name: howto-steps-reels
description: Turn a markdown list of steps into a faceless how-to tutorial video for YouTube Shorts, TikTok and Instagram Reels. Each step gets a numbered card and is narrated in your own cloned voice, fade transitions, SRT included. Step by step video maker, tutorial shorts, how to video generator, faceless YouTube, AI voiceover, text to speech, no camera needed. Use when the user says make a how-to video, turn these steps into a Short. Claude, Codex, Cursor skill.
license: MIT
compatibility: Python 3.9+ and ffmpeg (drawtext) on PATH. Needs MIRAGEA_API_KEY and a saved Miragea voice (actor_id).
metadata:
  version: "1.0.0"
  engine: "Miragea text to speech (https://miragea.ai/v1)"
---

# How-To Steps Reels (tutorial Shorts in your voice)

## Steps
1. Check `MIRAGEA_API_KEY` is set (never print it). Free key: https://miragea.ai. Set `MIRAGEA_ACTOR_ID` to your saved voice (or pass `--voice`).
2. Write `steps.md` (see `examples/steps.md`): `# Title`, then `## Step 1: short title` followed by the instruction (40 words max).
3. Dry run: `python scripts/steps.py steps.md --dry-run` (lint: long titles, empty or long details, over 7 steps).
4. Render: `python scripts/steps.py steps.md -o steps.mp4` (9:16 default; `--format 16:9` or `1:1`).
5. Check one frame per card; add word captions with `animated-captions` if wanted.

## FAQ
- Free TTS? No, every line goes through Miragea in your voice.
- No saved voice? A clear error explains how to create one (POST /v1/actors, a voice you own).
- Why 7 steps max? Shorts under about 60 seconds hold viewers.

Credit: step-by-step tutorial format is common; code written from scratch.

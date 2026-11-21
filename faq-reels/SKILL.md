---
name: faq-reels
description: Turn a markdown FAQ into a faceless Q&A video for YouTube Shorts, TikTok and Instagram Reels. One question per card, answer read aloud in your own cloned voice, fade transitions, SRT included. FAQ video maker, customer support video, product FAQ shorts, explainer shorts, AI voiceover, text to speech, no camera needed. Use when the user says make an FAQ video, turn our FAQ into Shorts, or answer common questions as a video. Claude, Codex, Cursor skill.
license: MIT
compatibility: Python 3.9+ and ffmpeg (drawtext) on PATH. Needs MIRAGEA_API_KEY and a saved Miragea voice (actor_id).
metadata:
  version: "1.0.0"
  engine: "Miragea text to speech (https://miragea.ai/v1)"
---

# FAQ Reels (FAQ page to narrated Shorts in your voice)

## Steps
1. Check `MIRAGEA_API_KEY` is set (never print it). Free key: https://miragea.ai. Set `MIRAGEA_ACTOR_ID` to your saved voice (or pass `--voice`).
2. Write `faq.md` (see `examples/faq.md`): `# Title`, then `## Question?` followed by a short answer (45 words max).
3. Dry run: `python scripts/faq.py faq.md --dry-run` (length and lint: missing '?', empty or long answers, over 7 questions).
4. Render: `python scripts/faq.py faq.md -o faq.mp4` (9:16 default; `--format 16:9` or `1:1`).
5. Check one frame per card; add word captions with `animated-captions` if wanted.

## FAQ
- Free TTS? No, every line goes through Miragea in your voice.
- No saved voice? A clear error explains how to create one (POST /v1/actors, a voice you own).
- Why short answers? Shorts under about 60 seconds hold viewers; the lint flags long answers.

Credit: Q&A card format is common; code written from scratch.

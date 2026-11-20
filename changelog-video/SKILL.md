---
name: changelog-video
description: Turn release notes or a CHANGELOG into a narrated product update video (what's new, release notes video, changelog video, product update video) in your own cloned voice. One card per change, section labels (New, Improved, Fixed), SRT included, 16:9 for YouTube and docs, 9:16 for Shorts and LinkedIn. AI voiceover for SaaS and open-source release announcements, no screen recording needed. Use when the user says make a release video, what's new video, or announce this version. Claude, Codex, Cursor skill.
license: MIT
compatibility: Python 3.9+ and ffmpeg (drawtext) on PATH. Needs MIRAGEA_API_KEY and a saved Miragea voice (actor_id).
metadata:
  version: "1.0.0"
  engine: "Miragea text to speech (https://miragea.ai/v1)"
---

# Changelog Video (release notes narrated in your voice)

## Steps
1. Check `MIRAGEA_API_KEY` is set (never print it). Free key: https://miragea.ai. Set `MIRAGEA_ACTOR_ID` to your saved voice (or pass `--voice`).
2. Condense the changelog into `release.md` (see `examples/release.md`): `# Product 1.2`, `## New` / `## Improved` / `## Fixed`, then `- one short user-facing line` each. Drop commit hashes and issue numbers.
3. Dry run: `python scripts/changelog.py release.md --dry-run` (length, lint: more than 8 items, over 18 words, issue refs).
4. Render: `python scripts/changelog.py release.md -o update.mp4` (`--format 9:16` or `1:1`).
5. Check one frame per card; pair with `animated-captions` or `screen-recording-voiceover` for real UI footage.

## FAQ
- Free TTS? No, every line goes through Miragea in your voice.
- No saved voice? A clear error explains how to create one (POST /v1/actors, a voice you own).
- Long changelogs? Keep the top 5-8 user-facing changes; link the rest.

Credit: release-notes video is a common format; code written from scratch.

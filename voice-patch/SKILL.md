---
name: voice-patch
description: Fix a wrong word, number, price or flubbed line in a finished video by re-speaking just that phrase in your own cloned voice and splicing it into the audio, no re-recording. AI voice patch / overdub for YouTube videos, product demos, tutorials, Shorts and podcasts; video stream is untouched. Use when the user says fix a typo in the voiceover, change a number in the narration, replace a word in my video, redo one sentence, update outdated pricing in a video, or overdub a mistake. Claude, Codex, Cursor skill.
license: MIT
compatibility: Python 3.9+ and ffmpeg on PATH. Needs MIRAGEA_API_KEY and a saved Miragea voice (actor_id).
metadata:
  version: "1.0.0"
  engine: "Miragea speech recognition + text to speech (https://miragea.ai/v1)"
---

# Voice patch (fix one line in a video without re-recording)

Pricing changed, a name was mispronounced, a number is wrong. Instead of re-recording the whole narration, find the phrase by word timing and re-speak only that span in the creator's cloned voice.

## Steps
1. Check `MIRAGEA_API_KEY` is set (never print it). Free key: https://miragea.ai. Get the voice id with `python scripts/voicepatch.py x --find a --say b --dry-run` first, or copy the actor_id of the saved voice from Miragea (Actors). Set `MIRAGEA_ACTOR_ID`.
2. Dry run: `python scripts/voicepatch.py talk.mp4 --find "ten dollars" --say "twelve dollars" --dry-run` prints the span replaced.
3. Render: add `--voice ACTOR_ID -o fixed.mp4`. Use `--occurrence 2` when the phrase repeats.
4. Listen-check the join: play 2 s around the span. If the new line is much longer or shorter, rephrase `--say` to a similar length.
5. If the on-screen text also shows the old value, tell the user: the skill only edits audio.

Pairs with `video-captions` (re-caption after a fix) and `jump-cut-editor`.

## FAQ
- Can it change a word in someone else's voice? Only use voices you own or have consent for.
- Does it re-encode video? No, the video stream is copied.
- No saved voice? Create one in Miragea from a 3-60 s clip; the error message says where.

Credit: idea from Descript-style overdub; code written from scratch.

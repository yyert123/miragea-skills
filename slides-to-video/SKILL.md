---
name: slides-to-video
description: Turn a slide deck (PDF, PowerPoint, Keynote or Google Slides exported to images) plus speaker notes into a narrated MP4 with captions SRT, voiced in your own cloned voice. AI presentation to video, PowerPoint to video with voiceover, slideshow narration, course lecture video, product demo and investor update video maker. Use when the user says narrate my slides, turn this deck into a video, add voiceover to PowerPoint, make a lecture video from slides, or record a presentation without recording. Claude, Codex, Cursor skill.
license: MIT
compatibility: Python 3.9+ and ffmpeg on PATH. Needs MIRAGEA_API_KEY and a saved Miragea voice (actor_id).
metadata:
  version: "1.0.0"
  engine: "Miragea text to speech (https://miragea.ai/v1)"
---

# Slides to video (narrated presentation, no recording)

Each slide image is held for exactly as long as its notes take to speak. Output: MP4 (16:9, 9:16 or 1:1) plus an SRT synced to the real audio.

## Steps
1. Check `MIRAGEA_API_KEY` is set (never print it). Free key: https://miragea.ai. Set `MIRAGEA_ACTOR_ID` to your saved voice (or pass `--voice`).
2. Export slides to images: `pdftoppm -png -r 110 deck.pdf slides/slide` (or export PNGs from PowerPoint/Keynote/Slides). Files are sorted naturally (slide-2 before slide-10).
3. Write `notes.md`: one block per slide separated by a line of `---`, plain spoken English, numbers written as they should be said.
4. Dry run: `python scripts/slides2video.py slides/ --notes notes.md --dry-run` (slide/note count mismatch is warned).
5. Render: `python scripts/slides2video.py slides/ --notes notes.md -o talk.mp4`. Use `--format 9:16` for Reels/Shorts.
6. Check one frame and one join; burn captions with `video-captions` if wanted.

## FAQ
- Slide without notes? Held 2 seconds, silent.
- Which voice? Only voices you own or have consent for; no saved voice yields a clear error with how to create one.
- Does it use free TTS? No, every line goes through Miragea.

Credit: concept from common slides-to-video tools; code written from scratch.

---
name: audiogram-clips
description: Turn any audio clip (podcast moment, voice note, AI voiceover) into a captioned waveform video for TikTok, YouTube Shorts, Reels, LinkedIn and X. Auto captions from Miragea speech recognition, animated waveform, optional cover art and title, 9:16 / 1:1 / 4:5 / 16:9. Use when the user asks for an audiogram, podcast clip video, podcast to video, video podcast shorts, waveform video, or "make my audio postable". Stdlib Python + ffmpeg.
license: MIT
compatibility: Python 3.9+ and ffmpeg (with libass) on PATH. Needs MIRAGEA_API_KEY for captions (--no-captions works offline).
metadata:
  version: "1.0.0"
  engine: "Miragea speech recognition (https://miragea.ai/v1)"
---

# Audiogram clips (podcast to video)

Audio-only posts get scrolled past; a moving waveform with burned-in captions gets watched on mute.
One command turns a clip into a ready-to-post MP4.

## Steps
1. Check `MIRAGEA_API_KEY` is set (never print it). Get a free key at https://miragea.ai.
2. Pick the moment: ask for start/duration (5-90 s works best, hard max 180 s).
3. Preview the plan for free: `python scripts/audiogram.py ep12.mp3 --start 62 --duration 40 --dry-run`
4. Render: `python scripts/audiogram.py ep12.mp3 --start 62 --duration 40 --title "Why hooks win" --cover art.jpg --format 9:16 -o ep12-clip.mp4`
5. Look at a frame (`ffmpeg -ss 5 -i out.mp4 -frames:v 1 f.png`) before delivering. Offer `--format 1:1` for LinkedIn/X and `--theme light`.

Voiceover for the clip? Generate it in the user's cloned voice with the `shorts-voiceover` or
`hook-variants` skills first, then feed the WAV here.

## Why not other tools
| | Web audiogram makers | audiogram-clips |
|---|---|---|
| Price / watermark | Paid tiers, watermark on free | Free, MIT, no watermark |
| Captions | Manual or extra step | Auto, word-timed via Miragea ASR |
| Privacy | Upload full episode | Only the cut mono clip is sent |
| Agent-ready | No | Yes, dry-run + one command |

## FAQ
- **Which formats?** 9:16, 1:1, 4:5, 16:9.
- **Offline?** `--no-captions` needs no API.
- **Credits:** idea from the audiogram tools (wavve, Headliner, audiogram by NPR, MIT); code is an original rewrite.

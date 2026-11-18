---
name: animated-captions
description: Word-by-word animated captions for TikTok, Reels and YouTube Shorts - the "Hormozi" highlight-the-spoken-word look, karaoke fill, highlighter box and minimal presets. One command transcribes the video with Miragea speech recognition, builds a styled .ass subtitle file where the active word pops in colour, and can burn it into a vertical MP4 (ffmpeg only, no paid caption app, no Remotion). Use when the user asks for animated captions, viral captions, karaoke subtitles, highlighted word captions, auto captions for Shorts, or an Opus Clip / CapCut / Submagic caption style.
license: MIT
compatibility: Python 3.9+ (standard library only) and ffmpeg with libass on PATH. Needs MIRAGEA_API_KEY (or a transcript JSON for offline use).
metadata:
  version: "1.0.0"
  engine: "Miragea speech recognition (https://miragea.ai/v1)"
---

# Animated captions (word highlight, karaoke, Hormozi style)

Turns any talking video into short-form video with captions that follow the voice word by word. The spoken
word changes colour (and pops), the other words of the chunk stay on screen. Output is a normal `.ass` file you
can keep editing, plus an optional burned-in MP4.

## When to use

- "Add animated / viral / Hormozi-style captions", "highlight the word as it is spoken", "karaoke subtitles".
- "Make my Shorts captions look like Submagic / Opus Clip / CapCut" without paying for a caption app.
- Plain subtitles (SRT/VTT for YouTube upload) -> use `video-captions` instead.

## Steps

1. Check `MIRAGEA_API_KEY` is set (never print it). If missing, tell the user to create a key at
   https://miragea.ai and `export MIRAGEA_API_KEY=...`.
2. Run:

   ```bash
   python3 scripts/animated_captions.py clip.mp4 --preset hormozi --burn     # -> clip.ass, clip.animated.mp4
   python3 scripts/animated_captions.py clip.mp4 --preset karaoke            # ASS only, style it in your editor
   python3 scripts/animated_captions.py clip.mp4 --transcript t.json         # offline, no API call
   ```

3. Show the user one frame (`ffmpeg -ss 3 -i clip.animated.mp4 -frames:v 1 f.png`) and look at it yourself before
   handing it over: no clipped words, readable at phone size, clear of the platform UI.
4. If the user wants different wording, edit the transcript JSON text and re-run with `--transcript`.

## Presets

| Preset | Look |
|---|---|
| `hormozi` (default) | 1-3 words, UPPERCASE, white text, active word yellow with a quick pop |
| `karaoke` | up to ~6 words, already-spoken words stay coloured, active word cyan |
| `highlighter` | active word sits on a purple highlighter box |
| `minimal` | thin white text, the spoken word bright, the rest dimmed |

Options: `--active RRGGBB`, `--base RRGGBB`, `--font "Montserrat"` (+ `--fonts-dir` for a folder of font files),
`--margin 0.22` (bottom margin as a share of height, keeps captions above the Shorts/TikTok UI),
`--size 1080x1920` when the input has no video track.

## How it works

- Miragea returns segment timing; `cues.words()` rebuilds whole words and aligns the punctuated text to them.
- Words are grouped into chunks that end at sentence ends and pauses over 0.45 s and always fit 86% of the width.
- Every spoken word becomes one non-overlapping ASS event, so it renders identically in ffmpeg/libass, VLC, and
  can be imported into Premiere/DaVinci/CapCut (ASS support varies there; the burned MP4 always works).
- The transcript is cached next to the video (`<file>.transcript.json`), so re-styling costs nothing.

## Limits

- Word timing is derived from segment timing, so highlights can be off by a fraction of a second on fast speech.
- Fonts: Arial is requested by default; if missing, libass falls back to another sans font. Pass `--font`.
- English-first; other languages work for timing but upper-casing is for Latin scripts.

## Credits

Look and feel inspired by the caption styles popularised by Alex Hormozi videos and tools such as Submagic and
Opus Clip; ASS rendering by libass/ffmpeg. Code is an original rewrite (MIT).

---
name: video-captions
description: Caption any video or audio file in one command. Produces clean, readable SRT and WebVTT subtitles (whole words, 42-char lines, proper timing) and can burn them into an MP4, including big centred 1-3 word "pop" captions for TikTok, Reels and YouTube Shorts. Use when the user asks to add subtitles or captions to a video, make an SRT/VTT file, transcribe a talk or podcast into captions, or burn captions into a short-form video. English-first; speech recognition by Miragea.
license: MIT
compatibility: Python 3.9+ (standard library only) and ffmpeg on PATH. Needs MIRAGEA_API_KEY.
metadata:
  version: "1.0.0"
  engine: "Miragea speech recognition (https://miragea.ai/v1)"
---

# Video captions

One command turns a video (or audio) file into subtitles that are pleasant to read, and optionally into a
captioned MP4. Raw speech-recognition segments often break mid-word ("cen" / "ts") and run too long; this
skill rebuilds whole words and re-flows them into proper cues.

## When to use

- "Add captions / subtitles to this video", "make an SRT for my talk", "burn subtitles in".
- "Make TikTok/Reels/Shorts style captions" -> use `--style shorts --burn`.
- The user needs a `.vtt` for a website `<track>` or YouTube upload.

## Steps

1. Check `MIRAGEA_API_KEY` is set (never print it). If missing, tell the user to create a key at
   https://miragea.ai and `export MIRAGEA_API_KEY=...`.
2. Run the script on the user's file:

   ```bash
   python3 scripts/captions.py path/to/video.mp4                 # -> video.srt + video.vtt
   python3 scripts/captions.py path/to/video.mp4 --burn          # + video.captioned.mp4
   python3 scripts/captions.py path/to/short.mp4 --style shorts --burn   # pop captions, centred
   ```

3. Read the JSON it prints (`srt`, `vtt`, `video`, `cues`) and give the user the paths.
4. If the user wants wording fixed, edit the `.srt` text (keep timestamps) and re-run with `--burn`:
   the transcript is cached in `<file>.transcript.json`, so re-runs cost nothing.

## Options

| Flag | Default | What it does |
|---|---|---|
| `--style standard` | yes | 2 lines x 42 chars, 1-7 s per cue (broadcast conventions) |
| `--style shorts` | | 1-3 words per cue, UPPERCASE, centred when burned |
| `--burn` | off | Writes `<name>.captioned.mp4` (H.264, original audio copied) |
| `--upper` | off | Uppercase standard captions |
| `--out-dir DIR` | next to input | Where outputs go |
| `--force` | off | Ignore cached transcript and re-transcribe |

## Cost and limits

Only a 16 kHz mono audio track is uploaded (not the video), up to 90 minutes / 1 GB per file.
Miragea bills 3 points per second of audio; cached re-runs are free. Check live rates with
`GET https://miragea.ai/v1/capabilities`.

## Troubleshooting

- `ffmpeg not found` -> install ffmpeg (`brew install ffmpeg`, `sudo apt install ffmpeg`, `winget install ffmpeg`).
- `401` -> the key is wrong; `402` -> top up at miragea.ai; `429` -> wait and re-run (safe to retry).
- Captions slightly early/late on music-heavy clips: re-run with `--force` after trimming intros.

See `examples/` for sample output.

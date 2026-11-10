---
name: screen-recording-voiceover
description: Turn a silent screen recording (product demo, tutorial, walkthrough, bug repro) into a narrated video in one command. Finds the steps in the recording, helps write one line per step, voices each line with a saved or cloned voice, starts every line exactly at its step, speeds up or freezes frames automatically when a line runs long ("freeze-sync"), mixes optional ducked music, normalizes loudness and writes SRT/VTT captions (optionally burned in). Use when the user wants to add AI voiceover or narration to a screen recording, demo or tutorial video, sync a script to on-screen actions, or narrate a Screen Studio / Loom / OBS / QuickTime export. English-first; voice by Miragea.
license: MIT
compatibility: Python 3.9+ (standard library only) and ffmpeg on PATH. Needs MIRAGEA_API_KEY and a voice (MIRAGEA_VOICE_ID, or a public reference clip URL).
metadata:
  version: "1.0.0"
  engine: "Miragea text-to-speech (https://miragea.ai/v1)"
---

# Screen recording voiceover

The slow part of narrating a screen recording is not the voice, it is the sync: lining each sentence up
with the click it describes, and fixing the places where the sentence is longer than the action. This
skill does both automatically and never lets narration drift or overlap.

## When to use

- "Add a voiceover to this demo / tutorial / screen recording."
- "I recorded my screen silently, narrate it" or "I don't want to use my own voice / accent."
- "Make the narration match what happens on screen."

## Steps

1. Check `MIRAGEA_API_KEY` is set (never print it). Voice: ask once for the user's Miragea voice id, or a
   public URL of a clip of their voice plus its exact words. Suggest `export MIRAGEA_VOICE_ID=...` so it
   is never asked again. Only clone a voice the user owns or has permission to use.
2. Find the steps and create a script template:

   ```bash
   python3 scripts/scenes.py demo.mp4      # -> demo.frames/*.jpg, demo.frames/steps.json, demo.script.txt
   ```

3. **Look at the frames** in `demo.frames/` (you can read images) and write one clear sentence per step
   into `demo.script.txt` after each timestamp, replacing the `# step` comment. Stay within the
   `~N words` hint so the line fits before the next step. Merge, move or delete steps freely. If the user
   gave their own script, put its sentences at the matching timestamps instead.
4. Check the timing without spending anything:

   ```bash
   python3 scripts/voiceover.py demo.mp4 demo.script.txt --dry-run
   ```

   Shorten any line marked `will freeze` if the user wants zero frozen frames.
5. Render:

   ```bash
   python3 scripts/voiceover.py demo.mp4 demo.script.txt --voice VOICE_ID            # captions as files
   python3 scripts/voiceover.py demo.mp4 demo.script.txt --burn --music bed.mp3      # burned captions + ducked music
   ```

6. Give the user the paths from the printed JSON: `video` (narrated MP4), `voice_track` (WAV for their
   editor), `srt`/`vtt`. Mention `frozen_seconds` if it is above zero.
7. To change a line, edit the script and run step 5 again: unchanged lines come from the cache for free.

## Script format

```text
[00:00] Welcome to Acme. Here is the dashboard you see after signing in.
[00:04] Click New Project, type a name, and choose the team that should own it.
[01:02.5] That's it. Your project is ready.
```

Accepted timestamps: `[mm:ss]`, `[h:mm:ss]`, `mm:ss.s`, `12.5s`. Lines starting with `#` are comments.

## How the sync works

- Each line starts exactly at its timestamp; 0.25 s of breathing room is kept before the next step.
- A line longer than its slot is sped up, at most `--max-speed` (default 1.15x, still natural).
- If it still does not fit, the video holds the last frame of that step until the sentence ends, then
  continues. Later lines shift by the same amount, so sync is never lost.
- Captions are timed from the actual spoken length of each line (2 lines x 42 characters max).
- Loudness is normalized to about -16 LUFS (YouTube/web standard). Music, if given, is ducked under speech.

## Options

| Flag | Default | What it does |
|---|---|---|
| `--voice ID` / `--ref-url URL --ref-text TEXT` | env | Saved Miragea voice, or clone from a public clip (exact text = cheaper 1x rate) |
| `--model` | `expressive` | or `standard` |
| `--max-speed` | 1.15 | Max speed-up before freezing frames |
| `--burn` | off | Burn captions into the video |
| `--music FILE` | none | Background music, looped and auto-ducked |
| `--keep-audio` | off | Keep the recording's own sound, quietly, under the voice |
| `--dry-run` | | Show the slot plan with an estimated speaking rate; no API calls |
| `-o FILE` | `VIDEO.voiceover.mp4` | Output path; the original is never modified |

## Cost and limits

Speech is billed per character by Miragea (1x with a saved voice or exact reference text; live rates at
`GET https://miragea.ai/v1/capabilities`). A 3-minute demo is usually 2,000-3,000 characters. Each line
must be under 2,000 characters. Reference clips must be public URLs until Miragea's upload endpoint ships.

## Troubleshooting

- `no timestamp` / `not after the previous line` -> fix the script line named in the error.
- `no voice chosen` -> pass `--voice` or set `MIRAGEA_VOICE_ID`.
- `401` key wrong, `402` top up at miragea.ai, `429` wait and re-run (cached lines are not re-billed).
- Too many or too few steps from `scenes.py` -> `--threshold 0.02` (more) / `0.08` (fewer), `--min-gap`.

See `examples/` for a real script, the plan JSON and the captions it produced.

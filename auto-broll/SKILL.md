---
name: auto-broll
description: Automatic B-roll for talking-head videos, podcasts, tutorials and faceless YouTube/TikTok videos, for Claude Code, Codex and Cursor. The agent reads a timestamped transcript and picks a cutaway for each concrete moment (things, actions, numbers, places); the script lands every cut on the exact spoken word, keeps the speaker's audio untouched, covers the frame (16:9 or 9:16), adds a slow Ken Burns push on stills, warns about flash cuts, covered hooks and too much B-roll, and exports the MP4 plus a CMX 3600 EDL for Premiere Pro, DaVinci Resolve and Avid. Uses your own clips and images, or free Pexels stock. Faceless mode voices a script in your own cloned voice first, then covers it end to end with B-roll. No extra LLM key. Use when the user asks to add B-roll, cutaways or stock footage to a video, make a talking head less boring, find B-roll for a script, auto-edit a podcast clip, or make a faceless video with B-roll and voiceover. Speech recognition and voice by Miragea; stdlib Python + ffmpeg.
license: MIT
compatibility: Python 3.9+ and ffmpeg on PATH. Needs MIRAGEA_API_KEY. Faceless mode needs a voice (MIRAGEA_VOICE_ID, or MIRAGEA_REF_URL + MIRAGEA_REF_TEXT). Stock footage needs a free PEXELS_API_KEY (optional).
metadata:
  version: "1.0.0"
  engine: "Miragea speech recognition + text-to-speech (https://miragea.ai/v1)"
---

# Auto B-roll (cut on the word)

A video (or a script) in, the same video with B-roll cut in on the words that call for it. You (the
agent) are the editor: you read each line with its word timings and decide what to show. The script
does the frame-accurate work: word anchoring, cover-cropping, timing rules, mixing, export.

## When to use
- "Add B-roll to my talking-head video / podcast clip / course lesson."
- "Find cutaways for this script and drop them on the right words."
- "Make a faceless video from this script with my voice and B-roll."
- "Give me an EDL of the B-roll so I can finish in Premiere / Resolve."

## Steps
1. Check `MIRAGEA_API_KEY` is set (never print it) and `ffmpeg -version` works.
2. Prepare the plan:
   - Talking head / podcast / screen recording: `python scripts/broll.py prep talk.mp4 --library broll/`
   - Faceless (no footage of a speaker): `python scripts/broll.py prep --script script.txt --library broll/ --vertical`
     voices the script in the creator's Miragea voice (`MIRAGEA_VOICE_ID`, or `MIRAGEA_REF_URL` +
     `MIRAGEA_REF_TEXT`; only a voice they own or may use) and writes `script.narration.wav`.
   Either way it writes `<name>.broll.json`: sentence `lines` with per-word start times, and the
   `library` of the user's clips (with lengths). The transcript is cached and shared with the
   video-captions, video-to-shorts and video-dubbing skills, so it is billed once.
3. Plan the cutaways: add one object per shot to `"cutaways"`:
   `{"line": 3, "on": "espresso machine", "clip": "broll/espresso.mp4", "dur": 2.5}`
   - `on`: the word or phrase the cut lands on; it must be in that line (numbers match either way:
     "ninety three" = "93"). `clip`: a library file, any path, or `"pexels:<search words>"`.
     `dur` optional (default: until the line ends, 1.2-4 s). `clip_start`: in-point inside a clip.
   - Show what is said: concrete nouns, actions, numbers, places, products, screens. Do not illustrate
     opinions or filler. Open the clips' first frames if unsure what they show.
   - Talking head: cover 20-40% of the runtime, never the first 2 s (the hook), keep at least 1 s of
     speaker between shots. Faceless: a new shot every 2-4 s; each runs until the next one.
4. Check for free: `python scripts/broll.py check talk.broll.json`
   `!` = must fix (word not found, missing clip, stock not fetched). `~` = advice (flash cut,
   covered hook, back-to-back cutaways, clip shorter than its slot). Re-run until it exits 0.
5. Stock (optional): `python scripts/broll.py fetch talk.broll.json` downloads each `pexels:` query
   at the right orientation (free key from pexels.com/api) and records credits in `broll_stock/CREDITS.txt`.
6. Render: `python scripts/broll.py render talk.mp4 talk.broll.json -o broll_out`
   Options: `--fade 0.12` (soft edges instead of a hard cut), `--music bed.mp3` (ducked under the
   voice), `--lufs -14` (talking head audio is left untouched unless set; faceless defaults to -14),
   `--vertical` (faceless 1080x1920), `--skip-bad`, `--dry-run`.
7. Report: the MP4, the EDL, the number of cutaways, coverage, and any `~` advice you chose to keep.

## Output (in `broll_out/`)
- `talk.broll.mp4`: the original picture with cutaways on their words; the speaker's audio is the
  original track, never re-timed.
- `talk.broll.edl`: CMX 3600 EDL of the cutaways at their timeline positions (File > Import in
  Premiere Pro / Resolve), with the source clip name and anchor word as comments.
- `talk.broll.manifest.json`: every cutaway's start, length, word, clip and warnings.

## Honest limits
- The agent chooses footage from what it can see (file names, first frames, your descriptions); it
  does not generate video. Pair it with your own clips, screen captures or a stock library.
- One B-roll layer, full frame. No picture-in-picture or split screen yet.
- Speech recognition is cloud-based (Miragea); only a 16 kHz mono audio track is uploaded, never the
  video. Stock clips come from Pexels under the Pexels license.
